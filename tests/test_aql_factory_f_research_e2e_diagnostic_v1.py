"""Factory diagnostic stays distinct from F5 and never manufactures trust."""
import copy
import tempfile
import unittest
from pathlib import Path
from research_wp_r0.aql_factory_f_research_e2e_diagnostic_v1 import (
    run_diagnostic,validate_diagnostic_input,ResultsStoreError,SCHEMA
)
from research_wp_r0.aql_factory_e_research_results_store_v1 import digest


class ResearchDiagnosticSafetyTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db=Path(tmp.name)/"diagnostic.sqlite"

    @staticmethod
    def packet():
        return {"schema":SCHEMA,"sha256":"f"*64}

    def test_missing_private_input_blocks_without_store_write(self):
        with self.assertRaises(ResultsStoreError):
            run_diagnostic(self.packet(),self.db)
        self.assertFalse(self.db.exists())

    def test_reseal_does_not_grant_execution_or_signed_f5(self):
        packet=self.packet()
        packet["sha256"]=digest({"schema":SCHEMA})
        with self.assertRaises(ResultsStoreError):
            run_diagnostic(packet,self.db)
        self.assertFalse(self.db.exists())

    def test_forged_promotion_does_not_create_store(self):
        packet=self.packet()
        packet["factory_consumer_ack_sha256"]="a"*64
        packet["sha256"]=digest({k:v for k,v in packet.items() if k!="sha256"})
        with self.assertRaises(ResultsStoreError):
            validate_diagnostic_input(packet)
        self.assertFalse(self.db.exists())

    def test_future_source_or_unknown_cohort_rejected(self):
        packet=self.packet()
        packet["attempts"]=[]
        packet["sha256"]=digest({k:v for k,v in packet.items() if k!="sha256"})
        with self.assertRaises(ResultsStoreError):
            validate_diagnostic_input(packet)
        self.assertFalse(self.db.exists())

if __name__=="__main__":
    unittest.main()
