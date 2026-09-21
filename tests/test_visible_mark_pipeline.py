import hashlib
import json
import os
import shutil
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main
from visible_mark_cleanup import (
    VisibleMarkCleanupCancelled,
    VisibleMarkCleanupError,
    _confirmed_region_mask,
    cleanup_visible_mark,
    visible_mark_region_key,
)


def create_marked_rgba(path, size=(100, 80), region=(78, 58, 10, 8)):
    width, height = size
    image = Image.new("RGBA", size)
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (30 + x, 60 + y, 90 + (x + y) // 3, 120 + (x + y) % 136)
    draw = ImageDraw.Draw(image)
    x, y, region_width, region_height = region
    draw.rectangle(
        (x, y, x + region_width - 1, y + region_height - 1),
        fill=(250, 250, 250, 255),
    )
    image.save(path, format="PNG")
    return region


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def worker_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "visible_mark_cleanup_enabled": True,
        "visible_mark_cleanup_mode": "confirmed_area",
        "visible_mark_confirmed_regions": {},
        "upscale": False,
        "upscale_after": False,
        "unsharp_enabled": False,
        "remove_bg": False,
        "trim_enabled": False,
        "edge_shrink_enabled": False,
        "cleanup_preserve_icc": True,
        "cleanup_preserve_dpi": True,
    }
    settings.update(overrides)
    return settings


class VisibleMarkPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def isolated_paths(self, root):
        return (
            patch.object(main, "CONFIG_FILE", str(root / "config.json")),
            patch.object(main, "ENV_FILE", str(root / ".env")),
            patch.object(main, "PROMPTS_STORAGE_FILE", str(root / "prompts.json")),
            patch.object(main, "LICENSE_CACHE_FILE", str(root / "license.json")),
            patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
            patch.object(main.QTimer, "singleShot"),
        )

    def close_window(self, window):
        window.settings_save_timer.stop()
        window.api_key_mask_timer.stop()
        window.deleteLater()
        self.app.processEvents()

    def test_confirmed_area_changes_only_mask_and_preserves_source_and_alpha(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-manual-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "raw" / "cleaned.png"
            region = create_marked_rgba(source)
            source_digest = file_hash(source)

            result = cleanup_visible_mark(
                source,
                output,
                "confirmed_area",
                confirmed_region=region,
            )

            self.assertTrue(result.changed)
            self.assertEqual(result.changed_pixels_outside_mask, 0)
            self.assertGreater(result.changed_pixels_inside_mask, 0)
            self.assertEqual(file_hash(source), source_digest)
            with Image.open(source) as original, Image.open(output) as cleaned:
                original.load()
                cleaned.load()
                self.assertEqual(cleaned.size, original.size)
                self.assertEqual(cleaned.mode, "RGBA")
                self.assertEqual(
                    cleaned.getchannel("A").tobytes(),
                    original.getchannel("A").tobytes(),
                )
                original_rgb = np.asarray(original.convert("RGB"))
                cleaned_rgb = np.asarray(cleaned.convert("RGB"))
                changed = np.any(original_rgb != cleaned_rgb, axis=2)
                x, y, width, height = region
                allowed = np.zeros(changed.shape, dtype=bool)
                allowed[y : y + height, x : x + width] = True
                self.assertFalse(np.any(changed & ~allowed))

    def test_confirmed_area_log_requires_visual_verification(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-claim-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            raw_dir = temp_path / "raw"
            raw_dir.mkdir()
            region = create_marked_rgba(source)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                {
                    "visible_mark_cleanup_enabled": True,
                    "visible_mark_cleanup_mode": "confirmed_area",
                    "visible_mark_confirmed_regions": {
                        visible_mark_region_key(source): region,
                    },
                    "upscale": False,
                    "upscale_after": False,
                    "remove_bg": False,
                },
            )
            progress = []
            worker.progress.connect(progress.append)

            result_path = worker._visible_mark_cleanup_pipeline_step(
                str(source),
                str(raw_dir),
                1,
                "file",
            )

            self.assertTrue(Path(result_path).is_file())
            joined = "\n".join(progress)
            self.assertIn("требует визуальной проверки", joined)
            self.assertNotIn("метка удалена", joined.lower())

    def test_gemini_alpha_recovery_preserves_texture_without_a_patch(self):
        class AlphaEngine:
            logo_value = 255.0

            def __init__(self, alpha, region):
                self.alpha = alpha
                self.region = region

            def detect_watermark(self, _image):
                return SimpleNamespace(detected=True, confidence=0.8, region=self.region)

            def get_interpolated_alpha(self, _size):
                return self.alpha

        with tempfile.TemporaryDirectory(prefix="clipart-visible-gemini-alpha-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "cleaned.png"
            width, height = 72, 64
            region = (48, 40, 16, 16)
            base = np.zeros((height, width, 3), dtype=np.uint8)
            for y in range(height):
                for x in range(width):
                    base[y, x] = (30 + x * 2, 40 + y * 2, 70 + (x + y) % 80)
            yy, xx = np.mgrid[-1:1:16j, -1:1:16j]
            alpha = np.clip(0.52 * (1.0 - np.maximum(np.abs(xx), np.abs(yy))), 0.0, 0.52).astype(np.float32)
            marked = base.astype(np.float32)
            x, y, region_width, region_height = region
            roi = marked[y : y + region_height, x : x + region_width]
            roi[:] = roi * (1.0 - alpha[..., None]) + 255.0 * alpha[..., None]
            marked = np.rint(marked).astype(np.uint8)
            Image.fromarray(marked, mode="RGB").save(source)
            source_digest = file_hash(source)

            result = cleanup_visible_mark(
                source,
                output,
                "gemini_auto",
                engine=AlphaEngine(alpha, region),
            )

            self.assertTrue(result.changed)
            self.assertEqual(result.changed_pixels_outside_mask, 0)
            self.assertEqual(file_hash(source), source_digest)
            with Image.open(output) as cleaned:
                cleaned_rgb = np.asarray(cleaned.convert("RGB"))
            difference = np.abs(cleaned_rgb.astype(np.int16) - base.astype(np.int16))
            self.assertLessEqual(int(difference.max()), 2)

    def test_confirmed_area_refines_a_light_service_label_inside_selection(self):
        image = np.full((120, 180, 3), (45, 70, 85), dtype=np.uint8)
        region = (70, 65, 95, 40)
        cv2.putText(
            image,
            "AI",
            (95, 96),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (235, 235, 235),
            3,
            cv2.LINE_AA,
        )

        mask = _confirmed_region_mask(image, region)
        ys, xs = np.where(mask > 0)

        self.assertGreater(xs.size, 0)
        self.assertGreaterEqual(int(xs.min()), region[0])
        self.assertGreaterEqual(int(ys.min()), region[1])
        self.assertLess(int(xs.max()), region[0] + region[2])
        self.assertLess(int(ys.max()), region[1] + region[3])
        self.assertLess(int(xs.max() - xs.min() + 1), region[2])
        self.assertLess(int(ys.max() - ys.min() + 1), region[3])

    def test_automatic_no_detection_leaves_source_unchanged_and_creates_no_raw_file(self):
        class NoDetectionEngine:
            def detect_watermark(self, _image):
                return SimpleNamespace(detected=False, confidence=0.22, region=(0, 0, 0, 0))

            def footprint_mask(self, *_args, **_kwargs):
                raise AssertionError("mask must not be requested without a confident detection")

        with tempfile.TemporaryDirectory(prefix="clipart-visible-unmarked-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "raw" / "cleaned.png"
            create_marked_rgba(source)
            source_digest = file_hash(source)

            result = cleanup_visible_mark(
                source,
                output,
                "gemini_auto",
                engine=NoDetectionEngine(),
            )

            self.assertFalse(result.changed)
            self.assertAlmostEqual(result.confidence, 0.22)
            self.assertEqual(file_hash(source), source_digest)
            self.assertFalse(output.exists())

    def test_failure_and_cancellation_keep_previous_output_and_remove_temp_files(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-rollback-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "existing.png"
            region = create_marked_rgba(source)
            output.write_bytes(b"previous-output")

            with self.assertRaises(VisibleMarkCleanupError):
                cleanup_visible_mark(
                    source,
                    output,
                    "confirmed_area",
                    confirmed_region=(0, 0, 100, 80),
                )
            self.assertEqual(output.read_bytes(), b"previous-output")

            calls = 0

            def cancelled():
                nonlocal calls
                calls += 1
                return calls >= 3

            with self.assertRaises(VisibleMarkCleanupCancelled):
                cleanup_visible_mark(
                    source,
                    output,
                    "confirmed_area",
                    confirmed_region=region,
                    cancelled=cancelled,
                )
            self.assertEqual(output.read_bytes(), b"previous-output")
            self.assertEqual(list(temp_path.glob(".visible-mark-*.tmp.png")), [])

    def test_visible_mark_step_precedes_existing_pipeline_order(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-order-") as temp_dir:
            temp_path = Path(temp_dir)
            raw_dir = temp_path / "raw"
            raw_dir.mkdir()
            source = temp_path / "source.png"
            create_marked_rgba(source)
            worker = main.WorkerThread(
                "mode2_process",
                str(temp_path),
                worker_settings(
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    upscale_after=True,
                    upscale_after_provider="local_realesrgan",
                    unsharp_enabled=True,
                    remove_bg=True,
                    remove_bg_provider="local_ben2",
                    skip_remover_for_alpha=False,
                    edge_shrink_enabled=True,
                    visible_mark_confirmed_regions={
                        visible_mark_region_key(source): (78, 58, 10, 8)
                    },
                ),
            )
            order = []

            def visible_step(self, input_path, raw_path, idx, prefix):
                order.append("visible")
                output_path = Path(raw_path) / "visible.png"
                shutil.copyfile(input_path, output_path)
                return str(output_path)

            def upscale_pass(self, current_path, current_url, **kwargs):
                order.append(kwargs["step_name"])
                target = Path(raw_dir) / (kwargs["step_name"] + ".png")
                with Image.open(current_path) as image:
                    scale = kwargs["local_scale"]
                    image.resize((image.width * scale, image.height * scale)).save(target)
                return str(target), None, True

            def unsharp_step(self, input_path, *_args):
                order.append("unsharp")
                return input_path

            def remove_background(self, input_path, output_path):
                order.append("background")
                shutil.copyfile(input_path, output_path)

            def edge_step(self, input_path, *_args):
                order.append("edge")
                return input_path

            worker._visible_mark_cleanup_pipeline_step = types.MethodType(visible_step, worker)
            worker._run_upscale_pass = types.MethodType(upscale_pass, worker)
            worker._unsharp_mask_pipeline_step = types.MethodType(unsharp_step, worker)
            worker._run_local_ben2 = types.MethodType(remove_background, worker)
            worker._edge_shrink_pipeline_step = types.MethodType(edge_step, worker)

            result_path = worker._run_processing_pipeline(
                str(source),
                None,
                str(raw_dir),
                1,
                "file",
            )

            self.assertTrue(Path(result_path).is_file())
            self.assertEqual(
                order,
                ["visible", "upscaled_before", "unsharp", "background", "upscaled_after", "edge"],
            )

    def test_process_only_visible_cleanup_runs_without_kie(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-process-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            region = create_marked_rgba(source)
            worker = main.WorkerThread(
                "mode2_process",
                str(temp_path),
                worker_settings(
                    visible_mark_confirmed_regions={
                        visible_mark_region_key(source): region
                    }
                ),
                selected_files=[str(source)],
            )

            with patch.object(
                worker,
                "_kie_upload_file",
                side_effect=AssertionError("KIE must not be called"),
            ):
                worker._mode2_process_files(emit_final=False)

            raw_outputs = list((temp_path / "rough").glob("*_visible-mark-cleaned.png"))
            final_outputs = list((temp_path / "output").glob("source_ready*.png"))
            self.assertEqual(len(raw_outputs), 1)
            self.assertEqual(len(final_outputs), 1)
            self.assertFalse(worker.kie_api_key)
            with Image.open(final_outputs[0]) as final_image:
                self.assertEqual(final_image.size, (100, 80))
                self.assertEqual(final_image.mode, "RGBA")

    def test_existing_alpha_bypasses_remover_by_default(self):
        with tempfile.TemporaryDirectory(prefix="clipart-alpha-reuse-") as temp_dir:
            temp_path = Path(temp_dir)
            raw_dir = temp_path / "raw"
            raw_dir.mkdir()
            source = temp_path / "source.png"
            native = Image.new("RGBA", (8, 8), (20, 30, 40, 0))
            native.putpixel((4, 4), (20, 30, 40, 128))
            native.save(source, format="PNG")
            worker = main.WorkerThread(
                "mode2_process",
                str(temp_path),
                worker_settings(
                    remove_bg=True,
                    remove_bg_provider="local_rembg",
                ),
            )
            worker._run_local_rembg = lambda *_args: self.fail(
                "remover must not run for an existing alpha mask"
            )
            progress_messages = []
            diagnostic_events = []
            worker.progress.connect(progress_messages.append)
            worker.diagnostic.connect(diagnostic_events.append)

            result_path = worker._run_processing_pipeline(
                str(source), None, str(raw_dir), 1, "file"
            )

            with Image.open(result_path) as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))
                self.assertEqual(result.getpixel((4, 4)), (20, 30, 40, 128))
            self.assertTrue(
                any("alpha-маска" in message for message in progress_messages)
            )
            stage_finished = next(
                event
                for event in diagnostic_events
                if event["event"] == "stage_finished"
                and event.get("stage") == "background_removal"
            )
            self.assertEqual(stage_finished["outcome"], "skipped")
            self.assertEqual(stage_finished["status"], "already_alpha")

    def test_ui_passes_confirmed_regions_only_to_current_run(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-ui-run-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            region = create_marked_rgba(source)
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()
                window.work_dir = temp_dir
                window.selected_files = [str(source)]
                window.radio_run_process.setChecked(True)
                window.chk_visible_mark_cleanup.setChecked(True)
                window.visible_mark_mode_combo.setCurrentIndex(
                    window.visible_mark_mode_combo.findData("confirmed_area")
                )
                window.chk_upscale.setChecked(False)
                window.chk_upscale_after.setChecked(False)
                window.chk_unsharp.setChecked(False)
                window.chk_remove_bg.setChecked(False)
                window.chk_edge_shrink.setChecked(False)
                window.chk_trim.setChecked(False)
                window.kie_api_key_input.setText("")

                expected_mapping = {visible_mark_region_key(source): region}
                with (
                    patch.object(
                        window,
                        "collect_visible_mark_regions",
                        return_value=expected_mapping,
                    ) as collect_mock,
                    patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                ):
                    window.start_work()

                collect_mock.assert_called_once()
                warning_mock.assert_not_called()
                start_mock.assert_called_once()
                self.assertFalse(window.worker.kie_api_key)
                self.assertEqual(window.worker.visible_mark_confirmed_regions, expected_mapping)
                saved_config = json.loads((temp_path / "config.json").read_text(encoding="utf-8"))
                self.assertNotIn("visible_mark_confirmed_regions", saved_config)
                self.close_window(window)


if __name__ == "__main__":
    unittest.main()
