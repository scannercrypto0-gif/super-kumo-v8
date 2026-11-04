"""Offline isolated invocation of pinned Core/Factory APIs, no alternate engine."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def deny(event,args):
    if event in {'socket.__new__','socket.connect','socket.getaddrinfo','urllib.Request','subprocess.Popen','os.system'}:
        raise RuntimeError('NETWORK_OR_EXECUTION_FORBIDDEN')


def call(name,body):
    if name=='core':
        from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
        from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
        from research_wp_r0.historical_library import HistoricalLibrary
        from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
        from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
        with TemporaryDirectory(prefix='aql247-custody-') as temp:
            library=HistoricalLibrary();stager=OfflineBridgeStager(temp)
            receipt=admit_original_bytes(bytes.fromhex(body['source_hex']),body['pin'],body['spec'],
                stager=stager,library=library,decision_cutoff_ms=body['cutoff_ms'],
                checksum_file_bytes=bytes.fromhex(body['checksum_hex']))
            request={'schema':REQUEST_SCHEMA,'dataset_id':body['spec']['dataset_id'],
                'version':body['spec']['version'],'start_ms':body['spec']['start_ms'],
                'end_exclusive_ms':body['spec']['end_exclusive_ms'],
                'decision_cutoff_ms':body['cutoff_ms'],'require_complete':False,'confirmed_only':False}
            query=query_price_custody(library,request,expected_source_sha256=receipt['source_bytes_sha256'],
                expected_manifest_integrity_sha256=receipt['manifest_integrity_sha256'])
            return {'admission':receipt,'prices':query}
    if name=='factory-core':
        from research_wp_r0.aql_factory_core_price_rule_port import from_core_original_price_query
        from research_wp_r0.aql_factory_authentic_research_admission import seal
        return from_core_original_price_query(body['admission'],body['prices'],seal(body['plan']))
    if name=='factory':
        from research_wp_r0.aql_factory_historical_rule_projection import evaluate_historical_rules,seal
        return evaluate_historical_rules(seal(body['packet']))
    raise ValueError('UNKNOWN_OWNER_PORT')


if __name__=='__main__':
    name,root=sys.argv[1:]
    sys.path.insert(0,str(Path(root).resolve()));sys.addaudithook(deny)
    raw=sys.stdin.buffer.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('INPUT_LIMIT')
    print(json.dumps(call(name,json.loads(raw)),sort_keys=True,separators=(',',':'),allow_nan=False))
