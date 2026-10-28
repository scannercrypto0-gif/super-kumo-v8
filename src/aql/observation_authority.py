"""Independent observer authority gate; no issuer-publication claim.

The trusted anchor must come from a DIFFERENT host/account than the watcher.
UTC calibration is externally supplied and checked, never self-attested here.
"""
from dataclasses import dataclass
import hashlib
import json
from aql.data_proof import ProofError
from aql.binance_observer import verify_bundle

@dataclass(frozen=True)
class AuthorityReceipt:
    ledger_head: str
    anchor_id: str
    anchor_time_ms: int
    anchor_custodian: str
    anchor_proof: str

def validate_anchor(bundle, receipt, *, trusted_anchor, verifier):
    """Fail closed: verifier must validate independently fetched anchor bytes.

    verifier(trusted_anchor, receipt) is a trust-boundary dependency, not a
    watcher-provided boolean or a digest comparison alone.
    """
    if not isinstance(receipt, AuthorityReceipt):
        raise ProofError("missing independent custody receipt")
    if (not callable(verifier) or not trusted_anchor or
        not receipt.anchor_id or not receipt.anchor_custodian or
        not receipt.anchor_proof or type(receipt.anchor_time_ms) is not int):
        raise ProofError("missing trusted anchor verifier")
    if receipt.ledger_head != bundle.get("ledger_head"):
        raise ProofError("anchor head mismatch")
    if verifier(trusted_anchor, receipt) is not True:
        raise ProofError("independent custody unverified")
    return verify_bundle(bundle, receipt.ledger_head)

def validate_utc_calibration(*, sample_wall_ms, reference_utc_ms,
                             maximum_error_ms, observed_error_ms,
                             independent_reference_verified):
    """Return conservative wall-clock uncertainty, never provider publication."""
    values=(sample_wall_ms, reference_utc_ms, maximum_error_ms, observed_error_ms)
    if (any(type(x) is not int or x < 0 for x in values) or
        independent_reference_verified is not True or maximum_error_ms == 0 or
        observed_error_ms > maximum_error_ms or
        abs(sample_wall_ms-reference_utc_ms) > maximum_error_ms):
        raise ProofError("UTC calibration unverified")
    return {"status":"UTC_BOUNDED", "max_error_ms":maximum_error_ms,
            "reference_utc_ms":reference_utc_ms}

def validate_coverage(*, expected_slots, observed_slots, explicit_gaps,
                      calibrated):
    """A finite slot-set assertion; no assertion about revisions between polls."""
    if calibrated is not True:
        raise ProofError("coverage requires verified clock")
    expected=set(expected_slots)
    observed=set(observed_slots)
    gaps=set(explicit_gaps)
    if not expected or not observed.issubset(expected) or not gaps.issubset(expected):
        raise ProofError("invalid coverage universe")
    if observed & gaps or observed | gaps != expected:
        raise ProofError("unaccounted observation gap")
    return "UNKNOWN_GAPS" if gaps else "SLOT_COVERAGE_ONLY_NOT_REVISION_COMPLETE"

def observed_as_of(bundle, receipt, cutoff_ms, *, trusted_anchor, verifier,
                   calibrated=False, complete_coverage=False):
    """Verified custody does not promote observer receipt to real historical PIT."""
    versions=validate_anchor(bundle, receipt, trusted_anchor=trusted_anchor,
                             verifier=verifier)
    if type(cutoff_ms) is not int:
        raise ProofError("invalid cutoff")
    known=[v for v in versions if v.first_local_seen_ms <= cutoff_ms]
    return {"versions":tuple(known), "timing_class":"FIRST_INDEPENDENT_OBSERVED",
            "empirical_eligible":False, "real_pit_accepted":False,
            "status":"REVIEW_ONLY" if calibrated and complete_coverage else "UNKNOWN_CLOCK_OR_COVERAGE"}
