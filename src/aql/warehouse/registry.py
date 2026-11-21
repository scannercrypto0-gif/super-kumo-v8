"""Derived registry over sealed warehouse evidence; never an admission authority.

Events and checkpoints are create-only. Source receipts remain authoritative.
An interrupted suffix can be resumed under the warehouse writer lock. Readers
never repair state. Hashes detect accidental/local changes, not a coordinated
rewrite of every artifact by an administrator (no external custody attestation).
"""
import json
import re

from .storage import canonical, need, seal

DATASET = 'BINANCE_VISION:SPOT:BTCUSDT:1m:RETROSPECTIVE_NON_PIT'
ZERO = '0' * 64


def sealed_document(path):
    raw = path.read_bytes()
    need(seal(raw) == path.stem, 'REGISTRY_EVIDENCE_DIGEST')
    return json.loads(raw)


def evidence(warehouse):
    """Verify original lineage and every physical row against committed sources."""
    from .engine import parse_archive
    from .september_correction import verify_derivative

    from collections import OrderedDict
    from datetime import datetime, timezone
    from .engine import DAY
    candidates, records, sources = {}, [], []
    expected_days = set()
    cache = OrderedDict()
    for path in sorted(warehouse.path('catalog').glob('*.json')):
        if not re.fullmatch(r'[0-9a-f]{64}', path.stem):
            continue
        record = json.loads(path.read_bytes())
        if record.get('schema') != 'aql.research.warehouse-source.v1':
            continue
        body = {k: v for k, v in record.items() if k != 'receipt_sha256'}
        need(record.get('receipt_sha256') == seal(canonical(body))
             and record.get('source_zip_sha256') == path.stem,
             'REGISTRY_SOURCE_IDENTITY')
        pin = path.stem
        raw = warehouse.path(f'raw/{pin}.zip').read_bytes()
        check = warehouse.path(f"raw/{record['checksum_sha256']}.CHECKSUM").read_bytes()
        need(seal(raw) == pin and seal(check) == record['checksum_sha256'],
             'REGISTRY_ORIGINAL_DIGEST')
        rows, meta = parse_archive(raw, check, record['key'], record['observed_ms'])
        need(all(record.get(k) == v for k, v in meta.items())
             and record['rows'] == len(rows)
             and record['source_zip_bytes'] == len(raw)
             and record['first_open_ms'] == rows[0]['open_ms']
             and record['last_open_ms'] == rows[-1]['open_ms']
             and record['source_class'] == 'RETROSPECTIVE_NON_PIT'
             and record['trading_authority'] == 'NONE', 'REGISTRY_SOURCE_FACTS')
        derivation = record.get('derivation')
        if derivation is not None:
            verify_derivative(warehouse, raw, check, record['key'], derivation)
            manifest = warehouse.path(f'catalog/{seal(canonical(derivation))}.derivation.json')
            need(manifest.is_file() and manifest.read_bytes() == canonical(derivation),
                 'REGISTRY_DERIVATION_MANIFEST')
            need(record.get('source_kind') == 'OWNER_AUTHORIZED_DERIVATIVE'
                 and record.get('publisher_integrity') == 'ORIGINAL_PINNED_DERIVATIVE_LOCAL_CHECKSUM'
                 and record.get('original_source_zip_sha256') == derivation['original_zip_sha256'],
                 'REGISTRY_DERIVATION_CLASSIFICATION')
        else:
            need(record.get('source_kind') is None
                 and record.get('publisher_integrity') == 'ZIP_CHECKSUM_MATCH'
                 and record.get('original_source_zip_sha256') is None,
                 'REGISTRY_MISSING_DERIVATION')
        facts = dict(source_receipt_sha256=record['receipt_sha256'],
                     source_zip_sha256=pin, key=record['key'], rows=len(rows),
                     first_open_ms=record['first_open_ms'], last_open_ms=record['last_open_ms'],
                     derivation=derivation)
        kind = 'APPROVED_DERIVED_CORRECTION' if derivation else 'SOURCE_COMMITTED'
        event = dict(event_type=kind, dataset_id=DATASET, source=pin,
                     policy_ref=derivation.get('policy') if derivation else None,
                     observed_ms=record['observed_ms'], before=None, after=facts)
        candidates[seal(canonical(event))] = event
        sources.append(facts)
        records.append(record)
        expected_days.update(row['open_ms'] // DAY * DAY for row in rows)
        cache[pin] = rows
        if len(cache) > 2:
            cache.popitem(last=False)

    physical_days = {int(datetime.strptime(p.stem, '%Y-%m-%d').replace(
        tzinfo=timezone.utc).timestamp()*1000)
        for p in warehouse.path('bars').glob('????-??-??.sqlite')}
    need(physical_days == expected_days, 'REGISTRY_UNCOMMITTED_OR_MISSING_ROWS')
    # At most two native archives and one daily shard in memory, independent of
    # warehouse history length. Overlapping sources must agree on exact rows.
    for day in sorted(expected_days):
        expected = {}
        for record in records:
            if record['last_open_ms'] < day or record['first_open_ms'] >= day + DAY:
                continue
            pin = record['source_zip_sha256']
            if pin not in cache:
                raw = warehouse.path(f'raw/{pin}.zip').read_bytes()
                check = warehouse.path(f"raw/{record['checksum_sha256']}.CHECKSUM").read_bytes()
                cache[pin] = parse_archive(raw, check, record['key'], record['observed_ms'])[0]
                if len(cache) > 2:
                    cache.popitem(last=False)
            cache.move_to_end(pin)
            for row in cache[pin]:
                t = row['open_ms']
                if not day <= t < day + DAY:
                    continue
                old = expected.get(t)
                need(old is None or signature(old) == signature(row), 'REGISTRY_SOURCE_CONFLICT')
                if old is None or row['available_at_ms'] < old['available_at_ms']:
                    expected[t] = row
        actual = {r['open_ms']: r for r in warehouse._existing(day)}
        need(actual.keys() == expected.keys(), 'REGISTRY_UNCOMMITTED_OR_MISSING_ROWS')
        for t, row in actual.items():
            need(signature(row) == signature(expected[t]), 'REGISTRY_ROW_LINEAGE')
            # Interrupted imports can retain the earlier observation of identical
            # bytes; they cannot make a source available later than its receipt.
            need(row['available_at_ms'] <= expected[t]['available_at_ms'], 'REGISTRY_ROW_OBSERVATION')

    for section in ('quarantine', 'receipts'):
        for path in sorted(warehouse.path(section).glob('*.json')):
            record = sealed_document(path)
            if section == 'quarantine':
                kind = 'SOURCE_REJECTED_QUARANTINED'
            elif record.get('registry_action') == 'REPAIR_RECOVERY':
                kind = 'REPAIR_RECOVERY'
            else:
                continue
            event = dict(event_type=kind, dataset_id=DATASET,
                         source=record.get('source_sha256', record.get('key')),
                         policy_ref=record.get('policy_ref'), observed_ms=record.get('observed_ms'),
                         before=record.get('before'), after=record, evidence_sha256=path.stem)
            candidates[seal(canonical(event))] = event
    from .source import MAX_ZIP
    for path in sorted(warehouse.path('quarantine').glob('*.zip')):
        match = re.fullmatch(r'([0-9a-f]{64})-([0-9a-f]{64})\.zip', path.name)
        need(match is not None and path.stat().st_size <= MAX_ZIP,
             'REGISTRY_QUARANTINE_IDENTITY')
        need(seal(path.read_bytes()) == match[2], 'REGISTRY_QUARANTINE_DIGEST')
        event = dict(event_type='CORRUPT_SOURCE_QUARANTINED', dataset_id=DATASET,
                     source=match[1], policy_ref='PUBLISHER_CHECKSUM_MISMATCH', observed_ms=None,
                     before=dict(expected_zip_sha256=match[1]),
                     after=dict(actual_zip_sha256=match[2], bytes=path.stat().st_size,
                                artifact=path.name))
        candidates[seal(canonical(event))] = event
    return candidates, sources


def signature(row):
    return [row[k] for k in ('o', 'h', 'l', 'c', 'v', 'constituent_sha256')]


def history(warehouse, *, recover=False):
    events, previous, identities = [], ZERO, set()
    directory = warehouse.path('catalog/registry')
    files = sorted(directory.glob('event-*.json'))
    checkpoints = sorted(directory.glob('checkpoint-*.json'))
    need(len(checkpoints) <= len(files), 'REGISTRY_MISSING_EVENT')
    for seq, path in enumerate(files, 1):
        need(path.name == f'event-{seq:012d}.json', 'REGISTRY_SEQUENCE')
        event = json.loads(path.read_bytes())
        digest = event.get('event_sha256')
        body = {k: v for k, v in event.items() if k != 'event_sha256'}
        identity = event.get('event_id')
        payload = {k: v for k, v in body.items() if k not in ('sequence', 'previous_sha256', 'event_id')}
        need(digest == seal(canonical(body)) and event.get('sequence') == seq
             and event.get('previous_sha256') == previous
             and identity == seal(canonical(payload)) and identity not in identities,
             'REGISTRY_CHAIN_OR_IDENTITY')
        checkpoint = dict(sequence=seq, event_sha256=digest)
        relative = f'catalog/registry/checkpoint-{seq:012d}.json'
        target = warehouse.path(relative)
        if not target.exists():
            need(recover and seq == len(files), 'REGISTRY_CHECKPOINT_MISSING')
            warehouse.write_once(relative, canonical(checkpoint))
        need(target.read_bytes() == canonical(checkpoint), 'REGISTRY_CHECKPOINT_DIGEST')
        events.append(event)
        identities.add(identity)
        previous = digest
    need({p.name for p in checkpoints}.issubset(
        {f'checkpoint-{i:012d}.json' for i in range(1, len(files)+1)}), 'REGISTRY_CHECKPOINT_SEQUENCE')
    return events


def snapshot(warehouse, *, synchronize=False, physical_report=None):
    need(not synchronize or warehouse.locked, 'WRITER_LOCK_REQUIRED')
    events = history(warehouse, recover=synchronize)
    candidates, sources = evidence(warehouse)
    present = {e['event_id'] for e in events}
    need(present <= candidates.keys(), 'REGISTRY_MISSING_LINEAGE')
    missing = sorted(candidates.keys() - present)
    if synchronize:
        warehouse.path('catalog/registry').mkdir(exist_ok=True)
        for identity in missing:
            body = dict(**candidates[identity], event_id=identity, sequence=len(events)+1,
                        previous_sha256=events[-1]['event_sha256'] if events else ZERO)
            event = dict(**body, event_sha256=seal(canonical(body)))
            seq = event['sequence']
            warehouse.write_once(f'catalog/registry/event-{seq:012d}.json', canonical(event))
            warehouse.write_once(f'catalog/registry/checkpoint-{seq:012d}.json',
                                 canonical(dict(sequence=seq, event_sha256=event['event_sha256'])))
            events.append(event)
    else:
        need(not missing, 'REGISTRY_COMMITTED_EVIDENCE_PENDING_SYNC')
    report = physical_report if physical_report is not None else warehouse._physical_report()
    first, last = report['stored_first_open_ms'], report['stored_last_open_ms']
    covered = []
    if first is not None:
        cursor = first
        for a, b in report['internal_gaps']:
            covered.append([cursor, a])
            cursor = b
        covered.append([cursor, last + 60000])
    # Registry/operational receipt bytes would recursively change their own digest.
    physical = {section: sum(p.stat().st_size for p in warehouse.path(section).glob('*')
                             if p.is_file() and not p.name.endswith('.pending'))
                for section in ('raw', 'bars', 'quarantine')}
    body = dict(schema='aql.warehouse.registry-snapshot.v1', version=1, dataset_id=DATASET,
                event_watermark=len(events), event_head_sha256=events[-1]['event_sha256'] if events else ZERO,
                as_of_ms=max((e.get('observed_ms') or 0 for e in events), default=0),
                physical_interval='1m', physical_rows=report['one_minute_rows'],
                first_open_ms=first, last_open_ms=last, covered_intervals=covered,
                internal_gaps=report['internal_gaps'],
                archive_unavailable_boundaries=report['archive_boundary_missing_ranges'],
                conflicts=report['conflicting_candidates'], sources=sources,
                physical_data_bytes=physical,
                storage_accounting='DATA_FILES_ONLY; total managed usage available in report.stored_bytes',
                projected_intervals=report['available_complete_projections'],
                projections_physically_stored=False, source_class='RETROSPECTIVE_NON_PIT',
                forward_status='FORWARD_UNQUALIFIED', scientific_status='REAL_PIT_OOS_BLOCKED',
                research_eligibility='RETROSPECTIVE_COVERED_WINDOWS_ONLY', trading_authority='NONE')
    result = dict(**body, snapshot_sha256=seal(canonical(body)))
    relative = f"catalog/registry/snapshot-{result['snapshot_sha256']}.json"
    if synchronize:
        warehouse.write_once(relative, canonical(result))
    elif events:
        need(warehouse.path(relative).exists() and warehouse.path(relative).read_bytes() == canonical(result),
             'REGISTRY_SNAPSHOT_PENDING_OR_CORRUPT')
    return result


def adopt_existing(warehouse):
    """Registry-only host handoff after the already completed September admission."""
    from .september_correction import AUGUST_SHARDS, START, END, GAP, _august_snapshot
    need(warehouse.path('catalog/warehouse-policy.json').is_file(),
         'EXISTING_WAREHOUSE_REQUIRED_NO_REBUILD')
    with warehouse.writer():
        before = _august_snapshot(warehouse)
        need(before['rows'] == 21360 and before['shard_sha256'] == AUGUST_SHARDS,
             'OWNER_AUGUST_BASELINE_MISMATCH')
        opens = [r['open_ms'] for day in range(START, END, 86400000)
                 for r in warehouse._existing(day)]
        gaps = [[a+60000, b] for a, b in zip(opens, opens[1:]) if b != a+60000]
        need(len(opens) == 42780 and opens[0] == START and opens[-1] == END-60000
             and gaps == [GAP], 'OWNER_SEPTEMBER_ADMISSION_REQUIRED')
        warehouse.rebuild_registry()
        report = warehouse.report()
        after = _august_snapshot(warehouse)
        need(before == after, 'ACCEPTED_AUGUST_CHANGED')
        result = dict(schema='aql.warehouse.registry-adoption.v1',
                      status='REGISTRY_ADOPTED_EXISTING_COMMITTED_DATA',
                      warehouse=report, august_before=before, august_after=after,
                      september_rows=len(opens), september_gaps=gaps,
                      source_network_calls=0, scheduler_changes=0, admission_operations=0,
                      trading_authority='NONE', scientific_status='REAL_PIT_OOS_BLOCKED')
        receipt = warehouse.document('receipts', result)
        return dict(result, receipt_file=receipt.name)


def main():
    import argparse
    from pathlib import Path
    from .engine import HistoricalWarehouse
    parser = argparse.ArgumentParser(description='Adopt committed warehouse evidence; no source import/network')
    parser.add_argument('--root', type=Path, default=Path('E:/ATLAS/DataWarehouse'))
    args = parser.parse_args()
    print(json.dumps(adopt_existing(HistoricalWarehouse(args.root)), sort_keys=True, indent=2))


if __name__ == '__main__':
    main()
