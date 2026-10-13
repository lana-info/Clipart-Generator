"""Read-only balance checks use the official endpoints and safe response parsing."""
import unittest
from unittest.mock import patch

from provider_balance import check_provider_balance, parse_balance


class ProviderBalanceTests(unittest.TestCase):
    def test_piapi_uses_actual_dollar_equivalent_not_point_credits(self):
        for record in ({"data": {"equivalent_in_usd": "12.346", "wallet": {"point_remain": 30}}},
                       {"data": [{"equivalent_in_usd": "12.346"}]}):
            self.assertEqual(parse_balance("piapi", record), "Баланс PiAPI: 12.35 USD")
        with self.assertRaises(ValueError):
            parse_balance("piapi", {"data": {"wallet": {"point_remain": 500}}})

    def test_atlas_uses_spendable_usd_not_bonus_or_frozen_balance(self):
        value = {"available": {"value": "13.230000", "currency": "usd"},
                 "frozen": {"value": "999", "currency": "usd"}}
        self.assertEqual(parse_balance("atlascloud", value), "Баланс AtlasCloud: 13.23 USD")
        with self.assertRaises(ValueError):
            parse_balance("atlascloud", {"available": {"value": "5", "currency": "btc"}})

    def test_only_approved_read_endpoints_receive_key_and_no_post(self):
        expected = {"piapi": ("https://api.piapi.ai/account/info", "X-API-KEY"),
                    "atlascloud": ("https://api.atlascloud.ai/public/v1/balance", "Authorization")}
        for provider,(url,auth_header) in expected.items():
            with self.subTest(provider=provider):
                def fake_request(request_url, *, headers, timeout, max_bytes):
                    self.assertEqual(request_url, url)
                    self.assertIn("secret-only-test", headers[auth_header])
                    self.assertEqual(max_bytes, 65536)
                    return ({"data": {"equivalent_in_usd": "3.0"}} if provider == "piapi"
                            else {"available": {"value": "3.0", "currency": "usd"}})
                with patch('provider_balance.secure_json_request', fake_request):
                    result = check_provider_balance(provider, "secret-only-test")
                self.assertIn("3.00 USD", result)
                self.assertNotIn("secret-only-test", result)

    def test_never_reports_bad_or_unknown_balance_as_free(self):
        for provider in ("piapi", "atlascloud"):
            with self.subTest(provider=provider):
                with patch('provider_balance.secure_json_request', return_value={}), self.assertRaises(RuntimeError):
                    check_provider_balance(provider, "a-key")
        for value in (True, None, "nan", "Infinity", "-1", "not-numeric"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_balance("piapi", {"equivalent_in_usd": value})

    def test_bad_key_rejected_before_transport(self):
        with patch('provider_balance.secure_json_request') as request:
            with self.assertRaises(ValueError):
                check_provider_balance("piapi", "bad\nkey")
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
