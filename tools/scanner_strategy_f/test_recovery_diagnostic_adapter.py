"""F2_RECOVERY_EVIDENCE diagnostic, no F2 report or signed F5 alias.

All unit data are synthetic contract fixtures; never simulate original
owner-private E: source or claim signed policy approval.
"""
from __future__ import annotations
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.strategy_service_offline.run import FIXTURES
from tools.strategy_service_offline.common import Frozen
from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from tools.scanner_strategy_f.frozen_diagnostic_contracts import (
    identify_frozen_work235_contracts,load_frozen_work235_contracts,FROZEN,
)
from tools.scanner_strategy_f.recovery_diagnostic_adapter import (
    diagnostic_from_verified_recovery,
    EXPECTED_RECOVERY,ADMITTED,
)


class TestRecoveryDiagnostic(unittest.TestCase):
    def setUp(self):
        self.original=json.loads((FIXTURES/"strategies.json").read_text())

    def test_actual_frozen_work235_ast_identities_and_draft_not_approval(self):
        x=identify_frozen_work235_contracts(self.original)
        y=load_frozen_work235_contracts(FIXTURES/"strategies.json")
        self.assertEqual(x,y)
        self.assertEqual(set(x["strategy_identities"]),set(FROZEN))
        self.assertEqual(x["policy_approval_status"],"PENDING_INDEPENDENT_OWNER")
        self.assertEqual(x["source_recovery_status"],
                         "SEPARATE_OWNER_LOCAL_DIAGNOSTIC_ONLY")
        self.assertEqual(x["original_f2_report_status"],"NOT_RECONSTRUCTED")
        self.assertEqual(x["signed_f5_status"],"NOT_APPROVED")
        self.assertEqual(x["policy_draft"]["payload"]["policy_version"],
                         "btc-spot-15m-retrospective-non-pit-v1")
        self.assertIsNone(x["policy_draft"]["payload"][
                          "independent_owner_approval_receipt_sha256"])

    def test_swapped_frozen_ast_dna_or_source_is_rejected(self):
        for name,value in (
            ("scope","RESEARCH_APPROVED"),
            ("market","BINANCE"),
            ("paper_approval","GRANTED"),
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                changed=copy.deepcopy(self.original)
                changed[0]["payload"][name]=value
                changed[0]=Frozen.build(changed[0]["payload"]).receipt()
                identify_frozen_work235_contracts(changed)
        changed=copy.deepcopy(self.original)
        changed[0]["payload"]["definition"]["digest"]="f"*64
        changed[0]=Frozen.build(changed[0]["payload"]).receipt()
        with self.assertRaises(ValueError):
            identify_frozen_work235_contracts(changed)

    def test_missing_or_fake_recovery_input_rejected_before_any_replay(self):
        cases=[
            {},
            {m:{"receipt":{}} for m in ADMITTED},
            {m:{"receipt":{"owner_f2_report_pin_verified":True}} for m in ADMITTED},
        ]
        for records in cases:
            with self.subTest(records=len(records)),self.assertRaises(ValueError):
                diagnostic_from_verified_recovery(
                    warehouse_root="/missing",
                    verified_recovery_readbacks=records,
                    recovery_file_sha256=EXPECTED_RECOVERY,
                    work_specs=self.original)

    def test_recovery_sha_is_not_original_f2_alias(self):
        with self.assertRaises(ValueError):
            diagnostic_from_verified_recovery(
                warehouse_root="/missing",
                verified_recovery_readbacks={},
                recovery_file_sha256=
                    "daf1208bf824e58040858a817c709f7943c19668dc23ce3fd3b0368e01156f40",
                work_specs=self.original)


    def test_core_v1_receipt_contract_and_immutable_query_replay(self):
        """Core #275 actual receipt field names; synthetic-only contract."""
        from tools.scanner_strategy_f import recovery_diagnostic_adapter as adapter
        from tools.scanner_strategy_f.research_e2e_diagnostic import _month_ms
        from unittest.mock import call
        rows={}
        queries={}
        for month in ADMITTED:
            start,end=_month_ms(month)
            count=(end-start)//900000
            bars=[{"bar_open_ms":start,"bar_close_ms":start+899999,
                   "bar_checksum":"a"*64}]*count
            native=[{"bar_open_ms":start,"bar_close_ms":start+899999,
                     "checksum":"a"*64}]*count
            q={"query_sha256":"b"*64,"bars":bars,
               "available_bar_count":count,
               "source_bytes_sha256":"c"*64,
               "manifest_integrity_sha256":"d"*64}
            body={"schema":"aql.core.f2-recovery-readonly-source.v1",
                  "month":month,"dataset_id":"BINANCE-SPOT-BTCUSDT-15M-"+month+"-F-v1",
                  "status":"SOURCE_BACKED_RECOVERY_READBACK_ONLY",
                  "recovery_file_sha256":EXPECTED_RECOVERY,
                  "opaque_recovery_file_pin_verified":True,
                  "original_f2_report_sha256":None,
                  "historical_pit":"NOT_ATTESTED",
                  "source_ack_sha256":None,"strategy_approval_sha256":None,
                  "factory_consumer_ack_sha256":None,
                  "secretary_state":"NOT_ENQUEUED","trading_authority":"NONE",
                  "bar_count":count,"start_ms":start,"end_exclusive_ms":end,
                  "decision_cutoff_ms":end+1000,
                  "source_zip_sha256":"c"*64,
                  "manifest_integrity_sha256":"d"*64,
                  "core253_local_query_sha256":"b"*64,
                  "core245_native_query_sha256":"e"*64,
                  "dual_map_sha256":"f"*64,
                  "warehouse_receipt_sha256":"1"*64,
                  "no_write_tree_fingerprint_sha256":"2"*64}
            rows[month]={"receipt":{**body,"receipt_sha256":digest(body)},
                         "native_bars":native,"local_bars":bars}
            queries[month]=q
        # No positive owner-data claim: the evaluator is a contract-only stub.
        fake=Frozen.build({
            "decision":"DIAGNOSTIC_ONLY_NOT_F5","selected":0,
            "native15m_month_bars":29376,"diagnostic_evaluated_attempts":20,
            "unknown_feb_aug_attempts":4,"source_ack_sha256":None,
            "strategy_approval_sha256":None,"factory_consumer_ack_sha256":None,
            "trading_authority":"NONE",
        }).receipt()
        with patch.object(adapter,"query_local",side_effect=list(queries.values())) as replay, \
             patch.object(adapter,"diagnostic_original_cohort",return_value=fake):
            output=adapter.diagnostic_from_verified_recovery(
                warehouse_root="/unused",verified_recovery_readbacks=rows,
                recovery_file_sha256=EXPECTED_RECOVERY,work_specs=self.original)
        self.assertEqual(replay.call_count,10)
        self.assertTrue(all(c.kwargs["sqlite_immutable"] is True
                            for c in replay.call_args_list))
        self.assertEqual(output["payload"]["original_f2_report_sha256"],None)
        self.assertEqual(output["payload"]["selected"],0)
        for key,value in (("original_f2_report_sha256","f"*64),
                          ("status","F5_APPROVED"),
                          ("core253_local_query_sha256","0"*64)):
            altered=copy.deepcopy(rows)
            altered[ADMITTED[0]]["receipt"][key]=value
            altered[ADMITTED[0]]["receipt"]["receipt_sha256"]=digest({
                k:v for k,v in altered[ADMITTED[0]]["receipt"].items()
                if k!="receipt_sha256"})
            with self.subTest(key=key),patch.object(
                adapter,"query_local",side_effect=list(queries.values())
            ),self.assertRaises(ValueError):
                adapter.diagnostic_from_verified_recovery(
                    warehouse_root="/unused",
                    verified_recovery_readbacks=altered,
                    recovery_file_sha256=EXPECTED_RECOVERY,
                    work_specs=self.original)


if __name__=="__main__":
    unittest.main()
