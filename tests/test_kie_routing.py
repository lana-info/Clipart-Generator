import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

import main


DUMMY_KIE_KEY = "test-kie-secret-must-not-appear-in-logs"


def kie_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "upscale": False,
        "upscale_provider": "kie",
        "local_realesrgan_scale": 2,
        "unsharp_enabled": False,
        "remove_bg": False,
        "remove_bg_provider": "kie",
        "kie_remove_bg_model": "recraft/remove-background",
        "edge_shrink_enabled": False,
        "edge_shrink_pixels": 1,
        "trim_enabled": False,
        "export_300_dpi": False,
    }
    settings.update(overrides)
    return settings


def create_rgb_source(path, size=(16, 12)):
    image = Image.new("RGB", size, (235, 235, 235))
    ImageDraw.Draw(image).rectangle((3, 2, size[0] - 4, size[1] - 3), fill=(180, 70, 100))
    image.save(path, format="PNG")
    return image


class KieRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def connect_messages(self, worker):
        progress = []
        finished = []
        worker.progress.connect(progress.append)
        worker.finished.connect(finished.append)
        return progress, finished

    def assert_secret_not_logged(self, progress, finished=()):
        messages = "\n".join([*progress, *finished])
        self.assertNotIn(DUMMY_KIE_KEY, messages)

    def test_provider_combinations_require_key_only_for_kie_steps(self):
        cases = [
            (
                "local_only",
                kie_settings(
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    remove_bg=True,
                    remove_bg_provider="local_ben2",
                ),
                False,
            ),
            ("kie_upscale", kie_settings(upscale=True, upscale_provider="kie"), True),
            ("kie_remove", kie_settings(remove_bg=True, remove_bg_provider="kie"), True),
            (
                "local_to_kie",
                kie_settings(
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    remove_bg=True,
                    remove_bg_provider="kie",
                ),
                True,
            ),
            (
                "kie_to_local",
                kie_settings(
                    upscale=True,
                    upscale_provider="kie",
                    remove_bg=True,
                    remove_bg_provider="local_ben2",
                ),
                True,
            ),
        ]

        for name, settings, expected in cases:
            with self.subTest(name=name):
                worker = main.WorkerThread("mode2_process", ".", settings)
                requires_kie = worker._uses_kie_upscale() or worker._uses_kie_remove_bg()
                self.assertEqual(requires_kie, expected)
                if expected:
                    with self.assertRaisesRegex(ValueError, "KIE API Key"):
                        worker._mode2_process_files(emit_final=False)

    def test_start_button_uses_the_same_key_routing_rules(self):
        cases = [
            ("local_remove", False, "kie", True, "local_ben2", False),
            ("kie_upscale", True, "kie", False, "kie", True),
            ("kie_remove", False, "kie", True, "kie", True),
            ("local_to_kie", True, "local_realesrgan", True, "kie", True),
            ("kie_to_local", True, "kie", True, "local_ben2", True),
        ]

        with tempfile.TemporaryDirectory(prefix="clipart-kie-ui-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)

            for name, upscale, upscale_provider, remove_bg, remove_provider, expects_warning in cases:
                with self.subTest(name=name):
                    case_dir = temp_path / name
                    case_dir.mkdir()
                    with (
                        patch.object(main, "CONFIG_FILE", str(case_dir / "config.json")),
                        patch.object(main, "PROMPTS_STORAGE_FILE", str(case_dir / "prompts.json")),
                        patch.object(main, "LICENSE_CACHE_FILE", str(case_dir / "license_cache.json")),
                        patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
                        patch.object(main.QTimer, "singleShot"),
                        patch.object(main.QMessageBox, "warning") as warning_mock,
                        patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                    ):
                        window = main.MainWindow()
                        window.work_dir = str(case_dir)
                        window.selected_files = [str(source_path)]
                        window.radio_run_process.setChecked(True)
                        window.kie_api_key_input.setText("")
                        window.chk_upscale.setChecked(upscale)
                        window.upscale_provider_combo.setCurrentIndex(
                            window.upscale_provider_combo.findData(upscale_provider)
                        )
                        window.chk_unsharp.setChecked(False)
                        window.chk_remove_bg.setChecked(remove_bg)
                        window.remove_bg_provider_combo.setCurrentIndex(
                            window.remove_bg_provider_combo.findData(remove_provider)
                        )
                        window.chk_edge_shrink.setChecked(False)
                        window.chk_trim.setChecked(False)

                        window.start_work()

                        if expects_warning:
                            warning_mock.assert_called_once()
                            self.assertIn("KIE API Key", str(warning_mock.call_args.args[2]))
                            start_mock.assert_not_called()
                        else:
                            warning_mock.assert_not_called()
                            start_mock.assert_called_once()
                        window.settings_save_timer.stop()
                        window.api_key_mask_timer.stop()
                        window.deleteLater()
                        self.app.processEvents()

    def test_generate_only_saves_raw_and_output_without_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-generate-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
                generated_prompts=[{"prompt": "test clipart", "references": []}],
            )
            progress, finished = self.connect_messages(worker)
            calls = []

            def fake_generate(self, prompt, references=None):
                calls.append(("generate", prompt, tuple(references or [])))
                return "mock://generated"

            def fake_download(self, url, output_path):
                calls.append(("download", url))
                create_rgb_source(output_path)

            worker._kie_generate_image = types.MethodType(fake_generate, worker)
            worker._download_file = types.MethodType(fake_download, worker)

            worker._mode1_generate(process_generated=False)

            raw_outputs = list((Path(temp_dir) / "raw").glob("*.png"))
            final_outputs = list((Path(temp_dir) / "output").glob("*.png"))
            self.assertEqual([call[0] for call in calls], ["generate", "download", "download"])
            self.assertEqual(len(raw_outputs), 1)
            self.assertEqual(len(final_outputs), 1)
            self.assertTrue(any("Готово (1/1)" in message for message in finished))
            self.assert_secret_not_logged(progress, finished)

    def test_local_to_kie_mixed_pipeline_saves_intermediates_and_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-mixed-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path, size=(20, 16))
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(
                    kie_api_key=DUMMY_KIE_KEY,
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    remove_bg=True,
                    remove_bg_provider="kie",
                    edge_shrink_enabled=True,
                ),
                selected_files=[str(source_path)],
            )
            progress, finished = self.connect_messages(worker)
            calls = []

            def fake_local_upscale(self, input_path, raw_dir, idx, prefix, step_name):
                calls.append("local_upscale")
                output_path = Path(raw_dir) / f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png"
                shutil.copyfile(input_path, output_path)
                return str(output_path)

            def fake_upload(self, file_path):
                calls.append("upload")
                if not Path(file_path).is_file():
                    raise AssertionError(f"Upload source does not exist: {file_path}")
                return "mock://uploaded"

            def fake_run_model(self, model, image_url, extra_input=None):
                calls.append("kie_remove")
                if model != "recraft/remove-background":
                    raise AssertionError(f"Unexpected KIE model: {model}")
                if image_url != "mock://uploaded":
                    raise AssertionError(f"Unexpected KIE input: {image_url}")
                return "mock://removed"

            def fake_download(self, url, output_path):
                calls.append("download_removed")
                image = Image.new("RGBA", (20, 16), (180, 70, 100, 0))
                alpha = Image.new("L", image.size, 0)
                ImageDraw.Draw(alpha).rectangle((3, 2, 16, 13), fill=255)
                image.putalpha(alpha)
                image.save(output_path, format="PNG")

            worker._local_realesrgan_pipeline_step = types.MethodType(fake_local_upscale, worker)
            worker._kie_upload_file = types.MethodType(fake_upload, worker)
            worker._kie_run_model_task = types.MethodType(fake_run_model, worker)
            worker._download_file = types.MethodType(fake_download, worker)

            worker._mode2_process_files()

            self.assertEqual(calls, ["local_upscale", "upload", "kie_remove", "download_removed"])
            raw_outputs = list((temp_path / "raw").glob("*.png"))
            final_outputs = list((temp_path / "output").glob("*.png"))
            self.assertGreaterEqual(len(raw_outputs), 3)
            self.assertEqual(len(final_outputs), 1)
            with Image.open(final_outputs[0]) as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertNotEqual(result.getchannel("A").getextrema(), (0, 0))
            self.assertTrue(any("Готово (1/1)" in message for message in finished))
            self.assert_secret_not_logged(progress, finished)

    def test_provider_error_is_visible_without_exposing_key(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-error-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
                generated_prompts=["test clipart"],
            )
            progress, finished = self.connect_messages(worker)

            def fail_generate(self, prompt, references=None):
                raise RuntimeError("provider unavailable")

            worker._kie_generate_image = types.MethodType(fail_generate, worker)

            worker._mode1_generate(process_generated=False)

            self.assertTrue(any("provider unavailable" in message for message in progress))
            self.assertTrue(any("Готово (0/1)" in message for message in finished))
            self.assertFalse(list((Path(temp_dir) / "output").glob("*.png")))
            self.assert_secret_not_logged(progress, finished)


if __name__ == "__main__":
    unittest.main()
