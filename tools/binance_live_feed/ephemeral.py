"""Bounded in-memory validation and aggregate timing for the one-shot pilot."""
from collections import Counter

from tools.binance_live_feed.feed import canonical, check_sequence, hash_bytes, ms, need, normalize
from tools.binance_live_feed.simulation import distribution

MODE = "EPHEMERAL_RESEARCH"
CUSTODY_STATUS = "RAW_CUSTODY_NOT_AVAILABLE"
SERIES = ("trade_latency", "trade_interarrival", "bbo_interarrival",
          "bbo_commit_age", "final_1m", "final_15m", "commit")


class EphemeralFeed:
    """Session sink. Holds fixed-size fingerprints and timing, never raw frames."""

    def __init__(self, max_rows=4096):
        need(type(max_rows) is int and 1 <= max_rows <= 4096, "MEMORY_BOUND")
        self.max_rows = max_rows
        self.identities = {}
        self.last = {}
        self.samples = {key: [] for key in SERIES}
        self.counts = Counter()
        self.enabled = False
        self.started = False
        self.last_receive = 0

    def start(self, now):
        need(not self.started, "EPHEMERAL_RECONNECT_REQUIRES_NEW_AUTHORIZATION")
        self.last_receive = ms(now)
        self.started = self.enabled = True

    def stop(self, now):
        self.enabled = False

    def ingest(self, raw, received, processing_clock):
        record = normalize(raw, received)
        need(self.enabled and received >= self.last_receive, "EPHEMERAL_CLOCK_OR_SESSION")
        channel = record["channel"]
        key = (channel, record["key"])
        material = record["material"]
        fingerprint = hash_bytes(canonical(material))
        if key in self.identities:
            need(self.identities[key] == fingerprint, "REVISION_QUARANTINE")
            return "DUPLICATE"
        need(len(self.identities) < self.max_rows, "EPHEMERAL_BACKPRESSURE")
        previous = self.last.get(channel)
        if previous is not None:
            check_sequence(record, previous)
        processed = ms(processing_clock())
        need(processed >= received, "PROCESSING_CLOCK_REGRESSION")
        if channel in ("trade", "bbo") and previous is not None:
            self.samples[channel + "_interarrival"].append(received - previous["receive_ms"])
        if channel == "trade":
            self.samples["trade_latency"].append(received - record["event_ms"])
        elif channel == "bbo":
            self.samples["bbo_commit_age"].append(processed - received)
        elif channel in ("1m", "15m"):
            self.samples["final_" + channel].append(received - material["end_ms_exclusive"])
        self.samples["commit"].append(processed - received)
        self.identities[key] = fingerprint
        self.last[channel] = {
            "receive_ms": received, "sequence": record["sequence"],
            "material": {k: material[k] for k in ("open_ms", "end_ms_exclusive") if k in material},
        }
        self.last_receive = received
        self.counts[channel] += 1
        return "STORED"

    def metrics(self):
        return {key: distribution(values) for key, values in self.samples.items()}

    def blocked(self, reason):
        return self.read(None)

    def read(self, cutoff):
        return {"status": "BLOCKED", "reason": CUSTODY_STATUS,
                "core": CUSTODY_STATUS, "scanner": CUSTODY_STATUS,
                "discoverer": CUSTODY_STATUS, "factory": "EVALUATION_PENDING",
                "trading_authority": "NONE"}

    def dispose(self):
        self.stop(None)
        self.identities.clear()
        self.last.clear()
        self.counts.clear()
        for values in self.samples.values():
            values.clear()
