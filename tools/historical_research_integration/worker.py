"""Isolated current Core/Factory APIs. No fabricated source or scientific attestation."""
import json
from pathlib import Path
import sys
import tempfile


def deny(event,args):
    if event in {'socket.__new__','socket.connect','socket.getaddrinfo','urllib.Request',
                 'subprocess.Popen','os.system'}:
        raise RuntimeError('NETWORK_OR_EXECUTION_FORBIDDEN')


def core(body):
    from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
    from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
    from research_wp_r0.historical_library import HistoricalLibrary
    results=[]
    library=HistoricalLibrary()
    with tempfile.TemporaryDirectory(prefix='aql239-test-custody-') as temp:
        stager=OfflineBridgeStager(temp)
        for obj in body['sources']:
            raw=None if obj['source_hex'] is None else bytes.fromhex(obj['source_hex'])
            try:
                result=admit_original_bytes(raw,obj['pin'],obj['spec'],stager=stager,library=library,
                                            decision_cutoff_ms=obj['cutoff_ms'])
                results.append({'status':'RETURNED','receipt':result})
            except ValueError as exc:
                # Existing component error codes only; no private source payload/path.
                results.append({'status':'REFUSED','code':str(exc)[:160],'error_type':type(exc).__name__})
    return {'schema':'aql.work.core-admission-call.v1','results':results}


def factory(body):
    from research_wp_r0.aql_factory_authentic_research_admission import assess_research_admission,seal
    packet=seal(body['packet'])
    receipt=assess_research_admission(packet)
    return {'schema':'aql.work.factory-admission-call.v1','packet':packet,'receipt':receipt}


if __name__=='__main__':
    name,root=sys.argv[1:]
    sys.path.insert(0,str(Path(root).resolve()))
    sys.addaudithook(deny)
    body=json.loads(sys.stdin.buffer.read(8*1024*1024+1))
    result=core(body) if name=='core' else factory(body) if name=='factory' else None
    if result is None:raise ValueError('UNKNOWN_PORT')
    print(json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False))
