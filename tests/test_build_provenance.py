import unittest

from build_provenance import build_provenance


class BuildProvenanceTests(unittest.TestCase):
    def test_manifest_is_machine_readable_and_secret_free(self):
        payload = build_provenance(commit="abc", archive_url="https://example.invalid/a.zip", archive_sha256="a" * 64)
        self.assertTrue(payload["secret_free"])
        self.assertEqual(payload["archive"]["sha256"], "a" * 64)
        self.assertNotIn("token", repr(payload).lower())

    def test_provenance_rejects_credential_bearing_urls(self):
        with self.assertRaises(ValueError):
            build_provenance(commit="abc", archive_url="https://user:secret@example.invalid/a.zip", archive_sha256="a" * 64)


if __name__ == "__main__":
    unittest.main()
