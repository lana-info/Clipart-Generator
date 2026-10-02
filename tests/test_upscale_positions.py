import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

import main
from studio_alpha_qc import inspect_alpha_png


def processing_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "upscale": True,
        "upscale_after": False,
        "upscale_provider": "local_realesrgan",
        "upscale_after_provider": "local_realesrgan",
        "local_realesrgan_profile": "clipart",
        "local_realesrgan_scale": 2,
        "local_realesrgan_after_scale": 2,
        "unsharp_enabled": False,
        "remove_bg": True,
        "remove_bg_provider": "local_ben2",
        "edge_shrink_enabled": False,
        "trim_enabled": False,
        "export_300_dpi": False,
    }
    settings.update(overrides)
    return settings


def create_rgb_source(path, size=(8, 6)):
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).rectangle((2, 1, 6, 4), fill=(180, 70, 100))
    image.save(path, format="PNG")


class UpscalePositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def test_final_upscale_checks_actual_pixels_before_publication(self):
        for provider in ("fal", "kie", "local_realesrgan"):
            for defect in ("opaque", "empty", "corrupt", "wrong_size", "valid"):
                with self.subTest(provider=provider, defect=defect), tempfile.TemporaryDirectory() as folder:
                    root = Path(folder)
                    source = root / "source.png"
                    image = Image.new("RGBA", (32, 32))
                    ImageDraw.Draw(image).ellipse((8, 8, 24, 24), fill=(200, 90, 50, 255))
                    image.save(source)
                    original = source.read_bytes()
                    output = root / "upscaled.png"
                    candidate = image.resize((128, 128))
                    if defect == "opaque":
                        candidate = candidate.convert("RGB")
                    elif defect == "empty":
                        candidate.putalpha(0)
                    elif defect == "wrong_size":
                        candidate = image
                    candidate.save(output)
                    if defect == "corrupt":
                        output.write_bytes(b"not an image")
                    worker = main.WorkerThread("mode2_process", folder, processing_settings(
                        upscale=False, remove_bg=False, upscale_after=True,
                        upscale_after_provider=provider, local_realesrgan_after_scale=4,
                        fal_upscale_after_model="topaz/upscale/image/transparent",
                        upscale_factor=4,
                    ))
                    messages = []
                    events = []
                    worker.progress.connect(messages.append)
                    worker.item_progress.connect(events.append)
                    with patch.object(worker, "_run_upscale_pass", return_value=(str(output), None, True)) as upscale:
                        if defect in {"valid", "opaque", "wrong_size"}:
                            result = worker._run_processing_pipeline(str(source), None, folder, 1, "file")
                            self.assertEqual(result, str(output))
                            self.assertEqual(worker._item_context.manual_transparency_required, defect == "opaque")
                            if defect == "opaque":
                                self.assertTrue(any("потерял прозрачность" in text for text in messages))
                                self.assertTrue(any(event["status"] == "stage_failed" and event["stage"] == "alpha_validation" for event in events))
                                saved = root / "final.png"
                                worker._save_final_output(result, str(source), str(saved), folder, 1, "file")
                                report = inspect_alpha_png(saved)
                                self.assertEqual(report.status, "block")
                                self.assertTrue(any(issue.code == "no_transparency" for issue in report.issues))
                            if defect == "wrong_size":
                                self.assertTrue(any("32x32 px вместо 128x128 px" in text for text in messages))
                        else:
                            with self.assertRaisesRegex(ValueError, "Исходник до апскейла сохранён"):
                                worker._run_processing_pipeline(str(source), None, folder, 1, "file")
                        upscale.assert_called_once()
                    self.assertEqual(source.read_bytes(), original)

    def run_local_pipeline(self, temp_path, **overrides):
        source_path = temp_path / "source.png"
        create_rgb_source(source_path)
        raw_dir = temp_path / "raw"
        raw_dir.mkdir()
        worker = main.WorkerThread(
            "mode2_process",
            str(temp_path),
            processing_settings(**overrides),
            selected_files=[str(source_path)],
        )
        order = []

        def fake_upscale(worker_self, input_path, raw_path, idx, prefix, step_name):
            order.append(step_name)
            scale = worker_self._active_local_realesrgan_scale
            output_path = Path(raw_path) / f"{prefix}_{step_name}_{idx:03d}_{worker_self.run_stamp}.png"
            with Image.open(input_path) as source:
                result = source.convert("RGBA").resize(
                    (source.width * scale, source.height * scale),
                    Image.Resampling.NEAREST,
                )
                result.save(output_path, format="PNG")
            return str(output_path)

        def fake_remove(worker_self, input_path, output_path):
            order.append("remove_bg")
            with Image.open(input_path) as source:
                result = source.convert("RGBA")
                alpha = Image.new("L", result.size, 0)
                inset = max(1, result.width // 5)
                ImageDraw.Draw(alpha).rectangle(
                    (inset, inset, result.width - inset - 1, result.height - inset - 1),
                    fill=255,
                )
                result.putalpha(alpha)
                result.save(output_path, format="PNG")
            return output_path

        worker._local_realesrgan_pipeline_step = types.MethodType(fake_upscale, worker)
        worker._run_local_ben2 = types.MethodType(fake_remove, worker)
        result_path = worker._run_processing_pipeline(
            str(source_path),
            None,
            str(raw_dir),
            1,
            "file",
        )
        return worker, order, Path(result_path)

    def test_trim_before_upscale_and_final_png_300_dpi(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            worker, order, result = self.run_local_pipeline(
                root, upscale=False, upscale_after=True,
                trim_enabled=True, export_300_dpi=True,
            )
            self.assertEqual(order, ["remove_bg", "upscaled_after"])
            # Fixture removes a one-pixel frame from 8x6 before the 2x pass.
            with Image.open(result) as image:
                self.assertEqual(image.size, (12, 8))
            # Simulate an upscaler returning new transparent working margins.
            with Image.open(result) as image:
                padded = Image.new("RGBA", (16, 12))
                padded.paste(image, (2, 2))
                padded.save(result)
            original = (root / "source.png").read_bytes()
            final = root / "ready.png"
            worker._save_final_output(str(result), str(result), str(final),
                                      str(root / "raw"), 1, "file")
            with Image.open(final) as image:
                self.assertEqual(image.size, (12, 8))
                self.assertEqual(image.getchannel("A").getbbox(), (0, 0, 12, 8))
                self.assertAlmostEqual(image.info["dpi"][0], 300, places=2)
                self.assertAlmostEqual(image.info["dpi"][1], 300, places=2)
            self.assertEqual((root / "source.png").read_bytes(), original)

    def test_pretrim_invalidates_url_preserves_faint_details_and_pattern_canvas(self):
        for kind, thin, expected in (("clipart", False, (4, 4)),
                                     ("clipart", True, (7, 4)),
                                     ("pattern", False, (12, 10))):
            with self.subTest(kind=kind, thin=thin), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                source = root / "source.png"
                image = Image.new("RGBA", (12, 10))
                ImageDraw.Draw(image).rectangle((4, 3, 7, 6), fill=(100, 60, 20, 255))
                if thin:
                    image.putpixel((1, 3), (100, 60, 20, 1))
                image.save(source)
                worker = main.WorkerThread("mode2_process", folder, processing_settings(
                    upscale=False, remove_bg=False, upscale_after=True, trim_enabled=True))
                def upscale(**kwargs):
                    with Image.open(kwargs["current_path"]) as cropped:
                        self.assertEqual(cropped.size, expected)
                        self.assertEqual(kwargs["current_url"],
                            None if kind == "clipart" else "https://example.invalid/source.png")
                        if thin:
                            self.assertEqual(cropped.getpixel((0, 0))[3], 1)
                        output = root / "upscaled.png"
                        cropped.resize((cropped.width * 2, cropped.height * 2),
                                       Image.Resampling.NEAREST).save(output)
                    return str(output), None, True
                with patch.object(worker, "_run_upscale_pass", side_effect=upscale) as mocked:
                    worker._run_processing_pipeline(str(source), "https://example.invalid/source.png",
                                                     folder, 1, "file", result_kind=kind)
                mocked.assert_called_once()

    def test_before_after_and_both_run_in_selected_order(self):
        cases = (
            ("before", {"upscale": True, "upscale_after": False}, ["upscaled_before", "remove_bg"], (16, 12)),
            ("after", {"upscale": False, "upscale_after": True}, ["remove_bg", "upscaled_after"], (16, 12)),
            (
                "both",
                {"upscale": True, "upscale_after": True},
                ["upscaled_before", "remove_bg", "upscaled_after"],
                (32, 24),
            ),
        )
        for name, overrides, expected_order, expected_size in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(prefix=f"clipart-{name}-") as temp_dir:
                worker, order, result_path = self.run_local_pipeline(Path(temp_dir), **overrides)
                self.assertEqual(order, expected_order)
                with Image.open(result_path) as result:
                    self.assertEqual(result.size, expected_size)
                    self.assertEqual(result.mode, "RGBA")
                    self.assertEqual(result.getchannel("A").getextrema(), (0, 255))
                expected_factor = 4 if name == "both" else 2
                self.assertEqual(worker._combined_upscale_factor(), expected_factor)

    def test_four_by_four_reports_sixteen_and_legacy_config_stays_before_only(self):
        both_worker = main.WorkerThread(
            "mode2_process",
            ".",
            processing_settings(
                upscale=True,
                upscale_after=True,
                local_realesrgan_scale=4,
                local_realesrgan_after_scale=4,
            ),
        )
        self.assertEqual(both_worker._combined_upscale_factor(), 16)

        old_enabled = main.WorkerThread("mode2_process", ".", {"upscale": True, "remove_bg": False})
        old_disabled = main.WorkerThread("mode2_process", ".", {"upscale": False, "remove_bg": False})
        self.assertTrue(old_enabled.upscale)
        self.assertFalse(old_enabled.upscale_after)
        self.assertFalse(old_disabled.upscale)
        self.assertFalse(old_disabled.upscale_after)

    def test_fal_combined_factor_matches_selected_endpoint_contract(self):
        bria = main.WorkerThread(
            "mode2_process",
            ".",
            processing_settings(
                upscale_provider="fal",
                fal_upscale_model="bria/upscale/creative",
                fal_upscale_scale=4,
                remove_bg=False,
            ),
        )
        topaz = main.WorkerThread(
            "mode2_process",
            ".",
            processing_settings(
                upscale_provider="fal",
                fal_upscale_model="topaz/upscale/image/precision",
                fal_upscale_scale=4,
                remove_bg=False,
            ),
        )
        recraft = main.WorkerThread(
            "mode2_process",
            ".",
            processing_settings(
                upscale_provider="fal",
                fal_upscale_model="fal-ai/recraft/upscale/crisp",
                fal_upscale_scale=2,
                remove_bg=False,
            ),
        )
        bria_increase = main.WorkerThread(
            "mode2_process",
            ".",
            processing_settings(
                upscale_provider="fal",
                fal_upscale_model="bria/increase-resolution",
                fal_upscale_scale=4,
                remove_bg=False,
            ),
        )
        topaz_transparent = main.WorkerThread(
            "mode2_process",
            ".",
            processing_settings(
                upscale_provider="fal",
                fal_upscale_model="topaz/upscale/image/transparent",
                fal_upscale_scale=2,
                remove_bg=False,
            ),
        )

        self.assertEqual(bria._combined_upscale_factor(), 2)
        self.assertEqual(topaz._combined_upscale_factor(), 4)
        self.assertEqual(recraft._combined_upscale_factor(), 4)
        self.assertEqual(bria_increase._combined_upscale_factor(), 4)
        self.assertEqual(topaz_transparent._combined_upscale_factor(), 4)

    def test_fal_ui_total_factor_matches_selected_endpoint_contract(self):
        fal_provider = types.SimpleNamespace(currentData=lambda: "fal")
        unused_combo = types.SimpleNamespace()

        bria_window = types.SimpleNamespace(
            config={
                "fal_upscale_model": "bria/upscale/creative",
                "fal_upscale_scale": 4,
            }
        )
        topaz_window = types.SimpleNamespace(
            config={
                "fal_upscale_model": "topaz/upscale/image/precision",
                "fal_upscale_scale": 4,
            }
        )
        recraft_window = types.SimpleNamespace(
            config={
                "fal_upscale_model": "fal-ai/recraft/upscale/crisp",
                "fal_upscale_scale": 2,
            }
        )

        self.assertEqual(
            main.MainWindow._ui_upscale_pass_factor(
                bria_window,
                fal_provider,
                unused_combo,
                unused_combo,
            ),
            2,
        )
        self.assertEqual(
            main.MainWindow._ui_upscale_pass_factor(
                topaz_window,
                fal_provider,
                unused_combo,
                unused_combo,
            ),
            4,
        )
        self.assertEqual(
            main.MainWindow._ui_upscale_pass_factor(
                recraft_window,
                fal_provider,
                unused_combo,
                unused_combo,
            ),
            4,
        )

    def test_after_pass_can_use_kie_and_requires_only_its_selected_key(self):
        with tempfile.TemporaryDirectory(prefix="clipart-upscale-after-kie-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path, size=(64, 48))
            settings = processing_settings(
                kie_api_key="test-kie-key",
                upscale=False,
                upscale_after=True,
                upscale_after_provider="kie",
                kie_upscale_after_model="recraft/crisp-upscale",
                remove_bg=False,
            )
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                settings,
                selected_files=[str(source_path)],
            )
            calls = []

            def fake_upload(worker_self, file_path):
                calls.append("upload")
                return "mock://source"

            def fake_model(worker_self, model_name, image_url, extra_input=None):
                calls.append((model_name, extra_input))
                return "mock://upscaled"

            def fake_download(worker_self, image_url, output_path):
                calls.append("download")
                with Image.open(source_path) as source:
                    source.convert("RGBA").resize((256, 192), Image.Resampling.NEAREST).save(
                        output_path,
                        format="PNG",
                    )

            worker._kie_upload_file = types.MethodType(fake_upload, worker)
            worker._kie_run_model_task = types.MethodType(fake_model, worker)
            worker._download_file = types.MethodType(fake_download, worker)
            worker._mode2_process_files(emit_final=False)

            self.assertEqual(calls[0], "upload")
            self.assertEqual(calls[1], ("recraft/crisp-upscale", None))
            self.assertEqual(calls.count("download"), 1)
            self.assertEqual(len(list((temp_path / "output").glob("*.png"))), 1)

            missing_key_worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {**settings, "kie_api_key": ""},
                selected_files=[str(source_path)],
            )
            with self.assertRaisesRegex(ValueError, "KIE API Key"):
                missing_key_worker._mode2_process_files(emit_final=False)

    def test_recraft_after_background_removal_is_rejected(self):
        message = main.validate_upscale_after_background_order(
            remove_bg=True,
            upscale_after=True,
            provider="kie",
            model="recraft/crisp-upscale",
        )
        self.assertIn("прозрач", message.lower())

        self.assertEqual(
            main.validate_upscale_after_background_order(
                remove_bg=True,
                upscale_after=True,
                provider="local_realesrgan",
                model="recraft/crisp-upscale",
            ),
            "",
        )

    def test_ui_saves_independent_passes_and_combined_multiplier(self):
        with tempfile.TemporaryDirectory(prefix="clipart-upscale-ui-") as temp_dir:
            temp_path = Path(temp_dir)
            config_path = temp_path / "config.json"
            config_path.write_text(json.dumps({"upscale": False}), encoding="utf-8")
            with (
                patch.multiple(main, CONFIG_FILE=str(config_path), USER_DATA_DIR=str(config_path.parent)),
                patch.object(main, "ENV_FILE", str(temp_path / ".env")),
                patch.object(main, "PROMPTS_STORAGE_FILE", str(temp_path / "prompts.json")),
                patch.object(main, "LICENSE_CACHE_FILE", str(temp_path / "license.json")),
                patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
                patch.object(main.QTimer, "singleShot"),
            ):
                window = main.MainWindow()
                self.assertFalse(window.chk_upscale.isChecked())
                self.assertFalse(window.chk_upscale_after.isChecked())

                window.chk_upscale.setChecked(True)
                window.chk_upscale_after.setChecked(True)
                window.upscale_provider_combo.setCurrentIndex(
                    window.upscale_provider_combo.findData("local_realesrgan")
                )
                window.upscale_after_provider_combo.setCurrentIndex(
                    window.upscale_after_provider_combo.findData("local_realesrgan")
                )
                window.local_realesrgan_scale_combo.setCurrentIndex(
                    window.local_realesrgan_scale_combo.findData(4)
                )
                window.local_realesrgan_after_scale_combo.setCurrentIndex(
                    window.local_realesrgan_after_scale_combo.findData(4)
                )
                window.update_upscale_total_label()
                self.assertEqual(window.upscale_total_label.text(), "Итоговый масштаб: 16x")
                window.persist_ui_settings()
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

                restored = main.MainWindow()
                self.assertTrue(restored.chk_upscale.isChecked())
                self.assertTrue(restored.chk_upscale_after.isChecked())
                self.assertEqual(restored.upscale_after_provider_combo.currentData(), "local_realesrgan")
                self.assertEqual(restored.local_realesrgan_after_scale_combo.currentData(), 4)
                self.assertEqual(restored.upscale_total_label.text(), "Итоговый масштаб: 16x")
                restored.settings_save_timer.stop()
                restored.api_key_mask_timer.stop()
                restored.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
