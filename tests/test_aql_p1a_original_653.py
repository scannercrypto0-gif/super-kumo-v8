"""TEST_ONLY synthetic seam fixtures. Never original-source/real-run evidence."""
from copy import deepcopy
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from research_wp_r0 import aql_p1a_original_653 as p


def fixture(count=1):
    pairs = []
    for i in range(count):
        e = dict(trial_id='TEST_ONLY', opportunity_id=f'opp-{i}', producer_event_id=f'pid-{i}',
            run_manifest_sha256='a' * 64, strategy_digest='b' * 64,
            decision_cutoff_ms=(20 + i) * p.BAR_MS, decision_ms=(20 + i) * p.BAR_MS + 2000,
            feature_policy_version='TEST_ONLY_FEATURE_V1', gap_inventory_sha256='c' * 64,
            correction_lineage_sha256='d' * 64, prefix_bar_checksums_sha256='e' * 64)
        e['envelope_sha256'] = p.content_hash(e)
        status = 'NO_SIGNAL' if i < min(616, count) else ('REJECTED' if i < 643 else 'TRIGGERED')
        r = {k: e[k] for k in ['trial_id', 'opportunity_id', 'producer_event_id',
                               'envelope_sha256', 'run_manifest_sha256', 'strategy_digest']}
        r.update(policy_id='TEST_ONLY', assumptions_digest='f' * 64,
                 effect_disposition=status, ordered_financial_event_ids=[], ordered_financial_payload_hashes=[])
        r['receipt_sha256'] = p.content_hash(r)
        pairs.append((e, r))
    bars = [dict(open_ms=i * p.BAR_MS, open=100., high=110., low=90., close=105., finalized=True)
            for i in range(672)]
    return pairs, bars


def report(pairs=None, bars=None):
    fp, fb = fixture()
    return p.build_report(pairs or fp, fb if bars is None else bars, 672 * p.BAR_MS,
                          {'scope': 'TEST_ONLY'}, generated_at_utc='2026-11-03T00:00:00Z',
                          code_sha='1' * 40)


class Original653Seams(unittest.TestCase):
    def setUp(self):
        self.pairs, self.bars = fixture()
        e = self.pairs[0][0]
        self.snap = p.RetrospectiveSnapshot(e['trial_id'], e['run_manifest_sha256'], e['opportunity_id'],
            e['producer_event_id'], e['envelope_sha256'], e['decision_cutoff_ms'], e['decision_ms'],
            'UNKNOWN', 'MISSING_ORIGINAL_F1_CAPTURE', None, 'NOT_ESTABLISHED', None, 'f' * 64)

    def window(self, bars=None, end=None, horizon=None):
        return p.window(self.snap, horizon or p.HORIZONS[0], self.bars if bars is None else bars,
                        672 * p.BAR_MS if end is None else end)[1]

    def test_exact_exclusive_window_and_unsigned_metrics(self):
        bars = deepcopy(self.bars)
        bars[19]['high'] = 9999.
        bars[36]['high'] = 8888.
        w = self.window(bars)
        self.assertEqual((w['expected_bars'], w['observed_bars'], w['availability']), (16, 16, 'COMPLETE'))
        self.assertEqual(w['market_metrics']['observed_high'], 110.)
        self.assertAlmostEqual(w['market_metrics']['market_low_return'], -.1)
        self.assertIsNone(w['directional_metrics'])

    def test_exact_source_end_is_complete(self):
        self.assertEqual(self.window(end=36 * p.BAR_MS)['availability'], 'COMPLETE')

    def test_partial_window_never_imputes_metrics(self):
        w = self.window(end=35 * p.BAR_MS)
        self.assertEqual((w['availability'], w['observed_bars']), ('CENSORED', 15))
        self.assertIsNone(w['market_metrics'])

    def test_zero_post_cutoff_is_censored_not_zero_return(self):
        w = self.window(end=20 * p.BAR_MS)
        self.assertEqual((w['availability'], w['observed_bars']), ('CENSORED', 0))
        self.assertIsNone(w['market_metrics'])

    def test_gap_is_unknown_even_in_censored_prefix(self):
        bars = [b for b in self.bars if b['open_ms'] != 22 * p.BAR_MS]
        self.assertEqual(self.window(bars)['availability_reason'], 'GAPPED_WINDOW')
        self.assertEqual(self.window(bars, end=35 * p.BAR_MS)['availability'], 'UNKNOWN')

    def test_duplicate_bar_is_unknown(self):
        self.assertEqual(self.window(self.bars + [self.bars[22]])['availability_reason'], 'DUPLICATE_BAR')

    def test_unfinalized_or_corrupt_is_unknown(self):
        for change, expected in [({'finalized': False}, 'UNFINALIZED_BAR'),
                                 ({'high': float('nan')}, 'INVALID_OHLC'),
                                 ({'low': -1.}, 'INVALID_OHLC')]:
            bars = deepcopy(self.bars)
            bars[22].update(change)
            self.assertEqual(self.window(bars)['availability_reason'], expected)

    def test_reversed_bars_do_not_change_reference(self):
        self.assertEqual(self.window(list(reversed(self.bars))), self.window())

    def test_653_denominator_1959_slots_censor_counts(self):
        pairs, bars = fixture(653)
        r = report(pairs, bars)
        self.assertEqual(r['summary']['original_f3_counts'], {'NO_SIGNAL': 616, 'REJECTED': 27, 'TRIGGERED': 10})
        self.assertEqual(len(r['rows']), 1959)
        for h, n in [(4, 637), (24, 557), (72, 365)]:
            self.assertEqual(r['summary']['coverage_by_horizon'][str(h)], {'CENSORED': 653 - n, 'COMPLETE': n})
        self.assertEqual(len({(x['opportunity_id'], x['horizon_hours']) for x in r['rows']}), 1959)

    def test_no_f1_direction_regime_or_execution_inference(self):
        r = report()
        for row in r['rows']:
            self.assertIsNone(row['direction'])
            self.assertIsNone(row['directional_metrics'])
            self.assertIsNone(row['regime'])
            self.assertEqual(row['original_modeled_finance_refs'], [])
            self.assertEqual(row['f1_status'], 'MISSING_ORIGINAL_CAPTURE')
            self.assertFalse(any(k in row for k in ['pnl', 'fees', 'fills', 'alpha', 'uplift']))
        self.assertEqual(r['base_status'], 'BASE_DESCRIPTIVE')
        self.assertTrue(r['shadow_status'].startswith('NOT_EVALUABLE'))

    def test_future_price_mutation_changes_only_posthoc_outcome(self):
        before = report()
        bars = deepcopy(self.bars)
        bars[22]['high'] = 150.
        after = report(bars=bars)
        for a, b in zip(before['rows'], after['rows']):
            self.assertEqual({k: v for k, v in a.items() if k != 'market_metrics'},
                             {k: v for k, v in b.items() if k != 'market_metrics'})
        self.assertNotEqual(before['rows'][0]['market_metrics'], after['rows'][0]['market_metrics'])

    def test_duplicate_or_mismatched_identity_rejected(self):
        with self.assertRaises(p.EvidenceError):
            report(self.pairs + self.pairs)
        pairs = deepcopy(self.pairs)
        pairs[0][1]['envelope_sha256'] = 'x' * 64
        with self.assertRaises(p.EvidenceError):
            report(pairs)

    def test_cutoff_lookahead_invalid_snapshot(self):
        with self.assertRaises(p.EvidenceError):
            replace(self.snap, decision_ms=self.snap.decision_cutoff_ms - 1)
        with self.assertRaises(p.EvidenceError):
            replace(self.snap, decision_cutoff_ms=self.snap.decision_cutoff_ms + 1)

    def joined(self):
        e, r = deepcopy(self.pairs[0])
        original = {**{k: r[k] for k in ['trial_id', 'opportunity_id', 'producer_event_id', 'envelope_sha256',
                    'run_manifest_sha256', 'strategy_digest', 'policy_id', 'assumptions_digest']},
                    'source_bytes_sha256': p.PINS['outer.zip'], 'state': 'APPLIED'}
        ack = {**original, 'state': 'ACKED'}
        return e, r, {e['producer_event_id']: original}, {e['producer_event_id']: ack}

    def test_original_vs_ack_copy_join_and_missing_receipt(self):
        e, r, original, ack = self.joined()
        self.assertEqual(len(p.join_original([e], [r], original, ack)), 1)
        with self.assertRaises(p.EvidenceError):
            p.join_original([e], [], original, ack)
        original[e['producer_event_id']]['state'] = 'ACKED'
        with self.assertRaises(p.EvidenceError):
            p.join_original([e], [r], original, ack)

    def test_forged_source_parent_and_receipt_digest_rejected(self):
        for kind in ['source', 'parent', 'receipt', 'feature']:
            e, r, original, ack = self.joined()
            if kind == 'source':
                original[e['producer_event_id']]['source_bytes_sha256'] = '0' * 64
            elif kind == 'parent':
                ack[e['producer_event_id']]['run_manifest_sha256'] = '0' * 64
            elif kind == 'receipt':
                r['effect_disposition'] = 'TRIGGERED'
            else:
                e['feature_policy_version'] = 'FORGED'
            with self.assertRaises(p.EvidenceError):
                p.join_original([e], [r], original, ack)

    def test_missing_journal_and_orphan_receipt_rejected(self):
        e, r, original, ack = self.joined()
        with self.assertRaises(p.EvidenceError):
            p.join_original([e], [r], original, {})
        with self.assertRaises(p.EvidenceError):
            p.join_original([e], [r, r], original, ack)

    def test_finance_refs_never_fabricated_for_no_signal(self):
        self.assertIsNone(p.validate_finance_refs(self.pairs, []))
        pairs = deepcopy(self.pairs)
        pairs[0][1]['ordered_financial_event_ids'] = ['fake']
        pairs[0][1]['ordered_financial_payload_hashes'] = ['0' * 64]
        with self.assertRaises(p.EvidenceError):
            p.validate_finance_refs(pairs, [])

    def test_financial_orphan_and_payload_tamper_rejected(self):
        f = {'event_id': 'orphan', 'opportunity_id': 'other'}
        f['payload_hash'] = p.content_hash(f)
        with self.assertRaises(p.EvidenceError):
            p.validate_finance_refs(self.pairs, [f])
        f['opportunity_id'] = 'changed'
        with self.assertRaises(p.EvidenceError):
            p.validate_finance_refs(self.pairs, [f])

    def test_missing_original_package_is_blocker_not_fake_report(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                p.load_original(Path(d) / 'absent.zip')

    def test_unsupported_horizon_rejected(self):
        with self.assertRaises(p.EvidenceError):
            self.window(horizon=123)

    def test_package_drift_and_malformed_json_fail_closed(self):
        with self.assertRaises(p.EvidenceError):
            p.checked_package(b'NOT_ORIGINAL')
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}']:
            with self.assertRaises(p.EvidenceError):
                p.parse(raw)

    def test_zip_duplicate_and_path_escape_rejected_without_extraction(self):
        for names in [['../escape'], ['same', 'same']]:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w') as z:
                for n in names:
                    z.writestr(n, '{}')
            with self.assertRaises(p.EvidenceError):
                p.zip_members(buf.getvalue())

    def test_deterministic_bytes_immutable_outputs_no_input_changes(self):
        a, b = report(), report()
        self.assertEqual(p.encode(a), p.encode(b))
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'result'
            before = p.encode(self.pairs)
            hashes = p.write_outputs(path, a, self.pairs, self.bars)
            self.assertEqual(p.hash_bytes((path / 'result.json').read_bytes()), hashes['result.json'])
            with self.assertRaises(p.EvidenceError):
                p.write_outputs(path, b, self.pairs, self.bars)
            self.assertEqual(before, p.encode(self.pairs))

    def test_no_source_network_or_strategy_replay_imports(self):
        import ast
        tree = ast.parse(Path(p.__file__).read_text())
        imports = [n.module or '' for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any(s in n for n in imports for s in ['f1f2_opportunities', 'f3_fill_model',
                                                             'f4_ledger', 'requests', 'websocket']))
        with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')):
            self.assertEqual(report()['summary']['opportunities'], 1)


if __name__ == '__main__':
    unittest.main()
