"""Read-only retained archive verification. Never fetches, scores or fabricates data."""
from datetime import datetime
from decimal import Decimal
from io import BytesIO,StringIO
from pathlib import PurePosixPath,Path
import csv
import zipfile
from tools.strategy_service_offline.common import Frozen,decode,digest,read,raw_sha,require
from .adapters import Ports,source_call

ALLOWED=('BTCUSDT-15m-2024-02.zip','BTCUSDT-15m-2024-08.zip')


def inspect_retained_package(path,expected_sha,*,requested_archives=ALLOWED):
    require(tuple(requested_archives)==ALLOWED,'SEALED_OR_UNDECLARED_WINDOW_DENIED')
    if path is None or not Path(path).is_file():
        return Frozen.build({'schema':'aql.work.retained-original-inventory.v1','status':'SOURCE_NOT_AVAILABLE',
            'source_available':False,'scientific_run':'NOT_PERFORMED','authentic_e2e':'NOT_CONNECTED',
            'scientific_result':'INSUFFICIENT_EVIDENCE','archives':[]})
    raw=read(Path(path));require(raw_sha(raw)==expected_sha,'RETAINED_PACKAGE_SHA_MISMATCH')
    with zipfile.ZipFile(BytesIO(raw)) as outer:
        names=[i.filename for i in outer.infolist()]
        require(len(names)==len(set(names)) and len(names)<=64,'OUTER_ARCHIVE_IDENTITY')
        manifest=decode(outer.read('ATLAS_P2A_DEV/intake-manifest.json'))
        plan=decode(outer.read('ATLAS_P2A_DEV/frozen-plan.json'))
        require(manifest['phase']==plan['phase']=='DEVELOPMENT_ONLY','SEALED_HOLDOUT_ACCESS_DENIED')
        require(manifest['historical_known_at_ms'] is None and manifest['historical_publication_ms'] is None,
                'UNREVIEWED_CHRONOLOGY_CONTRACT')
        require(plan['holdout_access'] is False if 'holdout_access' in plan else
                plan['sealed_holdout']['status']=='SEALED_NO_FETCH_NO_EVALUATION','HOLDOUT_POLICY')
        windows={w['source']['name']:w for w in manifest['development_windows']}
        require(set(windows)==set(ALLOWED),'UNDECLARED_DEVELOPMENT_WINDOW')
        records=[]
        for name in requested_archives:
            w=windows[name];ref=w['source'];entry='ATLAS_P2A_DEV/raw/'+name
            rawzip=outer.read(entry);check=outer.read(entry+'.CHECKSUM')
            require(raw_sha(rawzip)==ref['archive_sha256'],'ORIGINAL_ARCHIVE_SHA_MISMATCH')
            require(check.decode().split()==[raw_sha(rawzip),name] and raw_sha(check)==ref['checksum_sha256'],
                    'RETAINED_VENDOR_CHECKSUM_MISMATCH')
            with zipfile.ZipFile(BytesIO(rawzip)) as archive:
                members=archive.infolist();require(len(members)==1,'ORIGINAL_MEMBER_CENSUS')
                member=members[0];p=PurePosixPath(member.filename)
                require(not p.is_absolute() and '..' not in p.parts and member.file_size<=8*1024*1024,
                        'UNSAFE_OR_OVERSIZE_ARCHIVE_MEMBER')
                body=archive.read(member)
                require(raw_sha(body)==ref['member_sha256'],'ORIGINAL_MEMBER_SHA_MISMATCH')
                rows=list(csv.reader(StringIO(body.decode('utf-8-sig'))))
                require(len(rows)==w['expected_bars']==w['observed_bars'],'ORIGINAL_BAR_DENOMINATOR')
                opened=[]
                for row in rows:
                    require(len(row)==12,'NATIVE_BINANCE_COLUMN_CONTRACT')
                    start,end=int(row[0]),int(row[6]);require(end==start+900000-1,'ORIGINAL_GRID_WIDTH')
                    values=[Decimal(row[i]) for i in (1,2,3,4,5)]
                    require(all(v.is_finite() for v in values),'ORIGINAL_NONFINITE_OHLCV')
                    o,h,l,c,v=values
                    require(l>0 and l<=o<=h and l<=c<=h and v>=0,'ORIGINAL_OHLCV_GEOMETRY')
                    if opened:require(start==opened[-1]+900000,'ORIGINAL_DUPLICATE_GAP_OR_ORDER')
                    opened.append(start)
                require(opened[0]==ref['first_open_ms'],'ORIGINAL_SCOPE_START')
                records.append({'name':name,'dataset_id':w['dataset_id'],'archive_sha256':raw_sha(rawzip),
                    'member_sha256':raw_sha(body),'checksum_file_sha256':raw_sha(check),
                    'archive_bytes':len(rawzip),'member_bytes':len(body),'bar_count':len(rows),
                    'column_count':12,'start_ms':opened[0],'end_exclusive_ms':opened[-1]+900000,
                    'grid':'COMPLETE_SINGLE_SYMBOL_ARCHIVED_NATIVE_GRID',
                    'source_uri':ref['url'],'claimed_capture_utc':w['acquisition_evidence']['reported_fetch_at_utc'],
                    'historical_known_at_ms':None,'historical_publication_ms':None,
                    'source_class':'RETAINED_ORIGINAL_UNVERIFIED_CHRONOLOGY',
                    'independent_provenance':'NOT_ATTESTED','correction_history':'UNKNOWN_NOT_ATTESTED',
                    'complete_market_universe':'NOT_ATTESTED','prices_published':False})
    return Frozen.build({'schema':'aql.work.retained-original-inventory.v1',
        'status':'RETAINED_ORIGINAL_BYTES_AVAILABLE_INTEGRITY_VERIFIED',
        'source_available':True,'package_sha256':raw_sha(raw),'package_bytes':len(raw),
        'intake_manifest_sha256':raw_sha(outer_manifest_bytes(raw)),
        'archives':records,'strategy_statistical_evaluation':'NOT_PERFORMED',
        'sealed_holdout':'UNOPENED','source_acquisition':'NONE',
        'lawful_access_context':'OWNER_AUTHORIZED_RETAINED_PERSONAL_NONPRODUCTION_RESEARCH',
        'scientific_run':'BLOCKED','scientific_result':'INSUFFICIENT_EVIDENCE','authentic_e2e':'NOT_CONNECTED',
        'blockers':['INDEPENDENT_PROVENANCE_NOT_ATTESTED','HISTORICAL_KNOWN_AT_NOT_RECORDED',
                    'CORE_NATIVE_BINANCE_ZIP_12_COLUMN_PORT_NOT_SUPPORTED',
                    'CORE_QUERY_METADATA_NOT_PRICE_GRID','STRATEGY_RULE_TRIGGER_EVALUATOR_NOT_CONNECTED',
                    'FACTORY_CURRENT_CONTRACT_PREFLIGHT_ONLY','UNIVERSE_HISTORY_NOT_ATTESTED']})


def outer_manifest_bytes(raw):
    with zipfile.ZipFile(BytesIO(raw)) as z:return z.read('ATLAS_P2A_DEV/intake-manifest.json')


def probe_original_core_format(deps,package_path,inventory):
    """Actually ask current Core to admit original retained ZIP bytes.

    Current pin schema rejects this native format BEFORE staging. No normalized
    derivative is substituted as an original source object, and no timestamp
    is invented to force an archive through the seven-column CSV interface.
    """
    data=Frozen.restore(inventory).data
    if not data['source_available']:return []
    raw=read(Path(package_path));require(raw_sha(raw)==data['package_sha256'],'PACKAGE_CHANGED_BEFORE_PROBE')
    results=[]
    with zipfile.ZipFile(BytesIO(raw)) as z:
        for record in data['archives']:
            name=record['name'];require(name in ALLOWED,'SEALED_OR_UNDECLARED_WINDOW_DENIED')
            original=z.read('ATLAS_P2A_DEV/raw/'+name)
            captured=int(datetime.fromisoformat(record['claimed_capture_utc'].replace('Z','+00:00')).timestamp()*1000)
            spec={'dataset_id':record['dataset_id'],'version':1,'symbol':'BTCUSDT','interval':'15m',
                  'exchange':'BINANCE','market':'SPOT','source_label':'retained-binance-vision',
                  'start_ms':record['start_ms'],'end_exclusive_ms':record['end_exclusive_ms'],
                  'as_of_ms':captured,'parent_source_sha256':None,'correction_reason':None,'test_only':False}
            pin={'schema':'aql.core.external-original-byte-pin.v1','source_kind':'BINANCE_KLINES_ZIP',
                 'original_object_id':name,'original_sha256':record['archive_sha256'],
                 'provenance_reference':'WORK_RETAINED_P2A_INTAKE','captured_at_ms':captured,
                 'claimed_available_at_ms':None,'expected_inventory_sha256':None,'vault_object_metadata':None,
                 'universe_manifest_sha256':None,'universe_member_count':None,'test_only':False}
            boundary=source_call(Ports(deps),{'source_hex':original.hex(),'pin':pin,'spec':spec,
                                           'cutoff_ms':record['end_exclusive_ms']})
            require(boundary.data['status']=='CORE_ADMISSION_REFUSED' and
                    boundary.data['core_error']=='UNSUPPORTED_ORIGINAL_SOURCE','UNREVIEWED_ORIGINAL_FORMAT_ADMISSION')
            results.append({'original_archive_sha256':record['archive_sha256'],'core_probe':boundary.receipt(),
                            'real_discoverer_or_factory_execution':'NOT_INVOKED'})
    return results
