"""Focused DEV contract falsifiers. All candles and signals are fabricated."""
from copy import deepcopy
from dataclasses import replace
import pytest
from research_wp_r0.historical_dev_exits_v1 import (
    Config, PATHS, STRATEGY, digest, replay, replay_contract_fixture, verify_receipt)
from research_wp_r0.ema_first_backtest import ema_crossover_decisions

I = 60000


def bars(prices=None):
    prices = prices or [(100, 101, 99, 100)] * 6
    return [dict(open_ms=i*I, close_ms=(i+1)*I-1, open=o, high=h, low=l,
                 close=c, volume=1, available_ms=(i+1)*I, modeled_quote=True)
            for i, (o, h, l, c) in enumerate(prices)]


def source(bs):
    return dict(rows_sha256=digest(bs), archive_sha256='a'*64,
                version='fabricated-v1', reference='SYNTHETIC_TEST_ONLY',
                availability_evidence='UNKNOWN', correction_evidence='PINNED_VERSION_ONLY')


def signal(i, action, bs):
    return dict(bar_open_ms=i*I, action=action, available_ms=bs[i]['available_ms'])


def run(bs=None, actions=((0, 'ENTER_LONG'),), cfg=None):
    bs = bs or bars()
    return replay_contract_fixture(bs, source=source(bs),
        signals=[signal(i, action, bs) for i, action in actions],
        config=cfg or Config(latency_ms=0, fee_bps=0, spread_bps=0, slippage_bps=0))


def path(r, name='FACTUAL'):
    return r['paths'][name]


def test_three_paths_downstream_capacity_not_posthoc_pnl():
    bs = bars([(100,101,99,100), (100,120,80,100), (100,101,99,100)])
    cfg = Config(initial_cash=100, latency_ms=0, tp_fraction=.1, sl_fraction=.1,
                 fee_bps=0, spread_bps=0, slippage_bps=0)
    r = run(bs, ((0,'ENTER_LONG'), (1,'ENTER_LONG')), cfg)
    a, t, s = (path(r, p) for p in PATHS)
    assert a['status'] == 'UNKNOWN_UNRESOLVED'
    assert a['realized_pnl'] is None and a['held_quantity'] == 1
    assert a['opportunities'][1]['status'] == 'BLOCKED_PRIOR_UNKNOWN'
    assert a['settled_equity'] is None
    assert t['held_quantity'] == 1 and t['cash'] == pytest.approx(10)
    assert s['held_quantity'] == 0 and s['cash'] == pytest.approx(90)
    assert s['opportunities'][1]['status'] == 'CAPITAL_REJECTED'
    assert t['opportunities'][1]['status'] == 'MODELED_ENTRY'
    assert all(p['scheduled_denominator'] == 2 for p in (a,t,s))
    assert a['ledger'][1]['kind'] == 'MODELED_ENTRY'
    assert any(e['kind'] == 'UNKNOWN_EXIT_ORDER' and e['pnl'] is None for e in a['ledger'])
    assert all(p['ambiguous_events'] == 1 for p in (a,t,s))
    assert verify_receipt(r)


@pytest.mark.parametrize('high,low,kind,pnl', [(111,99,'TARGET',10), (101,89,'STOP',-10)])
def test_single_overlay(high, low, kind, pnl):
    bs = bars([(100,101,99,100),(100,high,low,100)])
    cfg = Config(latency_ms=0,tp_fraction=.1,sl_fraction=.1,fee_bps=0,spread_bps=0,slippage_bps=0)
    r = run(bs,cfg=cfg)
    for p in r['paths'].values():
        assert p['realized_pnl'] == pytest.approx(pnl)
        assert p['status'] == 'SETTLED_MODELED'
        assert any(e['kind'] == 'MODELED_'+kind+'_EXIT' and not e['actual_fill'] for e in p['ledger'])


def test_checkpoint_no_forced_close_and_inventory_conservation():
    bs = bars([(100,101,99,100)] * 1450)
    p = path(run(bs))
    assert p['status'] == 'OPEN_UNRESOLVED'
    assert p['settled_equity'] is None and p['held_quantity'] == 1
    assert p['cash'] + p['held_cost_basis'] == 1000
    assert p['realized_pnl'] == 0
    assert any(m['checkpoint'] for m in p['marks'])
    assert not any('EXIT' in e['kind'] for e in p['ledger'])


def test_indicator_exit_costs_and_conservation():
    cfg = Config(latency_ms=0,fee_bps=10,spread_bps=4,slippage_bps=3)
    p = path(run(actions=((0,'ENTER_LONG'),(2,'EXIT_LONG')),cfg=cfg))
    entry = 100*1.0005*1.001
    proceeds = 100*.9995*.999
    assert p['cash'] == pytest.approx(1000-entry+proceeds)
    assert p['realized_pnl'] == pytest.approx(proceeds-entry)
    assert p['fees_paid'] == pytest.approx(100*1.0005*.001 + 100*.9995*.001)
    assert p['held_quantity'] == 0


def test_latency_waits_for_first_eligible_open():
    p = path(run(cfg=Config(latency_ms=1)))
    assert p['opportunities'][0]['scheduled_ms'] == 2*I
    assert next(e for e in p['ledger'] if e['kind']=='MODELED_ENTRY')['time_ms'] == 2*I


@pytest.mark.parametrize('branch', PATHS)
def test_missing_quote_cannot_fabricate_even_hypothetical_exit(branch):
    # Entry on bar 1, then missing modeled exit quote on bar 2.
    bs = bars([(100,101,99,100),(100,101,99,100),(100,120,80,100)])
    bs[2]['modeled_quote'] = False
    p = path(run(bs,cfg=Config(latency_ms=0,tp_fraction=.1,sl_fraction=.1)),branch)
    assert p['realized_pnl'] is None and p['held_quantity'] == 1
    assert any(e['kind']=='UNKNOWN_EXIT_QUOTE' for e in p['ledger'])


def test_missing_entry_quote_and_full_denominator():
    bs=bars(); bs[1]['modeled_quote']=False
    p=path(run(bs,((0,'ENTER_LONG'),(1,'HOLD'))))
    assert p['scheduled_denominator']==2
    assert p['opportunities'][0]['status']=='UNKNOWN_ENTRY_QUOTE'
    assert p['cash']==1000 and p['held_quantity']==0


def test_missing_exit_open_is_unknown_not_zero():
    r=run(actions=((0,'ENTER_LONG'),(5,'EXIT_LONG')))
    p=path(r)
    assert p['realized_pnl'] is None
    assert p['opportunities'][-1]['status']=='UNKNOWN_NO_ELIGIBLE_OPEN'
    assert p['status']=='UNKNOWN_UNRESOLVED' and verify_receipt(r)


def test_indicator_overlay_collision_unknown_in_all_paths():
    bs=bars([(100,101,99,100),(100,101,99,100),(100,120,80,100)])
    r=run(bs,((0,'ENTER_LONG'),(1,'EXIT_LONG')),Config(latency_ms=0,tp_fraction=.1,sl_fraction=.1))
    assert all(p['realized_pnl'] is None for p in r['paths'].values())
    assert all(any(e['kind']=='UNKNOWN_INDICATOR_OVERLAY_COLLISION' for e in p['ledger']) for p in r['paths'].values())


@pytest.mark.parametrize('mutation,reason', [
    (lambda b: b[1].update(open_ms=9*I),'GAP'),
    (lambda b: b[1].update(open=None),'OHLC'),
    (lambda b: b[1].update(high=90),'OHLCV'),
    (lambda b: b[1].update(volume=float('inf')),'Out of range|OHLCV'),
    (lambda b: b[1].update(available_ms=None),'AVAILABILITY'),
    (lambda b: b[1].update(modeled_quote=None),'QUOTE'),
])
def test_bad_inputs_fail_closed(mutation,reason):
    bs=bars(); mutation(bs)
    with pytest.raises(ValueError,match=reason):
        run(bs)


@pytest.mark.parametrize('cfg', [Config(fee_bps=-1),Config(spread_bps=True),Config(slippage_bps=float('nan')),
                                  Config(quantity=0),Config(sl_fraction=1),Config(latency_ms=-1)])
def test_bad_config(cfg):
    with pytest.raises(ValueError): run(cfg=cfg)


def test_stale_signal_never_trades():
    bs=bars();bs[0]['available_ms']=4*I
    p=path(run(bs,cfg=Config(max_signal_age_ms=I,latency_ms=0)))
    assert p['opportunities'][0]['status']=='STALE_INDICATOR'
    assert p['held_quantity']==0


def test_missing_correction_evidence_or_digest_denied():
    bs=bars(); src=source(bs)
    for key in ('correction_evidence','rows_sha256','version','availability_evidence','archive_sha256'):
        changed={**src};changed.pop(key)
        with pytest.raises(ValueError,match='SOURCE_VERSION'):
            replay_contract_fixture(bs,source=changed,signals=[])


def test_determinism_chain_and_receipt_tampering():
    r=run();assert r==run() and verify_receipt(r)
    for field in ('cash','known_realized_pnl','ledger_head_sha256'):
        forged=deepcopy(r);forged['paths']['FACTUAL'][field]='forged'
        assert not verify_receipt(forged)
    forged=deepcopy(r);forged['paths']['FACTUAL']['ledger'][1]['cash']=123
    assert not verify_receipt(forged)
    for p in r['paths'].values():
        prev='0'*64
        for event in p['ledger']:
            body={k:v for k,v in event.items() if k!='event_sha256'}
            assert body['previous_hash']==prev
            assert digest(body)==event['event_sha256'];prev=event['event_sha256']


def test_fixed_ema_v2_signal_semantics_and_prefix_invariance():
    bs=bars([(100+i%9,101+i%9,99+i%9,100+i%9) for i in range(50)])
    r=replay(bs,source=source(bs),config=Config(latency_ms=0))
    records=[(b['open_ms'],b['close_ms'],b['open'],b['high'],b['low'],b['close'],b['volume']) for b in bs]
    expected=ema_crossover_decisions(records)
    assert r['strategy']==STRATEGY
    assert [s['action'] for s in r['signals']]==[d.signal for d in expected]
    prefix=replay(bs[:40],source=source(bs[:40]),config=Config(latency_ms=0))
    assert prefix['signals']==r['signals'][:len(prefix['signals'])]
    assert verify_receipt(r) and not r['claims']['as_known_at_cutoff']


def test_insufficient_ema_history_fails_closed():
    bs=bars()
    with pytest.raises(ValueError,match='warmup'): replay(bs,source=source(bs))


def test_indicator_exit_can_be_disabled():
    p=path(run(actions=((0,'ENTER_LONG'),(1,'EXIT_LONG')),cfg=Config(latency_ms=0,indicator_exit=False)))
    assert p['held_quantity']==1 and p['status']=='OPEN_UNRESOLVED'


def test_simultaneous_delayed_signals_unknown_without_source_order():
    bs=bars();bs[0]['available_ms']=2*I
    p=path(run(bs,((0,'ENTER_LONG'),(1,'EXIT_LONG'))))
    assert p['held_quantity']==0 and p['status']=='UNKNOWN_UNRESOLVED'


def test_gap_stop_uses_adverse_open_not_unattainable_stop():
    bs=bars([(100,101,99,100),(100,101,99,100),(70,75,65,70)])
    p=path(run(bs,cfg=Config(latency_ms=0,sl_fraction=.1,fee_bps=0,spread_bps=0,slippage_bps=0)))
    assert p['realized_pnl']==-30


def test_delayed_warmup_history_delays_all_dependent_ema_signals():
    bs=bars([(100+i%9,101+i%9,99+i%9,100+i%9) for i in range(50)])
    bs[0]['available_ms']=40*I
    r=replay(bs,source=source(bs),config=Config(latency_ms=0,max_signal_age_ms=I))
    assert r['signals'][0]['available_ms']==40*I
    assert path(r)['opportunities'][0]['stale']
    assert verify_receipt(r)


def test_unknown_is_never_an_opportunity_zero_score():
    bs=bars();bs[1]['modeled_quote']=False
    p=path(run(bs))
    assert p['opportunities'][0]['scored_return'] is None


def test_each_ledger_state_preserves_cash_cost_basis_and_known_pnl():
    r=run(actions=((0,'ENTER_LONG'),(2,'EXIT_LONG'),(3,'ENTER_LONG')),
          cfg=Config(latency_ms=0))
    for p in r['paths'].values():
        for e in p['ledger']:
            assert e['cash']>=0 and e['quantity'] in (0,1)
            assert e['cash']+e['basis']==pytest.approx(1000+e['known_realized_pnl'])
