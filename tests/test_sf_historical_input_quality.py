"""Injected byte fixtures only: quality is never timing/execution authority."""
import csv
import hashlib
import io
import json
from zipfile import ZipFile

import pytest

from research_wp_r0.historical_input_quality import (
    HistoricalInputSpec, InputQualityReceipt, inspect_historical_input, replay_input_quality)


START=1704067200000


def rows():
    return [[START+i*60000,START+i*60000+59999,100,105,95,102,5] for i in range(4)]


def encode(records):
    stream=io.StringIO();csv.writer(stream).writerows(records)
    return stream.getvalue().encode()


def specification(raw, **changes):
    sha=hashlib.sha256(raw).hexdigest()
    spec=dict(schema="historical-input-quality-1",scope="DEV_INPUT_QUALITY_ONLY",provider="BINANCE_VISION",
        venue="BINANCE_SPOT",symbol="BTCUSDT",timeframe="1m",timezone="UTC",price_unit="USDT_PER_BTC",volume_unit="BTC",
        source_uri="fixture:injected-not-real-market-data",license_reference="SYNTHETIC_FIXTURE",
        container="CSV",csv_format="NORMALIZED_7",timestamp_unit="ms",member_name=None,
        version_sha256=sha,publisher_checksum_sha256=sha,start_ms=START,end_exclusive_ms=START+4*60000,
        review_cutoff_ms=START+86400000,provenance=dict(observed_at_ms=None,publisher_available_at_ms=None,
            first_known_at_ms=None,vintage_id=None,supersedes_version=None,correction_history_ref=None,
            independent_utc_ref=None,independent_anchor_ref=None,source_ack_ref=None,target_ack_ref=None,
            verified_source_timing=False,real_pit_accepted=False))
    spec.update(changes)
    return spec


def inspect(raw, **changes):
    s=HistoricalInputSpec(specification(raw,**changes))
    return inspect_historical_input(raw,s,expected_spec_digest=s.digest)


def test_full_grid_quality_not_pit_and_determinism():
    raw=encode(rows());r=inspect(raw);body=r.spec
    assert body['quality_status']=='SOURCE_QUALITY_ACCEPTED'
    assert body['counts']['rows']==body['counts']['observed_slots']==body['counts']['expected_slots']==4
    assert body['counts']['missing_slots']==0 and body['quality_reasons']==[]
    assert body['pit']['status']=='PIT_UNKNOWN'
    assert body['verified_source_timing'] is body['real_pit_accepted'] is body['performance_execution_allowed'] is False
    assert r.payload==inspect(raw).payload
    assert InputQualityReceipt.from_json(r.to_json(),expected_digest=r.digest).payload==r.payload


@pytest.mark.parametrize('index',[0,1,3])
def test_missing_leading_internal_trailing_slots(index):
    records=rows();records.pop(index);r=inspect(encode(records)).spec
    assert r['quality_status']=='SOURCE_QUALITY_BLOCKED'
    assert r['counts']['missing_slots']==1 and 'MISSING_GRID_SLOTS' in r['quality_reasons']


def test_duplicate_not_repaired_or_sorted():
    records=rows();records.insert(1,records[0]);r=inspect(encode(records)).spec
    assert r['counts']['duplicate_opens']==1 and 'DUPLICATE_OPEN' in r['quality_reasons']
    assert r['counts']['rows']==5


def test_unsorted_not_silently_sorted():
    records=rows();records[1],records[2]=records[2],records[1]
    r=inspect(encode(records)).spec
    assert r['counts']['out_of_order']==1 and r['quality_status']=='SOURCE_QUALITY_BLOCKED'


def test_off_grid_and_close_time():
    records=rows();records[1][0]+=1;records[2][1]-=1;r=inspect(encode(records)).spec
    assert r['counts']['off_grid']==1 and r['counts']['bad_close_time']==2


@pytest.mark.parametrize('column,value',[(2,0),(3,99),(4,103),(5,-1),(6,-1),(2,float('nan')),(3,float('inf')),(4,-float('inf'))])
def test_invalid_ohlcv_reuses_accepted_library(column,value):
    records=rows();records[0][column]=value;r=inspect(encode(records)).spec
    assert r['counts']['invalid_ohlcv']==1
    assert r['quality_status']=='SOURCE_QUALITY_BLOCKED' and 'INVALID_OHLCV' in r['quality_reasons']


def test_outside_window_and_empty_input():
    records=rows();records.append([START+240000,START+299999,100,105,95,102,5])
    assert inspect(encode(records)).spec['counts']['outside_window']==1
    assert inspect(b'').spec['quality_status']=='SOURCE_QUALITY_BLOCKED'


@pytest.mark.parametrize('bad',[b'bad\n',b'\xff',b'"unclosed\n',b'\n'])
def test_malformed_csv_or_utf8_fails_closed(bad):
    assert inspect(bad).spec['quality_status']=='SOURCE_QUALITY_BLOCKED'


def test_corrupt_version_checksum_and_no_implicit_authority():
    raw=encode(rows())
    assert inspect(raw,version_sha256='0'*64).spec['quality_reasons']==['VERSION_HASH_MISMATCH']
    r=inspect(raw,publisher_checksum_sha256='0'*64).spec
    assert r['checksum_status']=='MISMATCH' and r['quality_status']=='SOURCE_QUALITY_BLOCKED'
    r=inspect(raw,publisher_checksum_sha256=None).spec
    assert r['quality_status']=='SOURCE_QUALITY_ACCEPTED' and r['checksum_status']=='NOT_SUPPLIED_VERSION_FINGERPRINT_ONLY'


def test_pit_missing_reason_codes_and_local_observer_not_first_known():
    raw=encode(rows());s=specification(raw);s['provenance']['observed_at_ms']=START+300000
    r=inspect(raw,provenance=s['provenance']).spec
    for reason in ['HISTORICAL_FIRST_KNOWN_MISSING','PUBLISHER_AVAILABILITY_MISSING','VINTAGE_ID_MISSING',
                   'CORRECTION_HISTORY_MISSING','INDEPENDENT_UTC_MISSING','INDEPENDENT_ANCHOR_MISSING',
                   'SOURCE_ACK_MISSING','TARGET_ACK_MISSING']:
        assert reason in r['pit']['reasons']
    assert r['pit']['claimed_metadata']['first_known_at_ms'] is None
    assert r['real_pit_accepted'] is False


@pytest.mark.parametrize('flag',['verified_source_timing','real_pit_accepted'])
def test_forced_false_pit_claim_is_rejected(flag):
    raw=encode(rows());s=specification(raw);s['provenance'][flag]=True
    r=inspect(raw,provenance=s['provenance']).spec
    assert r['quality_status']=='SOURCE_QUALITY_ACCEPTED'
    assert r['pit']['status']=='PIT_BLOCKED' and 'CALLER_PIT_CLAIM_REJECTED' in r['pit']['reasons']
    assert r[flag] is False and r['performance_execution_allowed'] is False


def test_supplied_reference_strings_do_not_establish_authority():
    raw=encode(rows());s=specification(raw);m=s['provenance']
    for key in ['vintage_id','correction_history_ref','independent_utc_ref','independent_anchor_ref','source_ack_ref','target_ack_ref']:
        m[key]='caller-assertion'
    m['publisher_available_at_ms']=m['first_known_at_ms']=START+240000
    r=inspect(raw,provenance=m).spec
    assert r['pit']['status']=='PIT_UNKNOWN' and r['real_pit_accepted'] is False
    assert 'INDEPENDENT_UTC_UNVERIFIED' in r['pit']['reasons']


@pytest.mark.parametrize('value',[START,START+86400001])
def test_invalid_source_availability_chronology_blocked(value):
    raw=encode(rows());s=specification(raw);s['provenance']['publisher_available_at_ms']=value
    assert inspect(raw,provenance=s['provenance']).spec['pit']['status']=='PIT_BLOCKED'


@pytest.mark.parametrize('change',[dict(timezone='LOCAL'),dict(scope='OOS'),dict(timeframe='0m'),dict(start_ms=START+1),dict(review_cutoff_ms=START),dict(timestamp_unit='auto')])
def test_invalid_utc_scope_cutoff_or_units_rejected(change):
    with pytest.raises(ValueError):HistoricalInputSpec(specification(encode(rows()),**change))


def test_missing_fields_and_invalid_metadata_rejected():
    raw=encode(rows());s=specification(raw);del s['provider']
    with pytest.raises(ValueError):HistoricalInputSpec(s)
    s=specification(raw);del s['provenance']['correction_history_ref']
    with pytest.raises(ValueError):HistoricalInputSpec(s)
    s=specification(raw);s['source_uri']=chr(0xd800)
    with pytest.raises(ValueError):HistoricalInputSpec(s)
    s=specification(raw);s['provenance']['observed_at_ms']=True
    with pytest.raises(ValueError):HistoricalInputSpec(s)


def test_spec_receipt_pins_and_corrupt_replay():
    raw=encode(rows());s=HistoricalInputSpec(specification(raw));r=inspect_historical_input(raw,s,expected_spec_digest=s.digest)
    assert replay_input_quality(raw,s,r,expected_spec_digest=s.digest,expected_receipt_digest=r.digest).payload==r.payload
    with pytest.raises(ValueError):inspect_historical_input(raw,s,expected_spec_digest='0'*64)
    with pytest.raises(ValueError):replay_input_quality(raw+b'\n',s,r,expected_spec_digest=s.digest,expected_receipt_digest=r.digest)
    with pytest.raises(ValueError):InputQualityReceipt.from_json(r.to_json(),expected_digest='0'*64)
    wrapper=json.loads(r.to_json());wrapper['receipt']['real_pit_accepted']=True
    with pytest.raises(ValueError):InputQualityReceipt.from_json(json.dumps(wrapper),expected_digest=r.digest)
    with pytest.raises(ValueError):InputQualityReceipt.from_json(r.to_json().replace('"digest":','"digest":"extra","digest":',1),expected_digest=r.digest)


def test_defensive_immutability_and_no_time_generated():
    raw=encode(rows());s=HistoricalInputSpec(specification(raw));before=s.digest
    snapshot=s.spec;snapshot['provenance']['vintage_id']='edited'
    assert s.digest==before
    r=inspect_historical_input(raw,s,expected_spec_digest=s.digest)
    assert 'created_at_ms' not in r.to_json() and 'CONFIRMED' not in r.to_json()


def test_explicit_microsecond_boundaries_and_mixed_precision():
    records=rows()
    for row in records:row[0]*=1000;row[1]=row[1]*1000+999
    assert inspect(encode(records),timestamp_unit='us').spec['quality_status']=='SOURCE_QUALITY_ACCEPTED'
    records[0][1]-=1
    assert inspect(encode(records),timestamp_unit='us').spec['counts']['malformed_rows']==1
    assert inspect(encode(rows()),timestamp_unit='us').spec['quality_status']=='SOURCE_QUALITY_BLOCKED'


def archive(member='BTCUSDT-1m-fixture.csv'):
    records=[[r[0],*r[2:],r[1],0,1,0,0,0] for r in rows()]
    buf=io.BytesIO()
    with ZipFile(buf,'w') as z:z.writestr(member,encode(records))
    return buf.getvalue()


def test_shared_binance_archive_decoder_and_member_pin():
    raw=archive();changes=dict(container='BINANCE_SPOT_ZIP',csv_format='BINANCE_KLINES_12',member_name='BTCUSDT-1m-fixture.csv')
    r=inspect(raw,**changes).spec
    assert r['quality_status']=='SOURCE_QUALITY_ACCEPTED' and r['csv_sha256'] is not None
    changes['member_name']='BTCUSDT-1m-other.csv'
    assert inspect(raw,**changes).spec['quality_reasons']==['ARCHIVE_MEMBER_MISMATCH']
    changes['member_name']='BTCUSDT-1m-fixture.csv'
    assert inspect(b'not-zip',**changes).spec['quality_reasons']==['INVALID_ARCHIVE_ENVELOPE']


def test_zip_wrong_identity_or_multiple_members():
    raw=archive('ETHUSDT-1m-fixture.csv')
    r=inspect(raw,container='BINANCE_SPOT_ZIP',csv_format='BINANCE_KLINES_12',member_name='BTCUSDT-1m-fixture.csv').spec
    assert r['quality_status']=='SOURCE_QUALITY_BLOCKED'


def test_no_core_or_execution_dependency():
    import ast
    import pathlib
    import sys
    tree=ast.parse(pathlib.Path('research_wp_r0/historical_input_quality.py').read_text(encoding='utf-8'))
    imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
    for node in imports:
        if isinstance(node,ast.ImportFrom) and node.level:
            assert node.module in {'historical_library','retrospective_kline_intake','strategy_definition'}
        elif isinstance(node,ast.ImportFrom):
            assert node.module.split('.')[0] in sys.stdlib_module_names
        else:
            assert all(alias.name.split('.')[0] in sys.stdlib_module_names for alias in node.names)
