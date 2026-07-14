import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, PngImagePlugin

from metadata_inspector import SCHEMA_VERSION, inspect_image_metadata


SECRET_COMMENT = "private-comment-must-not-leak"
SECRET_PROMPT = "private-prompt-must-not-leak"
SECRET_XMP = "private-xmp-value-must-not-leak"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exif_with_thumbnail():
    software = b"FixtureTool\x00"
    thumbnail = b"\xff\xd8fixture-thumbnail\xff\xd9"
    ifd0_offset = 8
    software_offset = 26
    ifd1_offset = 38
    thumbnail_offset = 68
    tiff = bytearray()
    tiff.extend(b"II")
    tiff.extend(struct.pack("<H", 42))
    tiff.extend(struct.pack("<I", ifd0_offset))
    tiff.extend(struct.pack("<H", 1))
    tiff.extend(struct.pack("<HHI", 0x0131, 2, len(software)))
    tiff.extend(struct.pack("<I", software_offset))
    tiff.extend(struct.pack("<I", ifd1_offset))
    tiff.extend(software)
    while len(tiff) < ifd1_offset:
        tiff.append(0)
    tiff.extend(struct.pack("<H", 2))
    tiff.extend(struct.pack("<HHII", 0x0201, 4, 1, thumbnail_offset))
    tiff.extend(struct.pack("<HHII", 0x0202, 4, 1, len(thumbnail)))
    tiff.extend(struct.pack("<I", 0))
    while len(tiff) < thumbnail_offset:
        tiff.append(0)
    tiff.extend(thumbnail)
    return b"Exif\x00\x00" + bytes(tiff), len(thumbnail)


def jpeg_metadata_segments():
    iptc = b"\x1c\x02\x05" + struct.pack(">H", len(SECRET_PROMPT)) + SECRET_PROMPT.encode("utf-8")
    resource = b"8BIM" + struct.pack(">H", 0x0404) + b"\x00\x00" + struct.pack(">I", len(iptc)) + iptc
    if len(iptc) % 2:
        resource += b"\x00"
    photoshop = b"Photoshop 3.0\x00" + resource
    app13 = b"\xff\xed" + struct.pack(">H", len(photoshop) + 2) + photoshop
    comment = SECRET_COMMENT.encode("utf-8")
    com = b"\xff\xfe" + struct.pack(">H", len(comment) + 2) + comment
    return app13 + com


def create_png_fixture(path):
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Comment", SECRET_COMMENT)
    pnginfo.add_text("parameters", SECRET_PROMPT)
    pnginfo.add_itxt(
        "XML:com.adobe.xmp",
        f'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:Description ai:System="{SECRET_XMP}"/></x:xmpmeta>',
    )
    exif = Image.Exif()
    exif[305] = "FixtureSoftware"
    image = Image.new("RGBA", (12, 9), (30, 80, 120, 170))
    image.save(
        path,
        format="PNG",
        pnginfo=pnginfo,
        exif=exif,
        icc_profile=b"fixture-icc-profile",
        dpi=(300, 300),
    )


def create_jpeg_fixture(path):
    exif, thumbnail_size = exif_with_thumbnail()
    Image.new("RGB", (13, 10), (220, 180, 140)).save(
        path,
        format="JPEG",
        quality=95,
        exif=exif,
        icc_profile=b"fixture-jpeg-icc-profile",
        dpi=(300, 300),
    )
    original = Path(path).read_bytes()
    Path(path).write_bytes(original[:2] + jpeg_metadata_segments() + original[2:])
    return thumbnail_size


class MetadataInspectorTests(unittest.TestCase):
    def test_png_summary_is_read_only_serializable_and_value_safe(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-png-") as temp_dir:
            path = Path(temp_dir) / "fixture.png"
            create_png_fixture(path)
            before_hash = file_hash(path)
            before_stat = path.stat()

            result = inspect_image_metadata(path)

            after_stat = path.stat()
            self.assertEqual(result["schema_version"], SCHEMA_VERSION)
            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["supported"])
            self.assertEqual(result["format"], "PNG")
            self.assertEqual((result["width"], result["height"]), (12, 9))
            self.assertTrue(result["categories"]["exif"]["present"])
            self.assertTrue(result["categories"]["xmp"]["present"])
            self.assertTrue(result["categories"]["comments_text"]["present"])
            self.assertTrue(result["categories"]["icc_profile"]["present"])
            self.assertTrue(result["categories"]["dpi"]["present"])
            self.assertIn("prompt", result["categories"]["generator_fields"]["fields"])
            self.assertIn("software", result["categories"]["generator_fields"]["fields"])

            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn(SECRET_COMMENT, serialized)
            self.assertNotIn(SECRET_PROMPT, serialized)
            self.assertNotIn(SECRET_XMP, serialized)
            self.assertEqual(file_hash(path), before_hash)
            self.assertEqual(path.stat().st_size, before_stat.st_size)
            self.assertEqual(after_stat.st_mtime_ns, before_stat.st_mtime_ns)

    def test_jpeg_reports_iptc_comment_thumbnail_icc_and_dpi(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-jpeg-") as temp_dir:
            path = Path(temp_dir) / "fixture.jpg"
            thumbnail_size = create_jpeg_fixture(path)
            before_hash = file_hash(path)
            before_stat = path.stat()

            result = inspect_image_metadata(path)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["format"], "JPEG")
            self.assertTrue(result["categories"]["exif"]["present"])
            self.assertTrue(result["categories"]["iptc"]["present"])
            self.assertTrue(result["categories"]["comments_text"]["present"])
            self.assertEqual(result["categories"]["embedded_thumbnail"]["size_bytes"], thumbnail_size)
            self.assertTrue(result["categories"]["icc_profile"]["present"])
            self.assertTrue(result["categories"]["dpi"]["present"])
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn(SECRET_COMMENT, serialized)
            self.assertNotIn(SECRET_PROMPT, serialized)
            self.assertEqual(file_hash(path), before_hash)
            self.assertEqual(path.stat().st_size, before_stat.st_size)
            self.assertEqual(path.stat().st_mtime_ns, before_stat.st_mtime_ns)

    def test_format_is_detected_from_content_not_extension(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-content-") as temp_dir:
            path = Path(temp_dir) / "actually-jpeg.png"
            Image.new("RGB", (7, 5), "white").save(path, format="JPEG")

            result = inspect_image_metadata(path)

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["format"], "JPEG")

    def test_animated_png_and_unsupported_or_invalid_files_are_clear(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-unsupported-") as temp_dir:
            temp_path = Path(temp_dir)
            animated_path = temp_path / "animated.png"
            first = Image.new("RGBA", (5, 5), "red")
            second = Image.new("RGBA", (5, 5), "blue")
            first.save(animated_path, format="PNG", save_all=True, append_images=[second], duration=100)

            gif_path = temp_path / "unsupported.png"
            Image.new("RGB", (5, 5), "green").save(gif_path, format="GIF")
            invalid_path = temp_path / "invalid.png"
            invalid_path.write_bytes(b"not an image")

            animated = inspect_image_metadata(animated_path)
            unsupported = inspect_image_metadata(gif_path)
            invalid = inspect_image_metadata(invalid_path)

            self.assertEqual(animated["status"], "unsupported")
            self.assertEqual(animated["reason"], "animated_not_supported")
            self.assertEqual(unsupported["status"], "unsupported")
            self.assertEqual(unsupported["format"], "GIF")
            self.assertEqual(unsupported["reason"], "unsupported_format")
            self.assertEqual(invalid["status"], "invalid")
            self.assertEqual(invalid["reason"], "unreadable_or_invalid_image")
            for result in (animated, unsupported, invalid):
                self.assertFalse(result["supported"])
                self.assertTrue(all(not category["present"] for category in result["categories"].values()))

    def test_decompression_bomb_is_a_structured_invalid_result(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-bomb-") as temp_dir:
            path = Path(temp_dir) / "large-for-test.png"
            Image.new("RGB", (20, 20), "white").save(path)

            with patch.object(Image, "MAX_IMAGE_PIXELS", 10):
                result = inspect_image_metadata(path)

            self.assertEqual(result["status"], "invalid")
            self.assertEqual(result["reason"], "unreadable_or_invalid_image")
            self.assertFalse(result["supported"])


if __name__ == "__main__":
    unittest.main()
