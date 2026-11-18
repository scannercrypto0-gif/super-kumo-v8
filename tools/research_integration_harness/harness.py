"""Versioned adapters over retained output bytes; never evaluates a strategy."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile

VERSION = 'aql.work.research-integration.v1'
MAX_BYTES = 8 * 1024 * 1024
MAX_DATASETS = 16
MAX_PAIRS = 10000
HASH = re.compile(r'[0-9a-f]{64}')
SCHEMAS = {'core': 'aql.p2.core.paired-schedule.v1',
           'factory': 'aql.p2.factory.breakout-modeled-trades.v1',
           'history': 'HistoricalLibrary.DatasetManifest.v1', 'vault': 'raw_object.v1'}


class BoundaryError(ValueError):
    """Closed affected integration boundary; no evidence upgrade."""


def require(ok, reason):
    if not ok:
        raise BoundaryError(reason)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(obj):
    return sha(canonical(obj))


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: require(False, 'NONFINITE_JSON'))


def confined(root, relative):
    root = Path(root).resolve()
    p = Path(relative)
    require(not p.is_absolute() and '..' not in p.parts, 'PATH_ESCAPE')
    target = root / p
    require(not any(x.is_symlink() for x in [target, *target.parents] if x != root.parent),
            'SYMLINK_INPUT')
    require(target.resolve().is_relative_to(root), 'PATH_ESCAPE')
    return target


def read_bytes(path):
    require(path.stat().st_size <= MAX_BYTES, 'RESOURCE_LIMIT_BYTES')
    with path.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    require(len(raw) <= MAX_BYTES, 'RESOURCE_LIMIT_BYTES')
    return raw


def load_object(root, ref):
    require(set(ref) == {'path', 'sha256'}, 'BAD_OBJECT_REFERENCE')
    require(isinstance(ref['sha256'], str) and HASH.fullmatch(ref['sha256']), 'BAD_SHA')
    raw = read_bytes(confined(root, ref['path']))
    require(sha(raw) == ref['sha256'], 'INPUT_SHA_MISMATCH')
    return strict_json(raw)


def sealed(obj):
    require(obj.get('artifact_sha256') == digest({k: v for k, v in obj.items()
                                                if k != 'artifact_sha256'}), 'TAMPERED_RECEIPT')


def modules(manifest, roots):
    """Explicit offline checkout mapping; verify bytes before loading pure contracts."""
    result = {}
    for name in SCHEMAS:
        spec = manifest['components'][name]
        require(spec['contract'] == SCHEMAS[name], 'STALE_ADAPTER_CONTRACT')
        require(re.fullmatch('[0-9a-f]{40}', spec['commit_sha']) is not None, 'BAD_COMPONENT_SHA')
        require(name in roots, 'MISSING_ADAPTER_CHECKOUT:' + name)
        path = confined(roots[name], spec['path'])
        require(sha(read_bytes(path)) == spec['file_sha256'], 'COMPONENT_SOURCE_DRIFT:' + name)
        # Factory is a receipt projection only: no evaluator import or call.
        if name == 'factory':
            continue
        module_name = '_aql_work_contract_' + name
        loader = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(loader)
        sys.modules[module_name] = module
        loader.loader.exec_module(module)
        result[name] = module
    return result


def prior_harness(manifest, roots):
    """Reuse #214 retained evidence only; its old producer harness has import side effects."""
    ref = manifest['prior_harness']
    require('prior' in roots, 'MISSING_PRIOR_HARNESS_CHECKOUT')
    require(ref['commit_sha'] == '0f0c4377db7682187dca78b2c556b00ae1a81bab',
            'STALE_PRIOR_HARNESS_MAPPING')
    raw = read_bytes(confined(roots['prior'], ref['path']))
    require(sha(raw) == ref['file_sha256'], 'PRIOR_HARNESS_SOURCE_DRIFT')
    obj = strict_json(raw)
    require(obj['bundle_type'] == ref['contract'], 'PRIOR_HARNESS_CONTRACT')
    return {'source_sha256': sha(raw), 'component_commit_sha': ref['commit_sha'],
            'bundle_type': obj['bundle_type'], 'prior_pinned_shas': obj['pinned_shas'],
            'prior_reported_result': obj['harness_v2']['result'],
            'status': 'REUSED_READ_ONLY_NOT_REVALIDATED',
            'current_contract_coverage': 'NOT_CONNECTED_OLD_CORE216_FACTORY209',
            'prior_blockers': obj['labels']['BLOCKED_EXTERNAL_EVIDENCE']}


def adapt_dataset(root, entry, mods, evidence):
    data = {name: load_object(root, entry['objects'][name]) for name in ('raw', *SCHEMAS)}
    bars, history, vault, core, factory = (data[x] for x in ('raw', 'history', 'vault', 'core', 'factory'))
    raw_sha = entry['objects']['raw']['sha256']
    require(entry['dataset_id'] == history['dataset_id'] == core['source']['source_id']
            == factory['source_id'], 'CROSS_COHORT_IDENTITY')
    require(entry['symbol'] == history['symbol'] == vault['instrument'] == core['source']['symbol'],
            'SYMBOL_IDENTITY_DRIFT')
    require(raw_sha == history['source_hash'] == vault['content_sha256']
            == core['source']['source_package_sha256'] == factory['source_package_sha256'],
            'SOURCE_HASH_DRIFT')
    require(vault['byte_length'] == confined(root, entry['objects']['raw']['path']).stat().st_size,
            'RAW_LENGTH_DRIFT')
    require(core['schema'] == SCHEMAS['core'] and factory['schema'] == SCHEMAS['factory'],
            'STALE_OUTPUT_CONTRACT')
    require(vault['schema_version'] == SCHEMAS['vault'], 'STALE_VAULT_CONTRACT')
    mods['vault'].validate_meta(mods['vault'].RawObjectMeta.from_dict(vault))
    try:
        hm = mods['history'].DatasetManifest.from_dict(history)
    except mods['history'].HistoricalDataError as exc:
        raise BoundaryError(str(exc)) from exc
    require(hm.provenance_verified and hm.verify_integrity(), 'HISTORY_MANIFEST_INTEGRITY')
    sealed(core)
    sealed(factory)
    require(core['source']['manifest_sha256'] == entry['objects']['history']['sha256'],
            'HISTORY_PARENT_DRIFT')
    require(core['source']['normalized_sha256'] == raw_sha, 'NORMALIZED_SOURCE_DRIFT')
    require(factory['source_schedule_sha256'] == core['artifact_sha256'], 'FORGED_PARENT')
    if evidence == 'TEST_ONLY':
        require(core['test_only'] is True and vault['evidence_class'] == 'FIXTURE_SYNTHETIC',
                'FIXTURE_EVIDENCE_UPGRADE')
        require(entry['dataset_id'].startswith('TEST_ONLY_'), 'FIXTURE_IDENTITY_NAMESPACE')
    else:
        require(core['test_only'] is False and vault['evidence_class'] != 'FIXTURE_SYNTHETIC',
                'SYNTHETIC_AS_AUTHENTIC')
    require(core['evidence_class'] == 'RETROSPECTIVE_NON_PIT', 'UNSUPPORTED_PIT_UPGRADE')
    require(factory['execution_status'] == 'NOT_OBSERVED', 'EXECUTION_CLAIM')
    require(0 < len(bars) <= MAX_PAIRS and 0 < len(core['pairs']) <= MAX_PAIRS, 'RESOURCE_LIMIT_ROWS')
    typed_bars = [mods['core'].HistoricalBarV1(**b) for b in bars]
    source = mods['core'].HistoricalSourceV1(**core['source'])
    mods['core'].validate_bars(source, typed_bars)
    require(history['bar_count'] == core['source_bar_count'] == len(bars), 'BAR_CENSUS_DRIFT')
    require(history['min_bar_open'] == entry['start_ms'] == bars[0]['open_ms'] and
            entry['end_exclusive_ms'] == bars[-1]['close_ms'] + 1 and
            history['max_bar_open'] == bars[-1]['open_ms'], 'COHORT_BOUNDARY_DRIFT')
    require(history['non_final_count'] == 0 and history['duplicate_count'] == 0, 'NONFINAL_HISTORY')
    trial = mods['core'].FrozenTrialV1(**core['protocol'])
    expected = set()
    identities = set()
    unknown_availability = 0
    rows = []
    opportunities = []
    for pair in core['pairs']:
        op = mods['core'].P2HistoricalOpportunityV1(**pair['opportunity'])
        require(op.opportunity_id not in identities, 'DUPLICATE_OPPORTUNITY')
        identities.add(op.opportunity_id)
        opportunities.append({'pair_id': pair['pair_id'], **pair['opportunity']})
        require(op.source_id == entry['dataset_id'] and op.source_package_sha256 == raw_sha
                and op.trial_id == trial.trial_id, 'CROSS_COHORT_OPPORTUNITY')
        require(pair['pair_id'] == mods['core']._hash(dict(protocol_sha256=trial.protocol_sha256,
                trial_id=trial.trial_id, opportunity_id=op.opportunity_id)), 'CONFLICTING_PAIR_IDENTITY')
        require(op.decision_cutoff_ms <= entry['decision_cutoff_ms']
                and entry['start_ms'] < op.decision_cutoff_ms <= entry['end_exclusive_ms']
                and op.decision_cutoff_ms < trial.train_end_exclusive_ms
                and op.decision_ms < trial.train_end_exclusive_ms, 'CUTOFF_LOOKAHEAD')
        prefix = [b for b in bars if b['close_ms'] < op.decision_cutoff_ms]
        require(prefix and prefix[-1]['close_ms'] + 1 == op.decision_cutoff_ms, 'CUTOFF_NOT_BAR_BOUNDARY')
        require(all(b['available_at_ms'] is None or b['available_at_ms'] <= op.decision_cutoff_ms
                    for b in prefix), 'FUTURE_AVAILABILITY')
        unknown_availability += any(b['available_at_ms'] is None for b in prefix)
        require(len(pair['arms']) == 2 and {a['arm'] for a in pair['arms']} == {'BASE', 'SHADOW'},
                'MISSING_OR_DUPLICATE_ARM')
        for arm in pair['arms']:
            require(arm['definition_sha256'] == core['protocol'][arm['arm'].lower() + '_definition_sha256'],
                    'ARM_POLICY_DRIFT')
            expected.add((pair['pair_id'], arm['arm']))
    require(core['scheduled_total'] == len(core['pairs']) == factory['pair_count'], 'PAIR_CENSUS_DRIFT')
    require(factory['arm_count'] == len(factory['modeled_trades']) == len(expected), 'ARM_CENSUS_DRIFT')
    seen = set()
    for row in factory['modeled_trades']:
        key = (row['pair_id'], row['arm'])
        require(key in expected and key not in seen, 'DUPLICATE_OR_FOREIGN_FACTORY_IDENTITY')
        seen.add(key)
        require(row['disposition'] in {'TRIGGERED', 'NO_SIGNAL', 'REJECTED', 'UNKNOWN'}, 'BAD_DISPOSITION')
        require(type(row['censored']) is bool, 'BAD_CENSOR_FLAG')
        require((row['status'] == 'MODELED_COMPLETE') == (row['disposition'] == 'TRIGGERED')
                and (row['status'] == 'UNKNOWN') == (row['disposition'] == 'UNKNOWN'),
                'DISPOSITION_STATUS_DRIFT')
        require(row['status'] in {'MODELED_COMPLETE', 'INELIGIBLE', 'UNKNOWN'}, 'BAD_RESULT_STATUS')
        require((row['modeled_net_return'] is None) == (row['status'] != 'MODELED_COMPLETE'),
                'NULL_ACCOUNTING_DRIFT')
        require(not row['censored'] or row['modeled_net_return'] is None, 'CENSORED_WITH_RESULT')
        # Keep original pair/arm/status/nulls. Never calculate or fill any result.
        rows.append({k: row[k] for k in ('pair_id', 'arm', 'disposition', 'status', 'censored')}
                    | {'result_is_null': row['modeled_net_return'] is None})
    require(seen == expected, 'MISSING_FACTORY_ARM')
    return {'dataset_id': entry['dataset_id'], 'symbol': entry['symbol'],
            'pairs': len(core['pairs']), 'arms': len(rows),
            'null': sum(r['result_is_null'] for r in rows),
            'censored': sum(r['censored'] for r in rows),
            'rejected': sum(r['disposition'] == 'REJECTED' for r in rows),
            'unknown': sum(r['disposition'] == 'UNKNOWN' for r in rows),
            'availability_unknown_opportunities': unknown_availability,
            'rows': rows, 'opportunities': opportunities, 'input_sha256': {k: v['sha256'] for k, v in entry['objects'].items()},
            'source_authentication': 'NOT_ATTESTED_BY_HARNESS', 'pit': 'NOT_ATTESTED'}


class ReceiptStore:
    """Create-only, fsynced content objects. Staging debris never means committed."""
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        require(not self.root.is_symlink(), 'SYMLINK_STORE')

    def put(self, value):
        raw = canonical(value)
        require(len(raw) <= MAX_BYTES, 'RESOURCE_LIMIT_OUTPUT')
        key = sha(raw)
        target = self.root / (key + '.json')
        require(not target.is_symlink(), 'SYMLINK_OBJECT')
        if target.exists():
            require(read_bytes(target) == raw, 'EXISTING_OBJECT_TAMPERED')
            return key
        require(sum(1 for _ in self.root.iterdir()) < 4096, 'RESOURCE_LIMIT_STORE')
        fd, name = tempfile.mkstemp(prefix='.staging-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(name, target)  # atomic create-only publication
            except FileExistsError:
                require(read_bytes(target) == raw, 'CONCURRENT_OBJECT_CONFLICT')
            if hasattr(os, 'O_DIRECTORY'):
                dfd = os.open(self.root, os.O_DIRECTORY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
        finally:
            os.unlink(name)
        return key


def run(manifest_path, expected_sha, roots, output):
    raw = read_bytes(Path(manifest_path))
    require(sha(raw) == expected_sha, 'MANIFEST_SHA_MISMATCH')
    manifest = strict_json(raw)
    require(set(manifest) == {'schema', 'evidence_class', 'components', 'datasets',
            'optional_connections', 'fixture_origin', 'contract_mapping', 'prior_harness',
            'optional_contract_inventory'},
            'UNEXPECTED_MANIFEST_FIELD')
    require(manifest['schema'] == VERSION, 'MANIFEST_VERSION')
    for entry in manifest['datasets']:
        require(set(entry) == {'dataset_id', 'symbol', 'start_ms', 'end_exclusive_ms',
                'decision_cutoff_ms', 'objects'}, 'UNEXPECTED_DATASET_FIELD')
        require(set(entry['objects']) == {'raw', *SCHEMAS}, 'MISSING_ADAPTER_OBJECT')
    require(manifest['evidence_class'] in {'TEST_ONLY', 'RETROSPECTIVE'}, 'PROSPECTIVE_PROOF_NOT_CONNECTED')
    require(0 < len(manifest['datasets']) <= MAX_DATASETS, 'RESOURCE_LIMIT_DATASETS')
    require(set(manifest['components']) == set(SCHEMAS), 'MISSING_COMPONENT')
    mods = modules(manifest, roots)
    prior = prior_harness(manifest, roots)
    ids = [d['dataset_id'] for d in manifest['datasets']]
    require(len(set(ids)) == len(ids), 'DUPLICATE_DATASET')
    require(manifest['optional_connections'] == {k: 'NOT_CONNECTED' for k in
            ('scanner', 'bridge', 'secretary', 'discoverer')}, 'UNAUTHORIZED_CONNECTION')
    root = Path(manifest_path).parent
    cohorts = [adapt_dataset(root, d, mods, manifest['evidence_class'])
               for d in sorted(manifest['datasets'], key=lambda d: d['dataset_id'])]
    # No publication occurs until EVERY input boundary has passed.
    store = ReceiptStore(output)
    manifest_key = store.put(manifest)
    nodes = []
    for cohort in cohorts:
        node = {'schema': VERSION + '.cohort', 'parent_manifest_sha256': manifest_key,
                'evidence_class': manifest['evidence_class'], **cohort}
        nodes.append(store.put(node))
    summary = {'schema': VERSION + '.summary', 'manifest_raw_sha256': expected_sha,
               'manifest_content_sha256': manifest_key, 'parents': nodes,
               'evidence_class': manifest['evidence_class'],
               'lifecycle': ['SOURCE_ADMITTED', 'AVAILABILITY_GUARDED',
                             'UNIVERSE_NOT_CONNECTED', 'NOMINATION_NOT_CONNECTED',
                             'SECRETARY_DISCOVERER_CONTRACT_ONLY', 'FACTORY_RECEIPT_READ_ONLY',
                             'IMMUTABLE_SUMMARY'],
               'connections': manifest['optional_connections'], 'cohorts': cohorts,
               'prior_harness': prior,
               'census': {k: sum(c[k] for c in cohorts) for k in
                          ('pairs', 'arms', 'null', 'censored', 'rejected', 'unknown')},
               'unscanned': {'status': 'UNKNOWN_NOT_CONNECTED', 'count': None},
               'adapter_compatibility': {k: {'contract': v, 'status': 'PROJECTED_OUTPUT_COMPATIBLE',
                    'full_producer_validation': 'NOT_PERFORMED'} for k, v in SCHEMAS.items()},
               'verdict': 'TEST_ONLY_CONTRACT_GATE' if manifest['evidence_class'] == 'TEST_ONLY'
                          else 'RETAINED_OUTPUT_INTEGRITY_ONLY',
               'limitations': ['NO_AUTHENTIC_E2E', 'NO_SOURCE_OR_PIT_ATTESTATION',
                               'NO_EVALUATOR_CALLED', 'NO_SCIENTIFIC_ACCEPTANCE',
                               'NO_ACTIVATION_OR_G0', 'SCANNER_BRIDGE_ROUTING_NOT_CONNECTED']}
    key = store.put(summary)
    return key, summary
