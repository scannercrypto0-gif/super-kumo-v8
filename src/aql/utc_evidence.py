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
    roundtrip_ms: float | None = None
    root_delay_ms: float | None = None
    request_ntp_hex: str | None = None
    response_ntp_hex: str | None = None

def assess(sample, now_monotonic_ns, max_uncertainty_ms, *, now_wall_ms=None):
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
    if now_wall_ms is not None:
        if type(now_wall_ms) is not int:
            return unknown
        # A wall step invalidates the diagnostic rather than tightening its bound.
        if abs((now_wall_ms - sample.wall_utc_ms) - age / 1_000_000) > 10:
            return unknown
    bound = abs(sample.offset_ms) + sample.network_uncertainty_ms + sample.root_dispersion_ms
    if bound > max_uncertainty_ms:
        return unknown
    return {"status": "UTC_DIAGNOSTIC_BOUNDED_NOT_ATTESTED",
            "uncertainty_ms": bound, "source": sample.source}


def measure_sntp(source="time.cloudflare.com", *, ttl_ms=60000, timeout=2):
    """Unauthenticated NTP diagnostic; never independent UTC attestation.

    Root dispersion + root delay/2 + measured RTT/2 + absolute offset is
    conservative diagnostic accounting, not a guaranteed network error bound.
    Measurement occurs in this process, so persisted monotonic values are not
    reused across restart. Unsupported/unsynchronized responses fail closed.
    """
    import socket
    import struct
    import time
    epoch = 2208988800
    def ntp_time(value):
        whole = int(value) + epoch
        return struct.pack("!II", whole, int((value % 1) * 2**32))
    def seconds(raw):
        whole, fraction = struct.unpack("!II", raw)
        return whole - epoch + fraction / 2**32
    t1 = time.time()
    mono1 = time.monotonic_ns()
    token = ntp_time(t1)
    request = bytes([0x23]) + bytes(39) + token
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.connect((source, 123))
        sock.send(request)
        response = sock.recv(512)
    mono4 = time.monotonic_ns()
    t4 = time.time()
    if (len(response) < 48 or response[0] >> 6 == 3 or
        response[0] & 7 != 4 or not 1 <= response[1] <= 15 or
        response[24:32] != token or response[40:48] == bytes(8)):
        raise ValueError("invalid or unsynchronized NTP response")
    elapsed = (mono4-mono1)/1e9
    if elapsed < 0 or abs((t4-t1)-elapsed) > .01:
        raise ValueError("wall clock stepped during measurement")
    t2, t3 = seconds(response[32:40]), seconds(response[40:48])
    if t3 < t2 or t3-t2 > elapsed + .001:
        raise ValueError("invalid NTP server processing time")
    root_delay = struct.unpack("!i", response[4:8])[0] / 65536
    root_dispersion = struct.unpack("!I", response[8:12])[0] / 65536
    return ClockSample(monotonic_ns=mono4, wall_utc_ms=int(t4*1000),
        source=source, offset_ms=((t2-t1)+(t3-t4))*500,
        network_uncertainty_ms=(elapsed+max(0, root_delay))*500,
        root_dispersion_ms=root_dispersion*1000, ttl_ms=ttl_ms, synchronized=True,
        roundtrip_ms=elapsed*1000, root_delay_ms=root_delay*1000,
        request_ntp_hex=request.hex(), response_ntp_hex=response.hex())
