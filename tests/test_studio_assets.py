from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio_assets import AssetRecord, AssetStore, AssetStoreError


class AssetStoreTests(unittest.TestCase):
    def _write(self, directory: Path, name: str, payload: bytes) -> Path:
        path = directory / name
        path.write_bytes(payload)
        return path

    def test_import_deduplicates_identical_bytes_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            first = self._write(base, "first.png", b"same image bytes")
            second = self._write(base, "second.jpg", b"same image bytes")
            before = first.read_bytes()
            store = AssetStore(base / "assets")

            first_record = store.import_file(first)
            second_record = store.import_file(second)

            self.assertEqual(first_record.id, hashlib.sha256(before).hexdigest())
            self.assertEqual(first_record.id, second_record.id)
            self.assertEqual(first_record.size, len(before))
            self.assertEqual(first.read_bytes(), before)
            self.assertEqual(second.read_bytes(), before)
            self.assertEqual(store.resolve(first_record).read_bytes(), before)
            self.assertEqual(len(list(store.root.iterdir())), 1)

    def test_record_round_trip_is_strict_and_does_not_store_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, "report.pdf", b"%PDF-sample")
            record = AssetStore(base / "assets").import_file(source)

            encoded = record.to_dict()
            self.assertEqual(AssetRecord.from_dict(encoded), record)
            self.assertNotIn(str(source), repr(encoded))
            self.assertEqual(encoded["filename"], "report.pdf")
            for invalid in (
                {**encoded, "schema_version": 2},
                {key: value for key, value in encoded.items() if key != "media_type"},
                {**encoded, "size": True},
                {**encoded, "filename": "/private/path.png"},
                {**encoded, "unexpected": "no"},
            ):
                with self.assertRaises(AssetStoreError):
                    AssetRecord.from_dict(invalid)

    def test_import_rejects_missing_and_symlinked_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            store = AssetStore(base / "assets")
            with self.assertRaisesRegex(AssetStoreError, "source"):
                store.import_file(base / "missing.png")

            target = self._write(base, "target.png", b"target")
            link = base / "link.png"
            try:
                link.symlink_to(target)
            except (NotImplementedError, OSError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(AssetStoreError, "symlink"):
                store.import_file(link)

    def test_resolve_rejects_tampering_and_metadata_mismatch(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            store = AssetStore(base / "assets")
            record = store.import_file(self._write(base, "safe.png", b"original"))
            mismatched = AssetRecord(record.id, record.sha256, record.size + 1,
                                     record.filename, record.media_type)
            with self.assertRaisesRegex(AssetStoreError, "integrity"):
                store.resolve(mismatched)
            stored = store.root / record.id
            stored.write_bytes(b"tampered")
            with self.assertRaisesRegex(AssetStoreError, "integrity"):
                store.resolve(record)

    def test_corrupted_existing_destination_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            payload = b"correct"
            source = self._write(base, "safe.png", payload)
            store = AssetStore(base / "assets")
            destination = store.root / hashlib.sha256(payload).hexdigest()
            destination.write_bytes(b"wrong")

            with self.assertRaisesRegex(AssetStoreError, "integrity"):
                store.import_file(source)
            self.assertEqual(destination.read_bytes(), b"wrong")

    def test_failed_publication_cleans_staged_file_and_never_creates_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, "safe.png", b"content")
            store = AssetStore(base / "assets")
            with patch("studio_assets.os.link", side_effect=OSError("interrupted")):
                with self.assertRaises(AssetStoreError):
                    store.import_file(source)
            self.assertEqual(list(store.root.iterdir()), [])

    def test_interrupted_copy_cleans_staged_file(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, "safe.png", b"content")
            store = AssetStore(base / "assets")
            with patch("studio_assets.os.fsync", side_effect=OSError("interrupted")):
                with self.assertRaisesRegex(AssetStoreError, "source"):
                    store.import_file(source)
            self.assertEqual(list(store.root.iterdir()), [])

    def test_streaming_limit_rejects_oversized_file_without_publication(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, "large.bin", b"x" * 17)
            store = AssetStore(base / "assets", max_per_asset=16)
            with self.assertRaisesRegex(AssetStoreError, "size limit"):
                store.import_file(source)
            self.assertEqual(list(store.root.iterdir()), [])

    def test_weird_filename_is_safe_basename_and_media_type_is_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, " strange name отчёт .PDF", b"document")
            record = AssetStore(base / "assets").import_file(source)

            self.assertEqual(record.filename, source.name)
            self.assertNotIn("/", record.filename)
            self.assertEqual(record.media_type, "application/pdf")

    def test_filename_is_sanitized_for_portable_materialization(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, "untrusted\\..\\report.PDF", b"document")
            record = AssetStore(base / "assets").import_file(source)

            self.assertEqual(record.filename, "untrusted_.._report.PDF")
            self.assertEqual(record.media_type, "application/pdf")
            unsafe = {**record.to_dict(), "filename": "..\\outside.pdf"}
            with self.assertRaises(AssetStoreError):
                AssetRecord.from_dict(unsafe)

    def test_filename_sanitizer_handles_windows_reserved_and_control_names(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = self._write(base, "CON.PDF", b"document")
            record = AssetStore(base / "assets").import_file(source)

            self.assertEqual(record.filename, "_CON.PDF")
            self.assertEqual(AssetStore._sanitize_filename("report. "), "report")
            self.assertEqual(AssetStore._sanitize_filename("bad\x01name.pdf"), "bad_name.pdf")
            long_name = AssetStore._sanitize_filename("é" * 130 + ".pdf")
            self.assertLessEqual(len(long_name), 240)
            self.assertLessEqual(len(long_name.encode("utf-8")), 240)
            self.assertTrue(long_name.endswith(".pdf"))
            for unsafe_name in ("PRN.txt", "report. ", "bad\x01name.pdf"):
                with self.assertRaises(AssetStoreError):
                    AssetRecord.from_dict({**record.to_dict(), "filename": unsafe_name})

    def test_windows_skips_directory_fsync_but_import_remains_usable(self):
        with tempfile.TemporaryDirectory() as temp:
            store = AssetStore(Path(temp) / "assets")
            with patch("studio_assets.os.name", "nt"), patch("studio_assets.os.open") as open_file:
                store._fsync_directory()
            open_file.assert_not_called()

    def test_root_and_asset_leaf_must_not_be_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            real_root = base / "real-assets"
            real_root.mkdir()
            link_root = base / "assets-link"
            try:
                link_root.symlink_to(real_root, target_is_directory=True)
            except (NotImplementedError, OSError):
                self.skipTest("symlinks unavailable")
            with self.assertRaisesRegex(AssetStoreError, "symlink"):
                AssetStore(link_root)

            store = AssetStore(base / "assets")
            source = self._write(base, "safe.png", b"asset")
            digest = hashlib.sha256(b"asset").hexdigest()
            outside = self._write(base, "outside", b"asset")
            (store.root / digest).symlink_to(outside)
            with self.assertRaisesRegex(AssetStoreError, "symlink"):
                store.import_file(source)

    def test_root_creation_permission_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "assets"
            with patch("studio_assets.Path.mkdir", side_effect=PermissionError("denied")):
                with self.assertRaisesRegex(AssetStoreError, "root"):
                    AssetStore(root)


if __name__ == "__main__":
    unittest.main()
