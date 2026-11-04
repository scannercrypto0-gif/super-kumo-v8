"""Explicit artificial native ZIP fixture. Never substituted for originals."""
from io import BytesIO
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
from tools.strategy_service_offline.common import raw_sha


def source_fixture():
    start=1706745600000;count=160;width=900000
    rows=[]
    for i in range(count):
        o=100+i*.005;c=o+.002
        rows.append(','.join(map(str,[start+i*width,o,c+.01,o-.01,c,10+i%7,
            start+(i+1)*width-1,1000,10,3,300,0])))
    raw=('\n'.join(rows)+'\n').encode();name='BTCUSDT-15m-2024-02.zip'
    sink=BytesIO();info=ZipInfo(name[:-4]+'.csv',(2024,2,1,0,0,0));info.compress_type=ZIP_DEFLATED
    with ZipFile(sink,'w') as z:z.writestr(info,raw)
    data=sink.getvalue();checksum=(raw_sha(data)+'  '+name+'\n').encode()
    pin={'schema':'aql.core.external-original-byte-pin.v1','source_kind':'BINANCE_KLINES_ZIP',
        'original_object_id':'TEST_ONLY_ARTIFICIAL_NATIVE_GRID','original_sha256':raw_sha(data),
        'provenance_reference':'TEST_ONLY_NOT_VENDOR_DATA','captured_at_ms':None,
        'claimed_available_at_ms':None,'expected_inventory_sha256':None,'vault_object_metadata':None,
        'universe_manifest_sha256':None,'universe_member_count':None,'test_only':True,
        'archive_name':name,'csv_member_name':name[:-4]+'.csv','csv_member_sha256':raw_sha(raw),
        'checksum_file_sha256':raw_sha(checksum)}
    spec={'dataset_id':'TEST_ONLY_NATIVE_247','version':1,'symbol':'BTCUSDT','interval':'15m',
        'exchange':'BINANCE','market':'SPOT','source_label':'TEST_ONLY_NATIVE_247','start_ms':start,
        'end_exclusive_ms':start+count*width,'as_of_ms':start+count*width,'parent_source_sha256':None,
        'correction_reason':None,'test_only':True}
    return {'source_hex':data.hex(),'checksum_hex':checksum.hex(),'pin':pin,'spec':spec,'cutoff_ms':start+count*width}
