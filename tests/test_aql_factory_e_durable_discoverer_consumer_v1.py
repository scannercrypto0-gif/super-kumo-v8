"""Factory E durable Discoverer checkpoint → local results store integration."""
import copy
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_e_durable_discoverer_consumer_v1 import (
    accept_durable_discoverer_e_research,
)
from research_wp_r0.aql_factory_e_research_results_store_v1 import (
    read_experiment,ResultsStoreError,
)
from tools.strategy_discoverer_offline.durable_checkpoint_e import DurableDiscovererCheckpoint
from tools.strategy_discoverer_offline.tests.test_package_e_membership import setup_case,admission

class FactoryEDurableDiscovererTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.db=self.root/"factory.sqlite"
        self.durable_path=self.root/"discoverer.sqlite"
        self.case=setup_case()
        _,self.decision,self.intake,self.membership=admission(self.case)
        self.durable=DurableDiscovererCheckpoint(self.durable_path)
        self.checkpoint=self.durable.append_ledger(self.case[2].to_dict_list())

    def consume(self,**changes):
        args=dict(
            discoverer_checkpoint_path=self.durable_path,
            ledger_checkpoint_sha256=self.checkpoint,
            package=self.case[1],evidence=self.case[0],
            receipt=self.case[5],intake=self.intake,
            handoff_decision=self.decision,membership=self.membership,
            experiment_id="DISC-E-DURABLE-1",store_path=self.db,
            code_sha256="1"*64,environment_sha256="2"*64,
            config_sha256="3"*64,core_source_sha256="4"*64,
            core_245_query_sha256="5"*64,core_253_query_sha256="6"*64)
        args.update(changes)
        return accept_durable_discoverer_e_research(**args)

    def test_fresh_process_custody_readback_and_replay(self):
        a=self.consume()
        b=self.consume()
        self.assertEqual(a,b)
        self.assertEqual(a["discoverer_checkpoint_sha256"],self.checkpoint)
        self.assertEqual(a["lab"],"NOT_EVALUATED")
        saved=read_experiment(self.db,"DISC-E-DURABLE-1")
        self.assertEqual(saved["attempt_states"]["SELECTED"],1)
        self.assertIsNone(saved["paper_receipt_sha256"])

    def test_swapped_checkpoint_sha_denied(self):
        with self.assertRaises(ResultsStoreError):
            self.consume(ledger_checkpoint_sha256="f"*64)

    def test_replaced_stored_ledger_denied(self):
        import sqlite3
        with sqlite3.connect(self.durable_path) as conn:
            conn.execute("UPDATE ledger_checkpoints SET checkpoint_sha=?",
                         ("f"*64,))
        # Owner's signed checkpoint SHA chain must remain intact.
        with self.assertRaises((ValueError,ResultsStoreError)):
            self.consume()

    def test_missing_checkpoint_path_does_not_promote(self):
        with self.assertRaises((ValueError,ResultsStoreError)):
            self.consume(discoverer_checkpoint_path=self.root/"unavailable.sqlite")

if __name__=="__main__":
    unittest.main()
