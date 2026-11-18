"""R1 actual Core handoff -> denominator-preserving MARKET_ONLY observations.

Only the pinned historical research producer is supported. No F1 reconstruction,
strategy execution, signed excursion, hypothetical fills or external authority.
Existing B1 hash encoding, B2 bounded month/window parsers and B3 original-parent
byte checks are reused; their old runners/tests are not executed.
"""
from __future__ import annotations

import argparse
import copy
import io
import json
import math
import os
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .aql_b1_market_research import canonical, sha
from .aql_b2_market_e2e import parse_source_month, test_market_window as bounded_window
from .aql_b3_core_vault_factory import source_from_accepted_b1
from .indicator_library_v2 import _ema

CORE_HEAD = '4ab3cd6b1cbf83a52f941f22d35892376c6feee7'
CORE_ARTIFACT = 13120952732
CORE_BYTES_SHA = '4798de0525be3d94190429b653125d6f3f00d2719d9dbe3e8d5cbda4fbb6c8d6'
FACTORY_BASE = '82d2fc881a6b7572e16670216fbaff7d815dc0cc'
VAULT_HEAD = '7d97b09c0c6ee2650a61d523acb8d8c771a99c46'
INDICATOR_BLOB = '87aa21841c7b649d3b860ee1337ccc45fd08e0bf'
B1_SHA = '265b7ade1be307bd2efafbd0a8438e6846c869df6205af717133d490e38aeb59'
B1_REPORT_SHA = '1791109fcbc7a8370ca234fbd24d27bc37db1fc078a142c3b7c54ea9d55cdb11'
LOCK_SHA = '267964c81772b1a118cd740c8d8a6bc6a757e615a98d80769a68e5a12df34679'
FEATURE = 'core-pinned-indicator-library-v2._ema/r1-ema8-21-sma20.v1'
REGIME = 'aql.r1-market-regime-ema8-21.v1'
SOURCE_VERSION = '2024-retrospective-original-archive-snapshot'
BAR_MS = 900000
HOURS = (4,24,72)
ARMS = ('BASE','SHADOW')
SCOPE = 'HISTORICAL_MARKET_ONLY_RESEARCH_NOT_OPERATIONAL_PIT'


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def strict_json(raw):
    def pairs(items):
        out={}
        for key,value in items:
            require(key not in out,'DUPLICATE_JSON_KEY')
            out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=pairs,
                      parse_constant=lambda _:(_ for _ in ()).throw(ValueError('NONFINITE_JSON')))


def load_market(raw):
    require(sha(raw) == B1_SHA,'B1_ARTIFACT_PIN_DRIFT')
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        data=outer.read('b1-replay/report.json')
        require(sha(data) == B1_REPORT_SHA,'B1_REPORT_PIN_DRIFT')
        report=strict_json(data)
        require(report['lock_sha256'] == LOCK_SHA,'MARKET_LOCK_DRIFT')
        inventory={item['name']:item for item in report['originals']}
        months={}
        for month in (2,7):
            item=inventory[f'BTCUSDT-15m-2024-{month:02}.zip']
            # B3 original RAW/checksum identity and B2 original member/grid checks.
            # No Vault admission, old test runner, or old market evaluation.
            source_from_accepted_b1(outer,item)
            months[item['member_sha256']]=dict(meta=item,bars=parse_source_month(outer,item))
    return months


def expected_schedule(months):
    schedule={}
    for member,source in months.items():
        month=int(source['meta']['name'][-6:-4])
        start=int(datetime(2024,month,15,tzinfo=timezone.utc).timestamp()*1000)
        for i in range(16):
            cutoff=start+(i+1)*BAR_MS
            identity=dict(symbol='BTCUSDT',market='SPOT',interval='15m',
                          bar_close_exclusive_ms=cutoff,source_member_sha256=member,
                          feature_version=FEATURE,regime_version=REGIME)
            identity_sha=sha(canonical(identity))
            oid='R1-'+identity_sha
            pair=sha(canonical(dict(identity_sha256=identity_sha,arms=list(ARMS))))
            schedule[oid]=(pair,member,cutoff)
    require(len(schedule) == 32,'EXPECTED_SCHEDULE_MISSING')
    return schedule


def validate_handoff(doc,months):
    """Structural checks independent of transport pin, also used by adversarial tests.

    Missing opportunities violate the producer schedule and are rejected. A
    missing ARM RECORD is materialized as MISSING_CAPTURE in its scheduled slot,
    with explicit supplied=False; never a fabricated NO_SIGNAL or dropped row.
    """
    require(doc.get('schema_version') == 'aql.r1-core-research-handoff.v1','CORE_SCHEMA')
    require(doc.get('handoff_sha256') == sha(canonical({k:v for k,v in doc.items() if k!='handoff_sha256'})),
            'CORE_HANDOFF_DIGEST')
    require(doc.get('scope') == SCOPE and doc.get('original_f1_strategy_decisions') == 'NOT_SUPPLIED'
            and doc.get('external_issuer_correction_clock_and_freeze') == 'BLOCKED_EXTERNAL_EVIDENCE'
            and doc.get('g0_merge_paper_shadow_live_authorized') is False,'CORE_PROOF_SCOPE')
    require((doc.get('feature_version'),doc.get('regime_version'),doc.get('strategy_version')) ==
            (FEATURE,REGIME,'NOT_CONNECTED'),'FEATURE_REGIME_STRATEGY_VERSION')
    require(doc['sample_policy'] == dict(months=[2,7],day_utc=15,bars_per_month=16,warmup_bars=252,
                description='Two bounded time-aligned 2024 samples. Full year market lock already accepted.'),
            'SAMPLE_POLICY_DRIFT')
    src=doc['source']
    require((src['symbol'],src['market'],src['interval'],src['mode'],src['source_version'],
             src['correction_generation']) == ('BTCUSDT','SPOT','15m','RETROSPECTIVE_MARKET_ONLY',
                 SOURCE_VERSION,'UNKNOWN_UNATTESTED'),'SOURCE_VINTAGE_DRIFT')
    require(src['archive_artifact_sha256'] == B1_SHA and src['accepted_market_report_sha256'] == B1_REPORT_SHA
            and src['market_lock_sha256'] == LOCK_SHA,'SOURCE_PARENT_DRIFT')
    require(all(src.get(k) is None for k in ('source_available_at_ms','source_published_at_ms',
                                            'correction_published_at_ms'))
            and src['external_evidence'] == 'BLOCKED_EXTERNAL_EVIDENCE','MISSING_WITNESS_CANNOT_BECOME_PROOF')
    expected_months=[{k:s['meta'][k] for k in ('name','archive_sha256','member_sha256','checksum_sha256',
                                             'first_open_ms','bars')} for s in months.values()]
    require(src['months'] == expected_months,'FORGED_PARENT_OR_MEMBER')
    expected=expected_schedule(months)
    opportunities=doc['opportunities']
    require(len(opportunities) == 32,'MISSING_OPPORTUNITY')
    require(len({r['opportunity_id'] for r in opportunities}) == 32
            and len({r['pair_id'] for r in opportunities}) == 32,'DUPLICATE_OPPORTUNITY_OR_PAIR')
    require({r['opportunity_id'] for r in opportunities} == set(expected),'MISSING_OR_UNKNOWN_IDENTITY')
    normalized=[]
    previous=None
    for row in opportunities:
        pair,member,cutoff=expected[row['opportunity_id']]
        require(type(row['decision_cutoff_ms']) is int and
                row['feature_last_bar_close_exclusive_ms'] <= row['decision_cutoff_ms']
                and row['bar_close_exclusive_ms'] <= row['decision_cutoff_ms'],'CUTOFF_LOOKAHEAD')
        require(row['pair_id'] == pair and row['source_member_sha256'] == member
                and row['decision_cutoff_ms'] == cutoff and row['bar_close_exclusive_ms'] == cutoff
                and row['bar_open_ms'] == cutoff-BAR_MS,'PAIR_SOURCE_OR_CUTOFF_DRIFT')
        require(previous is None or cutoff > previous,'OPPORTUNITY_ORDER_DRIFT')
        previous=cutoff
        require((row['symbol'],row['market'],row['interval'],row['source_version'],row['correction_generation']) ==
                ('BTCUSDT','SPOT','15m',SOURCE_VERSION,'UNKNOWN_UNATTESTED'),'ROW_SOURCE_DRIFT')
        for field in ('source_available_at_ms','correction_published_at_ms'):
            value=row[field]
            require(value is None or type(value) is int and value<=cutoff,'SOURCE_CLOCK_LOOKAHEAD')
            require(value is None,'UNATTESTED_CLOCK_PROMOTION')
        require(row['feature_version'] == FEATURE and row['regime_version'] == REGIME
                and row['regime']['version'] == REGIME,'FEATURE_REGIME_ROW_VERSION')
        # Independently check the consumed feature snapshot against this exact
        # <=cutoff source prefix using the already accepted native indicator.
        prefix=[values for t,values in months[member]['bars'].items() if t+BAR_MS<=cutoff]
        closes=[float(v[3]) for v in prefix]
        require(len(prefix)>=252 and row['feature_input_bars'] == len(prefix)
                and row['feature_last_bar_close_exclusive_ms'] == cutoff,'FEATURE_PREFIX_DRIFT')
        features=dict(readiness='READY_RESEARCH_ONLY',ema8=format(_ema(closes,8)[-1],'.8f'),
                      ema21=format(_ema(closes,21)[-1],'.8f'),sma20=format(math.fsum(closes[-20:])/20,'.8f'))
        require(row['features'] == features,'FEATURE_VALUE_OR_READINESS_DRIFT')
        fast,slow,price=Decimal(features['ema8']),Decimal(features['ema21']),Decimal(prefix[-1][3])
        state='UP_TREND' if fast>slow and price>slow else 'DOWN_TREND' if fast<slow and price<slow else 'RANGE_OR_MIXED'
        require(row['regime']['state'] == state and row['regime']['reason'] ==
                'RESEARCH_EMA8_EMA21_PRICE_ONLY_NOT_TRADING_SIGNAL','REGIME_VALUE_MISMATCH')
        require(row['strategy_version'] == 'NOT_CONNECTED' and row['strategy_signal'] is None
                and row['original_decision_provenance'] == 'NOT_SUPPLIED'
                and row['decision_status'] == 'UNKNOWN_ORIGINAL_DECISION'
                and row['pit_status'] == 'BLOCKED_EXTERNAL_EVIDENCE'
                and row['market_observation_only'] is True and row['trade_or_alpha_evidence'] is False,
                'UNSUPPORTED_ORIGINAL_DECISION_PROMOTION')
        supplied=row['arms']
        require(isinstance(supplied,list) and len({a['arm'] for a in supplied}) == len(supplied)
                and {a['arm'] for a in supplied}<=set(ARMS),'DUPLICATE_OR_UNKNOWN_ARM')
        arms=[]
        for arm in ARMS:
            item=next((a for a in supplied if a['arm'] == arm),None)
            if item is not None:
                require(item == dict(arm=arm,capture_status='MISSING_CAPTURE',direction=None,
                                     decision_status='UNKNOWN_ORIGINAL_DECISION'),'ARM_DECISION_SCOPE')
            arms.append(dict(arm=arm,capture_status='MISSING_CAPTURE',direction=None,
                             decision_status='UNKNOWN_ORIGINAL_DECISION',supplied=item is not None,
                             reason='CORE_EXPLICIT_MISSING_CAPTURE' if item else 'ARM_RECORD_NOT_SUPPLIED'))
        normalized.append((copy.deepcopy(row),arms))
    require(doc['counts'] == dict(n_opportunities=32,arm_slots_2n=64,expected_outcome_rows_6n=192,
                                  missing_capture=64,verified_original_strategy_decisions=0,features_ready=32),
            'CORE_COUNT_DRIFT')
    return normalized


def market_window(bars,cutoff,hours):
    require(hours in HOURS and type(cutoff) is int and cutoff%BAR_MS == 0,'WINDOW_GRID')
    horizon=hours*3600000
    clock=dict(window_start_ms=cutoff,window_end_exclusive_ms=cutoff+horizon,
               observation_basis='POST_CUTOFF_RETAINED_OHLC_NOT_KNOWN_AT_DECISION')
    if not bars:
        return dict(**clock,horizon_hours=hours,expected_bars=hours*4,observed_bars=0,
                    coverage_status='UNKNOWN',reason='SOURCE_NOT_SUPPLIED',complete=False,censored=False,
                    unknown=True,observed_high=None,observed_low=None)
    base=bounded_window(bars,cutoff,horizon)
    if base['observed_bars'] == base['expected_bars']:
        status,reason='COMPLETE','EXACT_ORIGINAL_FUTURE_GRID'
    elif max(bars)+BAR_MS < cutoff+horizon and cutoff>=min(bars) and all(
            t in bars for t in range(cutoff,min(max(bars)+BAR_MS,cutoff+horizon),BAR_MS)):
        status,reason='CENSORED','RETAINED_SOURCE_END'
    else:
        status,reason='UNKNOWN','MISSING_SOURCE_GRID'
    return dict(**clock,horizon_hours=hours,expected_bars=base['expected_bars'],observed_bars=base['observed_bars'],
                coverage_status=status,reason=reason,complete=status=='COMPLETE',censored=status=='CENSORED',
                unknown=status=='UNKNOWN',observed_high=base['observed_high'] if status=='COMPLETE' else None,
                observed_low=base['observed_low'] if status=='COMPLETE' else None)


def build_evaluation(doc,months):
    normalized=validate_handoff(doc,months)
    ledger=[]; outcomes=[]; pairs=[]; strata=defaultdict(list)
    for row,arms in normalized:
        ledger.append(dict(original_core_opportunity=row,arm_slots=arms))
        key=(row['feature_version'],row['features']['readiness'],row['regime_version'],row['regime']['state'])
        strata[key].append(row['opportunity_id'])
        for hours in HOURS:
            observation=market_window(months[row['source_member_sha256']]['bars'],row['decision_cutoff_ms'],hours)
            for arm in arms:
                outcomes.append(dict(opportunity_id=row['opportunity_id'],pair_id=row['pair_id'],arm=arm['arm'],
                    capture_status=arm['capture_status'],decision_status=arm['decision_status'],
                    decision_cutoff_ms=row['decision_cutoff_ms'],source_version=row['source_version'],
                    source_member_sha256=row['source_member_sha256'],correction_generation=row['correction_generation'],
                    feature_version=row['feature_version'],regime_version=row['regime_version'],regime=row['regime']['state'],
                    measurement_class='MARKET_ONLY',window=observation,
                    signed_mfe=None,signed_mae=None,tp_sl_ordering=None,fills=None,pnl=None,alpha=None,
                    independent_market_custody='BLOCKED_EXTERNAL_EVIDENCE'))
            pairs.append(dict(opportunity_id=row['opportunity_id'],pair_id=row['pair_id'],horizon_hours=hours,
                              arms=list(ARMS),status='NOT_EVALUABLE',base_shadow_uplift=None,
                              reason='NO_ORIGINAL_DECISION_DIRECTION_ENTRY_OR_INDEPENDENT_WITNESS'))
    require(len(outcomes) == 192 and len({(r['opportunity_id'],r['arm'],r['window']['horizon_hours'])
                                        for r in outcomes}) == 192,'OUTCOME_DENOMINATOR')
    stratification=[]
    for key,ids in sorted(strata.items()):
        selected=[r for r in outcomes if r['opportunity_id'] in ids]
        stratification.append(dict(feature_version=key[0],readiness=key[1],regime_version=key[2],regime=key[3],
            opportunity_ids=ids,n_opportunities=len(ids),arm_slots_2n=2*len(ids),horizon_rows_6n=6*len(ids),
            coverage=dict(sorted(Counter(r['window']['coverage_status'] for r in selected).items())),
            strategy_association='NOT_EVALUABLE',exclusions=0))
    report=dict(schema_version='aql.r1-factory-market-evaluation.v1',project_id='AQL-CRYPTO-RESEARCH-001',scope=SCOPE,
        pins=dict(factory_base=FACTORY_BASE,core=CORE_HEAD,core_artifact_id=CORE_ARTIFACT,core_input_sha256=CORE_BYTES_SHA,
                  vault_dependency=VAULT_HEAD,indicator_git_blob=INDICATOR_BLOB,b1_original_artifact_sha256=B1_SHA),
        source=copy.deepcopy(doc['source']),sample_policy=copy.deepcopy(doc['sample_policy']),
        counts=dict(opportunities=32,arm_slots_2n=64,outcome_rows_6n=len(outcomes),missing_capture=64,
                    supplied_arm_records=sum(a['supplied'] for _,arms in normalized for a in arms),
                    materialized_missing_arm_records=sum(not a['supplied'] for _,arms in normalized for a in arms),
                    original_strategy_decisions=0,features_ready=32,excluded_opportunities=0,
                    paired_horizon_comparisons=len(pairs),evaluable_comparisons=0,
                    not_evaluable_comparisons=len(pairs),
                    coverage=dict(sorted(Counter(r['window']['coverage_status'] for r in outcomes).items()))),
        opportunity_ledger=ledger,outcomes=outcomes,paired_comparisons=pairs,feature_regime_strata=stratification,
        coverage_by_horizon={str(h)+'h':dict(sorted(Counter(r['window']['coverage_status'] for r in outcomes
                                                       if r['window']['horizon_hours']==h).items())) for h in HOURS},
        costs=dict(status='NOT_CONFIGURED_NO_EXECUTION',fees=None,slippage=None),
        blockers=[dict(boundary=b,status=s,owner=o,needed=n) for b,s,o,n in (
            ('market_byte_integrity','PASS_PINNED_ORIGINAL_MONTHS','Factory','No new acquisition; two original source months only'),
            ('historical_strategy_decision','MISSING_CAPTURE','Core/owner','Original per-arm decision/direction/entry records'),
            ('issuer_publication_correction_clock','BLOCKED_EXTERNAL_EVIDENCE','Independent issuer/custodian','Original source/correction known-at evidence'),
            ('external_parent_custody_and_freeze','BLOCKED_EXTERNAL_EVIDENCE','Independent custodian','Retained independently verified original parent/receipt/pre-F3 anchor'),
            ('production_monitor','NOT_CONNECTED','Core','Actual monitor snapshot-to-outcome path'),
            ('real_prospective_F3','NOT_CONNECTED','Core/owner','Actual prospective producer/F3 lifecycle'),
            ('directional_performance','NOT_EVALUABLE','Core/owner','Authentic direction/entry + explicitly authorized performance protocol'))],
        limitations=['Two selected four-hour samples, not full-year strategy coverage or OOS',
                     'Overlapping windows and identical BASE/SHADOW market context are dependent, not uplift',
                     'Bar close is a modeled retrospective lower bound, not observed issuer availability',
                     'Local B3 custody acceptance is not independent operational PIT'],
        g0_merge_deployment_paper_shadow_live_authorized=False)
    report['evaluation_sha256']=sha(canonical(report))
    return report


def evaluate(core_bytes,b1_bytes):
    require(sha(core_bytes) == CORE_BYTES_SHA,'CORE_TRANSPORT_PIN_DRIFT')
    return build_evaluation(strict_json(core_bytes),load_market(b1_bytes))


def summary(report):
    c=report['counts']
    lines=['# Factory R1 — historical MARKET_ONLY evaluation','',
        f"32 opportunities / 64 arms / {c['outcome_rows_6n']} horizon rows; no exclusions.",
        f"Coverage: {c['coverage']}. Missing original captures: 64; evaluable paired comparisons: 0/96.",
        '','| Regime | Opportunities | Arms | Horizon rows |','|---|---:|---:|---:|']
    lines += [f"| {s['regime']} | {s['n_opportunities']} | {s['arm_slots_2n']} | {s['horizon_rows_6n']} |"
              for s in report['feature_regime_strata']]
    lines += ['', 'Direction, signed MFE/MAE, TP/SL, fills, PnL, alpha and BASE/SHADOW uplift are null / NOT_EVALUABLE.',
              'External issuer/correction clock, custody and freeze remain BLOCKED_EXTERNAL_EVIDENCE.',
              'No B1/B2/B3 runner or old test suite, full-year replay, operational PIT or activation claim.',
              '', 'Core input SHA256: `'+CORE_BYTES_SHA+'`.']
    return '\n'.join(lines)+'\n'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True);p.add_argument('--b1-artifact',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();require(not a.out.exists(),'REFUSE_OUTPUT_OVERWRITE')
    report=evaluate(a.core.read_bytes(),a.b1_artifact.read_bytes());a.out.mkdir(parents=True)
    for name,data in [('evaluation.json',canonical(report)),('SUMMARY.md',summary(report).encode())]:
        with (a.out/name).open('xb') as f:
            f.write(data);f.flush();os.fsync(f.fileno())
        require((a.out/name).read_bytes() == data,'OUTPUT_READBACK_FAILED')
        print(sha(data)+'  '+name)
    print(json.dumps(report['counts'],sort_keys=True))


if __name__=='__main__':
    main()
