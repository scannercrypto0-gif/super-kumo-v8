"""Versioned, retrospective DEVELOPMENT guard contract. Not SF-STRAT-01 V1.

No network, custody promotion, observed orders/fills, OOS or ledger COMPLETE.
VERIFIED_TIMESTAMPED is reserved and always fails closed pending a separately
reviewed binding for independent consumer receipt and decision-ready evidence.
"""
from dataclasses import dataclass
import json
import re

from .strategy_definition import canonical, digest, keys, integer, identifier
from .ema_first_backtest import EmaDecision, ema_crossover_decisions, _validated_closes

COSTS = {'BASE': {'fee_bps': 10, 'slippage_bps': 5},
         'STRESS': {'fee_bps': 20, 'slippage_bps': 10}}
_FIXED_COSTS = canonical(COSTS)
REQUIRED = {'candles', 'ema_8', 'ema_21'}
MANDATORY = {'SIGNAL', 'HARD_VETO', 'RISK_GATE', 'LIQUIDITY_GATE', 'SAFETY_GATE'}
SHA = re.compile(r'[0-9a-f]{64}\Z')


@dataclass(frozen=True, init=False)
class ResearchGuardPlan:
    payload: bytes

    def __init__(self, value):
        keys(value, 'schema_version strategy_id strategy_version scope data_sha256 evidence_sha256 '
             'split_cutoff_ms interval_ms timing inputs costs capital_policy protection_policy')
        if (value['schema_version'] != 'sf-research-guards-1' or
            value['strategy_id'] != 'EMA_8_21_CROSS_LONG_ONLY' or
            value['strategy_version'] != 'SF-IND-02:2:_ema:fsum' or
            value['scope'] != 'HISTORICAL_DEVELOPMENT_ONLY' or
            value['capital_policy'] != 'ONE_BTC_100000_USDT_COMMON_STRESS_CAPITAL_ENVELOPE' or
            value['protection_policy'] != 'UNRESOLVED_STOP_NEW_ENTRIES_NO_INVENTED_EXIT'):
            raise ValueError('Unsupported bounded research policy')
        for field in ('data_sha256', 'evidence_sha256'):
            if type(value[field]) is not str or not SHA.fullmatch(value[field]):
                raise ValueError('Pinned input/evidence hash required')
        integer(value['split_cutoff_ms'], 1, 2**53-1)
        integer(value['interval_ms'], 1, 86400000)
        timing = value['timing']
        keys(timing, 'mode guard_ms override_basis')
        if timing['mode'] not in ('RETROSPECTIVE_UNVERIFIED_TIMING', 'VERIFIED_TIMESTAMPED'):
            raise ValueError('Explicit supported timing mode required')
        if timing['guard_ms'] is None:
            if timing['override_basis'] is not None:
                raise ValueError('Default guard must not imply an override')
        else:
            integer(timing['guard_ms'], 0, min(86400000, value['interval_ms'] * 1000))
            if type(timing['override_basis']) is not str or not timing['override_basis'].strip():
                raise ValueError('Guard override needs separately reviewed frozen basis')
        if canonical(value['costs']) != _FIXED_COSTS:
            raise ValueError('Both fixed BASE/STRESS cost scenarios required')
        inputs = value['inputs']
        if type(inputs) is not list or not 3 <= len(inputs) <= 32:
            raise ValueError('Bounded per-strategy input list required')
        names = set()
        for item in inputs:
            keys(item, 'name criticality role max_age_ms supporting_effect missing_fallback')
            name = identifier(item['name'])
            if name in names:
                raise ValueError('Duplicate input')
            names.add(name)
            if item['criticality'] not in ('ESSENTIAL', 'SUPPORTING') or item['role'] not in MANDATORY | {'CONTEXT'}:
                raise ValueError('Explicit input role/criticality required')
            integer(item['max_age_ms'], 0, 86400000)
            if (name in REQUIRED or item['role'] in MANDATORY) and item['criticality'] != 'ESSENTIAL':
                raise ValueError('Required signal/veto/risk/liquidity/safety cannot be SUPPORTING')
            if name in REQUIRED and item['role'] != 'SIGNAL':
                raise ValueError('Built-in EMA signal inputs retain SIGNAL role')
            if item['criticality'] == 'SUPPORTING':
                if (item['supporting_effect'] != 'AUDIT_ONLY' or
                    item['missing_fallback'] != 'BASE_SIGNAL_WITH_UNKNOWN_CONTEXT'):
                    raise ValueError('Only explicit audit-only supporting fallback is supported')
            elif item['supporting_effect'] is not None or item['missing_fallback'] is not None:
                raise ValueError('Essential inputs cannot carry optional fallbacks')
        if not REQUIRED <= names:
            raise ValueError('Candle and both EMA inputs are essential')
        object.__setattr__(self, 'payload', canonical(value))

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def digest(self):
        return digest(self.spec)

    def eligible_open(self, cutoff):
        timing = self.spec['timing']
        if timing['mode'] != 'RETROSPECTIVE_UNVERIFIED_TIMING':
            return None
        delta = self.spec['interval_ms']
        guard = delta if timing['guard_ms'] is None else timing['guard_ms']
        return ((cutoff + guard + delta - 1) // delta) * delta


def guarded_decisions(bars, interval_ms):
    """Causal contiguous prefix only; warmup/gap rows are blocked, not HOLD.

    Validates all supplied development rows. Never resets EMA after a gap or
    silently resumes a position using a later favorable observation.
    """
    _validated_closes(bars, interval_ms, allow_gaps=True)
    gap = next((i for i in range(1, len(bars))
                if bars[i][0] != bars[i-1][0] + interval_ms), len(bars))
    complete = bars[:gap]
    known = {d.bar_open_ms: d for d in ema_crossover_decisions(complete, interval_ms=interval_ms)} if len(complete) >= 22 else {}
    return tuple(known.get(b[0], EmaDecision(b[1]+1, b[0], None, None, None, None, None)) for b in bars)


def assess_inputs(plan, decision, bar, evidence):
    """Evidence is hash-bound retrospective context, NOT confirmed custody.

    Built-in candle/EMA values come from accepted calculation, not caller
    replacements. Additional gates accept only explicit boolean PASS (True).
    """
    cutoff = decision.decision_cutoff_ms
    supplied = evidence.get(str(cutoff), {})
    names = {i['name'] for i in plan.spec['inputs']}
    if type(supplied) is not dict or not set(supplied) <= names:
        raise ValueError('Undeclared input evidence')
    native = {'candles': list(bar), 'ema_8': decision.ema_fast, 'ema_21': decision.ema_slow}
    audit, blocked = {}, []
    for item in plan.spec['inputs']:
        name = item['name']
        observed = supplied.get(name)
        if name in native:
            if observed is not None:
                keys(observed, 'state')
            state = observed['state'] if observed is not None else 'VALID'
            value, as_of = native[name], cutoff
            if value is None:
                state = 'INSUFFICIENT_WARMUP_OR_GAP'
        elif observed is None:
            state, value, as_of = 'MISSING', None, None
        else:
            keys(observed, 'state value as_of_ms')
            state, value, as_of = observed['state'], observed['value'], observed['as_of_ms']
        if state not in {'VALID', 'MISSING', 'STALE', 'NONFINAL', 'INVALID', 'UNVERIFIED', 'INSUFFICIENT_WARMUP_OR_GAP'}:
            raise ValueError('Unknown evidence state')
        if state == 'VALID':
            if value is None or type(as_of) is not int or not 0 <= as_of <= cutoff:
                state = 'INVALID_OR_FUTURE'
            elif cutoff - as_of > item['max_age_ms']:
                state = 'STALE'
            elif item['role'] in MANDATORY - {'SIGNAL'} and value is not True:
                state = 'REQUIRED_GATE_NOT_PASSED'
        missing = state != 'VALID'
        audit[name] = {'state': state, 'criticality': item['criticality'],
                       'value': 'UNKNOWN' if missing else value,
                       'as_of_ms': as_of, 'actual_receipt_ms': None,
                       'availability_basis': 'RETROSPECTIVE_ASSUMPTION_NOT_VERIFIED',
                       'audit': ('SUPPORTING_DATA_MISSING' if missing and item['criticality'] == 'SUPPORTING' else None)}
        if missing and item['criticality'] == 'ESSENTIAL':
            blocked.append(name + ':' + state)
    return {'status': 'BLOCKED_MISSING_REQUIRED_DATA' if blocked else 'READY',
            'reasons': blocked, 'inputs': audit}


def run_guarded_development(bars, *, plan, expected_plan_digest, evidence):
    """One accepted replay path, both predeclared scenarios, no optimizer.

    Caller must retain expected_plan_digest before observing any outcomes.
    This API does not download data or self-attest a historical freeze date.
    """
    if not isinstance(plan, ResearchGuardPlan) or plan.digest != expected_plan_digest:
        raise ValueError('Frozen guard plan mismatch')
    spec = plan.spec
    records = tuple(bars)
    if not 1 <= len(records) <= 10000 or any(type(b[0]) is not int or b[0] >= spec['split_cutoff_ms'] for b in records):
        raise ValueError('Only acquired development bars before split are allowed')
    if digest(records) != spec['data_sha256'] or digest(evidence) != spec['evidence_sha256']:
        raise ValueError('Frozen data/evidence mismatch')
    if type(evidence) is not dict or not set(evidence) <= {str(b[1]+1) for b in records}:
        raise ValueError('Evidence must bind a supplied development decision cutoff')
    result = {'schema_version': 'sf-guarded-development-1', 'plan_digest': plan.digest,
              'phase': 'HISTORICAL_DEVELOPMENT', 'oos': 'NOT_ACQUIRED_NOT_EVALUATED',
              'actual_fills': 'NOT_OBSERVED', 'independent_custody': 'NOT_VERIFIED'}
    if spec['timing']['mode'] == 'VERIFIED_TIMESTAMPED':
        result.update(status='UNRESOLVED', reason='VERIFIED_RECEIPT_READY_BINDING_NOT_IMPLEMENTED', scenarios=None)
    else:
        from .ema_development_replay import replay_ema_development
        scenarios = {name: replay_ema_development(records, split_cutoff_ms=spec['split_cutoff_ms'],
            interval_ms=spec['interval_ms'], fee_bps=cost['fee_bps'], slippage_bps=cost['slippage_bps'],
            guard_plan=plan, input_evidence=evidence) for name, cost in spec['costs'].items()}
        # Include outcomes in the parity check: a common stress-capital
        # envelope prevents favorable, cost-dependent opportunity selection.
        signature = lambda r: [(e['decision_cutoff_ms'], e['signal'], e['next_open_ms'], e['status'], e['snapshot_sha256'])
                               for e in r['opportunities']]
        if signature(scenarios['BASE']) != signature(scenarios['STRESS']):
            raise ValueError('Paired opportunity divergence; no selection allowed')
        result.update(status='DEVELOPMENT_SIMULATION_ONLY', scenarios=scenarios)
    result['digest'] = digest(result)
    return result
