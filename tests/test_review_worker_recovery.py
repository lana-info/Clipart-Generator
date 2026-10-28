"""Exercise queue retries through real workers, with only provider I/O stubbed."""
import json
from pathlib import Path
from types import MethodType

import pytest
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from main import WorkerThread
from v3_flow_runtime import FlowRunRequest
from v3_project_state import ProjectMode
from v3_run_queue import RunItemStatus, RunQueueSession


@pytest.fixture(scope="module", autouse=True)
def app():
    return QApplication.instance() or QApplication([])


def request_for(root, prompts, **settings):
    return FlowRunRequest("mode1_generate_only", str(root), {
        "kie_api_key": "fixture-only", "kie_concurrency": 1,
        "generation_launch_interval": 0, "remove_bg": False,
        "upscale": False, "upscale_after": False,
        "text_generation_model": "google/imagen4-fast",
        "output_dir": str(root / "workspace" / "output"),
        "workspace_root": str(root / "workspace"), **settings,
    }, [{"prompt": prompt, "references": [], "result_kind": "background"}
        for prompt in prompts])


def attach(worker, session):
    worker.item_progress.connect(session.handle_item_progress, Qt.ConnectionType.DirectConnection)
    worker.diagnostic.connect(session.handle_diagnostic, Qt.ConnectionType.DirectConnection)
    worker.completed.connect(lambda _message: session.handle_finished(), Qt.ConnectionType.DirectConnection)
    worker.error.connect(session.handle_fatal_error, Qt.ConnectionType.DirectConnection)


def download(_worker, _url, path):
    Image.new("RGB", (32, 32), "blue").save(path)


def test_subset_retry_resumes_accepted_second_task_without_another_post(tmp_path):
    request = request_for(tmp_path, ["object A", "object B"])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    creates, polls = [], []

    def configure(worker, first):
        def transport(current, url, method="GET", payload=None, **_kwargs):
            if method == "POST" and url.endswith("createTask"):
                task = f"stub-{len(creates) + 1}"
                creates.append((task, payload["input"]["prompt"]))
                if first and payload["input"]["prompt"] == "object B":
                    current.generation_wait_timeout = 0
                return {"code": 200, "data": {"taskId": task}}
            if method == "GET" and "/recordInfo?" in url:
                polls.append(url.split("taskId=")[1])
                return {"code": 200, "data": {"state": "success", "resultJson":
                    json.dumps({"resultUrls": ["https://fixture.invalid/raw.png"]})}}
            raise AssertionError("Unexpected provider call")
        worker._request_json = MethodType(transport, worker)
        worker._download_file = MethodType(download, worker)
        attach(worker, session)

    first = WorkerThread(**request.worker_kwargs())
    configure(first, True)
    first.run()
    assert [item.status for item in session.items] == [RunItemStatus.SUCCEEDED, RunItemStatus.FAILED]
    assert first.kie_task_journal.pending()[0].request_id == "stub-2"
    retry = session.prepare_retry()
    assert [row["prompt"] for row in retry.generated_prompts] == ["object B"]
    second = WorkerThread(**retry.worker_kwargs())
    configure(second, False)
    second.run()
    assert creates == [("stub-1", "object A"), ("stub-2", "object B")]
    assert polls == ["stub-1", "stub-2"]
    assert not second.kie_task_journal.pending()
    assert all(item.status is RunItemStatus.SUCCEEDED for item in session.items)


def test_processing_failure_retains_generated_source_and_provenance_for_retry(tmp_path):
    request = request_for(tmp_path, ["flower"], remove_bg=True, remove_bg_provider="local_chroma_key", chroma_key_color="green")
    request.mode = "mode1_full"
    request.generated_prompts[0].update(result_kind="clipart", chroma_key_color="blue")
    session = RunQueueSession(request, ProjectMode.CLIPART)
    worker = WorkerThread(**request.worker_kwargs())
    worker._kie_generate_image = MethodType(lambda *_args: "https://fixture.invalid/raw.png", worker)
    def download_clipart(_worker, _url, path):
        image = Image.new("RGB", (64, 64), "blue")
        ImageDraw.Draw(image).rectangle((20, 20, 44, 44), fill="red")
        image.save(path)
    worker._download_file = MethodType(download_clipart, worker)

    def fail_processing(*_args, **_kwargs):
        raise RuntimeError("Local processing failure after paid pixels arrived")
    worker._run_processing_pipeline = fail_processing
    attach(worker, session)
    worker.run()
    item = session.items[0]
    assert item.status is RunItemStatus.FAILED
    source = Path(item.source_path)
    assert source.is_file()
    from chroma_generation_record import load_generation_color
    assert load_generation_color(source) == "blue"
    retry = session.prepare_retry()
    assert retry is not None and retry.mode == "mode2_process"
    assert retry.selected_files == [str(source.resolve())]
    assert not retry.generated_prompts
    assert retry.settings["remove_bg_provider"] == "local_chroma_key"
    # Recovery uses local pixels, never submits generation again.
    recovery = WorkerThread(**retry.worker_kwargs())
    recovery._kie_generate_image = lambda *_args: pytest.fail("Paid regeneration")
    recovery._run_local_rembg = lambda *_args: pytest.fail("Recovery switched the selected remover")
    attach(recovery, session)
    recovery.run()
    assert session.items[0].status is RunItemStatus.SUCCEEDED
    with Image.open(source) as before, Image.open(session.items[0].output_path) as after:
        assert before.getpixel((0, 0)) == (0, 0, 255)
        assert after.mode == "RGBA"
        assert after.getpixel((0, 0))[3] == 0
        assert after.getpixel((32, 32)) == (255, 0, 0, 255)
    from chroma_generation_record import load_generation_result_metadata
    assert load_generation_result_metadata(session.items[0].output_path) == {
        "result_kind": "clipart", "stage": "final"}


def test_repeated_fal_subset_retries_keep_each_accepted_task_and_cleanup_success(tmp_path, monkeypatch):
    import main
    # Identical prompt payloads still represent distinct original queue items.
    request = request_for(tmp_path, ["same", "same", "same"],
                          fal_api_key="fixture-only", fal_concurrency=1,
                          text_generation_model="fal-ai/flux/schnell")
    session = RunQueueSession(request, ProjectMode.CLIPART)
    creates, polls = [], []
    phase = 0

    class FakeClient:
        def __init__(self, _config):
            pass

        def submit_task(self, provider_request):
            task = f"fixture-{len(creates) + 1}"
            creates.append((task, provider_request.input_payload["prompt"]))
            return {"request_id": task}

        def wait_for_result(self, task, **_kwargs):
            polls.append((phase, task))
            if (phase == 0 and task != "fixture-1") or (phase == 1 and task == "fixture-3"):
                raise TimeoutError("Accepted task still pending")
            return {"request_id": task, "status": "completed", "result": {
                "images": [{"url": "https://fixture.invalid/raw.png"}]}}

    monkeypatch.setattr(main, "FalClient", FakeClient)

    def run(current_request):
        worker = WorkerThread(**current_request.worker_kwargs())
        worker._download_file = MethodType(download, worker)
        worker._request_json = lambda *_args, **_kwargs: pytest.fail("Unexpected external transport")
        attach(worker, session)
        worker.run()
        return worker

    run(request)
    phase = 1
    retry = session.prepare_retry()
    assert retry.settings["task_item_indices"] == [2, 3]
    run(retry)
    phase = 2
    retry = session.prepare_retry()
    assert retry.settings["task_item_indices"] == [3]
    final = run(retry)
    assert creates == [(f"fixture-{index}", "same") for index in (1, 2, 3)]
    assert polls == [(0, "fixture-1"), (0, "fixture-2"), (0, "fixture-3"),
                     (1, "fixture-2"), (1, "fixture-3"), (2, "fixture-3")]
    assert all(item.status is RunItemStatus.SUCCEEDED for item in session.items)
    assert not final.fal_task_journal.pending()
    assert not [e for e in Path(final._run_raw_dir).glob('*') if not e.name.startswith('gen_')]


@pytest.mark.parametrize("sidecar_failure", [False, True])
def test_generation_only_publication_failure_recovers_without_processing_or_paid_calls(tmp_path, monkeypatch, sidecar_failure):
    request = request_for(tmp_path, ["background"])
    session = RunQueueSession(request, ProjectMode.CLIPART)
    first = WorkerThread(**request.worker_kwargs())
    first._kie_generate_image = lambda *_args: "https://fixture.invalid/raw.png"
    first._download_file = MethodType(download, first)
    def fail_publication(*_args, **_kwargs):
        raise OSError("Publication failed after download")
    first._save_final_output = fail_publication
    attach(first, session)
    first.run()
    assert session.items[0].status is RunItemStatus.FAILED
    source = Path(session.items[0].source_path)
    assert source.is_file()
    retry = session.prepare_retry()
    assert retry and not retry.generated_prompts and not retry.settings["remove_bg"]
    second = WorkerThread(**retry.worker_kwargs())
    second._kie_generate_image = lambda *_args: pytest.fail("Paid regeneration")
    second._request_json = lambda *_args, **_kwargs: pytest.fail("External processing")
    second._run_local_rembg = lambda *_args: pytest.fail("Unrequested background removal")
    messages = []
    second.progress.connect(messages.append)
    if sidecar_failure:
        def fail_sidecar(*_args, **_kwargs):
            raise OSError("Local sidecar write failed")
        monkeypatch.setattr("chroma_generation_record.bind_generation_record", fail_sidecar)
    attach(second, session)
    second.run()
    assert session.items[0].status is RunItemStatus.SUCCEEDED
    with Image.open(source) as before, Image.open(session.items[0].output_path) as after:
        assert before.convert("RGBA").tobytes() == after.convert("RGBA").tobytes()
    if sidecar_failure:
        assert any("назначение результата" in message for message in messages)
    else:
        from chroma_generation_record import load_generation_result_metadata
        assert load_generation_result_metadata(session.items[0].output_path) == {
            "result_kind": "background", "stage": "final"}


@pytest.mark.parametrize("provider", ["kie", "fal"])
@pytest.mark.parametrize("failure_stage", ["upscale", "background_removal"])
@pytest.mark.parametrize("evict_completed", [False, True])
@pytest.mark.parametrize("download_failure", [False, True])
def test_accepted_paid_upscale_resumes_when_generated_url_becomes_local_input(tmp_path, monkeypatch, provider, failure_stage, evict_completed, download_failure):
    import main
    request = request_for(tmp_path, ["flower"], upscale=True, upscale_provider=provider,
                          kie_upscale_model="recraft/crisp-upscale",
                          fal_api_key="fixture-only", fal_upscale_model="fal-ai/aura-sr",
                          remove_bg=failure_stage == "background_removal",
                          remove_bg_provider=provider,
                          kie_remove_bg_model="recraft/remove-background",
                          fal_remove_bg_model="fal-ai/imageutils/rembg")
    request.mode = "mode1_full"
    request.generated_prompts[0]["result_kind"] = "clipart"
    session = RunQueueSession(request, ProjectMode.CLIPART)
    creates, polls = [], []
    initial = True

    class FakeFal:
        def __init__(self, _config):
            pass

        def upload_storage_file(self, _path):
            return "https://fixture.invalid/fal-storage-input.png"

        def run_image_operation(self, _operation, image_url, **kwargs):
            task = f"upscale-{len(creates)+1}"
            creates.append(image_url)
            kwargs["on_submitted_task"](task, {})
            return self.wait_for_result(task)

        def wait_for_result(self, task, **_kwargs):
            polls.append(task)
            if initial and (failure_stage == "upscale" or task == "upscale-2"):
                raise TimeoutError("Accepted upscale still pending")
            return {"request_id": task, "status": "completed", "result": {
                "images": [{"url": f"https://fixture.invalid/{task}.png"}]}}

    monkeypatch.setattr(main, "FalClient", FakeFal)

    def run(current_request):
        worker = WorkerThread(**current_request.worker_kwargs())
        def transport(current, url, method="GET", payload=None, **_kwargs):
            if method == "POST" and url.endswith("createTask"):
                creates.append(payload)
                if initial and (failure_stage == "upscale" or len(creates) == 2):
                    current.generation_wait_timeout = 0
                return {"code": 200, "data": {"taskId": f"upscale-{len(creates)}"}}
            if method == "GET" and "/recordInfo?" in url:
                polls.append(url.split("taskId=")[1])
                return {"code": 200, "data": {"state": "success", "resultJson":
                    json.dumps({"resultUrls": [f"https://fixture.invalid/{polls[-1]}.png"]})}}
            pytest.fail("Unexpected external transport")
        worker._request_json = MethodType(transport, worker)
        # Keep the real uploader and its byte-hash registration.
        worker._request_with_retries = lambda *_args, **_kwargs: json.dumps({
            "data": {"downloadUrl": "https://fixture.invalid/upload.png"}}).encode()
        worker._kie_generate_image = lambda *_args: "https://fixture.invalid/generated.png"
        def download_processing_result(_worker, url, path):
            if initial and download_failure and url.endswith("upscale-1.png"):
                raise OSError("Paid result ready but local download failed")
            if failure_stage == "background_removal" and url.endswith("upscale-2.png"):
                image = Image.new("RGBA", (32, 32))
                ImageDraw.Draw(image).rectangle((8, 8, 23, 23), fill="blue")
                image.save(path)
            else:
                download(_worker, url, path)
        worker._download_file = MethodType(download_processing_result, worker)
        attach(worker, session)
        worker.progress.connect(session.handle_progress, Qt.ConnectionType.DirectConnection)
        worker.run()
        return worker

    first = run(request)
    assert session.items[0].status is RunItemStatus.FAILED
    journal = first.kie_task_journal if provider == "kie" else first.fal_task_journal
    assert len(journal.pending()) == (0 if download_failure and failure_stage == "background_removal" else 1)
    missing_history = evict_completed and failure_stage == "background_removal"
    if missing_history:
        monkeypatch.setattr("fal_provider.MAX_TASK_JOURNAL_RECORDS", 1)
        journal.upsert("unrelated", "upscale_before:999", "fixture-other", "completed")
        assert all(record.request_id != "upscale-1" for record in journal.completed())
    initial = False
    retry = session.prepare_retry()
    assert retry and retry.mode == "mode2_process" and not retry.generated_prompts
    second = run(retry)
    if missing_history:
        assert session.items[0].status is RunItemStatus.FAILED
        accepted_count = 1 if download_failure else 2
        assert len(creates) == accepted_count, "Evicted paid history must not authorize another charge"
        assert len(journal.pending()) == (0 if download_failure else 1)
        retry_again = session.prepare_retry()
        assert "upscale_before" in retry_again.settings["recovery_completed_stages"]
        run(retry_again)
        assert len(creates) == accepted_count
        assert session.items[0].status is RunItemStatus.FAILED
        return
    assert session.items[0].status is RunItemStatus.SUCCEEDED
    expected = 1 if failure_stage == "upscale" else 2
    assert len(creates) == expected
    assert polls[-1] == f"upscale-{expected}"
    journal = second.kie_task_journal if provider == "kie" else second.fal_task_journal
    assert not journal.pending()


def test_paid_content_aliases_still_reject_changed_pixels_model_parameters_and_origin(tmp_path):
    request = request_for(tmp_path, ["flower"])
    worker = WorkerThread(**request.worker_kwargs())
    source = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "blue").save(source)
    worker._set_diagnostic_context(2, 2, "upscale_before")
    worker._remember_paid_image_input("https://fixture.invalid/generated.png", source)
    original = worker._paid_task_fingerprint({"image": "https://fixture.invalid/generated.png", "scale": 2})
    worker.kie_task_journal.upsert("accepted", "upscale_before:2", "fixture-model", "queued", input_fingerprint=original)
    uri = worker._fal_source_url(str(source), None)
    assert uri not in worker._kie_uploaded_content_ids
    assert all(len(key) < 128 for key in worker._kie_uploaded_content_ids)
    same = worker._paid_task_fingerprint({"image": uri, "scale": 2})
    assert same == original

    def claim(model, fingerprint):
        return worker._claim_pending_task(worker.kie_task_journal, "upscale_before", model,
                                          set(), input_fingerprint=fingerprint)
    assert claim("fixture-model", same).request_id == "accepted"
    assert claim("different-model", same) is None
    changed_scale = worker._paid_task_fingerprint({"image": uri, "scale": 4})
    assert claim("fixture-model", changed_scale) is None
    worker._set_diagnostic_context(1, 2, "upscale_before")
    assert claim("fixture-model", same) is None
    worker._set_diagnostic_context(2, 2, "upscale_before")
    Image.new("RGB", (32, 32), "red").save(source)
    changed_uri = worker._fal_source_url(str(source), None)
    changed_pixels = worker._paid_task_fingerprint({"image": changed_uri, "scale": 2})
    assert changed_pixels != original
    assert claim("fixture-model", changed_pixels) is None


def test_fal_batch_aliases_retain_only_compact_identifiers(tmp_path):
    import random
    worker = WorkerThread(**request_for(tmp_path, ["flower"]).worker_kwargs())
    source = tmp_path / "source.png"
    rng = random.Random(42)
    for _ in range(10):
        Image.frombytes("RGB", (256, 256), rng.randbytes(256 * 256 * 3)).save(source)
        uri = worker._fal_source_url(str(source), None)
        assert len(uri) > 200000
        assert uri not in worker._kie_uploaded_content_ids
    assert len(worker._kie_uploaded_content_ids) == 10
    assert sum(len(key) for key in worker._kie_uploaded_content_ids) < 1000


def test_provider_success_checkpoints_paid_history_before_local_stage_finishes(tmp_path):
    session = RunQueueSession(request_for(tmp_path, ["first", "second"]), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[1].status = RunItemStatus.FAILED
    session.handle_finished()
    session.prepare_retry()
    checkpoints = []
    session.changed.connect(lambda: checkpoints.append(session.items[1].paid_completed_stages))
    session.handle_diagnostic({"event": "provider_task_succeeded", "item_index": 1,
        "item_total": 1, "stage": "upscale_before", "provider": "kie",
        "model": "fixture-model", "task": "accepted-2", "outcome": "succeeded"})
    assert checkpoints == [("upscale_before",)]
    assert session.items[0].paid_completed_stages == ()
    assert session.items[1].stage_statuses.get("upscale_before") != "complete"
    session.handle_diagnostic({"event": "stage_finished", "item_index": 1,
        "item_total": 1, "stage": "upscale_before", "provider": "kie", "outcome": "failed"})
    assert session.items[1].stage_statuses["upscale_before"] == "failed"
    assert session.items[1].paid_history_stages() == ("upscale_before",)
