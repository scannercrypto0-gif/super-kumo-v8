"""RED-first D2 contract probes against the pre-D2 local-only API.

This first revision intentionally exposes the five documented missing D2 gates.
The implementation revision will bind these contracts to a separate D2 adapter;
it must not change the accepted local D1 API or its original 64-case suite.
"""
from collections import Counter
from dataclasses import replace
import json

import pytest

from aql.delivery.authority import Authority, Limits, PublicationDenied
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from aql.storage.operational_store import OperationalStore


def bar(i=0):
    return MarketBar('BTCUSDT','1m',i*60000,(i+1)*60000-1,
        100.,101.,99.,100.,1.,True,'synthetic-d2',(i+1)*60000).with_checksum()


def baseline(root, *, records=2, capacity=8, events=64):
    j=DurableJournal(str(root/'source.sqlite'))
    for i in range(records): j.commit(bar(i))
    a=Authority(j,limits=Limits(capacity,131072,2,events),synthetic=True,
                stores=[OperationalStore(str(root/'operational.sqlite'))])
    return j,a,a.fence('sandbox')


def test_P1_no_target_effect_means_no_confirmed_D_or_S(tmp_path):
    j,a,e=baseline(tmp_path)
    a.deliver('sandbox',e,1)
    assert a.view('sandbox')['D']==[]
    assert a.view('sandbox')['S']==0


def test_P2_duplicate_ack_has_no_event_growth(tmp_path):
    j,a,e=baseline(tmp_path)
    a.deliver('sandbox',e,1)
    with j._connect() as c: before=c.execute('SELECT COUNT(*) FROM core128_events').fetchone()[0]
    a.deliver('sandbox',e,1)
    with j._connect() as c: after=c.execute('SELECT COUNT(*) FROM core128_events').fetchone()[0]
    assert after==before


def test_P5_new_epoch_cannot_blindly_confirm_old_receipt(tmp_path):
    j,a,e=baseline(tmp_path);sid=a.stage('sandbox',e,1)
    receipt=a.publish('sandbox',e,1,sid);new=a.fence('sandbox')
    with pytest.raises(PublicationDenied): a.settle('sandbox',new,1,receipt=receipt)


def test_P7_archive_quota_does_not_consume_critical_consumer_quota(tmp_path):
    j,a,e=baseline(tmp_path,capacity=2)
    archive=a.fence('archive');a.stage('archive',archive,1);a.stage('archive',archive,2)
    assert a.stage('sandbox',e,1)


def test_P8_idempotent_retries_do_not_fill_ledger(tmp_path):
    j,a,e=baseline(tmp_path,events=8)
    first=a.deliver('sandbox',e,1)
    for _ in range(8): assert a.deliver('sandbox',e,1)==first
