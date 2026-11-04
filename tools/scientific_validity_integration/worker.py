import json
from pathlib import Path
import sys


def deny(event,args):
    if event in {'socket.__new__','socket.connect','socket.getaddrinfo','urllib.Request','subprocess.Popen','os.system'}:
        raise RuntimeError('NETWORK_OR_EXECUTION_FORBIDDEN')


if __name__=='__main__':
    name,root=sys.argv[1:];sys.path.insert(0,str(Path(root).resolve()));sys.addaudithook(deny)
    raw=sys.stdin.buffer.read(8*1024*1024+1)
    if len(raw)>8*1024*1024:raise ValueError('INPUT_LIMIT')
    b=json.loads(raw)
    if name=='core':
        from research_wp_r0.aql_core_chronology_universe_evidence_v1 import assess_chronology_universe
        out=assess_chronology_universe(b['admission'],b['prices'],
             chronology_evidence=b.get('chronology'),universe_evidence=b.get('universe'))
    elif name=='factory':
        from research_wp_r0.aql_factory_opportunity_comparison_gate import assess_opportunity_comparison
        out=assess_opportunity_comparison(b['plan'])
    else:raise ValueError('PORT')
    print(json.dumps(out,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False))
