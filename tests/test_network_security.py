import unittest
from unittest.mock import patch

from network_security import HttpsOnlyRedirectHandler, NetworkSecurityError, secure_json_request


class NetworkSecurityTests(unittest.TestCase):
    def test_rejects_non_https_and_credentials_in_url(self):
        with self.assertRaises(NetworkSecurityError):
            secure_json_request("http://example.invalid", headers={}, timeout=1)
        with self.assertRaises(NetworkSecurityError):
            secure_json_request("https://user:pass@example.invalid", headers={}, timeout=1)

    def test_bounds_response_and_parses_json(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b'{"ok":true}' if size > 10 else b"x" * size
        with patch("network_security.urllib.request.OpenerDirector.open", return_value=Response()):
            self.assertEqual(secure_json_request("https://example.invalid", headers={}, timeout=1), {"ok": True})

    def test_redirect_policy_blocks_downgrade_cross_host_port_and_credentials(self):
        handler = HttpsOnlyRedirectHandler()
        request = __import__("urllib.request", fromlist=["Request"]).Request("https://api.example.test/v1")
        for target in (
            "http://api.example.test/v1",
            "https://other.example.test/v1",
            "https://api.example.test:8443/v1",
            "https://user:pass@api.example.test/v1",
        ):
            with self.assertRaises(NetworkSecurityError):
                handler.redirect_request(request, None, 302, "redirect", {}, target)

    def test_response_over_limit_and_malformed_json_are_rejected(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return b"x" * size
        with patch("network_security.urllib.request.OpenerDirector.open", return_value=Response()):
            with self.assertRaises(NetworkSecurityError):
                secure_json_request("https://example.invalid", headers={}, timeout=1, max_bytes=8)


if __name__ == "__main__":
    unittest.main()
