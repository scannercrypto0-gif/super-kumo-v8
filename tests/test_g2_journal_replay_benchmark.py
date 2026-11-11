"""Manual-only sampled append/replay diagnostic; not a production SLA."""
from dataclasses import asdict
import cProfile, hashlib, json, math, os, platform, sys, tempfile, time, tracemalloc, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from aql.observation.position_journal import DurablePositionJournal
from aql.observation.positions import PositionEvent

def seed(path,count):
    previous='0'*64
    with path.open('xb') as f:
        for i in range(count):
            event=PositionEvent('p1',f'event-{i}','opened' if i==0 else 'quote',i,i,'offline')
            row={'previous':previous,'event':asdict(event)}
            previous=hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            row['digest']=previous
            f.write((json.dumps(row,sort_keys=True,separators=(',',':'))+'\n').encode())
        f.flush();os.fsync(f.fileno())

def pct(samples):
    ordered=sorted(samples)
    return {f'p{p}_ms':round(ordered[max(0,math.ceil(p/100*len(ordered))-1)]*1000,4) for p in (50,95,99)}

def filesystem(path):
    if os.name=='nt':
        import ctypes
        name=ctypes.create_unicode_buffer(256)
        okay=ctypes.windll.kernel32.GetVolumeInformationW(Path(path).anchor,None,0,None,None,None,name,256)
        return name.value if okay else 'UNKNOWN'
    try:
        mounts=[(len(a[1]),a[2]) for line in Path('/proc/mounts').read_text().splitlines() if (a:=line.split()) and str(path).startswith(a[1].rstrip('/')+'/')]
        return max(mounts,default=(0,'UNKNOWN'))[1]
    except OSError:return 'UNKNOWN'

@unittest.skipUnless(os.environ.get('AQL_G2_BENCHMARK')=='1','manual opt-in benchmark')
class JournalReplayBenchmark(unittest.TestCase):
    def test_replay_cost_by_journal_size(self):
        sizes=[int(x) for x in os.environ.get('AQL_G2_SIZES','250,1000,5000,10000').split(',')]
        self.assertTrue(sizes and min(sizes)>0 and max(sizes)<=20000)
        results=[]
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for count in sizes:
                path=root/f'events-{count}.jsonl';seed(path,count)
                writer=DurablePositionJournal(path);samples=[]
                for i in range(count,count+20):
                    start=time.perf_counter()
                    self.assertEqual(writer.append(PositionEvent('p1',f'event-{i}','quote',i,i,'offline')),'inserted')
                    samples.append(time.perf_counter()-start)
                reopens=[]
                for _ in range(3):
                    start=time.perf_counter();copy=DurablePositionJournal(path);reopens.append((time.perf_counter()-start)*1000)
                    self.assertEqual(len(copy.ledger.events),count+20);self.assertEqual(copy._tail,writer._tail)
                profiler=cProfile.Profile();profiler.enable()
                writer.append(PositionEvent('p1','profile','quote',count+20,count+20,'offline'));profiler.disable()
                calls=[{'function':e.code.co_name,'calls':e.callcount,'total_s':e.totaltime} for e in profiler.getstats() if hasattr(e.code,'co_name') and e.code.co_name in ('append','_replay')]
                results.append({'seed_events':count,'bytes':path.stat().st_size,**pct(samples),'append_samples_ms':[x*1000 for x in samples],'reopen_samples_ms':reopens,'profile':calls})
            tracemalloc.start();copy=DurablePositionJournal(path)
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
            result={'os':platform.platform(),'python':platform.python_version(),'filesystem':filesystem(root),'storage':os.environ.get('AQL_G2_STORAGE_DESCRIPTION','physical medium UNKNOWN'),'results':results,'python_reopen_peak_bytes':peak,'journal_source_sha256':hashlib.sha256((Path(__file__).resolve().parents[1]/'src/aql/observation/position_journal.py').read_bytes()).hexdigest(),'method':'20 real tail appends after batched valid fixture (setup not durable-append throughput); p99=sample maximum, not population bound; Python allocation peak not RSS'}
            print('G2_REPLAY_BENCHMARK '+json.dumps(result,sort_keys=True))
            if os.environ.get('AQL_G2_BENCHMARK_OUTPUT'):Path(os.environ['AQL_G2_BENCHMARK_OUTPUT']).write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':unittest.main()
