"""P1-A private original January intake and thin W1 outcome orchestration.

No strategy replay, trading, network, original mutation, or inferred F1/direction.
CLI admits only the independently pinned original private audit package.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import zipfile

from .aql_p0_c1_source import admit_source, load_source
from .aql_p0_c2_producer import (
    load_journal, _verify_factory_receipt, _prefix_checksums_sha256,
    _opportunity_id, _producer_event_id,
)
from .aql_w1_opportunity_outcomes import (
    BAR_MS, HORIZONS, EvidenceError, RetrospectiveSnapshot, market_outcome,
)
from .aql_w1_factory_research_consumer import project, describe_original_p0_f3_effects
from .aql_w1_original_p0_readonly_link import _anchored
from .aql_w1_typed_contract import F3EffectV1

SCHEMA = 'aql-p1-original-opportunity-outcomes.v1'
POLICY = 'P1A-ORIGINAL-JAN-MARKET-v1'
FACTORY_PIN = '47558bea22af5480aa84148fd22bf2890bbe22ae'
PACKAGE_SHA = 'c72b6271b966ab6f522543a04831053556cfbdf3bd9b7b7fd8b4bc433f2ae503'
PREFIX = 'ATLAS_P0_ORIGINAL_AUDIT/'
PINS = {
    'outer.zip': 'f4e0b3680dd56c9fbe680be2473b8de29fc1d8d7e22657973c85945d2bf99f97',
    'manifest.json': 'f731bc19c1d4bb0dfa79198c6739a4dbd356e02904086d4df2a136773bd25456',
    'normalized.json': 'a881cc99e80697f2da57784b5bea91a7f339c6c391d4d53cc0222842168af0f0',
    'core_decision_envelopes.json': 'c66aec31151bc8097ab86da99e0274a741617331994ff43f6f1c65dccbc37444',
    'core_c2_journal.jsonl': '115161328ccecddddbed19d43dc2802c2e00297ff8b91481811aad5947d9e1dc',
    'consumer_receipts.zip': '7bcc5a79ebcf7569255bf196d6d1e7b785449e786c061a6ac8346eb4b5ddba60',
}
ACK_SHA = '312b88e510476255d0a9f1f137b786c8a3d32bf140d0e68339876ba0a01e41d8'
INPUT_MANIFEST_SHA = 'ac82451ad8a8ff57afb825e4e5c6d5103c79cb4f4595cf12b52404acfa12ca7b'


def require(ok, reason):
    if not ok:
        raise EvidenceError(reason)


def hash_bytes(raw):
    return sha256(raw).hexdigest()


def encode(obj):
    return (json.dumps(obj, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=False, allow_nan=False) + '\n').encode()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def reject(_):
        raise EvidenceError('NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


def content_hash(obj):
    return hash_bytes(encode(obj)[:-1])


def zip_members(raw):
    require(len(raw) <= 8 * 1024 * 1024, 'ARCHIVE_COMPRESSED_LIMIT')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        names = [x.filename for x in infos]
        require(len(names) == len(set(names)), 'DUPLICATE_ZIP_MEMBER')
        require(len(names) <= 2048 and sum(x.file_size for x in infos) <= 32 * 1024 * 1024,
                'ARCHIVE_UNCOMPRESSED_LIMIT')
        for info in infos:
            require(not info.filename.startswith(('/', '\\'))
                    and '\\' not in info.filename and ':' not in info.filename
                    and '..' not in info.filename.split('/')
                    and (info.external_attr >> 16) & 0o170000 != 0o120000,
                    'UNSAFE_ZIP_MEMBER')
        return {x.filename: archive.read(x) for x in infos if not x.is_dir()}


def checked_package(raw):
    _anchored(raw, PACKAGE_SHA, 'original private audit package')
    members = zip_members(raw)
    inv_raw = members[PREFIX + 'SHA256SUMS.json']
    _anchored(inv_raw, INPUT_MANIFEST_SHA, 'private input inventory')
    inventory = parse(inv_raw)['files']
    require(len(inventory) == 15, 'INPUT_INVENTORY_COUNT')
    expected = {PREFIX + 'SHA256SUMS.json'}
    for item in inventory:
        key = PREFIX + item['path']
        require(key not in expected, 'DUPLICATE_INPUT_INVENTORY')
        expected.add(key)
        require(len(members[key]) == item['bytes'], 'INPUT_SIZE_DRIFT')
        _anchored(members[key], item['sha256'], key)
    require(set(members) == expected, 'INPUT_INVENTORY_DRIFT')
    inputs = {name: members[PREFIX + 'evidence/' + name] for name in
              (*PINS, 'core_run_summary.json', 'manifest(1).json')}
    for name, anchor in PINS.items():
        _anchored(inputs[name], anchor, name)
    require(inputs['manifest(1).json'] == inputs['manifest.json'], 'MANIFEST_ALIAS_DRIFT')
    return inputs


def join_original(envelopes, receipts, original, ack):
    """Actual original P0 schema join, never fabricated F1 or source pointer fields."""
    require(len(envelopes) == len(receipts), 'RECEIPT_DENOMINATOR')
    identities = ('trial_id', 'opportunity_id', 'producer_event_id', 'envelope_sha256')
    by_id = {}
    opportunities = set()
    for receipt in receipts:
        key = receipt['producer_event_id']
        require(key not in by_id, 'DUPLICATE_RECEIPT')
        by_id[key] = receipt
    result = []
    seen = set()
    for envelope in envelopes:
        key = envelope['producer_event_id']
        require(key not in seen and key in by_id, 'DUPLICATE_OR_MISSING_ENVELOPE')
        require(envelope['opportunity_id'] not in opportunities, 'DUPLICATE_OPPORTUNITY')
        seen.add(key)
        opportunities.add(envelope['opportunity_id'])
        receipt = by_id[key]
        require(content_hash({k: v for k, v in envelope.items() if k != 'envelope_sha256'})
                == envelope['envelope_sha256'], 'ENVELOPE_DIGEST')
        require(content_hash({k: v for k, v in receipt.items() if k != 'receipt_sha256'})
                == receipt['receipt_sha256'], 'RECEIPT_DIGEST')
        require(key in original and key in ack, 'MISSING_JOURNAL_IDENTITY')
        for field in (*identities, 'run_manifest_sha256', 'strategy_digest'):
            require(envelope[field] == receipt[field] == original[key][field] == ack[key][field],
                    'ORIGINAL_JOIN_' + field)
        for field in ('policy_id', 'assumptions_digest', 'source_bytes_sha256'):
            require(original[key][field] == ack[key][field], 'JOURNAL_LINEAGE_' + field)
        require(original[key]['source_bytes_sha256'] == PINS['outer.zip'], 'ORIGINAL_SOURCE_DRIFT')
        require(original[key]['state'] == 'APPLIED' and ack[key]['state'] == 'ACKED',
                'ORIGINAL_VS_COPY_AUTHORITY')
        result.append((envelope, receipt))
    require(set(by_id) == set(original) == set(ack) == seen, 'ORPHAN_IDENTITY')
    return result


def load_original(path):
    """Only copies to private temporary files for existing read-only C2 validators."""
    inputs = checked_package(Path(path).read_bytes())
    envelopes = parse(inputs['core_decision_envelopes.json'])
    summary = parse(inputs['core_run_summary.json'])
    admitted = admit_source(outer_zip_bytes=inputs['outer.zip'],
                            manifest_bytes=inputs['manifest.json'],
                            normalized_bytes=inputs['normalized.json'])
    require(len(envelopes) == 653, 'ORIGINAL_653_REQUIRED')
    manifest = load_source(admitted=admitted, dataset_id=envelopes[0]['dataset_id'],
                           dataset_version=envelopes[0]['dataset_version'])
    factory = zip_members(inputs['consumer_receipts.zip'])
    ack_raw = factory['core_c2_journal_ack_copy.jsonl']
    _anchored(ack_raw, ACK_SHA, 'isolated ACK copy')
    require(ack_raw.startswith(inputs['core_c2_journal.jsonl']), 'ORIGINAL_PREFIX_DRIFT')
    names = sorted(n for n in factory if n.startswith('consumer_receipts/') and n.endswith('.json'))
    receipts = [parse(factory[n]) for n in names]
    require(len(names) == 653, 'ORIGINAL_RECEIPTS_653_REQUIRED')
    with tempfile.TemporaryDirectory(prefix='aql-p1a-private-') as temp:
        root = Path(temp)
        # Explicit allowlist, no uploaded code execution or general archive extraction.
        for name in ('core_c2_journal.jsonl',):
            (root / name).write_bytes(inputs[name])
        (root / 'ack.jsonl').write_bytes(ack_raw)
        (root / 'consumer_receipts').mkdir()
        for name in (*names, 'consumer_receipts/financial_receipts.jsonl'):
            (root / name).write_bytes(factory[name])
        journal = load_journal(root / 'core_c2_journal.jsonl')
        ack = load_journal(root / 'ack.jsonl')
        pairs = join_original(envelopes, receipts,
                              {k: asdict(v) for k, v in journal.entries.items()},
                              {k: asdict(v) for k, v in ack.entries.items()})
        for e, r in pairs:
            name = 'consumer_receipts/' + e['producer_event_id'] + '.json'
            require(name in factory, 'RECEIPT_FILENAME_IDENTITY')
            verified = _verify_factory_receipt(root / name, journal.entries[e['producer_event_id']])
            require(verified == ack.entries[e['producer_event_id']].consumer_receipt_hash,
                    'ACK_RECEIPT_BYTES_DRIFT')
    require(Counter(r['effect_disposition'] for _, r in pairs) ==
            Counter(NO_SIGNAL=616, REJECTED=27, TRIGGERED=10), 'ORIGINAL_DISPOSITION_DRIFT')
    bars = [dict(open_ms=b.bar_open_ms, open=b.open, high=b.high, low=b.low,
                 close=b.close, finalized=b.is_final) for b in manifest.bars]
    for i, (e, r) in enumerate(pairs):
        prefix = manifest.bars[:i + 20]
        require(e['decision_cutoff_ms'] == prefix[-1].bar_close_ms + 1
                and e['decision_ms'] == e['decision_cutoff_ms'] + 2000,
                'CUTOFF_LOOKAHEAD_OR_GRID')
        require(_prefix_checksums_sha256(prefix) == e['prefix_bar_checksums_sha256'], 'PREFIX_DRIFT')
        require(_opportunity_id(e['trial_id'], e['strategy_instance_id'], e['decision_cutoff_ms'],
                                e['dataset_version']) == e['opportunity_id'], 'OPPORTUNITY_IDENTITY')
        require(_producer_event_id(e['run_manifest_sha256'], e['opportunity_id'],
                                  e['prefix_bar_checksums_sha256']) == e['producer_event_id'],
                'PRODUCER_IDENTITY')
        require(e['availability_mode'] == 'RETROSPECTIVE_NON_PIT'
                and e['run_manifest_sha256'] == summary['run_manifest_sha256'], 'SCOPE_OR_PARENT_DRIFT')
    finance = [parse(x) for x in factory['consumer_receipts/financial_receipts.jsonl'].splitlines() if x.strip()]
    require(len(finance) == 20 and len({x['event_id'] for x in finance}) == 20, 'FINANCIAL_DENOMINATOR')
    validate_finance_refs(pairs, finance)
    return pairs, bars, manifest.window_end_exclusive_ms, {
        'package_sha256': PACKAGE_SHA, 'input_manifest_sha256': INPUT_MANIFEST_SHA,
        'original_file_sha256': {n: hash_bytes(b) for n, b in inputs.items()},
        'source_end_exclusive_ms': manifest.window_end_exclusive_ms,
        'source_bar_count': len(bars), 'original_journal_states': {'APPLIED': 653, 'ACKED': 0},
        'isolated_ack_copy_states': {'ACKED': 653}, 'original_financial_events': len(finance),
        'original_code_sha': summary['code_sha'], 'source_available_at_ms': None,
        'historical_pit': 'NOT_AUTHENTICATED', 'correction_history': 'UNKNOWN_NOT_ATTESTED',
    }


def validate_finance_refs(pairs, finance):
    """Read persisted event references only; no fills, fees, ledger or PnL generation."""
    by_id = {f['event_id']: f for f in finance}
    require(len(by_id) == len(finance), 'DUPLICATE_FINANCIAL_ID')
    for f in finance:
        require(f['payload_hash'] == content_hash({k: v for k, v in f.items() if k != 'payload_hash'}),
                'FINANCIAL_PAYLOAD_DRIFT')
    referenced = []
    for e, r in pairs:
        ids, hashes = r['ordered_financial_event_ids'], r['ordered_financial_payload_hashes']
        require(len(ids) == len(hashes) == (2 if r['effect_disposition'] == 'TRIGGERED' else 0),
                'ORIGINAL_FINANCIAL_REFERENCE_COUNT')
        for eid, ph in zip(ids, hashes):
            require(eid in by_id and by_id[eid]['opportunity_id'] == e['opportunity_id']
                    and by_id[eid]['payload_hash'] == ph, 'FINANCIAL_OWNERSHIP_DRIFT')
            referenced.append(eid)
    require(len(referenced) == len(set(referenced)) and set(referenced) == set(by_id),
            'ORPHAN_OR_REUSED_FINANCIAL_EVENT')


def window(snapshot, horizon, bars, source_end):
    """Unsigned market projection around W1's validated window/direction boundary."""
    legacy = market_outcome(snapshot, horizon, bars, source_version=PINS['outer.zip'],
        source_end_exclusive_ms=source_end, policy_version=POLICY,
        correction_generation='UNKNOWN_NOT_ATTESTED')
    start, end = snapshot.decision_cutoff_ms, snapshot.decision_cutoff_ms + horizon
    selected = sorted((b for b in bars if start <= b['open_ms'] < min(end, source_end)),
                      key=lambda b: b['open_ms'])
    opens = [b['open_ms'] for b in selected]
    expected_observed = range(start, min(end, source_end), BAR_MS)
    reason, availability = None, 'COMPLETE'
    if len(opens) != len(set(opens)):
        availability, reason = 'UNKNOWN', 'DUPLICATE_BAR'
    elif sorted(opens) != list(expected_observed):
        availability, reason = 'UNKNOWN', 'GAPPED_WINDOW'
    elif any(not b.get('finalized', False) for b in selected):
        availability, reason = 'UNKNOWN', 'UNFINALIZED_BAR'
    else:
        for b in selected:
            vals = [b.get(k) for k in ('open', 'high', 'low', 'close')]
            if (any(type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in vals)
                    or b['low'] > min(b['open'], b['close'])
                    or b['high'] < max(b['open'], b['close'])):
                availability, reason = 'UNKNOWN', 'INVALID_OHLC'
                break
        if availability == 'COMPLETE' and end > source_end:
            availability, reason = 'CENSORED', 'ARCHIVE_END_CENSORED'
    metrics = None
    if availability == 'COMPLETE':
        require(legacy['reason'] == 'DIRECTION_NOT_ESTABLISHED', 'UNEXPECTED_W1_WINDOW_RESULT')
        ref = selected[0]['open']
        high, low = max(b['high'] for b in selected), min(b['low'] for b in selected)
        metrics = dict(reference_price=ref, observed_high=high, observed_low=low,
            market_high_return=high / ref - 1, market_low_return=low / ref - 1,
            market_close_return=next(b['close'] for b in selected if b['open_ms'] == end - BAR_MS) / ref - 1)
    return legacy, dict(window_end_exclusive_ms=end, expected_bars=horizon // BAR_MS,
        observed_bars=len(set(opens)), availability=availability, availability_reason=reason,
        market_metrics=metrics, directional_metrics=None, direction=None,
        directional_status='NOT_EVALUABLE_MISSING_ORIGINAL_DIRECTION',
        reference_kind='OPEN_AT_CUTOFF_NON_EXECUTABLE')


def build_report(pairs, bars, source_end, proof, *, generated_at_utc, code_sha):
    require(bool(re.fullmatch('[0-9a-f]{40}', code_sha)), 'CODE_SHA_REQUIRED')
    require(generated_at_utc.endswith('Z') and
            datetime.fromisoformat(generated_at_utc.replace('Z', '+00:00')).utcoffset().total_seconds() == 0,
            'UTC_GENERATION_TIME_REQUIRED')
    snapshots, effects, outcomes, rows = [], [], [], []
    seen = set()
    for e, r in pairs:
        key = tuple(e[k] for k in ('trial_id', 'opportunity_id', 'producer_event_id', 'envelope_sha256'))
        require(key not in seen, 'DUPLICATE_ORIGINAL_IDENTITY')
        seen.add(key)
        require(all(e[k] == r[k] for k in ('trial_id', 'opportunity_id', 'producer_event_id', 'envelope_sha256')),
                'ROW_RECEIPT_IDENTITY')
        snap = RetrospectiveSnapshot(trial_id=e['trial_id'], manifest_sha256=e['run_manifest_sha256'],
            opportunity_id=e['opportunity_id'], producer_event_id=e['producer_event_id'],
            envelope_sha256=e['envelope_sha256'], decision_cutoff_ms=e['decision_cutoff_ms'],
            decision_ms=e['decision_ms'], signal_state='UNKNOWN', reason_code='MISSING_ORIGINAL_F1_CAPTURE',
            direction=None, eligibility='NOT_ESTABLISHED', eligibility_evidence=None,
            context_digest=content_hash({k: e[k] for k in ('envelope_sha256', 'prefix_bar_checksums_sha256',
                'feature_policy_version', 'gap_inventory_sha256', 'correction_lineage_sha256')}))
        snapshots.append(snap)
        effects.append(F3EffectV1(*key, effect_disposition=r['effect_disposition'], reason_code=None,
            direction=None, receipt_id=r['receipt_sha256'], archive_version=PINS['outer.zip'],
            execution_class='MODELED_NON_EXECUTABLE' if r['effect_disposition'] == 'TRIGGERED' else 'NOT_APPLICABLE'))
        for horizon in HORIZONS:
            legacy, observation = window(snap, horizon, bars, source_end)
            outcomes.append(legacy)
            rows.append({**dict(zip(('trial_id', 'opportunity_id', 'producer_event_id', 'envelope_sha256'), key)),
                'horizon_hours': horizon // 3600000, 'decision_cutoff_ms': e['decision_cutoff_ms'],
                'decision_ms': e['decision_ms'], 'context_digest': snap.context_digest,
                'feature_policy_version': e['feature_policy_version'],
                'prefix_bar_checksums_sha256': e['prefix_bar_checksums_sha256'],
                'regime': None, 'regime_status': 'MISSING_ORIGINAL_REGIME',
                'f3_disposition': r['effect_disposition'], 'f3_reason': None,
                'f3_reason_status': 'MISSING_FROM_ORIGINAL_RECEIPT',
                'receipt_sha256': r['receipt_sha256'],
                'original_modeled_finance_refs': list(r['ordered_financial_event_ids']),
                'f1_status': 'MISSING_ORIGINAL_CAPTURE', 'g2_prospective_status': 'NOT_CONNECTED',
                'w1_outcome_id': legacy['outcome_id'], **observation})
    descriptive = describe_original_p0_f3_effects(effects, expected_total=len(pairs))
    validated = project(snapshots, outcomes, expected_total=len(pairs), f3_effects=effects)
    coverage = {str(h): dict(sorted(Counter(row['availability'] for row in rows
                  if row['horizon_hours'] == h).items())) for h in (4, 24, 72)}
    report = dict(schema_version=SCHEMA, scope='RETROSPECTIVE_NON_PIT_DESCRIPTIVE',
        policy_version=POLICY, generated_at_utc=generated_at_utc, code_sha=code_sha,
        dependency_factory_sha=FACTORY_PIN, source_proof=proof,
        decision_cutoff_convention='POSTHOC_ONLY_[cutoff,cutoff+horizon)_16_96_288_NATIVE_BARS',
        base_status='BASE_DESCRIPTIVE', shadow_status='NOT_EVALUABLE_NO_PREDECLARED_PAIRED_CANDIDATE',
        rows=rows, summary={'opportunities': len(pairs), 'horizon_slots': len(rows),
            'original_f3_counts': descriptive['f3_final_effects'], 'coverage_by_horizon': coverage,
            'coverage_by_status': {s: {str(h): dict(sorted(Counter(r['availability'] for r in rows
                if r['f3_disposition'] == s and r['horizon_hours'] == h).items()))
                for h in (4, 24, 72)} for s in descriptive['f3_final_effects']}},
        w1_projection_validation={'scheduled_total': validated['scheduled_total'],
                                  'outcome_count': validated['outcome_count'],
                                  'directional_outcomes_by_status': validated['outcomes_by_status']},
        threats=['SEVEN_DAY_SAMPLE_NOT_STRATEGY_VALIDATION', 'OVERLAPPING_HORIZONS_NOT_INDEPENDENT',
                 'ARCHIVE_END_CENSORING', 'SOURCE_ARRIVAL_PIT_NOT_AUTHENTICATED',
                 'NO_ORIGINAL_F1_DIRECTION_OR_REGIME', 'NO_ALPHA_OOS_OR_TRADING_CLAIM'])
    report['artifact_content_sha256'] = content_hash(report)
    return report


def write_outputs(directory, report, pairs, bars):
    """New output directory only; never rewrites an experiment or original input."""
    target = Path(directory)
    require(not target.exists(), 'OUTPUT_ALREADY_EXISTS')
    # Canonical local indices are private derivatives, never source replacements.
    indices = {
        'original_opportunity_index.jsonl': b''.join(encode(e) for e, _ in pairs),
        'original_bar_index.jsonl': b''.join(encode(b) for b in bars),
        'original_receipt_index.jsonl': b''.join(encode(r) for _, r in pairs),
    }
    files = {'result.json': encode(report), **indices}
    summary = report['summary']
    files['summary.md'] = ('# Original January 2024 — descriptive market outcomes\n\n'
        + json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2)
        + '\n\nNON_PIT; non-executable market reference; no original F1/direction/regime. '
        'BASE_DESCRIPTIVE; SHADOW NOT_EVALUABLE. Seven-day overlapping sample, not alpha.\n').encode()
    files['sha256-manifest.json'] = encode({n: hash_bytes(b) for n, b in sorted(files.items())})
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.p1a-', dir=target.parent) as temp:
        for name, raw in files.items():
            with open(Path(temp) / name, 'xb') as f:
                os.chmod(f.name, 0o600)
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
        # mkdir is exclusive even if a concurrent caller won the same destination.
        target.mkdir(mode=0o700)
        for name in files:
            os.rename(Path(temp) / name, target / name)
    return {name: hash_bytes(raw) for name, raw in files.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--generated-at-utc', required=True, help='Explicit UTC timestamp; reuse for deterministic reproduction')
    parser.add_argument('--code-sha', required=True)
    args = parser.parse_args()
    pairs, bars, end, proof = load_original(args.package)
    report = build_report(pairs, bars, end, proof, generated_at_utc=args.generated_at_utc, code_sha=args.code_sha)
    hashes = write_outputs(args.output, report, pairs, bars)
    print(json.dumps({'status': 'PRIVATE_ORIGINAL_REPORT_WRITTEN', 'summary': report['summary'],
                      'sha256': hashes}, sort_keys=True))


if __name__ == '__main__':
    main()
