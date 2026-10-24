"""Offline-only immutable PIT and observation contracts. No durable persistence or execution."""
from dataclasses import dataclass, field, asdict
from types import MappingProxyType
import hashlib
import json

HORIZONS_MS = (14400000, 86400000, 259200000)
CONTEXT_KEYS = frozenset(('btc_eth','btc_dominance','btc_trend','altseason','breadth','liquidity','volatility','relative_strength'))
DISPOSITIONS = frozenset(('observed','rejected','expired','no_fill'))
class ContractError(ValueError): pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()

@dataclass(frozen=True)
class ContextValue:
    value: str | None
    source: str | None
    observed_ms: int | None
    available_ms: int | None
    missing_reason: str | None = None
    def validate(self, decision_ms):
        if self.value is None:
            if not self.missing_reason or self.source or self.observed_ms is not None or self.available_ms is not None:
                raise ContractError('missing context requires reason without fabricated provenance')
        elif not self.source or self.observed_ms is None or self.available_ms is None or self.missing_reason:
            raise ContractError('present context requires provenance and timestamps')
        if self.observed_ms is not None and (self.observed_ms < 0 or self.available_ms is None or self.available_ms < self.observed_ms or self.available_ms > decision_ms):
            raise ContractError('future or invalid context')

@dataclass(frozen=True)
class DecisionSnapshot:
    opportunity_key: str
    source: str
    event_ms: int
    receipt_ms: int
    decision_ms: int
    disposition: str
    context: dict
    freshness_limit_ms: int
    uncertainty_ms: int = 0
    schema_version: int = 1
    snapshot_id: str = field(init=False)
    def __post_init__(self):
        if not self.opportunity_key or not self.source or self.disposition not in DISPOSITIONS:
            raise ContractError('invalid identity/disposition')
        if not all(type(v) is int for v in (self.event_ms, self.receipt_ms, self.decision_ms)) or not (0 <= self.event_ms <= self.receipt_ms <= self.decision_ms):
            raise ContractError('invalid event/receipt/decision order')
        if self.schema_version != 1 or not all(type(v) is int and v >= 0 for v in (self.freshness_limit_ms, self.uncertainty_ms)):
            raise ContractError('invalid version/time bounds')
        if set(self.context) != CONTEXT_KEYS:
            raise ContractError('all eight context slots required')
        for item in self.context.values():
            if not isinstance(item, ContextValue): raise ContractError('invalid context type')
            item.validate(self.decision_ms)
            if item.available_ms is not None and self.decision_ms-item.available_ms > self.freshness_limit_ms:
                raise ContractError('stale context must be explicitly missing')
        object.__setattr__(self,'context',MappingProxyType(dict(self.context)))
        object.__setattr__(self,'snapshot_id',digest(self.payload()))
    def payload(self):
        return dict(schema_version=self.schema_version,opportunity_key=self.opportunity_key,source=self.source,
                    event_ms=self.event_ms,receipt_ms=self.receipt_ms,decision_ms=self.decision_ms,
                    disposition=self.disposition,freshness_limit_ms=self.freshness_limit_ms,
                    uncertainty_ms=self.uncertainty_ms,context={k:asdict(self.context[k]) for k in sorted(self.context)})
    def serialized(self): return canonical(dict(snapshot_id=self.snapshot_id,**self.payload()))

@dataclass(frozen=True)
class Observation:
    snapshot_id: str
    horizon_ms: int
    observed_ms: int
    received_ms: int
    source: str
    evidence_id: str
    value: str | None
    missing_reason: str | None = None
    def validate(self,decision_ms):
        if self.horizon_ms not in HORIZONS_MS or not self.source or not self.evidence_id:
            raise ContractError('invalid horizon/provenance')
        if not all(type(v) is int for v in (self.observed_ms,self.received_ms)) or self.observed_ms < decision_ms+self.horizon_ms or self.received_ms < self.observed_ms:
            raise ContractError('premature/impossible observation')
        if (self.value is None) == (self.missing_reason is None):
            raise ContractError('require either value or missing reason')

@dataclass(frozen=True)
class LateContextEvent:
    """Append-only information learned after the original decision; never rewrites PIT."""
    snapshot_id: str
    event_id: str
    source: str
    observed_ms: int
    received_ms: int
    context_key: str
    value: str
    def validate(self, decision_ms):
        if not self.snapshot_id or not self.event_id or not self.source or self.context_key not in CONTEXT_KEYS or not self.value:
            raise ContractError('invalid late context event')
        if not all(type(t) is int for t in (self.observed_ms,self.received_ms)):
            raise ContractError('invalid late context timestamps')
        if not (0 <= self.observed_ms <= self.received_ms) or self.received_ms <= decision_ms:
            raise ContractError('late context must arrive after PIT decision')

@dataclass(frozen=True)
class PaperIntent:
    snapshot_id: str
    intent_id: str
    status: str  # interface only: proposed / declined / cancelled; never orders/fills
    def __post_init__(self):
        if not self.snapshot_id or not self.intent_id or self.status not in ('proposed','declined','cancelled'):
            raise ContractError('invalid non-trading paper intent')

class ObservationLedger:
    """Volatile replay fixture only. No claim of crash-safe durable storage."""
    def __init__(self):
        self.snapshots={}
        self.observations={}
        self.late_context={}
        self.events=[]
    def add_snapshot(self,s):
        prior=self.snapshots.get(s.opportunity_key)
        if prior:
            if prior.snapshot_id != s.snapshot_id: raise ContractError('immutable snapshot conflict; correction contract required')
            return 'duplicate'
        self.snapshots[s.opportunity_key]=s
        self.events.append(('snapshot',s.snapshot_id))
        return 'inserted'
    def add_observation(self,o):
        snap=next((s for s in self.snapshots.values() if s.snapshot_id==o.snapshot_id),None)
        if snap is None: raise ContractError('unknown snapshot')
        o.validate(snap.decision_ms)
        key=(o.snapshot_id,o.horizon_ms)
        prior=self.observations.get(key)
        if prior:
            if prior != o: raise ContractError('observation conflict; correction contract required')
            return 'duplicate'
        self.observations[key]=o
        self.events.append(('observation',digest(asdict(o))))
        return 'inserted'
    def add_late_context(self,e):
        snap=next((s for s in self.snapshots.values() if s.snapshot_id==e.snapshot_id),None)
        if snap is None: raise ContractError('unknown snapshot')
        e.validate(snap.decision_ms)
        key=(e.snapshot_id,e.event_id)
        prior=self.late_context.get(key)
        if prior:
            if prior != e: raise ContractError('late event identity conflict')
            return 'duplicate'
        self.late_context[key]=e
        self.events.append(('late_context',digest(asdict(e))))
        return 'inserted'
    def horizon_state(self,snapshot_id,horizon_ms,as_of_ms):
        if horizon_ms not in HORIZONS_MS: return 'invalid'
        snap=next((s for s in self.snapshots.values() if s.snapshot_id==snapshot_id),None)
        if snap is None or as_of_ms < snap.decision_ms: return 'invalid'
        o=self.observations.get((snapshot_id,horizon_ms))
        if o and o.received_ms <= as_of_ms: return 'missing' if o.value is None else 'mature'
        return 'pending'
