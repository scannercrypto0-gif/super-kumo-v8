"""Bounded performance benchmark proves repeatable workload and fail-closed limits."""
import unittest
from tools.atlas_factory_e_bounded_perf import execute

class FactoryEPerformance(unittest.TestCase):
    def test_multi_strategy_symbol_denominator_and_resource_bound(self):
        result=execute(strategies=6,symbols=4,per_pair=4,
                       max_seconds=12.0,max_peak_mib=96.0)
        self.assertEqual(result["experiment_count"],24)
        self.assertEqual(result["attempts_count"],96)
        self.assertTrue(result["threshold_pass"])
        self.assertEqual(result["trading_authority"],"NONE")
        self.assertEqual(result["orders_created"],0)

    def test_deterministic_replay_canonical_document_set(self):
        a=execute(strategies=2,symbols=3,per_pair=3)
        b=execute(strategies=2,symbols=3,per_pair=3)
        self.assertEqual(a["document_set_sha256"],b["document_set_sha256"])
        self.assertEqual(a["attempts_count"],18)
        self.assertNotEqual(a["document_set_sha256"],"0"*64)

    def test_reject_unbounded_fixture_request(self):
        with self.assertRaisesRegex(ValueError,"invalid bounded"):
            execute(strategies=999)
        with self.assertRaisesRegex(ValueError,"invalid bounded"):
            execute(max_seconds=500)

if __name__=="__main__":
    unittest.main()
