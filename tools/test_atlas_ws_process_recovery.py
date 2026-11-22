"""Abrupt independent-process recovery through production frame/journal code."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

CHILD=r'''
import json,os,socket,sys
from pathlib import Path
from unittest.mock import patch
from tools.atlas_live_research_cycle import FIXTURE,STEP,make_plan,recover,consume,DurableJournal,OperationalStore,ProspectiveObserver
from tools.atlas_single_receipt import persist_frame,load_frame
from aql.observation.contracts import digest
root=Path(sys.argv[1]);mode=sys.argv[2];root.mkdir(exist_ok=True)
slot=1794654000000;close=slot+STEP-1;now=slot+STEP+500
fixture=json.loads(FIXTURE.read_text())[0];pin=digest(make_plan(slot,fixture))
raw=json.dumps({'E':close+10,'k':dict(s='BTCUSDT',i='15m',t=slot,T=close,o='100',h='102',l='99',c='101',v='3',x=True)}).encode()
with patch.object(socket,'socket',side_effect=AssertionError('NETWORK_DISABLED')),patch('time.time',return_value=now/1000),patch('aql.observation.prospective.time_ns',return_value=now*1000000):
 path=root/str(slot);path.mkdir(exist_ok=True)
 if mode.startswith('crash'):
  persist_frame(path,raw,slot=slot,received=now,uncertainty=10,monotonic_ns=1,session=pin[:24])
 journal=DurableJournal(str(root/'journal.sqlite'));store=OperationalStore(str(root/'market.sqlite'))
 observer=ProspectiveObserver(root/'g2.sqlite',journal,store,fixture,synthetic=True)
 if mode=='crash-after-ack':
  meta,seal,bar=load_frame(path);journal.commit(bar);journal.commit_receipt(bar.stable_key())
 if mode=='crash-after-apply':consume(path,journal,store,observer,lambda:now,lambda seconds:None,slot=slot,plan_pin=pin)
 if mode.startswith('crash'):os._exit(91)
 rows=recover(root,journal,store,observer,slot,lambda:now,lambda seconds:None,count=2,plan_pin=pin)
 result={'rows':len(rows),'journal_rows':len(journal.replay('BTCUSDT','15m',limit=3)),'source_sha256':rows[0]['source_sha256'],'ack_sha256':rows[0]['ack_sha256'],'scanner_sha256':rows[0]['scanner_sha256']}
 print(json.dumps(result))
'''


def child(root, mode):
    return subprocess.run([sys.executable,'-B','-c',CHILD,str(root),mode],capture_output=True,text=True,
                          timeout=30,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})


@pytest.mark.parametrize('point',['crash-after-frame','crash-after-ack','crash-after-apply'])
def test_fresh_process_replays_exactly_once_across_durable_boundaries(tmp_path,point):
    assert child(tmp_path,point).returncode==91
    first=child(tmp_path,'recover');assert first.returncode==0,first.stderr
    second=child(tmp_path,'recover');assert second.returncode==0,second.stderr
    a=json.loads(first.stdout);b=json.loads(second.stdout)
    assert a==b and a['rows']==a['journal_rows']==1


def test_corrupt_saved_frame_fails_before_recovery_ack(tmp_path):
    assert child(tmp_path,'crash-after-frame').returncode==91
    path=next(tmp_path.glob('*/receipt.sqlite'))
    with sqlite3.connect(path) as db:db.execute("UPDATE frame SET raw=? WHERE id=1",(b'corrupt',))
    result=child(tmp_path,'recover')
    assert result.returncode!=0 and 'CUSTODY_TAMPER' in result.stderr
