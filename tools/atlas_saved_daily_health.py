"""Read a sealed daily publisher health snapshot without loading batch databases."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

DAY_MS = 86_400_000
POLL_UTC_MS = 21_600_000
GRACE_MS = 30_000
STATES = {"WAIT_FOR_SOURCE", "RECENT_RESEARCH_RECEIPT", "LAST_TICK_STALE",
          "CADENCE_UNVERIFIED", "LOG_UNREADABLE", "NO_TICK_EVIDENCE", "LAST_TICK_FAILED",
          "LAST_TICK_INCOMPLETE", "LAST_TICK_RECEIPT_MISSING"}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def read_daily_health(path, expected_sha, as_of_ms):
    with path.open("rb") as stream:
        raw = stream.read(65_537)
    require(len(raw) <= 65_536 and sha256(raw).hexdigest() == expected_sha, "DAILY_HEALTH_PIN")
    health = json.loads(raw.decode("utf-8-sig"))
    require(isinstance(health, dict)
            and health.get("schema") == "aql.recurring-runtime.health.v1"
            and health.get("source_mode") == "AUTHORIZED_RETAINED_ARCHIVE"
            and health.get("source_cadence") == "DAILY_UTC"
            and health.get("freshness_limit_ms") == DAY_MS + GRACE_MS
            and health.get("market_feed_health") == "NOT_MEASURED"
            and health.get("trading_authority") == "NONE"
            and health.get("current_entry") == "NO_CURRENT_ENTRY", "DAILY_HEALTH_CONTRACT")
    observed, tick, next_check = (health.get(k) for k in
                                  ("observed_at_ms", "tick_age_ms", "next_check_ms"))
    require(type(observed) is type(as_of_ms) is int and 0 <= observed <= as_of_ms
            and (tick is None or type(tick) is int and 0 <= tick <= observed)
            and (next_check is None or type(next_check) is int and next_check > 0),
            "DAILY_HEALTH_CLOCK")
    snapshot_age = as_of_ms - observed
    age = None if tick is None else tick + snapshot_age
    freshness = "NOT_AVAILABLE" if age is None else "STALE" if age > DAY_MS + GRACE_MS else "RECENT"
    state = health.get("cycle_evidence")
    require(type(state) is str and state in STATES, "DAILY_HEALTH_STATE")
    if state == "RECENT_RESEARCH_RECEIPT" and freshness != "RECENT":
        state = "LAST_TICK_STALE" if freshness == "STALE" else "CADENCE_UNVERIFIED"
    if state == "WAIT_FOR_SOURCE" and (freshness == "STALE"
            or next_check is not None and as_of_ms > next_check + GRACE_MS):
        state, freshness = "LAST_TICK_STALE", "STALE"
    success = health.get("last_success")
    source_day = None
    source_freshness = "NOT_AVAILABLE"
    if success is not None:
        require(isinstance(success, dict), "DAILY_HEALTH_SUCCESS")
        source_day = success.get("source_day_ms")
        require(type(source_day) is int and source_day > 0 and source_day % DAY_MS == 0
                and source_day + DAY_MS <= observed, "DAILY_HEALTH_SOURCE_DAY")
        last_due = ((as_of_ms - POLL_UTC_MS) // DAY_MS - 1) * DAY_MS
        source_freshness = "STALE" if source_day < last_due else "LATEST_DUE_DAY_RECEIVED"
    return dict(schema="atlas.saved-daily-health.v1", health_file_sha256=expected_sha,
                cycle_evidence=state, tick_freshness=freshness, tick_age_at_report_ms=age,
                snapshot_age_ms=snapshot_age, next_check_ms=next_check, source_day_ms=source_day,
                source_freshness=source_freshness, trading_authority="NONE",
                current_entry="NO_CURRENT_ENTRY")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("sha256")
    parser.add_argument("as_of_ms", type=int)
    args = parser.parse_args()
    print(json.dumps(read_daily_health(args.snapshot, args.sha256, args.as_of_ms), sort_keys=True))
