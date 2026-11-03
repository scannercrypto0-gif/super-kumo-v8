"""Read-only Work #223 -> pinned Core #221 source constructor handshake.

No source acquisition, opportunity creation, paired schedule, outcome or alpha.
The external Core file must match the reviewed exact-byte pin before import.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from types import ModuleType

from .aql_p2a_public_intake import (
    IntakeError, canonical, parse, read_validated_index, require, sha,
)

CORE_HEAD = '0842fc0a753ec6a3327c00c24e74908e8f6ca39c'
CORE_FILE_SHA = '1162adc7bf755ae3fd7fe4a365c6f9c9409cf8fb74900fa40567456bfffe929d'
RETAINED_MANIFEST_SHA = '9b34e972e05002a7d6b11152e72164af825960b60e36c65ccf8049ce411eb4ff'
RETAINED_HANDOFF_SHA = '4031aea0b421d3749441cf40a09699d8bb0b27cee9320b848b3d1fd1345101bc'
DECLARED_HANDOFF_CORE = '9823f68221cc31e4b12dc11d5713513df22c69fb'


def load_pinned_core(path):
    """Load unchanged external code; no copy/merge into an owner branch."""
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'CORE_MODULE_NOT_AVAILABLE_OR_SYMLINK')
    raw = path.read_bytes()
    require(sha(raw) == CORE_FILE_SHA, 'CORE_MODULE_BYTE_PIN_MISMATCH')
    name = '_aql_p2_core_source_pin_' + CORE_HEAD
    module = ModuleType(name)
    module.__file__ = str(path)
    sys.modules[name] = module  # dataclasses resolves its defining module here
    # Execute exactly the verified snapshot, never reopen it or write pycache.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def validate_mapping(manifest, rows, handoff, core):
    """Actual Core source types are invoked separately for every dataset."""
    require(manifest['status'] == 'COMPLETE_DEVELOPMENT_INTAKE'
            and manifest['phase'] == 'DEVELOPMENT_ONLY'
            and manifest['holdout_fetched'] is False and manifest['holdout_evaluated'] is False,
            'ONLY_COMPLETE_UNOPENED_DEVELOPMENT_INPUT')
    require(handoff['schema'] == 'aql.p2a.core-source-constructor-handoff.v1'
            and handoff['core_contract_sha'] == DECLARED_HANDOFF_CORE,
            'HANDOFF_CONTRACT_OR_DECLARED_PIN_DRIFT')
    require(handoff['opportunities'] is None and handoff['frozen_trial'] is None
            and handoff['comparison_executed'] is False, 'SOURCE_ONLY_NO_CANDIDATE_AUTHORITY')
    windows = {w['dataset_id']: w for w in manifest['development_windows']}
    require(len(windows) == len(manifest['development_windows']), 'DUPLICATE_MANIFEST_DATASET')
    require(set(r['dataset_id'] for r in rows) == set(windows), 'ORPHAN_OR_MISSING_SOURCE_ROWS')
    seen, result = set(), []
    for source in handoff['sources']:
        kw = source['source_kwargs']
        dataset = kw['source_id']
        require(dataset in windows and dataset not in seen, 'MISSING_DUPLICATE_OR_MERGED_DATASET')
        seen.add(dataset)
        window = windows[dataset]
        selected = [r for r in rows if r['dataset_id'] == dataset]
        require(len(selected) == window['expected_bars'] == window['observed_bars'], 'DATASET_DENOMINATOR')
        expected_source = dict(source_id=dataset, exchange='BINANCE', market='SPOT', symbol='BTCUSDT',
            source_package_sha256=window['source']['archive_sha256'],
            manifest_sha256=sha(canonical(manifest)),
            normalized_sha256=sha(b''.join(canonical(r) for r in selected)),
            correction_generation='UNKNOWN_NOT_ATTESTED', interval_ms=900000,
            evidence_class='RETROSPECTIVE_NON_PIT')
        require(kw == expected_source, 'CORE_SOURCE_ARGUMENT_OR_HASH_DOMAIN_DRIFT')
        require(source['normalized_hash_domain'] == 'CANONICAL_JSONL_OF_THIS_DATASET_WORK_BAR_RECORDS',
                'UNDECLARED_NORMALIZED_HASH_DOMAIN')
        require(all(r['historical_known_at_ms'] is None and r['historical_receipt_ms'] is None
                    and r['historical_publication_ms'] is None
                    and r['finality'] == 'ARCHIVED_CLOSED_INTERVAL' for r in selected),
                'NO_PIT_OR_LIVE_FINALITY_UPGRADE')
        expected_bars = [dict(open_ms=r['open_ms'], close_ms=r['close_ms'],
            content_sha256=r['bar_sha256'], finalized=r['is_final'],
            available_at_ms=None, availability_evidence_ref=None) for r in selected]
        require(source['bar_kwargs'] == expected_bars, 'CORE_BAR_ARGUMENT_MAPPING_DRIFT')
        try:
            typed_source = core.HistoricalSourceV1(**kw)
            typed_bars = tuple(core.HistoricalBarV1(**b) for b in source['bar_kwargs'])
            valid = core.validate_bars(typed_source, typed_bars)
        except (core.ContractError, TypeError) as exc:
            raise IntakeError('CORE_SOURCE_CONTRACT_REJECTED: ' + str(exc)) from exc
        result.append({'dataset_id': dataset, 'validated_bars': len(valid),
            'source_archive_sha256': kw['source_package_sha256'],
            'dataset_normalized_sha256': kw['normalized_sha256'],
            'first_open_ms': valid[0].open_ms, 'last_close_ms': valid[-1].close_ms,
            'status': 'COMPATIBLE_CORE_SOURCE_TYPES', 'historical_known_at_ms': None})
    require(seen == set(windows), 'MISSING_HANDOFF_DATASET')
    return result


def run_bridge(directory, core_module, *, adapter_code_sha):
    """Use only this task's retained input; never re-intake or regenerate it."""
    import re
    require(bool(re.fullmatch('[0-9a-f]{40}', adapter_code_sha)), 'ADAPTER_CODE_SHA_REQUIRED')
    root = Path(directory)
    _, manifest, rows = read_validated_index(root, expected_manifest_sha256=RETAINED_MANIFEST_SHA)
    raw = (root / 'core-source-handoff.json').read_bytes()
    require(sha(raw) == RETAINED_HANDOFF_SHA, 'RETAINED_HANDOFF_RAW_SHA_DRIFT')
    handoff = parse(raw)
    core = load_pinned_core(core_module)
    results = validate_mapping(manifest, rows, handoff, core)
    return {'schema': 'aql.p2a-core-source-bridge-receipt.v1',
        'status': 'COMPATIBLE_SOURCE_MAPPING_ONLY', 'adapter_code_sha': adapter_code_sha,
        'intake_code_sha': manifest['code_sha'], 'core_runtime_head': CORE_HEAD,
        'core_module_sha256': CORE_FILE_SHA, 'handoff_declared_core_head': handoff['core_contract_sha'],
        'input_manifest_sha256': RETAINED_MANIFEST_SHA, 'input_handoff_sha256': RETAINED_HANDOFF_SHA,
        'input_bar_index_sha256': manifest['bar_index_sha256'],
        'datasets': results, 'validated_bars': sum(r['validated_bars'] for r in results),
        'per_dataset_validation_calls': len(results), 'evidence_class': 'RETROSPECTIVE_NON_PIT',
        'opportunities_created': None, 'schedule_pair_invoked': False,
        'factory_lab_invoked': False, 'base_shadow_comparison_executed': False,
        'holdout_fetched': False, 'holdout_evaluated': False,
        'next_seam': 'NOT_EVALUABLE_MISSING_REAL_OPPORTUNITIES_AND_PREREGISTERED_ARMS'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--intake-directory', type=Path, required=True)
    p.add_argument('--core-module', type=Path, required=True)
    p.add_argument('--adapter-code-sha', required=True)
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    require(not a.receipt.exists(), 'IMMUTABLE_RECEIPT_ALREADY_EXISTS')
    report = run_bridge(a.intake_directory, a.core_module, adapter_code_sha=a.adapter_code_sha)
    raw = canonical(report)
    with a.receipt.open('xb') as f:
        import os
        os.chmod(a.receipt, 0o600)
        f.write(raw); f.flush(); os.fsync(f.fileno())
    print(canonical({'status': report['status'], 'validated_bars': report['validated_bars'],
                     'receipt_sha256': sha(raw), 'core_head': CORE_HEAD}).decode().strip())


if __name__ == '__main__':
    main()
