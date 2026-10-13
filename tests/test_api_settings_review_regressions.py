"""Core settings admission and responsive balance checks, with no live API calls."""
import threading
import time

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QThreadPool, QTimer
from PyQt6.QtWidgets import QApplication

from main import WorkerThread
from studio_image_run_services import CoreImageRunGateway
from v3_flow_runtime import FlowRunRequest
from v3_api_settings import ApiSettingsDialog


def pump_until(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.001)
    assert predicate()


@pytest.mark.parametrize("limit", range(1, 6))
@pytest.mark.parametrize("processing", [False, True])
def test_core_limit_reaches_real_worker_and_executor(tmp_path, limit, processing):
    app = QApplication.instance() or QApplication([])
    workers = []

    def factory(**kwargs):
        worker = WorkerThread(**kwargs)
        workers.append(worker)
        return worker

    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {
            "api_concurrency": limit, "piapi_api_key": "dummy",
            "photoroom_api_key": "dummy",
        },
        authorization_provider=lambda: None, run_preparer=lambda: None,
        worker_factory=factory,
    )
    request = FlowRunRequest(
        mode="mode2_process" if processing else "mode1_generate_only",
        work_dir=str(tmp_path),
        settings={"text_generation_model": "piapi/gpt-image-2.5-flare",
                  "remove_bg": processing, "remove_bg_provider": "photoroom",
                  "api_concurrency": 3},  # stale plan must not override Core
        generated_prompts=[{"prompt": str(i), "references": []} for i in range(5)],
        selected_files=[str(tmp_path / f"input-{i}.png") for i in range(5)] if processing else [],
    )
    handle = gateway.launch(request)
    worker = workers[0]
    assert worker.api_concurrency == limit
    assert request.settings["api_concurrency"] == 3
    active = peak = 0
    lock = threading.Lock()
    first_wave = threading.Event()

    def item(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == limit:
                first_wave.set()
        assert first_wave.wait(3)
        with lock:
            active -= 1
        return str(tmp_path / "dummy.png")

    if processing:
        worker._process_file_entry = item
        worker._mode2_process_files_parallel(str(tmp_path), str(tmp_path), emit_final=False)
    else:
        worker._generate_entry = item
        worker._mode1_generate_parallel(emit_final=False)
    assert first_wave.is_set()
    assert peak == limit


def test_legacy_limits_survive_core_enrichment():
    from v3_image_worker_settings import enrich_image_worker_settings
    settings = enrich_image_worker_settings({}, {
        "generation_concurrency": 1, "photoroom_concurrency": 2, "fal_concurrency": 3,
    })
    assert "api_concurrency" not in settings
    assert settings["kie_concurrency"] == 1
    assert settings["photoroom_concurrency"] == 2
    assert settings["fal_concurrency"] == 3


@pytest.mark.parametrize("limit", [1, 5])
def test_saved_shared_limit_reaches_gateway_after_application_reopen(tmp_path, monkeypatch, limit):
    from v3_mode_selection import V3ApplicationView
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("v3_api_settings.load_credentials", lambda: {})
    monkeypatch.setattr("v3_api_settings.save_credentials", lambda values: None)

    def save_dialog(dialog):
        dialog.api_concurrency_combo.setCurrentIndex(dialog.api_concurrency_combo.findData(limit))
        dialog._save()
        return dialog.result()

    monkeypatch.setattr(ApiSettingsDialog, "exec", save_dialog)
    draft_path = tmp_path / "project_state.json"
    view = V3ApplicationView(draft_path=draft_path)
    view._show_api_settings()
    view.close()
    reopened = V3ApplicationView(
        draft_path=draft_path,
        runtime_settings_provider=lambda: {"api_concurrency": 3, "piapi_api_key": "dummy"},
    )
    try:
        assert reopened._runtime_settings()["api_concurrency"] == limit
        gateway = CoreImageRunGateway(
            runtime_settings_provider=reopened._runtime_settings,
            authorization_provider=lambda: None, run_preparer=lambda: None,
            worker_factory=lambda **kwargs: WorkerThread(**kwargs),
        )
        request = FlowRunRequest(
            mode="mode1_generate_only", work_dir=str(tmp_path),
            settings={"text_generation_model": "piapi/gpt-image-2.5-flare"},
            generated_prompts=[{"prompt": "test", "references": []}],
        )
        enriched = gateway._enriched_request(request, gateway._runtime_snapshot())
        worker = WorkerThread(**enriched.worker_kwargs())
        assert worker._remote_worker_limit(include_generation=True, include_processing=False) == limit
    finally:
        reopened.close()
        view.deleteLater()
        reopened.deleteLater()
        app.processEvents()


@pytest.mark.parametrize("destroy", [False, True])
def test_balance_does_not_block_events_and_survives_dialog_close(monkeypatch, destroy):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("v3_api_settings.load_credentials", lambda: {})
    entered, release, returned = (threading.Event() for _ in range(3))
    calls = []
    ui_thread = threading.get_ident()

    def balance(provider, key):
        calls.append(threading.get_ident())
        entered.set()
        release.wait(2)
        returned.set()
        return "Баланс PiAPI: 1.00 USD"

    monkeypatch.setattr("v3_api_settings.check_provider_balance", balance)
    dialog = ApiSettingsDialog({"piapi_api_key": "dummy"})
    dialog.show()
    ticks = []
    QTimer.singleShot(0, lambda: ticks.append(True))
    try:
        dialog.piapi_balance_button.click()
        assert entered.wait(1)
        assert calls == [calls[0]] and calls[0] != ui_thread
        assert not dialog.piapi_balance_button.isEnabled()
        pump_until(app, lambda: bool(ticks))
        assert not returned.is_set()
        dialog._check_external_balance("atlascloud", "dummy")
        assert len(calls) == 1
        if destroy:
            dialog.close()
            dialog.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            assert sip.isdeleted(dialog)
        release.set()
        assert returned.wait(1)
        assert QThreadPool.globalInstance().waitForDone(1000)
        if not destroy:
            pump_until(app, lambda: dialog.piapi_balance_button.isEnabled())
            assert dialog.status.text() == "Баланс PiAPI: 1.00 USD"
            assert dialog.atlascloud_balance_button.isEnabled()
        app.processEvents()
    finally:
        release.set()
        if not sip.isdeleted(dialog):
            dialog.close()
