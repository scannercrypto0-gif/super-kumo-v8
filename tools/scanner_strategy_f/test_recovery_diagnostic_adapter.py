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


if __name__=="__main__":
    unittest.main()
