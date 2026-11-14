"""H2 preflight authorization negatives: synthetic only, no source file access."""
from __future__ import annotations
import copy
import unittest
from tools.atlas_h2_readiness_preflight import assess,EXPECTED,SCHEMA


def valid():
    return {
        "schema":SCHEMA,
        "exact_heads":{**EXPECTED,"integration":"f"*40},
        "bounded_request":{
            "dataset_id":"BINANCE-SPOT-BTCUSDT-15M-2024-03-F-v1",
            "month":"2024-03","start_ms":0,"end_exclusive_ms":900000*4,
            "decision_cutoff_ms":900000*4,
            "strategy_definition_sha256":"a"*64,
        },
        "owner_permission":{
            "granted":True,"scope":"BOUNDED_ORIGINAL_HISTORY_READONLY",
            "authorization_reference":"SYNTHETIC-TEST-NOT-REAL-PERMISSION",
        },
        "owner_cost_policy":{
            "owner_authorized":True,"authorization_reference":"SYNTHETIC-TEST-COST",
            "market":"SPOT","direction":"LONG",
            "scenario_class":"OWNER_DECLARED_RESEARCH_SCENARIO",
            "costs":{"fee_entry_bps":"1","fee_exit_bps":"1",
                     "spread_entry_bps":"1","spread_exit_bps":"1",
                     "slippage_entry_bps":"1","slippage_exit_bps":"1",
                     "funding_bps_per_bar":"0"},
        },
        "source_provenance":{
            "source_rights_attested":True,"publisher_pit_attested":True,
            "source_receipt_sha256":"1"*64,
            "manifest_integrity_sha256":"2"*64,
            "core245_native_query_sha256":"3"*64,
            "core253_local_query_sha256":"4"*64,
        },
    }


class H2FailClosedReadiness(unittest.TestCase):
    def check(self,doc,status):
        result=assess(doc)
        self.assertEqual(result["status"],status)
        self.assertFalse(result["owner_private_data_accessed"])
        self.assertFalse(result["warehouse_written"])
        self.assertEqual(result["trading_authority"],"NONE")
        self.assertEqual(result["operation"],"READINESS_ONLY_NO_SOURCE_IO")

    def test_absent_source_permission_stops_first(self):
        req=valid()
        req["owner_permission"]={"granted":False}
        self.check(req,"WAIT_SOURCE_PERMISSION")

    def test_missing_and_zero_cost_block(self):
        for costs in (None,{**valid()["owner_cost_policy"]["costs"],
                             **{x:"0" for x in valid()["owner_cost_policy"]["costs"]}}):
            req=valid()
            if costs is None: req["owner_cost_policy"]={}
            else: req["owner_cost_policy"]["costs"]=costs
            self.check(req,"WAIT_COST_POLICY")

    def test_unapproved_nonzero_cost_denied(self):
        req=valid()
        req["owner_cost_policy"]["owner_authorized"]=False
        self.check(req,"WAIT_COST_POLICY")

    def test_missing_source_rights_or_pit_denied(self):
        for key in ("source_rights_attested","publisher_pit_attested"):
            req=valid()
            req["source_provenance"][key]=False
            self.check(req,"WAIT_PROVENANCE")

    def test_same_core_query_shas_denied(self):
        req=valid()
        req["source_provenance"]["core253_local_query_sha256"]="3"*64
        self.check(req,"WAIT_PROVENANCE")

    def test_changed_factory_head_denied(self):
        req=valid()
        req["exact_heads"]["factory"]="0"*40
        self.check(req,"BLOCKED_CONTRACT")

    def test_unbounded_or_future_range_denied(self):
        req=valid()
        req["bounded_request"]["end_exclusive_ms"]=900000*9000
        self.check(req,"BLOCKED_CONTRACT")

    def test_synthetic_all_fields_only_ready_not_history_pass(self):
        self.check(valid(),"READY_FOR_OWNER_AUTHORIZATION")
        self.assertNotIn("HISTORICAL_PASS",str(assess(valid())))

    def test_unknown_key_denied(self):
        req=copy.deepcopy(valid())
        req["original_source_path"]="E:\\private"
        self.check(req,"BLOCKED_CONTRACT")


if __name__=="__main__":
    unittest.main()
