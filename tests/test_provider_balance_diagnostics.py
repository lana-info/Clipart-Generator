"""Offline regression checks for balance diagnostics; no credentials or network."""
import json
import unittest
import urllib.error
from unittest.mock import patch
from provider_balance import check_provider_balance, balance_response_schema, ProviderBalanceError
from network_security import NetworkSecurityError

class BalanceDiagnosticTests(unittest.TestCase):
    def test_missing_field_reports_shape_but_no_values_or_arbitrary_keys(self):
        key = "private-api-key-value"
        payload = {"data": {"wallet": {"point_remain": 123, "email": "private@example.org"},
                            "account_name": "Private Person", "api_key": key, key: "another-private-value"}}
        events = []
        with patch("provider_balance.secure_json_request", return_value=payload):
            with self.assertRaisesRegex(ProviderBalanceError, "equivalent_in_usd"):
                check_provider_balance("piapi", key, diagnostic=events.append)
        event = events[-1]
        self.assertEqual(event["details"]["reason"], "usd_field_missing")
        self.assertEqual(event["details"]["stage"], "parse_response")
        self.assertIn("$.data.wallet:object", event["details"]["response_schema"])
        self.assertEqual(event["details"]["retry_risk"], "no_generation_submitted")
        text = json.dumps(events)
        for secret in (key, "Private Person", "private@example.org", "another-private-value"):
            self.assertNotIn(secret, text)
        self.assertNotIn("http_status", event["details"])

    def test_actual_http_status_is_recorded(self):
        events = []
        def request(url, *, on_response, **kwargs):
            on_response(200)
            return {"equivalent_in_usd": "3.25"}
        with patch("provider_balance.secure_json_request", request):
            self.assertEqual(check_provider_balance("piapi", "test-key", diagnostic=events.append),
                             "Баланс PiAPI: 3.25 USD")
        self.assertEqual(events[-1]["event"], "provider_balance_succeeded")
        self.assertEqual(events[-1]["details"]["http_status"], 200)
        self.assertEqual(events[0]["details"]["correlation_id"], events[-1]["details"]["correlation_id"])

    def test_http_error_keeps_status_and_drops_raw_message(self):
        events = []
        error = urllib.error.HTTPError("https://api.piapi.ai/account/info", 403, "private-api-key-value", {}, None)
        with patch("provider_balance.secure_json_request", side_effect=error):
            with self.assertRaises(ProviderBalanceError) as caught:
                check_provider_balance("piapi", "private-api-key-value", diagnostic=events.append)
        self.assertEqual(events[-1]["details"]["http_status"], 403)
        self.assertEqual(events[-1]["details"]["stage"], "http_response")
        self.assertNotIn("private-api-key-value", str(caught.exception) + json.dumps(events))

    def test_malformed_json_has_specific_safe_reason(self):
        events = []
        with patch("provider_balance.secure_json_request", side_effect=NetworkSecurityError("API returned malformed JSON")):
            with self.assertRaisesRegex(ProviderBalanceError, "JSON"):
                check_provider_balance("piapi", "dummy", diagnostic=events.append)
        self.assertEqual(events[-1]["details"]["reason"], "invalid_json")

    def test_bad_usd_value_is_not_called_missing(self):
        events = []
        with patch("provider_balance.secure_json_request", return_value={"equivalent_in_usd": "NaN"}):
            with self.assertRaises(ProviderBalanceError):
                check_provider_balance("piapi", "dummy", diagnostic=events.append)
        self.assertEqual(events[-1]["details"]["reason"], "usd_value_invalid")

    def test_broken_diagnostic_sink_does_not_change_balance(self):
        def broken(event):
            raise OSError("test failure")
        with patch("provider_balance.secure_json_request", return_value={"equivalent_in_usd": 0}):
            self.assertEqual(check_provider_balance("piapi", "dummy", diagnostic=broken), "Баланс PiAPI: 0.00 USD")

    def test_schema_is_bounded_for_large_response(self):
        self.assertLessEqual(len(balance_response_schema({"data": {"wallet": [{"data": {"wallet": {"data": 1}}}]} })), 480)

if __name__ == "__main__":
    unittest.main()
