import os
import tempfile
import threading
import time
import types
import unittest
from collections import defaultdict
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
        self.order = defaultdict(list)
        self.kie_models = defaultdict(list)

    def start(self, provider, item_index, model=""):
        with self.lock:
            self.active[provider] += 1
            self.maximum[provider] = max(
                self.maximum[provider], self.active[provider]
            )
            self.max_remote = max(self.max_remote, sum(self.active.values()))
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
):
    tasks = {}
    tasks_lock = threading.Lock()

    def fake_create(worker_self, model, input_payload):
        item_index = worker_self._diagnostic_context.item_index
        with tasks_lock:
            task_id = f"task-{item_index}-{len(tasks) + 1}"
            tasks[task_id] = item_index
        activity.start("kie", item_index, model)
        if started is not None:
            with tasks_lock:
                if len(tasks) >= started_target:
                    started.set()
        return task_id

    def fake_wait(worker_self, task_id):
        try:
            if release is None:
                time.sleep(delay)
            else:
                release.wait(timeout=2)
            return f"https://example.invalid/{task_id}.png"
        finally:
            activity.finish("kie")

    worker._kie_create_task = types.MethodType(fake_create, worker)
    worker._kie_wait_result = types.MethodType(fake_wait, worker)


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

    def fake_request(worker_self, req, timeout=None):
        nonlocal start_count
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
    def fake_upload(worker_self, _path):
        return "https://example.invalid/input.png"

    def fake_download(worker_self, _url, output_path):
        main.Image.new("RGBA", (8, 8), "white").save(output_path)

    def fake_save(worker_self, _url, _source, output_path, *_args):
        main.Image.new("RGBA", (8, 8), "white").save(output_path)
        if saved is not None:
            saved.append(Path(output_path).name)

    worker._kie_upload_file = types.MethodType(fake_upload, worker)
    worker._download_file = types.MethodType(fake_download, worker)
    worker._save_final_output = types.MethodType(fake_save, worker)


class ParallelGenerationTests(unittest.TestCase):
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
                [name.split("_")[1] for name in sorted(saved)],
                ["001", "002", "003", "004"],
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
                        "_photoroom_launch_interval": 0,
                        "upscale": False,
                        "remove_bg": True,
                        "remove_bg_provider": "photoroom",
                        "output_dir": str(Path(temp_dir) / "output"),
                    },
                    selected_files=create_inputs(temp_dir, 6),
                )
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
                    "_photoroom_launch_interval": 0,
                    "upscale": True,
                    "upscale_provider": "kie",
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=create_inputs(temp_dir, 6),
            )
            activity = ProviderActivity()
            install_fake_kie_network(worker, activity, delay=0.02)
            install_fake_photoroom_network(worker, activity, delay=0.10)
            install_fake_file_io(worker)

            worker._mode2_process_files(emit_final=False)

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
                    "_photoroom_launch_interval": 0,
                    "upscale": True,
                    "upscale_provider": "local_realesrgan",
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=create_inputs(temp_dir, 5),
            )
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
                    "_photoroom_launch_interval": 0,
                    "upscale": False,
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "output_dir": str(Path(temp_dir) / "output"),
                },
                selected_files=create_inputs(temp_dir, 8),
            )
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
                "_photoroom_launch_interval": 1.0,
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

    def test_photoroom_launch_guard_does_not_reserve_start_while_provider_is_full(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            {
                "photoroom_concurrency": 1,
                "_photoroom_launch_interval": 0,
            },
        )
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
