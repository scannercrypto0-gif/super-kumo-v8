"""Additive StrategyDNA V2: bounded SYNTHETIC role evaluation, no execution.

V1 definitions/AST/canonicalization are reused unchanged, never translated into
weighted scores. Inputs are supplied synthetic indicator observations, not
authenticated market/source receipts. No Core, provider, OOS or trading access.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import (
    StrategyDefinition, canonical, digest, identifier, integer, keys, load_json,
    number, _reference,
)


def _items(value, minimum=0, maximum=64):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError("Invalid bounded list")
    return value


def _unique(values, label):
    if len(set(values)) != len(values):
        raise ValueError("Duplicate " + label)


def _input(item, refs):
    identifier(item["reference"]); identifier(item["field"])
    if item["reference"] not in refs or item["field"] not in refs[item["reference"]]:
        raise ValueError("Unknown typed indicator reference/output")
    integer(item["max_age_ms"], 0, 2**53-1)


def _predicate(item, refs):
    keys(item, "rule_id reference field max_age_ms operator value")
    identifier(item["rule_id"])
    _input(item, refs)
    if item["operator"] not in ("gt", "ge", "lt", "le", "eq", "ne"):
        raise ValueError("Unsupported predicate")
    number(item["value"])


class _Frozen:
    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return hashlib.sha256(self.payload).hexdigest()


@dataclass(frozen=True, init=False)
class ScannerProfile(_Frozen):
    payload: bytes

    def __init__(self, value, *, references):
        keys(value, "profile_id version allowed_symbols allowed_venues filters ranking max_candidates tie_break")
        identifier(value["profile_id"]); integer(value["version"])
        for field in ("allowed_symbols", "allowed_venues"):
            values = _items(value[field], 1, 256)
            for name in values:
                identifier(name)
            _unique(values, field)
        integer(value["max_candidates"], 1, 256)
        if value["tie_break"] != "SYMBOL_VENUE_ASC":
            raise ValueError("Explicit deterministic tie break required")
        for item in _items(value["filters"], maximum=32):
            _predicate(item, references)
        _unique([x["rule_id"] for x in value["filters"]], "scanner rule")
        for item in _items(value["ranking"], maximum=8):
            keys(item, "reference field max_age_ms direction")
            _input(item, references)
            if item["direction"] not in ("ASC", "DESC"):
                raise ValueError("Invalid rank direction")
        _unique([(x["reference"], x["field"]) for x in value["ranking"]], "ranking input")
        object.__setattr__(self, "payload", canonical(value))


@dataclass(frozen=True, init=False)
class DecisionProfile(_Frozen):
    payload: bytes

    def __init__(self, value, *, references):
        keys(value, "profile_id version normalization conflict_policy entry exit")
        identifier(value["profile_id"]); integer(value["version"])
        if value["normalization"] != "POSITIVE_WEIGHTED_MEAN_CLAMPED_LINEAR_V1":
            raise ValueError("Unsupported explicit score normalization")
        if value["conflict_policy"] != "REJECT_AMBIGUOUS":
            raise ValueError("Ambiguous entry/exit must not select an implicit winner")
        for channel in ("entry", "exit"):
            part = value[channel]
            keys(part, "terms threshold mandatory")
            number(part["threshold"], 0, 1)
            terms = _items(part["terms"], 1, 32)
            for item in terms:
                keys(item, "term_id reference field max_age_ms weight lower upper direction")
                identifier(item["term_id"]); _input(item, references)
                number(item["weight"])
                number(item["lower"]); number(item["upper"])
                if (item["weight"] <= 0 or item["upper"] <= item["lower"]
                        or not math.isfinite(item["upper"] - item["lower"])):
                    raise ValueError("Positive weight and finite nonzero normalization range required")
                if item["direction"] not in ("HIGH", "LOW"):
                    raise ValueError("Unknown evidence direction")
            _unique([x["term_id"] for x in terms], "decision term")
            try:
                total = math.fsum(x["weight"] for x in terms)
            except OverflowError as error:
                raise ValueError("Weight sum overflow") from error
            if not math.isfinite(total) or any(x["weight"] / total == 0 for x in terms):
                raise ValueError("Unrepresentable normalized weights")
            for item in _items(part["mandatory"], maximum=32):
                _predicate(item, references)
            _unique([x["rule_id"] for x in part["mandatory"]], "mandatory rule")
        object.__setattr__(self, "payload", canonical(value))


@dataclass(frozen=True, init=False)
class MonitoringProfile(_Frozen):
    payload: bytes

    def __init__(self, value, *, references):
        keys(value, "profile_id version authority features")
        identifier(value["profile_id"]); integer(value["version"])
        if value["authority"] != "OBSERVE_ONLY":
            raise ValueError("Monitoring cannot gain decision or ranking authority")
        for item in _items(value["features"]):
            keys(item, "feature_id reference field max_age_ms")
            identifier(item["feature_id"]); _input(item, references)
        _unique([x["feature_id"] for x in value["features"]], "monitor feature")
        object.__setattr__(self, "payload", canonical(value))


def reference_digest(ref):
    return digest({key: ref[key] for key in ("indicator_id", "version", "parameters")})


def _critical_names(spec):
    scanner, decision = spec["scanner_profile"], spec["decision_profile"]
    items = scanner["filters"] + scanner["ranking"]
    for channel in ("entry", "exit"):
        items += decision[channel]["terms"] + decision[channel]["mandatory"]
    return {item["reference"] for item in items}


@dataclass(frozen=True, init=False)
class StrategyDNAV2(_Frozen):
    payload: bytes

    def __init__(self, spec, *, v1_definition, registry=None):
        if not isinstance(v1_definition, StrategyDefinition):
            raise ValueError("Actual immutable V1 reference required")
        registry = registry if registry is not None else IndicatorRegistryV2()
        StrategyDefinition(v1_definition.spec, registry=registry)
        keys(spec, "schema_version strategy_id strategy_version scope v1_digest v1_link_mode indicators scanner_profile decision_profile monitoring_profile provenance regime_policy execution")
        identifier(spec["strategy_id"]); identifier(spec["strategy_version"])
        if (spec["schema_version"] != "2" or spec["scope"] != "SYNTHETIC_RESEARCH_ONLY"
                or spec["v1_digest"] != v1_definition.digest
                or spec["v1_link_mode"] != "REFERENCE_ONLY_NO_AST_TRANSLATION"
                or spec["regime_policy"] != "DEFERRED_NOT_EVALUATED"
                or spec["execution"] != "DISABLED"):
            raise ValueError("Unsupported V2 scope, V1 binding, adapter or runtime authority")
        provenance = spec["provenance"]
        keys(provenance, "kind source_generation_id allowed_sources plan_id")
        if provenance["kind"] != "SYNTHETIC_NOT_AUTHENTICATED":
            raise ValueError("This slice cannot certify historical/PIT custody")
        identifier(provenance["source_generation_id"]); identifier(provenance["plan_id"])
        for source in _items(provenance["allowed_sources"], 1, 16):
            identifier(source)
        _unique(provenance["allowed_sources"], "source")
        refs = {}
        for ref in _items(spec["indicators"], 1, 64):
            fields = _reference(ref, registry)
            if ref["name"] in refs:
                raise ValueError("Duplicate reference name")
            refs[ref["name"]] = fields
        ScannerProfile(spec["scanner_profile"], references=refs)
        DecisionProfile(spec["decision_profile"], references=refs)
        MonitoringProfile(spec["monitoring_profile"], references=refs)
        used = _critical_names(spec) | {x["reference"] for x in spec["monitoring_profile"]["features"]}
        if used != set(refs):
            raise ValueError("Every reference must have an explicit supported role")
        raw = canonical(spec)
        if len(raw) > 100000:
            raise ValueError("V2 envelope exceeds bounded JSON size")
        object.__setattr__(self, "payload", raw)

    @property
    def scanner_profile(self):
        return ScannerProfile(self.spec["scanner_profile"], references=self._fields())

    @property
    def decision_profile(self):
        return DecisionProfile(self.spec["decision_profile"], references=self._fields())

    @property
    def monitoring_profile(self):
        return MonitoringProfile(self.spec["monitoring_profile"], references=self._fields())

    def _fields(self):
        registry = IndicatorRegistryV2()
        return {ref["name"]: _reference(ref, registry) for ref in self.spec["indicators"]}

    @property
    def decision_policy_digest(self):
        # Semantic noninterference commitment, NOT operational authorization.
        spec = self.spec
        names = _critical_names(spec)
        return digest(dict(v1_digest=spec["v1_digest"], scanner=spec["scanner_profile"],
                           decision=spec["decision_profile"], provenance=spec["provenance"],
                           indicators=[x for x in spec["indicators"] if x["name"] in names]))

    def to_json(self):
        return canonical({"dna": self.spec, "digest": self.digest}).decode("utf-8")

    @classmethod
    def from_json(cls, raw, *, v1_definition, expected_digest):
        value = load_json(raw)
        keys(value, "dna digest")
        obj = cls(value["dna"], v1_definition=v1_definition)
        if obj.digest != value["digest"] or obj.digest != expected_digest:
            raise ValueError("V2 differs from retained digest")
        return obj

    def revise(self, spec, *, v1_definition):
        obj = type(self)(spec, v1_definition=v1_definition)
        if spec["strategy_id"] != self.spec["strategy_id"]:
            raise ValueError("Revision must preserve strategy lineage")
        if obj.digest != self.digest and spec["strategy_version"] == self.spec["strategy_version"]:
            raise ValueError("Changed policy requires a NEW immutable version")
        return obj


def _stamp(value):
    return value if type(value) is int and 0 <= value <= 2**53-1 else None


def _read(features, item, ref, provenance, cutoff):
    """Freshness applies to as-of content, not merely recent arrival."""
    raw = features.get(item["reference"]) if type(features) is dict else None
    row = dict(reference=item["reference"], field=item["field"], value=None,
               as_of_ms=None, observed_at_ms=None, available_at_ms=None,
               source_id=None, status="MISSING", reason="NO_OBSERVATION")
    if raw is None:
        return row
    if type(raw) is not dict:
        return dict(row, status="UNVERIFIED", reason="MALFORMED_OBSERVATION")
    row.update({k: _stamp(raw.get(k)) for k in ("as_of_ms", "observed_at_ms", "available_at_ms")})
    row["source_id"] = raw.get("source_id") if type(raw.get("source_id")) is str else None
    quality = raw.get("quality")
    if quality in ("MISSING", "STALE", "LATE", "DROPPED", "UNVERIFIED", "NOT_APPLICABLE"):
        return dict(row, status=quality, reason="SOURCE_MARKED_" + quality)
    if (quality != "VALID" or raw.get("source_kind") != "SYNTHETIC"
            or raw.get("source_generation_id") != provenance["source_generation_id"]
            or raw.get("source_id") not in provenance["allowed_sources"]
            or raw.get("indicator_digest") != reference_digest(ref)
            or raw.get("is_final") is not True):
        return dict(row, status="UNVERIFIED", reason="IDENTITY_SOURCE_QUALITY_OR_FINALITY")
    asof, observed, available = (row[k] for k in ("as_of_ms", "observed_at_ms", "available_at_ms"))
    if None in (asof, observed, available) or not asof <= observed <= available:
        return dict(row, status="UNVERIFIED", reason="INVALID_TEMPORAL_ORDER")
    if available > cutoff:
        return dict(row, status="LATE", reason="NOT_AVAILABLE_AT_DECISION")
    if cutoff - asof > item["max_age_ms"]:
        return dict(row, status="STALE", reason="AS_OF_TOO_OLD")
    values = raw.get("values")
    value = values.get(item["field"]) if type(values) is dict else None
    try:
        number(value)
    except (ValueError, TypeError, OverflowError):
        return dict(row, status="UNVERIFIED", reason="INVALID_FINITE_VALUE")
    return dict(row, status="AVAILABLE_SYNTHETIC", reason=None, value=value)


def _test_predicate(rule, reading):
    if reading["status"] != "AVAILABLE_SYNTHETIC":
        return False
    left, right, op = reading["value"], rule["value"], rule["operator"]
    return {"gt": left > right, "ge": left >= right, "lt": left < right,
            "le": left <= right, "eq": left == right, "ne": left != right}[op]


def _channel(spec, read):
    total = math.fsum(t["weight"] for t in spec["terms"])
    terms, reasons = [], []
    for term in spec["terms"]:
        feature = read(term)
        value = feature["value"]
        normalized = contribution = None
        if feature["status"] == "AVAILABLE_SYNTHETIC":
            low, high = term["lower"], term["upper"]
            normalized = 0.0 if value <= low else 1.0 if value >= high else (value-low)/(high-low)
            if term["direction"] == "LOW":
                normalized = 1.0 - normalized
            contribution = normalized * (term["weight"]/total)
        else:
            reasons.append(term["term_id"] + ":" + feature["status"])
        terms.append(dict(term_id=term["term_id"], reading=feature, weight=term["weight"],
                          normalized_weight=term["weight"]/total,
                          normalized_value=normalized, contribution=contribution))
    mandatory = []
    for rule in spec["mandatory"]:
        feature = read(rule)
        passed = _test_predicate(rule, feature)
        mandatory.append(dict(rule_id=rule["rule_id"], reading=feature, passed=passed))
        if not passed:
            reasons.append(rule["rule_id"] + ":MANDATORY_NOT_SATISFIED")
    complete = all(t["contribution"] is not None for t in terms)
    score = math.fsum(t["contribution"] for t in terms) if complete else None
    return dict(score=score, threshold=spec["threshold"], terms=terms, mandatory=mandatory,
                eligible=not reasons and score >= spec["threshold"], reasons=reasons)


@dataclass(frozen=True)
class SyntheticRoleReport(_Frozen):
    payload: bytes

    @classmethod
    def from_json(cls, raw, *, expected_digest):
        value = load_json(raw)
        keys(value, "report digest")
        obj = cls(canonical(value["report"]))
        if obj.digest != value["digest"] or obj.digest != expected_digest:
            raise ValueError("Report differs from retained digest")
        return obj

    def to_json(self):
        return canonical({"report": self.spec, "digest": self.digest}).decode("utf-8")


def evaluate_synthetic(dna, assets, *, decision_cutoff_ms):
    """Pure supplied-fixture evaluation. No market scanner, fills or storage IO."""
    if not isinstance(dna, StrategyDNAV2):
        raise ValueError("Explicit V2 opt-in required")
    integer(decision_cutoff_ms, 0, 2**53-1)
    _items(assets, maximum=256)
    spec = dna.spec
    refs = {r["name"]: r for r in spec["indicators"]}
    scanner = spec["scanner_profile"]
    frames = []
    for asset in assets:
        keys(asset, "symbol venue features")
        identifier(asset["symbol"]); identifier(asset["venue"])
        frames.append(asset)
    _unique([(a["symbol"], a["venue"]) for a in frames], "asset")
    frames.sort(key=lambda a: (a["symbol"], a["venue"]))
    screens, eligible = [], []
    for asset in frames:
        def read(item):
            return _read(asset["features"], item, refs[item["reference"]], spec["provenance"], decision_cutoff_ms)
        reasons = []
        if asset["symbol"] not in scanner["allowed_symbols"]:
            reasons.append("SYMBOL_NOT_ALLOWED")
        if asset["venue"] not in scanner["allowed_venues"]:
            reasons.append("VENUE_NOT_ALLOWED")
        rules = []
        for rule in scanner["filters"]:
            feature = read(rule)
            passed = _test_predicate(rule, feature)
            rules.append(dict(rule_id=rule["rule_id"], reading=feature, passed=passed))
            if not passed:
                reasons.append(rule["rule_id"] + ":" + (feature["status"] if feature["reason"] else "FILTER_REJECTED"))
        rank = []
        for term in scanner["ranking"]:
            feature = read(term)
            rank.append(feature)
            if feature["status"] != "AVAILABLE_SYNTHETIC":
                reasons.append("RANK_INPUT:" + feature["status"])
        screen = dict(symbol=asset["symbol"], venue=asset["venue"], rules=rules,
                      rank_readings=rank, selected=False, rank=None, reasons=reasons)
        screens.append(screen)
        if not reasons:
            key = tuple((-r["value"] if t["direction"] == "DESC" else r["value"])
                        for r, t in zip(rank, scanner["ranking"]))
            eligible.append((key, asset["symbol"], asset["venue"], screen))
    eligible.sort(key=lambda x: (x[0], x[1], x[2]))
    for i, (_, _, _, screen) in enumerate(eligible, 1):
        screen["rank"] = i
        screen["selected"] = i <= scanner["max_candidates"]
        if not screen["selected"]:
            screen["reasons"].append("CAPACITY_EXCLUDED")
    decisions, monitoring = [], []
    for asset, screen in zip(frames, screens):
        def read(item):
            return _read(asset["features"], item, refs[item["reference"]], spec["provenance"], decision_cutoff_ms)
        identity = dict(scope="SYNTHETIC_DNA_V2", dna_digest=dna.digest,
                        symbol=asset["symbol"], venue=asset["venue"], cutoff=decision_cutoff_ms)
        opportunity_id = digest(identity)  # NOT a Core operational candidate ID
        # Comparison identity is deliberately independent of monitor-only revisions.
        # It is synthetic research lineage, not an operational/Core identifier.
        opportunity_family_id = digest(dict(
            schema="synthetic-opportunity-family-1",
            strategy_id=spec["strategy_id"],
            decision_policy_digest=dna.decision_policy_digest,
            source_generation_id=spec["provenance"]["source_generation_id"],
            plan_id=spec["provenance"]["plan_id"],
            symbol=asset["symbol"], venue=asset["venue"], cutoff=decision_cutoff_ms))
        if screen["selected"]:
            entry = _channel(spec["decision_profile"]["entry"], read)
            exit_value = _channel(spec["decision_profile"]["exit"], read)
            if entry["eligible"] and exit_value["eligible"]:
                signal = "AMBIGUOUS_REJECTED"
            elif entry["eligible"]:
                signal = "ENTRY_CONDITION_MET"
            elif exit_value["eligible"]:
                signal = "EXIT_CONDITION_MET"
            elif entry["score"] is None or exit_value["score"] is None:
                signal = "BLOCKED"
            else:
                signal = "WAIT"
            decisions.append(dict(symbol=asset["symbol"], opportunity_id=opportunity_id,
                                   opportunity_family_id=opportunity_family_id,
                                  signal=signal, entry=entry, exit=exit_value))
        else:
            decisions.append(dict(symbol=asset["symbol"], opportunity_id=opportunity_id,
                                   opportunity_family_id=opportunity_family_id,
                                  signal="NOT_EVALUATED_SCANNER"))
        expected = []
        for feature in spec["monitoring_profile"]["features"]:
            expected.append(dict(feature_id=feature["feature_id"], **read(feature)))
        monitoring.append(dict(symbol=asset["symbol"], opportunity_id=opportunity_id,
                               opportunity_family_id=opportunity_family_id,
                               coverage_scope="SCANNER_SELECTED" if screen["selected"] else "SCANNER_EXCLUDED",
                               expected=len(expected), available=sum(r["status"] == "AVAILABLE_SYNTHETIC" for r in expected),
                               status="COMPLETE_SYNTHETIC" if all(r["status"] == "AVAILABLE_SYNTHETIC" for r in expected) else "MONITORING_INCOMPLETE",
                               observations=expected))
    core = dict(scanner=screens, decisions=decisions)
    return SyntheticRoleReport(canonical(dict(
        schema="synthetic-role-evaluation-2", scope="SYNTHETIC_RESEARCH_ONLY",
        dna_digest=dna.digest, decision_policy_digest=dna.decision_policy_digest,
        decision_cutoff_ms=decision_cutoff_ms, core=core, core_digest=digest(core),
        monitoring=monitoring, orders_created=False, execution="DISABLED",
        independent_custody="NOT_VERIFIED", temporal_evidence="SYNTHETIC_STRUCTURAL_ONLY",
        regime_policy="NOT_EVALUATED", oos="NOT_ACCESSED")))
