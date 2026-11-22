"""Persistent local admission for opted-in continuous research; never grants PIT."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

POLICY = dict(schema='atlas.ws.continuity-policy.v1', connections_per_5m=2,
              min_retry_ms=30000, max_retry_ms=300000, max_failures_per_hour=4,
              idle_poll_ms=90000, orders=0, trading_authority='NONE')
PIN = hashlib.sha256(json.dumps(POLICY,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def database(path):
    path=Path(path)
    for node in (path,*path.parents):
        if node.is_symlink() or (node.exists() and getattr(node.lstat(),'st_file_attributes',0)&1024):
            raise ValueError('CONTINUITY_STATE_LINK')
    if path.exists() and (path.stat().st_nlink!=1 or path.stat().st_size>128*1024*1024):
        raise ValueError('CONTINUITY_STATE_LINK_OR_BOUND')
    db=sqlite3.connect(path,timeout=0)
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE TABLE IF NOT EXISTS policy(id INTEGER PRIMARY KEY,pin TEXT)')
        db.execute('INSERT OR IGNORE INTO policy VALUES(1,?)',(PIN,))
        if db.execute('SELECT pin FROM policy WHERE id=1').fetchone() != (PIN,):
            db.close();raise ValueError('CONTINUITY_POLICY_PIN')
        db.execute('CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,kind TEXT,at INTEGER,slot INTEGER,body TEXT)')
        if db.execute('SELECT count(*) FROM events').fetchone()[0]>=100000:
            db.close();raise ValueError('CONTINUITY_HISTORY_BOUND')
        db.commit()
        return db
    except BaseException:
        db.close()
        raise


def reserve(path, now, slot):
    """Charge before connect; crash loses admission, never refunds it."""
    with closing(database(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        last=db.execute('SELECT max(at) FROM events').fetchone()[0]
        if last is not None and now<last:raise ValueError('CONTINUITY_CLOCK_REGRESSION')
        recent=db.execute("SELECT at FROM events WHERE kind='CONNECT' AND at>? ORDER BY at",(now-300000,)).fetchall()
        wait=0 if len(recent)<2 else recent[-2][0]+300000-now+1
        if wait:return wait
        db.execute("INSERT INTO events(kind,at,slot,body) VALUES('CONNECT',?,?,NULL)",(now,slot))
        # Keep bounded admission history; outcomes/gaps remain in sealed segment receipts.
        db.execute("DELETE FROM events WHERE kind='CONNECT' AND at<?",(now-3600000,))
        return 0


def outcome(path, now, slot, *, failed, missing_start=None, missing_end=None):
    """Idempotent segment disposition. Failed segments never disappear on success."""
    with closing(database(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        body=json.dumps(dict(failed=failed,missing_start=missing_start,missing_end=missing_end),sort_keys=True)
        prior=db.execute("SELECT body FROM events WHERE kind='OUTCOME' AND slot=?",(slot,)).fetchall()
        if prior:
            if prior != [(body,)]:raise ValueError('CONTINUITY_OUTCOME_CONFLICT')
        else:db.execute("INSERT INTO events(kind,at,slot,body) VALUES('OUTCOME',?,?,?)",(now,slot,body))
        failures=[json.loads(b)['failed'] for (b,) in db.execute("SELECT body FROM events WHERE kind='OUTCOME' AND at>?",(now-3600000,))]
        count=sum(failures)
        return dict(policy_sha256=PIN, circuit_open=count>=4,
                    retry_after_ms=min(300000,30000*2**min(count,3)), failures_last_hour=count,
                    source_class='LIVE_CAPTURE',gap_status='OUTAGE_REQUIRES_COVERAGE_RECONCILIATION' if failed else 'NONE',
                    orders=0,trading_authority='NONE')


def authority(root, config_pin=None):
    """Opt-in must be installed by the guarded operator, never environment flags."""
    path=Path(root)/'continuous-research.authorized.json'
    if not path.exists():return None
    import re
    def need(ok,code):
        if not ok:raise ValueError(code)
    def read(p,maximum=65536):
        p=Path(p)
        for node in (p,*p.parents):
            if node.is_symlink() or (node.exists() and getattr(node.lstat(),'st_file_attributes',0)&1024):
                raise ValueError('CONTINUITY_AUTHORITY_LINK')
        need(p.is_file() and p.stat().st_nlink==1 and p.stat().st_size<=maximum,'CONTINUITY_AUTHORITY_BOUND')
        return p.read_bytes()
    def pairs(items):
        result={}
        for k,v in items:
            need(k not in result,'CONTINUITY_DUPLICATE_KEY');result[k]=v
        return result
    a=json.loads(read(path),object_pairs_hook=pairs)
    need(a.get('schema')=='atlas.ws.continuous-authority.v1' and a.get('policy_sha256')==PIN
         and type(a.get('orders')) is int and a.get('orders')==0 and a.get('trading_authority')=='NONE'
         and type(a.get('authorization_sha256')) is str and re.fullmatch('[0-9a-f]{64}',a['authorization_sha256']),
         'CONTINUITY_AUTHORITY_SCOPE')
    claimed=read(Path(root)/'operator-authorizations'/(a['authorization_sha256']+'.claimed'))
    need(hashlib.sha256(claimed).hexdigest()==a['authorization_sha256'],'CONTINUITY_OWNER_PERMIT_PIN')
    permit=json.loads(claimed,object_pairs_hook=pairs)
    need(permit.get('schema')=='atlas.ws.operator-authorization.v1' and permit.get('action')=='DEPLOY_ONE_RECOVERY'
         and permit.get('continuous_research') is True and permit.get('continuity_policy_sha256')==PIN
         and permit.get('allow_explicit_missing_intervals') is True and permit.get('max_connections')==2
         and permit.get('max_segments')==1 and type(permit.get('orders')) is int and permit['orders']==0
         and permit.get('trading_authority')=='NONE','CONTINUITY_OWNER_PERMIT_SCOPE')
    need(type(a.get('activated_ms')) is int and type(permit.get('issued_ms')) is int
         and type(permit.get('expires_ms')) is int and
         permit['issued_ms']<=a['activated_ms']<permit['expires_ms']<=permit['issued_ms']+1800000,
         'CONTINUITY_ACTIVATION_TIME')
    name=a.get('config_filename')
    need(type(name) is str and Path(name).name==name and name not in ('.','..'), 'CONTINUITY_CONFIG_PATH')
    actual=hashlib.sha256(read(Path(root)/name,8*1024*1024)).hexdigest()
    need(a.get('config_sha256')==actual and (config_pin is None or config_pin==actual),'CONTINUITY_CONFIG_PIN')
    return a


def next_action(root, config_pin, now, slot=None, failed=False):
    """Scheduler decision; no market calls or silent HOLD removal."""
    if authority(root,config_pin) is None:return dict(enabled=False,wait_until_ms=0,circuit_open=False)
    path=Path(root)/'continuous-admission.sqlite'
    if slot is not None:
        r=outcome(path,now,slot,failed=failed)
        return dict(enabled=True,wait_until_ms=now+r['retry_after_ms'] if failed else 0,**r)
    with closing(database(path)) as db:
        latest=db.execute("SELECT at,body FROM events WHERE kind='OUTCOME' ORDER BY id DESC LIMIT 1").fetchone()
        count=sum(json.loads(b)['failed'] for (b,) in db.execute("SELECT body FROM events WHERE kind='OUTCOME' AND at>?",(now-3600000,)))
    wait=latest[0]+min(300000,30000*2**min(count,3)) if latest and json.loads(latest[1])['failed'] else 0
    return dict(enabled=True,wait_until_ms=wait,circuit_open=count>=4)


def report(root,config_pin,now):
    from datetime import datetime
    from tools.atlas_live_research_cycle import read_service_receipt,saved_pilot_summary
    from aql.observation.contracts import digest
    root=Path(root);a=authority(root,config_pin)
    if a is None:raise ValueError('CONTINUITY_AUTHORITY_REQUIRED')
    start=a['activated_ms'];first=start-start%900000
    def bounded(path):
        for node in (path,*path.parents):
            if node.is_symlink() or (node.exists() and getattr(node.lstat(),'st_file_attributes',0)&1024):
                raise ValueError('CONTINUITY_REPORT_LINK')
        if path.is_symlink() or path.stat().st_nlink!=1 or path.stat().st_size>8*1024*1024:
            raise ValueError('CONTINUITY_REPORT_BOUND')
        return path.read_text(encoding='utf-8')
    def lines(path):
        raw=bounded(path)
        if raw and not raw.endswith('\n'):
            if not (root/'segment-execution.active.json').exists():raise ValueError('CONTINUITY_LOG_INCOMPLETE')
            raw=raw.rsplit('\n',1)[0] if '\n' in raw else ''
        return raw.splitlines()
    rows=[];previous=None;missing=[]
    candidates=list((root/'segments'/'receipts').glob('*.json'))
    if len(candidates)>100000:raise ValueError('CONTINUITY_RECEIPT_COUNT_BOUND')
    for p in sorted((p for p in candidates if p.stem.isdecimal() and int(p.stem)>=first),key=lambda p:int(p.stem)):
        bounded(p);r=read_service_receipt(p);row=r['observation']
        if not (row['slot']+900000<=row['committed_ms']<=now and row['slot']%900000==0):
            raise ValueError('CONTINUITY_RECEIPT_TIME')
        if previous:
            gap=(row['slot']-previous['observation']['slot'])//900000-1
            if r['previous_sha256']!=previous['sha256'] or r['missing_slots']!=gap or gap<0:
                raise ValueError('CONTINUITY_RECEIPT_CHAIN')
        expected=first if previous is None else previous['observation']['slot']+900000
        if row['slot']>expected:missing.append([expected,row['slot']])
        rows.append(r);previous=r
    last=rows[-1]['observation'] if rows else None
    expected=last['slot']+900000 if last else first
    observed_until=(now-300000)//900000*900000
    if observed_until>expected:missing.append([expected,observed_until])
    complete=[];events=[]
    log=root/'supervisor.jsonl'
    if log.exists():
        for line in lines(log):
            e=json.loads(line);at=int(datetime.fromisoformat(e['utc']).timestamp()*1000)
            if at>=start:
                if at>now+250:raise ValueError('CONTINUITY_EVENT_FUTURE')
                events.append(e)
                if e['status']=='COMPLETE':
                    state=root/'segments'/str(e['slot_ms']);plan=json.loads(bounded(state/'plan.json'))
                    summary=saved_pilot_summary(state,plan,digest(plan))
                    if len(summary['bars'])!=8:raise ValueError('CONTINUITY_INCOMPLETE_SEGMENT')
                    for bar in summary['bars']:
                        if not any(r['observation']['receipt_sha256']==bar['receipt_sha256'] for r in rows):
                            raise ValueError('CONTINUITY_SUMMARY_RECEIPT_MISSING')
                    complete.append(e['slot_ms'])
    complete=sorted(set(complete));faults=[];reconnections=[]
    dirs=[p for p in (root/'segments').iterdir() if p.is_dir() and p.name.isdecimal() and int(p.name)>=first]
    if len(dirs)>10000:raise ValueError('CONTINUITY_SEGMENT_COUNT_BOUND')
    for state in dirs:
        for name in ('health.previous.jsonl','health.jsonl'):
            path=state/name
            if path.exists():
                for line in lines(path):
                    e=json.loads(line)
                    if e['status']=='TRANSPORT_INTERRUPTED':faults.append(e)
                    if e['status']=='CONNECTING' and e.get('attempt')==2:reconnections.append(e)
    recovered=any(r['observation']['committed_ms']>e.get('utc_ms',now) for e in faults for r in rows)
    hold=root/'hold.json';reason=json.loads(bounded(hold)).get('reason') if hold.exists() else None
    awaiting=False
    ticket=root/'operator-resume.authorized.json'
    if reason in ('PILOT_STOP_TimeoutError','PILOT_STOP_ConnectionResetError') and not rows and ticket.exists():
        t=json.loads(bounded(ticket))
        awaiting=(t.get('schema')=='atlas.ws.operator-resume.v1' and t.get('config_sha256')==config_pin
            and t.get('authorization_sha256')==a['authorization_sha256']
            and type(t.get('issued_ms')) is int and type(t.get('expires_ms')) is int
            and t['issued_ms']<=now<t['expires_ms']<=t['issued_ms']+1800000
            and not (root/'operator-recovery.active.json').exists())
    fresh=bool(last and 0<=now-last['slot']-900000<=1200000)
    rollovers=sum(b==a+8*900000 for a,b in zip(complete,complete[1:]))
    ready=not reason and len(complete)>=3 and rollovers>=2 and len(rows)>=24 and fresh and recovered
    return dict(schema='atlas.ws.continuous-report.v1',status='CONTINUOUS_EVIDENCE_READY' if ready else
                ('AWAITING_EXISTING_SCHEDULE' if awaiting else ('HELD' if reason else 'OBSERVING_CONTINUOUS_ACCEPTANCE')),acceptance_ready=ready,initial_resume_pending=awaiting,
                as_of_ms=now,activated_ms=start,policy_sha256=PIN,config_sha256=config_pin,
                completed_segments=complete,confirmed_rollovers=rollovers,verified_receipts=len(rows),
                last_committed_ms=last['committed_ms'] if last else None,last_receipt_fresh=fresh,
                verified_receipt_sha256=[r['sha256'] for r in rows],missing_open_ranges=missing,
                real_fault_events=len(faults),within_segment_reconnections=len(reconnections),
                later_receipt_after_real_fault=recovered,hold_reason=reason,
                source_class='LIVE_CAPTURE',coverage='OBSERVED_RECEIPTS_ONLY',retention='SANITIZED_RECEIPTS_ONLY',
                full_original_payload_custody=False,real_pit_oos='BLOCKED',orders=0,trading_authority='NONE')


def main():
    import argparse,time
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('status','complete','failed','report'))
    p.add_argument('--root',required=True,type=Path);p.add_argument('--config-pin',required=True)
    p.add_argument('--slot',type=int);a=p.parse_args()
    if a.mode not in ('status','report') and (a.slot is None or a.slot%900000):raise ValueError('CONTINUITY_SLOT')
    if a.mode=='report':
        print(json.dumps(report(a.root,a.config_pin,time.time_ns()//1000000),sort_keys=True));return
    print(json.dumps(next_action(a.root,a.config_pin,time.time_ns()//1000000,
        slot=a.slot if a.mode!='status' else None,failed=a.mode=='failed'),sort_keys=True))


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError) as exc:
        import re
        code=str(exc) if isinstance(exc,ValueError) and re.fullmatch('[A-Z][A-Z0-9_]{1,119}',str(exc)) else 'CONTINUITY_PRIVATE_STATE_FAILURE'
        print(json.dumps(dict(status='CONTINUITY_BLOCKED',reason=code,orders=0,trading_authority='NONE')))
        raise SystemExit(2)
