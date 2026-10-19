"""Paid-job recovery with the real worker, transport and durable journal, offline."""
import json
import os
from contextlib import ExitStack
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import main
from fal_provider import FalTaskJournal
from gpt25_provider import generation_payload
from gpt25_recovery import confirm_expired_generation_retries, expired_generation_retries


PROMPT = "A ceramic cup"
IMAGE_URL = "https://images.example.org/result.png"


def worker(directory, provider="piapi", **settings):
    result = main.WorkerThread("mode1_generate_only", str(directory), {
        f"{provider}_api_key": "DUMMY_KEY",
        "text_generation_model": f"{provider}/gpt-image-2.5-flare",
        "text_generation_ratio": "1:1", "text_generation_resolution": "1K",
        "upscale": False, "remove_bg": False, "gpt25_cost_confirmed": True,
        "retries": 0,
        **settings,
    }, generated_prompts=[{"prompt": PROMPT, "references": []}])
    result._set_diagnostic_context(1, 1, "generation")
    return result


def add_record(subject, task_id, status="expired"):
    provider = "piapi" if subject.piapi_api_key else "atlascloud"
    model = subject.text_generation_model
    fingerprint = subject._paid_task_fingerprint(generation_payload(model, PROMPT, "1:1", "1K"))
    return subject.gpt25_task_journals[provider].upsert(
        task_id, subject._task_operation_key("generation"), model, status,
        input_fingerprint=fingerprint,
    )


class Response(BytesIO):
    status = 200

    def __init__(self, payload, after_read=None):
        super().__init__(json.dumps(payload).encode())
        self.after_read = after_read

    def read(self, *args):
        value = super().read(*args)
        if self.after_read:
            self.after_read()
        return value


def network(subject, provider="piapi", poll_error=None):
    calls = []

    def open_request(request, **_kwargs):
        calls.append(request.get_method())
        if request.get_method() == "POST":
            return Response({"task_id": "accepted"} if provider == "piapi"
                            else {"data": {"id": "accepted"}})
        if poll_error:
            raise HTTPError(request.full_url, poll_error, "controlled error", {}, BytesIO())
        return Response({"status": "completed", "output": {"data": [{"url": IMAGE_URL}]}}
                        if provider == "piapi" else
                        {"data": {"status": "completed", "outputs": [IMAGE_URL]}})

    return calls, open_request


def test_accept_submission_replaces_guard_in_one_journal_write(tmp_path, monkeypatch):
    journal = FalTaskJournal(tmp_path / "jobs.json")
    journal.upsert("unconfirmed_guard", "generation:1", "piapi/gpt-image-2.5-flare", "submitting")
    writes = []
    original_write = journal._write

    def track_write(records):
        writes.append(tuple(records))
        original_write(records)

    monkeypatch.setattr(journal, "_write", track_write)
    journal.accept_submission("unconfirmed_guard", "accepted")
    assert writes == [("accepted",)]
    assert [(record.request_id, record.status) for record in journal.pending()] == [("accepted", "queued")]


@pytest.mark.parametrize("after_replace", [False, True])
def test_interrupted_acceptance_retains_guard_or_accepted_id(tmp_path, after_replace):
    journal = FalTaskJournal(tmp_path / "jobs.json")
    journal.upsert("unconfirmed_guard", "generation:1", "piapi/gpt-image-2.5-flare", "submitting")
    original_replace = main.os.replace

    def interrupted_replace(source, target):
        if after_replace:
            original_replace(source, target)
        raise OSError("controlled interruption")

    with patch("fal_provider.os.replace", side_effect=interrupted_replace), pytest.raises(OSError):
        journal.accept_submission("unconfirmed_guard", "accepted")
    ids = [record.request_id for record in FalTaskJournal(journal.path).pending()]
    assert ids == (["accepted"] if after_replace else ["unconfirmed_guard"])


@pytest.mark.parametrize("provider", ["atlascloud", "piapi"])
def test_legacy_split_journal_recovers_known_id_without_post(tmp_path, provider):
    subject = worker(tmp_path, provider)
    add_record(subject, "unconfirmed_guard", "submitting")
    add_record(subject, "accepted", "queued")
    calls, opener = network(subject, provider)
    with patch("main.open_url_secure", side_effect=opener):
        assert subject._gpt25_generate_image(PROMPT, subject.text_generation_model) == IMAGE_URL
    assert calls == ["GET"]


@pytest.mark.parametrize("provider", ["atlascloud", "piapi"])
def test_stop_before_transport_allows_restart_without_unknown_guard(tmp_path, monkeypatch, provider):
    subject = worker(tmp_path, provider)
    journal = subject.gpt25_task_journals[provider]
    original_upsert = journal.upsert

    def save_then_stop(*args, **kwargs):
        record = original_upsert(*args, **kwargs)
        subject.stop()
        return record

    monkeypatch.setattr(journal, "upsert", save_then_stop)
    with patch("main.open_url_secure") as opened, pytest.raises(main.ProcessingCancelled):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert not opened.called
    assert journal.pending() == ()
    restarted = worker(tmp_path, provider)
    calls, opener = network(restarted, provider)
    with patch("main.open_url_secure", side_effect=opener):
        assert restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model) == IMAGE_URL
    assert calls == ["POST", "GET"]


def test_stop_after_transport_keeps_unknown_guard_and_never_reposts(tmp_path):
    subject = worker(tmp_path)
    response = Response({"task_id": "accepted"}, after_read=subject.stop)
    with patch("main.open_url_secure", return_value=response), pytest.raises(main.ProcessingCancelled):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert subject.gpt25_task_journals["piapi"].pending()[0].request_id.startswith("unconfirmed_")
    restarted = worker(tmp_path)
    with patch("main.open_url_secure") as opened, pytest.raises(RuntimeError, match="двойного списания"):
        restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model)
    assert not opened.called


@pytest.mark.parametrize("code", [404, 410])
def test_missing_result_requires_confirmation_instead_of_repeated_get(tmp_path, code):
    subject = worker(tmp_path)
    add_record(subject, "old", "queued")
    calls, opener = network(subject, poll_error=code)
    with patch("main.open_url_secure", side_effect=opener), pytest.raises(RuntimeError, match="новой платной"):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert calls == ["GET"]
    assert subject.gpt25_task_journals["piapi"].pending()[0].status == "expired"
    restarted = worker(tmp_path)
    with patch("main.open_url_secure") as opened, pytest.raises(RuntimeError, match="новой платной"):
        restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model)
    assert not opened.called


def test_specific_expired_task_confirmation_submits_once_then_recovers_new_job(tmp_path):
    first = worker(tmp_path)
    add_record(first, "old")
    approved = worker(tmp_path, gpt25_expired_task_confirmations=["piapi:old"])
    calls, opener = network(approved)
    with patch("main.open_url_secure", side_effect=opener):
        assert approved._gpt25_generate_image(PROMPT, approved.text_generation_model) == IMAGE_URL
    assert calls == ["POST", "GET"]
    records = approved.gpt25_task_journals["piapi"]._read()
    assert records["old"].status == "superseded"
    restarted = worker(tmp_path)
    calls, opener = network(restarted)
    with patch("main.open_url_secure", side_effect=opener):
        assert restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model) == IMAGE_URL
    assert calls == ["GET"]


def test_unrelated_confirmation_cannot_replace_expired_task(tmp_path):
    subject = worker(tmp_path, gpt25_expired_task_confirmations=["piapi:another"])
    add_record(subject, "old")
    with patch("main.open_url_secure") as opened, pytest.raises(RuntimeError, match="новой платной"):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert not opened.called


@pytest.mark.parametrize("provider", ["atlascloud", "piapi"])
@pytest.mark.parametrize("code", [401, 403, 429, 500])
def test_transient_or_auth_poll_failure_keeps_paid_receipt(tmp_path, provider, code):
    subject = worker(tmp_path, provider)
    add_record(subject, "accepted", "queued")
    calls, opener = network(subject, provider, poll_error=code)
    with patch("main.open_url_secure", side_effect=opener), pytest.raises(RuntimeError, match="без новой оплаты"):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert calls == ["GET"]
    assert subject.gpt25_task_journals[provider].pending()[0].status == "poll_deferred"
    assert expired_generation_retries(tmp_path, subject.settings, subject.generated_prompts) == ()


def test_confirmation_discovery_preserves_project_item_and_payload_scopes(tmp_path):
    subject = worker(tmp_path, task_item_indices=[7])
    add_record(subject, "old")
    assert expired_generation_retries(tmp_path, subject.settings, subject.generated_prompts) == ("piapi:old",)
    assert expired_generation_retries(tmp_path, subject.settings, subject.generated_prompts, project_id="other-project") == ()
    for changed in ({"task_item_indices": [8]}, {"text_generation_ratio": "2:3"},
                    {"text_generation_model": "piapi/gpt-image-2.5-sunburst"}):
        assert expired_generation_retries(tmp_path, {**subject.settings, **changed}, subject.generated_prompts) == ()
    assert expired_generation_retries(tmp_path, subject.settings, [{"prompt": "Another cup", "references": []}]) == ()
    assert expired_generation_retries(tmp_path, subject.settings, [{"prompt": PROMPT, "references": ["reference.png"]}]) == ()


def test_unknown_replacement_is_not_offered_for_another_paid_retry(tmp_path):
    subject = worker(tmp_path, gpt25_expired_task_confirmations=["piapi:old"])
    add_record(subject, "old")
    add_record(subject, "unconfirmed_new", "submitting")
    assert expired_generation_retries(tmp_path, subject.settings, subject.generated_prompts) == ()
    with patch("main.open_url_secure") as opened, pytest.raises(RuntimeError, match="двойного списания"):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert not opened.called


def test_legacy_unindexed_expired_receipt_can_be_replaced(tmp_path):
    subject = worker(tmp_path, gpt25_expired_task_confirmations=["piapi:old"])
    record = add_record(subject, "old")
    subject.gpt25_task_journals["piapi"].upsert(
        "old", "generation", record.model_id, "expired", input_fingerprint=record.input_fingerprint,
    )
    calls, opener = network(subject)
    with patch("main.open_url_secure", side_effect=opener):
        assert subject._gpt25_generate_image(PROMPT, subject.text_generation_model) == IMAGE_URL
    assert calls == ["POST", "GET"]


@pytest.mark.parametrize("answer", [False, True])
def test_core_gateway_requires_fresh_user_consent_for_exact_expired_task(tmp_path, answer):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from studio_image_run_services import CoreImageRunGateway, ImageRunGatewayError
    from v3_flow_runtime import FlowRunRequest

    app = QApplication.instance() or QApplication([])
    previous = worker(tmp_path)
    add_record(previous, "old")
    settings = {key: value for key, value in previous.settings.items() if "api_key" not in key}
    # A saved plan or module cannot grant itself replacement consent.
    settings["gpt25_expired_task_confirmations"] = ["piapi:old"]
    request = FlowRunRequest("mode1_generate_only", str(tmp_path), settings, previous.generated_prompts)
    created = []

    def factory(**kwargs):
        instance = main.WorkerThread(**kwargs)
        instance._set_diagnostic_context(1, 1, "generation")
        created.append(instance)
        return instance

    gateway = CoreImageRunGateway(runtime_settings_provider=lambda: {"piapi_api_key": "DUMMY_KEY"},
                                  authorization_provider=lambda: None, run_preparer=lambda: None,
                                  worker_factory=factory)
    response = QMessageBox.StandardButton.Yes if answer else QMessageBox.StandardButton.No
    with patch.object(QMessageBox, "question", return_value=response) as question:
        if answer:
            gateway.launch(request)
        else:
            with pytest.raises(ImageRunGatewayError, match="отменена"):
                gateway.launch(request)
    question.assert_called_once()
    assert question.call_args.args[-1] == QMessageBox.StandardButton.No
    assert "новой оплаты" in question.call_args.args[2]
    assert PROMPT not in question.call_args.args[2] and "old" not in question.call_args.args[2]
    assert len(created) == int(answer)
    if answer:
        calls, opener = network(created[0])
        with patch("main.open_url_secure", side_effect=opener):
            assert created[0]._gpt25_generate_image(PROMPT, created[0].text_generation_model) == IMAGE_URL
        assert calls == ["POST", "GET"]
    else:
        assert previous.gpt25_task_journals["piapi"].pending()[0].status == "expired"
    app.processEvents()


def test_regular_generation_never_opens_expired_task_dialog(tmp_path):
    subject = worker(tmp_path)
    with patch("PyQt6.QtWidgets.QMessageBox.question") as question:
        assert confirm_expired_generation_retries(tmp_path, subject.settings, subject.generated_prompts) == ()
    assert not question.called


def test_launch_dialog_pre_approval_skips_second_paid_question(tmp_path):
    from PyQt6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    previous = worker(tmp_path)
    add_record(previous, "old")
    approvals = expired_generation_retries(tmp_path, previous.settings, previous.generated_prompts)
    assert len(approvals) == 1
    with patch("PyQt6.QtWidgets.QMessageBox.question") as question:
        confirmed = confirm_expired_generation_retries(
            tmp_path, previous.settings, previous.generated_prompts, pre_approved=approvals,
        )
    assert confirmed == approvals
    assert not question.called

    response = QMessageBox.StandardButton.No
    with patch("PyQt6.QtWidgets.QMessageBox.question", return_value=response) as question:
        mismatched = confirm_expired_generation_retries(
            tmp_path, previous.settings, previous.generated_prompts,
            pre_approved=("piapi:other",),
        )
    assert mismatched is None
    assert question.called


@pytest.mark.parametrize("after_replace", [False, True])
def test_crash_after_paid_post_never_submits_again_on_restart(tmp_path, after_replace):
    subject = worker(tmp_path)
    calls, opener = network(subject)
    original_replace = main.os.replace
    writes = []

    def interrupt_acceptance(source, target):
        writes.append(target)
        if len(writes) == 2:
            if after_replace:
                original_replace(source, target)
            raise OSError("controlled interruption after paid POST")
        original_replace(source, target)

    with patch("main.open_url_secure", side_effect=opener), \
            patch("fal_provider.os.replace", side_effect=interrupt_acceptance), pytest.raises(OSError):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert calls == ["POST"]
    restarted = worker(tmp_path)
    calls, opener = network(restarted)
    with patch("main.open_url_secure", side_effect=opener):
        if after_replace:
            assert restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model) == IMAGE_URL
            assert calls == ["GET"]
        else:
            with pytest.raises(RuntimeError, match="двойного списания"):
                restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model)
            assert not calls


@pytest.mark.parametrize("model", [
    "atlascloud/gpt-image-2.5-flare", "atlascloud/gpt-image-2.5-sunburst",
    "piapi/gpt-image-2.5-flare", "piapi/gpt-image-2.5-sunburst", "piapi/gpt-image-2.5",
])
def test_all_models_produce_final_png_and_close_receipt(tmp_path, model, monkeypatch):
    provider = model.split("/", 1)[0]
    profile = {"text_generation_ratio": "auto", "text_generation_resolution": "auto"} \
        if model == "piapi/gpt-image-2.5" else {}
    subject = worker(tmp_path, provider, text_generation_model=model, **profile)
    calls, opener = network(subject, provider)
    monkeypatch.setattr(subject, "_download_file",
                        lambda url, path: main.Image.new("RGBA", (8, 8), "cyan").save(path))
    raw = tmp_path / "raw"
    raw.mkdir()
    output = tmp_path / "finished.png"
    with patch("main.open_url_secure", side_effect=opener):
        subject._generate_entry(1, 1, {"prompt": PROMPT, "references": []}, str(raw), str(output), False)
    with main.Image.open(output) as image:
        assert image.size == (8, 8) and image.format == "PNG"
    assert calls == ["POST", "GET"]
    assert subject.gpt25_task_journals[provider].pending() == ()


@pytest.mark.parametrize("answer", [False, True, "error"])
def test_legacy_window_checks_expired_receipt_before_launch(tmp_path, monkeypatch, answer):
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from tests.test_v3_provider_settings import V3ProviderSettingsTests

    app = QApplication.instance() or QApplication([])
    previous = worker(tmp_path)
    add_record(previous, "old")
    with ExitStack() as stack:
        for isolated in V3ProviderSettingsTests().isolated_paths(tmp_path):
            stack.enter_context(isolated)
        stack.enter_context(patch.object(main.ProviderCredentialStore, "load", return_value={"piapi_api_key": "DUMMY_KEY"}))
        stack.enter_context(patch.object(main.ProviderCredentialStore, "save"))
        window = main.MainWindow()
        try:
            window.work_dir = str(tmp_path)
            window.radio_run_generate.setChecked(True)
            window.text_generation_model_combo.setCurrentIndex(
                window.text_generation_model_combo.findData(previous.text_generation_model))
            window.text_ratio_combo.setCurrentText("1:1")
            window.text_resolution_combo.setCurrentText("1K")
            monkeypatch.setattr(window, "get_list_mode_prompts", lambda: previous.generated_prompts)
            if answer == "error":
                def fail_confirmation(*args, **kwargs):
                    raise ValueError("DUMMY_KEY invalid")

                monkeypatch.setattr(main, "confirm_expired_generation_retries", fail_confirmation)
            responses = [QMessageBox.StandardButton.Yes,
                         QMessageBox.StandardButton.Yes if answer else QMessageBox.StandardButton.No]
            fake = SimpleNamespace(isRunning=lambda: False, stop=lambda: None)
            with patch.object(QMessageBox, "question", side_effect=responses) as question, \
                    patch.object(QMessageBox, "warning") as warning, \
                    patch("main.launch_worker", return_value=fake) as launch:
                window.start_work()
            if answer == "error":
                assert not launch.called and warning.called
                assert "DUMMY_KEY" not in warning.call_args.args[2]
            else:
                assert question.call_count == 2
                assert launch.called == answer
                if answer:
                    assert launch.call_args.kwargs["settings"]["gpt25_expired_task_confirmations"] == ("piapi:old",)
                assert not warning.called
        finally:
            window.settings_save_timer.stop()
            window.api_key_mask_timer.stop()
            window.deleteLater()
            app.processEvents()


def test_real_qt_cancel_button_preserves_expired_receipt(tmp_path):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QMessageBox

    app = QApplication.instance() or QApplication([])
    subject = worker(tmp_path)
    add_record(subject, "old")
    observed = []

    def cancel_dialog():
        dialog = next(widget for widget in app.topLevelWidgets() if isinstance(widget, QMessageBox))
        observed.append(dialog.defaultButton() == dialog.button(QMessageBox.StandardButton.No))
        dialog.grab().save(str(tmp_path / "expired-dialog.png"))
        dialog.button(QMessageBox.StandardButton.No).click()

    QTimer.singleShot(0, cancel_dialog)
    assert confirm_expired_generation_retries(tmp_path, subject.settings, subject.generated_prompts) is None
    assert observed == [True]
    assert subject.gpt25_task_journals["piapi"].pending()[0].status == "expired"


@pytest.mark.parametrize("code,rejected", [(403, True), (429, True), (500, False), (504, False)])
def test_paid_post_is_never_retried_by_transport(tmp_path, code, rejected):
    subject = worker(tmp_path, retries=5)
    calls = []

    def reject_post(request, **kwargs):
        calls.append(request.get_method())
        raise HTTPError(request.full_url, code, "controlled submit failure", {}, BytesIO())

    with patch("main.open_url_secure", side_effect=reject_post), pytest.raises(RuntimeError):
        subject._gpt25_generate_image(PROMPT, subject.text_generation_model)
    assert calls == ["POST"]
    assert bool(subject.gpt25_task_journals["piapi"].pending()) != rejected
    if not rejected:
        restarted = worker(tmp_path)
        with patch("main.open_url_secure") as opened, pytest.raises(RuntimeError, match="двойного списания"):
            restarted._gpt25_generate_image(PROMPT, restarted.text_generation_model)
        assert not opened.called
