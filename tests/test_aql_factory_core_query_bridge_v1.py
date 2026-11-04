"""Bundle B synthetic contract tests; never replay retained original Feb/Aug."""
import copy
import unittest

from research_wp_r0.aql_factory_unified_backbone_v1 import freeze
from research_wp_r0.aql_factory_same_source_lab_paper_v1 import LabHandoffError
from research_wp_r0.aql_factory_core_query_bridge_v1 import (
    bridge_core_query_identities, run_isolated_bundle_b,
)
from test_aql_factory_same_source_lab_paper_v1 import source_and_core


def fixture():
    source, core = source_and_core()
    s = {k: copy.deepcopy(v) for k,v in source.items()
         if k != "artifact_sha256"}
    # Native #245 and #253 query digests MUST be distinct.
    s["core_price_query_sha256"] = "f"*64
    source = freeze(s)
    native = freeze({
        "schema":"aql.core.historical-price-custody-query.v1",
        "dataset_id":s["dataset_id"], "version":s["version"],
        "source_bytes_sha256":s["source_bytes_sha256"],
        "manifest_integrity_sha256":s["manifest_integrity_sha256"],
        "decision_cutoff_ms":s["cutoff_ms"],
    }, "price_query_sha256")
    local = freeze({
        "schema":"aql.core.local-history-query.v1",
        "dataset_id":s["dataset_id"], "version":s["version"],
        "source_bytes_sha256":s["source_bytes_sha256"],
        "manifest_integrity_sha256":s["manifest_integrity_sha256"],
        "decision_cutoff_ms":s["cutoff_ms"],
        "coverage":"COMPLETE","missing_bar_opens":[],
        "available_bar_count":24,"required_bar_count":24,
    }, "query_sha256")
    s["core_price_query_sha256"] = native["price_query_sha256"]
    s["core_253_warehouse_query_sha256"] = local["query_sha256"]
    source=freeze(s)
    c={k:copy.deepcopy(v) for k,v in core.items()
       if k != "evaluation_sha256"}
    c["core_price_query_sha256"]=local["query_sha256"]
    c["core_253_query_sha256"]=local["query_sha256"]
    core=freeze(c,"evaluation_sha256")
    return source,native,local,core


class BundleBBridgeTests(unittest.TestCase):
    def test_bridge_retains_two_separate_sha_domains_and_replay(self):
        s,n,q,c=fixture()
        result=run_isolated_bundle_b(s,n,q,c)
        bridge=result["bridge"]
        self.assertNotEqual(bridge["core_245_price_query_sha256"],
                            bridge["core_253_query_local_sha256"])
        self.assertEqual(bridge["core_245_price_query_sha256"],
                         n["price_query_sha256"])
        self.assertEqual(result["adapted_source"]["core_price_query_sha256"],
                         q["query_sha256"])
        self.assertEqual(result["lab"]["core_lab_evaluation_sha256"],
                         c["evaluation_sha256"])
        self.assertEqual(result["paper"]["decision"],"REJECT")
        self.assertEqual(result["paper"]["orders_created"],0)
        self.assertEqual(result,run_isolated_bundle_b(s,n,q,c))

    def test_mismatched_parent_identity_and_resealed_tamper_fail_closed(self):
        faults=[
            ("native_source",1,"source_bytes_sha256","0"*64),
            ("native_version",1,"version",2),
            ("local_cutoff",2,"decision_cutoff_ms",1),
            ("local_source",2,"source_bytes_sha256","0"*64),
            ("local_coverage",2,"coverage","PARTIAL"),
            ("local_missing",2,"missing_bar_opens",[900000]),
            ("local_denominator",2,"available_bar_count",23),
            ("core_query",3,"core_253_query_sha256","0"*64),
            ("core_price_query",3,"core_price_query_sha256","0"*64),
            ("core_strategy_source",3,"source_zip_sha256","0"*64),
            ("core_strategy_version",3,"version",2),
            ("core_scanner",3,"operational_scanner_status","SELECTED"),
            ("core_trading",3,"trading_authority","PAPER"),
            ("core_width",3,"width_ms",1800000),
            ("core_cutoff",3,"decision_cutoff_ms",1),
            ("source_warehouse",0,"raw_warehouse_query","NOT_CONNECTED"),
            ("source_native_query",0,"core_price_query_sha256","0"*64),
            ("source_local_query",0,"core_253_warehouse_query_sha256","0"*64),
        ]
        seal_fields=("artifact_sha256","price_query_sha256",
                     "query_sha256","evaluation_sha256")
        for label,index,key,value in faults:
            with self.subTest(label=label):
                objs=list(fixture())
                packet={k:copy.deepcopy(v) for k,v in objs[index].items()
                        if k!=seal_fields[index]}
                packet[key]=value
                objs[index]=freeze(packet,seal_fields[index])
                with self.assertRaises((LabHandoffError,ValueError)):
                    run_isolated_bundle_b(*objs)

    def test_sha_seal_tamper_without_resealing(self):
        for index,key in [(0,"dataset_id"),(1,"version"),
                          (2,"coverage"),(3,"strategy_id")]:
            with self.subTest(index=index):
                objs=list(fixture())
                objs[index][key]="TAMPERED"
                with self.assertRaises((LabHandoffError,ValueError)):
                    run_isolated_bundle_b(*objs)


if __name__=="__main__":
    unittest.main()
