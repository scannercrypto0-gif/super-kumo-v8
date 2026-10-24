"""Additive SF-IND-02 registry. Accepted V1 bytes and APIs remain unchanged."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math

from research_wp_r0.indicator_library import IndicatorLibrary, _get_ds_meta
from research_wp_r0.historical_library import CustodyAccessor, DataAvailabilityKind


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _ema(values, period):
    """SMA seed, standard alpha=2/(period+1); only fully observed prefixes."""
    if len(values) < period:
        return []
    result = [math.fsum(values[:period])/period]
    alpha = 2/(period+1)
    for value in values[period:]:
        result.append(alpha*value+(1-alpha)*result[-1])
    return result


@dataclass(frozen=True)
class VectorResult:
    indicator_id: str
    version: str
    dataset_id: str
    dataset_version: int
    dataset_manifest_hash: str
    bar_open_ms: int
    decision_cutoff_ms: int
    value: tuple
    parameters: tuple
    warmup_bars_consumed: int
    partial_coverage: bool
    provenance_hash: str

    def to_dict(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def create(cls, **fields):
        return cls(**fields, provenance_hash=_hash(fields))

    def verify_integrity(self):
        fields = self.to_dict()
        stored = fields.pop("provenance_hash")
        return stored == _hash(fields) and all(math.isfinite(v) for _, v in self.value)

    @classmethod
    def from_dict(cls, fields):
        expected = set(cls.__dataclass_fields__)
        if type(fields) is not dict or set(fields) != expected:
            raise ValueError("Unexpected result fields")
        data = dict(fields)
        data["value"] = tuple(tuple(v) for v in data["value"])
        data["parameters"] = tuple(tuple(v) for v in data["parameters"])
        obj = cls(**data)
        if not obj.verify_integrity():
            raise ValueError("Result provenance mismatch")
        return obj


@dataclass(frozen=True)
class VectorManifest:
    payload: bytes

    @classmethod
    def create(cls, metadata, results):
        value = {**metadata, "result_hashes": [r.provenance_hash for r in results],
                 "result_count": len(results)}
        return cls(_canonical(value))

    def to_dict(self):
        fields = json.loads(self.payload)
        return {**fields, "manifest_hash": _hash(fields)}

    def __getattr__(self, name):
        fields = json.loads(self.payload)
        if name not in fields:
            raise AttributeError(name)
        value = fields[name]
        return tuple(tuple(p) for p in value) if name == "parameter_set" else value

    def verify(self, results):
        fields = json.loads(self.payload)
        return len(results) == fields["result_count"] and all(r.verify_integrity() for r in results) and (
            [r.provenance_hash for r in results] == fields["result_hashes"])

    @classmethod
    def from_dict(cls, value, *, expected_hash):
        fields = dict(value)
        stored = fields.pop("manifest_hash")
        if stored != _hash(fields) or stored != expected_hash:
            raise ValueError("Manifest commitment mismatch")
        return cls(_canonical(fields))


# Fixed registry: no runtime mutation or third-party plugin loading.
SPECS = (
    ("MACD_v2", ("fast", "slow", "signal"), ("macd", "signal", "histogram")),
    ("BBANDS_v2", ("period", "deviations"), ("middle", "upper", "lower")),
    ("ADX_v2", ("period",), ("adx", "plus_di", "minus_di")),
    ("STOCH_v2", ("period", "smooth"), ("k", "d")),
    ("ROC_v2", ("period",), ("roc",)),
    ("OBV_v2", (), ("obv",)),
)


class ExpandedIndicator:
    version = "2"

    def __init__(self, indicator_id, **params):
        spec = next((s for s in SPECS if s[0] == indicator_id), None)
        if spec is None or set(params) != set(spec[1]):
            raise ValueError("Unknown indicator or parameter set; parameters must be explicit")
        for name, value in params.items():
            if name == "deviations":
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 10:
                    raise ValueError("Invalid finite deviation multiplier")
            elif type(value) is not int or not 2 <= value <= 10000:
                raise ValueError("Integer parameter must be 2..10000, no booleans")
        if indicator_id == "MACD_v2" and params["fast"] >= params["slow"]:
            raise ValueError("MACD requires fast < slow")
        self.indicator_id = indicator_id
        self.output_fields = spec[2]
        self._params = tuple(sorted(params.items()))
        p = params.get("period", 0)
        self.min_warmup_bars = {
            "MACD_v2": params.get("slow", 0)+params.get("signal", 0)-2,
            "BBANDS_v2": p-1, "ADX_v2": 2*p-1,
            "STOCH_v2": p+params.get("smooth", 0)-2,
            "ROC_v2": p, "OBV_v2": 0,
        }[indicator_id]

    @property
    def params(self):
        return dict(self._params)

    def compute(self, accessor, dataset_id, start_ms, end_ms, decision_cutoff_ms,
                *, version=None, require_complete=True):
        # V2 intentionally has no partial-coverage escape hatch.
        if not isinstance(accessor, CustodyAccessor):
            raise ValueError("CustodyAccessor required")
        if require_complete is not True:
            raise ValueError("V2 requires complete confirmed coverage")
        for value in (start_ms, end_ms, decision_cutoff_ms):
            if type(value) is not int or value < 0:
                raise ValueError("Explicit nonnegative integer timestamps required")
        if start_ms > end_ms or end_ms > decision_cutoff_ms:
            raise ValueError("Invalid cutoff/range")
        ds_version, ds_hash = _get_ds_meta(accessor, dataset_id, version)
        bars = accessor.range_query(dataset_id, start_ms, end_ms, decision_cutoff_ms,
                                    version=ds_version, require_complete=True)
        for b in bars:
            if not b.verify_checksum() or not all(math.isfinite(v) for v in (b.open,b.high,b.low,b.close,b.volume)):
                raise ValueError("Invalid OHLCV/checksum")
            if (b.volume < 0 or b.observation_cutoff_ms > decision_cutoff_ms or
                b.bar_close >= decision_cutoff_ms or b.availability_kind != DataAvailabilityKind.CONFIRMED):
                raise ValueError("Invalid volume/availability")
        vectors = self._values(bars)
        results = []
        for index, values in vectors:
            if len(values) != len(self.output_fields) or not all(math.isfinite(v) for v in values):
                raise ValueError("Non-finite or mistyped output")
            results.append(VectorResult.create(
                indicator_id=self.indicator_id, version=self.version,
                dataset_id=dataset_id, dataset_version=ds_version, dataset_manifest_hash=ds_hash,
                bar_open_ms=bars[index].bar_open, decision_cutoff_ms=decision_cutoff_ms,
                value=tuple(zip(self.output_fields, values)), parameters=self._params,
                warmup_bars_consumed=self.min_warmup_bars, partial_coverage=False))
        metadata = dict(indicator_id=self.indicator_id, version=self.version,
                        dataset_id=dataset_id, dataset_version=ds_version,
                        dataset_manifest_hash=ds_hash, decision_cutoff_ms=decision_cutoff_ms,
                        parameter_set=self._params, warmup_policy=self.min_warmup_bars,
                        output_fields=self.output_fields)
        return results, VectorManifest.create(metadata, results)

    def _values(self, bars):
        c = [b.close for b in bars]
        p = self.params
        n = len(c)
        if n <= self.min_warmup_bars:
            return []
        if self.indicator_id == "MACD_v2":
            fast, slow, sig = p["fast"], p["slow"], p["signal"]
            f, s = _ema(c, fast), _ema(c, slow)
            line = [f[i+slow-fast]-v for i,v in enumerate(s)]
            signals = _ema(line, sig)
            return [(slow+sig-2+i, (line[sig-1+i],v,line[sig-1+i]-v))
                    for i,v in enumerate(signals)]
        if self.indicator_id == "BBANDS_v2":
            size = p["period"]
            out = []
            for i in range(size-1,n):
                values = c[i-size+1:i+1]
                mean = math.fsum(values)/size
                sd = math.sqrt(math.fsum((v-mean)**2 for v in values)/size) # population SD
                out.append((i,(mean,mean+p["deviations"]*sd,mean-p["deviations"]*sd)))
            return out
        if self.indicator_id == "STOCH_v2":
            size, smooth = p["period"], p["smooth"]
            ks = []
            for i in range(size-1,n):
                hi=max(b.high for b in bars[i-size+1:i+1])
                lo=min(b.low for b in bars[i-size+1:i+1])
                ks.append(50. if hi==lo else 100*(c[i]-lo)/(hi-lo))
            return [(size+smooth-2+i,(ks[smooth-1+i],math.fsum(ks[i:i+smooth])/smooth))
                    for i in range(len(ks)-smooth+1)]
        if self.indicator_id == "ROC_v2":
            size=p["period"]
            if any(c[i-size]==0 for i in range(size,n)):
                raise ValueError("ROC zero denominator; no invented return")
            return [(i,(100*(c[i]/c[i-size]-1),)) for i in range(size,n)]
        if self.indicator_id == "OBV_v2":
            # Explicit zero seed at the FIRST requested bar; base-volume units.
            values=[0.]
            for i in range(1,n):
                direction = 1 if c[i]>c[i-1] else -1 if c[i]<c[i-1] else 0
                values.append(values[-1]+direction*bars[i].volume)
            return [(i,(v,)) for i,v in enumerate(values)]
        # Wilder ADX: first TR/DM at index1, sums seed at period,
        # first ADX averages period DX values at index(2*period-1).
        size=p["period"]
        trs=[]; plus=[]; minus=[]
        for i in range(1,n):
            up=bars[i].high-bars[i-1].high
            down=bars[i-1].low-bars[i].low
            trs.append(max(bars[i].high-bars[i].low,abs(bars[i].high-c[i-1]),abs(bars[i].low-c[i-1])))
            plus.append(up if up>down and up>0 else 0.)
            minus.append(down if down>up and down>0 else 0.)
        tr, pos, neg = (math.fsum(v[:size]) for v in (trs,plus,minus))
        dxs=[]; dis=[]
        for i in range(size,n):
            if i>size:
                tr=tr-tr/size+trs[i-1];pos=pos-pos/size+plus[i-1];neg=neg-neg/size+minus[i-1]
            pd,md = (100*pos/tr,100*neg/tr) if tr else (0.,0.)
            dis.append((pd,md))
            dxs.append(100*abs(pd-md)/(pd+md) if pd+md else 0.)
        adx=math.fsum(dxs[:size])/size
        out=[]
        for i in range(size-1,len(dxs)):
            if i>size-1:
                adx=(adx*(size-1)+dxs[i])/size
            out.append((size+i,(adx,*dis[i])))
        return out


class IndicatorRegistryV2(IndicatorLibrary):
    """Inject into StrategyDefinition(..., registry=...) without importing strategies."""
    def get(self, indicator_id, **params):
        if indicator_id in {s[0] for s in SPECS}:
            return ExpandedIndicator(indicator_id, **params)
        return super().get(indicator_id, **params)

    @classmethod
    def available(cls):
        return sorted(super().available()+[s[0] for s in SPECS])
