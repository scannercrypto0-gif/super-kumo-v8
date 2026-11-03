"""TEST_ONLY source mapping fixtures; imports exact external Core, not a mock producer."""
from copy import deepcopy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_wp_r0 import aql_p2a_core_source_bridge as bridge
from research_wp_r0 import aql_p2a_public_intake as intake


def fixture():
    rows, windows = [], []
    for dataset, start, source_hash in [('TEST_ONLY_FEB',1706745600000,'a'*64),
                                        ('TEST_ONLY_AUG',1722470400000,'b'*64)]:
        windows.append({'dataset_id':dataset,'expected_bars':2,'observed_bars':2,
                        'source':{'archive_sha256':source_hash}})
        for i in range(2):
            row={'dataset_id':dataset,'open_ms':start+i*900000,'close_ms':start+(i+1)*900000-1,
                 'is_final':True,'finality':'ARCHIVED_CLOSED_INTERVAL','historical_known_at_ms':None,
                 'historical_receipt_ms':None,'historical_publication_ms':None,'fixture_scope':'TEST_ONLY'}
            row['bar_sha256']=intake.sha(intake.canonical(row));rows.append(row)
    manifest={'status':'COMPLETE_DEVELOPMENT_INTAKE','phase':'DEVELOPMENT_ONLY',
              'holdout_fetched':False,'holdout_evaluated':False,'development_windows':windows}
    handoff=intake.core_source_handoff(manifest,b''.join(intake.canonical(r) for r in rows))
    return manifest,rows,handoff


class CoreSourceBridge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('AQL_P2_CORE_MODULE')
        if not path:
            raise RuntimeError('EXACT_PINNED_CORE_MODULE_REQUIRED_NO_SILENT_SKIP')
        cls.path=Path(path)
        cls.core=bridge.load_pinned_core(cls.path)

    def test_real_core_constructors_per_dataset_never_schedule(self):
        m,rows,h=fixture()
        with patch.object(self.core,'schedule_pair',side_effect=AssertionError('NO_CANDIDATE_AUTHORITY')) as sched:
            with patch.object(self.core,'validate_bars',wraps=self.core.validate_bars) as validate:
                result=bridge.validate_mapping(m,rows,h,self.core)
                self.assertEqual(validate.call_count,2)
            sched.assert_not_called()
        self.assertEqual([r['validated_bars'] for r in result],[2,2])
        self.assertTrue(all(r['historical_known_at_ms'] is None for r in result))

    def test_duplicate_missing_or_merged_dataset_rejected(self):
        for mutate in [lambda h:h['sources'].pop(),
                       lambda h:h['sources'].append(deepcopy(h['sources'][0])),
                       lambda h:h['sources'][0]['bar_kwargs'].extend(h['sources'][1]['bar_kwargs'])]:
            m,rows,h=fixture();mutate(h)
            with self.assertRaises(intake.IntakeError):bridge.validate_mapping(m,rows,h,self.core)

    def test_original_hash_domains_and_bar_mapping_cannot_drift(self):
        for mutate in [lambda h:h['sources'][0]['source_kwargs'].update(manifest_sha256='0'*64),
                       lambda h:h['sources'][0]['source_kwargs'].update(normalized_sha256='0'*64),
                       lambda h:h['sources'][0]['bar_kwargs'][0].update(content_sha256='0'*64),
                       lambda h:h['sources'][0]['source_kwargs'].update(source_package_sha256='0'*64)]:
            m,rows,h=fixture();mutate(h)
            with self.assertRaises(intake.IntakeError):bridge.validate_mapping(m,rows,h,self.core)

    def test_actual_core_rejects_gap_duplicate_and_unfinalized(self):
        for kind in ['gap','duplicate','unfinalized']:
            m,rows,_=fixture()
            if kind=='gap':rows[1]['open_ms']+=900000;rows[1]['close_ms']+=900000
            elif kind=='duplicate':rows[1]=deepcopy(rows[0])
            else:rows[0]['is_final']=False
            h=intake.core_source_handoff(m,b''.join(intake.canonical(r) for r in rows))
            with self.assertRaisesRegex(intake.IntakeError,'CORE_SOURCE_CONTRACT_REJECTED'):
                bridge.validate_mapping(m,rows,h,self.core)

    def test_no_known_at_upgrade_holdout_or_pair_authority(self):
        for kind in ['availability','holdout','trial']:
            m,rows,h=fixture()
            if kind=='availability':h['sources'][0]['bar_kwargs'][0]['available_at_ms']=1706746500000
            elif kind=='holdout':m['holdout_evaluated']=True
            else:h['frozen_trial']={'fake_registration':True}
            with self.assertRaises(intake.IntakeError):bridge.validate_mapping(m,rows,h,self.core)

    def test_core_code_pin_is_checked_before_any_import(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'forged.py';path.write_text("raise RuntimeError('MUST_NOT_EXECUTE')")
            with self.assertRaisesRegex(intake.IntakeError,'CORE_MODULE_BYTE_PIN_MISMATCH'):
                bridge.load_pinned_core(path)

    def test_core_pin_and_input_fixture_unchanged_deterministic(self):
        m,rows,h=fixture();before=intake.canonical([m,rows,h]);module_bytes=self.path.read_bytes()
        a=bridge.validate_mapping(m,rows,h,self.core);b=bridge.validate_mapping(m,rows,h,self.core)
        self.assertEqual(intake.canonical(a),intake.canonical(b))
        self.assertEqual(before,intake.canonical([m,rows,h]));self.assertEqual(module_bytes,self.path.read_bytes())

    def test_missing_private_runtime_is_exact_access_blocker(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                bridge.run_bridge(Path(d)/'absent',self.path,adapter_code_sha='1'*40)


if __name__=='__main__':unittest.main()
