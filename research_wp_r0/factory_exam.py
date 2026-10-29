"""Factory synthetic exam adapter. No providers, real receipts, or order IO.

Only cash-funded LONG lots, DNA exits or explicitly declared horizon exits and supplied
synthetic fill fractions are supported. Shared #108 accounting is authoritative.
This does not replace the historical replay or implement Core's Trader.
"""
from dataclasses import dataclass
import json
import math

from .strategy_definition import canonical, digest, identifier, integer, keys, number
from .strategy_dna_v2 import StrategyDNAV2, evaluate_synthetic, SyntheticRoleReport
from .synthetic_execution import account_long_prices


@dataclass(frozen=True)
class FrozenExam:
    payload: bytes

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return digest(self.spec)

    def to_json(self):
        return SyntheticRoleReport(self.payload).to_json()


def _freeze(value):
    raw = canonical(value)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Bounded exam payload required")
    return FrozenExam(raw)


def _check(obj, expected):
    if not isinstance(obj, FrozenExam) or obj.digest != expected:
        raise ValueError("Retained exam digest mismatch")


def freeze_manifest(dna, events):
    """Freeze externally enumerated slots BEFORE scanner/gate attrition.

    Features are evaluated by the accepted V2 function at each supplied cutoff.
    Quotes after cutoff are execution-only: never passed into decision/gate code.
    Missing externally scheduled slots are represented by features=None.
    """
    if not isinstance(dna, StrategyDNAV2) or type(events) is not list or not 1 <= len(events) <= 256:
        raise ValueError("Bounded explicit synthetic event universe required")
    rows, monitoring, seen, prices = [], [], set(), {}
    groups = {}
    for event in events:
        keys(event, "event_id cutoff_ms symbol venue features quotes fill_fraction regime protection")
        identifier(event["event_id"]); identifier(event["symbol"]); identifier(event["venue"])
        integer(event["cutoff_ms"], 0, 2**53-1)
        identity = (event["symbol"], event["venue"], event["cutoff_ms"])
        if event["event_id"] in seen or identity in seen:
            raise ValueError("Duplicate opportunity")
        seen.update((event["event_id"], identity))
        if event["features"] is not None:
            groups.setdefault(event["cutoff_ms"], []).append(dict(
                symbol=event["symbol"], venue=event["venue"], features=event["features"]))
    # Scanner capacity and ranking see the entire supplied cross-section.
    reports = {t: evaluate_synthetic(dna, assets, decision_cutoff_ms=t).spec for t, assets in groups.items()}
    for event in sorted(events, key=lambda e: (e["cutoff_ms"], e["symbol"], e["venue"])):
        cutoff = event["cutoff_ms"]
        core = reports[cutoff]["core"] if event["features"] is not None else None
        selected = decision = None
        if core is not None:
            index = next(i for i, x in enumerate(core["scanner"]) if
                         (x["symbol"], x["venue"]) == (event["symbol"], event["venue"]))
            selected, decision = core["scanner"][index], core["decisions"][index]
            monitoring.append(dict(event_id=event["event_id"], observation=reports[cutoff]["monitoring"][index]))
        else:
            monitoring.append(dict(event_id=event["event_id"], observation=None, reason="NOT_SUPPLIED"))
        if type(event["quotes"]) is not list or len(event["quotes"]) > 64:
            raise ValueError("Bounded execution quotes required")
        quotes, previous = [], cutoff
        for quote in event["quotes"]:
            keys(quote, "at_ms available_at_ms price")
            integer(quote["at_ms"], 0, 2**53-1); integer(quote["available_at_ms"], 0, 2**53-1)
            number(quote["price"], 0.0000000001, 1e9)
            if not previous < quote["at_ms"] or quote["available_at_ms"] < quote["at_ms"]:
                raise ValueError("Noncausal execution quote")
            key = (event["symbol"], event["venue"], quote["at_ms"])
            if key in prices and prices[key] != quote:
                raise ValueError("Contradictory shared market path")
            prices[key] = quote
            quotes.append(quote); previous = quote["at_ms"]
        fraction = event["fill_fraction"]
        if fraction is not None:
            number(fraction, 0, 1)
        regime = event["regime"]
        if regime is not None:
            keys(regime, "kind as_of_ms available_at_ms score")
            if regime["kind"] != "AS_OF_SYNTHETIC_SCORE":
                raise ValueError("Generator truth/oracle regimes forbidden")
            integer(regime["as_of_ms"], 0, cutoff)
            integer(regime["available_at_ms"], regime["as_of_ms"], cutoff)
            number(regime["score"], 0, 1)
        protection = event["protection"]
        if protection is not None:
            keys(protection, "available_at_ms covers_until_ms")
            integer(protection["available_at_ms"], 0, cutoff)
            integer(protection["covers_until_ms"], cutoff, 2**53-1)
        rows.append(dict(event_id=event["event_id"], symbol=event["symbol"], venue=event["venue"],
                         cutoff_ms=cutoff, scanner=selected, decision=decision, quotes=quotes,
                         fill_fraction=fraction, regime=regime, protection=protection))
    return _freeze(dict(schema="factory-ex-ante-manifest-1", scope="SYNTHETIC_OFFLINE_ONLY",
                        dna_digest=dna.digest, strategy_id=dna.spec["strategy_id"],
                        strategy_version=dna.spec["strategy_version"], provenance=dna.spec["provenance"],
                        rows=rows, monitoring=monitoring))


def _validate_config(config, first_cutoff_ms):
    """Shared versioned synthetic execution contract, not a research selector."""
    keys(config, "schema seed capital notional fee_bps spread_bps slippage_bps latency_ms holding_ms exit_policy protection_required regime_threshold regime_max_age_ms trial_id registered_at_ms parameter_count overlay")
    if config["schema"] != "factory-exam-protocol-1" or config["exit_policy"] != "DNA_EXIT_OR_NATIVE_HORIZON_LONG":
        raise ValueError("Explicit supported native exit contract required")
    integer(config["seed"], 0, 2**31-1); identifier(config["trial_id"])
    integer(config["parameter_count"], 0, 10000)
    integer(config["registered_at_ms"], 0, first_cutoff_ms)
    number(config["capital"], 1, 1e9); number(config["notional"], 0.01, config["capital"])
    for name in ("fee_bps", "spread_bps", "slippage_bps"):
        number(config[name], 0, 1000)
    integer(config["latency_ms"], 1, 86400000); integer(config["holding_ms"], 1, 86400000)
    integer(config["regime_max_age_ms"], 0, 86400000)
    number(config["regime_threshold"], 0, 1)
    if type(config["protection_required"]) is not bool:
        raise ValueError("Explicit strategy-specific protection requirement")
    overlay = config["overlay"]
    if overlay is not None:
        keys(overlay, "name version max_concurrent")
        if overlay["name"] != "MAX_CONCURRENT" or overlay["version"] != "1":
            raise ValueError("Exactly one opt-in supported overlay")
        integer(overlay["max_concurrent"], 1, 256)


def freeze_protocol(manifest, *, expected_manifest_digest, config):
    _check(manifest, expected_manifest_digest)
    _validate_config(config, manifest.spec["rows"][0]["cutoff_ms"])
    return _freeze(dict(manifest_digest=manifest.digest, config=config,
                        leverage=1, margin="CASH_ONLY", funding="NOT_APPLICABLE_SPOT_LONG",
                        seed_policy="RECORDED_NO_RANDOMNESS_EXPLICIT_FILL_FRACTIONS"))


def run_route(manifest, protocol, *, expected_manifest_digest, expected_protocol_digest, arm):
    """Chronological cash-funded simulation; one native fixed-horizon lot/slot.

    Missing fill evidence is UNKNOWN and halts simulation, not a favorable
    no-fill. Adverse execution assumptions are exactly shared #108 arithmetic.
    Quoted mid marks are sampled MTM, not an intrabar liquidation guarantee.
    """
    _check(manifest, expected_manifest_digest); _check(protocol, expected_protocol_digest)
    if protocol.spec["manifest_digest"] != manifest.digest or arm not in ("ALWAYS", "REGIME"):
        raise ValueError("Manifest/route mismatch")
    cfg, rows = protocol.spec["config"], manifest.spec["rows"]
    cash, peak, dd, halted = cfg["capital"], cfg["capital"], 0.0, False
    positions, marks, outcomes, exit_requests, ledger, timeline = {}, {}, {}, {}, [], []
    friction = cfg["slippage_bps"] + cfg["spread_bps"] / 2
    fee = cfg["fee_bps"] / 10000
    def append(at, kind, event_id, details):
        prior = ledger[-1]["digest"] if ledger else protocol.digest
        item = dict(at_ms=at, kind=kind, event_id=event_id, details=details, previous=prior)
        ledger.append(dict(item, digest=digest(item)))
    def finish(row, status, reason, net=None, unit=None, gross=None):
        outcomes[row["event_id"]] = dict(event_id=row["event_id"],
            family_id=None if row["decision"] is None else row["decision"]["opportunity_family_id"],
            source_fingerprint=digest(row), status=status, reason=reason,
            net_quote=net, net_per_requested_notional=None if net is None else net/cfg["notional"],
            executed_net_return=unit, gross_quote=gross)
    by_id = {row["event_id"]: row for row in rows}
    def close_lot(eid, quote, at, reason, trigger):
        nonlocal cash, halted
        row = by_id[eid]
        if quote is None:
            finish(row, "UNKNOWN", "UNOBSERVED_NATIVE_EXIT"); halted = True
            return
        lot = positions.pop(eid)
        account = account_long_prices(lot["entry_mid"], quote["price"], fee_bps=cfg["fee_bps"], slippage_bps=friction)
        credit = lot["quantity"] * account["exit_execution_price"] * (1-fee)
        cash += credit
        net = credit-lot["debit"]
        gross = lot["quantity"]*(quote["price"]-lot["entry_mid"])
        finish(row, "EXECUTED", reason, net, account["net_return"], gross)
        append(at, "SIMULATED_EXIT", eid, dict(trigger_event_id=trigger, credit=credit,
               net_quote=net, gross_quote=gross, cash=cash))
    for i, row in enumerate(rows):
        cutoff = row["cutoff_ms"]
        timeline.extend([(cutoff, 2, i, "DECISION", None),
                         (cutoff+cfg["latency_ms"], 1, i, "SIGNAL_EXIT", None),
                         (cutoff+cfg["latency_ms"], 3, i, "ENTRY", None),
                         (cutoff+cfg["latency_ms"]+cfg["holding_ms"], 1, i, "EXIT", None)])
        timeline.extend((q["at_ms"], 0, i, "MARK", q) for q in row["quotes"])
    for at, _, index, kind, quote in sorted(timeline, key=lambda x: x[:3]):
        row = rows[index]; eid = row["event_id"]; market = (row["symbol"], row["venue"])
        if halted:
            if eid not in outcomes:
                finish(row, "UNKNOWN", "HALTED_INCOMPLETE_EXECUTION")
            continue
        if kind == "MARK":
            if quote["available_at_ms"] == at:
                marks[market] = quote["price"]
            elif any(lot["market"] == market for lot in positions.values()):
                # Required supplied MTM evidence cannot silently become a stale
                # valuation while the report claims complete drawdown coverage.
                halted = True
                append(at, "HALT", eid, dict(reason="LATE_MARK_WITH_OPEN_EXPOSURE"))
        elif kind == "DECISION":
            decision = row["decision"]
            reason = None
            if decision is None:
                finish(row, "UNKNOWN", "NOT_SUPPLIED")
            elif decision["signal"] == "NOT_EVALUATED_SCANNER":
                reason = "SCANNER_EXCLUDED"
            elif decision["signal"] == "BLOCKED":
                finish(row, "UNKNOWN", "CRITICAL_UNAVAILABLE")
            elif decision["signal"] != "ENTRY_CONDITION_MET":
                reason = decision["signal"]
                if reason == "EXIT_CONDITION_MET":
                    exit_requests[eid] = [pid for pid, lot in positions.items() if lot["market"] == market]
            elif arm == "REGIME":
                reg = row["regime"]
                if reg is None or at-reg["as_of_ms"] > cfg["regime_max_age_ms"]:
                    finish(row, "UNKNOWN", "REGIME_UNKNOWN_OR_STALE")
                elif reg["score"] < cfg["regime_threshold"]:
                    reason = "REGIME_ABSTAIN"
            if reason:
                finish(row, "ZERO_EXPOSURE", reason, 0.0, gross=0.0)
            append(at, "DECISION", eid, dict(reason=reason, source_fingerprint=digest(row)))
        elif kind == "SIGNAL_EXIT" and eid in exit_requests:
            q = next((q for q in row["quotes"] if q["at_ms"] == at and q["available_at_ms"] == at), None)
            for pid in exit_requests[eid]:
                if pid in positions:
                    close_lot(pid, q, at, "SYNTHETIC_DNA_EXIT", eid)
        elif kind == "ENTRY" and eid not in outcomes:
            q = next((q for q in row["quotes"] if q["at_ms"] == at and q["available_at_ms"] == at), None)
            protect = row["protection"]
            if cfg["protection_required"] and (protect is None or protect["covers_until_ms"] < at+cfg["holding_ms"]):
                finish(row, "ZERO_EXPOSURE", "REQUIRED_PROTECTION_UNAVAILABLE", 0.0, gross=0.0)
            elif cfg["overlay"] and len(positions) >= cfg["overlay"]["max_concurrent"]:
                finish(row, "ZERO_EXPOSURE", "OVERLAY_CAPACITY", 0.0, gross=0.0)
            elif q is None or row["fill_fraction"] is None:
                finish(row, "UNKNOWN", "UNOBSERVED_FILL"); halted = True
            elif row["fill_fraction"] == 0:
                finish(row, "NO_FILL", "EXPLICIT_SYNTHETIC_NO_FILL", 0.0, gross=0.0)
            else:
                account = account_long_prices(q["price"], q["price"], fee_bps=cfg["fee_bps"], slippage_bps=friction)
                entry = account["entry_execution_price"]
                qty = cfg["notional"] * row["fill_fraction"] / q["price"]
                debit = qty * entry * (1+fee)
                if debit > cash:
                    finish(row, "ZERO_EXPOSURE", "CASH_BUDGET_DENIED", 0.0, gross=0.0)
                else:
                    cash -= debit
                    positions[eid] = dict(quantity=qty, entry_mid=q["price"], debit=debit, market=market)
                    append(at, "SIMULATED_ENTRY", eid, dict(quantity=qty, price=entry, debit=debit, cash=cash))
        elif kind == "EXIT" and eid in positions:
            q = next((q for q in row["quotes"] if q["at_ms"] == at and q["available_at_ms"] == at), None)
            close_lot(eid, q, at, "SYNTHETIC_FIXED_HORIZON", eid)
        if not halted:
            equity = cash + math.fsum(lot["quantity"]*marks[lot["market"]] for lot in positions.values())
            if cash < 0 or not math.isfinite(equity):
                raise ValueError("Corrupt synthetic account")
            peak = max(peak, equity); dd = max(dd, (peak-equity)/peak)
            append(at, "EQUITY", eid, dict(cash=cash, marked_equity=equity, open_lots=len(positions)))
    for row in rows:
        if row["event_id"] not in outcomes:
            finish(row, "UNKNOWN", "UNRESOLVED")
    unknown = sum(o["net_quote"] is None for o in outcomes.values())
    return _freeze(dict(schema="factory-route-1", arm=arm, manifest_digest=manifest.digest,
        protocol_digest=protocol.digest, outcomes=[outcomes[r["event_id"]] for r in rows],
        ledger=ledger, ledger_head=ledger[-1]["digest"] if ledger else protocol.digest,
        assumptions=cfg, window=dict(first_cutoff_ms=rows[0]["cutoff_ms"], last_cutoff_ms=rows[-1]["cutoff_ms"],
            final_native_exit_ms=rows[-1]["cutoff_ms"]+cfg["latency_ms"]+cfg["holding_ms"]),
        portfolio=dict(currency="SYNTHETIC_QUOTE_UNITS", initial_capital=cfg["capital"], final_equity=None if halted or positions else cash,
            net_quote=None if halted or positions else cash-cfg["capital"],
            sampled_mtm_drawdown_fraction=dd, drawdown_complete=not halted,
            unknown_opportunities=unknown, halted=halted), execution="SYNTHETIC_ONLY_NO_ORDER_IO"))


def replay_route(manifest, protocol, receipt, *, arm):
    """Recompute hash chain AND accounting; a self-rehashed corrupt ledger fails."""
    actual = run_route(manifest, protocol, expected_manifest_digest=manifest.digest,
                       expected_protocol_digest=protocol.digest, arm=arm)
    if not isinstance(receipt, FrozenExam) or receipt.payload != actual.payload:
        raise ValueError("Corrupt/non-deterministic route receipt")
    return actual


def _comparison_input(receipt):
    """Refuse inconsistent claims at the actual public aggregation boundary.

    Structural validation is not replay, independent custody or empirical
    admission. Authenticity still requires replay_route and retained inputs.
    """
    if not isinstance(receipt, FrozenExam):
        raise ValueError("Frozen synthetic route required")
    spec = receipt.spec
    keys(spec, "schema arm manifest_digest protocol_digest outcomes ledger ledger_head assumptions window portfolio execution")
    if (spec["schema"] != "factory-route-1" or spec["arm"] not in ("ALWAYS", "REGIME")
            or spec["execution"] != "SYNTHETIC_ONLY_NO_ORDER_IO"):
        raise ValueError("Unsupported synthetic route claims")
    keys(spec["window"], "first_cutoff_ms last_cutoff_ms final_native_exit_ms")
    _validate_config(spec["assumptions"], spec["window"]["first_cutoff_ms"])
    rows = spec["outcomes"]
    if type(rows) is not list or not 1 <= len(rows) <= 256:
        raise ValueError("Scheduled opportunity inventory required")
    ids = set()
    for row in rows:
        keys(row, "event_id family_id source_fingerprint status reason net_quote net_per_requested_notional executed_net_return gross_quote")
        identifier(row["event_id"])
        if row["event_id"] in ids:
            raise ValueError("Duplicate opportunity denominator")
        ids.add(row["event_id"])
        status = row["status"]
        values = [row[k] for k in ("net_quote", "net_per_requested_notional", "gross_quote")]
        if status == "UNKNOWN":
            if any(v is not None for v in values) or row["executed_net_return"] is not None:
                raise ValueError("UNKNOWN cannot be zero-filled or scored")
        elif status in ("NO_FILL", "ZERO_EXPOSURE"):
            if any(type(v) not in (int, float) or v != 0 for v in values) or row["executed_net_return"] is not None:
                raise ValueError("Unexecuted exposure cannot claim a conditional executed return")
            if status == "NO_FILL" and row["reason"] != "EXPLICIT_SYNTHETIC_NO_FILL":
                raise ValueError("No-fill requires explicit synthetic evidence")
        elif status == "EXECUTED":
            for value in values + [row["executed_net_return"]]:
                number(value)
            expected = row["net_quote"] / spec["assumptions"]["notional"]
            if not math.isclose(row["net_per_requested_notional"], expected, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("Requested-notional estimand mismatch")
        else:
            raise ValueError("Unknown outcome state")
    portfolio = spec["portfolio"]
    keys(portfolio, "currency initial_capital final_equity net_quote sampled_mtm_drawdown_fraction drawdown_complete unknown_opportunities halted")
    unknown = sum(row["status"] == "UNKNOWN" for row in rows)
    if (type(portfolio["unknown_opportunities"]) is not int
            or portfolio["unknown_opportunities"] != unknown
            or type(portfolio["drawdown_complete"]) is not bool
            or type(portfolio["halted"]) is not bool
            or portfolio["drawdown_complete"] != (not portfolio["halted"])
            or portfolio["currency"] != "SYNTHETIC_QUOTE_UNITS"):
        raise ValueError("Inconsistent coverage/denominator claims")
    number(portfolio["sampled_mtm_drawdown_fraction"], 0, 1)
    if portfolio["halted"] and (portfolio["net_quote"] is not None or portfolio["final_equity"] is not None):
        raise ValueError("Halted execution cannot claim complete portfolio outcome")
    return spec


def compare_routes(left, right, *, sensitivity=False):
    """Keep universe policy mean separate from conditional both-executed mean.

    Missing outcomes are never zero-filled. Universe mean is null unless all
    slots are known. Conditional subset is explicitly selection-sensitive.
    """
    a, b = _comparison_input(left), _comparison_input(right)
    if a["manifest_digest"] != b["manifest_digest"]:
        raise ValueError("Family identity alone is insufficient: different source manifest")
    controlled = ("capital", "notional", "fee_bps", "spread_bps", "slippage_bps", "latency_ms", "holding_ms", "exit_policy", "protection_required", "overlay")
    differences = [k for k in controlled if a["assumptions"][k] != b["assumptions"][k]]
    policy_fields = ("regime_threshold", "regime_max_age_ms")
    changed_policy = [k for k in policy_fields if a["assumptions"][k] != b["assumptions"][k]]
    if (differences or changed_policy) and not sensitivity:
        raise ValueError("Unmatched execution or REGIME policy assumptions; explicit sensitivity required")
    if len(a["outcomes"]) != len(b["outcomes"]):
        raise ValueError("Opportunity denominator mismatch")
    matched = []
    for x, y in zip(a["outcomes"], b["outcomes"]):
        if any(x[k] != y[k] for k in ("event_id", "family_id", "source_fingerprint")):
            raise ValueError("False opportunity match")
        if x["status"] == y["status"] == "EXECUTED":
            matched.append(y["executed_net_return"]-x["executed_net_return"])
    def arm_summary(spec):
        rows = spec["outcomes"]
        vals = [x["net_per_requested_notional"] for x in rows if x["net_per_requested_notional"] is not None]
        counts = {}
        for x in rows:
            counts[x["reason"]] = counts.get(x["reason"], 0)+1
        return dict(scheduled=len(rows), known=len(vals), unknown=len(rows)-len(vals), attrition=counts,
            executed=sum(x["status"]=="EXECUTED" for x in rows),
            observed_gross_quote=math.fsum(x["gross_quote"] for x in rows if x["gross_quote"] is not None),
            observed_net_quote=math.fsum(x["net_quote"] for x in rows if x["net_quote"] is not None),
            ex_ante_policy_mean_per_requested_notional=math.fsum(vals)/len(rows) if len(vals)==len(rows) else None,
            observed_sum_per_requested_notional=math.fsum(vals), portfolio=spec["portfolio"])
    result = dict(schema="factory-comparison-1", manifest_digest=a["manifest_digest"],
        left_protocol=a["protocol_digest"], right_protocol=b["protocol_digest"],
        left=arm_summary(a), right=arm_summary(b),
        conditional_both_executed_count=len(matched),
        conditional_both_executed_mean_net_return_lift=math.fsum(matched)/len(matched) if matched else None,
        conditional_selection_sensitive=True, inference="DESCRIPTIVE_SYNTHETIC_NO_P_VALUES_NO_PROMOTION",
        comparison_kind="SENSITIVITY" if sensitivity else "MATCHED_ASSUMPTIONS",
        changed_execution_assumptions=differences,
        oos="NOT_ACCESSED", independent_custody="NOT_VERIFIED")
    if changed_policy:
        result["comparison_kind"] = "POLICY_SENSITIVITY"
        result["changed_policy_parameters"] = changed_policy
    return _freeze(result)
