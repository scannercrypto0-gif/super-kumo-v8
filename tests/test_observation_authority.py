import unittest
from aql.data_proof import ProofError
from aql.observation_authority import (
    AuthorityReceipt, validate_anchor, validate_utc_calibration,
    validate_coverage, observed_as_of)

class AuthorityGateTests(unittest.TestCase):
    def test_utc_unverified_fails(self):
        with self.assertRaises(ProofError):
            validate_utc_calibration(sample_wall_ms=1001,reference_utc_ms=1000,
                maximum_error_ms=10,observed_error_ms=1,
                independent_reference_verified=False)
    def test_utc_outside_bounds_fails(self):
        with self.assertRaises(ProofError):
            validate_utc_calibration(sample_wall_ms=1200,reference_utc_ms=1000,
                maximum_error_ms=10,observed_error_ms=1,
                independent_reference_verified=True)
    def test_utc_bounded(self):
        self.assertEqual("UTC_BOUNDED",validate_utc_calibration(
            sample_wall_ms=1001,reference_utc_ms=1000,maximum_error_ms=10,
            observed_error_ms=1,independent_reference_verified=True)["status"])
    def test_gap_must_be_explicit(self):
        with self.assertRaises(ProofError):
            validate_coverage(expected_slots=[1,2],observed_slots=[1],
                              explicit_gaps=[],calibrated=True)
        self.assertEqual("UNKNOWN_GAPS",validate_coverage(
            expected_slots=[1,2],observed_slots=[1],explicit_gaps=[2],calibrated=True))
    def test_no_coverage_from_uncalibrated_clock(self):
        with self.assertRaises(ProofError):
            validate_coverage(expected_slots=[1],observed_slots=[1],
                              explicit_gaps=[],calibrated=False)
    def test_untrusted_or_rollback_anchor_fails(self):
        receipt=AuthorityReceipt("a"*64,"external-1",1000,"remote","proof")
        bundle={"ledger_head":"b"*64}
        with self.assertRaises(ProofError):
            validate_anchor(bundle,receipt,trusted_anchor="remote",
                            verifier=lambda *_:True)
        with self.assertRaises(ProofError):
            validate_anchor({"ledger_head":"a"*64},receipt,trusted_anchor="remote",
                            verifier=lambda *_:False)
    def test_missing_independent_verifier_fails(self):
        receipt=AuthorityReceipt("a"*64,"external-1",1000,"remote","proof")
        with self.assertRaises(ProofError):
            validate_anchor({"ledger_head":"a"*64},receipt,trusted_anchor="remote",
                            verifier=None)
if __name__=="__main__":
    unittest.main()
