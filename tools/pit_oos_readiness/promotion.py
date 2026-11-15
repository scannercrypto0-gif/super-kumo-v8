"""Offline scientific and promotion preflight for a frozen delayed replay."""
import argparse
from datetime import date, timedelta
from pathlib import Path

from research_wp_r0.frozen_research_plan import verify_research_plan
from research_wp_r0.strategy_definition import canonical, load_json
from tools.pit_oos_readiness.proof import need, sha, verify_bundle

SPLITS = ("train", "embargo_1", "validation", "embargo_2", "holdout")
GRADES = ("SYNTHETIC_TESTED", "EXPLORATORY", "EVIDENCE_PENDING")
ARCHIVE = "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/15m/BTCUSDT-15m-{utc_date}.zip"
POLICY = {
    "RESEARCH_REVIEW": "REPORT_ONLY",
    "RESEARCH_TO_SHADOW": "QUALIFICATION_AND_OWNER_AUTHORITY_REQUIRED",
    "SHADOW_TO_PAPER": "QUALIFICATION_AND_OWNER_AUTHORITY_REQUIRED",
    "PAPER_TO_LIVE": "SEPARATE_OWNER_AUTHORIZATION_NO_AUTO_PROMOTION",
    "REMOVE_PAPER": "OWNER_APPROVAL_REQUIRED",
}


def verify_delayed_plan(plan_raw, protocol_raw, window_raw, plan_pin):
    plan = verify_research_plan(plan_raw, plan_pin)
    protocol = load_json(protocol_raw.decode("utf-8"))
    window = load_json(window_raw.decode("utf-8-sig"))
    need(canonical(protocol) == protocol_raw and plan["protocol_digest"] == sha(protocol_raw)
         and protocol["window_sha256"] == sha(window_raw), "PROTOCOL_OR_WINDOW_PIN")
    split = {name: window[name] for name in SPLITS}
    need(protocol["window"] == split and plan["split_digest"] == sha(canonical(split)),
         "SPLIT_PIN")
    need(protocol["schema"] == "aql.delayed-prospective-protocol.v1"
         and protocol["source"]["path_template"] == ARCHIVE
         and protocol["source"]["checksum_suffix"] == ".CHECKSUM"
         and plan["dataset_digest"] == sha(canonical(protocol["source"])), "SOURCE_PIN")
    need(window["venue"] == "Binance Spot" and window["symbol"] == "BTCUSDT"
         and window["interval"] == "15m"
         and plan["candidates"] == [{"candidate_id": "sma3-12-v1",
                                    "strategy_digest": protocol["strategy_sha256"]}]
         and window["strategy_sha256"] == protocol["strategy_sha256"]
         and plan["selection_rule"] == protocol["selection"]
         and plan["cost_model"] == protocol["cost_model"] and plan["metrics"] == protocol["metrics"]
         and plan["baseline_digest"] == sha(canonical(protocol["baseline"])), "FROZEN_DESIGN_PIN")
    need(window["independent_attestation"] == protocol["independent_attestation"] == "SKIPPED_BY_OWNER"
         and window["holdout_access"] == "SEALED_UNOPENED"
         and protocol["collection"] == "NOT_ACTIVATED", "EVIDENCE_BOUNDARY")
    dates = {name: tuple(date.fromisoformat(stamp[:10]) for stamp in split[name]) for name in SPLITS}
    need(all(split[name] == [day.isoformat() + "T00:00:00Z" for day in dates[name]]
             and len(dates[name]) == 2 and dates[name][0] < dates[name][1] for name in SPLITS)
         and all(dates[left][1] == dates[right][0] for left, right in zip(SPLITS, SPLITS[1:]))
         and all((dates[name][1] - dates[name][0]).days >= 3 for name in ("embargo_1", "embargo_2")),
         "SPLIT_GRID")
    inventory = []
    for partition in ("train", "validation"):
        first, end = dates[partition]
        for offset in range((end - first).days):
            day = first + timedelta(days=offset)
            url = ARCHIVE.format(utc_date=day.isoformat())
            inventory.append(dict(partition=partition, date=day.isoformat(), zip=url,
                                  checksum=url + ".CHECKSUM",
                                  expected_publication_utc_date=(day + timedelta(days=1)).isoformat()))
    return dict(plan_sha256=plan_pin, protocol_sha256=sha(protocol_raw), first_open_utc=split["train"][0],
                holdout="SEALED_UNOPENED", independent_attestation="SKIPPED_BY_OWNER",
                planned_archives=inventory, earliest_evaluation_utc_date=dates["validation"][1].isoformat())


def review(verified_plan, *, evidence_grade="EVIDENCE_PENDING", holdout_requested=False,
           action="RESEARCH_REVIEW"):
    need(not holdout_requested, "HOLDOUT_ACCESS_DENIED")
    need(evidence_grade in GRADES, "EVIDENCE_GRADE_DENIED")
    need(action in POLICY, "PROMOTION_ACTION_DENIED")
    return dict(**verified_plan, schema="aql.scientific-promotion.preflight.v1",
                evidence_grade=evidence_grade, scientific_status="REAL_PIT_OOS_BLOCKED",
                scientific_reason="INDEPENDENT_PIT_AND_AUDIT_EVIDENCE_REQUIRED",
                lab="NOT_AUTHORIZED", collection="NOT_ACTIVATED", trading_authority="NONE",
                requested_action=action, request_disposition=POLICY[action],
                state_changed=False, decisions=dict(POLICY))


def inspect_prospective_proof(bundle, trust, trust_pin, plan_raw):
    """Existing prospective proof format, separate from the delayed archive plan."""
    checked = verify_bundle(bundle, trust, trust_pin, plan_raw)
    return {**checked, "promotion": "BLOCKED", "audit": "NOT_REVIEWED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "protocol", "window"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--evidence-grade", choices=GRADES, default="EVIDENCE_PENDING")
    parser.add_argument("--action", choices=POLICY, default="RESEARCH_REVIEW")
    args = parser.parse_args()
    raw = []
    for path in (args.plan, args.protocol, args.window):
        with path.open("rb") as stream:
            value = stream.read(100_001)
        need(len(value) <= 100_000, "BOUNDED_INPUT")
        raw.append(value)
    result = review(verify_delayed_plan(*raw, args.plan_sha256),
                    evidence_grade=args.evidence_grade, action=args.action)
    print(canonical({**result, "sha256": sha(canonical(result))}).decode("utf-8"))
    return 0 if args.action == "RESEARCH_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
