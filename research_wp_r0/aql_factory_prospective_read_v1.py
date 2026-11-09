"""Factory read-only census and horizon linkage. No fills or approval."""
from collections import Counter

from aql.observation.contracts import digest
from aql.observation.durable_bridge_v1 import require
from aql.observation.prospective import ProspectiveObserver


def read_prospective_research(observer, *, as_of_ms):
    require(isinstance(observer, ProspectiveObserver), "FACTORY_PROSPECTIVE_READER_REQUIRED")
    evidence = observer.verified_read(as_of_ms=as_of_ms)
    decisions = Counter()
    horizons = Counter()
    for row in evidence["rows"]:
        item = row["decision"]
        decisions[item["state"] if row["source_valid"] else "UNKNOWN"] += 1
        for horizon in row["horizons"]:
            horizons[f'{horizon["horizon_ms"]}:{horizon["state"]}'] += 1
    body = {
        "schema": "aql.factory.prospective-research-read.v1",
        "g2_sha256": evidence["sha256"], "evidence_mode": evidence["run"]["evidence_mode"],
        "as_of_ms": as_of_ms, "decision_counts": dict(decisions),
        "horizon_counts": dict(horizons), "trading_authority": "NONE",
        "secretary_enqueued": False, "orders_enabled": False,
    }
    return {**body, "sha256": digest(body)}
