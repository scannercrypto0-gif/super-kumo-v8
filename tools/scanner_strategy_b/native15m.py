"""Scanner B: native 15m TEST_ONLY compatibility, reuse Work #235 DNA/indicator semantics.

This is NOT a patch to frozen Scanner #227 or Work #235. A historical
RETROSPECTIVE source has no independently attested 2024 known-at and always
remains UNKNOWN. The only SELECTED state here is for explicitly synthetic,
sealed, offline TEST_ONLY source bytes, never an operational Scanner nomination.
"""
from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
import math

from research_wp_r0.strategy_definition import StrategyDefinition, number, integer
from research_wp_r0.strategy_dna_v2 import StrategyDNAV2, _read, _test_predicate, _channel, reference_digest
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from tools.strategy_service_offline.common import Frozen, BoundaryError, digest, decode, raw_sha, require
from tools.strategy_service_offline.screening import StrategyScreeningSpec, KERNELS, STATES

WIDTH_MS = 900_000
SCHEMA = "aql.scanner.strategy-native15m-test-only.v1"


def native_15m_policy(work235_spec_receipt):
    """Explicit new timeframe declaration over a validated Work235 policy.

    The retained Work policy may declare 5m/30m/etc; NO input bar is
    resampled/relabelled. A distinct config digest is issued for native 15m.
    """
    original = StrategyScreeningSpec.restore_spec(work235_spec_receipt)
    old = original.data
    require(old["scope"] == "TEST_ONLY_UNAPPROVED_POLICY"
            and old["paper_approval"] == "NOT_FOUND", "UNAPPROVED_POLICY_REQUIRED")
    result = {
        "schema": "aql.scanner.native15m-policy.v1",
        "work235_policy_receipt_sha256": original.sha256,
        "work235_config_digest": old["config_digest"],
        "definition": old["definition"],
        "dna": old["dna"],
        "strategy_id": old["strategy_id"],
        "strategy_version": old["strategy_version"],
        "market": old["market"],
        "source_policy_timeframe": old["timeframe"],
        "timeframe": "15m",
        "max_source_age_ms": old["max_source_age_ms"],
        "weighted_ranking": old["weighted_ranking"],
        "override_is_explicit": True,
        "evidence_class": "TEST_ONLY",
        "approved_paper_registry": "NOT_CONNECTED",
        "operational_work235_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "trading_authority": "NONE",
    }
    result["config_digest"] = digest(result)
    return Frozen.build(result)


def verify_policy(policy, work235_spec_receipt):
    item = Frozen.restore(policy)
    require(item.data == native_15m_policy(work235_spec_receipt).data,
            "NATIVE15M_POLICY_IDENTITY_OR_VERSION_DRIFT")
    return item


def _source_windows(raw, manifest, universe, cutoff):
    """One native 900000-ms grid per symbol; no partial salvage or fake PIT."""
    require(type(cutoff) is int and cutoff >= 0, "CUTOFF_TYPE")
    require(type(manifest) is dict and type(universe) is dict,
            "SOURCE_MANIFEST_AND_UNIVERSE")
    require(manifest.get("schema") == "aql.strategy-service.source.v1"
            and manifest.get("timeframe") == "15m"
            and universe.get("schema") == "aql.strategy-service.universe.v1"
            and manifest.get("cutoff_ms") == universe.get("cutoff_ms") == cutoff
            and universe.get("source_raw_sha256") == manifest.get("raw_sha256")
            and universe.get("count_unit") == "SYMBOL", "SOURCE_SCOPE_OR_TIMEFRAME")
    members = universe.get("members")
    require(type(members) is list and 0 < len(members) <= 256
            and all(type(x) is dict and type(x.get("symbol")) is str for x in members)
            and len({x["symbol"] for x in members}) == len(members),
            "UNIVERSE_DUPLICATES_OR_BUDGET")
    errors = {m["symbol"]: "SOURCE_NOT_ATTESTED" for m in members}
    # Historical ZIP known-at is not retrospectively reconstructed as PIT.
    if manifest.get("evidence_class") != "TEST_ONLY" or universe.get("evidence_class") != "TEST_ONLY":
        return {}, errors, "RETROSPECTIVE_KNOWN_AT_NOT_ATTESTED"
    if type(raw) is not bytes or raw_sha(raw) != manifest.get("raw_sha256"):
        return {}, errors, "SOURCE_BYTES_SHA_MISMATCH"
    try:
        obj = decode(raw)
        require(obj.get("schema") == "aql.strategy-service.synthetic-bars.v1"
                and obj.get("source_id") == manifest.get("source_id")
                and obj.get("generation_id") == manifest.get("generation_id"),
                "SYNTHETIC_SOURCE_IDENTITY")
        bars = obj["rows"]
        require(type(bars) is list and len(bars) <= 8192, "SOURCE_BAR_BUDGET")
        require(type(manifest.get("start_ms")) is int
                and type(manifest.get("end_exclusive_ms")) is int
                and manifest["start_ms"] % WIDTH_MS == 0
                and manifest["end_exclusive_ms"] > manifest["start_ms"]
                and manifest["end_exclusive_ms"] <= cutoff
                and (manifest["end_exclusive_ms"]-manifest["start_ms"]) % WIDTH_MS == 0,
                "DECLARED_15M_WINDOW")
    except (ValueError, KeyError, TypeError, AttributeError):
        return {}, errors, "SOURCE_ENCODING_OR_DECLARATION"
    bucket = {m["symbol"]: [] for m in members}
    for b in bars:
        if type(b) is not dict or b.get("symbol") not in bucket:
            return {}, errors, "FOREIGN_OR_INVALID_SOURCE_SYMBOL"
        bucket[b["symbol"]].append(b)
    ok = {}
    expected_count = (manifest["end_exclusive_ms"]-manifest["start_ms"]) // WIDTH_MS
    for symbol, rows in bucket.items():
        if len(rows) != expected_count:
            errors[symbol] = "INCOMPLETE_15M_WINDOW"
            continue
        previous = None
        reason = None
        for b in rows:
            opened = b.get("open_ms")
            closed = b.get("close_ms")
            available = b.get("available_ms")
            vals = [b.get(k) for k in ("open", "high", "low", "close", "volume")]
            if (b.get("symbol") != symbol or b.get("timeframe") != "15m"
                    or b.get("source_id") != manifest["source_id"]
                    or b.get("finalized") is not True):
                reason = "SOURCE_IDENTITY_TIMEFRAME_OR_FINALITY"
            elif (type(opened) is not int or type(closed) is not int
                  or type(available) is not int
                  or opened % WIDTH_MS or closed != opened+WIDTH_MS-1
                  or not closed < available <= cutoff
                  or opened != (manifest["start_ms"] if previous is None else previous+WIDTH_MS)):
                reason = "DUPLICATE_GAP_OR_PIT_UNKNOWN"
            elif (any(type(v) not in (int, float) or not math.isfinite(v) for v in vals)
                  or vals[2] <= 0 or vals[4] < 0
                  or not vals[2] <= vals[0] <= vals[1]
                  or not vals[2] <= vals[3] <= vals[1]):
                reason = "BAD_OHLCV"
            if reason:
                break
            previous = opened
        if reason:
            errors[symbol] = reason
        else:
            ok[symbol] = rows
            errors.pop(symbol, None)
    return ok, errors, "SYNTHETIC_TEST_ONLY_NATIVE_15M"


def _features(dna, rows, manifest, cutoff, cache):
    refs = {r["name"]: r for r in dna["indicators"]}
    evidence = {}
    for name, ref in refs.items():
        require(ref["indicator_id"] in KERNELS, "KERNEL_NOT_SUPPORTED")
        key = (manifest["raw_sha256"], rows[0]["symbol"], "15m",
               ref["indicator_id"], digest(ref["parameters"]))
        if key not in cache:
            ind = IndicatorRegistryV2().get(ref["indicator_id"], **ref["parameters"])
            typed = [SimpleNamespace(**r) for r in rows]
            if hasattr(ind, "_compute_values"):
                values = ind._compute_values([r["close"] for r in rows], typed)
                value = values[-1] if len(rows) > ind.min_warmup_bars and values else None
                mapped = {"value": value}
            else:
                values = ind._values(typed)
                last = values[-1][1] if values and values[-1][0] == len(rows)-1 else None
                mapped = (dict(zip(ind.output_fields, last)) if last is not None
                          else {key: None for key in ind.output_fields})
            for value in mapped.values():
                if value is not None:
                    number(value)
            cache[key] = mapped
        mapped = cache[key]
        evidence[name] = {
            "indicator_digest": reference_digest(ref),
            "source_kind": "SYNTHETIC",
            "source_id": manifest["source_id"],
            "source_generation_id": manifest["generation_id"],
            "original_source_sha256": manifest["raw_sha256"],
            "quality": "VALID" if all(v is not None for v in mapped.values()) else "MISSING",
            "is_final": True,
            "as_of_ms": rows[-1]["close_ms"],
            "observed_at_ms": rows[-1]["available_ms"],
            "available_at_ms": rows[-1]["available_ms"],
            "values": mapped,
        }
    def read(item):
        return _read(evidence, item, refs[item["reference"]], dna["provenance"], cutoff)
    filters = [read(x) for x in dna["scanner_profile"]["filters"]]
    rankings = [read(x) for x in dna["scanner_profile"]["ranking"]]
    if any(x["status"] != "AVAILABLE_SYNTHETIC" for x in filters+rankings):
        return "UNKNOWN", ["MISSING_STALE_OR_UNKNOWN_FEATURE"], evidence, None, []
    if not all(_test_predicate(rule, result) for rule, result in zip(dna["scanner_profile"]["filters"], filters)):
        return "REJECTED", ["STRATEGY_HARD_GATE"], evidence, None, []
    rank = [-r["value"] if t["direction"] == "DESC" else r["value"]
            for t, r in zip(dna["scanner_profile"]["ranking"], rankings)]
    return "SELECTED", [], evidence, None, rank


def scan_native15m(policies, work235_specs, raw, manifest, universe,
                   *, cutoff_ms, symbol_budget):
    """All strategy/symbol pairs counted; no consumer/secretary/Paper activation."""
    integer(symbol_budget, 1, 256)
    require(len(policies) == len(work235_specs) and 0 < len(policies) <= 16,
            "STRATEGY_SPEC_BUDGET")
    specs = [verify_policy(p, w) for p, w in zip(policies, work235_specs)]
    identities = [(s.data["strategy_id"], s.data["strategy_version"]) for s in specs]
    require(len(set(identities)) == len(identities), "DUPLICATE_STRATEGY")
    require(all(s.data["market"] == manifest.get("market") for s in specs),
            "STRATEGY_MARKET_SCOPE")
    windows, errors, source_status = _source_windows(raw, manifest, universe, cutoff_ms)
    ordered = sorted(universe["members"], key=lambda m: m["symbol"])
    selected = [
        m["symbol"] for m in ordered
        if m.get("eligible") is True
        and type(m.get("membership_available_ms")) is int
        and 0 <= m["membership_available_ms"] <= cutoff_ms
    ][:symbol_budget]
    run_id = digest({"schema": SCHEMA, "registry": [s.sha256 for s in specs],
                     "source": manifest, "universe": universe,
                     "cutoff_ms": cutoff_ms, "budget": symbol_budget})
    cache, sealed_rows = {}, []
    for s in sorted(specs, key=lambda x: x.data["strategy_id"]):
        policy = s.data
        dna = policy["dna"]["dna"]
        candidates = []
        strategy_rows = []
        for m in ordered:
            symbol = m["symbol"]
            state, reasons, features, score, rank = "UNKNOWN", [], {}, None, []
            if type(m.get("membership_available_ms")) is not int or not 0 <= m["membership_available_ms"] <= cutoff_ms:
                reasons = ["UNIVERSE_MEMBERSHIP_UNKNOWN"]
            elif m.get("eligible") is False:
                state, reasons = "INELIGIBLE", ["UNIVERSE_INELIGIBLE"]
            elif m.get("eligible") is None:
                reasons = ["UNIVERSE_ELIGIBILITY_UNKNOWN"]
            elif m.get("eligible") is not True:
                reasons = ["UNIVERSE_ELIGIBILITY_INVALID"]
            elif source_status != "SYNTHETIC_TEST_ONLY_NATIVE_15M":
                reasons = [source_status]
            elif symbol not in selected:
                state, reasons = "UNSCANNED", ["SYMBOL_BUDGET"]
            elif symbol in errors:
                reasons = [errors[symbol]]
            elif cutoff_ms - windows[symbol][-1]["close_ms"] - 1 > policy["max_source_age_ms"]:
                reasons = ["STALE_15M_WINDOW"]
            elif (symbol not in dna["scanner_profile"]["allowed_symbols"]
                  or policy["market"] not in dna["scanner_profile"]["allowed_venues"]):
                state, reasons = "INELIGIBLE", ["STRATEGY_SCOPE"]
            else:
                try:
                    state, reasons, features, score, rank = _features(
                        dna, windows[symbol], manifest, cutoff_ms, cache)
                except (ValueError, KeyError, TypeError, ArithmeticError):
                    state, reasons, features = "UNKNOWN", ["INDICATOR_OR_RULE_UNAVAILABLE"], {}
            row = {
                "schema": "aql.scanner.native15m-strategy-nomination.v1",
                "run_id": run_id, "strategy_id": policy["strategy_id"],
                "strategy_version": policy["strategy_version"],
                "config_digest": policy["config_digest"],
                "work235_config_digest": policy["work235_config_digest"],
                "strategy_definition_digest": policy["definition"]["digest"],
                "symbol": symbol, "timeframe": "15m", "market": policy["market"],
                "cutoff_ms": cutoff_ms,
                "source_raw_sha256": manifest["raw_sha256"],
                "source_manifest_sha256": digest(manifest),
                "universe_sha256": digest(universe),
                "feature_evidence": features,
                "feature_snapshot_sha256": digest(features),
                "status": state, "reason_codes": reasons,
                "strategy_screening_rank_score": score,
                "evidence_class": "TEST_ONLY" if source_status == "SYNTHETIC_TEST_ONLY_NATIVE_15M" else "RETROSPECTIVE_NON_PIT",
                "operational_scanner_status": "UNKNOWN",
                "work235_native_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
                "paper_execution": "NOT_ACTIVATED",
                "trading_authority": "NONE",
                "publishable": False, "delivery_authorized": False,
                "attempt_id": digest({"run": run_id, "strategy": policy["config_digest"], "symbol": symbol}),
            }
            strategy_rows.append(row)
            if state == "SELECTED":
                candidates.append((rank, symbol, row))
        candidates.sort(key=lambda x: (x[0], x[1]))
        for i, (_, _, row) in enumerate(candidates):
            if i >= dna["scanner_profile"]["max_candidates"]:
                row["status"] = "REJECTED"
                row["reason_codes"] = ["STRATEGY_CAPACITY_EXCLUDED"]
        count = Counter(x["status"] for x in strategy_rows)
        census = {name.lower(): count[name] for name in STATES}
        require(sum(census.values()) == len(ordered), "CENSUS_MISMATCH")
        for row in strategy_rows:
            row["strategy_census"] = census
            row["denominator"] = len(ordered)
            sealed_rows.append(Frozen.build(row).receipt())
    return Frozen.build({
        "schema": SCHEMA, "run_id": run_id, "nominations": sealed_rows,
        "source_status": source_status, "source_symbols_considered": len(selected),
        "unique_feature_computations": len(cache),
        "operational_scanner_status": "UNKNOWN",
        "work235_native_15m": "NOT_CONNECTED_15M_UNSUPPORTED",
        "secretary_delivery": "NOT_AUTHORIZED_BY_STRATEGY_ADAPTER",
        "discoverer_dependency": "OPTIONAL",
        "paper_execution": "NOT_ACTIVATED",
        "trading_authority": "NONE",
        "g0": "NOT_APPROVED",
    })


def safe_wait_for_paper(nomination_receipt, policy_receipt):
    """No auto-promotion even for SELECTED synthetic TEST_ONLY nominations."""
    n = Frozen.restore(nomination_receipt).data
    policy = Frozen.restore(policy_receipt).data
    require(n["schema"] == "aql.scanner.native15m-strategy-nomination.v1"
            and n["strategy_id"] == policy["strategy_id"]
            and n["strategy_version"] == policy["strategy_version"]
            and n["config_digest"] == policy["config_digest"],
            "STRATEGY_VERSION_CONFIG_MISMATCH")
    require(n["trading_authority"] == "NONE"
            and n["publishable"] is False
            and n["delivery_authorized"] is False
            and n["operational_scanner_status"] == "UNKNOWN"
            and n["feature_snapshot_sha256"] == digest(n["feature_evidence"]),
            "PAPER_AUTHORITY_OR_FEATURE_TAMPER")
    return Frozen.build({
        "schema": "aql.scanner.native15m-paper-boundary.v1",
        "nomination_sha256": Frozen.restore(nomination_receipt).sha256,
        "strategy_config_digest": policy["config_digest"],
        "decision": "WAIT", "consumer_status": "NOT_CONNECTED_15M_UNSUPPORTED",
        "paper_execution": "NOT_ACTIVATED", "trading_authority": "NONE",
        "orders_created": 0, "position_events": 0, "actual_fills": None,
    })
