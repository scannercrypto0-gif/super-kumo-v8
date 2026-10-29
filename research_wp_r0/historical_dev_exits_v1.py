"""Offline DEV-only, long-only native exits. No execution or PIT authority.

All fills are assumptions, including FACTUAL's unambiguous modeled exits.
FACTUAL means evidence-preserving ambiguity policy, NOT observed execution.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import math

from .ema_first_backtest import ema_crossover_decisions

VERSION = 'SF-HISTORICAL-DEV-EXITS-1'
STRATEGY = 'EMA8_21_SMA_SEED_FSUM_V2_CROSS_LONG_1'
PATHS = ('FACTUAL', 'TARGET_FIRST', 'STOP_FIRST')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def number(x, minimum=0, maximum=None):
    return (type(x) in (int, float) and math.isfinite(x) and x >= minimum
            and (maximum is None or x <= maximum))


@dataclass(frozen=True)
class Config:
    interval_ms: int = 60000
    initial_cash: float = 1000
    quantity: float = 1
    tp_fraction: float | None = None
    sl_fraction: float | None = None
    indicator_exit: bool = True
    fee_bps: float = 10
    spread_bps: float = 2
    slippage_bps: float = 5
    latency_ms: int = 1
    max_signal_age_ms: int = 120000
    checkpoint_ms: int = 86400000
    warmup_bars: int | None = None  # None preserves legacy engine/receipts; B0 must explicitly pin 252

    def validate(self):
        for name in ('interval_ms', 'max_signal_age_ms', 'checkpoint_ms'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError('INVALID_CONFIG_' + name)
        if self.warmup_bars is not None and (type(self.warmup_bars) is not int or self.warmup_bars < 22):
            raise ValueError('INVALID_WARMUP_BARS')
        if type(self.latency_ms) is not int or self.latency_ms < 0:
            raise ValueError('INVALID_LATENCY')
        if (not number(self.initial_cash, 1e-12) or not number(self.quantity, 1e-12)
                or type(self.indicator_exit) is not bool):
            raise ValueError('INVALID_CAPITAL_OR_EXIT')
        for name in ('fee_bps', 'spread_bps', 'slippage_bps'):
            if not number(getattr(self, name), 0, 1000):
                raise ValueError('INVALID_COST_' + name)
        for name in ('tp_fraction', 'sl_fraction'):
            value = getattr(self, name)
            if value is not None and not number(value, 1e-12, .99):
                raise ValueError('INVALID_OVERLAY_' + name)


def _validate(bars, source, cfg):
    cfg.validate()
    if not bars:
        raise ValueError('EMPTY_DATA')
    # Explicit unknown timing is permitted ONLY as retrospective DEV evidence.
    if (source.get('rows_sha256') != digest(bars) or
            not isinstance(source.get('version'), str) or not source['version'] or
            not isinstance(source.get('reference'), str) or not source['reference'] or
            source.get('availability_evidence') not in ('UNKNOWN', 'PINNED_OBSERVATION') or
            source.get('correction_evidence') not in ('PINNED_VERSION_ONLY', 'PINNED_LINEAGE') or
            not isinstance(source.get('archive_sha256'), str) or
            len(source['archive_sha256']) != 64 or
            any(c not in '0123456789abcdef' for c in source['archive_sha256'])):
        raise ValueError('MISSING_OR_MISMATCHED_SOURCE_VERSION_EVIDENCE')
    previous = None
    for b in bars:
        t = b.get('open_ms')
        if (type(t) is not int or t < 0 or t % cfg.interval_ms or
                type(b.get('close_ms')) is not int or b['close_ms'] != t + cfg.interval_ms - 1 or
                previous is not None and t != previous + cfg.interval_ms):
            raise ValueError('GAP_OR_INVALID_GRID')
        previous = t
        if any(not number(b.get(k), 1e-12) for k in ('open', 'high', 'low', 'close')):
            raise ValueError('MISSING_OR_BAD_OHLC')
        if (not number(b.get('volume')) or
                b['high'] < max(b['open'], b['close'], b['low']) or
                b['low'] > min(b['open'], b['close'])):
            raise ValueError('BAD_OHLCV')
        if (type(b.get('available_ms')) is not int or b['available_ms'] < t + cfg.interval_ms
                or type(b.get('modeled_quote')) is not bool):
            raise ValueError('MISSING_AVAILABILITY_OR_QUOTE_ASSUMPTION')


def _signals(bars, cfg):
    records = [(b['open_ms'], b['close_ms'], b['open'], b['high'], b['low'],
                b['close'], b['volume']) for b in bars]
    decisions = ema_crossover_decisions(records, interval_ms=cfg.interval_ms)
    prefix_ready = {}
    ready = 0
    for b in bars:
        ready = max(ready, b['available_ms'])
        prefix_ready[b['open_ms']] = ready
    # Compute EMA on the entire available prefix, but prohibit scoring/signals
    # before the configured warmup count. Do not re-seed at the scoring boundary.
    eligible = None if cfg.warmup_bars is None else {b['open_ms'] for b in bars[cfg.warmup_bars:]}
    return [{'bar_open_ms': d.bar_open_ms, 'action': d.signal,
             'available_ms': prefix_ready[d.bar_open_ms]} for d in decisions
            if eligible is None or d.bar_open_ms in eligible]


def replay(bars, *, source, config=Config()):
    """Non-production replay API for synthetic/contract development only.

    The original-local-pair production source is accepted only by the Factory
    post-admission function below, which requires the one-time start marker.
    """
    if isinstance(source, dict) and source.get("version") == "original-local-pair-v1":
        raise PermissionError("PRODUCTION_REPLAY_REQUIRES_FACTORY_START_RECEIPT")
    return _replay_impl(bars, source=source, config=config)


def replay_after_factory_start(bars, *, source, config=Config(), start_receipt):
    """Internal production replay primitive, callable only with a real start marker.

    This is an application-level boundary, not a defense against hostile code
    running with the same filesystem identity. Production callers must obtain
    the receipt from Core authorize_factory_execution immediately before use.
    """
    from pathlib import Path
    if not isinstance(start_receipt, dict) or start_receipt.get("schema") != "aql-owner-admission-start-v1":
        raise PermissionError("FACTORY_START_RECEIPT_REQUIRED")
    if start_receipt.get("max_runs") != 1:
        raise PermissionError("FACTORY_START_RECEIPT_INVALID")
    marker_path = start_receipt.get("start_record_path")
    expected_sha = start_receipt.get("start_record_sha256")
    if not isinstance(marker_path, str) or not Path(marker_path).is_absolute():
        raise PermissionError("FACTORY_START_MARKER_PATH_INVALID")
    if not isinstance(expected_sha, str) or len(expected_sha) != 64:
        raise PermissionError("FACTORY_START_MARKER_HASH_INVALID")
    try:
        raw = Path(marker_path).read_bytes()
        marker = json.loads(raw)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise PermissionError("FACTORY_START_MARKER_UNREADABLE") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise PermissionError("FACTORY_START_MARKER_HASH_MISMATCH")
    for key in ("schema", "permit_id", "admission_record_sha256", "head_sha", "started_at", "max_runs"):
        if marker.get(key) != start_receipt.get(key):
            raise PermissionError("FACTORY_START_MARKER_BINDING_MISMATCH")
    if not isinstance(source, dict) or source.get("version") != "original-local-pair-v1":
        raise PermissionError("FACTORY_PRODUCTION_SOURCE_IDENTITY_REQUIRED")
    return _replay_impl(bars, source=source, config=config)


def _replay_impl(bars, *, source, config=Config()):
    """Engine primitive. Production callers must use replay_after_factory_start."""
    bars, source = json.loads(json.dumps([bars, source], allow_nan=False))
    _validate(bars, source, config)
    return _receipt(bars, source, config, _signals(bars, config), STRATEGY)


def replay_contract_fixture(bars, *, source, signals, config=Config()):
    """Handcrafted execution-contract falsifiers, explicitly NOT EMA study data."""
    bars, source, signals = json.loads(json.dumps([bars, source, signals], allow_nan=False))
    _validate(bars, source, config)
    return _receipt(bars, source, config, signals, 'CONTRACT_FIXTURE_ONLY_1')


def _receipt(bars, source, cfg, signals, strategy):
    by_time = {b['open_ms']: b for b in bars}
    previous = -1
    prefix_ready, ready = {}, 0
    for b in bars:
        ready = max(ready, b['available_ms'])
        prefix_ready[b['open_ms']] = ready
    scheduled = []
    for s in signals:
        t = s.get('bar_open_ms')
        if (type(t) is not int or t not in by_time or t <= previous or
                s.get('action') not in ('ENTER_LONG', 'EXIT_LONG', 'HOLD') or
                type(s.get('available_ms')) is not int or
                s['available_ms'] != (prefix_ready[t] if strategy == STRATEGY else by_time[t]['available_ms'])):
            raise ValueError('INVALID_OR_UNPINNED_SIGNAL')
        previous = t
        ready = s['available_ms'] + cfg.latency_ms
        execution = ((ready + cfg.interval_ms - 1) // cfg.interval_ms) * cfg.interval_ms
        scheduled.append({**s, 'scheduled_ms': execution,
                          'stale': execution - (t + cfg.interval_ms) > cfg.max_signal_age_ms})
    config_payload = asdict(cfg)
    if cfg.warmup_bars is None:
        # Legacy receipts predate this opt-in field; preserve canonical hashes.
        del config_payload['warmup_bars']
    payload = {'schema': VERSION, 'scope': 'HISTORICAL_DEV_ONLY', 'strategy': strategy,
               'source': source, 'config': config_payload, 'signals_sha256': digest(signals),
               'input_rows': bars, 'signals': signals,
               'claims': {'actual_fills': False, 'as_known_at_cutoff': False,
                          'real_pit_accepted': False, 'profitability': False,
                          'oos': False, 'paper': False, 'live': False},
               'assumptions': 'ONE_LONG_FIXED_QTY; MODELED_FULL_FILL_OR_UNKNOWN; HALF_SPREAD_PLUS_SLIPPAGE_PER_SIDE; FEES_PER_SIDE; GAP_OVERLAY_AT_OPEN; NO_INTRABAR_ORDER; NO_FORCED_CLOSE; SCENARIOS_NOT_BOUNDS',
               'paths': {p: _path(bars, scheduled, cfg, p) for p in PATHS}}
    return {**payload, 'receipt_sha256': digest(payload)}


def _path(bars, scheduled, cfg, path):
    cash, quantity, basis, entry_reference = cfg.initial_cash, 0., 0., None
    realized, fees, uncertain, ambiguous = 0., 0., False, 0
    ledger, opportunities, marks = [], [], []
    previous_hash = '0' * 64
    impact = (cfg.spread_bps / 2 + cfg.slippage_bps) / 10000
    fee = cfg.fee_bps / 10000
    peak, dd = cfg.initial_cash, 0.
    next_checkpoint = bars[0]['open_ms'] + cfg.checkpoint_ms

    def event(t, kind, **details):
        nonlocal previous_hash
        body = dict(sequence=len(ledger), time_ms=t, kind=kind, cash=cash,
                    quantity=quantity, basis=basis, known_realized_pnl=realized,
                    fees_paid=fees, uncertain=uncertain, previous_hash=previous_hash,
                    **details)
        previous_hash = digest(body)
        ledger.append({**body, 'event_sha256': previous_hash})

    def close(t, raw, kind):
        nonlocal cash, quantity, basis, realized, fees, entry_reference
        execution = raw * (1 - impact)
        charged = execution * quantity * fee
        proceeds = execution * quantity - charged
        pnl = proceeds - basis
        cash += proceeds
        fees += charged
        realized += pnl
        quantity, basis, entry_reference = 0., 0., None
        event(t, kind, raw_model_price=raw, execution_price=execution,
              modeled_fill=True, actual_fill=False, filled_quantity=cfg.quantity, pnl=pnl)

    def unknown(t, reason):
        nonlocal uncertain
        uncertain = True
        event(t, reason, modeled_fill=False, actual_fill=False, pnl=None)

    # An unobserved entry quote is not evidence that the policy abstained. Keep
    # the modeled cash path as a conditional subtotal, but mask policy totals.
    due = {}
    for s in scheduled:
        due.setdefault(s['scheduled_ms'], []).append(s)
    for b in bars:
        t = b['open_ms']
        timestamp_collision = len(due.get(t, [])) > 1
        for s in due.get(t, []):
            status = 'NO_SIGNAL'
            if timestamp_collision:
                unknown(t, 'UNKNOWN_SIGNAL_TIMESTAMP_COLLISION')
            if uncertain:
                status = 'BLOCKED_PRIOR_UNKNOWN'
            elif s['stale']:
                status = 'STALE_INDICATOR'
                if quantity:
                    unknown(t, status)
            elif s['action'] == 'ENTER_LONG':
                if quantity:
                    status = 'CAPACITY_HELD'
                elif not b['modeled_quote']:
                    status = 'UNKNOWN_ENTRY_QUOTE'
                    unknown(t, status)
                else:
                    execution = b['open'] * (1 + impact)
                    charged = execution * cfg.quantity * fee
                    debit = execution * cfg.quantity + charged
                    if not math.isfinite(debit):
                        raise ValueError('ACCOUNTING_OVERFLOW')
                    if debit > cash:
                        status = 'CAPITAL_REJECTED'
                    else:
                        cash -= debit
                        basis, quantity, entry_reference = debit, cfg.quantity, b['open']
                        fees += charged
                        status = 'MODELED_ENTRY'
                        event(t, status, execution_price=execution, modeled_fill=True,
                              actual_fill=False, filled_quantity=cfg.quantity)
            elif s['action'] == 'EXIT_LONG' and cfg.indicator_exit and quantity:
                # OHLC alone does not certify executable open-vs-overlay ordering.
                hit_tp = cfg.tp_fraction is not None and b['high'] >= entry_reference * (1 + cfg.tp_fraction)
                hit_sl = cfg.sl_fraction is not None and b['low'] <= entry_reference * (1 - cfg.sl_fraction)
                if hit_tp or hit_sl:
                    unknown(t, 'UNKNOWN_INDICATOR_OVERLAY_COLLISION')
                    status = 'UNKNOWN_INDICATOR_OVERLAY_COLLISION'
                elif not b['modeled_quote']:
                    unknown(t, 'UNKNOWN_EXIT_QUOTE')
                    status = 'UNKNOWN_EXIT_QUOTE'
                else:
                    close(t, b['open'], 'MODELED_INDICATOR_EXIT')
                    status = 'MODELED_INDICATOR_EXIT'
            opportunities.append({**s, 'status': status, 'scored_return': None})
        if quantity and not uncertain:
            tp = entry_reference * (1 + cfg.tp_fraction) if cfg.tp_fraction is not None else None
            sl = entry_reference * (1 - cfg.sl_fraction) if cfg.sl_fraction is not None else None
            target = tp is not None and b['high'] >= tp
            stop = sl is not None and b['low'] <= sl
            if target or stop:
                if target and stop:
                    ambiguous += 1
                if not b['modeled_quote']:
                    unknown(t, 'UNKNOWN_EXIT_QUOTE')
                elif target and stop and path == 'FACTUAL':
                    unknown(t, 'UNKNOWN_EXIT_ORDER')
                else:
                    use_target = target and (not stop or path == 'TARGET_FIRST')
                    raw = max(tp, b['open']) if use_target else min(sl, b['open'])
                    close(t, raw, 'MODELED_TARGET_EXIT' if use_target else 'MODELED_STOP_EXIT')
        if not all(math.isfinite(x) for x in (cash, quantity, basis, realized, fees)) or cash < 0 or not math.isclose(
                cash + basis, cfg.initial_cash + realized, rel_tol=1e-12, abs_tol=1e-9):
            raise ValueError('ACCOUNTING_CONSERVATION_FAILED')
        equity = cash + quantity * b['close']
        if not math.isfinite(equity):
            raise ValueError('MARK_OVERFLOW')
        peak = max(peak, equity)
        dd = max(dd, (peak - equity) / peak)
        checkpoint = b['close_ms'] + 1 >= next_checkpoint
        if checkpoint:
            next_checkpoint += ((b['close_ms'] + 1 - next_checkpoint) // cfg.checkpoint_ms + 1) * cfg.checkpoint_ms
        marks.append({'time_ms': b['close_ms'] + 1, 'sampled_mtm': None if uncertain else equity,
                      'conditional_held_inventory_mark': equity if uncertain else None,
                      'checkpoint': checkpoint, 'realized_pnl': None if uncertain else realized})
        event(b['close_ms'] + 1, 'CHECKPOINT_MTM' if checkpoint else 'SAMPLED_MTM',
              equity=None if uncertain else equity)
    last_open = bars[-1]['open_ms']
    for s in scheduled:
        if s['scheduled_ms'] > last_open:
            # An entry with no observable next OPEN is not an abstention or a
            # zero-return trade. It leaves the whole-policy outcome unknown.
            # A terminal exit likewise cannot be counted as a realized fill.
            terminal_entry = s['action'] == 'ENTER_LONG' and not quantity
            terminal_exit = s['action'] == 'EXIT_LONG' and cfg.indicator_exit and bool(quantity)
            terminal_unknown = (terminal_entry or terminal_exit) and not s['stale']
            opportunities.append({**s, 'status': ('UNKNOWN_NO_ELIGIBLE_OPEN' if terminal_unknown
                else 'STALE_INDICATOR' if s['stale'] else 'NO_TERMINAL_ACTION'),
                'scored_return': None})
            if terminal_unknown and not uncertain:
                unknown(s['scheduled_ms'], 'UNKNOWN_NO_ENTRY_OPEN' if terminal_entry else 'UNKNOWN_NO_EXIT_OPEN')
    status = 'UNKNOWN_UNRESOLVED' if uncertain else 'OPEN_UNRESOLVED' if quantity else 'SETTLED_MODELED'
    return {'path': path, 'scenario': path != 'FACTUAL', 'status': status,
            'scheduled_denominator': len(scheduled), 'opportunities': opportunities,
            'ambiguous_events': ambiguous, 'cash': cash, 'held_quantity': quantity,
            'held_cost_basis': basis, 'fees_paid': fees, 'known_realized_pnl': realized,
            'realized_pnl': None if uncertain else realized,
            'settled_equity': cash if not quantity and not uncertain else None,
            'unsettled_sampled_equity': equity if quantity and not uncertain else None,
            'modeled_equity_return': equity / cfg.initial_cash - 1 if not uncertain else None,
            'sampled_mtm_drawdown': None if uncertain else dd, 'marks': marks,
            'ledger': ledger, 'ledger_head_sha256': previous_hash}


def verify_receipt(receipt):
    """Recompute source, signals, complete downstream state, and every chain."""
    try:
        cfg = Config(**receipt['config'])
        if receipt['strategy'] == STRATEGY:
            expected = _replay_impl(receipt['input_rows'], source=receipt['source'], config=cfg)
        elif receipt['strategy'] == 'CONTRACT_FIXTURE_ONLY_1':
            expected = replay_contract_fixture(receipt['input_rows'], source=receipt['source'],
                                                signals=receipt['signals'], config=cfg)
        else:
            return False
        return receipt == expected
    except (ValueError, KeyError, TypeError, OverflowError):
        return False
