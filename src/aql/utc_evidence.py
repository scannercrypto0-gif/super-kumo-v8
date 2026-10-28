"""Conservative, expiring diagnostic UTC observations; not time attestation."""
from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ClockSample:
    monotonic_ns: int
    wall_utc_ms: int
    source: str
    offset_ms: float
    network_uncertainty_ms: float
    root_dispersion_ms: float
    ttl_ms: int
    synchronized: bool

def assess(sample, now_monotonic_ns, max_uncertainty_ms):
    unknown = {"status": "UNKNOWN"}
    if not isinstance(sample, ClockSample):
        return unknown
    if type(now_monotonic_ns) is not int or type(sample.monotonic_ns) is not int:
        return unknown
    if type(sample.wall_utc_ms) is not int or type(sample.ttl_ms) is not int:
        return unknown
    if sample.ttl_ms <= 0 or not sample.source or sample.synchronized is not True:
        return unknown
    age = now_monotonic_ns - sample.monotonic_ns
    if age < 0 or age > sample.ttl_ms * 1000000:
        return unknown
    nums = (sample.offset_ms, sample.network_uncertainty_ms,
            sample.root_dispersion_ms, max_uncertainty_ms)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in nums):
        return unknown
    if min(sample.network_uncertainty_ms, sample.root_dispersion_ms) < 0 or max_uncertainty_ms <= 0:
        return unknown
    bound = abs(sample.offset_ms) + sample.network_uncertainty_ms + sample.root_dispersion_ms
    if bound > max_uncertainty_ms:
        return unknown
    return {"status": "UTC_DIAGNOSTIC_BOUNDED_NOT_ATTESTED",
            "uncertainty_ms": bound, "source": sample.source}
