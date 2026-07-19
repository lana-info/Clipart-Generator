import tempfile
import unittest
import hashlib
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import main


class _Response:
    def __init__(self, payload, content_length=None):
        self.payload = payload
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def read(self, limit=-1):
        if limit < 0:
            return self.payload
        return self.payload[:limit]


class _ResponseContext(_Response):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _UpdateHarness:
    _sha256_file = main.MainWindow._sha256_file


class SecurityBoundaryTests(unittest.TestCase):
    def test_local_image_preflight_accepts_single_frame_within_limits(self):
        with tempfile.TemporaryDirectory(prefix="clipart-local-preflight-") as temp_dir:
            image_path = Path(temp_dir) / "input.png"
            Image.new("RGBA", (4, 3), (255, 255, 255, 255)).save(image_path)

            self.assertIsNone(main.validate_local_image_input(image_path))

    def test_local_image_preflight_rejects_animated_input(self):
        with tempfile.TemporaryDirectory(prefix="clipart-local-preflight-gif-") as temp_dir:
            image_path = Path(temp_dir) / "input.gif"
            frames = [Image.new("RGB", (4, 3), color) for color in ("red", "blue")]
            frames[0].save(image_path, save_all=True, append_images=frames[1:], format="GIF")

            with self.assertRaisesRegex(ValueError, "single-frame"):
                main.validate_local_image_input(image_path)

    def test_local_image_preflight_rejects_oversized_input(self):
        with tempfile.TemporaryDirectory(prefix="clipart-local-preflight-size-") as temp_dir:
            image_path = Path(temp_dir) / "input.png"
            Image.new("RGB", (4, 3), "white").save(image_path)

            with patch.object(main, "MAX_PROVIDER_IMAGE_PIXELS", 4):
                with self.assertRaisesRegex(ValueError, "pixel limit"):
                    main.validate_local_image_input(image_path)

    def test_update_installer_rejects_non_https_url_before_network(self):
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            main.MainWindow._download_update_installer(object(), "http://updates.example/app.exe")

    def test_update_installer_rejects_credentials_in_url(self):
        with self.assertRaisesRegex(RuntimeError, "credentials"):
            main.MainWindow._download_update_installer(object(), "https://user:pass@updates.example/app.exe")

    def test_update_installer_response_is_size_limited(self):
        response = _ResponseContext(b"0123456789", content_length=10)
        with patch.object(main, "open_url_secure", return_value=response):
            with patch.object(main, "MAX_UPDATE_INSTALLER_BYTES", 8):
                with self.assertRaises(main.ResponseLimitError):
                    main.MainWindow._download_update_installer(object(), "https://updates.example/app.exe")

    def test_update_manifest_response_is_size_limited(self):
        response = _Response(b"0123456789", content_length=10)
        with self.assertRaises(main.ResponseLimitError):
            main.read_response_limited(response, 8)

    def test_update_installer_download_writes_verified_bytes_to_temp_file(self):
        payload = b"trusted-installer-fixture"
        response = _ResponseContext(payload, content_length=len(payload))
        expected_sha256 = hashlib.sha256(payload).hexdigest()
        with tempfile.TemporaryDirectory(prefix="clipart-update-") as temp_dir:
            with (
                patch.object(main, "open_url_secure", return_value=response),
                patch.object(main.tempfile, "gettempdir", return_value=temp_dir),
            ):
                installer_path = main.MainWindow._download_update_installer(
                    _UpdateHarness(),
                    "https://updates.example/app.exe",
                    expected_sha256=expected_sha256,
                )

            self.assertEqual(Path(installer_path).read_bytes(), payload)

    def test_update_installer_checksum_mismatch_removes_untrusted_temp_file(self):
        payload = b"untrusted-installer-fixture"
        response = _ResponseContext(payload, content_length=len(payload))
        with tempfile.TemporaryDirectory(prefix="clipart-update-mismatch-") as temp_dir:
            with (
                patch.object(main, "open_url_secure", return_value=response),
                patch.object(main.tempfile, "gettempdir", return_value=temp_dir),
                patch.object(main.time, "time", return_value=123),
            ):
                with self.assertRaisesRegex(RuntimeError, "Контрольная сумма"):
                    main.MainWindow._download_update_installer(
                    _UpdateHarness(),
                        "https://updates.example/app.exe",
                        expected_sha256="0" * 64,
                    )

            self.assertFalse((Path(temp_dir) / "ClipartGenerator-Update-123.exe").exists())

    def test_local_image_preflight_rejects_corrupt_input(self):
        with tempfile.TemporaryDirectory(prefix="clipart-local-preflight-corrupt-") as temp_dir:
            image_path = Path(temp_dir) / "corrupt.png"
            image_path.write_bytes(b"not-a-png")

            with self.assertRaisesRegex(ValueError, "invalid"):
                main.validate_local_image_input(image_path)


if __name__ == "__main__":
    unittest.main()
