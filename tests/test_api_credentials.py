import unittest

from api_credentials import ALL_PROVIDER_CREDENTIAL_KEYS, SECRET_CONFIG_KEYS


class ApiCredentialKeysTests(unittest.TestCase):
    def test_fal_key_is_secret_and_available_to_provider_settings(self):
        self.assertIn("fal_api_key", SECRET_CONFIG_KEYS)
        self.assertIn("fal_api_key", ALL_PROVIDER_CREDENTIAL_KEYS)


if __name__ == "__main__":
    unittest.main()
