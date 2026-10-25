"""Offline G1 commit probe during G2 work; not deployed pipeline acceptance."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.observation.position_journal import DurablePositionJournal, JournalIntegrityError, _exclusive_writer
from aql.observation.positions import PositionEvent
from test_g2_journal_replay_benchmark import seed, pct, filesystem


def commit_samples(path, count=30):
    journal = DurableJournal(str(path)); samples=[]
    for i in range(count):
        bar=MarketBar('BTCUSDT','1m',i*60000,(i+1)*60000-1,
                      100.,101.,99.,100.,1.,True,'synthetic-offline',(i+1)*60000)
        start=time.perf_counter();assert journal.commit(bar);samples.append(time.perf_counter()-start)
    assert len(journal.replay())==count
    return {**pct(samples),'max_ms':max(samples)*1000,'samples_ms':[v*1000 for v in samples]}


class CoreJournalIsolationTests(unittest.TestCase):
    def test_blocked_position_snapshot_does_not_hold_g1_commit_path(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'positions.jsonl'
            DurablePositionJournal(path).append(PositionEvent('p','o','opened',0,0,'offline'))
            entered, release=threading.Event(),threading.Event();errors=[]
            def backup():
                try:
                    with _exclusive_writer(path):
                        entered.set();assert release.wait(10)
                except Exception as error:errors.append(str(error))
            thread=threading.Thread(target=backup);thread.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(JournalIntegrityError):
                    DurablePositionJournal(path).append(PositionEvent('p','q','quote',1,1,'offline'))
                probe=commit_samples(root/'g1.sqlite',3)
                self.assertEqual(len(probe['samples_ms']),3)
                self.assertTrue(thread.is_alive())
            finally:release.set();thread.join(10)
            self.assertFalse(thread.is_alive());self.assertFalse(errors)


@unittest.skipUnless(os.environ.get('AQL_G2_CONTENTION')=='1','manual opt-in load diagnostic')
class CoreJournalContentionDiagnostic(unittest.TestCase):
    def test_cpu_only_thread_vs_process_diagnostic(self):
        """Opt-in causal probe: no G2 file IO; process and thread are distinct."""
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            # Pure Python integer work stresses interpreter scheduling without
            # any background disk operations. No assertion about which is faster.
            work = ("x=1\n"
                    "while True:\n"
                    "    x=(x*1664525+1013904223)&0xffffffff\n")
            stop = threading.Event()
            def cpu_thread():
                x = 1
                while not stop.is_set():
                    for _ in range(10000):
                        x = (x * 1664525 + 1013904223) & 0xffffffff

            baseline = commit_samples(root / 'cpu-idle.sqlite')
            thread = threading.Thread(target=cpu_thread, daemon=True)
            thread.start()
            try:
                time.sleep(0.1)
                thread_load = commit_samples(root / 'cpu-thread.sqlite')
            finally:
                stop.set()
                thread.join(5)
            self.assertFalse(thread.is_alive())

            # Independent interpreter, not a thread. Separate DB per trial;
            # all foreground commits remain SQLite FULL synchronous.
            child = subprocess.Popen([sys.executable, '-B', '-c', work],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.PIPE)
            try:
                time.sleep(0.2)
                self.assertIsNone(child.poll(), 'CPU worker exited unexpectedly')
                process_load = commit_samples(root / 'cpu-process.sqlite')
            finally:
                child.terminate()
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate(timeout=5)

            result = {
                'baseline': baseline, 'cpu_thread': thread_load,
                'cpu_process': process_load, 'filesystem': filesystem(root),
                'os': sys.platform, 'python': sys.version.split()[0],
                'scope': 'CPU-only scheduling probe; no G2 disk work; '
                         'sequential trials, no randomization, no SLO inference',
            }
            print('G2_CPU_CAUSAL_PROBE ' + json.dumps(result, sort_keys=True))
            if os.environ.get('AQL_G2_CONTENTION_OUTPUT'):
                output = Path(os.environ['AQL_G2_CONTENTION_OUTPUT'])
                output.with_name(output.stem + '-cpu.json').write_text(
                    json.dumps(result, indent=2) + '\n')

    def test_shared_disk_and_python_replay_load(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'positions.jsonl';seed(path,10000)
            baseline=commit_samples(root/'baseline.sqlite')
            ready,stop=threading.Event(),threading.Event();errors=[];passes=[]
            def background():
                try:
                    for _ in range(20):
                        if stop.is_set():break
                        with _exclusive_writer(path):
                            replay=DurablePositionJournal(path)
                            raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
                            # Disposable overwrite is benchmark-only, not a retention policy.
                            copy=root/'background-copy'
                            with copy.open('wb') as handle:
                                handle.write(raw);handle.flush();os.fsync(handle.fileno())
                            assert hashlib.sha256(copy.read_bytes()).hexdigest()==digest
                            assert DurablePositionJournal(copy)._tail==replay._tail
                        passes.append(len(raw));ready.set()
                except Exception as error:errors.append(repr(error));ready.set()
            thread=threading.Thread(target=background);thread.start()
            self.assertTrue(ready.wait(15));start=time.monotonic()
            try:loaded=commit_samples(root/'loaded.sqlite')
            finally:stop.set();thread.join(20)
            self.assertFalse(thread.is_alive());self.assertFalse(errors);self.assertTrue(passes)
            result={'baseline':baseline,'under_background_load':loaded,'completed_background_passes':len(passes),
                    'background_bytes':sum(passes),'foreground_elapsed_s':time.monotonic()-start,
                    'filesystem':filesystem(root),'os':sys.platform,'python':sys.version.split()[0],
                    'scope':'same-interpreter threads and shared temporary disk, actual G1 commit API; no end-to-end Core Run or SLA'}
            print('G2_CORE_CONTENTION '+json.dumps(result,sort_keys=True))
            if os.environ.get('AQL_G2_CONTENTION_OUTPUT'):
                Path(os.environ['AQL_G2_CONTENTION_OUTPUT']).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':unittest.main()
