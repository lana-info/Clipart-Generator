import errno
import os
import tempfile
import threading
import time
import types
import unittest
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main
from tests.test_photoroom_provider import create_photoroom_response_bytes


class ProviderActivity:
    def __init__(self):
        self.lock = threading.Lock()
        self.active = {"kie": 0, "photoroom": 0}
        self.maximum = {"kie": 0, "photoroom": 0}
        self.max_remote = 0
        self.overlapped = False
        self.remote_six = threading.Event()
        self.order = defaultdict(list)
        self.kie_models = defaultdict(list)

    def start(self, provider, item_index, model=""):
        with self.lock:
            self.active[provider] += 1
            self.maximum[provider] = max(
                self.maximum[provider], self.active[provider]
            )
            self.max_remote = max(self.max_remote, sum(self.active.values()))
            if sum(self.active.values()) == main.MAX_REMOTE_CONCURRENCY:
                self.remote_six.set()
            self.overlapped = self.overlapped or all(self.active.values())
            self.order[item_index].append(provider)
            if provider == "kie":
                self.kie_models[item_index].append(model)

    def finish(self, provider):
        with self.lock:
            self.active[provider] -= 1


def install_fake_kie_network(
    worker,
    activity,
    *,
    delay=0.04,
    release=None,
    started=None,
    started_target=0,
    release_by_item=None,
    release_waves=None,
):
    tasks = {}
    tasks_lock = threading.Lock()

    def fake_request(worker_self, req, timeout=None):
        item_index = worker_self._diagnostic_context.item_index
        if "file-stream-upload" in req.full_url:
            return b'{"success":true,"data":{"downloadUrl":"https://example.invalid/input.png"}}'
        if "createTask" in req.full_url:
            payload = main.json.loads(req.data.decode("utf-8"))
            with tasks_lock:
                task_count = len(tasks) + 1
                task_id = f"task-{item_index}-{task_count}"
                wave_release = None
                if release_waves is not None:
                    wave_release = release_waves[0 if task_count <= 3 else 1]
                tasks[task_id] = (item_index, wave_release)
            activity.start("kie", item_index, payload["model"])
            if started is not None and task_count >= started_target:
                started.set()
            return main.json.dumps(
                {"code": 200, "data": {"taskId": task_id}}
            ).encode("utf-8")
        if "recordInfo" in req.full_url:
            task_id = main.parse.parse_qs(main.urlparse(req.full_url).query)["taskId"][0]
            try:
                item_release = (
                    tasks[task_id][1]
                    or (
                        release_by_item.get(item_index)
                        if release_by_item is not None
                        else release
                    )
                )
                if item_release is None:
                    threading.Event().wait(delay)
                else:
                    item_release.wait(timeout=2)
                return main.json.dumps(
                    {
                        "code": 200,
                        "data": {
                            "state": "success",
                            "resultJson": main.json.dumps(
                                {"resultUrls": [f"https://example.invalid/{task_id}.png"]}
                            ),
                        },
                    }
                ).encode("utf-8")
            finally:
                activity.finish("kie")
        raise AssertionError(f"Unexpected KIE request: {req.full_url}")

    worker._request_with_retries = types.MethodType(fake_request, worker)


def install_fake_photoroom_network(
    worker,
    activity,
    *,
    delay=0.04,
    release=None,
    started=None,
    started_target=0,
    fail_items=(),
):
    response_bytes = create_photoroom_response_bytes(size=(8, 8))
    start_count = 0
    count_lock = threading.Lock()
    previous_request = worker._request_with_retries

    def fake_request(worker_self, req, timeout=None):
        nonlocal start_count
        if req.full_url != main.PHOTOROOM_SEGMENT_URL:
            return previous_request(req, timeout=timeout)
        item_index = worker_self._diagnostic_context.item_index
        activity.start("photoroom", item_index)
        with count_lock:
            start_count += 1
            if started is not None and start_count >= started_target:
                started.set()
        try:
            if release is None:
                time.sleep(delay)
            else:
                release.wait(timeout=2)
            if item_index in fail_items:
                raise RuntimeError("controlled PhotoRoom failure")
            return response_bytes
        finally:
            activity.finish("photoroom")

    worker._request_with_retries = types.MethodType(fake_request, worker)
    return lambda: start_count


def create_inputs(temp_dir, count):
    inputs = []
    for index in range(1, count + 1):
        path = Path(temp_dir) / f"input-{index}.png"
        main.Image.new("RGBA", (8, 8), "white").save(path)
        inputs.append(str(path))
    return inputs


def install_fake_file_io(worker, saved=None):
    def fake_download(worker_self, _url, output_path):
        main.Image.new("RGBA", (8, 8), "white").save(output_path)

    def fake_save(worker_self, _url, _source, output_path, *_args):
        main.Image.new("RGBA", (8, 8), "white").save(output_path)
        if saved is not None:
            saved.append(Path(output_path).name)

    worker._download_file = types.MethodType(fake_download, worker)
    worker._save_final_output = types.MethodType(fake_save, worker)


class ParallelGenerationTests(unittest.TestCase):
    def _failed_reference_read_message(self, temp_dir, reference_path, private_path):
        private_prompt = "private path prompt"
        api_key = "private-path-api-key"
        worker = main.WorkerThread(
            "mode1_generate_only",
            temp_dir,
            {
                "kie_api_key": api_key,
                "kie_concurrency": 1,
                "generation_launch_interval": 0,
            },
            generated_prompts=[
                {"prompt": private_prompt, "references": [reference_path]}
            ],
        )
        item_events = []
        worker.item_progress.connect(item_events.append)

        def fail_read(worker_self, file_path):
            raise OSError(
                errno.EACCES,
                (
                    f"Permission denied while reading {private_path}; "
                    "provider says retry with PNG; "
                    f"api_key={api_key}; prompt={private_prompt}"
                ),
                private_path,
            )

        worker._read_upload_file = types.MethodType(fail_read, worker)
        worker._mode1_generate(process_generated=False, emit_final=False)

        failed = next(
            event for event in item_events if event.get("status") == "failed"
        )
        message = failed["message"]
        self.assertEqual(failed["stage"], "generation")
        self.assertEqual(failed.get("provider"), "kie")
        self.assertEqual(failed.get("model"), worker.reference_generation_model)
        self.assertIn("Permission denied", message)
        self.assertIn("provider says retry with PNG", message)
        self.assertIn("input.png", message)
        self.assertLessEqual(len(message), 500)
        self.assertNotIn(private_path, message)
        self.assertNotIn(private_prompt, message)
        self.assertNotIn(api_key, message)
        return message

    def test_item_error_sanitizes_posix_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="kie-private-path-failure-") as temp_dir:
            reference_path = (
                Path(temp_dir) / "Private Folder" / "Customer A" / "input.png"
            )
            reference_path.parent.mkdir(parents=True)
            main.Image.new("RGBA", (8, 8), "white").save(reference_path)

            message = self._failed_reference_read_message(
                temp_dir,
                str(reference_path),
                str(reference_path),
            )

            self.assertNotIn(temp_dir, message)
            self.assertNotIn("Private Folder", message)
            self.assertNotIn("Customer A", message)

    def test_item_error_sanitizes_windows_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="kie-private-path-failure-") as temp_dir:
            reference_path = create_inputs(temp_dir, 1)[0]
            windows_path = r"C:\Users\Jane Doe\Customer A\input.png"

            message = self._failed_reference_read_message(
                temp_dir,
                reference_path,
                windows_path,
            )

            self.assertNotIn(r"C:\Users", message)
            self.assertNotIn("Jane Doe", message)
            self.assertNotIn("Customer A", message)

    def test_item_error_sanitizes_unc_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="kie-private-path-failure-") as temp_dir:
            reference_path = create_inputs(temp_dir, 1)[0]
            unc_path = r"\\server\private-share\Customer A\input.png"

            message = self._failed_reference_read_message(
                temp_dir,
                reference_path,
                unc_path,
            )

            self.assertNotIn("server", message)
            self.assertNotIn("private-share", message)
            self.assertNotIn("Customer A", message)

    def test_generation_reference_upload_failure_keeps_exact_kie_context(self):
        with tempfile.TemporaryDirectory(prefix="kie-generation-reference-failure-") as temp_dir:
            reference_path = create_inputs(temp_dir, 1)[0]
            private_prompt = "private generation prompt"
            api_key = "private-kie-key"
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                {
                    "kie_api_key": api_key,
                    "kie_concurrency": 1,
                    "generation_launch_interval": 0,
                },
                generated_prompts=[
                    {"prompt": private_prompt, "references": [reference_path]}
                ],
            )
            item_events = []
            worker.item_progress.connect(item_events.append)

            def fail_upload(worker_self, req, timeout=None):
                raise RuntimeError(
                    f"controlled upload failure {private_prompt} {api_key}"
                )

            worker._request_with_retries = types.MethodType(fail_upload, worker)
            worker._mode1_generate(process_generated=False, emit_final=False)

            failed = next(
                event for event in item_events if event.get("status") == "failed"
            )
            self.assertEqual(failed["stage"], "generation")
            self.assertEqual(failed.get("provider"), "kie")
            self.assertEqual(failed.get("model"), worker.reference_generation_model)
            self.assertNotIn(private_prompt, str(failed))
            self.assertNotIn(api_key, str(failed))
            self.assertNotIn(reference_path, str(failed))

    def test_generation_create_failure_keeps_exact_kie_context(self):
        with tempfile.TemporaryDirectory(prefix="kie-generation-create-failure-") as temp_dir:
            private_prompt = "private create prompt"
            api_key = "private-create-key"
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                {
                    "kie_api_key": api_key,
                    "kie_concurrency": 1,
                    "generation_launch_interval": 0,
                },
                generated_prompts=[
                    {"prompt": private_prompt, "references": []}
                ],
            )
            item_events = []
            worker.item_progress.connect(item_events.append)

            def fail_create(worker_self, req, timeout=None):
                self.assertIn("createTask", req.full_url)
                raise RuntimeError(
                    f"controlled create failure {private_prompt} {api_key}"
                )

            worker._request_with_retries = types.MethodType(fail_create, worker)
            worker._mode1_generate(process_generated=False, emit_final=False)

            failed = next(
                event for event in item_events if event.get("status") == "failed"
            )
            self.assertEqual(failed["stage"], "generation")
            self.assertEqual(failed.get("provider"), "kie")
            self.assertEqual(failed.get("model"), worker.text_generation_model)
            self.assertNotIn(private_prompt, str(failed))
            self.assertNotIn(api_key, str(failed))

    def test_normal_kie_upscale_upload_failure_keeps_exact_context(self):
        with tempfile.TemporaryDirectory(prefix="kie-normal-upscale-failure-") as temp_dir:
            source_path = create_inputs(temp_dir, 1)[0]
            api_key = "private-upscale-key"
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "kie_api_key": api_key,
                    "photoroom_api_key": "test-photoroom-key",
                    "kie_concurrency": 1,
                    "photoroom_concurrency": 1,
                    "upscale": True,
                    "upscale_provider": "kie",
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=[source_path],
            )
            item_events = []
            worker.item_progress.connect(item_events.append)

            def fail_upload(worker_self, req, timeout=None):
                self.assertIn("file-stream-upload", req.full_url)
                raise RuntimeError(f"controlled upload failure {api_key}")

            worker._request_with_retries = types.MethodType(fail_upload, worker)
            worker._mode2_process_files(emit_final=False)

            failed = next(
                event for event in item_events if event.get("status") == "failed"
            )
            self.assertEqual(failed["stage"], "upscale_before")
            self.assertEqual(failed.get("provider"), "kie")
            self.assertEqual(failed.get("model"), worker.kie_upscale_model)
            self.assertNotIn(api_key, str(failed))
            self.assertNotIn(source_path, str(failed))

    def test_legacy_kie_upscale_upload_failure_keeps_exact_context(self):
        with tempfile.TemporaryDirectory(prefix="kie-legacy-upscale-failure-") as temp_dir:
            source_path = create_inputs(temp_dir, 1)[0]
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "kie_concurrency": 1,
                    "upscale": True,
                    "upscale_provider": "kie",
                    "remove_bg": False,
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=[source_path],
            )
            item_events = []
            worker.item_progress.connect(item_events.append)

            def fail_upload(worker_self, req, timeout=None):
                raise RuntimeError("controlled legacy upload failure")

            worker._request_with_retries = types.MethodType(fail_upload, worker)

            worker._mode2_process_files(emit_final=False)

            failed = next(
                event for event in item_events if event.get("status") == "failed"
            )
            self.assertEqual(failed["stage"], "upscale_before")
            self.assertEqual(failed.get("provider"), "kie")
            self.assertEqual(failed.get("model"), worker.kie_upscale_model)
            self.assertNotIn(source_path, str(failed))

    def test_legacy_kie_background_create_failure_keeps_exact_context(self):
        with tempfile.TemporaryDirectory(prefix="kie-legacy-background-failure-") as temp_dir:
            source_path = create_inputs(temp_dir, 1)[0]
            api_key = "private-background-key"
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "kie_api_key": api_key,
                    "kie_concurrency": 1,
                    "generation_launch_interval": 0,
                    "upscale": True,
                    "upscale_provider": "kie",
                    "remove_bg": True,
                    "remove_bg_provider": "kie",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=[source_path],
            )
            item_events = []
            worker.item_progress.connect(item_events.append)
            create_count = 0

            def fake_request(worker_self, req, timeout=None):
                nonlocal create_count
                if "file-stream-upload" in req.full_url:
                    return b'{"success":true,"data":{"downloadUrl":"https://example.invalid/input.png"}}'
                if "createTask" in req.full_url:
                    create_count += 1
                    if create_count == 2:
                        raise RuntimeError(
                            f"controlled background failure {api_key}"
                        )
                    return b'{"code":200,"data":{"taskId":"upscale-task"}}'
                if "recordInfo" in req.full_url:
                    return b'{"code":200,"data":{"state":"success","resultJson":"{\\"resultUrls\\":[\\"https://example.invalid/upscaled.png\\"]}"}}'
                raise AssertionError(f"Unexpected request: {req.full_url}")

            worker._request_with_retries = types.MethodType(fake_request, worker)
            install_fake_file_io(worker)
            worker._mode2_process_files(emit_final=False)

            failed = next(
                event for event in item_events if event.get("status") == "failed"
            )
            self.assertEqual(failed["stage"], "background_removal")
            self.assertEqual(failed.get("provider"), "kie")
            self.assertEqual(failed.get("model"), worker.kie_remove_bg_model)
            self.assertNotIn(api_key, str(failed))
            self.assertNotIn(source_path, str(failed))

    def test_kie_uploads_share_the_provider_limit_with_other_kie_network_work(self):
        with tempfile.TemporaryDirectory(prefix="parallel-kie-upload-") as temp_dir:
            inputs = create_inputs(temp_dir, 6)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "kie_concurrency": 3,
                    "generation_launch_interval": 0,
                },
            )
            release = threading.Event()
            three_started = threading.Event()
            lock = threading.Lock()
            active = 0
            maximum = 0
            started = 0

            def fake_request(worker_self, req, timeout=None):
                nonlocal active, maximum, started
                with lock:
                    active += 1
                    started += 1
                    maximum = max(maximum, active)
                    if started >= 3:
                        three_started.set()
                try:
                    self.assertTrue(release.wait(timeout=2), "upload release deadlock")
                    return b'{"success":true,"data":{"downloadUrl":"https://example.invalid/input.png"}}'
                finally:
                    with lock:
                        active -= 1

            worker._request_with_retries = types.MethodType(fake_request, worker)
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = [executor.submit(worker._kie_upload_file, path) for path in inputs]
                self.assertTrue(three_started.wait(timeout=1), "three uploads did not start")
                self.assertFalse(
                    threading.Event().wait(0.05) or maximum > 3,
                    "a fourth KIE network operation started while three leases were held",
                )
                release.set()
                for future in futures:
                    self.assertEqual(
                        future.result(timeout=2),
                        "https://example.invalid/input.png",
                    )

            self.assertEqual(maximum, 3)

    def test_stop_after_current_cancels_a_kie_upload_waiting_for_a_provider_slot(self):
        with tempfile.TemporaryDirectory(prefix="parallel-kie-stop-") as temp_dir:
            first_path, second_path = create_inputs(temp_dir, 2)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {"kie_api_key": "test-key", "kie_concurrency": 1},
            )
            first_started = threading.Event()
            release_first = threading.Event()
            lock = threading.Lock()
            network_calls = 0

            def fake_request(worker_self, req, timeout=None):
                nonlocal network_calls
                with lock:
                    network_calls += 1
                    call_number = network_calls
                if call_number == 1:
                    first_started.set()
                    self.assertTrue(release_first.wait(timeout=2), "first upload release deadlock")
                return b'{"success":true,"data":{"downloadUrl":"https://example.invalid/input.png"}}'

            worker._request_with_retries = types.MethodType(fake_request, worker)
            with ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(worker._kie_upload_file, first_path)
                self.assertTrue(first_started.wait(timeout=1), "first upload did not start")
                second = executor.submit(worker._kie_upload_file, second_path)
                self.assertFalse(second.done(), "second upload did not wait for the KIE slot")
                worker.request_stop_after_current()
                release_first.set()
                self.assertEqual(
                    first.result(timeout=2),
                    "https://example.invalid/input.png",
                )
                with self.assertRaises(main.ProcessingCancelled):
                    second.result(timeout=2)

            self.assertEqual(network_calls, 1)

    def test_stop_closes_paid_kie_submission_even_inside_a_nested_provider_lease(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            {"kie_api_key": "test-key", "generation_launch_interval": 0},
        )
        worker._provider_lease_context.depths = {"kie": 1}
        worker.request_stop_after_current()
        req = main.request.Request(
            "https://api.kie.ai/api/v1/jobs/createTask",
            data=b"{}",
            method="POST",
        )

        with patch.object(main, "open_url_secure") as opener:
            with self.assertRaises(main.ProcessingCancelled):
                worker._request_with_retries(req)

        opener.assert_not_called()

    def test_stop_prevents_photoroom_429_retry_inside_nested_provider_lease(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            {"photoroom_api_key": "photo-key", "retries": 2},
        )
        worker._provider_lease_context.depths = {"photoroom": 1}
        worker._photoroom_launch_interval = 0.0
        req = main.request.Request(
            main.PHOTOROOM_SEGMENT_URL,
            data=b"image",
            method="POST",
        )

        def reject_once(*args, **kwargs):
            worker.request_stop_after_current()
            raise main.urlerror.HTTPError(
                req.full_url,
                429,
                "rate limited",
                {},
                None,
            )

        with patch.object(main, "open_url_secure", side_effect=reject_once) as opener:
            with self.assertRaises(main.ProcessingCancelled):
                worker._request_with_retries(req)

        self.assertEqual(opener.call_count, 1)

    def test_kie_provider_slot_is_reused_after_upload_failure(self):
        with tempfile.TemporaryDirectory(prefix="parallel-kie-reuse-") as temp_dir:
            first_path, second_path = create_inputs(temp_dir, 2)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {"kie_api_key": "test-key", "kie_concurrency": 1},
            )
            call_count = 0

            def fake_request(worker_self, req, timeout=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("controlled upload failure")
                return b'{"success":true,"data":{"downloadUrl":"https://example.invalid/recovered.png"}}'

            worker._request_with_retries = types.MethodType(fake_request, worker)
            with self.assertRaisesRegex(RuntimeError, "controlled upload failure"):
                worker._kie_upload_file(first_path)
            self.assertEqual(
                worker._kie_upload_file(second_path),
                "https://example.invalid/recovered.png",
            )

    def test_nested_reference_upload_reuses_the_current_kie_lease(self):
        with tempfile.TemporaryDirectory(prefix="parallel-kie-reference-") as temp_dir:
            reference_path = create_inputs(temp_dir, 1)[0]
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "kie_concurrency": 1,
                    "generation_launch_interval": 0,
                },
            )
            worker._set_diagnostic_context(1, 1, "generation")
            activity = ProviderActivity()
            install_fake_kie_network(worker, activity)

            result = worker._kie_generate_image("reference prompt", [reference_path])

            self.assertTrue(result.endswith(".png"))
            self.assertEqual(activity.maximum["kie"], 1)

    def test_generation_runs_independent_items_concurrently_and_preserves_indexes(self):
        with tempfile.TemporaryDirectory(prefix="parallel-generation-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "kie_concurrency": 3,
                    "generation_launch_interval": 0,
                },
                generated_prompts=[
                    {"prompt": f"prompt-{index}", "references": []}
                    for index in range(1, 5)
                ],
            )
            activity = ProviderActivity()
            saved = []
            install_fake_kie_network(worker, activity)
            install_fake_file_io(worker, saved)

            worker._mode1_generate(process_generated=False, emit_final=False)

            self.assertEqual(activity.maximum["kie"], 3)
            self.assertEqual(
                [name.split("_")[-2] for name in sorted(saved)],
                ["01", "02", "03", "04"],
            )

    def test_kie_provider_limit_three_and_one_are_enforced_by_real_adapters(self):
        for limit in (1, 3):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory(
                prefix=f"parallel-generation-{limit}-"
            ) as temp_dir:
                worker = main.WorkerThread(
                    "mode1_generate_only",
                    temp_dir,
                    {
                        "kie_api_key": "test-key",
                        "kie_concurrency": limit,
                        "generation_launch_interval": 0,
                    },
                    generated_prompts=[
                        {"prompt": f"prompt-{index}", "references": []}
                        for index in range(1, 7)
                    ],
                )
                activity = ProviderActivity()
                install_fake_kie_network(worker, activity)
                install_fake_file_io(worker)

                worker._mode1_generate(process_generated=False, emit_final=False)

                self.assertEqual(activity.maximum["kie"], limit)

    def test_processing_only_overlaps_kie_stages_and_preserves_each_item_order(self):
        with tempfile.TemporaryDirectory(prefix="parallel-processing-") as temp_dir:
            inputs = create_inputs(temp_dir, 4)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "kie_concurrency": 3,
                    "generation_launch_interval": 0,
                    "upscale": True,
                    "remove_bg": True,
                    "upscale_provider": "kie",
                    "remove_bg_provider": "kie",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=inputs,
            )
            activity = ProviderActivity()
            install_fake_kie_network(worker, activity)
            install_fake_file_io(worker)

            worker._mode2_process_files(emit_final=False)

            self.assertEqual(activity.maximum["kie"], 3)
            for item_index in range(1, 5):
                self.assertEqual(
                    activity.kie_models[item_index],
                    [worker.kie_upscale_model, worker.kie_remove_bg_model],
                )

    def test_generate_then_process_uses_the_same_kie_provider_limit(self):
        with tempfile.TemporaryDirectory(prefix="parallel-full-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_full",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "kie_concurrency": 3,
                    "generation_launch_interval": 0,
                    "upscale": True,
                    "remove_bg": False,
                    "upscale_provider": "kie",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                generated_prompts=[
                    {"prompt": f"prompt-{index}", "references": []}
                    for index in range(1, 5)
                ],
            )
            activity = ProviderActivity()
            install_fake_kie_network(worker, activity)
            install_fake_file_io(worker)

            worker._mode1_generate(process_generated=True, emit_final=False)

            self.assertEqual(activity.maximum["kie"], 3)
            self.assertLessEqual(activity.max_remote, 3)

    def test_photoroom_provider_limit_three_and_one_are_enforced_by_real_adapter(self):
        for limit in (1, 3):
            with self.subTest(limit=limit), tempfile.TemporaryDirectory(
                prefix=f"parallel-photoroom-{limit}-"
            ) as temp_dir:
                worker = main.WorkerThread(
                    "mode2_process",
                    temp_dir,
                    {
                        "photoroom_api_key": "photo-key",
                        "photoroom_concurrency": limit,
                        "upscale": False,
                        "remove_bg": True,
                        "remove_bg_provider": "photoroom",
                        "output_dir": str(Path(temp_dir) / "output"),
                    },
                    selected_files=create_inputs(temp_dir, 6),
                )
                worker._photoroom_launch_interval = 0.0
                activity = ProviderActivity()
                install_fake_photoroom_network(worker, activity)
                install_fake_file_io(worker)

                worker._mode2_process_files(emit_final=False)

                self.assertEqual(activity.maximum["photoroom"], limit)

    def test_mixed_providers_overlap_with_independent_limits_and_six_task_cap(self):
        with tempfile.TemporaryDirectory(prefix="parallel-mixed-") as temp_dir:
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "photoroom_api_key": "photo-key",
                    "kie_concurrency": 3,
                    "photoroom_concurrency": 3,
                    "generation_launch_interval": 0,
                    "upscale": True,
                    "upscale_provider": "kie",
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=create_inputs(temp_dir, 6),
            )
            worker._photoroom_launch_interval = 0.0
            activity = ProviderActivity()
            first_kie_wave = threading.Event()
            second_kie_wave = threading.Event()
            first_three_kie_started = threading.Event()
            photoroom_release = threading.Event()
            three_photoroom_started = threading.Event()
            install_fake_kie_network(
                worker,
                activity,
                release_waves=(first_kie_wave, second_kie_wave),
                started=first_three_kie_started,
                started_target=3,
            )
            install_fake_photoroom_network(
                worker,
                activity,
                release=photoroom_release,
                started=three_photoroom_started,
                started_target=3,
            )
            install_fake_file_io(worker)
            runner = threading.Thread(
                target=worker._mode2_process_files,
                kwargs={"emit_final": False},
            )
            runner.start()
            try:
                self.assertTrue(
                    first_three_kie_started.wait(timeout=1),
                    "first KIE wave did not start",
                )
                first_kie_wave.set()
                self.assertTrue(
                    three_photoroom_started.wait(timeout=1),
                    "PhotoRoom wave did not start",
                )
                self.assertTrue(
                    activity.remote_six.wait(timeout=1),
                    "three KIE and three PhotoRoom operations did not overlap",
                )
            finally:
                second_kie_wave.set()
                photoroom_release.set()
                runner.join(timeout=3)

            self.assertFalse(runner.is_alive())
            self.assertTrue(activity.overlapped)
            self.assertEqual(activity.maximum["kie"], 3)
            self.assertEqual(activity.maximum["photoroom"], 3)
            self.assertEqual(activity.max_remote, main.MAX_REMOTE_CONCURRENCY)
            self.assertLessEqual(activity.max_remote, 6)
            for item_index in range(1, 7):
                self.assertEqual(
                    activity.order[item_index], ["kie", "photoroom"]
                )

    def test_local_upscale_stays_sequential_during_remote_photoroom_run(self):
        with tempfile.TemporaryDirectory(prefix="parallel-local-lock-") as temp_dir:
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "photoroom_api_key": "photo-key",
                    "photoroom_concurrency": 3,
                    "upscale": True,
                    "upscale_provider": "local_realesrgan",
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=create_inputs(temp_dir, 5),
            )
            worker._photoroom_launch_interval = 0.0
            activity = ProviderActivity()
            install_fake_photoroom_network(worker, activity)
            install_fake_file_io(worker)
            local_lock = threading.Lock()
            local_active = 0
            max_local_active = 0

            def fake_local(worker_self, input_path, output_path, *args, **kwargs):
                nonlocal local_active, max_local_active
                with local_lock:
                    local_active += 1
                    max_local_active = max(max_local_active, local_active)
                time.sleep(0.02)
                main.Image.new("RGBA", (8, 8), "white").save(output_path)
                with local_lock:
                    local_active -= 1
                return output_path

            worker._run_local_realesrgan = types.MethodType(fake_local, worker)

            worker._mode2_process_files(emit_final=False)

            self.assertEqual(max_local_active, 1)
            self.assertLessEqual(activity.maximum["photoroom"], 3)

    def test_stop_after_current_prevents_pending_photoroom_items_from_starting(self):
        with tempfile.TemporaryDirectory(prefix="parallel-stop-") as temp_dir:
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "photoroom_api_key": "photo-key",
                    "photoroom_concurrency": 3,
                    "upscale": False,
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=create_inputs(temp_dir, 8),
            )
            worker._photoroom_launch_interval = 0.0
            activity = ProviderActivity()
            release = threading.Event()
            three_started = threading.Event()
            start_count = install_fake_photoroom_network(
                worker,
                activity,
                release=release,
                started=three_started,
                started_target=3,
            )
            install_fake_file_io(worker)
            runner = threading.Thread(
                target=worker._mode2_process_files,
                kwargs={"emit_final": False},
            )
            runner.start()
            reached_limit = three_started.wait(timeout=0.6)

            worker.request_stop_after_current()
            release.set()
            runner.join(timeout=3)

            self.assertTrue(reached_limit)
            self.assertFalse(runner.is_alive())
            self.assertEqual(start_count(), 3)

    def test_photoroom_launch_guard_allows_initial_burst_then_one_start_per_second(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            {
                "photoroom_concurrency": 3,
            },
        )
        now = [0.0]
        starts = []

        def fake_monotonic():
            return now[0]

        def fake_sleep(delay):
            now[0] += delay

        with (
            patch.object(main.time, "monotonic", side_effect=fake_monotonic),
            patch.object(main.time, "sleep", side_effect=fake_sleep),
        ):
            for _ in range(5):
                worker._wait_for_photoroom_launch_slot()
                starts.append(now[0])
                worker._photoroom_slots.release()

        self.assertEqual(starts[:3], [0.0, 0.0, 0.0])
        self.assertAlmostEqual(starts[3], 1.0, places=6)
        self.assertAlmostEqual(starts[4], 2.0, places=6)

    def test_photoroom_first_post_burst_start_is_one_second_after_delayed_final_burst(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            {"photoroom_concurrency": 3},
        )
        now = [0.0]
        starts = []

        def fake_monotonic():
            return now[0]

        def fake_sleep(delay):
            now[0] += delay

        with (
            patch.object(main.time, "monotonic", side_effect=fake_monotonic),
            patch.object(main.time, "sleep", side_effect=fake_sleep),
        ):
            for launch_time in (0.0, 0.25, 0.5):
                now[0] = launch_time
                worker._wait_for_photoroom_launch_slot()
                starts.append(now[0])
                worker._photoroom_slots.release()
            worker._wait_for_photoroom_launch_slot()
            starts.append(now[0])
            worker._photoroom_slots.release()

        self.assertEqual(starts[:3], [0.0, 0.25, 0.5])
        self.assertAlmostEqual(starts[3], 1.5, places=6)

    def test_photoroom_production_pacing_cannot_be_disabled_by_settings(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            {
                "photoroom_concurrency": 3,
                "_photoroom_launch_interval": 0,
            },
        )

        self.assertEqual(worker._photoroom_launch_interval, 1.0)

    def test_each_concurrent_photoroom_429_retry_gets_a_separately_paced_launch(self):
        with tempfile.TemporaryDirectory(prefix="parallel-photoroom-retry-") as temp_dir:
            first_path, second_path = create_inputs(temp_dir, 2)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "photoroom_api_key": "photo-key",
                    "photoroom_concurrency": 2,
                    "retries": 1,
                },
            )
            response_bytes = create_photoroom_response_bytes(size=(8, 8))
            clock = [0.0]
            clock_lock = threading.Lock()
            attempts_by_thread = defaultdict(int)
            launch_times = []
            initial_attempts = threading.Barrier(2)

            def fake_monotonic():
                with clock_lock:
                    return clock[0]

            def fake_sleep(delay):
                if delay >= 1.0:
                    return
                with clock_lock:
                    clock[0] += delay

            def fake_open(req, timeout=None, context=None):
                thread_id = threading.get_ident()
                attempts_by_thread[thread_id] += 1
                with clock_lock:
                    launch_times.append(clock[0])
                if attempts_by_thread[thread_id] == 1:
                    initial_attempts.wait(timeout=1)
                    raise main.urlerror.HTTPError(
                        req.full_url,
                        429,
                        "Too Many Requests",
                        {},
                        BytesIO(b"rate limited"),
                    )
                response = BytesIO(response_bytes)
                response.status = 200
                response.headers = {}
                return response

            outputs = [str(Path(temp_dir) / f"output-{index}.png") for index in (1, 2)]
            with (
                patch.object(main.time, "monotonic", side_effect=fake_monotonic),
                patch.object(main.time, "sleep", side_effect=fake_sleep),
                patch.object(main, "open_url_secure", side_effect=fake_open),
                ThreadPoolExecutor(max_workers=2) as executor,
            ):
                futures = [
                    executor.submit(worker._run_photoroom_remove_bg, source, output)
                    for source, output in zip((first_path, second_path), outputs)
                ]
                for future in futures:
                    future.result(timeout=2)

            self.assertEqual(len(launch_times), 4)
            ordered = sorted(launch_times)
            self.assertEqual(ordered[:2], [0.0, 0.0])
            self.assertGreaterEqual(ordered[2], 1.0)
            self.assertGreaterEqual(ordered[3] - ordered[2], 1.0)

    def test_photoroom_launch_guard_does_not_reserve_start_while_provider_is_full(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            {
                "photoroom_concurrency": 1,
            },
        )
        worker._photoroom_launch_interval = 0.0
        self.assertTrue(worker._photoroom_slots.acquire(blocking=False))
        returned = threading.Event()

        waiter = threading.Thread(
            target=lambda: (
                worker._wait_for_photoroom_launch_slot(),
                returned.set(),
            )
        )
        waiter.start()

        self.assertFalse(returned.wait(timeout=0.1))
        worker._photoroom_slots.release()
        self.assertTrue(returned.wait(timeout=1))
        worker._photoroom_slots.release()
        waiter.join(timeout=1)
        self.assertFalse(waiter.is_alive())


if __name__ == "__main__":
    unittest.main()
