import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from scripts import repack_reverse_synthid_codebook as repacker


class _ForbiddenPayload:
    def __reduce__(self):
        import os

        return os.system, ("echo unsafe",)


class ReverseSynthIdCodebookRepackTests(unittest.TestCase):
    def _source(self, root: Path, value: object) -> Path:
        source = root / "source.npz"
        np.savez(
            source,
            format_version=np.array(4),
            keys=np.array([value], dtype=object),
            numeric=np.arange(6, dtype=np.int16),
        )
        return source

    def test_repack_converts_strings_and_is_deterministic(self):
        with tempfile.TemporaryDirectory(prefix="m1-repack-") as temp:
            root = Path(temp)
            source = self._source(root, "model|1|1")
            first = root / "first.npz"
            second = root / "second.npz"
            with mock.patch.object(
                repacker,
                "SOURCE_SHA256",
                repacker.sha256_file(source),
            ):
                first_hash = repacker.repack(source, first)
                second_hash = repacker.repack(source, second)

            self.assertEqual(first_hash, second_hash)
            with np.load(first, allow_pickle=False) as archive:
                self.assertEqual(archive["keys"].dtype.kind, "U")
                self.assertFalse(any(archive[key].dtype.hasobject for key in archive.files))

    def test_repack_rejects_forbidden_pickle_global_without_execution(self):
        with tempfile.TemporaryDirectory(prefix="m1-repack-malicious-") as temp:
            root = Path(temp)
            source = self._source(root, _ForbiddenPayload())
            destination = root / "safe.npz"
            with mock.patch.object(
                repacker,
                "SOURCE_SHA256",
                repacker.sha256_file(source),
            ):
                with self.assertRaisesRegex(repacker.RepackError, "forbidden"):
                    repacker.repack(source, destination)
            self.assertFalse(destination.exists())

    def test_repack_never_overwrites_destination(self):
        with tempfile.TemporaryDirectory(prefix="m1-repack-existing-") as temp:
            root = Path(temp)
            source = self._source(root, "model|1|1")
            destination = root / "keep.npz"
            destination.write_bytes(b"keep")
            with mock.patch.object(
                repacker,
                "SOURCE_SHA256",
                repacker.sha256_file(source),
            ):
                with self.assertRaisesRegex(repacker.RepackError, "must not"):
                    repacker.repack(source, destination)
            self.assertEqual(destination.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
