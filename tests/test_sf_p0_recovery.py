"""P0 recovery tests. All data in this file is SYNTHETIC, never market evidence."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from research_wp_r0.synthetic_execution import account_long_prices, execute_synthetic_long
from research_wp_r0.ema_first_backtest import ema_crossover_decisions, frozen_ema_plan
from research_wp_r0.indicator_library_v2 import _ema
from research_wp_r0.pinned_ema_research import run_pinned_ema_development
from tests.test_sf_pinned_ema_research import make_archive
from tests.test_sf_ema_first_backtest import bars


@pytest.mark.parametrize('exit_price', [95, 100, 105])
def test_notional_accounting_golden(exit_price):
    a = account_long_prices(100, exit_price, fee_bps=10, slippage_bps=5)
    entry, exit_ = 100 * 1.0005, exit_price * .9995
    expected = exit_ / entry - 1 - .001 * (1 + exit_ / entry)
    assert a['net_return'] == expected
    assert a['raw_gross_return'] - a['slippage_fraction'] - a['fee_fraction'] == pytest.approx(expected)
    # Exercise the accepted #108 engine, rather than only a mirrored helper.
    rows = [{'bar_open': i*60000, 'bar_close': (i+1)*60000-1,
             'open': p, 'high': p+1, 'low': p-1, 'close': p}
            for i,p in enumerate([100,100,exit_price])]
    # Stop reached on third bar; exact opening gap is the execution price.
    if exit_price == 95:
        r = execute_synthetic_long(rows,0,stop_fraction=.02,target_fraction=.5,
            ttl_bars=1,holding_bars=2,fee_bps=10,slippage_bps=5)
        assert r['status'] == 'RESOLVED_STOP'
        assert r['details']['net_return'] == expected


def test_borderline_v2_exact_prefix_and_warmup():
    prices = [100.] * 24 + [100.000000000001, 99.999999999999, 100.000000000002]
    records = bars(prices)
    decisions = ema_crossover_decisions(records)
    assert decisions[0].bar_open_ms == records[21][0]
    for i,d in enumerate(decisions,21):
        assert d.ema_fast == _ema(prices[:i+1],8)[-1]
        assert d.ema_slow == _ema(prices[:i+1],21)[-1]
        assert ema_crossover_decisions(records[:i+1])[-1] == d


@pytest.mark.parametrize('change', ['split_cutoff_ms','fee_bps','slippage_bps','source_reference'])
def test_separately_frozen_plan_rejects_changed_assumption(tmp_path,change):
    path,sha,start = make_archive(tmp_path)
    args = dict(archive_sha256=sha,source_reference='synthetic',split_cutoff_ms=start+38*60000)
    _, expected = frozen_ema_plan(**args)
    args[change] = {'split_cutoff_ms':start+39*60000,'fee_bps':11,
                    'slippage_bps':6,'source_reference':'changed'}[change]
    with pytest.raises(ValueError,match='plan commitment'):
        run_pinned_ema_development(path,expected_plan_sha256=expected,**args)


def test_cross_process_report_and_snapshot_tamper_evidence(tmp_path):
    path,sha,start = make_archive(tmp_path)
    args=dict(archive_sha256=sha,source_reference='synthetic',split_cutoff_ms=start+38*60000)
    _, expected=frozen_ema_plan(**args)
    args['expected_plan_sha256']=expected
    script = ('import json; from research_wp_r0.pinned_ema_research import run_pinned_ema_development; '
              f'print(json.dumps(run_pinned_ema_development({str(path)!r}, **{args!r}),sort_keys=True))')
    first=subprocess.check_output([sys.executable,'-B','-c',script])
    assert first == subprocess.check_output([sys.executable,'-B','-c',script])
    plan_file=tmp_path/'plan.json'
    plan_file.write_text(json.dumps({k:v for k,v in args.items() if k != 'expected_plan_sha256'}))
    output=tmp_path/'output.json'
    subprocess.check_call([sys.executable,'-B','-m','scripts.sf_ema_development',
        '--archive',str(path),'--plan-arguments',str(plan_file),
        '--expected-plan-sha256',expected,'--output',str(output)])
    assert json.loads(output.read_text()) == json.loads(first)
    # Existing artifacts cannot be overwritten by rerunning the CLI.
    assert subprocess.run([sys.executable,'-B','-m','scripts.sf_ema_development',
        '--archive',str(path),'--plan-arguments',str(plan_file),
        '--expected-plan-sha256',expected,'--output',str(output)],capture_output=True).returncode != 0
    report=json.loads(first)['development_report']
    for e in report['opportunities']:
        digest=e['snapshot_sha256']
        e=e['decision_snapshot']
        assert hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()==digest
        e['ema_fast'] += 1
        assert hashlib.sha256(json.dumps(e,sort_keys=True,separators=(',',':')).encode()).hexdigest()!=digest
    assert report['no_fill_count']==report['expired_count']==0
    assert set(report['regime_results'])=={'TARGET','OFF_TARGET'}


def test_next_open_price_not_decision_close_and_terminal_unknown():
    from research_wp_r0.ema_development_replay import replay_ema_development
    data=list(bars([100.]*24+[105.]*6+[90.]*7))
    r=replay_ema_development(data,split_cutoff_ms=data[-1][0]+60000)
    t=r['trades'][0]
    assert t['entry_open_ms'] == next(e['next_open_ms'] for e in r['opportunities'] if e['status']=='SIMULATED_ENTRY')
    i=next(i for i,b in enumerate(data) if b[0]==t['entry_open_ms'])
    b=data[i];data[i]=(b[0],b[1],106.,107.,b[4],b[5],b[6])
    changed=replay_ema_development(data,split_cutoff_ms=data[-1][0]+60000)
    assert changed['trades'][0]['entry_price']==106.
    assert changed['trades'][0]['net_return_bps']!=t['net_return_bps']


def test_archive_market_identity_and_fixed_strategy(tmp_path):
    from research_wp_r0.retrospective_kline_intake import inspect_binance_spot_zip
    path,sha,start=make_archive(tmp_path)
    for changes in ({'symbol':'ETHUSDT'}, {'interval_ms':120000}):
        with pytest.raises(ValueError,match='identity'):
            inspect_binance_spot_zip(path,expected_sha256=sha,**changes)
    with pytest.raises(ValueError,match='frozen'):
        frozen_ema_plan(archive_sha256=sha,source_reference='synthetic',split_cutoff_ms=start+38*60000,fast=9)
