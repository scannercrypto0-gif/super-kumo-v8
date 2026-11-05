"""Scanner E original-history fail-closed contract tests, no new ZIP fixture.

Positive historical receipt consumption uses Core's real generated TEST_ONLY
cohort ONLY to assert refusal; it must not be promoted to original-market.
Original market provenance remains conditional on actual Core-provided evidence.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from research_wp_r0.aql_core_d_permitted_cohort_v1 import create_permitted_synthetic_cohort
from tools.scanner_strategy_e.historical_core_screening import (
    screen_historical_core_query,
)

class ScannerEHistoricalBoundaries(unittest.TestCase):
    def setUp(self):
        t=TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)/"core"
        self.vault=Path(t.name)/"vault"
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.actions={
            (x["payload"]["strategy_id"],x["payload"]["strategy_version"]):
            {"action":"APPROVE_TEST_ONLY","governance_policy_id":"SCANNER_E_FIXTURE",
             "approver_id":"E_FIXTURE","approval_nonce":x["payload"]["strategy_id"]}
            for x in self.work
        }

    def call(self, **inputs):
        d={"warehouse":None,"native_price_query":None,"local_query":None,
           "identity_map":None,"work_specs":self.work,
           "governance_actions":self.actions}
        d.update(inputs)
        return screen_historical_core_query(self.root,**d)

    def test_missing_genuine_original_source_emits_explicit_source_wait(self):
        a=self.call()
        self.assertEqual(Frozen.restore(a).data["reason"],
                         "WAIT_SOURCE_PROVENANCE_NOT_CONNECTED")
        self.assertEqual(Frozen.restore(a).data["strategy_secretary_state"],
                         "NOT_ENQUEUED")
        self.assertIsNone(Frozen.restore(a).data["factory_consumer_ack"])
        self.assertEqual(Frozen.restore(a).data["trading_authority"],"NONE")
        self.assertEqual(a,self.call())

    def test_core_d_synthetic_cohort_denied_as_original_history(self):
        c=create_permitted_synthetic_cohort(self.root,self.vault,self.work)
        d=dict(warehouse=c["warehouse"],native_price_query=c["native"],
               local_query=c["local"],identity_map=c["mapping"])
        with self.assertRaises(ValueError):
            self.call(**d)
        # No writes to Core Secretary/Factory can occur from Scanner E.
        self.assertFalse((self.root/"scanner-e-strategy-secretary.sqlite").exists())

    def test_corrupted_core_query_and_resealed_false_pit_denied(self):
        c=create_permitted_synthetic_cohort(self.root,self.vault,self.work)
        d=dict(warehouse=c["warehouse"],native_price_query=c["native"],
               local_query=c["local"],identity_map=c["mapping"])
        local=copy.deepcopy(c["local"])
        local["query_sha256"]="f"*64
        with self.assertRaises(ValueError):
            self.call(**{**d,"local_query":local})
        warehouse=copy.deepcopy(c["warehouse"])
        warehouse["test_only"]=False
        warehouse["receipt_sha256"]="f"*64
        with self.assertRaises(ValueError):
            self.call(**{**d,"warehouse":warehouse})

    def test_frozen_work235_symbol_and_no_historical_selected_route(self):
        # The only pre-existing authenticated Core original-format fixture is
        # BTCUSDT; frozen Work235 permits AAA..EEE, never magic BTC approval.
        for w in self.work:
            self.assertNotIn("BTCUSDT",
                w["payload"]["dna"]["payload"]["scanner_profile"]["allowed_symbols"]
                if "payload" in w["payload"]["dna"] else
                w["payload"]["dna"]["dna"]["scanner_profile"]["allowed_symbols"])
        result=Frozen.restore(self.call()).data
        self.assertEqual(result["decision"],"WAIT")
        self.assertNotIn("strategy_route_requests",result)
        self.assertNotIn("discoverer",result)

if __name__=="__main__":
    unittest.main()
