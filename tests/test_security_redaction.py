import unittest
import os
import tempfile
from pathlib import Path

from api_credentials import EnvCredentialStore
from security_redaction import redact_text, redact_value


class SecurityRedactionTests(unittest.TestCase):
    def test_redacts_query_headers_bearer_and_private_material(self):
        text = (
            "?api_key=live-key&access_token=access-value&token=abc "
            "X-API-Key: header-value Authorization: Bearer bearer-value "
            '{"api_key":"json-value"} '
            "-----BEGIN PRIVATE KEY-----secret-----END PRIVATE KEY-----"
        )
        result = redact_text(text, ("live-key",))
        self.assertNotIn("live-key", result)
        self.assertNotIn("access-value", result)
        self.assertNotIn("header-value", result)
        self.assertNotIn("json-value", result)
        self.assertNotIn("bearer-value", result)
        self.assertNotIn("PRIVATE KEY-----secret", result)

    def test_redacts_nested_sensitive_fields_without_mutating_input(self):
        payload = {
            "headers": {"Authorization": "Bearer abc"},
            "body": {"nested": {"runpod_api_key": "secret"}, "ok": "value"},
            "items": [{"license_key": "license"}],
        }
        result = redact_value(payload)
        self.assertEqual(payload["body"]["nested"]["runpod_api_key"], "secret")
        self.assertEqual(result["headers"]["Authorization"], "[hidden]")
        self.assertEqual(result["body"]["nested"]["runpod_api_key"], "[hidden]")
        self.assertEqual(result["items"][0]["license_key"], "[hidden]")
        self.assertEqual(result["body"]["ok"], "value")

    def test_sensitive_artifact_scanner_allows_only_explicit_baseline(self):
        from scripts.check_sensitive_artifacts import scan_paths

        self.assertEqual(scan_paths([Path("licenses.db")]), ["blocked sensitive path: licenses.db"])
        self.assertEqual(scan_paths([Path("licenses.db")], allowed={"licenses.db"}), [])

    def test_sensitive_artifact_scanner_allows_known_detection_fixtures(self):
        from scripts.check_sensitive_artifacts import scan_paths

        paths = [Path("scripts/check_sensitive_artifacts.py"), Path(__file__)]
        findings = scan_paths(paths)
        self.assertEqual(len(findings), 2)
        self.assertEqual(scan_paths(paths, allowed={path.as_posix() for path in paths}), [])

    def test_legacy_env_store_uses_private_file_mode_on_posix(self):
        if os.name == "nt":
            self.skipTest("POSIX file mode is not applicable on Windows")
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / ".env"
            EnvCredentialStore(str(path)).save({"kie_api_key": "fixture-key"})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
