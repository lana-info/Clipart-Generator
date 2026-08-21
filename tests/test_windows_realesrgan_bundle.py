import hashlib
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = ROOT_DIR / "scripts" / "prepare_realesrgan_runtime.py"


class WindowsRealEsrganBundleTests(unittest.TestCase):
    def _write_archive(
        self, path: Path, *, include_models: bool, include_photo: bool = True
    ) -> str:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("realesrgan-ncnn-vulkan.exe", b"test executable")
            archive.writestr("vcomp140.dll", b"test runtime")
            if include_models:
                names = [
                    "realesr-animevideov3-x2",
                    "realesrgan-x4plus-anime",
                ]
                if include_photo:
                    names.append("realesrgan-x4plus")
                for name in names:
                    archive.writestr(f"models/{name}.bin", b"model")
                    archive.writestr(f"models/{name}.param", b"parameters")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _run_prepare(self, archive: Path, target: Path, digest: str):
        return subprocess.run(
            [
                sys.executable,
                str(PREPARE_SCRIPT),
                "--archive",
                str(archive),
                "--target",
                str(target),
                "--sha256",
                digest,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_prepares_complete_runtime_with_required_scale_models(self):
        with tempfile.TemporaryDirectory(prefix="realesrgan-bundle-") as temp:
            root = Path(temp)
            archive = root / "runtime.zip"
            target = root / "runtime"
            digest = self._write_archive(archive, include_models=True)

            result = self._run_prepare(archive, target, digest)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((target / "realesrgan-ncnn-vulkan.exe").is_file())
            self.assertTrue((target / "models" / "realesr-animevideov3-x2.bin").is_file())
            self.assertTrue((target / "models" / "realesr-animevideov3-x2.param").is_file())
            self.assertTrue((target / "models" / "realesrgan-x4plus-anime.bin").is_file())
            self.assertTrue((target / "models" / "realesrgan-x4plus-anime.param").is_file())
            self.assertTrue((target / "models" / "realesrgan-x4plus.bin").is_file())
            self.assertTrue((target / "models" / "realesrgan-x4plus.param").is_file())

    def test_rejects_archive_without_required_models(self):
        with tempfile.TemporaryDirectory(prefix="realesrgan-incomplete-") as temp:
            root = Path(temp)
            archive = root / "runtime.zip"
            target = root / "runtime"
            digest = self._write_archive(archive, include_models=False)

            result = self._run_prepare(archive, target, digest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("required Real-ESRGAN file is missing", result.stderr)
            self.assertFalse(target.exists())

    def test_rejects_archive_without_photo_model(self):
        with tempfile.TemporaryDirectory(prefix="realesrgan-no-photo-") as temp:
            root = Path(temp)
            archive = root / "runtime.zip"
            target = root / "runtime"
            digest = self._write_archive(
                archive, include_models=True, include_photo=False
            )

            result = self._run_prepare(archive, target, digest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("realesrgan-x4plus", result.stderr)
            self.assertFalse(target.exists())

    def test_rejects_archive_with_wrong_sha256(self):
        with tempfile.TemporaryDirectory(prefix="realesrgan-hash-") as temp:
            root = Path(temp)
            archive = root / "runtime.zip"
            target = root / "runtime"
            self._write_archive(archive, include_models=True)

            result = self._run_prepare(archive, target, "0" * 64)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SHA-256 mismatch", result.stderr)
            self.assertFalse(target.exists())

    def test_rejects_archive_path_traversal(self):
        with tempfile.TemporaryDirectory(prefix="realesrgan-traversal-") as temp:
            root = Path(temp)
            archive = root / "runtime.zip"
            target = root / "runtime"
            self._write_archive(archive, include_models=True)
            with zipfile.ZipFile(archive, "a") as bundle:
                bundle.writestr("../outside.txt", b"must not escape")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

            result = self._run_prepare(archive, target, digest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe Real-ESRGAN archive member", result.stderr)
            self.assertFalse((root / "outside.txt").exists())
            self.assertFalse(target.exists())

    def test_rejects_archive_symlink(self):
        with tempfile.TemporaryDirectory(prefix="realesrgan-symlink-") as temp:
            root = Path(temp)
            archive = root / "runtime.zip"
            target = root / "runtime"
            self._write_archive(archive, include_models=True)
            link = zipfile.ZipInfo("models/unsafe-link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(archive, "a") as bundle:
                bundle.writestr(link, "../outside.txt")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()

            result = self._run_prepare(archive, target, digest)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("symlink is not allowed", result.stderr)
            self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
