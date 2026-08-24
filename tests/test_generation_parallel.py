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


if __name__ == "__main__":
    unittest.main()
