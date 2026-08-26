import os
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main


class ParallelGenerationTests(unittest.TestCase):
    def test_generation_runs_independent_items_concurrently_and_preserves_indexes(self):
        with tempfile.TemporaryDirectory(prefix="parallel-generation-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                {
                    "kie_api_key": "test-key",
                    "generation_concurrency": 3,
                    "generation_launch_interval": 0,
                },
                generated_prompts=[
                    {"prompt": f"prompt-{index}", "references": []}
                    for index in range(1, 5)
                ],
            )
            lock = threading.Lock()
            active = 0
            max_active = 0
            saved = []

            def fake_generate(self, prompt, references=None):
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1
                return prompt

            def fake_download(self, url, output_path):
                Path(output_path).write_bytes(b"fake-download")

            def fake_save(self, final_url, source_path, output_path, *args):
                Path(output_path).write_bytes(b"fake-result")
                saved.append(Path(output_path).name)

            worker._kie_generate_image = types.MethodType(fake_generate, worker)
            worker._download_file = types.MethodType(fake_download, worker)
            worker._save_final_output = types.MethodType(fake_save, worker)

            worker._mode1_generate(process_generated=False, emit_final=False)

            self.assertGreaterEqual(max_active, 2)
            self.assertEqual(
                [name.split("_")[1] for name in sorted(saved)],
                ["001", "002", "003", "004"],
            )

    def test_global_kie_concurrency_accepts_five_and_one_is_sequential(self):
        for limit in (1, 5):
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
                lock = threading.Lock()
                active = 0
                max_active = 0

                def fake_generate(self, prompt, references=None):
                    nonlocal active, max_active
                    with lock:
                        active += 1
                        max_active = max(max_active, active)
                    time.sleep(0.03)
                    with lock:
                        active -= 1
                    return prompt

                def fake_download(self, url, output_path):
                    Path(output_path).write_bytes(b"fake-download")

                def fake_save(self, final_url, source_path, output_path, *args):
                    Path(output_path).write_bytes(b"fake-result")

                worker._kie_generate_image = types.MethodType(fake_generate, worker)
                worker._download_file = types.MethodType(fake_download, worker)
                worker._save_final_output = types.MethodType(fake_save, worker)

                worker._mode1_generate(process_generated=False, emit_final=False)

                self.assertLessEqual(max_active, limit)
                self.assertEqual(max_active, limit)

    def test_processing_only_overlaps_kie_stages_and_preserves_each_item_order(self):
        with tempfile.TemporaryDirectory(prefix="parallel-processing-") as temp_dir:
            inputs = []
            for index in range(1, 5):
                path = Path(temp_dir) / f"input-{index}.png"
                main.Image.new("RGB", (8, 8), "white").save(path)
                inputs.append(str(path))
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
            lock = threading.Lock()
            active = 0
            max_active = 0
            stages = {index: [] for index in range(1, 5)}

            def fake_upload(self, _path):
                return "https://example.invalid/input.png"

            def fake_kie_task(self, model, image_url, extra_input=None):
                nonlocal active, max_active
                item_index = self._diagnostic_context.item_index
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                    stages[item_index].append(model)
                time.sleep(0.03)
                with lock:
                    active -= 1
                return image_url

            def fake_download(self, _url, output_path):
                main.Image.new("RGBA", (8, 8), "white").save(output_path)

            def fake_save(self, _url, _source, output_path, *_args):
                main.Image.new("RGBA", (8, 8), "white").save(output_path)

            worker._kie_upload_file = types.MethodType(fake_upload, worker)
            worker._kie_run_model_task = types.MethodType(fake_kie_task, worker)
            worker._download_file = types.MethodType(fake_download, worker)
            worker._save_final_output = types.MethodType(fake_save, worker)

            worker._mode2_process_files(emit_final=False)

            self.assertGreaterEqual(max_active, 2)
            self.assertLessEqual(max_active, 3)
            for item_stages in stages.values():
                self.assertEqual(
                    item_stages,
                    [worker.kie_upscale_model, worker.kie_remove_bg_model],
                )

    def test_generate_then_process_uses_the_same_parallel_queue(self):
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
            lock = threading.Lock()
            active = 0
            max_active = 0

            def paid_call():
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1

            def fake_generate(self, prompt, references=None):
                paid_call()
                return "https://example.invalid/generated.png"

            def fake_kie_task(self, model, image_url, extra_input=None):
                paid_call()
                return image_url

            def fake_download(self, _url, output_path):
                main.Image.new("RGBA", (8, 8), "white").save(output_path)

            def fake_save(self, _url, _source, output_path, *_args):
                main.Image.new("RGBA", (8, 8), "white").save(output_path)

            worker._kie_generate_image = types.MethodType(fake_generate, worker)
            worker._kie_upload_file = types.MethodType(
                lambda self, _path: "https://example.invalid/input.png",
                worker,
            )
            worker._kie_run_model_task = types.MethodType(fake_kie_task, worker)
            worker._download_file = types.MethodType(fake_download, worker)
            worker._save_final_output = types.MethodType(fake_save, worker)

            worker._mode1_generate(process_generated=True, emit_final=False)

            self.assertGreaterEqual(max_active, 2)
            self.assertLessEqual(max_active, 3)

    def test_photoroom_and_local_upscale_operations_remain_sequential(self):
        cases = (
            {
                "name": "photoroom",
                "settings": {
                    "upscale": False,
                    "remove_bg": True,
                    "remove_bg_provider": "photoroom",
                    "photoroom_api_key": "photo-key",
                },
                "method": "_run_photoroom_remove_bg",
            },
            {
                "name": "local-upscale",
                "settings": {
                    "upscale": True,
                    "remove_bg": False,
                    "upscale_provider": "local_realesrgan",
                },
                "method": "_run_local_realesrgan",
            },
        )
        for case in cases:
            with self.subTest(provider=case["name"]), tempfile.TemporaryDirectory(
                prefix=f"serial-{case['name']}-"
            ) as temp_dir:
                inputs = []
                for index in range(1, 5):
                    path = Path(temp_dir) / f"input-{index}.png"
                    main.Image.new("RGBA", (8, 8), "white").save(path)
                    inputs.append(str(path))
                settings = {
                    "kie_concurrency": 3,
                    "generation_launch_interval": 0,
                    "output_dir": str(Path(temp_dir) / "output"),
                    **case["settings"],
                }
                worker = main.WorkerThread(
                    "mode2_process",
                    temp_dir,
                    settings,
                    selected_files=inputs,
                )
                lock = threading.Lock()
                active = 0
                max_active = 0

                def fake_local_operation(self, input_path, output_path, *args, **kwargs):
                    nonlocal active, max_active
                    with lock:
                        active += 1
                        max_active = max(max_active, active)
                    time.sleep(0.03)
                    main.Image.new("RGBA", (8, 8), "white").save(output_path)
                    with lock:
                        active -= 1
                    return output_path

                def fake_save(self, _url, _source, output_path, *_args):
                    main.Image.new("RGBA", (8, 8), "white").save(output_path)

                setattr(
                    worker,
                    case["method"],
                    types.MethodType(fake_local_operation, worker),
                )
                worker._save_final_output = types.MethodType(fake_save, worker)

                worker._mode2_process_files(emit_final=False)

                self.assertEqual(max_active, 1)

    def test_stop_after_current_prevents_pending_parallel_items_from_starting(self):
        with tempfile.TemporaryDirectory(prefix="parallel-stop-") as temp_dir:
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
                    for index in range(1, 9)
                ],
            )
            release = threading.Event()
            three_started = threading.Event()
            lock = threading.Lock()
            started = []

            def fake_generate(self, prompt, references=None):
                with lock:
                    started.append(prompt)
                    if len(started) == 3:
                        three_started.set()
                release.wait(timeout=2)
                return prompt

            def fake_download(self, url, output_path):
                Path(output_path).write_bytes(b"fake-download")

            def fake_save(self, final_url, source_path, output_path, *args):
                Path(output_path).write_bytes(b"fake-result")

            worker._kie_generate_image = types.MethodType(fake_generate, worker)
            worker._download_file = types.MethodType(fake_download, worker)
            worker._save_final_output = types.MethodType(fake_save, worker)
            runner = threading.Thread(
                target=worker._mode1_generate,
                kwargs={"process_generated": False, "emit_final": False},
            )
            runner.start()
            self.assertTrue(three_started.wait(timeout=2))

            worker.request_stop_after_current()
            release.set()
            runner.join(timeout=3)

            self.assertFalse(runner.is_alive())
            self.assertEqual(len(started), 3)


if __name__ == "__main__":
    unittest.main()
