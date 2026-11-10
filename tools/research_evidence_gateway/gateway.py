"""Bounded v1 reader for pinned prospective and paper-simulation exports.

The trust anchor is an independently retained manifest digest. A self-hash is
integrity, not publisher authentication. No producer business logic is rerun.
"""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'aql.research-evidence-gateway.read-model.v1'
HORIZONS = (14400000, 86400000, 259200000)
STEP_MS = 900000
CLOCK_MS = 5000
PARENT_FIELDS = {'key','open_ms','close_ms','ingested_ms','commit_ms',
                 'bar_checksum','content_sha256','g1_receipt_sha256'}


class EvidenceStop(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise EvidenceStop(code)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode()


def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def pairs(items):
    result = {}
    for key, value in items:
        need(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read(path):
    need(not any(p.is_symlink() or (p.exists() and
             getattr(p.stat(), 'st_file_attributes', 0) & 0x400)
             for p in (path, *path.parents)) and path.is_file(), 'MISSING_OR_LINKED_ARTIFACT')
    raw = path.read_bytes()
    need(len(raw) <= 4_000_000, 'ARTIFACT_TOO_LARGE')
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(EvidenceStop('NONFINITE_JSON')))
    except (UnicodeError, json.JSONDecodeError):
        raise EvidenceStop('CORRUPT_ARTIFACT') from None


def sealed(obj, field='sha256'):
    need(type(obj) is dict and obj.get(field) == sha({k:v for k,v in obj.items() if k != field}),
         'RECEIPT_SEAL')


def boundary(obj):
    """Deny authority/promotion even inside nested metadata; never export raw input."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith('ack_sha256'):
                need(v is None, 'FAKE_ACK')
            if k in ('actual_fills', 'real_fills'):
                need(v is None, 'REAL_FILL_CLAIM')
            if k in ('orders_enabled', 'stage_closed', 'strategy_performance_accepted'):
                need(v is False, 'AUTHORITY_PROMOTION')
            if k in ('trading_authority', 'paper_authority', 'research_authority'):
                need(v == 'NONE', 'AUTHORITY_PROMOTION')
            if k == 'historical_pit':
                need(v in ('NOT_ATTESTED', 'NON_PIT', 'RETROSPECTIVE_NON_PIT'), 'PIT_PROMOTION')
            if k in ('evidence_mode', 'evidence_grade'):
                need(v == 'SYNTHETIC_TESTED', 'EVIDENCE_PROMOTION')
            boundary(v)
    elif isinstance(obj, list):
        for v in obj:
            boundary(v)


def native_parent(parent, cutoff):
    """Native prospective v1 finalized G1 receipt-reference shape, not raw prices."""
    need(type(parent) is dict and set(parent) == PARENT_FIELDS, 'SOURCE_PARENT_FIELDS')
    need(all(type(parent[k]) is int and parent[k] >= 0 for k in
             ('open_ms','close_ms','ingested_ms','commit_ms'))
         and parent['open_ms'] % STEP_MS == 0
         and parent['close_ms'] == parent['open_ms'] + STEP_MS - 1
         and parent['close_ms'] < parent['ingested_ms'] <= parent['commit_ms'] <= cutoff,
         'SOURCE_TIME')
    need(parent['key'] == f"BTCUSDT:15m:{parent['open_ms']}"
         and all(type(parent[k]) is str and re.fullmatch('[0-9a-f]{64}', parent[k])
                 for k in ('bar_checksum','content_sha256','g1_receipt_sha256')),
         'SOURCE_IDENTITY')


def native_horizon(horizon, decision, run, asof, parents):
    """Consume actual #286 v1 outcome parents; never manufacture maturity.

    Values are authenticated by the independently pinned native export, not
    independently recomputed from unavailable raw candles. Every outcome parent
    must also occur as a source-valid finalized G1 parent in that same export.
    """
    need(type(horizon) is dict and set(horizon) ==
         {'horizon_ms','due_ms','state','evidence'}, 'HORIZON_FIELDS')
    span, status, due = horizon['horizon_ms'], horizon['state'], horizon['due_ms']
    need(type(span) is int and span in HORIZONS and type(due) is int
         and due == decision['cutoff_ms'] + span, 'HORIZON_PARENT')
    need(status in ('pending','UNKNOWN','missing','mature','late'), 'HORIZON_STATE')
    evidence = horizon['evidence']
    if status in ('pending','UNKNOWN'):
        need(evidence is None and (asof < due) == (status == 'pending'), 'FAKE_MATURITY')
        return status
    need(type(evidence) is dict and set(evidence) == {
        'run','decision_key','opportunity_id','horizon_ms','due_ms',
        'recorded_ms','parent','state','value','trading_authority'}, 'HORIZON_EVIDENCE_FIELDS')
    need(evidence['run'] == run and evidence['decision_key'] == decision['parent']['key']
         and evidence['opportunity_id'] == decision['opportunity_id']
         and evidence['horizon_ms'] == span and evidence['due_ms'] == due
         and evidence['state'] == status and evidence['trading_authority'] == 'NONE',
         'HORIZON_LINEAGE_SWAP')
    recorded = evidence['recorded_ms']
    need(type(recorded) is int and 0 <= recorded <= asof, 'HORIZON_FUTURE_RECORD')
    parent = evidence['parent']
    native_parent(parent, recorded)
    need(due <= parent['close_ms'], 'PREMATURE_HORIZON_PARENT')
    need(parents.get(parent['key']) == parent, 'HORIZON_SOURCE_RECEIPT_SWAP')
    native_status = ('missing' if parent['close_ms'] >= due + STEP_MS else
                     'late' if parent['commit_ms'] > parent['close_ms'] + CLOCK_MS else 'mature')
    need(status == native_status, 'HORIZON_NATIVE_STATE_SWAP')
    if status == 'mature':
        try:
            value = Decimal(evidence['value']) if type(evidence['value']) is str else None
        except InvalidOperation:
            value = None
        need(value is not None and value.is_finite() and value > 0, 'MATURE_VALUE')
    else:
        need(evidence['value'] is None, 'MISSING_OR_LATE_VALUE_PROMOTION')
    return status


def modeled_state(result, cutoff):
    """Check native exported accounting identities, never re-simulate fills."""
    def number(value):
        try:
            n=Decimal(value) if type(value) is str and len(value)<=128 else None
        except InvalidOperation:
            n=None
        need(n is not None and n.is_finite(), 'MODELED_NONFINITE_NUMBER')
        return n
    need(type(cutoff) is int and type(result['updated_ms']) is int
         and result['signal']['decision_ms'] <= result['updated_ms'] <= cutoff,
         'MODELED_FUTURE_STATE')
    need(type(result['fills']) is list and len(result['fills']) <= 10000, 'MODELED_FILL_BOUND')
    with localcontext() as ctx:
        ctx.prec=40
        buy_qty=sell_qty=entry=exit=fees=adverse=Decimal(0)
        for fill in result['fills']:
            qty,price,fee,cost=(number(fill[k]) for k in ('qty','price','fee','adverse_cost'))
            need(qty>0 and price>0 and fee>=0 and cost>=0 and fill['side'] in ('buy','sell'), 'MODELED_FILL_RANGE')
            start,end=fill['assumed_execution_window']
            received=fill['received_ms'];executed=fill['execution_ms']
            need(all(type(v) is int for v in (start,end,received))
                 and result['signal']['decision_ms'] < start <= end <= received <= result['updated_ms'],
                 'MODELED_FUTURE_FILL')
            need((fill['liquidity']=='ASSUMED_MAKER' and executed is None) or
                 (fill['liquidity']=='ASSUMED_TAKER' and type(executed) is int and executed==start==end),
                 'MODELED_EXECUTION_CLAIM')
            if fill['side']=='buy':buy_qty+=qty;entry+=qty*price
            else:sell_qty+=qty;exit+=qty*price
            fees+=fee;adverse+=cost
        need(buy_qty==number(result['filled']) and sell_qty==number(result['exited']) and sell_qty<=buy_qty
             and entry==number(result['entry_notional']) and exit==number(result['exit_notional'])
             and fees==number(result['fees']) and adverse==number(result['adverse_cost']), 'MODELED_AGGREGATE_MISMATCH')
        capital=number(result['policy']['capital'])
        need(number(result['cash'])==capital-entry+exit-fees-adverse, 'MODELED_CASH_CONSERVATION')
        if result['phase']=='CLOSED':
            need(buy_qty>0 and buy_qty==sell_qty and number(result['net_pnl'])==exit-entry-fees-adverse,
                 'MODELED_PNL_PROMOTION')
        else:
            need(result['net_pnl'] is None, 'MODELED_OPEN_PNL_PROMOTION')


def modeled_factory_comparison(doc):
    """Compare only persisted PKG02 model population/boundaries, not strategies."""
    sealed(doc)
    need(doc['schema']=='aql.factory.h.execution-exit-comparison.v1'
         and doc['source_class']=='SYNTHETIC_FIXTURE_ONLY'
         and doc['trading_authority']=='NONE' and doc['actual_fills'] is None
         and doc['orders_created']==0 and doc['winner'] is None
         and doc['assessment']=='SYNTHETIC_ENGINEERING_ONLY_NO_ALPHA_CLAIM', 'FACTORY_MODEL_PROMOTION')
    counts=Counter(r['status'] for r in doc['outcomes'])
    need(len(doc['outcomes'])==doc['denominators']['total_variant_rows']
         and len(doc['comparisons'])==2*doc['denominators']['variants_per_cohort']
         and sum(doc['denominators']['attempt_state_counts'].values())==doc['denominators']['total_attempted'],
         'FACTORY_MODEL_POPULATION')
    need(all(r['net_return'] is None and r['gross_return'] is None for r in doc['outcomes']
             if r['status'].startswith('UNKNOWN'))
         and all(r['filled_fraction']=='0' and r['net_return']=='0' for r in doc['outcomes']
                 if r['status']=='NONFILL'), 'FACTORY_UNKNOWN_NONFILL_PROMOTION')
    return dict(status='VERIFIED_SEPARATE_SYNTHETIC_MODEL_BOUNDARY',report_sha256=doc['sha256'],
                rows=len(doc['outcomes']),status_counts=dict(counts),
                linked_to_discoverer_trial=False,same_cohort_or_strategy_not_assumed=True,
                actual_fills=None,trading_authority='NONE')


def build(root, expected_manifest):
    manifest = read(root/'manifest.json')
    need(sha(manifest) == expected_manifest, 'MANIFEST_TRUST_ANCHOR')
    need(manifest.get('schema') == 'aql.research-evidence-gateway.inputs.v1', 'MANIFEST_VERSION')
    docs = {}
    for name, digest in manifest['files'].items():
        need(re.fullmatch(r'[a-z]+\.json', name) is not None, 'UNSAFE_INPUT_NAME')
        docs[name] = read(root/name)
        need(sha(docs[name]) == digest, 'ARTIFACT_DIGEST')
        boundary(docs[name])
    source, results = docs['source.json'], docs['results.json']
    sealed(source)
    need(source.get('schema') == 'aql.g2.prospective-verified-read.v1', 'SOURCE_CONTRACT')
    run, rows, asof = source['run'], source['rows'], source['as_of_ms']
    need(run == manifest['run'] and run['evidence_mode'] == 'SYNTHETIC_TESTED', 'RUN_IDENTITY')
    need(source['visible_sha256'] == sha(rows), 'VISIBLE_ROWS')
    need(type(asof) is int and asof == manifest['as_of_ms'], 'MIXED_UTC_CUTOFF')
    results_asof=manifest.get('results_as_of_ms',asof)
    need(type(results_asof) is int and results_asof>=asof, 'MODELED_RESULT_CUTOFF')
    seen, signals, census, horizons, objects = set(), {}, Counter(), Counter(), []
    need(len(rows) == manifest['expected_decisions'], 'DECISION_POPULATION')
    parents = {r['decision']['parent']['key']: r['decision']['parent']
               for r in rows if r['source_valid'] is True}
    for row in rows:
        d = row['decision']; identity = sha(d); p = d['parent']
        need(row['decision_sha256'] == identity and p['key'] not in seen, 'DECISION_DUPLICATE_OR_SEAL')
        seen.add(p['key'])
        need(d['run'] == run and row['source_valid'] is True, 'SOURCE_OR_STRATEGY_SWAP')
        need(type(d['cutoff_ms']) is int and d['cutoff_ms'] <= asof, 'SOURCE_TIME')
        native_parent(p, d['cutoff_ms'])
        state = d['state']
        need(state in ('ENTRY_SIGNAL','EXIT_SIGNAL','NO_SIGNAL','REJECTED','UNKNOWN'), 'DECISION_STATE')
        census[state] += 1
        if state in ('ENTRY_SIGNAL','EXIT_SIGNAL'):
            need(d['opportunity_id'] == sha({k:v for k,v in d.items() if k != 'opportunity_id'}), 'SIGNAL_ID')
            if state == 'ENTRY_SIGNAL':
                signals[d['opportunity_id']] = (d, identity)
            observed = set()
            for h in row['horizons']:
                span = h['horizon_ms']
                need(span not in observed, 'HORIZON_PARENT')
                status = native_horizon(h, d, run, asof, parents)
                observed.add(span)
                horizons[status] += 1
                evidence = h['evidence']
                objects.append(dict(record_type='horizon',id=f"{d['opportunity_id']}:{span}",
                    status=status,due_ms=h['due_ms'],
                    evidence_sha256=None if evidence is None else sha(evidence),
                    g1_receipt_sha256=None if evidence is None else evidence['parent']['g1_receipt_sha256'],
                    source_sha256=None if evidence is None else evidence['parent']['content_sha256'],
                    recorded_ms=None if evidence is None else evidence['recorded_ms'],
                    grade='INDEPENDENTLY_VERIFIED_ARTIFACT',scope='SYNTHETIC_BYTES_AND_LINEAGE_ONLY'))
            horizons['NOT_AVAILABLE'] += len(set(HORIZONS) - observed)
        else:
            need(d['opportunity_id'] is None and row['horizons'] == [], 'NO_SIGNAL_MISCLASSIFIED')
        objects.append(dict(record_type='decision',id=identity,status=state,
                            grade='INDEPENDENTLY_VERIFIED_ARTIFACT',scope='SYNTHETIC_BYTES_AND_LINEAGE_ONLY',
                            source_sha256=p['content_sha256'],observed_at_ms=d['cutoff_ms']))
    need(sorted(signals) == manifest['expected_signal_ids'], 'SIGNAL_POPULATION')
    modeled, result_ids = [], set()
    for result in results:
        need(result.get('schema') == 'aql.paper-sim.state.v1', 'RESULT_CONTRACT')
        sig = result['signal']; sid = sig['signal_id']
        need(sid in signals and sid not in result_ids, 'RESULT_MISSING_PARENT_OR_DUPLICATE')
        result_ids.add(sid); d, decision_sha = signals[sid]
        need(sig['source_sha256'] == decision_sha and
             all(sig[k] == run[k] for k in ('strategy_id','strategy_version','definition_sha256',
                                           'config_sha256','evaluator_sha256')) and
             sig['decision_ms'] == d['cutoff_ms'] and sig['available_ms'] == d['parent']['commit_ms'] and
             sig['source_close_ms'] == d['parent']['close_ms'], 'RESULT_LINEAGE_SWAP')
        need(result['engine_sha256'] == manifest['engine_sha256'], 'ENGINE_SWAP')
        need(result['phase'] in ('WATCH','ARMED','TRIGGERED','CLOSED','UNKNOWN','NO_FILL','EXPIRED','CANCELLED','REJECTED'), 'RESULT_STATE')
        need(all(f['liquidity'] in ('ASSUMED_TAKER','ASSUMED_MAKER') for f in result['fills']), 'FAKE_FILL')
        need(result['phase'] != 'UNKNOWN' or result['net_pnl'] is None, 'UNKNOWN_PNL_PROMOTION')
        need(result['phase'] != 'NO_FILL' or not result['fills'], 'NONFILL_PROMOTION')
        modeled_state(result,results_asof)
        modeled.append(dict(record_type='modeled_result',id=sid,status=result['phase'],
                            grade='INDEPENDENTLY_VERIFIED_ARTIFACT',scope='SYNTHETIC_BYTES_AND_LINEAGE_ONLY',
                            receipt_sha256=sha(result),modeled_fill_count=len(result['fills']),
                            net_pnl=result['net_pnl']))
    need(sorted(result_ids) == manifest['expected_result_signal_ids'], 'MISSING_MODELED_RESULT')
    # No guessed join from generation attempts to Factory variants.
    research = dict(status='NOT_AVAILABLE',grade='MISSING',attempts=None,trials=None,variants=None,
                    blocker='PERSISTED_DISCOVERER_FACTORY_JOIN_NOT_AVAILABLE')
    if 'research' in manifest:
        from tools.research_evidence_gateway.research import consume
        research = consume(root,manifest['research'],read=read,sha=sha,need=need,sealed=sealed,boundary=boundary)
    joined = research['status'] == 'RESEARCH_JOIN_PASS'
    comparison = modeled_factory_comparison(docs['factory.json']) if 'factory.json' in docs else dict(status='NOT_SUPPLIED')
    body = dict(schema=SCHEMA,status='PASS_READ_ONLY_EVIDENCE_INTEGRATION' if joined else 'BLOCKED_ONE_EXACT_SEAM',
        health='VERIFIED_SYNTHETIC_ARTIFACTS' if joined else 'PARTIAL_VERIFIED_SYNTHETIC',
        mature_g2_consumer_seam='MATURE_G2_CONSUMER_SEAM_PASS' if any(horizons[s] for s in ('mature','missing','late'))
                               else 'SUPPORTED_NOT_EXERCISED_BY_THIS_INPUT',
        manifest_sha256=expected_manifest,pinned_heads=manifest['pinned_heads'],as_of_ms=asof,
        modeled_results_as_of_ms=results_asof,
        denominators=dict(scanner_decisions=len(rows),scanner_signals=len(signals),
                          modeled_results=len(results),discoverer_attempts=research['attempts'],
                          factory_trials=research['trials'],factory_variants=research['variants']),
        decision_counts=dict(census),horizon_counts=dict(horizons),research=research,
        pkg02_model_comparison=comparison,
        objects=sorted(objects+modeled,key=lambda x:(x['record_type'],x['id'])),
        evidence_boundary=dict(historical_pit='NOT_ATTESTED',rights='NOT_ATTESTABLE',known_at='NOT_ATTESTABLE',
            real_oos='NOT_ATTESTABLE',alpha='NOT_ATTESTABLE',stage_signoff='NONE',
            natural_horizon_maturity='NOT_ESTABLISHED',synthetic_embargo_is_natural_maturity=False,
            trading_authority='NONE',actual_fills=None),
        coverage=dict(g1='REFERENCED_FINALIZED_SYNTHETIC_PARENTS',scanner='VERIFIED_SYNTHETIC_CENSUS',
                      g2='VERIFIED_NATIVE_HORIZON_STATES',g3='VERIFIED_SYNTHETIC_MODELED_STATE',
                      discoverer_factory='VERIFIED_PERSISTED_SYNTHETIC_LINEAGE' if joined else 'NOT_AVAILABLE'))
    return dict(body,sha256=sha(body))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',type=Path,required=True)
    p.add_argument('--manifest-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    try:
        need(not args.output.exists() and not args.output.is_symlink(), 'OUTPUT_EXISTS')
        need(args.inputs.resolve() not in args.output.resolve().parents, 'OUTPUT_INSIDE_INPUTS')
        report = build(args.inputs,args.manifest_sha256)
        # Exclusive create: never overwrite upstream or an existing output.
        with args.output.open('xb') as stream:
            stream.write(canonical(report)+b'\n')
        print(report['sha256'])
    except (EvidenceStop,KeyError,TypeError,ValueError,OSError) as error:
        print(json.dumps(dict(status='REJECTED',code=str(error) if isinstance(error,EvidenceStop) else 'INVALID_ARTIFACT')))
        raise SystemExit(2) from None


if __name__ == '__main__':
    main()
