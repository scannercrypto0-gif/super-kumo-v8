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


def causal_background(root, mode, stop_path, ready_path, output, stop_event=None):
    """One matched work implementation for thread/process; test-only IO quotas."""
    root = Path(root)
    path = root/'fixture.jsonl'
    is_cpu = mode in ('cpu', 'cpu_bounded')
    raw = path.read_bytes() if not is_cpu else None
    result = dict(pid=os.getpid(), thread=threading.get_ident(), completed=0,
                  logical_read_bytes=0, write_bytes=0, fsync_calls=0, errors=[],
                  work_unit_wall_samples_s=[])
    clock = time.thread_time if hasattr(time, 'thread_time') else time.process_time
    cpu_start = clock()
    process_cpu_start = time.process_time()
    started = time.monotonic()
    if is_cpu and stop_event is None:
        # Process control uses a pipe, not filesystem polling in CPU-only load.
        stop_event = threading.Event()
        def control():
            sys.stdin.buffer.read(1)
            stop_event.set()
        threading.Thread(target=control, daemon=True).start()
    def stopping():
        return stop_event.is_set() if is_cpu else Path(stop_path).exists()
    Path(ready_path).touch()
    try:
        while not stopping() and time.monotonic()-started < 58:
            before = time.monotonic()
            if mode == 'cpu_bounded':
                # B2 is a NEW 20%-nominal CPU profile, not saturated B1.
                # One ~5ms busy-wall burst each25ms wall period, <=2000
                # bursts. A Windows thread CPU clock can tick in ~15ms units;
                # use perf_counter to bound work, CPU clock for aggregate telemetry.
                # Scheduling/preemption can cause wall-period differences;
                # observed CPU/wall and completed bursts are retained below.
                if result['completed'] >= 2000:
                    stop_event.wait(.01)
                    continue
                burst_start = time.perf_counter()
                x = 1
                while time.perf_counter()-burst_start < .005 and not stopping():
                    for _ in range(256):
                        x = (x*1664525+1013904223)&0xffffffff
                result['work_unit_wall_samples_s'].append(time.monotonic()-before)
                result['completed'] += 1
                stop_event.wait(max(0,.025-(time.monotonic()-before)))
                continue
            elif mode == 'cpu':
                x = 1
                for _ in range(50000):
                    x = (x*1664525+1013904223)&0xffffffff
            else:
                # Same one-second offered work rate for C/D/E/F. G deliberately
                # halves this rate. No writes beyond 20 <=64MiB units.
                if result['completed'] >= 20:
                    time.sleep(.01)
                    continue
                if mode in ('replay', 'combined', 'throttled'):
                    journal = DurablePositionJournal(path)
                    if len(journal.ledger.events) != 10000:
                        raise AssertionError('fixture count changed')
                    result['logical_read_bytes'] += path.stat().st_size
                if mode in ('copy', 'combined', 'throttled'):
                    if result['write_bytes'] + len(raw) > 64*1024*1024:
                        raise AssertionError('background byte ceiling')
                    copy = root/'trial-copy'
                    with copy.open('wb') as handle:
                        if handle.write(raw) != len(raw):
                            raise OSError('short diagnostic write')
                        handle.flush(); os.fsync(handle.fileno())
                    result['write_bytes'] += len(raw)
                    result['fsync_calls'] += 1
                    if mode in ('combined', 'throttled'):
                        if hashlib.sha256(copy.read_bytes()).digest() != hashlib.sha256(raw).digest():
                            raise AssertionError('copy changed')
                        DurablePositionJournal(copy)
                        result['logical_read_bytes'] += 2*len(raw)
            result['work_unit_wall_samples_s'].append(time.monotonic()-before)
            result['completed'] += 1
            if not is_cpu:
                period = 2 if mode == 'throttled' else 1
                while (not stopping()
                       and time.monotonic()-before < period
                       and time.monotonic()-started < 58):
                    time.sleep(.005)
    except Exception as error:
        result['errors'].append(repr(error))
    finally:
        result['cpu_s'] = clock()-cpu_start
        result['whole_process_cpu_s'] = time.process_time()-process_cpu_start
        result['cpu_clock'] = 'thread_time' if hasattr(time,'thread_time') else 'process_time'
        result['wall_s'] = time.monotonic()-started
        result['offered_units'] = (2000 if mode == 'cpu_bounded' else None) if is_cpu else 20
        result['unfinished_offered_units'] = (2000-result['completed'] if mode == 'cpu_bounded' else None) if is_cpu else 20-result['completed']
        result['profile'] = ('B2:5ms busy-wall/25ms wall, nominal20%, <=40bursts/s, <=2000bursts'
                             if mode == 'cpu_bounded' else mode)
        result['observed_cpu_wall_fraction'] = result['cpu_s']/result['wall_s']
        result['active_work_wall_s'] = sum(result['work_unit_wall_samples_s'])
        result['observed_busy_wall_fraction'] = result['active_work_wall_s']/result['wall_s']
        result['completed_units_per_s'] = result['completed']/result['wall_s']
        Path(output).write_text(json.dumps(result)+'\n')


def causal_trial(root, mode, output):
    """230 real G1 commits plus an independent existing JournalConsumer."""
    from aql.lanes import JournalConsumer
    from aql.storage.operational_store import OperationalStore
    root = Path(root)
    token = Path(output).stem
    journal = DurableJournal(str(root/(token+'.sqlite')))
    store = OperationalStore(str(root/(token+'-store.sqlite')))
    stop_path, ready_path = root/(token+'.stop'), root/(token+'.ready')
    bg_output = root/(token+'-background.json')
    commit_done, ack, queue_age, ingest_start, samples = {}, {}, {}, {}, []
    observation_lock = threading.Lock()
    peak_pending = 0
    def backlog():
        return len(commit_done.keys()-ack.keys())
    upsert, mark = store.upsert, journal.mark_persisted
    def observed_upsert(bar):
        key = bar.stable_key()
        entered = time.perf_counter()
        with observation_lock:
            if key in commit_done:
                queue_age[key] = entered-commit_done[key]
        return upsert(bar)
    def observed_ack(key):
        mark(key)
        with observation_lock:
            ack[key] = time.perf_counter()
    store.upsert, journal.mark_persisted = observed_upsert, observed_ack
    consumer = JournalConsumer(journal, store, 'BTCUSDT', '1m')
    consumer.start()
    bg = None
    bg_stop = threading.Event()
    started, cpu_start = time.monotonic(), time.process_time()
    result = dict(mode=mode, status='INCOMPLETE', accepted=0, committed=0,
                  errors=[], pid=os.getpid(), sqlite_version=__import__('sqlite3').sqlite_version,
                  python=sys.version.split()[0], rejected='NOT APPLICABLE: direct durable admission')
    keys = []
    def commit_one(i):
        nonlocal peak_pending
        bar = MarketBar('BTCUSDT','1m',i*60000,(i+1)*60000-1,
                        100.,101.,99.,100.,1.,True,'synthetic-offline',(i+1)*60000)
        key = bar.stable_key()
        before = time.perf_counter(); ingest_start[key] = before
        result['accepted'] += 1
        if not journal.commit(bar):
            raise AssertionError('unexpected duplicate')
        end = time.perf_counter()
        with observation_lock:
            commit_done[key] = end
            peak_pending = max(peak_pending,backlog())
        result['committed'] += 1
        return key, end-before
    try:
        for i in range(30):
            commit_one(i)
        while len(ack) < 30:
            if time.monotonic()-started > 55:
                raise TimeoutError('warmup/ACK bound')
            time.sleep(.001)
        peak_pending = 0
        if mode != 'idle':
            bg_mode = {'cpu_thread':'cpu_bounded','cpu_process':'cpu_bounded','copy':'copy',
                       'replay':'replay','combined_thread':'combined',
                       'combined_process':'combined','throttled_process':'throttled'}[mode]
            args = (str(root), bg_mode, str(stop_path), str(ready_path), str(bg_output))
            if mode.endswith('process'):
                bg = subprocess.Popen([sys.executable,'-B',__file__,'--causal-background',*args],
                                      stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                bg = threading.Thread(target=causal_background, args=args,
                                      kwargs={'stop_event':bg_stop}, daemon=True)
                bg.start()
            while not ready_path.exists():
                if time.monotonic()-started > 55:
                    raise TimeoutError('background startup bound')
                time.sleep(.001)
        measured_start = time.perf_counter()
        for i in range(30,230):
            if time.monotonic()-started > 55:
                raise TimeoutError('foreground trial bound')
            key, elapsed = commit_one(i)
            keys.append(key); samples.append(elapsed)
        ingestion_end = time.perf_counter()
        while len(ack) < 230:
            if time.monotonic()-started > 55:
                raise TimeoutError('consumer ACK bound')
            time.sleep(.001)
        result['status'] = 'COMPLETE'
    except Exception as error:
        with observation_lock:
            result['at_guard_observed_pending'] = backlog()
            result['at_guard_observed_acked'] = len(ack)
        result['errors'].append(repr(error))
    finally:
        stop_path.touch()
        bg_stop.set()
        if isinstance(bg, subprocess.Popen):
            try:
                bg.stdin.write(b'x'); bg.stdin.flush(); bg.stdin.close()
            except (BrokenPipeError,OSError):
                pass
            try: bg.wait(timeout=2)
            except subprocess.TimeoutExpired:
                bg.kill(); bg.wait(timeout=1)
                result['errors'].append('background process killed: cleanup bound')
        elif bg is not None:
            bg.join(2)
            if bg.is_alive(): result['errors'].append('background thread still alive')
        consumer_result = consumer.finish(timeout=1)
        result['consumer'] = consumer_result
        result['foreground_process_cpu_s'] = time.process_time()-cpu_start
        result['wall_s'] = time.monotonic()-started
        result['samples_ms'] = [s*1000 for s in samples]
        def summarize(values):
            return {**pct(values), 'max_ms':max(values)*1000, 'count':len(values)} if values else 'NOT MEASURED'
        result['commit'] = summarize(samples)
        # ACK age starts at observed durable commit RETURN, not committed_at.
        ages = [ack[k]-commit_done[k] for k in keys if k in ack and ack[k]>=commit_done[k]]
        queues = [queue_age[k] for k in keys if k in queue_age and queue_age[k]>=0]
        result['ack_age'] = summarize(ages)
        result['queue_age'] = summarize(queues)
        result['ack_samples_ms'] = [s*1000 for s in ages]
        result['queue_samples_ms'] = [s*1000 for s in queues]
        result['queue_age_unobserved'] = len(keys)-len(queues)
        result['peak_observed_pending'] = peak_pending
        result.setdefault('at_guard_observed_pending','NOT APPLICABLE: no guard fired')
        result.setdefault('at_guard_observed_acked','NOT APPLICABLE: no guard fired')
        # Receipt-level backlog is sampled at commit/ACK RETURN boundaries,
        # not kernel fsync completion or an unsampled DB peak.
        result['backlog_provenance'] = 'commit RETURN minus ACK RETURN; measured phase peak'
        if keys and 'measured_start' in locals():
            result['commit_throughput_per_s'] = len(keys)/(ingestion_end-measured_start) if 'ingestion_end' in locals() else 'INCOMPLETE'
            result['ack_throughput_per_s'] = len(ages)/(max(ack[k] for k in keys if k in ack)-measured_start) if ages else 'NOT MEASURED'
        result['replayed'] = len(journal.replay())
        result['pending'] = journal.count_by_state().get('LOCAL_COMMITTED',0)
        result['background'] = json.loads(bg_output.read_text()) if bg_output.exists() else ('NONE' if mode=='idle' else 'NOT MEASURED')
        result['kernel_io_bytes'] = 'NOT MEASURED; logical work counters only'
        if result['errors'] or consumer_result['errors'] or consumer_result['worker_alive']:
            result['status'] = 'INCOMPLETE'
        Path(output).write_text(json.dumps(result)+'\n')


def causal_matrix():
    """Owner6409357112; opt-in only, capped globally and per child process."""
    import platform
    import sqlite3
    output = Path(os.environ.get('AQL_G2_MATRIX_OUTPUT','g2-causal-matrix.jsonl'))
    # First CI step timestamps job start, including checkout/Python setup.
    job_start = float(os.environ.get('AQL_G2_JOB_START',time.time()))
    deadline = time.monotonic()+max(0,1500-(time.time()-job_start))
    result = dict(schema='aql.g2-causal.v1', status='INCOMPLETE',
                  sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
                  tree=subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True).strip(),
                  platform=platform.platform(), python=sys.version, sqlite=sqlite3.sqlite_version,
                  trials=[], errors=[], setup_started_epoch=job_start)
    paths = ['src/aql/journal/durable_journal.py','src/aql/lanes.py',
             'src/aql/storage/operational_store.py','src/aql/observation/position_journal.py',
             'tests/test_g2_core_journal_contention.py']
    result['source_blobs'] = {p:subprocess.check_output(['git','rev-parse','HEAD:'+p],text=True).strip() for p in paths}
    with output.open('x',encoding='utf-8') as log, tempfile.TemporaryDirectory(prefix='g2-causal-',dir=Path.cwd()) as d:
        def record(value):
            log.write(json.dumps(value,sort_keys=True)+'\n'); log.flush();os.fsync(log.fileno())
        root = Path(d); path=root/'fixture.jsonl';seed(path,10000)
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        result['fixture_sha256'], result['fixture_bytes'] = expected,path.stat().st_size
        result['filesystem'] = filesystem(root)
        result['storage'] = 'physical medium UNKNOWN; workspace temporary directory'
        if os.name != 'nt':
            try:
                result['mount'] = subprocess.check_output(['findmnt','-T',str(root),'-o','SOURCE,FSTYPE,TARGET','-n'],text=True,timeout=2).strip()
            except Exception: result['mount']='NOT MEASURED'
        else: result['mount'] = str(root.anchor)
        result['settings'] = dict(seed_events=10000, warmup=30, measured=200,
                                  trials_per_load=3, trial_timeout_s=60,
                                  job_timeout_s=1500, background_write_cap=64*1024*1024,
                                  io_work_units=20, io_period_s=1, throttled_period_s=2,
                                  sqlite='WAL/FULL', acknowledged_by='existing JournalConsumer',
                                  cpu_profile='B2:5ms busy-wall/25ms wall, nominal20%, <=40bursts/s, <=2000bursts',
                                  B1_retained_run=40278088682,
                                  receipt_time='observed commit RETURN, not physical fsync timestamp')
        record(dict(kind='metadata',**{k:v for k,v in result.items() if k!='trials'}))
        modes=['cpu_thread','copy','replay','combined_thread','combined_process','cpu_process','throttled_process']
        try:
            for repeat in range(3):
                # Rotate order while retaining an immediate baseline for each load.
                order=modes[repeat:]+modes[:repeat]
                for mode in order:
                    for condition in ('idle',mode):
                        remaining=deadline-time.monotonic()
                        if remaining < 62:
                            raise TimeoutError('cannot fit next bounded trial in25min')
                        label=f'{repeat}-{mode}-{condition}'
                        child_output=root/(label+'.json')
                        try:
                            child=subprocess.run([sys.executable,'-B',__file__,'--causal-trial',d,condition,str(child_output)],
                                                 capture_output=True,text=True,timeout=60)
                        except subprocess.TimeoutExpired as error:
                            raise TimeoutError('trial hard60s bound: '+label) from error
                        if child.returncode or not child_output.exists():
                            raise RuntimeError('trial failed: '+label+' '+child.stderr[-1500:])
                        trial=json.loads(child_output.read_text())
                        trial.update(repeat=repeat, paired_load=mode, label=label)
                        result['trials'].append(trial);record(dict(kind='trial',**trial))
                        print('G2_CAUSAL_TRIAL '+json.dumps({k:trial[k] for k in ('label','status','commit','ack_age','queue_age','pending','peak_observed_pending','errors')}),flush=True)
                        if trial['status']!='COMPLETE' or trial['pending'] or trial['replayed']!=230:
                            raise RuntimeError('incomplete trial: '+label)
                        if isinstance(trial['background'],dict) and trial['background']['errors']:
                            raise RuntimeError('background errors: '+label)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
                raise AssertionError('fixture mutated')
            result['status']='COMPLETE'
        except Exception as error:
            result['errors'].append(repr(error))
        result['elapsed_s']=time.time()-job_start
        record(dict(kind='summary',status=result['status'],errors=result['errors'],
                    elapsed_s=result['elapsed_s'],trials=len(result['trials'])))
    print('G2_CAUSAL_SUMMARY '+json.dumps({k:result[k] for k in ('sha','status','elapsed_s','errors','filesystem','fixture_sha256')}),flush=True)
    return 0 if result['status']=='COMPLETE' else 1


if __name__=='__main__':
    if '--causal-background' in sys.argv:
        causal_background(*sys.argv[2:])
    elif '--causal-trial' in sys.argv:
        causal_trial(*sys.argv[2:])
    elif '--causal-matrix' in sys.argv:
        raise SystemExit(causal_matrix())
    else:
        unittest.main()
