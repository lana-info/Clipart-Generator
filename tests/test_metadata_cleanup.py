import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from PIL import Image, PngImagePlugin

from metadata_cleanup import (
    MetadataCleanupError,
    MetadataCleanupOptions,
    _filter_xmp_generator_fields,
    _pixel_fingerprint,
    cleanup_image_metadata,
)
from metadata_inspector import _exif_thumbnail_size, inspect_image_metadata
from tests.test_c2pa_inspector import add_png_chunk_after_ihdr, c2pa_jumbf
from tests.test_metadata_inspector import create_jpeg_fixture


SECRET_COMMENT = "comment-must-be-preserved-unless-selected"
SECRET_PARAMETERS = "generator-parameters-must-be-removed"
CUSTOM_TEXT = "custom-text-must-be-preserved"
LOCALIZED_TEXT = "localized-text-must-be-preserved"
XMP_NAMESPACE = "http://ns.adobe.com/xap/1.0/"
IPTC_NAMESPACE = "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
CUSTOM_NAMESPACE = "https://example.invalid/custom/"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exif_with_thumbnail_and_artist():
    software = b"FixtureSoftware\x00"
    artist = b"Keep Artist\x00"
    thumbnail = b"\xff\xd8fixture-thumbnail\xff\xd9"
    ifd0_offset = 8
    software_offset = 38
    artist_offset = software_offset + len(software)
    ifd1_offset = artist_offset + len(artist)
    thumbnail_offset = ifd1_offset + 30

    tiff = bytearray(b"II" + struct.pack("<H", 42) + struct.pack("<I", ifd0_offset))
    tiff.extend(struct.pack("<H", 2))
    tiff.extend(struct.pack("<HHII", 0x0131, 2, len(software), software_offset))
    tiff.extend(struct.pack("<HHII", 0x013B, 2, len(artist), artist_offset))
    tiff.extend(struct.pack("<I", ifd1_offset))
    tiff.extend(software)
    tiff.extend(artist)
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


def xmp_fixture():
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/"
        xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:xmp="{XMP_NAMESPACE}"
        xmlns:iptc="{IPTC_NAMESPACE}"
        xmlns:custom="{CUSTOM_NAMESPACE}">
      <rdf:RDF>
        <rdf:Description xmp:CreatorTool="FixtureGenerator"
            iptc:DigitalSourceType="trainedAlgorithmicMedia"
            custom:Keep="keep-xmp-value" />
      </rdf:RDF>
    </x:xmpmeta>"""


def create_png_fixture(path):
    exif, thumbnail_size = exif_with_thumbnail_and_artist()
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text("Comment", SECRET_COMMENT)
    pnginfo.add_text("parameters", SECRET_PARAMETERS)
    pnginfo.add_text("signature", "known-generator-signature")
    pnginfo.add_text("Model Release", "ordinary-field-with-model-substring")
    pnginfo.add_text("CustomField", CUSTOM_TEXT)
    pnginfo.add_itxt("Localized", LOCALIZED_TEXT, lang="fr", tkey="Texte localise")
    pnginfo.add_itxt("XML:com.adobe.xmp", xmp_fixture())
    Image.new("RGBA", (14, 11), (25, 75, 125, 170)).save(
        path,
        format="PNG",
        pnginfo=pnginfo,
        exif=exif,
        icc_profile=b"fixture-icc-profile",
        dpi=(300, 300),
    )
    return thumbnail_size


def image_pixels(path):
    with Image.open(path) as image:
        image.load()
        return image.mode, image.size, image.tobytes()


def output_xmp_attributes(image):
    payload = image.text["XML:com.adobe.xmp"].encode("utf-8")
    root = ElementTree.fromstring(payload)
    description = next(element for element in root.iter() if element.tag.endswith("Description"))
    return description.attrib


class MetadataCleanupTests(unittest.TestCase):
    def test_generator_cleanup_preserves_pixels_thumbnail_unchecked_metadata_icc_and_dpi(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-generator-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            thumbnail_size = create_png_fixture(source)
            source_hash = file_hash(source)
            source_stat = source.stat()
            source_pixels = image_pixels(source)

            result = cleanup_image_metadata(
                source,
                output,
                MetadataCleanupOptions(remove_generator_fields=True),
            )

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["actions"]["generator_fields"], "removed")
            self.assertEqual(result["actions"]["embedded_thumbnail"], "preserved")
            self.assertEqual(result["actions"]["icc_profile"], "preserved")
            self.assertEqual(result["actions"]["dpi"], "preserved")
            self.assertEqual(image_pixels(output), source_pixels)
            with Image.open(output) as image:
                image.load()
                exif = image.getexif()
                self.assertNotIn(305, exif)
                self.assertEqual(exif[315], "Keep Artist")
                self.assertEqual(_exif_thumbnail_size(image.info["exif"]), thumbnail_size)
                self.assertEqual(image.text["Comment"], SECRET_COMMENT)
                self.assertEqual(image.text["CustomField"], CUSTOM_TEXT)
                self.assertNotIn("parameters", image.text)
                self.assertNotIn("signature", image.text)
                self.assertEqual(image.text["Model Release"], "ordinary-field-with-model-substring")
                self.assertEqual(image.text["Localized"], LOCALIZED_TEXT)
                self.assertEqual(image.text["Localized"].lang, "fr")
                self.assertEqual(image.text["Localized"].tkey, "Texte localise")
                attributes = output_xmp_attributes(image)
                self.assertNotIn(f"{{{XMP_NAMESPACE}}}CreatorTool", attributes)
                self.assertNotIn(f"{{{IPTC_NAMESPACE}}}DigitalSourceType", attributes)
                self.assertEqual(attributes[f"{{{CUSTOM_NAMESPACE}}}Keep"], "keep-xmp-value")
                self.assertEqual(image.info["icc_profile"], b"fixture-icc-profile")
                self.assertAlmostEqual(image.info["dpi"][0], 300, delta=0.05)
            self.assertEqual(file_hash(source), source_hash)
            self.assertEqual(source.stat().st_size, source_stat.st_size)
            self.assertEqual(source.stat().st_mtime_ns, source_stat.st_mtime_ns)

    def test_exif_xmp_comments_and_thumbnail_are_independently_selectable(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-categories-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            create_png_fixture(source)
            cases = (
                ("exif", MetadataCleanupOptions(remove_exif=True), "exif"),
                ("xmp", MetadataCleanupOptions(remove_xmp=True), "xmp"),
                ("comments", MetadataCleanupOptions(remove_comments_text=True), "comments_text"),
                ("thumbnail", MetadataCleanupOptions(remove_embedded_thumbnail=True), "embedded_thumbnail"),
            )

            for name, options, selected_category in cases:
                with self.subTest(name=name):
                    output = temp_path / f"{name}.png"
                    result = cleanup_image_metadata(source, output, options)
                    inspected = inspect_image_metadata(output)
                    self.assertEqual(result["actions"][selected_category], "removed")
                    self.assertFalse(inspected["categories"][selected_category]["present"])
                    if selected_category != "exif":
                        self.assertTrue(inspected["categories"]["exif"]["present"])
                    if selected_category != "xmp":
                        self.assertTrue(inspected["categories"]["xmp"]["present"])
                    if selected_category != "comments_text":
                        self.assertTrue(inspected["categories"]["comments_text"]["present"])
                    if selected_category != "embedded_thumbnail" and selected_category != "exif":
                        self.assertTrue(inspected["categories"]["embedded_thumbnail"]["present"])

    def test_icc_and_dpi_preservation_are_independent(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-export-data-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            create_png_fixture(source)

            without_icc = temp_path / "without-icc.png"
            result_icc = cleanup_image_metadata(
                source,
                without_icc,
                MetadataCleanupOptions(preserve_icc=False, preserve_dpi=True),
            )
            inspected_icc = inspect_image_metadata(without_icc)
            self.assertEqual(result_icc["actions"]["icc_profile"], "removed")
            self.assertFalse(inspected_icc["categories"]["icc_profile"]["present"])
            self.assertTrue(inspected_icc["categories"]["dpi"]["present"])

            without_dpi = temp_path / "without-dpi.png"
            result_dpi = cleanup_image_metadata(
                source,
                without_dpi,
                MetadataCleanupOptions(preserve_icc=True, preserve_dpi=False),
            )
            inspected_dpi = inspect_image_metadata(without_dpi)
            self.assertEqual(result_dpi["actions"]["dpi"], "removed")
            self.assertTrue(inspected_dpi["categories"]["icc_profile"]["present"])
            self.assertFalse(inspected_dpi["categories"]["dpi"]["present"])

    def test_jpeg_iptc_limit_is_explicit_for_png_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-iptc-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.jpg"
            create_jpeg_fixture(source)
            source_hash = file_hash(source)

            preserved_request = cleanup_image_metadata(source, temp_path / "default.png")
            removed_request = cleanup_image_metadata(
                source,
                temp_path / "remove-iptc.png",
                MetadataCleanupOptions(remove_iptc=True),
            )

            self.assertEqual(preserved_request["actions"]["iptc"], "not_preserved_output_unsupported")
            self.assertEqual(removed_request["actions"]["iptc"], "removed")
            self.assertFalse(inspect_image_metadata(temp_path / "default.png")["categories"]["iptc"]["present"])
            self.assertFalse(inspect_image_metadata(temp_path / "remove-iptc.png")["categories"]["iptc"]["present"])
            self.assertEqual(file_hash(source), source_hash)

    def test_palette_transparency_is_part_of_the_pixel_invariant(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-palette-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "palette.png"
            output = temp_path / "output.png"
            image = Image.new("P", (4, 2))
            palette = [255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 9)
            image.putpalette(palette)
            image.putdata([0, 1, 2, 0, 2, 1, 0, 2])
            transparency = bytes([0, 128, 255] + [255] * 253)
            image.save(source, transparency=transparency)
            with Image.open(source) as before:
                before.load()
                before_rgba = before.convert("RGBA").tobytes()

            cleanup_image_metadata(source, output)

            with Image.open(output) as after:
                after.load()
                self.assertEqual(after.mode, "P")
                self.assertEqual(after.info["transparency"], transparency)
                self.assertEqual(after.convert("RGBA").tobytes(), before_rgba)

    def test_rgb_transparency_changes_the_pixel_fingerprint(self):
        first = Image.new("RGB", (2, 2), (10, 20, 30))
        second = first.copy()
        first.info["transparency"] = (10, 20, 30)
        second.info["transparency"] = (11, 20, 30)
        try:
            self.assertNotEqual(_pixel_fingerprint(first), _pixel_fingerprint(second))
        finally:
            first.close()
            second.close()

    def test_utf16_xmp_is_filtered_and_utf16_dtd_is_rejected(self):
        payload = (
            '<?xml version="1.0" encoding="UTF-16"?>'
            f'<root xmlns:xmp="{XMP_NAMESPACE}" xmp:CreatorTool="remove-me" keep="yes" />'
        ).encode("utf-16-le")
        filtered, removed = _filter_xmp_generator_fields(payload)
        root = ElementTree.fromstring(filtered)
        self.assertEqual(removed, 1)
        self.assertEqual(root.attrib, {"keep": "yes"})

        hostile = '<!DOCTYPE root [<!ENTITY x "x">]><root>&x;</root>'.encode("utf-16-le")
        with self.assertRaisesRegex(MetadataCleanupError, "unsupported declarations"):
            _filter_xmp_generator_fields(hostile)

    def test_c2pa_input_is_rejected_until_explicit_cleanup_is_selected(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-c2pa-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            create_png_fixture(source)
            add_png_chunk_after_ihdr(source, b"caBX", c2pa_jumbf())
            source_hash = file_hash(source)

            with self.assertRaisesRegex(MetadataCleanupError, "explicit C2PA cleanup"):
                cleanup_image_metadata(source, output)

            self.assertEqual(file_hash(source), source_hash)
            self.assertFalse(output.exists())

    def test_overlapping_exif_thumbnail_is_rejected_without_publishing(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-exif-overlap-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            exif, _ = exif_with_thumbnail_and_artist()
            damaged = bytearray(exif)
            tiff_start = 6
            ifd0_offset = struct.unpack_from("<I", damaged, tiff_start + 4)[0]
            ifd0_count = struct.unpack_from("<H", damaged, tiff_start + ifd0_offset)[0]
            next_pointer = tiff_start + ifd0_offset + 2 + ifd0_count * 12
            ifd1_offset = struct.unpack_from("<I", damaged, next_pointer)[0]
            thumbnail_entry_value = tiff_start + ifd1_offset + 2 + 8
            artist_offset = struct.unpack_from("<I", damaged, tiff_start + ifd0_offset + 2 + 12 + 8)[0]
            struct.pack_into("<I", damaged, thumbnail_entry_value, artist_offset)
            Image.new("RGBA", (4, 4), (20, 30, 40, 128)).save(source, exif=bytes(damaged))
            output.write_bytes(b"existing-output")

            with self.assertRaisesRegex(MetadataCleanupError, "overlaps"):
                cleanup_image_metadata(
                    source,
                    output,
                    MetadataCleanupOptions(remove_embedded_thumbnail=True),
                )

            self.assertEqual(output.read_bytes(), b"existing-output")

    def test_generator_exif_cannot_corrupt_a_preserved_thumbnail(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-generator-overlap-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            exif, _ = exif_with_thumbnail_and_artist()
            damaged = bytearray(exif)
            tiff_start = 6
            ifd0_offset = struct.unpack_from("<I", damaged, tiff_start + 4)[0]
            ifd0_count = struct.unpack_from("<H", damaged, tiff_start + ifd0_offset)[0]
            next_pointer = tiff_start + ifd0_offset + 2 + ifd0_count * 12
            ifd1_offset = struct.unpack_from("<I", damaged, next_pointer)[0]
            thumbnail_offset = struct.unpack_from("<I", damaged, tiff_start + ifd1_offset + 2 + 8)[0]
            software_value_offset = tiff_start + ifd0_offset + 2 + 8
            struct.pack_into("<I", damaged, software_value_offset, thumbnail_offset)
            Image.new("RGBA", (4, 4), (20, 30, 40, 128)).save(source, exif=bytes(damaged))
            output.write_bytes(b"existing-output")

            with self.assertRaisesRegex(MetadataCleanupError, "overlaps the embedded thumbnail"):
                cleanup_image_metadata(
                    source,
                    output,
                    MetadataCleanupOptions(remove_generator_fields=True),
                )

            self.assertEqual(output.read_bytes(), b"existing-output")

    def test_exif_camera_model_and_similar_text_are_not_guessed_as_generator_fields(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-exact-policy-") as temp_dir:
            source = Path(temp_dir) / "source.png"
            exif = Image.Exif()
            exif[272] = "Ordinary Camera Model"
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("Model Release", "keep")
            Image.new("RGB", (2, 2), "white").save(source, exif=exif, pnginfo=pnginfo)

            inspected = inspect_image_metadata(source)

            self.assertFalse(inspected["categories"]["generator_fields"]["present"])

    def test_multiple_jpeg_comments_require_explicit_removal(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-jpeg-comments-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.jpg"
            Image.new("RGB", (3, 3), "white").save(source, quality=95)
            original = source.read_bytes()

            def comment_segment(value):
                encoded = value.encode("ascii")
                return b"\xff\xfe" + struct.pack(">H", len(encoded) + 2) + encoded

            source.write_bytes(
                original[:2]
                + comment_segment("first-comment")
                + comment_segment("second-comment")
                + original[2:]
            )

            with self.assertRaisesRegex(MetadataCleanupError, "multiple JPEG comments"):
                cleanup_image_metadata(source, temp_path / "preserve.png")

            result = cleanup_image_metadata(
                source,
                temp_path / "removed.png",
                MetadataCleanupOptions(remove_comments_text=True),
            )
            self.assertEqual(result["actions"]["comments_text"], "removed")

    def test_duplicate_png_text_keys_and_oversized_pixel_count_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-preflight-") as temp_dir:
            temp_path = Path(temp_dir)
            duplicate_source = temp_path / "duplicate.png"
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_text("Comment", "first")
            pnginfo.add_text("Comment", "second")
            Image.new("RGB", (2, 2), "white").save(duplicate_source, pnginfo=pnginfo)
            with self.assertRaisesRegex(MetadataCleanupError, "duplicate PNG text keys"):
                cleanup_image_metadata(duplicate_source, temp_path / "duplicate-output.png")

            source = temp_path / "source.png"
            create_png_fixture(source)
            with patch("metadata_cleanup._MAX_SOURCE_PIXELS", 1):
                with self.assertRaisesRegex(MetadataCleanupError, "pixel limit"):
                    cleanup_image_metadata(source, temp_path / "pixel-output.png")

    def test_validation_failure_preserves_existing_output_and_source(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-atomic-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "existing.png"
            create_png_fixture(source)
            output.write_bytes(b"previous-output-must-survive")
            source_hash = file_hash(source)
            previous_output = output.read_bytes()

            with patch(
                "metadata_cleanup._validate_cleanup_output",
                side_effect=MetadataCleanupError("forced validation failure"),
            ):
                with self.assertRaisesRegex(MetadataCleanupError, "forced validation failure"):
                    cleanup_image_metadata(source, output, MetadataCleanupOptions(remove_xmp=True))

            self.assertEqual(file_hash(source), source_hash)
            self.assertEqual(output.read_bytes(), previous_output)
            self.assertEqual(list(temp_path.glob(".*.tmp.png")), [])

    def test_same_path_animation_and_non_png_destination_are_rejected(self):
        with tempfile.TemporaryDirectory(prefix="clipart-metadata-cleanup-invalid-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            create_png_fixture(source)
            source_hash = file_hash(source)
            with self.assertRaisesRegex(MetadataCleanupError, "never overwrites"):
                cleanup_image_metadata(source, source)
            with self.assertRaisesRegex(MetadataCleanupError, r"\.png extension"):
                cleanup_image_metadata(source, temp_path / "output.jpg")

            animated = temp_path / "animated.png"
            first = Image.new("RGBA", (4, 4), "red")
            second = Image.new("RGBA", (4, 4), "blue")
            first.save(animated, save_all=True, append_images=[second], duration=100)
            with self.assertRaisesRegex(MetadataCleanupError, "single-frame"):
                cleanup_image_metadata(animated, temp_path / "animated-output.png")
            self.assertEqual(file_hash(source), source_hash)


if __name__ == "__main__":
    unittest.main()
