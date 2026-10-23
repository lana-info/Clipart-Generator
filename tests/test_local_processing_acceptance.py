import shutil
import subprocess
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageChops, ImageDraw

import main
from chroma_provenance import image_digest, load_receipt, receipt_path


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
    def test_auto_clipart_fallback_makes_binary_inset_mask(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            output = root / "cutout.png"
            Image.new("RGB", (32, 32), "white").save(source)
            segmented = Image.new("RGBA", (32, 32), (170, 90, 40, 0))
            ImageDraw.Draw(segmented).rectangle((4, 4, 27, 27), fill=(170, 90, 40, 255))
            buffer = BytesIO()
            segmented.save(buffer, format="PNG")
            remove = lambda *_args, **_kwargs: buffer.getvalue()
            worker = self.make_worker(root, auto_clipart_sharp_fallback=True)
            with patch.object(main, "import_rembg_tools", return_value=(lambda name: name, remove)):
                worker._run_auto_clipart_sharp_fallback(str(source), str(output))
            with Image.open(output) as image:
                alpha = image.getchannel("A")
                self.assertEqual(
                    {index for index, count in enumerate(alpha.histogram()) if count},
                    {0, 255},
                )
                self.assertEqual(alpha.getpixel((4, 16)), 0)
                self.assertEqual(alpha.getpixel((16, 16)), 255)

    def test_auto_clipart_uses_fallback_when_key_background_is_ambiguous(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source = root / "source.png"
            output = root / "source_ready.png"
            Image.new("RGB", (40, 40), "white").save(source)
            worker = self.make_worker(root, remove_bg=True,
                                      remove_bg_provider="local_chroma_key",
                                      auto_clipart_sharp_fallback=True)

            def cutout(_source, target):
                image = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
                ImageDraw.Draw(image).rectangle((8, 8, 31, 31), fill=(100, 50, 20, 255))
                image.save(target)

            with patch.object(main, "remove_chroma_key_automatic",
                              side_effect=main.ChromaKeyAmbiguousError("ambiguous key")), \
                 patch.object(worker, "_run_auto_clipart_sharp_fallback", side_effect=cutout):
                worker._process_file_entry(1, 1, str(source), str(raw), str(output))
            with Image.open(output) as image:
                self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
            self.assertFalse(worker._item_context.manual_transparency_required)

    def test_auto_clipart_keeps_manual_status_if_fallback_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source = root / "source.png"
            output = root / "source_ready.png"
            Image.new("RGB", (40, 40), "white").save(source)
            worker = self.make_worker(root, remove_bg=True,
                                      remove_bg_provider="local_chroma_key",
                                      auto_clipart_sharp_fallback=True)
            with patch.object(main, "remove_chroma_key_automatic",
                              side_effect=main.ChromaKeyAmbiguousError("ambiguous key")), \
                 patch.object(worker, "_run_auto_clipart_sharp_fallback",
                              side_effect=RuntimeError("model unavailable")):
                worker._process_file_entry(1, 1, str(source), str(raw), str(output))
            self.assertTrue(worker._item_context.manual_transparency_required)
            with Image.open(output) as image:
                self.assertEqual(image.convert("RGBA").getchannel("A").getextrema(), (255, 255))

    def test_generation_records_key_before_api_and_reprocessing_uses_it(self):
        from chroma_generation_record import load_generation_color, record_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            worker = self.make_worker(root, remove_bg=True,
                                      remove_bg_provider="local_chroma_key",
                                      chroma_key_color="blue")
            source = raw / f"gen_001_{worker.run_stamp}.png"
            def generate(prompt, references):
                self.assertTrue(record_path(source, pending=True).exists())
                self.assertFalse(source.exists())
                return "https://example.invalid/generated.png"
            def download(url, target):
                image = Image.new("RGB", (64, 64), (0, 255, 0))
                ImageDraw.Draw(image).rectangle((16, 16, 47, 47), fill=(130, 80, 170))
                image.save(target)
            with patch.object(worker, "_kie_generate_image", side_effect=generate), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output"):
                worker._generate_entry(1, 1, {"prompt": "flower", "chroma_key_color": "green"},
                                       str(raw), str(root / "output.png"), False)
            self.assertEqual(load_generation_color(source), "green")
            original = source.read_bytes()
            restarted = self.make_worker(root, remove_bg=True,
                                         remove_bg_provider="local_chroma_key",
                                         chroma_key_color="red")
            with patch.object(main, "remove_chroma_key_automatic", wraps=main.remove_chroma_key_automatic) as keyer:
                result = restarted._run_processing_pipeline(str(source), None, str(raw), 2, "file")
            self.assertEqual(keyer.call_args.args[1], "green")
            with Image.open(result) as image:
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                self.assertEqual(image.getpixel((32, 32))[3], 255)
            self.assertEqual(source.read_bytes(), original)
            with self.assertRaisesRegex(ValueError, "не совпадает"):
                restarted._run_processing_pipeline(str(source), None, str(raw), 3, "file", chroma_key_color="blue")

    def test_failed_generation_intent_write_never_submits_paid_request(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = self.make_worker(Path(temp))
            with patch("chroma_generation_record.write_generation_intent", side_effect=OSError("disk full")), \
                 patch.object(worker, "_kie_generate_image") as generate:
                with self.assertRaises(OSError):
                    worker._generate_entry(1, 1, {"prompt": "flower", "chroma_key_color": "red"},
                                           temp, str(Path(temp) / "output.png"), False)
                generate.assert_not_called()

    def test_generation_records_result_kind_before_api_and_binds_raw_and_final(self):
        from chroma_generation_record import (
            load_generation_color, load_generation_result_kind, record_path,
        )
        import json

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "pattern_ready.png"
            worker = self.make_worker(root, remove_bg=True, remove_bg_provider="local_chroma_key")
            source = raw / f"gen_001_{worker.run_stamp}.png"

            def generate(prompt, references):
                pending = json.loads(record_path(source, pending=True).read_text())
                self.assertEqual(pending["schema_version"], 2)
                self.assertEqual(pending["result_kind"], "pattern")
                self.assertEqual(pending["stage"], "raw")
                self.assertIsNone(pending["requested_color"])
                self.assertFalse(source.exists())
                return "https://example.invalid/generated.png"

            def download(url, target):
                Image.new("RGB", (32, 32), (30, 40, 50)).save(target)

            def save_final(result_url, source_path, output_path, *args, **kwargs):
                Image.open(source_path).save(output_path, format="PNG")

            with patch.object(worker, "_kie_generate_image", side_effect=generate), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output", side_effect=save_final):
                worker._generate_entry(
                    1, 1, {"prompt": "seamless pattern", "result_kind": "pattern"},
                    str(raw), str(output), False,
                )

            self.assertEqual(load_generation_result_kind(source), "pattern")
            self.assertEqual(load_generation_result_kind(output), "pattern")
            self.assertIsNone(load_generation_color(output))
            final_record = json.loads(record_path(output).read_text())
            self.assertEqual(final_record["stage"], "final")

    def test_imported_final_png_recovers_surface_result_kind_without_rekeying(self):
        from chroma_generation_record import bind_generation_record, write_generation_intent

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source = root / "moved-pattern.png"
            Image.new("RGB", (32, 32), (30, 40, 50)).save(source)
            intent = write_generation_intent(
                source, color=None, prompt="pattern", result_kind="pattern"
            )
            bind_generation_record(source, intent, stage="final")
            worker = self.make_worker(
                root, remove_bg=True, remove_bg_provider="local_chroma_key",
                chroma_key_color="red",
            )
            with patch.object(main, "remove_chroma_key_automatic",
                              side_effect=AssertionError("final surface must not be re-keyed")):
                result = worker._run_processing_pipeline(
                    str(source), None, str(raw), 1, "file"
                )
            self.assertIsNone(result)

    def test_generation_only_opaque_chroma_clipart_output_remains_raw_for_later_removal(self):
        from chroma_generation_record import load_generation_color, record_path
        import json

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(root)

            def download(url, target):
                Image.new("RGB", (32, 32), (0, 255, 0)).save(target)

            def save_final(result_url, source_path, output_path, *args, **kwargs):
                Image.open(source_path).save(output_path, format="PNG")

            with patch.object(worker, "_kie_generate_image", return_value="https://example.invalid/generated.png"), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output", side_effect=save_final):
                worker._generate_entry(
                    1, 1, {
                        "prompt": "flower", "result_kind": "clipart",
                        "chroma_key_color": "green",
                    }, str(raw), str(output), False,
                )

            data = json.loads(record_path(output).read_text())
            self.assertEqual(data["stage"], "raw")
            self.assertEqual(load_generation_color(output), "green")

    def test_generation_only_clipart_with_isolated_alpha_noise_remains_raw(self):
        from chroma_generation_record import record_path
        import json

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(root)

            def download(url, target):
                image = Image.new("RGBA", (64, 64), (0, 255, 0, 255))
                image.putpixel((0, 0), (0, 255, 0, 0))
                image.save(target)

            def save_final(result_url, source_path, output_path, *args, **kwargs):
                Image.open(source_path).save(output_path, format="PNG")

            with patch.object(worker, "_kie_generate_image", return_value="https://example.invalid/generated.png"), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output", side_effect=save_final):
                worker._generate_entry(
                    1, 1, {
                        "prompt": "flower", "result_kind": "clipart",
                        "chroma_key_color": "green",
                    }, str(raw), str(output), False,
                )

            data = json.loads(record_path(output).read_text())
            self.assertEqual(data["stage"], "raw")

    def test_generation_only_native_transparent_clipart_output_is_final(self):
        from chroma_generation_record import load_generation_color, record_path
        import json

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(root)

            def download(url, target):
                image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                ImageDraw.Draw(image).rectangle((8, 8, 23, 23), fill=(120, 80, 40, 255))
                image.save(target)

            def save_final(result_url, source_path, output_path, *args, **kwargs):
                Image.open(source_path).save(output_path, format="PNG")

            with patch.object(worker, "_kie_generate_image", return_value="https://example.invalid/generated.png"), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output", side_effect=save_final):
                worker._generate_entry(
                    1, 1, {"prompt": "flower", "result_kind": "clipart"},
                    str(raw), str(output), False,
                )

            data = json.loads(record_path(output).read_text())
            self.assertEqual(data["stage"], "final")
            self.assertIsNone(load_generation_color(output))

    def test_imported_final_clipart_png_is_not_chroma_keyed_again(self):
        from chroma_generation_record import bind_generation_record, write_generation_intent

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source = root / "finished-clipart.png"
            Image.new("RGBA", (32, 32), (120, 80, 40, 255)).save(source)
            intent = write_generation_intent(
                source, color="green", prompt="flower", result_kind="clipart"
            )
            bind_generation_record(source, intent, stage="final")
            worker = self.make_worker(
                root, remove_bg=True, remove_bg_provider="local_chroma_key",
                chroma_key_color="red",
            )
            with patch.object(
                main, "remove_chroma_key_automatic",
                side_effect=AssertionError("final clipart must not be re-keyed"),
            ):
                result = worker._run_processing_pipeline(
                    str(source), None, str(raw), 1, "file"
                )
            self.assertIsNone(result)

    def test_imported_png_result_kind_conflict_stops_instead_of_guessing(self):
        from chroma_generation_record import bind_generation_record, write_generation_intent

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source = root / "moved-pattern.png"
            Image.new("RGB", (32, 32), (30, 40, 50)).save(source)
            intent = write_generation_intent(
                source, color=None, prompt="pattern", result_kind="pattern"
            )
            bind_generation_record(source, intent, stage="final")
            worker = self.make_worker(root, remove_bg=True, remove_bg_provider="local_chroma_key")
            with self.assertRaisesRegex(ValueError, "назнач|тип результата"):
                worker._run_processing_pipeline(
                    str(source), None, str(raw), 1, "file", result_kind="clipart"
                )

    def test_final_sidecar_collision_blocks_before_paid_generation(self):
        from chroma_generation_record import record_path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            record_path(output).write_text("stale sidecar")
            worker = self.make_worker(root)
            with patch.object(worker, "_kie_generate_image") as generate:
                with self.assertRaises(FileExistsError):
                    worker._generate_entry(
                        1, 1, {"prompt": "flower", "result_kind": "clipart"},
                        str(raw), str(output), False,
                    )
            generate.assert_not_called()

    def test_final_sidecar_write_failure_does_not_turn_paid_generation_into_retryable_failure(self):
        import chroma_generation_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(root)
            original_bind = chroma_generation_record.bind_generation_record
            generated = []

            def generate(prompt, references):
                generated.append(prompt)
                return "https://example.invalid/generated.png"

            def download(url, target):
                Image.new("RGB", (24, 24), (10, 20, 30)).save(target)

            def save_final(result_url, source_path, output_path, *args, **kwargs):
                Image.open(source_path).save(output_path, format="PNG")

            def fail_final(path, intent, *, stage="raw"):
                if stage == "final":
                    raise OSError("disk full for sidecar")
                return original_bind(path, intent, stage=stage)

            with patch.object(worker, "_kie_generate_image", side_effect=generate), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output", side_effect=save_final), \
                 patch("chroma_generation_record.bind_generation_record", side_effect=fail_final):
                result = worker._generate_entry(
                    1, 1, {"prompt": "flower", "result_kind": "clipart"},
                    str(raw), str(output), False,
                )

            self.assertEqual(result, str(output))
            self.assertTrue(output.exists())
            self.assertEqual(generated, ["flower"])


    def test_final_v2_clipart_skips_kie_background_removal_in_legacy_pipeline(self):
        from chroma_generation_record import bind_generation_record, write_generation_intent

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source = root / "finished.png"
            Image.new("RGBA", (32, 32), (10, 20, 30, 0)).save(source)
            intent = write_generation_intent(
                source, color="green", prompt="flower", result_kind="clipart"
            )
            bind_generation_record(source, intent, stage="final")
            worker = self.make_worker(
                root, upscale=True, upscale_provider="kie", kie_api_key="dummy",
                remove_bg=True, remove_bg_provider="kie",
            )
            calls = []

            def model_task(model, image_url, extra_input=None):
                calls.append(model)
                return "https://example.invalid/result.png"

            def download(_url, target):
                Image.new("RGBA", (32, 32), (10, 20, 30, 0)).save(target)

            with patch.object(worker, "_kie_upload_file", return_value="https://example.invalid/source.png"), \
                 patch.object(worker, "_kie_run_model_task", side_effect=model_task), \
                 patch.object(worker, "_download_file", side_effect=download):
                worker._run_processing_pipeline(str(source), None, str(raw), 1, "file")

            self.assertIn(worker.kie_upscale_model, calls)
            self.assertNotIn(worker.kie_remove_bg_model, calls)

    def test_raw_sidecar_bind_failure_after_paid_generation_is_non_retryable(self):
        import chroma_generation_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(root)
            original_bind = chroma_generation_record.bind_generation_record
            calls = []

            def generate(prompt, references):
                calls.append(prompt)
                return "https://example.invalid/generated.png"

            def download(_url, target):
                Image.new("RGB", (24, 24), (10, 20, 30)).save(target)

            def save_final(_result_url, source_path, output_path, *args, **kwargs):
                Image.open(source_path).save(output_path, format="PNG")

            def fail_raw(path, intent, *, stage="raw"):
                if stage == "raw":
                    raise OSError("disk full for raw sidecar")
                return original_bind(path, intent, stage=stage)

            with patch.object(worker, "_kie_generate_image", side_effect=generate), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch.object(worker, "_save_final_output", side_effect=save_final), \
                 patch("chroma_generation_record.bind_generation_record", side_effect=fail_raw):
                result = worker._generate_entry(
                    1, 1, {"prompt": "flower", "result_kind": "clipart"},
                    str(raw), str(output), False,
                )

            self.assertEqual(result, str(output))
            self.assertEqual(calls, ["flower"])
            self.assertTrue(output.exists())


    def test_raw_sidecar_bind_failure_can_continue_current_processing_without_retry(self):
        import chroma_generation_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(
                root, remove_bg=True, remove_bg_provider="local_chroma_key",
                chroma_key_color="green",
            )
            original_bind = chroma_generation_record.bind_generation_record
            generated = []

            def generate(prompt, references):
                generated.append(prompt)
                return "https://example.invalid/generated.png"

            def download(_url, target):
                image = Image.new("RGB", (48, 48), (0, 255, 0))
                ImageDraw.Draw(image).rectangle((12, 12, 35, 35), fill=(120, 80, 180))
                image.save(target)

            def fail_raw(path, intent, *, stage="raw"):
                if stage == "raw":
                    raise OSError("raw sidecar unavailable")
                return original_bind(path, intent, stage=stage)

            with patch.object(worker, "_kie_generate_image", side_effect=generate), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch("chroma_generation_record.bind_generation_record", side_effect=fail_raw):
                result = worker._generate_entry(
                    1, 1, {
                        "prompt": "flower", "result_kind": "clipart",
                        "chroma_key_color": "green",
                    }, str(raw), str(output), True,
                )

            self.assertEqual(result, str(output))
            self.assertEqual(generated, ["flower"])
            self.assertTrue(output.exists())
            with Image.open(output) as final:
                self.assertEqual(final.convert("RGBA").getpixel((0, 0))[3], 0)


    def test_raw_bind_and_pending_cleanup_failure_still_uses_current_explicit_metadata(self):
        import chroma_generation_record

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            output = root / "clipart_ready.png"
            worker = self.make_worker(
                root, remove_bg=True, remove_bg_provider="local_chroma_key", chroma_key_color="green"
            )
            generated = []

            def generate(prompt, references):
                generated.append(prompt)
                return "https://example.invalid/generated.png"

            def download(_url, target):
                image = Image.new("RGB", (48, 48), (0, 255, 0))
                ImageDraw.Draw(image).rectangle((12, 12, 35, 35), fill=(120, 80, 180))
                image.save(target)

            with patch.object(worker, "_kie_generate_image", side_effect=generate), \
                 patch.object(worker, "_download_file", side_effect=download), \
                 patch("chroma_generation_record.bind_generation_record", side_effect=OSError("bind failed")), \
                 patch("chroma_generation_record.discard_generation_intent", side_effect=OSError("cannot unlink")):
                result = worker._generate_entry(
                    1, 1, {
                        "prompt": "flower", "result_kind": "clipart", "chroma_key_color": "green"
                    }, str(raw), str(output), True,
                )

            self.assertEqual(result, str(output))
            self.assertEqual(generated, ["flower"])
            with Image.open(output) as final:
                self.assertEqual(final.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_native_alpha_route_preserves_detail_without_chroma_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "rough"
            raw.mkdir()
            source_path = root / "native.png"
            source = Image.new("RGBA", (32, 32), (0, 0, 255, 0))
            ImageDraw.Draw(source).rectangle((8, 8, 23, 23), fill=(120, 70, 30, 255))
            source.putpixel((7, 12), (80, 60, 190, 1))
            source.putpixel((7, 13), (80, 60, 190, 128))
            source.save(source_path)
            original = source_path.read_bytes()
            worker = self.make_worker(root, remove_bg=True, remove_bg_provider="local_chroma_key")
            with patch.object(main, "remove_chroma_key_automatic", side_effect=AssertionError("unexpected keyer")):
                result_path = worker._run_processing_pipeline(str(source_path), None, str(raw), 1, "file")
            with Image.open(result_path) as result:
                # The model's own matte is cleaned (2026-10-21): the opaque subject keeps its
                # exact coverage and colour, an isolated faint pixel (haze) is dropped, and an
                # edge pixel next to the subject stays a real partial edge.
                self.assertEqual(result.crop((8, 8, 24, 24)).tobytes(), source.crop((8, 8, 24, 24)).tobytes())
                self.assertEqual(result.getpixel((7, 12)), (0, 0, 0, 0))
                self.assertTrue(120 <= result.getpixel((7, 13))[3] <= 140)
                self.assertEqual(result.getpixel((7, 13))[:3], source.getpixel((7, 13))[:3])
                self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))
            self.assertEqual(source_path.read_bytes(), original)

    def test_local_chroma_export_preserves_near_key_opaque_subject(self):
        for green in (36, 37):
            with self.subTest(green=green), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                raw = root / "rough"
                raw.mkdir()
                source_path = root / "source.png"
                source = Image.new("RGB", (96, 96), (2, green, 250))
                ImageDraw.Draw(source).rectangle((20, 20, 75, 75), fill=(120, 80, 180))
                ImageDraw.Draw(source).line((20, 20, 75, 20), fill=(61, 58, 215))
                source.save(source_path)
                original_bytes = source_path.read_bytes()
                worker = self.make_worker(root, remove_bg=True,
                                          remove_bg_provider="local_chroma_key")
                result_path = worker._run_processing_pipeline(
                    str(source_path), None, str(raw), 1, "file"
                )
                self.assertNotEqual(Path(result_path), source_path)
                self.assertEqual(source_path.read_bytes(), original_bytes)
                with Image.open(result_path) as result:
                    self.assertEqual(result.getpixel((48, 48)), (120, 80, 180, 255))
                    edge = result.getpixel((48, 20))
                    self.assertLessEqual(max(abs(a - b) for a, b in zip(edge[:3], (120, 80, 180))), 4)
                    self.assertAlmostEqual(edge[3], 128, delta=4)
                    self.assertEqual(result.getpixel((0, 0))[3], 0)
                final_path = root / "final.png"
                worker._save_final_output(result_path, str(source_path), str(final_path), str(raw), 1, "file")
                receipt = load_receipt(final_path)
                self.assertIsNotNone(receipt)
                self.assertEqual(receipt["source_sha256"], image_digest(source_path))
                self.assertEqual(receipt["observed_removal_background"], "#02%02XFA" % green)
                self.assertEqual(receipt["quality_status"], "not_evaluated")
                second_path = root / "no-processing.png"
                worker._save_final_output(None, str(source_path), str(second_path), str(raw), 2, "file")
                self.assertFalse(receipt_path(second_path).exists())

    def test_failed_chroma_receipt_does_not_lose_exported_png(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            Image.new("RGBA", (4, 4), (10, 20, 30, 255)).save(source)
            worker = self.make_worker(root)
            worker._item_context.chroma_receipt = {
                "pipeline_result": str(source), "source_sha256": image_digest(source),
                "requested_background": "#0000FF", "observed_background": "#0000FF",
            }
            messages = []
            worker.progress.connect(messages.append)
            final_path = root / "final.png"
            with patch.object(main, "write_receipt", side_effect=OSError("fixture failure")):
                worker._save_final_output(str(source), str(source), str(final_path), str(root), 1, "file")
            self.assertTrue(final_path.is_file())
            self.assertTrue(any("PNG сохранён" in message for message in messages))

    def test_unfinished_chroma_receipt_is_not_attached_to_next_export(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            Image.new("RGB", (4, 4), (10, 20, 30)).save(source)
            worker = self.make_worker(root)
            worker._item_context.chroma_receipt = {"source_sha256": image_digest(source)}
            output = root / "final.png"
            worker._save_final_output(None, str(source), str(output), str(root), 1, "file")
            self.assertFalse(receipt_path(output).exists())

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

    def test_local_chroma_pipeline_preserves_ambiguous_image_for_manual_correction(self):
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

            messages = []
            diagnostics = []
            worker.progress.connect(messages.append)
            worker.diagnostic.connect(diagnostics.append)

            result_path = worker._run_processing_pipeline(
                str(source_path), None, str(raw_dir), 1, "file"
            )

            self.assertEqual(Path(result_path), source_path)
            with Image.open(result_path) as preserved:
                self.assertIsNone(
                    ImageChops.difference(preserved.convert("RGBA"), image).getbbox()
                )
            self.assertTrue(
                any("ручн" in message.casefold() for message in messages)
            )
            stage_terminal = [
                event
                for event in diagnostics
                if event.get("event") == "stage_finished"
                and event.get("stage") == "background_removal"
            ]
            self.assertEqual(stage_terminal[-1]["outcome"], "skipped")
            self.assertEqual(
                stage_terminal[-1]["status"],
                "manual_transparency_required",
            )

    def test_ambiguous_local_chroma_bypasses_final_trim_and_preserves_ready_pixels(self):
        with tempfile.TemporaryDirectory(prefix="ambiguous-chroma-ready-") as temp:
            root = Path(temp)
            source_path = root / "source.png"
            raw_dir = root / "rough"
            output_path = root / "output" / "source_ready.png"
            raw_dir.mkdir()
            output_path.parent.mkdir()
            size = 40
            image = Image.new("RGBA", (size, size), (255, 255, 255, 255))
            ImageDraw.Draw(image).rectangle(
                (8, 8, 31, 31), fill=(0, 0, 210, 255)
            )
            image.save(source_path)
            worker = self.make_worker(
                root,
                remove_bg=True,
                remove_bg_provider="local_chroma_key",
                chroma_key_color="blue",
                trim_enabled=True,
            )

            with patch.object(
                main,
                "remove_chroma_key_automatic",
                side_effect=main.ChromaKeyAmbiguousError("ambiguous key"),
            ):
                result_path = worker._process_file_entry(
                    1,
                    1,
                    str(source_path),
                    str(raw_dir),
                    str(output_path),
                )

            self.assertEqual(Path(result_path), output_path)
            with Image.open(output_path) as ready:
                self.assertEqual(ready.size, image.size)
                self.assertIsNone(
                    ImageChops.difference(ready.convert("RGBA"), image).getbbox()
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

    def test_auto_chroma_detects_each_file_in_one_worker_and_preserves_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            worker = self.make_worker(root, remove_bg=True,
                                      remove_bg_provider="local_chroma_key",
                                      chroma_key_color="auto")
            for index, (color, rgb) in enumerate(main.KEY_COLORS.items(), 1):
                source = root / f"{color}.png"
                image = Image.new("RGB", (64, 64), rgb)
                ImageDraw.Draw(image).rectangle((20, 20, 44, 44), fill=(235, 230, 210))
                image.save(source)
                before = source.read_bytes()
                result = worker._run_processing_pipeline(str(source), None, str(raw), index, "file")
                with Image.open(result) as output:
                    self.assertEqual(output.getpixel((0, 0))[3], 0)
                    self.assertEqual(output.getpixel((32, 32)), (235, 230, 210, 255))
                self.assertEqual(source.read_bytes(), before)
                self.assertEqual(worker.chroma_key_color, "auto")
            # Auto inspects the actual background even if generation declared another key.
            declared = "blue" if color != "blue" else "green"
            with patch("chroma_generation_record.load_generation_color", return_value=declared), \
                 patch.object(main, "detect_chroma_key_color", wraps=main.detect_chroma_key_color) as detect:
                result = worker._run_processing_pipeline(str(source), None, str(raw), 9, "recorded")
            detect.assert_called_once()
            with Image.open(result) as output:
                self.assertEqual(output.getpixel((0, 0))[3], 0)
                self.assertEqual(output.getpixel((32, 32)), (235, 230, 210, 255))
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(worker._item_context.chroma_receipt["requested_background"],
                             "#%02X%02X%02X" % rgb)

    def test_auto_chroma_uncertain_background_does_not_call_neural_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            source = root / "white.png"
            Image.new("RGB", (64, 64), "white").save(source)
            worker = self.make_worker(root, remove_bg=True,
                                      remove_bg_provider="local_chroma_key",
                                      chroma_key_color="auto", auto_clipart_sharp_fallback=True)
            with patch.object(worker, "_run_auto_clipart_sharp_fallback") as fallback:
                result = worker._run_processing_pipeline(str(source), None, str(raw), 1, "file")
            fallback.assert_not_called()
            self.assertEqual(result, str(source))
            self.assertTrue(worker._item_context.manual_transparency_required)

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

    def test_local_realesrgan_hides_key_colour_only_in_transparent_input(self):
        with tempfile.TemporaryDirectory(prefix="clipart-alpha-safe-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path, output_path = root / "source.png", root / "output.png"
            source = Image.new("RGBA", (8, 8), (0, 15, 255, 0))
            source.putpixel((3, 3), (230, 190, 130, 255))
            source.putpixel((4, 3), (150, 100, 170, 128))
            source.save(source_path)
            original = source_path.read_bytes()
            worker = self.make_worker(root, local_realesrgan_dir=str(root))
            captured = {}

            class FakeProcess:
                returncode = 0

                def __init__(self, command, **_kwargs):
                    with Image.open(command[command.index("-i") + 1]) as image:
                        captured["input"] = image.copy()
                        image.resize((16, 16)).save(command[command.index("-o") + 1])

                def communicate(self, timeout=None):
                    return "", ""

                def poll(self):
                    return self.returncode

            with patch.object(main.subprocess, "Popen", FakeProcess):
                worker._run_local_realesrgan(str(source_path), str(output_path), scale=2)
            self.assertEqual(captured["input"].getpixel((0, 0)), (230, 190, 130))
            self.assertEqual(captured["input"].getpixel((3, 3)), (230, 190, 130))
            # A soft-alpha pixel within the rim of transparency takes the colour
            # of the nearest opaque pixel so edge junk is not upscaled into a halo.
            self.assertEqual(captured["input"].getpixel((4, 3)), (230, 190, 130))
            self.assertEqual(source_path.read_bytes(), original)

    def test_upscale_input_preparation_failure_cleans_temporary_directory(self):
        with tempfile.TemporaryDirectory(prefix="clipart-upscale-prep-fail-") as temp_dir:
            root = Path(temp_dir)
            self.create_fake_realesrgan_runtime(root)
            source_path = root / "source.png"
            Image.new("RGBA", (3, 3), (200, 110, 140, 128)).save(source_path)
            worker = self.make_worker(root, local_realesrgan_dir=str(root))
            prepared_dir = tempfile.TemporaryDirectory()
            prepared_name = prepared_dir.name
            with patch.object(main.tempfile, "TemporaryDirectory", return_value=prepared_dir), \
                    patch.object(worker, "_prepare_upscale_rgb", side_effect=ValueError("prep failed")), \
                    patch.object(main.subprocess, "Popen") as popen:
                with self.assertRaisesRegex(ValueError, "prep failed"):
                    worker._run_local_realesrgan(str(source_path), str(root / "out.png"), scale=2)
            self.assertFalse(Path(prepared_name).exists())
            popen.assert_not_called()

    def test_upscale_rgb_preserves_opaque_soft_and_empty_inputs(self):
        for alpha in (0, 128, 255):
            with self.subTest(alpha=alpha):
                image = Image.new("RGBA", (3, 3), (200, 110, 140, alpha))
                result = main.WorkerThread._prepare_upscale_rgb(image)
                self.assertEqual(result.tobytes(), image.convert("RGB").tobytes())
        image = Image.new("RGBA", (5, 5), (0, 15, 255, 0))
        image.putpixel((2, 2), (170, 120, 100, 30))
        result = main.WorkerThread._prepare_upscale_rgb(image)
        self.assertEqual(result.getpixel((0, 0)), (170, 120, 100))
        self.assertEqual(result.getpixel((2, 2)), (170, 120, 100))
        self.assertEqual(image.getpixel((0, 0)), (0, 15, 255, 0))

    def test_upscale_rgb_replaces_dark_junk_in_soft_alpha_rim(self):
        size = 64
        yy, xx = np.mgrid[:size, :size]
        radius = np.hypot(xx - size / 2, yy - size / 2)
        alpha = np.clip((28 - radius) / 3.0, 0.0, 1.0)
        cream = np.array((250, 225, 170), dtype=float)
        rgba = np.zeros((size, size, 4), dtype=np.uint8)
        rgba[..., :3] = np.where(alpha[..., None] >= 1.0, cream, cream * alpha[..., None])
        rgba[..., 3] = np.rint(alpha * 255).astype(np.uint8)
        image = Image.fromarray(rgba, mode="RGBA")
        self.assertTrue(((rgba[..., 3] > 0) & (rgba[..., 3] < 255)).any())

        def rim_darkening(rgb):
            upscaled = np.asarray(rgb.resize((size * 3, size * 3), Image.Resampling.LANCZOS), dtype=float)
            big_alpha = np.asarray(image.getchannel("A").resize((size * 3, size * 3), Image.Resampling.BILINEAR))
            opaque = big_alpha >= 128
            kernel = np.ones((3, 3), dtype=np.uint8)

            def erode(mask, iterations):
                return cv2.erode(mask.astype(np.uint8), kernel, iterations=iterations).astype(bool)

            edge = opaque & ~erode(opaque, 1)
            inner = erode(opaque, 4) & ~erode(opaque, 8)
            return upscaled[inner].mean() - upscaled[edge].mean()

        self.assertGreater(rim_darkening(image.convert("RGB")), 8)
        prepared = main.WorkerThread._prepare_upscale_rgb(image)
        self.assertLess(rim_darkening(prepared), 3)
        opaque = rgba[..., 3] == 255
        np.testing.assert_array_equal(np.asarray(prepared)[opaque], rgba[..., :3][opaque])

    def test_restored_hard_alpha_stays_binary(self):
        with tempfile.TemporaryDirectory(prefix="clipart-hard-alpha-") as temp_dir:
            root = Path(temp_dir)
            output_path = root / "output.png"
            Image.new("RGB", (18, 18), (200, 180, 140)).save(output_path)
            alpha = Image.new("L", (9, 9), 0)
            alpha.putpixel((4, 4), 255)
            self.make_worker(root)._restore_upscaled_alpha(str(output_path), alpha)
            with Image.open(output_path) as result:
                restored = result.getchannel("A")
                self.assertEqual(set(restored.getdata()), {0, 255})
                self.assertEqual(restored.tobytes(), alpha.resize(result.size, Image.Resampling.NEAREST).tobytes())

    def test_restored_soft_alpha_has_no_disconnected_resampling_rings(self):
        with tempfile.TemporaryDirectory(prefix="clipart-alpha-rings-") as temp_dir:
            root = Path(temp_dir)
            output_path = root / "output.png"
            Image.new("RGB", (36, 36), (200, 180, 140)).save(output_path)
            alpha = Image.new("L", (9, 9), 0)
            alpha.putpixel((4, 4), 128)
            worker = self.make_worker(root)
            worker._restore_upscaled_alpha(str(output_path), alpha)
            with Image.open(output_path) as result:
                restored = result.getchannel("A")
                expected = alpha.resize(result.size, Image.Resampling.BILINEAR)
                self.assertEqual(restored.tobytes(), expected.tobytes())
                self.assertGreater(restored.getpixel((17, 17)), 0)
                self.assertEqual(restored.getpixel((9, 17)), 0)
                self.assertEqual(result.getpixel((17, 17))[:3], (200, 180, 140))

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

    def test_unsharp_uses_premultiplied_rgb_for_transparent_edges(self):
        with tempfile.TemporaryDirectory(prefix="clipart-alpha-unsharp-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            output_path = Path(temp_dir) / "output.png"
            image = Image.new("RGBA", (9, 9), (255, 255, 255, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((2, 2, 6, 6), fill=(80, 140, 210, 128))
            draw.rectangle((3, 3, 5, 5), fill=(180, 70, 90, 255))
            original_alpha = image.getchannel("A").tobytes()
            image.save(source_path, format="PNG")
            worker = self.make_worker(
                temp_dir,
                unsharp_amount=180,
                unsharp_radius=2,
            )

            worker._apply_unsharp_mask_file(str(source_path), str(output_path))

            with Image.open(output_path) as result:
                rgba = result.convert("RGBA")
                self.assertEqual(rgba.getchannel("A").tobytes(), original_alpha)
                self.assertEqual(rgba.getpixel((0, 0)), (0, 0, 0, 0))
                self.assertNotEqual(
                    rgba.convert("RGB").tobytes(),
                    image.convert("RGB").tobytes(),
                )

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
