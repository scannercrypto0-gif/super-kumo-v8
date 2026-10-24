"""Offline paper-position lifecycle contracts. No broker, orders or price fetching."""
from dataclasses import dataclass
from hashlib import sha256
import json

class PositionContractError(ValueError): pass

def _fingerprint(obj):
    return sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()

@dataclass(frozen=True)
class HorizonPolicy:
    policy_id: str
    version: int
    horizons_ms: tuple[int,...]
    def __post_init__(self):
        if not self.policy_id or type(self.version) is not int or self.version < 1:
            raise PositionContractError('invalid horizon policy identity')
        if not self.horizons_ms or any(type(x) is not int or x <= 0 for x in self.horizons_ms) or tuple(sorted(set(self.horizons_ms))) != self.horizons_ms:
            raise PositionContractError('horizons must be positive, sorted and unique')

@dataclass(frozen=True)
class PositionEvent:
    position_id: str
    event_id: str
    kind: str  # opened, quote, closed
    event_ms: int
    received_ms: int
    source: str
    price: str | None = None
    reason: str | None = None
    def __post_init__(self):
        if not self.position_id or not self.event_id or not self.source or self.kind not in ('opened','quote','closed'):
            raise PositionContractError('invalid event identity')
        if any(type(x) is not int for x in (self.event_ms,self.received_ms)) or not 0 <= self.event_ms <= self.received_ms:
            raise PositionContractError('invalid temporal provenance')
        if self.kind == 'closed' and not self.reason:
            raise PositionContractError('explicit close requires reason')
        if self.price is not None:
            if not isinstance(self.price,str): raise PositionContractError('price must be a decimal string')
            from decimal import Decimal, InvalidOperation
            try:
                p=Decimal(self.price)
                if not p.is_finite() or p <= 0: raise PositionContractError('invalid price')
            except (InvalidOperation, TypeError): raise PositionContractError('invalid price')

class PositionLedger:
    """Volatile deterministic event replay; NOT a crash-safe production journal."""
    def __init__(self):
        self.events={}
        self.positions={}
    def append(self,e):
        if not isinstance(e,PositionEvent): raise PositionContractError('invalid event')
        key=(e.position_id,e.event_id)
        if key in self.events:
            if self.events[key] != e: raise PositionContractError('event identity conflict')
            return 'duplicate'
        state=self.positions.get(e.position_id)
        if state is None:
            if e.kind != 'opened': raise PositionContractError('position must open first')
            self.positions[e.position_id]=[e]
        else:
            if e.kind == 'opened' or state[-1].kind == 'closed':
                raise PositionContractError('cannot reopen or mutate closed position')
            if e.event_ms < state[-1].event_ms or e.received_ms < state[-1].received_ms:
                raise PositionContractError('out-of-order event')
            state.append(e)
        self.events[key]=e
        return 'inserted'
    def status(self,position_id,as_of_ms):
        if type(as_of_ms) is not int or as_of_ms < 0: raise PositionContractError('invalid assessment time')
        state=self.positions.get(position_id)
        if not state: return 'unknown'
        visible=[e for e in state if e.received_ms <= as_of_ms]
        if not visible: return 'unknown'
        return 'closed' if visible[-1].kind == 'closed' else 'open'
    def elapsed_ms(self,position_id,as_of_ms):
        state=self.positions.get(position_id)
        if not state: return None
        first=state[0]
        if type(as_of_ms) is not int or as_of_ms < 0: raise PositionContractError('invalid assessment time')
        if as_of_ms < first.received_ms: return None
        end=next((e.event_ms for e in state if e.kind=='closed' and e.received_ms <= as_of_ms),as_of_ms)
        return max(0,end-first.event_ms)
    def checkpoint_state(self,position_id,policy,offset_ms,as_of_ms):
        if not isinstance(policy,HorizonPolicy) or type(offset_ms) is not int or type(as_of_ms) is not int or as_of_ms < 0: return 'invalid'
        if offset_ms not in policy.horizons_ms: return 'invalid'
        state=self.positions.get(position_id)
        if not state or as_of_ms < state[0].received_ms: return 'invalid'
        return 'pending' if as_of_ms < state[0].event_ms+offset_ms else 'due'
