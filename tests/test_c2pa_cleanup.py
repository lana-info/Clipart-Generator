import hashlib
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

from PIL import Image, PngImagePlugin

from metadata_cleanup import MetadataCleanupError, MetadataCleanupOptions, cleanup_image_metadata
from metadata_inspector import inspect_image_metadata
from tests.test_c2pa_inspector import (
    add_jpeg_segments,
    add_png_chunk_after_ihdr,
    c2pa_jumbf,
    jpeg_app11_segments,
    png_chunk,
)


DCTERMS_NAMESPACE = "http://purl.org/dc/terms/"
CUSTOM_NAMESPACE = "https://example.invalid/c2pa-cleanup/"
REMOTE_MANIFEST_URL = "https://example.invalid/private-manifest.c2pa"
CUSTOM_XMP_VALUE = "preserve-this-xmp-value"


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def xmp_with_reference(reference=REMOTE_MANIFEST_URL):
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/"
        xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:dcterms="{DCTERMS_NAMESPACE}"
        xmlns:custom="{CUSTOM_NAMESPACE}">
      <rdf:RDF>
        <rdf:Description dcterms:provenance="{reference}"
            custom:Keep="{CUSTOM_XMP_VALUE}" />
      </rdf:RDF>
    </x:xmpmeta>"""


def xmp_with_resource_reference():
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/"
        xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:dcterms="{DCTERMS_NAMESPACE}"
        xmlns:custom="{CUSTOM_NAMESPACE}">
      <rdf:RDF>
        <rdf:Description custom:Keep="{CUSTOM_XMP_VALUE}">
          <dcterms:provenance rdf:resource="{REMOTE_MANIFEST_URL}" />
        </rdf:Description>
      </rdf:RDF>
    </x:xmpmeta>"""


def wrapped_xmp_with_reference():
    return (
        '<?xpacket begin="packet-start"?>'
        f'<x:xmpmeta xmlns:x="adobe:ns:meta/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        f'xmlns:dcterms="{DCTERMS_NAMESPACE}" xmlns:custom="{CUSTOM_NAMESPACE}">'
        '<!--keep-comment--><?keep instruction?>'
        f'<rdf:RDF><rdf:Description dcterms:provenance="{REMOTE_MANIFEST_URL}" '
        f'custom:Keep="{CUSTOM_XMP_VALUE}" /></rdf:RDF></x:xmpmeta>'
        '<?xpacket end="w"?>'
    )


def create_png_c2pa_fixture(path, *, embedded=True, reference=REMOTE_MANIFEST_URL):
    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_itxt("XML:com.adobe.xmp", xmp_with_reference(reference))
    Image.new("RGBA", (8, 6), (20, 40, 60, 180)).save(path, pnginfo=pnginfo, dpi=(300, 300))
    if embedded:
        add_png_chunk_after_ihdr(path, b"caBX", c2pa_jumbf())


def create_jpeg_c2pa_fixture(path):
    Image.new("RGB", (9, 7), (220, 180, 140)).save(path, quality=95, dpi=(300, 300))
    xmp_payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp_with_resource_reference().encode("utf-8")
    xmp_segment = b"\xff\xe1" + struct.pack(">H", len(xmp_payload) + 2) + xmp_payload
    app11_segments, _ = jpeg_app11_segments(c2pa_jumbf(), split_at=70)
    add_jpeg_segments(path, xmp_segment + app11_segments)


def add_png_xmp_after_idat(path, xmp_text):
    data = Path(path).read_bytes()
    iend_type_position = data.rfind(b"IEND")
    if iend_type_position < 4:
        raise AssertionError("fixture PNG has no IEND chunk")
    iend_start = iend_type_position - 4
    payload = b"XML:com.adobe.xmp\x00\x00\x00\x00\x00" + xmp_text.encode("utf-8")
    Path(path).write_bytes(data[:iend_start] + png_chunk(b"iTXt", payload) + data[iend_start:])


def output_xmp_attributes(path):
    with Image.open(path) as image:
        image.load()
        payload = image.text["XML:com.adobe.xmp"].encode("utf-8")
    root = ElementTree.fromstring(payload)
    description = next(element for element in root.iter() if element.tag.endswith("Description"))
    return description.attrib


class C2paCleanupTests(unittest.TestCase):
    def test_png_embedded_structure_and_xmp_reference_are_removed_from_new_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-png-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            create_png_c2pa_fixture(source)
            source_sidecar = source.with_suffix(".c2pa")
            output_sidecar = output.with_suffix(".c2pa")
            source_sidecar.write_bytes(b"source-sidecar-must-survive")
            output_sidecar.write_bytes(b"output-sidecar-must-survive")
            source_hash = file_hash(source)
            before = inspect_image_metadata(source)

            result = cleanup_image_metadata(
                source,
                output,
                MetadataCleanupOptions(remove_embedded_c2pa=True),
            )

            after = inspect_image_metadata(output)
            self.assertEqual(before["c2pa"]["embedded_presence"], "present")
            self.assertEqual(before["c2pa"]["external_reference_presence"], "present")
            self.assertEqual(after["c2pa"]["presence"], "not_present")
            self.assertEqual(result["actions"]["embedded_c2pa"], "removed")
            self.assertEqual(result["actions"]["c2pa_external_reference"], "removed_from_output")
            attributes = output_xmp_attributes(output)
            self.assertNotIn(f"{{{DCTERMS_NAMESPACE}}}provenance", attributes)
            self.assertEqual(attributes[f"{{{CUSTOM_NAMESPACE}}}Keep"], CUSTOM_XMP_VALUE)
            self.assertEqual(result["c2pa_scope"]["remote_manifest"], "not_deleted_or_accessed")
            self.assertEqual(result["c2pa_scope"]["sidecar_manifest"], "not_deleted_or_accessed")
            self.assertEqual(result["c2pa_scope"]["pixel_soft_bindings"], "not_removed_or_validated")
            self.assertEqual(file_hash(source), source_hash)
            self.assertEqual(source_sidecar.read_bytes(), b"source-sidecar-must-survive")
            self.assertEqual(output_sidecar.read_bytes(), b"output-sidecar-must-survive")
            serialized = json.dumps(result, sort_keys=True)
            self.assertNotIn(REMOTE_MANIFEST_URL, serialized)
            self.assertNotIn(CUSTOM_XMP_VALUE, serialized)

    def test_jpeg_app11_and_remote_xmp_reference_are_removed_without_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-jpeg-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.jpg"
            output = temp_path / "output.png"
            create_jpeg_c2pa_fixture(source)
            source_hash = file_hash(source)
            before = inspect_image_metadata(source)
            self.assertEqual(before["c2pa"]["embedded_presence"], "present")
            self.assertEqual(before["c2pa"]["external_reference_presence"], "present")

            with patch("socket.create_connection", side_effect=AssertionError("network access is forbidden")):
                result = cleanup_image_metadata(
                    source,
                    output,
                    MetadataCleanupOptions(remove_embedded_c2pa=True),
                )

            self.assertEqual(inspect_image_metadata(output)["c2pa"]["presence"], "not_present")
            self.assertEqual(result["actions"]["embedded_c2pa"], "removed")
            self.assertEqual(result["actions"]["c2pa_external_reference"], "removed_from_output")
            attributes = output_xmp_attributes(output)
            self.assertNotIn(f"{{{DCTERMS_NAMESPACE}}}provenance", attributes)
            self.assertEqual(attributes[f"{{{CUSTOM_NAMESPACE}}}Keep"], CUSTOM_XMP_VALUE)
            self.assertEqual(file_hash(source), source_hash)

    def test_remote_reference_requires_explicit_cleanup_and_preserves_previous_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-explicit-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            create_png_c2pa_fixture(source, embedded=False)
            output.write_bytes(b"previous-output")
            source_hash = file_hash(source)

            with self.assertRaisesRegex(MetadataCleanupError, "requires explicit C2PA cleanup"):
                cleanup_image_metadata(source, output)

            self.assertEqual(output.read_bytes(), b"previous-output")
            self.assertEqual(file_hash(source), source_hash)

    def test_embedded_self_reference_is_not_reported_as_a_remote_manifest(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-self-reference-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            create_png_c2pa_fixture(source, embedded=False, reference="self#jumbf=c2pa/urn:uuid:test")
            before = inspect_image_metadata(source)

            result = cleanup_image_metadata(
                source,
                output,
                MetadataCleanupOptions(remove_embedded_c2pa=True),
            )

            self.assertEqual(before["c2pa"]["embedded_reference_presence"], "present")
            self.assertEqual(before["c2pa"]["external_reference_presence"], "not_present")
            self.assertEqual(result["actions"]["c2pa_embedded_reference"], "removed_from_output")
            self.assertEqual(result["actions"]["c2pa_external_reference"], "absent")

    def test_xmp_reference_after_idat_is_inspected_and_removed(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-post-idat-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            Image.new("RGBA", (4, 4), (10, 20, 30, 128)).save(source)
            add_png_xmp_after_idat(source, xmp_with_reference())

            before = inspect_image_metadata(source)
            result = cleanup_image_metadata(
                source,
                output,
                MetadataCleanupOptions(remove_embedded_c2pa=True),
            )

            self.assertEqual(before["c2pa"]["external_reference_presence"], "present")
            self.assertEqual(result["actions"]["c2pa_external_reference"], "removed_from_output")
            self.assertEqual(inspect_image_metadata(output)["c2pa"]["presence"], "not_present")

    def test_selective_xmp_cleanup_preserves_packet_comments_and_processing_instructions(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-xmp-structure-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_itxt("XML:com.adobe.xmp", wrapped_xmp_with_reference())
            Image.new("RGBA", (4, 4), (10, 20, 30, 128)).save(source, pnginfo=pnginfo)

            cleanup_image_metadata(
                source,
                output,
                MetadataCleanupOptions(remove_embedded_c2pa=True),
            )

            with Image.open(output) as image:
                image.load()
                output_xmp = str(image.text["XML:com.adobe.xmp"])
            self.assertIn('<?xpacket begin="packet-start"?>', output_xmp)
            self.assertIn("<!--keep-comment-->", output_xmp)
            self.assertIn("<?keep instruction?>", output_xmp)
            self.assertIn('<?xpacket end="w"?>', output_xmp)
            self.assertIn(CUSTOM_XMP_VALUE, output_xmp)
            self.assertNotIn(REMOTE_MANIFEST_URL, output_xmp)

    def test_ordinary_or_invalid_provenance_uri_is_not_removed_by_guess(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-unknown-provenance-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            ordinary_provenance = "https://example.invalid/provenance-record"
            create_png_c2pa_fixture(source, embedded=False, reference=ordinary_provenance)
            source_hash = file_hash(source)
            before = inspect_image_metadata(source)

            with self.assertRaisesRegex(MetadataCleanupError, "cannot be classified safely"):
                cleanup_image_metadata(
                    source,
                    output,
                    MetadataCleanupOptions(remove_embedded_c2pa=True),
                )

            self.assertEqual(before["c2pa"]["external_reference_presence"], "not_present")
            self.assertEqual(before["c2pa"]["unclassified_reference_presence"], "present")
            self.assertEqual(file_hash(source), source_hash)
            self.assertFalse(output.exists())

    def test_valid_and_unknown_references_cannot_hide_the_unclassified_value(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-mixed-provenance-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            mixed_xmp = f"""<x:xmpmeta xmlns:x="adobe:ns:meta/"
                xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
                xmlns:dcterms="{DCTERMS_NAMESPACE}">
              <rdf:RDF><rdf:Description dcterms:provenance="{REMOTE_MANIFEST_URL}">
                <dcterms:provenance>https://example.invalid/ordinary-provenance</dcterms:provenance>
              </rdf:Description></rdf:RDF>
            </x:xmpmeta>"""
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_itxt("XML:com.adobe.xmp", mixed_xmp)
            Image.new("RGB", (3, 3), "white").save(source, pnginfo=pnginfo)
            before = inspect_image_metadata(source)

            with self.assertRaisesRegex(MetadataCleanupError, "cannot be classified safely"):
                cleanup_image_metadata(
                    source,
                    output,
                    MetadataCleanupOptions(remove_embedded_c2pa=True),
                )

            self.assertEqual(before["c2pa"]["external_reference_presence"], "present")
            self.assertEqual(before["c2pa"]["unclassified_reference_presence"], "present")
            self.assertFalse(output.exists())

    def test_jumbf_prefix_collision_is_unclassified(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-jumbf-prefix-") as temp_dir:
            source = Path(temp_dir) / "source.png"
            create_png_c2pa_fixture(
                source,
                embedded=False,
                reference="https://example.invalid/image.jpg#jumbf=c2party/not-c2pa",
            )

            inspected = inspect_image_metadata(source)

            self.assertEqual(inspected["c2pa"]["external_reference_presence"], "not_present")
            self.assertEqual(inspected["c2pa"]["unclassified_reference_presence"], "present")

    def test_duplicate_xmp_keys_are_rejected_before_selective_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-duplicate-xmp-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            pnginfo = PngImagePlugin.PngInfo()
            pnginfo.add_itxt("XML:com.adobe.xmp", xmp_with_reference())
            pnginfo.add_itxt("XML:com.adobe.xmp", xmp_with_reference("self#jumbf=c2pa/urn:uuid:test"))
            Image.new("RGB", (3, 3), "white").save(source, pnginfo=pnginfo)
            source_hash = file_hash(source)

            with self.assertRaisesRegex(MetadataCleanupError, "duplicate PNG text keys"):
                cleanup_image_metadata(
                    source,
                    output,
                    MetadataCleanupOptions(remove_embedded_c2pa=True),
                )

            self.assertEqual(file_hash(source), source_hash)
            self.assertFalse(output.exists())

    def test_post_save_c2pa_mismatch_aborts_atomic_publication(self):
        with tempfile.TemporaryDirectory(prefix="clipart-c2pa-cleanup-validation-") as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "source.png"
            output = temp_path / "output.png"
            create_png_c2pa_fixture(source)
            output.write_bytes(b"previous-output")
            source_hash = file_hash(source)
            real_inspect = inspect_image_metadata

            def simulated_inspection(path):
                result = real_inspect(path)
                if Path(path).name.endswith(".tmp.png"):
                    result["c2pa"] = dict(result["c2pa"])
                    result["c2pa"]["presence"] = "present"
                    result["c2pa"]["embedded_presence"] = "present"
                return result

            with patch("metadata_cleanup.inspect_image_metadata", side_effect=simulated_inspection):
                with self.assertRaisesRegex(MetadataCleanupError, "retained a C2PA"):
                    cleanup_image_metadata(
                        source,
                        output,
                        MetadataCleanupOptions(remove_embedded_c2pa=True),
                    )

            self.assertEqual(output.read_bytes(), b"previous-output")
            self.assertEqual(file_hash(source), source_hash)
            self.assertEqual(list(temp_path.glob(".*.tmp.png")), [])


if __name__ == "__main__":
    unittest.main()
