import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib import error

import license_client


DUMMY_LICENSE_KEY = "test-license-secret-must-not-appear"


class FakeOpener:
    def __init__(self, response=None, failure=None):
        self.response = response
        self.failure = failure
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        if self.failure is not None:
            raise self.failure
        return self.response


class LicenseClientSecurityTests(unittest.TestCase):
    def make_client(self, root, server_url="https://license.example", backup_server_url=""):
        return license_client.LicenseClient(
            server_url,
            str(Path(root) / "license-cache.json"),
            "1.0.2",
            timeout=3,
            backup_server_url=backup_server_url,
        )

    def test_remote_http_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-license-http-") as temp_dir:
            client = self.make_client(temp_dir, server_url="http://license.example")
            with patch.object(license_client.request, "build_opener") as opener_mock:
                with self.assertRaisesRegex(RuntimeError, "HTTPS"):
                    client.activate(DUMMY_LICENSE_KEY)
            opener_mock.assert_not_called()

    def test_http_error_body_and_license_key_are_not_exposed(self):
        with tempfile.TemporaryDirectory(prefix="clipart-license-error-") as temp_dir:
            client = self.make_client(temp_dir)
            body_marker = "private-provider-response-body"
            provider_error = error.HTTPError(
                "https://license.example/activate",
                500,
                f"Server Error {DUMMY_LICENSE_KEY}",
                {},
                BytesIO(f"{body_marker} {DUMMY_LICENSE_KEY}".encode("utf-8")),
            )
            opener = FakeOpener(failure=provider_error)

            with patch.object(license_client.request, "build_opener", return_value=opener) as build_mock:
                with self.assertRaises(RuntimeError) as raised:
                    client.activate(DUMMY_LICENSE_KEY)

            rendered = str(raised.exception)
            self.assertNotIn(body_marker, rendered)
            self.assertNotIn(DUMMY_LICENSE_KEY, rendered)
            handlers = build_mock.call_args.args
            self.assertTrue(
                any(isinstance(handler, license_client.NoRedirectHandler) for handler in handlers)
            )
            self.assertEqual(len(opener.requests), 1)

    def test_license_response_read_is_bounded(self):
        with tempfile.TemporaryDirectory(prefix="clipart-license-limit-") as temp_dir:
            client = self.make_client(temp_dir)
            response = BytesIO(b"123456789")
            response.headers = {}
            opener = FakeOpener(response=response)

            with (
                patch.object(license_client, "MAX_LICENSE_RESPONSE_BYTES", 8, create=True),
                patch.object(license_client.request, "build_opener", return_value=opener),
            ):
                with self.assertRaisesRegex(RuntimeError, "size limit"):
                    client.activate(DUMMY_LICENSE_KEY)

    def test_ambiguous_failure_does_not_try_backup_or_fallback_route(self):
        with tempfile.TemporaryDirectory(prefix="clipart-license-once-") as temp_dir:
            client = self.make_client(
                temp_dir,
                server_url="https://primary.example",
                backup_server_url="https://backup.example",
            )
            with patch.object(client, "_post", side_effect=TimeoutError("ambiguous")) as post_mock:
                with self.assertRaises(TimeoutError):
                    client._post_any("/status", {"license_key": DUMMY_LICENSE_KEY}, ["/validate"])
            self.assertEqual(post_mock.call_count, 1)

    def test_definitive_missing_route_can_fallback_once_on_same_server(self):
        with tempfile.TemporaryDirectory(prefix="clipart-license-route-") as temp_dir:
            client = self.make_client(temp_dir)
            with patch.object(
                client,
                "_post",
                side_effect=[
                    license_client.LicenseHTTPError(404, "Not Found"),
                    {"ok": True},
                ],
            ) as post_mock:
                result = client._post_any(
                    "/status",
                    {"license_key": DUMMY_LICENSE_KEY},
                    ["/validate"],
                )
            self.assertTrue(result["ok"])
            self.assertEqual(post_mock.call_count, 2)
            self.assertEqual(post_mock.call_args_list[0].args[0], "https://license.example")
            self.assertEqual(post_mock.call_args_list[1].args[0], "https://license.example")


if __name__ == "__main__":
    unittest.main()
