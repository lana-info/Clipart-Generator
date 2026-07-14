import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import main
from metadata_cleanup import cleanup_image_metadata
from metadata_inspector import inspect_image_metadata
from tests.test_c2pa_inspector import add_png_chunk_after_ihdr, c2pa_jumbf
from tests.test_metadata_cleanup import (
    SECRET_COMMENT,
    SECRET_PARAMETERS,
    create_png_fixture,
)
from tests.test_metadata_inspector import create_jpeg_fixture


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pixel_signature(path):
    with Image.open(path) as image:
        image.load()
        alpha = image.convert("RGBA").getchannel("A").tobytes()
        return image.size, image.convert("RGBA").tobytes(), alpha


def cleanup_settings(**overrides):
    settings = {
        "upscale": False,
        "upscale_after": False,
        "unsharp_enabled": False,
        "remove_bg": False,
        "trim_enabled": False,
        "edge_shrink_enabled": False,
        "cleanup_remove_exif": False,
        "cleanup_remove_xmp": False,
        "cleanup_remove_iptc": False,
        "cleanup_remove_comments_text": False,
        "cleanup_remove_embedded_thumbnail": False,
        "cleanup_remove_generator_fields": False,
        "cleanup_remove_embedded_c2pa": False,
        "cleanup_preserve_icc": True,
        "cleanup_preserve_dpi": True,
    }
    settings.update(overrides)
    return settings


class MetadataCleanupAcceptanceTests(unittest.TestCase):
    def test_each_cleanup_checkbox_is_independently_effective(self):
        cases = (
            ("exif", "cleanup_remove_exif", "exif", "exif"),
            ("xmp", "cleanup_remove_xmp", "xmp", "xmp"),
            ("iptc", "cleanup_remove_iptc", "iptc", "iptc"),
            (
                "comments",
                "cleanup_remove_comments_text",
                "comments_text",
                "comments_text",
            ),
            (
                "thumbnail",
                "cleanup_remove_embedded_thumbnail",
                "embedded_thumbnail",
                "embedded_thumbnail",
            ),
            (
                "generator",
                "cleanup_remove_generator_fields",
                "generator_fields",
                "generator_fields",
            ),
            (
                "c2pa",
                "cleanup_remove_embedded_c2pa",
                "embedded_c2pa",
                None,
            ),
        )

        for name, setting_key, action_key, category_key in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory(
                prefix=f"clipart-cleanup-acceptance-{name}-"
            ) as temp_dir:
                temp_path = Path(temp_dir)
                source_path = temp_path / ("source.jpg" if name == "iptc" else "source.png")
                output_path = temp_path / "output.png"
                if name == "iptc":
                    create_jpeg_fixture(source_path)
                else:
                    create_png_fixture(source_path)
                if name == "c2pa":
                    add_png_chunk_after_ihdr(source_path, b"caBX", c2pa_jumbf())

                source_hash = file_hash(source_path)
                source_pixels = pixel_signature(source_path)
                worker = main.WorkerThread(
                    "mode2_process",
                    temp_dir,
                    cleanup_settings(**{setting_key: True}),
                )
                result = worker._publish_final_output(str(source_path), str(output_path))

                self.assertEqual(result["actions"][action_key], "removed")
                self.assertEqual(pixel_signature(output_path), source_pixels)
                self.assertEqual(file_hash(source_path), source_hash)
                inspection = inspect_image_metadata(output_path)
                if category_key is not None:
                    self.assertFalse(inspection["categories"][category_key]["present"])
                else:
                    self.assertEqual(inspection["c2pa"]["presence"], "not_present")
                self.assertTrue(inspection["categories"]["icc_profile"]["present"])
                self.assertTrue(inspection["categories"]["dpi"]["present"])

                if name == "thumbnail":
                    self.assertTrue(inspection["categories"]["exif"]["present"])
                if name == "generator":
                    self.assertTrue(inspection["categories"]["xmp"]["present"])
                    self.assertTrue(inspection["categories"]["comments_text"]["present"])

    def test_combined_local_pipeline_cleans_once_without_changing_final_stage_pixels(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cleanup-acceptance-combined-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_png_fixture(source_path)
            add_png_chunk_after_ihdr(source_path, b"caBX", c2pa_jumbf())
            source_hash = file_hash(source_path)
            captured = []

            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                cleanup_settings(
                    unsharp_enabled=True,
                    edge_shrink_enabled=True,
                    edge_shrink_pixels=1,
                    trim_enabled=True,
                    cleanup_remove_exif=True,
                    cleanup_remove_xmp=True,
                    cleanup_remove_iptc=True,
                    cleanup_remove_comments_text=True,
                    cleanup_remove_embedded_thumbnail=True,
                    cleanup_remove_generator_fields=True,
                    cleanup_remove_embedded_c2pa=True,
                ),
                selected_files=[str(source_path)],
            )
            progress = []
            worker.progress.connect(progress.append)

            def tracked_cleanup(stage_path, output_path, options):
                before = pixel_signature(stage_path)
                result = cleanup_image_metadata(stage_path, output_path, options)
                captured.append((before, pixel_signature(output_path), options, result))
                return result

            with patch.object(main, "cleanup_image_metadata", side_effect=tracked_cleanup):
                worker._mode2_process_files(emit_final=False)

            self.assertEqual(len(captured), 1)
            before_pixels, after_pixels, options, result = captured[0]
            self.assertEqual(after_pixels, before_pixels)
            self.assertTrue(options.remove_exif)
            self.assertTrue(options.remove_xmp)
            self.assertTrue(options.remove_iptc)
            self.assertTrue(options.remove_comments_text)
            self.assertTrue(options.remove_embedded_thumbnail)
            self.assertTrue(options.remove_generator_fields)
            self.assertTrue(options.remove_embedded_c2pa)
            self.assertEqual(result["status"], "ok")

            output_path = next((temp_path / "output").glob("*.png"))
            inspection = inspect_image_metadata(output_path)
            for category in (
                "exif",
                "xmp",
                "iptc",
                "comments_text",
                "embedded_thumbnail",
                "generator_fields",
            ):
                self.assertFalse(inspection["categories"][category]["present"], category)
            self.assertEqual(inspection["c2pa"]["presence"], "not_present")
            self.assertTrue(inspection["categories"]["icc_profile"]["present"])
            self.assertTrue(inspection["categories"]["dpi"]["present"])
            self.assertEqual(file_hash(source_path), source_hash)
            joined_log = "\n".join(progress)
            self.assertNotIn(SECRET_COMMENT, joined_log)
            self.assertNotIn(SECRET_PARAMETERS, joined_log)


if __name__ == "__main__":
    unittest.main()
