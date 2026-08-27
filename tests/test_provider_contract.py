import unittest

from provider_contract import (
    MAX_PROVIDER_PAYLOAD_BYTES,
    ProviderContractError,
    ProviderTaskRequest,
)


class ProviderContractTests(unittest.TestCase):
    def test_request_contract_is_provider_neutral_and_json_safe(self):
        request = ProviderTaskRequest(
            provider_id="fal",
            operation="generation",
            model_id="fal-ai/flux/schnell",
            input_payload={"prompt": "a fox"},
            idempotency_key="clipart-123",
        )

        request.validate()
        self.assertEqual(request.to_dict()["provider_id"], "fal")

    def test_request_contract_rejects_invalid_identifiers_and_oversized_payloads(self):
        with self.assertRaises(ProviderContractError):
            ProviderTaskRequest("fal", "generation", "../secret", {}).validate()
        with self.assertRaises(ProviderContractError):
            ProviderTaskRequest(
                "fal",
                "generation",
                "fal-ai/model",
                {"prompt": "x" * MAX_PROVIDER_PAYLOAD_BYTES},
            ).validate()


if __name__ == "__main__":
    unittest.main()
