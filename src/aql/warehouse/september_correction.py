"""One owner-authorized derived correction, never a general timestamp exception."""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import time
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from .diagnose import SEPT_KEY, SEPT_PIN, CHECKSUM_PIN, AUGUST_PIN, _august_snapshot
from .engine import HistoricalWarehouse, parse_archive
from .storage import canonical, need, seal

DECISION = 'https://github.com/scannercrypto0-gif/super-kumo-v8/pull/330#issuecomment-7058751093'
POLICY = 'AQL-2017-09-CLOSE-8160-v1'
CSV_PIN = 'd103edb024d391f67713e2e9377a9b2f3101ac02700b5e0637c20cea7fe7a149'
GAP = [1504713600000, 1504738800000]
START, END = 1504224000000, 1506816000000
NAME = 'BTCUSDT-1m-2017-09.zip'
AUGUST_SHARDS = {
 '2017-08-17.sqlite':'c1c7acd9dcf10478f183a122931213075026b897cd0d5b4c43812e40c1becaee',
 '2017-08-18.sqlite':'df1039822deb07cb42888a92012d9ae12c77e7d66b24bb56f66741c8323b1e1c',
 '2017-08-19.sqlite':'22de8e12d70e0fa26a0a208b4135600e2713c8c81bd29b4cd12c5ba03887c3d5',
 '2017-08-20.sqlite':'47086c09b054965c0ad5191d34f240bac7881c0de17315e2fb33ea78be4ee39c',
 '2017-08-21.sqlite':'8ca695895ea63b4713e7db89d32e3b0cd1146e31b88653a0c3bdc106e29859e4',
 '2017-08-22.sqlite':'975440f98d11c78710ee78e46a4b98ac7ee6ea415f746b984b71d68d96f4f9dc',
 '2017-08-23.sqlite':'8ec106deed33288d6cbc528a6891f2bb4805ef9b82c8088ad3d25c48fc939006',
 '2017-08-24.sqlite':'593212409ba71c7cb4dc7d454200ce24eb003b7b61a418a5944c8122473ab8f2',
 '2017-08-25.sqlite':'cb0363b36225e01fa92b4a734bfaeebeb37c4e8448eda1e1efce0e09eaae0265',
 '2017-08-26.sqlite':'c0a3aa04a4713aa9600679732291db02a4c0bcc97d7129e85b62c04d33f1e938',
 '2017-08-27.sqlite':'8dfad6e0a070fe64f2cf3cf3107cebc8550edca31d6af43a2a07d1de145504d8',
 '2017-08-28.sqlite':'7a9b0c9734982f4d50ce9eb30aaa0f015f9279327674a2802a1a18e03b4b1336',
 '2017-08-29.sqlite':'472bc603e78ec677a1f13641d1e4daf8e72738ca68f9097d34e5a0b04425e2ca',
 '2017-08-30.sqlite':'9a4e54b6b3272ede8c52f4c1da0cc8a08cae2dd44fd09ca6b5fcbcfafd3a5046',
 '2017-08-31.sqlite':'88f3a3c0cfa0767a03e162bb9f72279464b7a95cdaa8372d253119794d65c27e',
}


def derive(raw, checksum):
    """Pure deterministic transformation of three exact original-byte pins."""
    need(seal(raw) == SEPT_PIN and seal(checksum) == CHECKSUM_PIN, 'CORRECTION_ORIGINAL_PIN_MISMATCH')
    need(checksum.split() == [SEPT_PIN.encode(), NAME.encode()], 'CORRECTION_CHECKSUM_BINDING')
    with ZipFile(BytesIO(raw)) as z:
        entries = z.infolist()
        need(len(entries) == 1 and entries[0].filename == NAME[:-4]+'.csv', 'CORRECTION_MEMBER_IDENTITY')
        need(entries[0].file_size <= 32*1024*1024, 'CORRECTION_MEMBER_BOUND')
        original_csv = z.read(entries[0])
    need(seal(original_csv) == CSV_PIN, 'CORRECTION_CSV_PIN_MISMATCH')
    lines = original_csv.splitlines(keepends=True)
    need(len(lines) == 42780, 'CORRECTION_ROW_CENSUS')
    fields = lines[8159].split(b',')
    need(len(fields) == 12 and fields[0] == b'1504713540000'
         and fields[6] == b'1504713600000', 'CORRECTION_EXACT_ROW_FIELD_REQUIRED')
    fields[6] = b'1504713599999'
    lines[8159] = b','.join(fields)
    derived_csv = b''.join(lines)
    # No parsing/re-serialization of the original: all other bytes survive.
    output = BytesIO()
    info = ZipInfo(NAME[:-4]+'.csv', date_time=(1980,1,1,0,0,0))
    info.create_system, info.external_attr = 0, 0x20
    with ZipFile(output, 'w', compression=ZIP_STORED) as z:
        z.writestr(info, derived_csv, compress_type=ZIP_STORED)
    derived_zip = output.getvalue()
    local_checksum = (seal(derived_zip)+'  '+NAME).encode('ascii')
    rows, _ = parse_archive(derived_zip, local_checksum, SEPT_KEY, END)
    opens = [r['open_ms'] for r in rows]
    gaps = [[a+60000,b] for a,b in zip(opens,opens[1:]) if b != a+60000]
    need(len(rows) == 42780 and opens[0] == START and opens[-1] == END-60000
         and gaps == [GAP], 'CORRECTION_UNEXPECTED_CENSUS_OR_GAP')
    lineage = dict(schema='aql.warehouse.authorized-derivation.v1', policy=POLICY, version=1,
        authorizing_decision=DECISION, provisional_pending_final_g0=True,
        source_key=SEPT_KEY, source_class='RETROSPECTIVE_NON_PIT',
        original_zip_sha256=SEPT_PIN, original_checksum_sha256=CHECKSUM_PIN,
        original_csv_sha256=CSV_PIN, derived_zip_sha256=seal(derived_zip),
        derived_csv_sha256=seal(derived_csv), derived_local_checksum_sha256=seal(local_checksum),
        checksum_kind='LOCAL_DERIVATIVE_DIGEST_NOT_PUBLISHER_CHECKSUM',
        transform=dict(native_csv_line=8160, field_zero_indexed=6,
                       old='1504713600000', new='1504713599999', all_other_bytes_unchanged=True),
        source_rows=42780, missing_open_time_ranges=[GAP], missing_minutes=420,
        full_history_verified=False, trading_authority='NONE', pit_oos='NOT_ATTESTED')
    return derived_zip, local_checksum, lineage


def verify_derivative(warehouse, raw, checksum, key, lineage):
    need(key == SEPT_KEY and type(lineage) is dict, 'DERIVATION_SCOPE_REQUIRED')
    source = warehouse.path(f'raw/{SEPT_PIN}.zip')
    check = warehouse.path(f'raw/{CHECKSUM_PIN}.CHECKSUM')
    need(source.is_file() and check.is_file() and source.stat().st_size <= 64*1024*1024
         and check.stat().st_size <= 512, 'DERIVATION_ORIGINALS_REQUIRED')
    expected_raw, expected_checksum, expected_lineage = derive(source.read_bytes(),check.read_bytes())
    need(raw == expected_raw and checksum == expected_checksum and lineage == expected_lineage,
         'DERIVATION_BYTES_OR_LINEAGE_MISMATCH')
    return expected_lineage


def apply_correction(warehouse, *, observed_ms, task_inspection=None):
    need(warehouse.root.is_dir() and warehouse.path('catalog/warehouse-policy.json').is_file(),
         'EXISTING_WAREHOUSE_REQUIRED_NO_REBUILD')
    with warehouse.writer():
        before = _august_snapshot(warehouse)
        need(before['rows'] == 21360 and before['shard_sha256'] == AUGUST_SHARDS,
             'OWNER_AUGUST_BASELINE_MISMATCH')
        august = warehouse.path(f'raw/{AUGUST_PIN}.zip')
        need(august.is_file() and august.stat().st_size <= 64*1024*1024
             and seal(august.read_bytes()) == AUGUST_PIN, 'ACCEPTED_AUGUST_SOURCE_PIN_REQUIRED')
        original = warehouse.path(f'raw/{SEPT_PIN}.zip')
        checksum_path = warehouse.path(f'raw/{CHECKSUM_PIN}.CHECKSUM')
        need(original.is_file() and checksum_path.is_file()
             and original.stat().st_size <= 64*1024*1024 and checksum_path.stat().st_size <= 512,
             'RETAINED_SEPTEMBER_ORIGINALS_REQUIRED')
        raw, checksum = original.read_bytes(), checksum_path.read_bytes()
        derived, local_checksum, lineage = derive(raw,checksum)
        expected_rows, _ = parse_archive(derived,local_checksum,SEPT_KEY,observed_ms)
        expected = {r['open_ms']:r for r in expected_rows}
        for day in range(START,END,86400000):
            for row in warehouse._existing(day):
                needed = expected.get(row['open_ms'])
                need(needed is not None and row['constituent_sha256'] == needed['constituent_sha256']
                     and all(row[k] == needed[k] for k in ('o','h','l','c','v')),
                     'UNEXPECTED_EXISTING_SEPTEMBER_BAR')
        manifest = warehouse.write_once(f"catalog/{seal(canonical(lineage))}.derivation.json",canonical(lineage))
        result = warehouse.import_archive(derived,local_checksum,SEPT_KEY,observed_ms=observed_ms,
                                           derivation=lineage)
        after = _august_snapshot(warehouse)
        need(before == after, 'ACCEPTED_AUGUST_CHANGED')
        september = []
        for day in range(START,END,86400000):
            september.extend(warehouse._existing(day))
        opens = [r['open_ms'] for r in september]
        gaps = [[a+60000,b] for a,b in zip(opens,opens[1:]) if b != a+60000]
        need(len(september) == 42780 and gaps == [GAP], 'SEPTEMBER_ADMISSION_CENSUS_OR_GAP_FAILED')
        need(original.read_bytes() == raw and checksum_path.read_bytes() == checksum,
             'ORIGINAL_SOURCE_CHANGED')
        report = dict(schema='aql.warehouse.september-derived-admission.v1',
            status='SEPTEMBER_DERIVED_ADMISSION_PASS_WITH_EXPLICIT_GAP',
            policy=POLICY, authorizing_decision=DECISION, lineage=lineage,
            derivation_manifest_sha256=seal(canonical(lineage)), derivation_manifest=manifest.name,
            august_before=before, august_after=after, august_unchanged=True,
            original_bytes_unchanged=True, september_rows=42780,
            september_first_open_ms=opens[0], september_last_open_ms=opens[-1],
            september_gaps=gaps, missing_minutes=420, full_history_verified=False,
            import_result=result, warehouse=warehouse.report(), task_inspection=task_inspection,
            scheduler_changes=0, network_calls=0, source_class='RETROSPECTIVE_NON_PIT',
            trading_authority='NONE', pit_oos='NOT_ATTESTED')
        receipt = warehouse.document('receipts',report)
        report['receipt_file'] = receipt.name
        return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('E:/ATLAS/DataWarehouse'))
    a = p.parse_args()
    inspection = os.environ.get('ATLAS_WAREHOUSE_RECOVERY_TASK_INSPECTION')
    need(inspection is None or len(inspection.encode()) <= 65536,'TASK_INSPECTION_BOUND')
    report = apply_correction(HistoricalWarehouse(a.root),observed_ms=time.time_ns()//1000000,
                              task_inspection=json.loads(inspection) if inspection else None)
    print(json.dumps(report,sort_keys=True,indent=2))


if __name__ == '__main__':
    main()
