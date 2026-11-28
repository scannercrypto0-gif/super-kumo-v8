"""Generated clocks, real Store/lineage and read-only settlement; no provider."""
import hashlib
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from tools.realtime_market_feed import settlement as protocol
from tools.realtime_market_feed import service

START=1_700_000_040_000  # aligned minute
END=START+86_400_000
MONO=1_000_000


def packet(opened, close='10.5'):
    return json.dumps({'e':'kline','s':'BTCUSDT','k':{'i':'1m','t':opened,
        'T':opened+59999,'o':'10','h':'11','l':'9','c':close,'v':'2','n':1,'x':True}})


@pytest.fixture(scope='module')
def baseline(tmp_path_factory):
    root=tmp_path_factory.mktemp('settlement-base');db=root/'source.sqlite'
    current=[START,MONO]
    with patch.object(protocol,'clock',lambda:tuple(current)), \
         patch.object(service,'utc_ms',lambda:current[0]), \
         patch.object(service.time,'monotonic_ns',lambda:current[1]*1_000_000):
        store=service.Store(db)
        run=store.begin_run(['btcusdt'],86400)
        current[:]=[START+1000,MONO+1000]
        protocol.create_plan(db,run,root/'plan.json',owner_decision_ref='OWNER_CHAT_D14A_120S_ENGINEERING_ONLY')
        for i in range(1439):
            opened=START+i*60000
            current[:]=[opened+60000,MONO+opened+60000-START]
            store.ingest(packet(opened),received_ms=current[0])
        current[:]=[END,MONO+86_400_000]
        endpoint=protocol.capture_endpoint(db,root/'plan.json',root/'endpoint.json')
        assert endpoint['body']['coverage_at_endpoint']==1439
        store.db.close()
    return root,run


@pytest.fixture
def case(tmp_path,baseline,monkeypatch):
    root,run=baseline
    for name in ('source.sqlite','plan.json','endpoint.json'):
        shutil.copy2(root/name,tmp_path/name)
    current=[END+40000,MONO+86_440_000]
    monkeypatch.setattr(protocol,'clock',lambda:tuple(current))
    monkeypatch.setattr(service,'utc_ms',lambda:current[0])
    monkeypatch.setattr(service.time,'monotonic_ns',lambda:current[1]*1_000_000)
    return tmp_path,run,current


def deliver(case,opened=END-60000,close='10.5'):
    root,run,current=case
    store=service.Store(root/'source.sqlite');store.active_run_id=run
    store.ingest(packet(opened,close),received_ms=current[0]);store.db.close()


def finish(case):
    root,_,_=case
    return protocol.finalize(root/'source.sqlite',root/'plan.json',root/'endpoint.json',root/'final.json')


def verify(case):
    root,_,_=case
    from tools.realtime_market_feed.acceptance_gates import evaluate_settlement_coverage
    return evaluate_settlement_coverage(root/'source.sqlite',root/'plan.json',root/'endpoint.json',root/'final.json',
        expected_plan_sha256=protocol.read(root/'plan.json')['sha256'],
        expected_endpoint_sha256=protocol.read(root/'endpoint.json')['sha256'],
        expected_verifier_code_sha256=protocol.CODE_SHA256)


def test_late_closed_boundary_settles_without_extending_denominator(case):
    root,_,_=case
    before=hashlib.sha256((root/'endpoint.json').read_bytes()).hexdigest()
    deliver(case);receipt=finish(case);result=verify(case)
    assert result['status']=='SETTLEMENT_COVERAGE_PASS'
    assert result['coverage_at_endpoint']==1439 and result['settled_bars']==1440
    assert result['late_bars']==1 and result['endpoint_ms']==END
    assert result['operational_24h_acceptance']=='NOT_ATTESTED'
    assert receipt['body']['late_arrivals'][0]['received_ms']==END+40000
    assert receipt['body']['expected_bars']==1440
    assert hashlib.sha256((root/'endpoint.json').read_bytes()).hexdigest()==before


def test_exact_deadline_is_inclusive(case):
    case[2][:]=[END+120000,MONO+86_520_000]
    deliver(case);finish(case)
    assert verify(case)['status']=='SETTLEMENT_COVERAGE_PASS'


def test_beyond_deadline_fails_closed(case):
    case[2][:]=[END+120001,MONO+86_520_001]
    deliver(case)
    with pytest.raises(ValueError,match='SETTLEMENT_DEADLINE'):finish(case)
    assert not (case[0]/'final.json').exists()


def test_missing_boundary_and_future_open_do_not_reduce_denominator(case):
    deliver(case,opened=END)
    receipt=finish(case)
    assert receipt['body']['expected_bars']==1440
    assert len(receipt['body']['snapshot']['missing'])==1
    assert verify(case)['status']=='SETTLEMENT_COVERAGE_BLOCKED'


def test_conflict_in_settlement_cannot_be_cured(case):
    deliver(case);deliver(case,close='10.6');finish(case)
    assert verify(case)['status']=='SETTLEMENT_COVERAGE_BLOCKED'


def test_bad_lineage_rejected(case):
    deliver(case);store=service.Store(case[0]/'source.sqlite')
    store.db.execute('UPDATE final_bar_lineage SET receipt_sha256=? WHERE open_ms=?',('0'*64,END-60000))
    store.db.commit();store.db.close()
    with pytest.raises(ValueError,match='FEED_'):finish(case)


def test_clock_jump_or_monotonic_reversal_rejected(case):
    deliver(case);case[2][1]+=3000
    with pytest.raises(ValueError,match='SETTLEMENT_(CLOCK|DEADLINE)'):finish(case)
    case[2][1]=MONO
    with pytest.raises(ValueError,match='SETTLEMENT_(CLOCK|DEADLINE)'):finish(case)


def test_no_retroactive_plan_or_late_endpoint_capture(case):
    root,run,_=case
    with pytest.raises(ValueError,match='PLAN_MUST_PRECEDE'):
        protocol.create_plan(root/'source.sqlite',run,root/'late-plan.json',owner_decision_ref='TEST')
    with pytest.raises(ValueError,match='ENDPOINT_CAPTURE_WINDOW'):
        protocol.capture_endpoint(root/'source.sqlite',root/'plan.json',root/'late-end.json')


def test_create_only_and_independent_receipt_recompute(case):
    deliver(case);finish(case)
    with pytest.raises(FileExistsError):finish(case)
    body=protocol.read(case[0]/'final.json')['body'];body['late_arrivals']=[]
    (case[0]/'final.json').unlink();protocol.publish(case[0]/'final.json',body)
    with pytest.raises(ValueError,match='SOURCE_RECOMPUTE_MISMATCH'):verify(case)


def test_original_source_event_rewrite_blocked(case):
    deliver(case);store=service.Store(case[0]/'source.sqlite')
    store.db.execute("UPDATE service_event SET detail='CHANGED' WHERE kind='RUN_STARTED'")
    store.db.commit();store.db.close()
    with pytest.raises(ValueError,match='ENDPOINT_SOURCE_CHANGED'):finish(case)


def test_external_pins_required(case):
    deliver(case);finish(case);root,_,_=case
    with pytest.raises(ValueError,match='EXTERNAL_PIN'):
        protocol.verify(root/'source.sqlite',root/'plan.json',root/'endpoint.json',root/'final.json',
            expected_plan_sha256='0'*64,expected_endpoint_sha256='0'*64,
            expected_verifier_code_sha256=protocol.CODE_SHA256)


def test_premature_observation_stop_blocks_settlement(case):
    root,run,_=case
    store=service.Store(root/'source.sqlite')
    store.db.execute('UPDATE service_run SET stopped_ms=? WHERE run_id=?',(END-1,run))
    store.db.commit();store.db.close()
    with pytest.raises(ValueError,match='OBSERVATION_ENDED_EARLY'):finish(case)


def test_monotonic_deadline_is_also_hard_bound(case):
    case[2][:]=[END+120000,MONO+86_520_001]
    with pytest.raises(ValueError,match='SETTLEMENT_DEADLINE'):finish(case)


def test_read_only_source_and_pinned_identity(case):
    deliver(case);root,_,_=case
    before=hashlib.sha256((root/'source.sqlite').read_bytes()).hexdigest()
    finish(case);verify(case)
    assert hashlib.sha256((root/'source.sqlite').read_bytes()).hexdigest()==before
    store=service.Store(root/'source.sqlite')
    store.db.execute("UPDATE service_run SET config_sha256=?",('0'*64,))
    store.db.commit();store.db.close()
    with pytest.raises(ValueError,match='RUN_PIN_CHANGED'):verify(case)


def test_subminute_plan_excludes_partial_leading_and_trailing(case):
    root,_,current=case
    # Independent new generated run, not a rewrite of an existing endpoint.
    current[:]=[END+40001,MONO+86_440_001]
    store=service.Store(root/'subminute.sqlite')
    run=store.begin_run(['btcusdt'],86400)
    plan=protocol.create_plan(root/'subminute.sqlite',run,root/'subminute-plan.json',
        owner_decision_ref='TEST_ONLY')
    p=plan['body']
    assert (p['eligible_end_ms']-p['eligible_start_ms'])//60000==1439
    store.db.close()


def test_other_run_commit_cannot_settle_original_observation(case):
    root,_,current=case
    store=service.Store(root/'source.sqlite');store.active_run_id='other-run'
    store.ingest(packet(END-60000),received_ms=current[0]);store.db.close()
    with pytest.raises(ValueError,match='COMMIT_RUN_UNBOUND'):finish(case)


@pytest.mark.parametrize('offset',[40000,120000])
def test_commit_visible_after_clock_sample_but_beyond_monotonic_cutoff(case,monkeypatch,offset):
    root,_,current=case
    current[:]=[END+offset,MONO+86_400_000+offset]
    original=protocol.collect
    injected=[False]
    endpoint_before=(root/'endpoint.json').read_bytes()
    def race(database,plan,wall_cutoff,mono_cutoff):
        # finalize already sampled in-bound wall/mono. A genuine Store commit
        # becomes visible before the reader begins its SQLite snapshot, with
        # wall time unchanged but monotonic timestamp one millisecond too late.
        if not injected[0]:
            injected[0]=True
            with patch.object(service.time,'monotonic_ns',lambda:(current[1]+1)*1_000_000):
                deliver(case)
        return original(database,plan,wall_cutoff,mono_cutoff)
    monkeypatch.setattr(protocol,'collect',race)
    with pytest.raises(ValueError,match='COMMIT_RUN_UNBOUND'):finish(case)
    assert injected[0] and not (root/'final.json').exists()
    assert (root/'endpoint.json').read_bytes()==endpoint_before


def test_endpoint_membership_uses_logical_cutoffs_not_capture_uncertainty(case):
    root,_,current=case
    current[:]=[END,MONO+86_400_000]
    with patch.object(service.time,'monotonic_ns',lambda:(current[1]+1)*1_000_000):
        deliver(case)
    # Capture is permitted up to2s after endpoint; that uncertainty does not
    # admit a post-endpoint commit into original endpoint coverage.
    current[:]=[END+1,MONO+86_400_001]
    with pytest.raises(ValueError,match='COMMIT_RUN_UNBOUND'):
        protocol.capture_endpoint(root/'source.sqlite',root/'plan.json',root/'new-endpoint.json')
    assert not (root/'new-endpoint.json').exists()


def test_endpoint_exact_wall_and_monotonic_boundary_is_inclusive(case):
    root,_,current=case
    current[:]=[END,MONO+86_400_000];deliver(case)
    endpoint=protocol.capture_endpoint(root/'source.sqlite',root/'plan.json',root/'exact-endpoint.json')
    assert endpoint['body']['coverage_at_endpoint']==1440
    assert endpoint['body']['snapshot']['cutoff_ms']==END
    assert endpoint['body']['snapshot']['cutoff_monotonic_ms']==MONO+86_400_000
