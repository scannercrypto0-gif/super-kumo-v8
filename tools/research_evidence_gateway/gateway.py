"""Bounded v1 reader for pinned prospective and paper-simulation exports.

The trust anchor is an independently retained manifest digest. A self-hash is
integrity, not publisher authentication. No producer business logic is rerun.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'aql.research-evidence-gateway.read-model.v1'
HORIZONS = (14400000, 86400000, 259200000)


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
    need(not path.is_symlink() and path.is_file(), 'MISSING_OR_LINKED_ARTIFACT')
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
    seen, signals, census, horizons, objects = set(), {}, Counter(), Counter(), []
    need(len(rows) == manifest['expected_decisions'], 'DECISION_POPULATION')
    for row in rows:
        d = row['decision']; identity = sha(d); p = d['parent']
        need(row['decision_sha256'] == identity and p['key'] not in seen, 'DECISION_DUPLICATE_OR_SEAL')
        seen.add(p['key'])
        need(d['run'] == run and row['source_valid'] is True, 'SOURCE_OR_STRATEGY_SWAP')
        need(all(type(x) is int for x in (p['close_ms'],p['ingested_ms'],p['commit_ms'],d['cutoff_ms']))
             and p['close_ms'] < p['ingested_ms'] <= p['commit_ms'] <= d['cutoff_ms'] <= asof,
             'SOURCE_TIME')
        need(all(re.fullmatch('[0-9a-f]{64}', p[k]) for k in
                 ('bar_checksum','content_sha256','g1_receipt_sha256')), 'SOURCE_IDENTITY')
        state = d['state']
        need(state in ('ENTRY_SIGNAL','EXIT_SIGNAL','NO_SIGNAL','REJECTED','UNKNOWN'), 'DECISION_STATE')
        census[state] += 1
        if state == 'ENTRY_SIGNAL':
            need(d['opportunity_id'] == sha({k:v for k,v in d.items() if k != 'opportunity_id'}), 'SIGNAL_ID')
            signals[d['opportunity_id']] = (d, identity)
            observed = set()
            for h in row['horizons']:
                span = h['horizon_ms']; status = h['state']
                need(span in HORIZONS and span not in observed and h['due_ms'] == d['cutoff_ms'] + span,
                     'HORIZON_PARENT')
                observed.add(span)
                need(status in ('pending','UNKNOWN','missing','mature'), 'HORIZON_STATE')
                # This bounded reader does not attest uninspected mature observations.
                if status in ('pending','UNKNOWN'):
                    need(h['evidence'] is None and (asof < h['due_ms']) == (status == 'pending'), 'FAKE_MATURITY')
                else:
                    raise EvidenceStop('UNSUPPORTED_MATURE_EVIDENCE_CONTRACT')
                horizons[status] += 1
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
        modeled.append(dict(record_type='modeled_result',id=sid,status=result['phase'],
                            grade='INDEPENDENTLY_VERIFIED_ARTIFACT',scope='SYNTHETIC_BYTES_AND_LINEAGE_ONLY',
                            receipt_sha256=sha(result),modeled_fill_count=len(result['fills']),
                            net_pnl=result['net_pnl']))
    need(sorted(result_ids) == manifest['expected_result_signal_ids'], 'MISSING_MODELED_RESULT')
    # No guessed join from generation attempts to Factory variants.
    research = dict(status='NOT_AVAILABLE',grade='MISSING',attempts=None,trials=None,variants=None,
                    blocker='PERSISTED_DISCOVERER_FACTORY_JOIN_NOT_AVAILABLE')
    body = dict(schema=SCHEMA,status='BLOCKED_ONE_EXACT_SEAM',health='PARTIAL_VERIFIED_SYNTHETIC',
        manifest_sha256=expected_manifest,pinned_heads=manifest['pinned_heads'],as_of_ms=asof,
        denominators=dict(scanner_decisions=len(rows),scanner_signals=len(signals),
                          modeled_results=len(results),discoverer_attempts=None,factory_trials=None,factory_variants=None),
        decision_counts=dict(census),horizon_counts=dict(horizons),research=research,
        objects=sorted(objects+modeled,key=lambda x:(x['record_type'],x['id'])),
        evidence_boundary=dict(historical_pit='NOT_ATTESTED',rights='NOT_ATTESTABLE',known_at='NOT_ATTESTABLE',
            real_oos='NOT_ATTESTABLE',alpha='NOT_ATTESTABLE',stage_signoff='NONE',
            natural_horizon_maturity='NOT_ESTABLISHED',synthetic_embargo_is_natural_maturity=False,
            trading_authority='NONE',actual_fills=None),
        coverage=dict(g1='REFERENCED_FINALIZED_SYNTHETIC_PARENTS',scanner='VERIFIED_SYNTHETIC_CENSUS',
                      g2='PENDING_OR_UNKNOWN_ONLY',g3='VERIFIED_SYNTHETIC_MODELED_STATE',
                      discoverer_factory='NOT_AVAILABLE'))
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
