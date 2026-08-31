import shutil
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

import main


ROOT_DIR = Path(__file__).resolve().parents[1]
REALESRGAN_DIR = ROOT_DIR / "realesrgan-ncnn-vulkan-20211212-windows"


def worker_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "upscale": False,
        "upscale_provider": "local_realesrgan",
        "local_realesrgan_dir": str(REALESRGAN_DIR),
        "local_realesrgan_profile": "clipart",
        "local_realesrgan_scale": 2,
        "unsharp_enabled": False,
        "unsharp_amount": 100,
        "unsharp_radius": 2,
        "unsharp_threshold": 0,
        "remove_bg": False,
        "remove_bg_provider": "local_ben2",
        "local_rembg_edge_quality": "normal",
        "local_ben2_alpha_threshold": 24,
        "local_ben2_edge_softness": 0,
        "local_ben2_corner_radius": 0,
        "edge_shrink_enabled": False,
        "edge_shrink_pixels": 1,
        "trim_enabled": False,
        "trim_mode": "alpha",
        "export_300_dpi": False,
    }
    settings.update(overrides)
    return settings


def create_quadrant_rgba(path, size=(32, 28)):
    width, height = size
    image = Image.new("RGBA", size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = 2, 2, width - 3, height - 3
    middle_x = width // 2
    middle_y = height // 2
    draw.rectangle((left, top, middle_x - 1, middle_y - 1), fill=(230, 20, 20, 255))
    draw.rectangle((middle_x, top, right, middle_y - 1), fill=(20, 210, 20, 255))
    draw.rectangle((left, middle_y, middle_x - 1, bottom), fill=(20, 40, 230, 255))
    draw.rectangle((middle_x, middle_y, right, bottom), fill=(210, 20, 210, 255))
    image.save(path, format="PNG")
    return image


class LocalProcessingAcceptanceTests(unittest.TestCase):
    def make_worker(self, work_dir, **settings):
        return main.WorkerThread(
            "mode2_process",
            str(work_dir),
            worker_settings(**settings),
        )

    def test_local_chroma_pipeline_uses_automatic_engine_and_ignores_legacy_numbers(self):
        with tempfile.TemporaryDirectory(prefix="automatic-chroma-") as temp:
            root = Path(temp)
            source_path = root / "source.png"
            raw_dir = root / "rough"
            raw_dir.mkdir()
            image = Image.new("RGBA", (15, 15), (0, 0, 255, 255))
            for y in range(4, 11):
                for x in range(4, 11):
                    image.putpixel((x, y), (220, 90, 40, 255))
            image.save(source_path)
            worker = self.make_worker(
                root,
                remove_bg=True,
                remove_bg_provider="local_chroma_key",
                chroma_key_color="custom",
                chroma_key_custom_color="#0000FF",
                chroma_key_tolerance=255,
                chroma_key_softness=255,
            )

            with patch.object(
                main,
                "remove_chroma_key_automatic",
                wraps=main.remove_chroma_key_automatic,
            ) as automatic:
                result_path = worker._run_processing_pipeline(
                    str(source_path), None, str(raw_dir), 1, "file"
                )

            automatic.assert_called_once()
            with Image.open(result_path) as result:
                self.assertEqual(result.getpixel((0, 0))[3], 0)
                self.assertEqual(result.getpixel((7, 7)), (220, 90, 40, 255))

    def test_local_chroma_pipeline_rejects_an_ambiguous_background(self):
        with tempfile.TemporaryDirectory(prefix="ambiguous-chroma-") as temp:
            root = Path(temp)
            source_path = root / "source.png"
            raw_dir = root / "rough"
            raw_dir.mkdir()
            size = 65
            image = Image.new("RGBA", (size, size))
            for y in range(size):
                for x in range(size):
                    edge_distance = min(x, y, size - 1 - x, size - 1 - y)
                    blue = 255 - round(95 * edge_distance / ((size - 1) / 2))
                    image.putpixel((x, y), (0, 0, blue, 255))
            image.save(source_path)
            worker = self.make_worker(
                root,
                remove_bg=True,
                remove_bg_provider="local_chroma_key",
                chroma_key_color="blue",
            )

            with self.assertRaisesRegex(ValueError, "неоднородный"):
                worker._run_processing_pipeline(
                    str(source_path), None, str(raw_dir), 1, "file"
                )

    def test_worker_normalizes_a_non_preset_legacy_chroma_color_to_blue(self):
        with tempfile.TemporaryDirectory(prefix="legacy-chroma-color-") as temp:
            worker = self.make_worker(
                temp,
                remove_bg=True,
                remove_bg_provider="local_chroma_key",
                chroma_key_color="#FF0000",
            )

            self.assertEqual(worker.chroma_key_color, "blue")

    def require_local_realesrgan(self):
        exe_path, error = main.validate_local_realesrgan_exe(str(REALESRGAN_DIR))
        if error:
            self.skipTest(error)
        return Path(exe_path)

    def create_fake_realesrgan_runtime(self, root):
        (root / main.REALESRGAN_EXE_NAME).write_bytes(b"fake")
        models = root / "models"
        models.mkdir()
        for name in ("realesr-animevideov3-x2", "realesrgan-x4plus-anime"):
            (models / f"{name}.bin").write_bytes(b"model")
            (models / f"{name}.param").write_bytes(b"params")

    def test_clipart_2x_uses_model_present_in_bundled_runtime(self):
        self.assertEqual(
            main.get_local_realesrgan_model_name("clipart", 2),
            "realesr-animevideov3-x2",
        )

    def test_bundled_realesrgan_uses_pyinstaller_resource_root(self):
        previous_meipass = getattr(main.sys, "_MEIPASS", None)
        had_meipass = hasattr(main.sys, "_MEIPASS")
        try:
            main.sys._MEIPASS = str(ROOT_DIR / "_internal")
            self.assertEqual(
                main.bundled_local_realesrgan_dir(),
                str(ROOT_DIR / "_internal" / "realesrgan-ncnn-vulkan-20211212-windows"),
            )
        finally:
            if had_meipass:
                main.sys._MEIPASS = previous_meipass
            else:
                delattr(main.sys, "_MEIPASS")

    def test_bundled_realesrgan_uses_macos_runtime_and_binary_name(self):
        previous_meipass = getattr(main.sys, "_MEIPASS", None)
        had_meipass = hasattr(main.sys, "_MEIPASS")
        try:
            main.sys._MEIPASS = str(ROOT_DIR / "_internal")
            with patch.object(main.sys, "platform", "darwin"):
                directory = main.bundled_local_realesrgan_dir()
                executable = main.resolve_local_realesrgan_exe_path(directory)
            self.assertEqual(
                directory,
                str(ROOT_DIR / "_internal" / "realesrgan-ncnn-vulkan-20220424-macos"),
            )
            self.assertEqual(Path(executable).name, "realesrgan-ncnn-vulkan")
        finally:
            if had_meipass:
                main.sys._MEIPASS = previous_meipass
            else:
                delattr(main.sys, "_MEIPASS")

    def assert_quadrant_layout(self, image):
        rgb = image.convert("RGB")
        width, height = rgb.size
        samples = {
            "red": rgb.getpixel((width // 4, height // 4)),
            "green": rgb.getpixel((3 * width // 4, height // 4)),
            "blue": rgb.getpixel((width // 4, 3 * height // 4)),
            "magenta": rgb.getpixel((3 * width // 4, 3 * height // 4)),
        }
        red = samples["red"]
        green = samples["green"]
        blue = samples["blue"]
        magenta = samples["magenta"]
        self.assertGreater(red[0], red[1] + 40)
        self.assertGreater(red[0], red[2] + 40)
        self.assertGreater(green[1], green[0] + 40)
        self.assertGreater(green[1], green[2] + 40)
        self.assertGreater(blue[2], blue[0] + 40)
        self.assertGreater(blue[2], blue[1] + 40)
        self.assertGreater(magenta[0], magenta[1] + 40)
        self.assertGreater(magenta[2], magenta[1] + 40)

    def test_local_realesrgan_2x_and_4x_preserve_alpha_and_layout(self):
        self.require_local_realesrgan()
        with tempfile.TemporaryDirectory(prefix="clipart-realesrgan-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "quadrants.png"
            source = create_quadrant_rgba(source_path)
            source_bbox = source.getchannel("A").getbbox()

            for scale in (2, 4):
                with self.subTest(scale=scale):
                    output_path = temp_path / f"quadrants_{scale}x.png"
                    worker = self.make_worker(temp_path, local_realesrgan_scale=scale)
                    worker._run_local_realesrgan(str(source_path), str(output_path))

                    with Image.open(output_path) as result:
                        self.assertEqual(result.size, (source.width * scale, source.height * scale))
                        self.assertEqual(result.mode, "RGBA")
                        self.assertEqual(result.getchannel("A").getextrema(), (0, 255))
                        self.assertEqual(
                            result.getchannel("A").getbbox(),
                            tuple(coordinate * scale for coordinate in source_bbox),
                        )
                        self.assert_quadrant_layout(result)

    def test_missing_local_realesrgan_path_is_actionable(self):
        with tempfile.TemporaryDirectory(prefix="clipart-missing-realesrgan-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            Image.new("RGB", (4, 4), "white").save(source_path)
            worker = self.make_worker(temp_dir, local_realesrgan_dir=str(Path(temp_dir) / "missing"))

            with self.assertRaisesRegex(ValueError, "Real-ESRGAN"):
                worker._run_local_realesrgan(str(source_path), str(Path(temp_dir) / "output.png"))

    def test_local_realesrgan_hides_windows_console_when_started(self):
        with tempfile.TemporaryDirectory(prefix="clipart-realesrgan-window-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path = root / "source.png"
            output_path = root / "output.png"
            Image.new("RGB", (4, 4), "white").save(source_path)
            worker = self.make_worker(root, local_realesrgan_dir=str(root))
            captured = {}

            class FakeProcess:
                returncode = 0

                def __init__(self, command, **kwargs):
                    captured.update(kwargs)
                    shutil.copyfile(
                        command[command.index("-i") + 1],
                        command[command.index("-o") + 1],
                    )

                def communicate(self, timeout=None):
                    return "", ""

                def poll(self):
                    return self.returncode

            with patch.object(main.subprocess, "Popen", FakeProcess):
                worker._run_local_realesrgan(str(source_path), str(output_path), scale=2)

            self.assertEqual(
                captured["creationflags"],
                getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

    def test_local_realesrgan_keeps_straight_rgb_under_soft_alpha(self):
        with tempfile.TemporaryDirectory(prefix="clipart-soft-alpha-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path = root / "source.png"
            output_path = root / "output.png"
            Image.new("RGBA", (2, 2), (220, 10, 20, 128)).save(source_path)
            worker = self.make_worker(root, local_realesrgan_dir=str(root))

            class FakeProcess:
                returncode = 0

                def __init__(self, command, **_kwargs):
                    with Image.open(command[command.index("-i") + 1]) as image:
                        image.resize((4, 4)).save(command[command.index("-o") + 1])

                def communicate(self, timeout=None):
                    return "", ""

                def poll(self):
                    return self.returncode

            with patch.object(main.subprocess, "Popen", FakeProcess):
                worker._run_local_realesrgan(str(source_path), str(output_path), scale=2)

            with Image.open(output_path) as result:
                red, green, blue, alpha = result.getpixel((1, 1))
            self.assertGreater(red, 200)
            self.assertLess(green, 40)
            self.assertLess(blue, 40)
            self.assertGreater(alpha, 0)

    def test_local_realesrgan_rejects_oversized_projected_output_before_launch(self):
        with tempfile.TemporaryDirectory(prefix="clipart-large-output-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path = root / "source.png"
            Image.new("RGB", (3000, 3000), "white").save(source_path)
            worker = self.make_worker(root, local_realesrgan_dir=str(root))

            with patch.object(main.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(ValueError, "result.*pixel limit"):
                    worker._run_local_realesrgan(
                        str(source_path), str(root / "output.png"), scale=4
                    )

            popen.assert_not_called()

    def test_local_rembg_failure_emits_exact_failed_stage(self):
        with tempfile.TemporaryDirectory(prefix="clipart-rembg-stage-") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.png"
            Image.new("RGB", (8, 8), "white").save(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                str(root),
                worker_settings(
                    remove_bg=True,
                    remove_bg_provider="local_rembg",
                ),
                selected_files=[str(source_path)],
            )
            messages = []
            worker.progress.connect(messages.append)
            worker._run_local_rembg = types.MethodType(
                lambda self, *_args: (_ for _ in ()).throw(RuntimeError("model failed")),
                worker,
            )

            worker._mode2_process_files(emit_final=False)

            self.assertIn(
                "  Этап обработки: background_removal; status=running",
                messages,
            )
            self.assertIn(
                "  Этап обработки: background_removal; status=failed",
                messages,
            )
            self.assertTrue(any("model failed" in message for message in messages))

    def test_local_realesrgan_timeout_terminates_child_process(self):
        with tempfile.TemporaryDirectory(prefix="clipart-realesrgan-timeout-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path = root / "source.png"
            Image.new("RGB", (8, 8), "white").save(source_path)
            worker = self.make_worker(root, local_realesrgan_dir=str(root))

            class HangingProcess:
                returncode = None
                terminated = False

                def __init__(self, *_args, **_kwargs):
                    pass

                def poll(self):
                    return self.returncode

                def terminate(self):
                    self.terminated = True
                    self.returncode = -15

                def kill(self):
                    self.returncode = -9

                def communicate(self, timeout=None):
                    return "", ""

            process = HangingProcess()
            with patch.object(main.subprocess, "Popen", return_value=process), patch.object(
                main, "LOCAL_REALESRGAN_TIMEOUT_SECONDS", 0
            ):
                with self.assertRaisesRegex(TimeoutError, "exceeded"):
                    worker._run_local_realesrgan(
                        str(source_path), str(root / "output.png"), scale=2
                    )

            self.assertTrue(process.terminated)

    def test_invisible_cleanup_only_is_dispatched_as_local_processing(self):
        with tempfile.TemporaryDirectory(prefix="clipart-invisible-only-") as temp_dir:
            root = Path(temp_dir)
            source_path = root / "source.png"
            Image.new("RGB", (8, 8), "white").save(source_path)
            with patch.object(main, "gpu_backend_available", return_value=True):
                worker = main.WorkerThread(
                    "mode2_process",
                    str(root),
                    worker_settings(invisible_watermark_cleanup_enabled=True),
                    selected_files=[str(source_path)],
                )

            def fake_cleanup(source, destination, **_kwargs):
                shutil.copyfile(source, destination)

            with patch.object(main, "clean_invisible_watermark", fake_cleanup):
                worker._mode2_process_files(emit_final=False)

            self.assertEqual(len(list((root / "output").glob("*.png"))), 1)

    def test_local_realesrgan_reports_missing_selected_photo_model_before_launch(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photo-model-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path = root / "source.png"
            Image.new("RGB", (8, 8), "white").save(source_path)
            worker = self.make_worker(
                root,
                local_realesrgan_dir=str(root),
                local_realesrgan_profile="photo",
            )

            with patch.object(main.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(ValueError, "realesrgan-x4plus"):
                    worker._run_local_realesrgan(
                        str(source_path), str(root / "output.png"), scale=4
                    )

            popen.assert_not_called()

    def test_dpi_failure_keeps_safe_underlying_cause_for_technical_log(self):
        worker = self.make_worker(Path.cwd())
        with patch.object(main.Image, "open", side_effect=OSError("disk is read-only")):
            with self.assertRaisesRegex(RuntimeError, "disk is read-only"):
                worker._set_png_dpi("result.png", dpi=300)

    def test_local_process_without_kie_uses_expected_pipeline_order(self):
        with tempfile.TemporaryDirectory(prefix="clipart-local-pipeline-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_quadrant_rgba(source_path, size=(20, 20))
            worker = main.WorkerThread(
                "mode2_process",
                str(temp_path),
                worker_settings(
                    upscale=True,
                    unsharp_enabled=True,
                    remove_bg=True,
                    skip_remover_for_alpha=False,
                    edge_shrink_enabled=True,
                    trim_enabled=True,
                ),
                selected_files=[str(source_path)],
            )
            order = []
            raw_dirs = []
            original_unsharp = main.WorkerThread._unsharp_mask_pipeline_step
            original_edge = main.WorkerThread._edge_shrink_pipeline_step
            original_trim = main.WorkerThread._trim_image_file

            def fake_upscale(self, input_path, raw_dir, idx, prefix, step_name):
                order.append("upscale")
                output_path = Path(raw_dir) / f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png"
                shutil.copyfile(input_path, output_path)
                return str(output_path)

            def tracked_unsharp(self, input_path, raw_dir, idx, prefix):
                order.append("unsharp")
                return original_unsharp(self, input_path, raw_dir, idx, prefix)

            def fake_ben2(self, input_path, output_path):
                order.append("remove_bg")
                with Image.open(input_path) as image:
                    rgba = image.convert("RGBA")
                    rgba.putalpha(rgba.getchannel("A").point(lambda value: 255 if value else 0))
                    rgba.save(output_path, format="PNG")
                return output_path

            def tracked_edge(self, input_path, raw_dir, idx, prefix):
                order.append("edge_shrink")
                return original_edge(self, input_path, raw_dir, idx, prefix)

            def tracked_trim(self, source_path, output_path, stage_label, trim_mode=None):
                order.append("trim")
                result = original_trim(self, source_path, output_path, stage_label, trim_mode=trim_mode)
                order.append("save")
                return result

            worker._local_realesrgan_pipeline_step = types.MethodType(fake_upscale, worker)
            worker._unsharp_mask_pipeline_step = types.MethodType(tracked_unsharp, worker)
            worker._run_local_ben2 = types.MethodType(fake_ben2, worker)
            worker._edge_shrink_pipeline_step = types.MethodType(tracked_edge, worker)
            worker._trim_image_file = types.MethodType(tracked_trim, worker)
            original_create_raw_dir = worker._create_run_raw_dir
            worker._create_run_raw_dir = lambda: (
                raw_dirs.append(original_create_raw_dir()) or raw_dirs[-1]
            )

            worker._mode2_process_files(emit_final=False)

            self.assertEqual(order, ["upscale", "unsharp", "remove_bg", "edge_shrink", "trim", "save"])
            outputs = list((temp_path / "output").glob("*.png"))
            rough_outputs = list((temp_path / "rough").glob("*.png"))
            self.assertEqual(len(outputs), 1)
            self.assertGreaterEqual(len(rough_outputs), 4)
            self.assertFalse(Path(raw_dirs[0]).exists())
            with Image.open(outputs[0]) as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertNotEqual(result.getchannel("A").getextrema(), (0, 0))

    def test_process_only_accepts_rgb_jpeg_without_kie(self):
        with tempfile.TemporaryDirectory(prefix="clipart-local-jpeg-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.jpg"
            image = Image.new("RGB", (18, 14), (225, 225, 225))
            ImageDraw.Draw(image).rectangle((4, 3, 13, 10), fill=(180, 60, 90))
            image.save(source_path, format="JPEG", quality=95)
            worker = main.WorkerThread(
                "mode2_process",
                str(temp_path),
                worker_settings(unsharp_enabled=True),
                selected_files=[str(source_path)],
            )

            worker._mode2_process_files(emit_final=False)

            outputs = list((temp_path / "output").glob("*.png"))
            self.assertEqual(len(outputs), 1)
            with Image.open(outputs[0]) as result:
                self.assertEqual(result.mode, "RGB")
                self.assertEqual(result.size, image.size)

    def test_unsharp_preserves_alpha_and_changes_rgb(self):
        with tempfile.TemporaryDirectory(prefix="clipart-unsharp-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            output_path = Path(temp_dir) / "output.png"
            image = Image.new("RGBA", (17, 17), (120, 120, 120, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle((5, 5, 11, 11), fill=(190, 70, 70, 255))
            image.save(source_path)
            worker = self.make_worker(temp_dir, unsharp_amount=180, unsharp_radius=2)

            worker._apply_unsharp_mask_file(str(source_path), str(output_path))

            with Image.open(output_path) as result:
                self.assertEqual(result.getchannel("A").getextrema(), (255, 255))
                self.assertNotEqual(result.convert("RGB").tobytes(), image.convert("RGB").tobytes())

    def test_background_edge_controls_are_deterministic(self):
        alpha = Image.new("L", (9, 9), 0)
        ImageDraw.Draw(alpha).rectangle((2, 2, 6, 6), fill=255)
        rgba = Image.new("RGBA", (9, 9), (90, 140, 200, 255))
        rgba.putalpha(alpha)

        hard_worker = self.make_worker(".", local_ben2_edge_softness=0)
        hard_result = hard_worker._apply_ben2_alpha_settings(rgba)
        self.assertLessEqual(set(hard_result.getchannel("A").tobytes()), {0, 255})

        soft_worker = self.make_worker(".", local_ben2_edge_softness=1)
        soft_result = soft_worker._apply_ben2_alpha_settings(rgba)
        self.assertTrue(any(0 < value < 255 for value in soft_result.getchannel("A").tobytes()))

        rembg_worker = self.make_worker(".", local_rembg_edge_quality="soft")
        rembg_result = rembg_worker._apply_local_rembg_edge_quality(rgba)
        self.assertEqual(rembg_result.convert("RGB").tobytes(), rgba.convert("RGB").tobytes())
        self.assertTrue(any(0 < value < 255 for value in rembg_result.getchannel("A").tobytes()))

    def test_edge_shrink_preserves_rgb_and_trim_removes_transparent_border(self):
        with tempfile.TemporaryDirectory(prefix="clipart-edge-trim-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            edge_path = temp_path / "edge.png"
            trim_path = temp_path / "trim.png"
            image = Image.new("RGBA", (11, 11), (40, 120, 220, 0))
            alpha = Image.new("L", image.size, 0)
            ImageDraw.Draw(alpha).rectangle((2, 2, 8, 8), fill=255)
            image.putalpha(alpha)
            image.save(source_path)
            worker = self.make_worker(temp_path, edge_shrink_pixels=1, trim_enabled=True)

            worker._shrink_alpha_edges(str(source_path), str(edge_path), 1)
            with Image.open(edge_path) as edged:
                self.assertEqual(edged.convert("RGB").tobytes(), image.convert("RGB").tobytes())
                self.assertEqual(edged.getchannel("A").getbbox(), (3, 3, 8, 8))

            worker._trim_image_file(str(edge_path), str(trim_path), "test", trim_mode="alpha")
            with Image.open(trim_path) as trimmed:
                self.assertEqual(trimmed.size, (5, 5))
                self.assertEqual(trimmed.getchannel("A").getextrema(), (255, 255))


if __name__ == "__main__":
    unittest.main()
