import unittest
from aql.utc_evidence import ClockSample, assess

def sample(**overrides):
    args = dict(monotonic_ns=1000000000, wall_utc_ms=1000,
                source="time.cloudflare.com", offset_ms=2.6,
                network_uncertainty_ms=10.0, root_dispersion_ms=7761.8,
                ttl_ms=60000, synchronized=True)
    args.update(overrides)
    return ClockSample(**args)

class TestUtcEvidence(unittest.TestCase):
    def test_large_root_dispersion_not_millisecond_proof(self):
        self.assertEqual("UNKNOWN", assess(sample(), 2000000000, 100)["status"])

    def test_valid_sample_still_not_attestation(self):
        result = assess(sample(root_dispersion_ms=10), 2000000000, 100)
        self.assertEqual("UTC_DIAGNOSTIC_BOUNDED_NOT_ATTESTED", result["status"])

    def test_expired_and_monotonic_reset(self):
        self.assertEqual("UNKNOWN", assess(sample(ttl_ms=10), 2000000000, 100)["status"])
        self.assertEqual("UNKNOWN", assess(sample(), 0, 100)["status"])

    def test_unsynchronized_and_invalid_values(self):
        self.assertEqual("UNKNOWN", assess(sample(synchronized=False), 2000000000, 100)["status"])
        self.assertEqual("UNKNOWN", assess(sample(offset_ms=float("nan")), 2000000000, 100)["status"])

if __name__ == "__main__":
    unittest.main()
