import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from chroma_provenance import image_digest, load_receipt, receipt_path, write_receipt


class ChromaProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / "result.png"
        Image.new("RGBA", (3, 3), (10, 20, 30, 255)).save(self.image)

    def write(self):
        return write_receipt(self.image, source_sha256="a" * 64,
                             requested_background="#0000FF", observed_background="#0225FA")

    def test_roundtrip_is_hash_bound_and_not_a_quality_certificate(self):
        self.write()
        record = load_receipt(self.image)
        self.assertEqual(record["observed_removal_background"], "#0225FA")
        self.assertEqual(record["result_sha256"], image_digest(self.image))
        self.assertEqual(record["quality_status"], "not_evaluated")
        self.assertEqual(record["profile"], "opaque-clipart-v9")
        self.assertFalse(any("path" in field or "prompt" in field for field in record))

    def test_previous_profile_receipt_remains_readable_without_relabeling(self):
        path = self.write()
        record = json.loads(path.read_text())
        for profile in ("opaque-clipart-v1", "opaque-clipart-v2", "opaque-clipart-v3", "opaque-clipart-v4", "opaque-clipart-v5", "opaque-clipart-v6", "opaque-clipart-v7", "opaque-clipart-v8"):
            record["profile"] = profile
            path.write_text(json.dumps(record))
            self.assertEqual(load_receipt(self.image)["profile"], profile)

    def test_image_and_receipt_can_move_together(self):
        original = self.write()
        moved = self.image.with_name("renamed.png")
        self.image.rename(moved)
        original.rename(receipt_path(moved))
        self.assertIsNotNone(load_receipt(moved))

    def test_changed_image_invalidates_receipt(self):
        self.write()
        Image.new("RGBA", (3, 3), (100, 20, 30, 255)).save(self.image)
        self.assertIsNone(load_receipt(self.image))

    def test_changed_export_cannot_receive_receipt_from_previous_processing(self):
        with self.assertRaises(ValueError):
            write_receipt(self.image, source_sha256="a" * 64,
                          requested_background="#0000FF", observed_background="#0000FF",
                          expected_result_sha256="b" * 64)
        self.assertFalse(receipt_path(self.image).exists())

    def test_existing_sidecar_is_not_overwritten(self):
        path = self.write()
        before = path.read_bytes()
        with self.assertRaises(FileExistsError):
            self.write()
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(path.parent.glob(".chroma-*")), [])

    def test_missing_and_invalid_records_are_unavailable(self):
        self.assertIsNone(load_receipt(self.image))
        path = receipt_path(self.image)
        for content in (b"{", b"[]", b"x" * 9000):
            path.write_bytes(content)
            self.assertIsNone(load_receipt(self.image))

    def test_unrecognized_schema_cannot_claim_quality(self):
        path = self.write()
        record = json.loads(path.read_text())
        for key, value in (("schema_version", True), ("quality_status", "ready"),
                           ("profile", "future-v9")):
            bad = dict(record, **{key: value})
            path.write_text(json.dumps(bad))
            self.assertIsNone(load_receipt(self.image))
