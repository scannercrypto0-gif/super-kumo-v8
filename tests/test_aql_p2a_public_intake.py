"""TEST_ONLY native archive fixtures; never actual-market or paired-strategy proof."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import urllib.error
import zipfile

from research_wp_r0 import aql_p2a_public_intake as p

PLAN = Path(__file__).parents[1] / 'docs/research/p2a/development-plan.json'


def synthetic_archive(window, mutate=None):
    """Explicitly TEST_ONLY generated rows, with fresh fixture-only pins."""
    item = window['source']
    rows = []
    for i in range(item['bars']):
        t = item['first_open_ms'] + i * p.BAR_MS
        rows.append([str(t), '100.0', '110.0', '90.0', '101.0', '1.0',
                     str(t+p.BAR_MS-1), '100.0', '2', '0.5', '50.0', '0'])
    if mutate:
        mutate(rows)
    raw = ('\n'.join(','.join(r) for r in rows) + '\n').encode()
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr(item['name'][:-4] + '.csv', raw)
    archive = b.getvalue()
    checksum = (p.sha(archive) + '  ' + item['name'] + '\n').encode()
    item.update(archive_sha256=p.sha(archive), archive_bytes=len(archive),
                checksum_sha256=p.sha(checksum), checksum_bytes=len(checksum), member_sha256=p.sha(raw))
    return archive, checksum


class PublicIntakeSeams(unittest.TestCase):
    def setUp(self):
        self.plan = p.parse(PLAN.read_bytes())
        self.plan['selection'] = 'TEST_ONLY_SYNTHETIC_NATIVE_SCHEMA_FIXTURES'

    def make_cache(self, root, mutate=None):
        for w in self.plan['development_windows']:
            a,c = synthetic_archive(w, mutate)
            (root/w['source']['name']).write_bytes(a)
            (root/(w['source']['name']+'.CHECKSUM')).write_bytes(c)

    def intake(self, root, **kwargs):
        return p.intake(self.plan, p.canonical(self.plan), root,
                         verified_at_utc='2026-11-04T00:00:00Z', **kwargs)

    def test_plan_months_source_pins_and_embargo(self):
        p.validate_plan(self.plan)
        self.assertEqual(len(self.plan['development_windows']), 2)
        self.assertGreaterEqual(self.plan['embargo_ms'], 72*3600000)

    def test_plan_hash_and_object_bytes_drift(self):
        with self.assertRaises(p.IntakeError):
            p.read_plan(PLAN, '0'*64)
        with self.assertRaises(p.IntakeError):
            p.intake(self.plan, b'{}', '.', verified_at_utc='2026-11-04T00:00:00Z')

    def test_holdout_and_72h_boundary_fail_closed(self):
        for start,end in [(p.HOLDOUT_START,p.HOLDOUT_END),
                          (p.HOLDOUT_START-p.EMBARGO_MS-1,p.HOLDOUT_START-p.EMBARGO_MS+1)]:
            with self.assertRaises(p.IntakeError):
                p.guard_development(start,end,self.plan)
        p.guard_development(p.HOLDOUT_START-p.EMBARGO_MS-2,
                             p.HOLDOUT_START-p.EMBARGO_MS,self.plan)

    def test_cannot_enable_holdout_or_shorten_embargo(self):
        for key,value in [('phase','HOLDOUT'),('embargo_ms',1000)]:
            plan=copy.deepcopy(self.plan);plan[key]=value
            with self.assertRaises(p.IntakeError): p.validate_plan(plan)
        self.plan['sealed_holdout']['start_utc']='2026-11-01T00:00:00Z'
        with self.assertRaises(p.IntakeError): p.validate_plan(self.plan)

    def test_noncontiguous_not_duplicate_or_adjacent(self):
        self.plan['development_windows'][1]=copy.deepcopy(self.plan['development_windows'][0])
        with self.assertRaises(p.IntakeError): p.validate_plan(self.plan)

    def test_wrong_venue_uri_unit_and_arms_rejected(self):
        for mutate in [lambda x:x.update(source_market='FUTURES'),
                       lambda x:x['development_windows'][0]['source'].update(url='https://evil.test/data'),
                       lambda x:x['development_windows'][0].update(timestamp_unit='MICROSECONDS'),
                       lambda x:x.update(shadow_registration={'pretend':True})]:
            plan=copy.deepcopy(self.plan);mutate(plan)
            with self.assertRaises(p.IntakeError):p.validate_plan(plan)

    def test_full_native_fixture_deterministic_readonly_and_nonpit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_cache(root)
            before={f.name:p.sha(f.read_bytes()) for f in root.iterdir()}
            a=self.intake(root);b=self.intake(root)
            self.assertEqual(p.canonical(a[0]),p.canonical(b[0]))
            self.assertEqual(a[1],b[1]);self.assertEqual(a[0]['validated_bars'],5760)
            self.assertEqual(a[0]['status'],'COMPLETE_DEVELOPMENT_INTAKE')
            self.assertEqual(before,{f.name:p.sha(f.read_bytes()) for f in root.iterdir()})
            self.assertFalse(a[0]['holdout_fetched']);self.assertIsNone(a[0]['opportunities'])
            self.assertIsNone(a[0]['comparative_alpha'])
            bar=p.parse(a[1].splitlines()[0]);self.assertIsNone(bar['historical_known_at_ms'])
            self.assertEqual(bar['finality'],'ARCHIVED_CLOSED_INTERVAL')

    def test_duplicate_gap_bad_ohlc_and_interval_rejected(self):
        mutations=[lambda r:r.__setitem__(1,r[0]),lambda r:r.pop(1),
                   lambda r:r[0].__setitem__(2,'80'),lambda r:r[0].__setitem__(6,str(int(r[0][6])+1)),
                   lambda r:r[0].__setitem__(1,'NaN')]
        for mutate in mutations:
            with self.subTest(mutate=mutate),tempfile.TemporaryDirectory() as d:
                root=Path(d);self.make_cache(root,mutate)
                with self.assertRaises((p.IntakeError,ValueError)):
                    p.read_source(self.plan['development_windows'][0],root)

    def test_byte_drift_requires_new_source_plan_not_silent_correction(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_cache(root)
            name=self.plan['development_windows'][0]['source']['name']
            (root/name).write_bytes((root/name).read_bytes()+b'changed')
            with self.assertRaises(p.IntakeError):p.read_source(self.plan['development_windows'][0],root)

    def test_checksum_and_member_hash_drift_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_cache(root)
            w=self.plan['development_windows'][0];w['source']['member_sha256']='0'*64
            with self.assertRaises(p.IntakeError):p.read_source(w,root)

    def test_missing_source_no_fetch_does_not_fabricate_zero_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            m,index,_=self.intake(Path(d))
            self.assertEqual(m['status'],'BLOCKED_OR_PARTIAL_INTAKE')
            self.assertEqual(index,b'')
            self.assertIsNone(m['development_windows'][0]['observed_bars'])
            self.assertIsNone(m['development_windows'][0]['gap_count'])

    def test_denied_fetch_stops_without_retry_or_alternate_source(self):
        calls=[]
        def denied(url):
            calls.append(url);raise p.AccessDenied('HTTP_DENIED_451')
        with tempfile.TemporaryDirectory() as d:
            m,index,_=self.intake(Path(d),fetch=True,fetcher=denied)
            self.assertEqual(len(calls),1);self.assertEqual(m['unattempted_windows'],1)
            self.assertEqual(index,b'');self.assertIn('451',m['development_windows'][0]['reason'])

    def test_successful_fetch_pins_and_no_cache_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            w=self.plan['development_windows'][0];a,c=synthetic_archive(w);calls=[]
            def get(url):
                calls.append(url);return (c if url.endswith('.CHECKSUM') else a),{'url':url,'status':200}
            bars,_,events=p.read_source(w,root,fetch=True,fetcher=get)
            self.assertEqual(len(bars),2784);self.assertEqual(len(calls),2)
            self.assertEqual(list(root.iterdir()),[])
            self.assertEqual(events[0]['mode'],'PUBLIC_ARCHIVE_GET')

    def test_public_fetch_forbids_arbitrary_host_and_redirects(self):
        with self.assertRaises(p.IntakeError):p.fetch_public('https://example.com/data.zip')
        with self.assertRaises(p.AccessDenied):
            p.NoRedirect().redirect_request(None,None,302,'',{},'https://another.test')

    def test_fetch_http451_has_one_attempt_and_no_proxy(self):
        opener=MagicMock();opener.open.side_effect=urllib.error.HTTPError('https://data.binance.vision',451,'denied',{},None)
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(p.AccessDenied):p.fetch_public(self.plan['development_windows'][0]['source']['url'])
        self.assertEqual(opener.open.call_count,1)

    def test_fetch_timeout_is_terminal(self):
        opener=MagicMock();opener.open.side_effect=TimeoutError('TEST_ONLY')
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(p.AccessDenied):p.fetch_public(self.plan['development_windows'][0]['source']['url'])
        self.assertEqual(opener.open.call_count,1)

    def test_malformed_archive_is_recorded_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_cache(root)
            w=self.plan['development_windows'][0];bad=b'INVALID_ZIP'
            check=(p.sha(bad)+'  '+w['source']['name']+'\n').encode()
            w['source'].update(archive_sha256=p.sha(bad),archive_bytes=len(bad),
                               checksum_sha256=p.sha(check),checksum_bytes=len(check))
            (root/w['source']['name']).write_bytes(bad)
            (root/(w['source']['name']+'.CHECKSUM')).write_bytes(check)
            m,_,_=self.intake(root)
            self.assertEqual(m['status'],'BLOCKED_OR_PARTIAL_INTAKE')
            self.assertIn('NATIVE_ARCHIVE_REJECTED',m['development_windows'][0]['reason'])

    def test_unknown_fetch_time_not_forged_from_bar_close(self):
        x=p.cached_fetch_evidence(self.plan['development_windows'][0],None)
        self.assertIsNone(x['reported_fetch_at_utc'])
        with self.assertRaises(p.IntakeError):
            p.cached_fetch_evidence(self.plan['development_windows'][0],b'[]')

    def test_private_manifest_index_contract_and_asof_no_future(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);cache=root/'cache';cache.mkdir();self.make_cache(cache)
            m,index,raw=self.intake(cache);out=root/'out'
            anchor=p.persist(out,m,index,raw,p.canonical(self.plan))
            plan,manifest,rows=p.read_validated_index(out,expected_manifest_sha256=anchor)
            w=plan['development_windows'][0];cut=p.utc_ms(w['start_utc'])+20*p.BAR_MS
            prefix=p.asof_features(rows,plan,dataset_id=w['dataset_id'],cutoff_ms=cut)
            self.assertEqual(len(prefix),20);self.assertTrue(all(x['close_ms']<cut for x in prefix))
            with self.assertRaises(p.IntakeError):p.asof_features(rows,plan,dataset_id='SEALED',cutoff_ms=p.HOLDOUT_START)
            with self.assertRaises(p.IntakeError):p.persist(out,m,index,raw,p.canonical(self.plan))
            (out/'bars.jsonl').write_bytes(index+b'changed')
            with self.assertRaises(p.IntakeError):p.read_validated_index(out,expected_manifest_sha256=anchor)

    def test_rejected_partial_source_not_usable_by_core(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);m,index,raw=self.intake(root)
            out=root/'out';anchor=p.persist(out,m,index,raw,p.canonical(self.plan))
            with self.assertRaises(p.IntakeError):p.read_validated_index(out,expected_manifest_sha256=anchor)
            self.assertEqual(p.core_source_handoff(m,index)['sources'],[])

    def test_core_source_mapping_is_per_period_not_paired_opportunities(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.make_cache(root);m,index,_=self.intake(root)
            h=p.core_source_handoff(m,index)
            self.assertEqual(len(h['sources']),2);self.assertIsNone(h['opportunities'])
            self.assertFalse(h['comparison_executed'])
            rows=[p.parse(x) for x in index.splitlines()]
            for src in h['sources']:
                kw=src['source_kwargs'];bs=src['bar_kwargs']
                selected=[r for r in rows if r['dataset_id']==kw['source_id']]
                self.assertEqual(kw['normalized_sha256'],p.sha(b''.join(p.canonical(r) for r in selected)))
                self.assertEqual(kw['manifest_sha256'],p.sha(p.canonical(m)))
                self.assertEqual(len(selected),len(bs))
                self.assertTrue(all(b['available_at_ms'] is None and b['availability_evidence_ref'] is None for b in bs))

    def test_predeclaration_and_nonfinite_json_fail_closed(self):
        with self.assertRaises(p.IntakeError):
            p.intake(self.plan,p.canonical(self.plan),'.',verified_at_utc='2020-01-01T00:00:00Z')
        for b in [b'{"a":1,"a":2}',b'{"a":NaN}']:
            with self.assertRaises(p.IntakeError):p.parse(b)


if __name__=='__main__':unittest.main()
