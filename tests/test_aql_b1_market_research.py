"""B1 new-path tests on actual downloaded originals, not synthetic market fixtures."""
import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from research_wp_r0.aql_b1_market_research import (
    describe_market, load_originals, parse_archive,
)

LOCK = Path(__file__).resolve().parents[1]/'docs/evidence/factory-b1-20261101/originals-lock.json'


class B1OriginalMarket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Missing actual bytes is a hard error; never substitute a generated fixture.
        cls.data = Path(os.environ['AQL_B1_DATA_DIR'])
        cls.lock = json.loads(LOCK.read_bytes())
        cls.rows, _, _ = load_originals(cls.lock, cls.data)
        cls.first = int(cls.rows[0][0])

    def archive(self, rows):
        # Adversarial derivative of actual vendor rows, only for parser negatives.
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as z:
            z.writestr('test.csv', '\n'.join(','.join(r) for r in rows)+'\n')
        return buffer.getvalue()

    def test_full_original_year(self):
        self.assertEqual(len(self.rows),35136)
        self.assertEqual(self.rows[-1][6],'1735689599999')

    def test_changed_archive_lock_denied(self):
        lock=copy.deepcopy(self.lock); lock['archives'][0]['archive_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'locked original archive'):
            load_originals(lock,self.data)

    def test_changed_checksum_lock_denied(self):
        lock=copy.deepcopy(self.lock); lock['archives'][0]['checksum_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'locked original checksum'):
            load_originals(lock,self.data)

    def test_changed_member_denied(self):
        lock=copy.deepcopy(self.lock); lock['archives'][0]['member_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CSV member hash'):
            load_originals(lock,self.data)

    def test_duplicate_or_missing_grid_denied(self):
        rows=copy.deepcopy(self.rows[:2]); rows[1][0]=rows[0][0]
        with self.assertRaisesRegex(ValueError,'contiguous'):
            parse_archive(self.archive(rows),'test.csv',self.first,2)

    def test_changed_ohlc_denied(self):
        rows=copy.deepcopy(self.rows[:2]); rows[0][2]='1'
        with self.assertRaisesRegex(ValueError,'OHLC'):
            parse_archive(self.archive(rows),'test.csv',self.first,2)

    def test_nonfinite_denied(self):
        rows=copy.deepcopy(self.rows[:2]); rows[0][5]='NaN'
        with self.assertRaisesRegex(ValueError,'nonfinite'):
            parse_archive(self.archive(rows),'test.csv',self.first,2)

    def test_horizon_censor_and_next_open_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'windows.csv'
            results=describe_market(self.rows[:17],path)
            self.assertEqual((results[0]['complete'],results[0]['censored']),(1,16))
            self.assertEqual(results[1]['complete'],0)
            self.assertEqual(results[2]['complete'],0)
            first=path.read_text().splitlines()[1].split(',')
            self.assertEqual(first[3],str(__import__('decimal').Decimal(self.rows[1][1])))
            self.assertEqual(first[4],self.rows[16][4])


if __name__ == '__main__':
    unittest.main()
