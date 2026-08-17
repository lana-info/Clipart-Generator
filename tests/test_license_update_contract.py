import unittest
from datetime import datetime, timedelta, timezone

from license_update_contract import LicenseLifecycleState, LicenseUpdatePolicy, classify_failure


class LicenseUpdateContractTests(unittest.TestCase):
    def test_rotation_accepts_overlapping_trust_roots(self):
        policy = LicenseUpdatePolicy(accepted_key_ids=("license-v1", "license-v2"))
        self.assertTrue(policy.accepts_key("license-v1"))
        self.assertTrue(policy.accepts_key("license-v2"))
        self.assertFalse(policy.accepts_key("license-v0"))

    def test_clock_skew_and_failure_states_are_explicit(self):
        now = datetime.now(timezone.utc)
        policy = LicenseUpdatePolicy(clock_skew_seconds=60)
        self.assertTrue(policy.validate_timestamp(now, now=now))
        self.assertFalse(policy.validate_timestamp(now - timedelta(minutes=2), now=now))
        self.assertEqual(classify_failure(tampered=True), LicenseLifecycleState.TAMPERED)
        self.assertEqual(classify_failure(outage=True), LicenseLifecycleState.OUTAGE)
        self.assertEqual(classify_failure(revoked=True), LicenseLifecycleState.REVOKED)


if __name__ == "__main__":
    unittest.main()
