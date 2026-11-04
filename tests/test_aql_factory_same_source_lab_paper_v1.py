"""Factory #254 final-batch adapter tests on clearly synthetic Core envelopes.

The genuine original-source Core strategy receipt is NOT delivered yet.
No fake original run or operational Scanner SELECTED is asserted here.
"""
import copy
import unittest

from research_wp_r0.aql_factory_authentic_research_admission import _digest
from research_wp_r0.aql_factory_unified_backbone_v1 import freeze
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import (
    LabHandoffError, admit_core_lab_calculation, isolate_test_only_paper_decision,
)
from test_aql_factory_historical_rule_projection import definition


def source_and_core():
    source = freeze({
        "schema": "aql.factory.unified-custody-source.v1",
        "dataset_id": "SYNTHETIC_LAB_15M", "version":1,
        "source_bytes_sha256":"a"*64, "manifest_integrity_sha256":"b"*64,
        "core_253_warehouse_receipt_sha256":"c"*64,
        "core_price_query_sha256":"d"*64,
        "core_253_warehouse_query_sha256":"e"*64,
        "cutoff_ms":1793775600000,
        "coverage":"COMPLETE","missing_bar_opens":[],
        "bar_count_available":24,"bar_count_required":24,
        "raw_warehouse_query":"CONNECTED_PINNED_CORE_253_RAW_WAREHOUSE",
        "core_query_consumer":"CONNECTED_READ_ONLY_CORE_CUSTODY",
        "source_eligible_for_historical_pit":False,
        "holdout":"SEALED_UNOPENED","trading_authority":"NONE",
    })
    definition_obj=definition()
    rows=[{"bar_open_ms":900000*(1000+i),
           "state":("ENTRY_TRIGGERED" if i==4 else
                    "EXIT_TRIGGERED" if i==10 else
                    "UNKNOWN" if i<3 else "NO_SIGNAL"),
           "indicator_ready":i>=3} for i in range(23)]
    counts={s:sum(row["state"]==s for row in rows) for s in
            ("ENTRY_TRIGGERED","EXIT_TRIGGERED","NO_SIGNAL","UNKNOWN")}
    attempt=_digest({
        "dataset_id":source["dataset_id"],
        "source_sha256":source["source_bytes_sha256"],
        "strategy_digest":definition_obj["digest"],
        "cutoff_ms":source["cutoff_ms"],
        "research_lane":"OFFLINE_LAB_TEST_STRATEGY",
    })
    core={
        "schema":"aql.core.offline-lab-test-strategy.v1",
        "research_lane":"OFFLINE_LAB_TEST_STRATEGY",
        "evidence_class":"RETROSPECTIVE_NON_PIT",
        "test_only":True,
        "operational_scanner_status":"UNKNOWN",
        "historical_known_at_ms":None,
        "historical_pit":"NOT_ATTESTED",
        "scientific_result":"INSUFFICIENT_EVIDENCE",
        "trading_authority":"NONE",
        "real_paper_activation":"DISABLED",
        "holdout":"SEALED_UNOPENED",
        "dataset_id":source["dataset_id"],
        "version":source["version"],
        "source_zip_sha256":source["source_bytes_sha256"],
        "manifest_integrity_sha256":source["manifest_integrity_sha256"],
        "warehouse_receipt_sha256":source["core_253_warehouse_receipt_sha256"],
        "core_price_query_sha256":source["core_price_query_sha256"],
        "core_253_query_sha256":source["core_253_warehouse_query_sha256"],
        "decision_cutoff_ms":source["cutoff_ms"],
        "strategy_definition":definition_obj,
        "strategy_digest":definition_obj["digest"],
        "strategy_id":definition_obj["definition"]["strategy_id"],
        "strategy_version":definition_obj["definition"]["strategy_version"],
        "bar_count":24,"width_ms":900000,"source_first_bar_open_ms":900000*1000,
        "decisions":rows,"decision_slots":23,"decision_counts":counts,
        "attempt_id":attempt,"attempt_denominator":1,
        "independent_market_opportunity_denominator":None,
        "base_shadow_results":None,
    }
    return source,freeze(core,"evaluation_sha256")


class SameSourceLabPaperTests(unittest.TestCase):
    def test_one_real_contract_shape_but_synthetic_fixture_decisions_replay(self):
        source,core=source_and_core()
        lab=admit_core_lab_calculation(source,core)
        assert lab["decision_slots"]==23
        assert lab["decision_counts"]["UNKNOWN"]==3
        assert lab["attempt_denominator"]==1
        assert lab["source_zip_sha256"]==source["source_bytes_sha256"]
        assert lab["operational_scanner_status"]=="UNKNOWN"
        assert lab["historical_known_at_ms"] is None
        dec=isolate_test_only_paper_decision(lab)
        assert dec["decision"]=="REJECT"
        assert dec["main_paper_intent_interface"]["status"]=="declined"
        assert dec["paper_positions"]==dec["paper_position_events"]==dec["orders_created"]==0
        assert dec["work235_actual_route"]=="NOT_CONNECTED_15M_UNSUPPORTED"
        assert dec==isolate_test_only_paper_decision(lab)

    def test_wait_when_no_signal_but_real_computation_required(self):
        source,core=source_and_core()
        packet={k:copy.deepcopy(v) for k,v in core.items()
                if k!="evaluation_sha256"}
        for row in packet["decisions"]:
            if row["state"] in ("ENTRY_TRIGGERED","EXIT_TRIGGERED"):
                row["state"]="NO_SIGNAL"
        packet["decision_counts"]={
            s:sum(row["state"]==s for row in packet["decisions"])
            for s in ("ENTRY_TRIGGERED","EXIT_TRIGGERED","NO_SIGNAL","UNKNOWN")}
        lab=admit_core_lab_calculation(source,freeze(packet,"evaluation_sha256"))
        dec=isolate_test_only_paper_decision(lab)
        assert dec["decision"]=="WAIT"
        assert dec["main_paper_intent_interface"] is None
        assert dec["orders_created"]==0

    def test_source_and_calculation_integrity_adversarial(self):
        faults={
            "source_sha":lambda x:x.update(source_zip_sha256="0"*64),
            "query_sha":lambda x:x.update(core_253_query_sha256="0"*64),
            "warehouse_sha":lambda x:x.update(warehouse_receipt_sha256="0"*64),
            "version":lambda x:x.update(version=2),
            "cutoff":lambda x:x.update(decision_cutoff_ms=1),
            "duplicate_grid":lambda x:x["decisions"][10].update(
                bar_open_ms=x["decisions"][9]["bar_open_ms"]),
            "unknown_status":lambda x:x.update(operational_scanner_status="SELECTED"),
            "pit":lambda x:x.update(historical_pit="ATTESTED"),
            "policy":lambda x:x.update(real_paper_activation="ACTIVATED"),
            "scope":lambda x:x.update(width_ms=1800000),
            "missing_bar":lambda x:x["decisions"].pop(),
            "unbounded":lambda x:x.update(attempt_denominator=53),
            "fake_universe":lambda x:x.update(
                independent_market_opportunity_denominator=10),
            "census":lambda x:x["decision_counts"].update(ENTRY_TRIGGERED=99),
            "strategy":lambda x:x.update(strategy_digest="0"*64),
            "future_window":lambda x:x.update(
                source_first_bar_open_ms=900000*999),
            "signal_unknown":lambda x:x["decisions"][4].update(
                indicator_ready=False),
        }
        for name,mutate in faults.items():
            with self.subTest(name=name):
                source,receipt=source_and_core()
                packet=copy.deepcopy({k:v for k,v in receipt.items()
                                     if k!="evaluation_sha256"})
                mutate(packet)
                with self.assertRaises(LabHandoffError):
                    admit_core_lab_calculation(source,freeze(
                        packet,"evaluation_sha256"))

    def test_tampered_seal_and_partial_original_source_rejected(self):
        source,core=source_and_core()
        core["decisions"][0]["state"]="ENTRY_TRIGGERED"
        with self.assertRaises(LabHandoffError):
            admit_core_lab_calculation(source,core)
        source,core=source_and_core()
        src={k:v for k,v in source.items() if k!="artifact_sha256"}
        src["raw_warehouse_query"]="CONNECTED_CORE_253_STAGE_ONLY_RAW_VAULT_MISSING"
        with self.assertRaises(LabHandoffError):
            admit_core_lab_calculation(freeze(src),core)

    def test_policy_tamper_and_independent_unknown(self):
        source,core=source_and_core()
        lab=admit_core_lab_calculation(source,core)
        with self.assertRaises(LabHandoffError):
            isolate_test_only_paper_decision(lab,"ACCEPT_ALL")
        fake={k:v for k,v in lab.items() if k!="artifact_sha256"}
        fake["operational_scanner_status"]="SELECTED"
        with self.assertRaises(LabHandoffError):
            isolate_test_only_paper_decision(freeze(fake))


if __name__=="__main__":
    unittest.main()
