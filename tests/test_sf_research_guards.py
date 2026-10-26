"""Synthetic deterministic acceptance only. No market data/download or OOS run."""
import hashlib
import json

import pytest

from research_wp_r0.ema_development_replay import replay_ema_development
from research_wp_r0.ema_first_backtest import frozen_ema_plan
from research_wp_r0.research_guards import ResearchGuardPlan, run_guarded_development, COSTS
from research_wp_r0.strategy_definition import digest
from research_wp_r0.synthetic_execution import account_long_prices

START = 1704067200000


def data(delta=60000, prices=None):
    prices = prices or [100.] * 24 + [105.] * 6 + [90.] * 8 + [110.] * 5
    return tuple((START+i*delta, START+(i+1)*delta-1, p, p+1, p-1, p, 10) for i,p in enumerate(prices))


def plan_for(rows, evidence=None, *, delta=60000, additions=(), timing=None, split=None):
    essential=lambda name: {'name':name,'criticality':'ESSENTIAL','role':'SIGNAL',
        'max_age_ms':delta,'supporting_effect':None,'missing_fallback':None}
    return ResearchGuardPlan({'schema_version':'sf-research-guards-1',
        'strategy_id':'EMA_8_21_CROSS_LONG_ONLY','strategy_version':'SF-IND-02:2:_ema:fsum',
        'scope':'HISTORICAL_DEVELOPMENT_ONLY','data_sha256':digest(rows),
        'evidence_sha256':digest(evidence or {}),'split_cutoff_ms':split or rows[-1][1]+1,
        'interval_ms':delta,'timing':timing or {'mode':'RETROSPECTIVE_UNVERIFIED_TIMING','guard_ms':None,'override_basis':None},
        'inputs':[essential(n) for n in ('candles','ema_8','ema_21')]+list(additions),
        'costs':COSTS,'capital_policy':'ONE_BTC_100000_USDT_COMMON_STRESS_CAPITAL_ENVELOPE',
        'protection_policy':'UNRESOLVED_STOP_NEW_ENTRIES_NO_INVENTED_EXIT'})


def run(rows, evidence=None, **kwargs):
    plan=plan_for(rows,evidence,**kwargs)
    return run_guarded_development(rows,plan=plan,expected_plan_digest=plan.digest,evidence=evidence or {})


def supporting():
    return {'name':'dominance','criticality':'SUPPORTING','role':'CONTEXT','max_age_ms':60000,
            'supporting_effect':'AUDIT_ONLY','missing_fallback':'BASE_SIGNAL_WITH_UNKNOWN_CONTEXT'}


@pytest.mark.parametrize('delta', [60000,300000,3600000])
def test_delay_applies_to_entry_exit_and_correct_benchmark(delta):
    rows=data(delta);r=run(rows,delta=delta)['scenarios']['BASE']
    assert r['trades'][0]['entry_open_ms']==rows[26][0]
    assert all(e['next_open_ms']==e['decision_cutoff_ms']+delta for e in r['opportunities'])
    assert r['benchmark_window'][0]==rows[23][0]
    assert r['trades'][0]['exit_open_ms']>r['trades'][0]['entry_open_ms']
    assert all(e['actual_fill_evidence']=='NOT_OBSERVED' for e in r['opportunities'][21:])


def test_pinned_override_threshold_and_no_unjustified_override():
    rows=data();p=plan_for(rows,timing={'mode':'RETROSPECTIVE_UNVERIFIED_TIMING','guard_ms':60001,'override_basis':'synthetic frozen timing study'})
    assert p.eligible_open(START+22*60000)==START+24*60000
    with pytest.raises(ValueError,match='basis'):
        plan_for(rows,timing={'mode':'RETROSPECTIVE_UNVERIFIED_TIMING','guard_ms':0,'override_basis':''})


def test_verified_mode_missing_receipts_fails_closed_without_fallback():
    r=run(data(),timing={'mode':'VERIFIED_TIMESTAMPED','guard_ms':None,'override_basis':None})
    assert r['status']=='UNRESOLVED' and r['scenarios'] is None
    assert r['reason']=='VERIFIED_RECEIPT_READY_BINDING_NOT_IMPLEMENTED'


def test_first_eligible_gap_and_intervening_gap_no_favorable_skip():
    for missing in (25,26):
        rows=tuple(b for i,b in enumerate(data()) if i!=missing)
        r=run(rows)['scenarios']['BASE']
        enter=next(e for e in r['opportunities'] if e['signal']=='ENTER_LONG')
        assert enter['status']=='UNRESOLVED_NO_NEXT_BAR'
        assert enter['eligibility_reason']=='FIRST_ELIGIBLE_BAR_OR_COVERAGE_MISSING'
        assert r['closed_trade_count']==0 and r['open_position'] is None
        assert r['terminal_equity_quote'] is None and r['drawdown_status']=='PARTIAL_COVERAGE'
        assert r['no_fill_count']==0


def test_delayed_candidate_at_split_is_unresolved_without_reading_oos():
    rows=data()[:26];r=run(rows)['scenarios']['BASE']
    e=next(e for e in r['opportunities'] if e['signal']=='ENTER_LONG')
    assert e['next_open_ms']==rows[-1][1]+1
    assert e['status']=='UNRESOLVED_NO_NEXT_BAR' and e['eligibility_reason']=='DEVELOPMENT_BOUNDARY'
    assert r['open_position'] is None


def test_pair_uses_common_opportunities_and_both_notional_costs():
    result=run(data());base,stress=(result['scenarios'][n] for n in ('BASE','STRESS'))
    assert base['opportunities']==stress['opportunities']
    assert base['trades'][0]['entry_open_ms']==stress['trades'][0]['entry_open_ms']
    assert stress['trades'][0]['net_pnl_quote']<base['trades'][0]['net_pnl_quote']
    a=account_long_prices(100,105,fee_bps=10,slippage_bps=5)
    assert a['net_return']*a['entry_execution_price']==pytest.approx(4.6925025)
    assert base['open_position'] is not None  # separate open mark, not a closed trade


def test_stress_capital_envelope_prevents_cost_conditioned_selection():
    rows=data(prices=[99800.]*24+[99820.]*6+[99700.]*8+[99900.]*5)
    result=run(rows)
    for r in result['scenarios'].values():
        assert r['outcome_counts']['REJECTED_CAPITAL_LIMIT']>0
        assert r['open_position'] is None
    assert result['scenarios']['BASE']['opportunities']==result['scenarios']['STRESS']['opportunities']


@pytest.mark.parametrize('state',['MISSING','STALE','NONFINAL','INVALID'])
def test_missing_essential_blocks_entry_not_hold(state):
    rows=data();evidence={str(rows[24][1]+1):{'ema_8':{'state':state}}}
    r=run(rows,evidence)['scenarios']['BASE'];event=r['opportunities'][24]
    assert event['status']=='BLOCKED_MISSING_REQUIRED_DATA' and event['signal'] is None
    assert event['input_assessment']['reasons']==['ema_8:'+state]
    assert event['snapshot_sha256']


def test_supporting_missing_or_conflicting_is_unknown_or_audit_only():
    rows=data();missing=run(rows,additions=[supporting()])['scenarios']['BASE']
    event=missing['opportunities'][24]
    assert event['status']=='SIMULATED_ENTRY'
    audit=event['decision_snapshot']['input_assessment']['inputs']['dominance']
    assert audit['value']=='UNKNOWN' and audit['audit']=='SUPPORTING_DATA_MISSING'
    evidence={str(rows[24][1]+1):{'dominance':{'state':'VALID','value':False,'as_of_ms':rows[24][1]+1}}}
    present=run(rows,evidence,additions=[supporting()])['scenarios']['BASE']
    assert present['opportunities'][24]['signal']=='ENTER_LONG'
    bad=supporting();bad['missing_fallback']=None
    with pytest.raises(ValueError,match='fallback'):
        plan_for(rows,additions=[bad])


@pytest.mark.parametrize('role',['HARD_VETO','RISK_GATE','LIQUIDITY_GATE','SAFETY_GATE'])
def test_mislabeled_required_gate_cannot_be_supporting(role):
    item=supporting();item['role']=role
    with pytest.raises(ValueError,match='cannot be SUPPORTING'):
        plan_for(data(),additions=[item])


def test_missing_hard_veto_and_stale_or_future_supporting():
    rows=data();item=supporting();item.update(criticality='ESSENTIAL',role='HARD_VETO',supporting_effect=None,missing_fallback=None)
    r=run(rows,additions=[item])['scenarios']['BASE']
    assert r['outcome_counts']['SIMULATED_ENTRY']==0
    for as_of in (rows[24][1]+2,rows[22][0]):
        evidence={str(rows[24][1]+1):{'dominance':{'state':'VALID','value':50,'as_of_ms':as_of}}}
        r=run(rows,evidence,additions=[supporting()])['scenarios']['BASE']
        assert r['opportunities'][24]['input_assessment']['inputs']['dominance']['value']=='UNKNOWN'


def test_required_loss_while_holding_stops_new_entries_and_disclaims_protection():
    rows=data();evidence={str(rows[27][1]+1):{'candles':{'state':'MISSING'}}}
    r=run(rows,evidence)['scenarios']['BASE']
    assert r['open_position']['status']=='UNRESOLVED_PROTECTION_REQUIRED'
    assert r['protection_status']=='UNRESOLVED_PROTECTION_REQUIRED'
    assert r['terminal_equity_quote'] is None and r['portfolio_net_return_fraction'] is None
    assert r['closed_trade_count']==0
    assert all(e['signal'] is None for e in r['opportunities'][27:])
    assert 'PRIOR_REQUIRED_LOSS_POSITION_PROTECTION_UNRESOLVED' in r['opportunities'][28]['input_assessment']['reasons']


def test_required_warmup_and_short_history_are_blocked_not_synthetic_holds():
    r=run(data()[:10])['scenarios']['BASE']
    assert len(r['opportunities'])==10
    assert all(e['signal'] is None and e['status']=='BLOCKED_MISSING_REQUIRED_DATA' for e in r['opportunities'])
    assert r['benchmark_window'] is None


def test_frozen_plan_data_and_evidence_mismatch_and_immutability():
    rows=data();p=plan_for(rows);value=p.spec;value['timing']['guard_ms']=0
    assert p.spec['timing']['guard_ms'] is None
    for change in ('plan','evidence','data'):
        with pytest.raises(ValueError,match='mismatch'):
            run_guarded_development(rows if change!='data' else rows[:-1],plan=p,
                expected_plan_digest='f'*64 if change=='plan' else p.digest,
                evidence={str(rows[24][1]+1):{}} if change=='evidence' else {})


def test_legacy_synthetic_golden_and_old_frozen_p0_plan_unchanged():
    rows=data();r=replay_ema_development(rows,split_cutoff_ms=rows[-1][1]+1)
    assert r['report_sha256']=='ef1bdd5ab2c0cb7e60fc7068e5c1aa8d32110f161961ad18cad5f4f93f294895'
    assert hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()=='d34cad3a0d5fe02762bd8f57eee4d6a79a86da9eafb339fc9323c3d934679775'
    args={'archive_sha256':'4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e',
          'source_reference':'https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip',
          'split_cutoff_ms':1704153600000,'fee_bps':10,'slippage_bps':5}
    assert frozen_ema_plan(**args)[1]=='a804e75d43ca0cd57988e7b44873d4179be198fea3c452ec7b38a9a9b9f8ad1b'


def test_missing_required_candle_taints_derived_history_without_silent_resume():
    rows=data();evidence={str(rows[20][1]+1):{'candles':{'state':'MISSING'}}}
    r=run(rows,evidence)['scenarios']['BASE']
    assert r['outcome_counts']['SIMULATED_ENTRY']==0
    assert all(e['signal'] is None for e in r['opportunities'][20:])
    assert r['opportunities'][24]['ema_fast'] is None
    assert 'EMA_HISTORY_TAINTED_REQUIRED_CANDLE' in r['opportunities'][24]['input_assessment']['reasons']
