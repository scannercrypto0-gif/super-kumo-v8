"""Versioned TEST_ONLY transport between existing unmerged component contracts."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from .harness import (BoundaryError, ReceiptStore, canonical, confined, digest,
                      load_object, read_bytes, require, sealed, sha, strict_json)

SCHEMA = 'aql.work.research-seam-integration.v2'
SLOTS = {'NO_SIGNAL', 'REJECTED', 'UNKNOWN', 'NULL', 'UNSCANNED', 'UNRESOLVED', 'NOMINATED'}


def ms(text):
    require(type(text) is str and len(text) < 50, 'INVALID_UTC')
    parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    require(parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0, 'INVALID_UTC')
    return int(parsed.timestamp() * 1000)


def checkouts(lock, roots):
    require(set(roots) == set(lock['components']) == {'core', 'factory', 'scanner', 'discoverer'},
            'MISSING_COMPONENT_CHECKOUT')
    for name, spec in lock['components'].items():
        require(re.fullmatch('[0-9a-f]{40}', spec['commit_sha']) is not None, 'COMPONENT_COMMIT')
        for path, expected in spec['files'].items():
            require(sha(read_bytes(confined(roots[name], path))) == expected,
                    'COMPONENT_DRIFT:' + name + ':' + path)


def worker(name, body, roots):
    script = Path(__file__).with_name('worker_v2.py')
    raw = canonical(body)
    require(len(raw) <= 8 * 1024 * 1024, 'WORKER_INPUT_LIMIT')
    result = subprocess.run([sys.executable, '-I', str(script), name, str(Path(roots[name]).resolve())],
                            input=raw, capture_output=True, timeout=30, check=False)
    if result.returncode:
        lines = result.stderr.decode(errors='replace').splitlines()
        raise BoundaryError('COMPONENT_REFUSED:' + name + ':' + (lines[-1][:220] if lines else 'NO_ERROR_DETAIL'))
    require(len(result.stdout) <= 8 * 1024 * 1024, 'WORKER_OUTPUT_LIMIT')
    return strict_json(result.stdout)


def core_call(root, cohort, roots):
    raw_ref = cohort['objects']['source']
    raw = read_bytes(confined(root, raw_ref['path']))
    require(sha(raw) == raw_ref['sha256'], 'ORIGINAL_SOURCE_SHA')
    spec = cohort['spec']
    require(set(cohort['objects']) == {'source', 'schedule', 'slots', 'scanner'}, 'MISSING_INPUT_BOUNDARY')
    require(spec['test_only'] is True and spec['dataset_id'].startswith('TEST_ONLY_'), 'PRIVATE_RUN_FORBIDDEN')
    require(cohort['inventory_sha256'] == strict_json(raw)['inventory_hash'], 'INVENTORY_DRIFT')
    require(len(cohort['requests']) <= 32, 'QUERY_BUDGET')
    for req in cohort['requests']:
        require(req['dataset_id'] == spec['dataset_id'] and req['version'] == spec['version'],
                'QUERY_COHORT_VERSION')
        require(req['schema'] == 'aql.core-research.custody-query.v1' and
                req['confirmed_only'] is False, 'CORE_REQUEST_CONTRACT')
    return worker('core', {'source_hex': raw.hex(), 'source_sha256': raw_ref['sha256'],
                          'inventory_sha256': cohort['inventory_sha256'], 'spec': spec,
                          'requests': cohort['requests']}, roots)


def factory_boundary(cohort, schedule, slots, core, roots):
    """No schedule production: require an original, sealed TEST_ONLY paired schedule."""
    sealed(schedule)
    spec = cohort['spec']
    original_sha = cohort['objects']['source']['sha256']
    require(schedule['test_only'] is True and schedule['source']['source_id'] == spec['dataset_id']
            and schedule['source']['symbol'] == spec['symbol']
            and schedule['source']['source_package_sha256'] == original_sha, 'SCHEDULE_SOURCE_IDENTITY')
    require(len(schedule['pairs']) <= 32 and len(slots) == 2 * len(schedule['pairs']), 'ARM_DENOMINATOR')
    queries = core['queries']
    require(len(queries) == len(schedule['pairs']), 'CORE_QUERY_DENOMINATOR')
    seen, attempts, rows = set(), set(), []
    manifest = core['registration']['manifest_integrity_sha256']
    require(core['registration']['source_bytes_sha256'] == original_sha, 'CORE_SOURCE_DRIFT')
    require(schedule['source']['manifest_sha256'] == manifest, 'CORE_MANIFEST_DRIFT')
    for pair, query, request in zip(schedule['pairs'], queries, cohort['requests']):
        op = pair['opportunity']
        require(op['source_id'] == spec['dataset_id'] and op['source_package_sha256'] == original_sha,
                'OPPORTUNITY_SOURCE_DRIFT')
        require(query['schema'] == 'aql.core-research.custody-query-result.v1'
                and query['status'] == 'OK' and query['evidence_class'] == 'SYNTHETIC_TEST',
                'CORE_QUERY_UNAVAILABLE')
        result = query['result']
        require(result['schema'] == 'aql.bridge.custody-range.v1'
                and result['dataset_id'] == spec['dataset_id'] and result['version'] == spec['version']
                and result['source_bytes_sha256'] == original_sha
                and result['manifest_integrity_sha256'] == manifest, 'CORE_QUERY_PARENT')
        require(request['end_exclusive_ms'] == request['decision_cutoff_ms'] == op['decision_cutoff_ms']
                == result['decision_cutoff_ms'], 'CUTOFF_DRIFT')
        require(result['status'] == 'COMPLETE' and not result['missing_bar_opens']
                and result['available_bar_count'] == result['required_bar_count'], 'CORE_COVERAGE_BLOCKED')
        require(all(b['bar_close'] < op['decision_cutoff_ms'] and
                    b['observation_cutoff_ms'] <= op['decision_cutoff_ms'] for b in result['bars']),
                'FUTURE_SOURCE_AVAILABILITY')
        require(op['feature_prefix_sha256'] == digest(result['bars']), 'FEATURE_PREFIX_DRIFT')
        for arm in ('BASE', 'SHADOW'):
            key = (pair['pair_id'], arm)
            matching = [s for s in slots if (s['pair_id'], s['arm']) == key]
            require(len(matching) == 1 and key not in seen, 'MISSING_OR_DUPLICATE_SLOT')
            seen.add(key)
            row = deepcopy(matching[0])
            require(row['attempt_id'] not in attempts, 'DUPLICATE_ATTEMPT')
            attempts.add(row['attempt_id'])
            require(row['cohort_id'] == spec['dataset_id'] and row['opportunity_id'] == op['opportunity_id'],
                    'SLOT_COHORT_IDENTITY')
            require(row['source_package_sha256'] == original_sha and row['source_manifest_sha256'] == manifest,
                    'SLOT_SOURCE_DRIFT')
            require(row['decision_cutoff_ms'] == op['decision_cutoff_ms'], 'SLOT_CUTOFF_DRIFT')
            require(type(row['feature_available_ms']) is int, 'UNKNOWN_FEATURE_AVAILABILITY_BLOCKED')
            require(row['feature_snapshot_sha256'] == op['feature_prefix_sha256'], 'FEATURE_SNAPSHOT_DRIFT')
            # Feature clocks are explicit TEST_ONLY fixture declarations, not recomputed features/PIT.
            rows.append(row)
    envelope = {'schema': 'aql.factory.research-consumer-seam.v1', 'test_only': True,
                'evidence_class': 'TEST_ONLY', 'execution_status': 'NOT_OBSERVED',
                'trading_authority': 'NONE', 'source_schedule_sha256': schedule['artifact_sha256'],
                'source_package_sha256': original_sha, 'source_manifest_sha256': manifest,
                'cohort_id': spec['dataset_id'], 'strategy_version': cohort['strategy_version'], 'rows': rows}
    envelope['artifact_sha256'] = digest(envelope)
    receipt = worker('factory', {'schedule': schedule, 'envelope': envelope,
                'queries': list(zip(cohort['requests'], core['queries']))}, roots)
    sealed(receipt)
    require(receipt['arm_slots'] == len(slots) and receipt['scheduled_pairs'] == len(schedule['pairs']),
            'FACTORY_RECEIPT_CENSUS')
    require(receipt['source_schedule_sha256'] == schedule['artifact_sha256'] and
            receipt['source_package_sha256'] == original_sha and receipt['source_manifest_sha256'] == manifest,
            'FACTORY_RECEIPT_PARENT')
    return envelope, receipt


def scanner_boundary(cohort, batch, core, roots, scanner_commit):
    """Bind actual Scanner schema + original bytes to Discoverer's proposed input.

    The added sidecar contains missing full-universe identity; it is TEST_ONLY.
    It is never described as a field already supplied by the Scanner engine.
    """
    require(batch['schema'] == 'aql.work.scanner-sidecar.v2' and batch['test_only'] is True,
            'SCANNER_SIDECAR_VERSION')
    require(batch['independent_witness'] is None, 'FORGED_INDEPENDENT_WITNESS')
    require(batch['source_raw_sha256'] == cohort['objects']['source']['sha256'] and
            batch['source_manifest_sha256'] == core['registration']['manifest_integrity_sha256'],
            'SCANNER_SOURCE_PARENT')
    universe = batch['universe']
    require(0 < len(universe) <= 64 and len({u['attempt_id'] for u in universe}) == len(universe),
            'DUPLICATE_UNIVERSE_ATTEMPT')
    require(all(u['state'] in {'NOMINATED', 'REJECTED', 'UNKNOWN', 'FAILED', 'INELIGIBLE', 'UNSCANNED'}
                for u in universe), 'UNIVERSE_STATE')
    require(len({(u['symbol'], u['profile']) for u in universe}) == len(universe), 'CONFLICTING_UNIVERSE_IDENTITY')
    require(all(type(v) is int and v >= 0 for v in batch['census'].values()), 'INVALID_CENSUS_INTEGER')
    attempt_map = {u['attempt_id']: u for u in universe}
    expected = {u['attempt_id'] for u in universe if u['state'] not in {'INELIGIBLE', 'UNSCANNED'}}
    attempts = batch['attempts']
    require({a['attempt_id'] for a in attempts} == expected and len(attempts) == len(expected),
            'MISSING_SCANNER_DENOMINATOR')
    counts = Counter(u['state'] for u in universe)
    require(batch['census'] == {k: counts[k] for k in
            ('NOMINATED', 'REJECTED', 'UNKNOWN', 'FAILED', 'INELIGIBLE', 'UNSCANNED')}, 'SCANNER_CENSUS_DRIFT')
    admitted = []
    request_cutoffs = {r['decision_cutoff_ms'] for r in cohort['requests']}
    for a in attempts:
        member = attempt_map[a['attempt_id']]
        e, r = a['envelope'], a['receipt']
        envelope_raw = bytes.fromhex(a['envelope_raw_hex'])
        receipt_raw = bytes.fromhex(a['receipt_raw_hex'])
        require(strict_json(envelope_raw) == e and strict_json(receipt_raw) == r, 'SCANNER_ORIGINAL_BYTES_DRIFT')
        require(e['schema_version'] == r['schema_version'] == 'AQL-SCANNER-V1', 'SCANNER_VERSION')
        require(e['publishable'] is False and e['delivery_authorized'] is False, 'SCANNER_AUTHORITY')
        require(e['availability_class'] == 'RETROSPECTIVE_NON_PIT', 'SCANNER_PIT_UPGRADE')
        require(e['source_manifest']['dataset_id'] == cohort['spec']['dataset_id']
                and e['source_manifest']['dataset_sha'] == batch['source_raw_sha256'], 'SCANNER_MANIFEST_SOURCE')
        cutoff = ms(e['cutoff_at'])
        require(cutoff in request_cutoffs and ms(e['source_manifest']['cutoff_at']) == cutoff,
                'SCANNER_CUTOFF_DRIFT')
        require(ms(e['source_manifest']['created_at']) <= cutoff, 'FUTURE_MANIFEST')
        require(e['stage'] == ('UNKNOWN' if member['state'] == 'FAILED' else member['state']),
                'SCANNER_STATUS_PROMOTION')
        require(e['candidate_id'] == a['attempt_id'], 'SCANNER_CANDIDATE_IDENTITY')
        require(e['profile_id'] == member['profile'] and r['profile'] == member['profile']
                and r['symbol'] == member['symbol'] and r['scanner_id'] == e['scanner_id']
                and r['stage'] == e['stage'] and r['score'] == e['score']
                and r['score_status'] == e['score_status'], 'SCANNER_HEADER_DRIFT')
        native = lambda obj: json.dumps(obj, sort_keys=True, separators=(',', ':'),
                                        ensure_ascii=False, allow_nan=False).encode()
        require(r['payload_digest'] == sha(native(e)), 'SCANNER_PAYLOAD_DIGEST')
        require(e['digest'] == sha(native({k:v for k,v in e.items() if k != 'digest'})), 'SCANNER_ENVELOPE_DIGEST')
        require(r['claim_at'] == r['committed_at'] == e['cutoff_at'], 'SCANNER_RECEIPT_CLOCK')
        require(e['score'] is None and e['score_status'] == 'SCORE_UNAVAILABLE', 'UNCOMPUTED_SCORE_REQUIRED')
        require(e['feature_snapshot']['uncomputed_feature'] is None, 'UNCOMPUTED_FEATURE_REQUIRED')
        coverage = e['coverage']
        require(coverage['resampling'] == 'NOT_CONNECTED' and
                coverage['source_interval'] == cohort['spec']['interval'], 'UNAUTHORIZED_RESAMPLING')
        require(coverage['symbol'] == cohort['spec']['symbol'] == member['symbol'] and
                coverage['timeframe'] == batch['timeframe'], 'SCANNER_SYMBOL_TIMEFRAME')
        require(coverage['available_at_ms'] is None or
                (type(coverage['available_at_ms']) is int and coverage['available_at_ms'] <= cutoff),
                'FUTURE_FEATURE_AVAILABILITY')
        verified = worker('scanner', {'envelope': e, 'receipt': r, 'run_id': batch['scan_run_id']}, roots)
        require(verified['envelope'] == e and verified['receipt'] == r, 'SCANNER_ROUNDTRIP_DRIFT')
        # Work supplies required context absent from native ScannerNominationEnvelope.
        # A null witness maps to an explicit hash sentinel in a QUARANTINED contract only.
        raw = {'schema_version': 'aql.scanner-adapter.input.v1', 'scanner_contract_version': 'AQL-SCANNER-V1',
               'scanner_source_commit': scanner_commit, 'scan_run_id': batch['scan_run_id'],
               'market': e['market'], 'symbol': member['symbol'], 'timeframe': batch['timeframe'],
               'profile': member['profile'], 'cutoff_ms': cutoff,
               'source_dataset_id': cohort['spec']['dataset_id'], 'source_dataset_version': cohort['spec']['version'],
               'source_raw_sha256': batch['source_raw_sha256'], 'source_manifest_sha256': batch['source_manifest_sha256'],
               'universe_snapshot_sha256': digest(universe), 'full_universe_denominator': len(universe),
               'eligible_selected': len(expected), 'ineligible': counts['INELIGIBLE'], 'unscanned': counts['UNSCANNED'],
               'screened_rejected': counts['REJECTED'], 'unknown': counts['UNKNOWN'],
               'nominated': counts['NOMINATED'], 'failed_attempts': counts['FAILED'],
               'omission_reason_codes': ['TEST_ONLY_SIDECAR_NOT_NATIVE_CENSUS', 'INDEPENDENT_WITNESS_NOT_CONNECTED'],
               'independent_verifier_receipt_sha256': '0' * 64,
               'envelope_hex': envelope_raw.hex(), 'receipt_hex': receipt_raw.hex()}
        outcome = worker('discoverer', raw, roots)
        evidence = outcome['evidence']
        require(outcome['eligible'] is False and outcome['quarantine'] == 'UNKNOWN_DEFERRED' and
                evidence['evidence_class'] == 'UNKNOWN_UNVERIFIED' and evidence['source_availability'] == 'UNKNOWN',
                'DISCOVERER_QUARANTINE_PROMOTION')
        require(evidence['scanner_envelope_sha256'] == sha(envelope_raw) and evidence['scanner_receipt_sha256'] == sha(receipt_raw),
                'DISCOVERER_BYTE_PARENT')
        admitted.append({'attempt_id': a['attempt_id'], 'original_state': member['state'], **outcome})
    return {'schema': 'aql.work.scanner-discoverer-boundary-result.v2',
            'original_universe': universe, 'census': batch['census'], 'attempts': admitted,
            'eligible_count': 0, 'candidate_count': 0, 'witness': 'NOT_CONNECTED',
            'authentic_route': 'NOT_CONNECTED_SCANNER_P0_UNRESOLVED'}


def run_v2(manifest_path, expected_sha, roots, output):
    manifest_path = Path(manifest_path)
    raw = read_bytes(manifest_path)
    require(sha(raw) == expected_sha, 'MANIFEST_SHA_MISMATCH')
    lock = strict_json(raw)
    require(set(lock) == {'schema', 'evidence_class', 'owner_order', 'work_parent',
            'fixture_origin', 'components', 'cohorts'}, 'UNEXPECTED_MANIFEST_PAYLOAD')
    require(lock['schema'] == SCHEMA and lock['evidence_class'] == 'TEST_ONLY', 'PRIVATE_OR_VERSION_FORBIDDEN')
    require(0 < len(lock['cohorts']) <= 4, 'COHORT_BUDGET')
    require(len({c['spec']['dataset_id'] for c in lock['cohorts']}) == len(lock['cohorts']), 'DUPLICATE_COHORT')
    checkouts(lock, roots)
    root = manifest_path.parent
    cohorts = []
    for c in lock['cohorts']:
        core = core_call(root, c, roots)
        schedule = load_object(root, c['objects']['schedule'])
        slots = load_object(root, c['objects']['slots'])
        batch = load_object(root, c['objects']['scanner'])
        envelope, receipt = factory_boundary(c, schedule, slots, core, roots)
        boundary = scanner_boundary(c, batch, core, roots, lock['components']['scanner']['commit_sha'])
        cohorts.append({'dataset_id': c['spec']['dataset_id'], 'original_source_sha256': c['objects']['source']['sha256'],
                        'core': core, 'factory_envelope': envelope, 'factory_receipt': receipt,
                        'scanner_discoverer': boundary})
    store = ReceiptStore(output)
    manifest_key = store.put(lock)
    parents = [store.put({'schema': SCHEMA + '.cohort', 'parent_manifest_sha256': manifest_key,
                         'evidence_class': 'TEST_ONLY', **c}) for c in cohorts]
    counts = Counter()
    for c in cohorts:
        counts.update(c['factory_receipt']['status_counts'])
    summary = {'schema': SCHEMA + '.summary', 'evidence_class': 'TEST_ONLY', 'manifest_sha256': expected_sha,
               'parent_manifest_sha256': manifest_key, 'parents': parents,
               'source_matrix': {n: s['commit_sha'] for n,s in lock['components'].items()},
               'factory_pairs': sum(c['factory_receipt']['scheduled_pairs'] for c in cohorts),
               'factory_arm_slots': sum(c['factory_receipt']['arm_slots'] for c in cohorts),
               'factory_status_counts': dict(sorted(counts.items())),
               'scanner_census': {k:sum(c['scanner_discoverer']['census'][k] for c in cohorts)
                                 for k in ('NOMINATED','REJECTED','UNKNOWN','FAILED','INELIGIBLE','UNSCANNED')},
               'discoverer_attempts': sum(len(c['scanner_discoverer']['attempts']) for c in cohorts),
               'discoverer_eligible': 0, 'candidates_generated': 0,
               'authentic_paths': 'NOT_CONNECTED', 'scanner_quarantine': 'P0_UNRESOLVED_UNKNOWN_DEFERRED',
               'discoverer_candidate_to_factory': 'NOT_CONNECTED_SCANNER_QUARANTINE_AND_EXPLICIT_OWNER_BINDING_REQUIRED',
               'source_to_scanner_features': 'NOT_CONNECTED_NO_RESAMPLING_OR_FEATURE_COMPUTATION',
               'private_run': 'NOT_PERFORMED', 'evaluation': 'NOT_PERFORMED',
               'scientific_acceptance': 'NOT_OBTAINED', 'g0': 'NOT_APPROVED',
               'verdict': 'TEST_ONLY_CONTRACT_BOUNDARY_GATE'}
    return store.put(summary), summary
