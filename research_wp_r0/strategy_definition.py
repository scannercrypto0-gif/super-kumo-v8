"""SF-STRAT-01: immutable declarative research contracts, no execution engine."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from research_wp_r0.indicator_library import IndicatorLibrary
from research_wp_r0.historical_library import CustodyAccessor, DataAvailabilityKind, BarQuality


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def _reject(value):
    raise ValueError("Non-finite JSON constant")


def _clean(value, depth=0):
    if depth > 24:
        raise ValueError("JSON too deep")
    if value is None or type(value) in (str, bool, int):
        if type(value) is int and abs(value) > 2**53 - 1:
            raise ValueError("Integer outside exact interoperable range")
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite number")
        # Equal numeric values (1/1.0 and signed zero) have identical bytes.
        return _clean(int(value), depth) if value.is_integer() else value
    if type(value) in (list, tuple):
        return [_clean(v, depth+1) for v in value]
    if type(value) is dict and all(type(k) is str for k in value):
        return {k: _clean(v, depth+1) for k, v in value.items()}
    raise ValueError("Only JSON values allowed")


def canonical(value):
    return json.dumps(_clean(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _json_float(text):
    value = float(text)
    significand = text.lower().split("e")[0]
    if not math.isfinite(value) or (value == 0 and any(c in "123456789" for c in significand)):
        raise ValueError("JSON number overflow/underflow")
    return value


def load_json(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > 100000:
        raise ValueError("Expected bounded UTF-8 JSON string")
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_reject, parse_float=_json_float)
    except (RecursionError, UnicodeError) as error:
        raise ValueError("Invalid JSON encoding/depth") from error


def keys(obj, required):
    if type(obj) is not dict or set(obj) != set(required.split()):
        raise ValueError("Unexpected or missing fields: " + required)


def integer(value, minimum=1, maximum=100000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError("Invalid integer")
    return value


def number(value, minimum=None, maximum=None):
    if type(value) not in (int, float) or (type(value) is int and abs(value) > 2**53-1) or not math.isfinite(value):
        raise ValueError("Invalid finite number")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError("Number outside bounds")
    return value


def identifier(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", value):
        raise ValueError("Invalid identifier")
    return value


def _reference(ref, registry):
    keys(ref, "name indicator_id version parameters constraints")
    identifier(ref["name"])
    identifier(ref["indicator_id"])
    if type(ref["version"]) is not str:
        raise ValueError("Version must be explicit string")
    params, constraints = ref["parameters"], ref["constraints"]
    if type(params) is not dict or type(constraints) is not dict or set(params) != set(constraints):
        raise ValueError("Every parameter needs an explicit constraint")
    for name, value in params.items():
        identifier(name)
        c = constraints[name]
        keys(c, "type min max")
        if c["type"] == "int":
            integer(value)
            integer(c["min"]); integer(c["max"])
        elif c["type"] == "number":
            number(value); number(c["min"]); number(c["max"])
        else:
            raise ValueError("Unknown parameter type")
        if not c["min"] <= value <= c["max"]:
            raise ValueError("Parameter outside declared bounds")
    try:
        ind = registry.get(ref["indicator_id"], **params)
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("Unsupported indicator/parameters") from error
    if ind.version != ref["version"] or set(ind.params) != set(params):
        raise ValueError("Version/default parameters must be explicit")
    return tuple(getattr(ind, "output_fields", ("value",)))


def _expression(node, refs, depth=0, count=None):
    if count is None:
        count = [0]
    count[0] += 1
    if depth > 8 or count[0] > 128:
        raise ValueError("Expression exceeds bounds")
    if type(node) is not dict or "op" not in node:
        raise ValueError("Invalid AST node")
    op = node["op"]
    if op == "constant":
        keys(node, "op value"); number(node["value"])
        return "number"
    if op == "indicator":
        keys(node, "op name field lag")
        identifier(node["name"]); identifier(node["field"])
        if node["name"] not in refs or node["field"] not in refs[node["name"]]:
            raise ValueError("Unresolved typed output")
        integer(node["lag"], 0, 10000)
        return "number"
    if op in ("gt", "ge", "lt", "le", "eq"):
        keys(node, "op left right")
        if any(_expression(node[k], refs, depth+1, count) != "number" for k in ("left", "right")):
            raise ValueError("Comparison operands must be numeric")
        return "bool"
    if op in ("all", "any"):
        keys(node, "op args")
        if type(node["args"]) is not list or not 2 <= len(node["args"]) <= 8:
            raise ValueError("Invalid boolean arity")
        if any(_expression(v, refs, depth+1, count) != "bool" for v in node["args"]):
            raise ValueError("Boolean operands required")
        return "bool"
    if op == "not":
        keys(node, "op arg")
        if _expression(node["arg"], refs, depth+1, count) != "bool":
            raise ValueError("Boolean operand required")
        return "bool"
    raise ValueError("Operator is not declarative allowlisted AST")


@dataclass(frozen=True, init=False)
class StrategyDefinition:
    """Canonical bytes are the only state; returned dictionaries are copies."""
    payload: bytes

    def __init__(self, spec, *, registry=None):
        registry = registry if registry is not None else IndicatorLibrary()
        # Validate original types before numeric canonicalization (bool != int).
        keys(spec, "schema_version strategy_id strategy_version scope indicators entry exit timing risk")
        if spec["schema_version"] != "1" or spec["scope"] != "RESEARCH_ONLY":
            raise ValueError("Unsupported schema/scope")
        identifier(spec["strategy_id"]); identifier(spec["strategy_version"])
        if type(spec["indicators"]) is not list or not 1 <= len(spec["indicators"]) <= 32:
            raise ValueError("Bounded indicator references required")
        refs = {}
        for ref in spec["indicators"]:
            fields = _reference(ref, registry)
            if ref["name"] in refs:
                raise ValueError("Duplicate reference name")
            refs[ref["name"]] = fields
        for name in ("entry", "exit"):
            if _expression(spec[name], refs) != "bool":
                raise ValueError("Entry/exit must be boolean")
        keys(spec["timing"], "decision entry_execution ambiguity")
        if spec["timing"] != {"decision": "CONFIRMED_CLOSE", "entry_execution": "NEXT_ELIGIBLE_OPEN",
                              "ambiguity": "REJECT"}:
            raise ValueError("Unsupported timing/ambiguity semantics")
        risk = spec["risk"]
        keys(risk, "unit max_exposure max_leverage stop_fraction target_fraction entry_ttl_bars holding_bars")
        if risk["unit"] != "ENTRY_NOTIONAL":
            raise ValueError("Unsupported sizing unit")
        number(risk["max_exposure"], 0.000001, 1)
        number(risk["max_leverage"], 1, 1)  # V1 unlevered research only
        number(risk["stop_fraction"], 0.000001, 0.999999)
        number(risk["target_fraction"], 0.000001, 10)
        integer(risk["entry_ttl_bars"], 1, 1000); integer(risk["holding_bars"], 1, 10000)
        object.__setattr__(self, "payload", canonical(spec))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return hashlib.sha256(self.payload).hexdigest()

    def to_dict(self):
        return {"definition": self.spec, "digest": self.digest}

    def to_json(self):
        return canonical(self.to_dict()).decode("utf-8")

    @classmethod
    def from_dict(cls, value, *, registry=None):
        keys(value, "definition digest")
        obj = cls(value["definition"], registry=registry)
        if value["digest"] != obj.digest:
            raise ValueError("Definition digest mismatch")
        return obj

    @classmethod
    def from_json(cls, raw, *, registry=None):
        return cls.from_dict(load_json(raw), registry=registry)


@dataclass(frozen=True, init=False)
class EvaluationBinding:
    """Separate PIT receipt; generated from verified custody, never raw user hashes."""
    payload: bytes

    def __init__(self, value):
        object.__setattr__(self, "payload", canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return hashlib.sha256(self.payload).hexdigest()

    def to_dict(self):
        return {"binding": self.spec, "digest": self.digest}

    @classmethod
    def from_dict(cls, value, *, expected_digest):
        keys(value, "binding digest")
        obj = cls(value["binding"])
        if value["digest"] != obj.digest or obj.digest != expected_digest:
            raise ValueError("Binding differs from retained commitment")
        return obj


def bind_evaluation(definition, accessor, dataset_id, version, start_ms, end_ms,
                    decision_cutoff_ms, *, registry=None):
    """No signals/trades evaluated. Complete, confirmed PIT inputs only."""
    registry = registry if registry is not None else IndicatorLibrary()
    if not isinstance(accessor, CustodyAccessor):
        raise ValueError("CustodyAccessor required")
    integer(version)
    for value in (start_ms, end_ms, decision_cutoff_ms):
        integer(value, 0, 2**53-1)
    if start_ms > end_ms or end_ms > decision_cutoff_ms:
        raise ValueError("Invalid temporal range")
    # Revalidate registry compatibility when binding (registry may differ).
    StrategyDefinition(definition.spec, registry=registry)
    bars = accessor.range_query(dataset_id, start_ms, end_ms, decision_cutoff_ms,
                                version=version, require_complete=True)
    if any(not b.verify_checksum() or b.availability_kind != DataAvailabilityKind.CONFIRMED or
           b.bar_close >= decision_cutoff_ms or b.observation_cutoff_ms > decision_cutoff_ms
           for b in bars):
        raise ValueError("Unconfirmed/future/corrupt input")
    for b in bars:
        if (b.quality != BarQuality.FINAL or type(b.observation_cutoff_ms) is not int or
            b.observation_cutoff_ms < b.bar_close + 1 or
            b.ingest_time_ms is not None and (type(b.ingest_time_ms) is not int or
                                             b.ingest_time_ms < 0 or b.ingest_time_ms > b.observation_cutoff_ms)):
            raise ValueError("Non-final or inconsistent receipt/availability timestamps")
    meta = accessor._library.get_manifest(dataset_id, version)
    if not meta.verify_integrity():
        raise ValueError("Dataset manifest integrity failure")
    receipts = []
    for ref in definition.spec["indicators"]:
        ind = registry.get(ref["indicator_id"], **ref["parameters"])
        results, manifest = ind.compute(accessor, dataset_id, start_ms, end_ms,
                                        decision_cutoff_ms, version=version, require_complete=True)
        needed_lag = max(_lags(definition.spec["entry"], ref["name"]) +
                         _lags(definition.spec["exit"], ref["name"]) + [0])
        if len(results) <= needed_lag or not manifest.verify(results):
            raise ValueError("Insufficient warmup/history or invalid manifest")
        if manifest.indicator_id != ref["indicator_id"] or manifest.decision_cutoff_ms != decision_cutoff_ms or tuple(manifest.parameter_set) != tuple(sorted(ind.params.items())) or manifest.warmup_policy != ind.min_warmup_bars:
            raise ValueError("Indicator manifest identity mismatch")
        if manifest.dataset_id != dataset_id or manifest.dataset_version != version or (
            manifest.dataset_manifest_hash != meta.manifest_integrity_hash):
            raise ValueError("Dataset/indicator manifest mismatch")
        if [r.bar_open_ms for r in results] != [b.bar_open for b in bars[ind.min_warmup_bars:]]:
            raise ValueError("Indicator output ordering/coverage mismatch")
        for r in results:
            if not r.verify_integrity() or r.partial_coverage or r.decision_cutoff_ms != decision_cutoff_ms:
                raise ValueError("Invalid result provenance/partial coverage")
            if (r.indicator_id != ref["indicator_id"] or r.version != ref["version"] or
                r.dataset_id != dataset_id or r.dataset_version != version or
                r.dataset_manifest_hash != meta.manifest_integrity_hash or
                tuple(r.parameters) != tuple(sorted(ind.params.items()))):
                raise ValueError("Indicator result identity mismatch")
            fields = getattr(ind, "output_fields", None)
            if fields is not None:
                if type(r.value) is not tuple or tuple(k for k, _ in r.value) != tuple(fields):
                    raise ValueError("Typed output fields mismatch")
            elif type(r.value) is tuple:
                raise ValueError("Scalar indicator output required")
            if r.warmup_bars_consumed != ind.min_warmup_bars:
                raise ValueError("Result warmup mismatch")
            values = [v for _, v in r.value] if type(r.value) is tuple else [r.value]
            for value in values:
                number(value)
            if r.bar_open_ms > end_ms or r.bar_open_ms > decision_cutoff_ms:
                raise ValueError("Future indicator result")
        receipts.append({"name": ref["name"], "indicator_id": ref["indicator_id"],
                         "version": ref["version"], "parameters": ref["parameters"],
                         "manifest": manifest.to_dict(),
                         "result_hashes": [r.provenance_hash for r in results]})
    return EvaluationBinding({"schema_version": "1", "strategy_digest": definition.digest,
                              "dataset_id": dataset_id, "dataset_version": version,
                              "dataset_manifest_hash": meta.manifest_integrity_hash,
                              "start_ms": start_ms, "end_ms": end_ms, "decision_cutoff_ms": decision_cutoff_ms,
                              "bar_checksums": [b.checksum for b in bars], "indicators": receipts})


def _lags(node, name):
    if node["op"] == "indicator":
        return [node["lag"]] if node["name"] == name else []
    if node["op"] in ("all", "any"):
        return [v for n in node["args"] for v in _lags(n, name)]
    if node["op"] == "not":
        return _lags(node["arg"], name)
    if node["op"] in ("gt", "ge", "lt", "le", "eq"):
        return _lags(node["left"], name) + _lags(node["right"], name)
    return []


@dataclass(frozen=True)
class PreparedAttempt:
    family_id: str
    candidate_id: str
    input_digest: str
    strategy_digest: str


class AttemptRecorder:
    """Narrow caller-owned durable ledger port, not another journal implementation.

    sink.record_attempt(event_dict) must persist or raise, including INVALID.
    Caller retains returned events/commitments; no durability/custody is claimed here.
    """
    def __init__(self, sink):
        self.sink = sink

    def prepare(self, raw_json, family_id, candidate_id, *, registry=None):
        identifier(family_id); identifier(candidate_id)
        if type(raw_json) is not str:
            raise ValueError("Raw attempt must be JSON text")
        raw_hash = hashlib.sha256(raw_json.encode("utf-8", errors="surrogatepass")).hexdigest()
        try:
            definition = StrategyDefinition.from_json(raw_json, registry=registry)
        except Exception as error:
            # Registry/provider failures are attempted work too. Never swallow
            # the failure or fabricate a completed result; persistence may raise.
            state = "INVALID" if isinstance(error, (ValueError, TypeError, KeyError)) else "FAILED"
            self.sink.record_attempt({"state": state, "family_id": family_id,
                                      "candidate_id": candidate_id, "input_digest": raw_hash,
                                      "error_type": type(error).__name__})
            raise
        prepared = PreparedAttempt(family_id, candidate_id, raw_hash, definition.digest)
        self.sink.record_attempt({**prepared.__dict__, "state": "PENDING"})
        return prepared, definition

    def finish(self, prepared, state, *, binding=None, result_digest=None):
        if state not in ("COMPLETE", "FAILED", "ABANDONED"):
            raise ValueError("Explicit terminal attempt state required")
        if state == "COMPLETE":
            if binding is None or binding.spec["strategy_digest"] != prepared.strategy_digest:
                raise ValueError("Binding mismatch")
            if type(result_digest) is not str or not re.fullmatch("[0-9a-f]{64}", result_digest):
                raise ValueError("Result commitment required")
        event = {**prepared.__dict__, "state": state,
                 "binding_digest": binding.digest if binding is not None else None,
                 "result_digest": result_digest}
        self.sink.record_attempt(event)
        return event

def candidate_grid(definition, axes, *, registry=None, maximum=256):
    """Finite predeclared Cartesian grid; every candidate validated and retained."""
    from itertools import product
    if type(axes) is not dict or not axes:
        raise ValueError("Explicit grid axes required")
    names = sorted(axes)
    count = 1
    for name in names:
        if type(axes[name]) is not list or not axes[name]:
            raise ValueError("Nonempty finite axis required")
        count *= len(axes[name])
    integer(maximum, 1, 4096)
    if count > maximum:
        raise ValueError("Candidate family exceeds bound")
    candidates = []
    seen = set()
    for values in product(*(axes[n] for n in names)):
        spec = definition.spec
        refs = {r["name"]: r for r in spec["indicators"]}
        for name, value in zip(names, values):
            parts = name.split(".")
            if len(parts) != 2 or parts[0] not in refs or parts[1] not in refs[parts[0]]["parameters"]:
                raise ValueError("Unknown grid parameter")
            refs[parts[0]]["parameters"][parts[1]] = value
        item = StrategyDefinition(spec, registry=registry)
        if item.digest in seen:
            raise ValueError("Duplicate canonical candidate")
        seen.add(item.digest); candidates.append(item)
    return tuple(candidates)
