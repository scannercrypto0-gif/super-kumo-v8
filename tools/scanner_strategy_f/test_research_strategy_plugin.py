"""Package H focused synthetic-only plug-in, causality and Factory boundaries."""
from __future__ import annotations

import copy
import json
import unittest
from unittest.mock import patch

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
from research_wp_r0.strategy_definition import StrategyDefinition
from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.run import FIXTURES
from tools.scanner_strategy_f import research_strategy_plugin as h


START=1735689600000  # Synthetic Jan 2025 range, NOT owner original 2024 F2.


def synthetic_query(n=64, missing_index=None):
    expected=list(range(START,START+n*900000,900000))
    bars=[]
    missing=[]
    for i,t in enumerate(expected):
        if i==missing_index:
            missing.append(t)
            continue
        px=98.0+(i%17)*0.3
        bars.append({
            "bar_open_ms":t,"bar_close_ms":t+899999,
            "open":px,"high":px+1,"low":px-1,"close":px,
            "volume":float(i),"bar_checksum":digest({"test_bar":i}),
            "observation_lower_bound_ms":START+n*900000,
            "historical_known_at_ms":None,
        })
    body={
        "schema":"aql.core.local-history-query.v1",
        "dataset_id":"TEST-ONLY-H-BTC-15M",
        "version":1,"source_bytes_sha256":"a"*64,
        "manifest_integrity_sha256":"b"*64,
        "start_ms":START,"end_exclusive_ms":START+n*900000,
        "decision_cutoff_ms":START+n*900000+1000,
        "coverage":"COMPLETE" if not missing else
                   "PARTIAL" if bars else "UNKNOWN",
        "missing_bar_opens":missing,
        "required_bar_count":n,"available_bar_count":len(bars),
        "bars":bars,"source_availability":"RETROSPECTIVE_NON_PIT",
        "historical_pit":"NOT_ATTESTED","universe":"NOT_ATTESTED",
    }
    return {**body,"query_sha256":digest(body)}


def reseal_query(q):
    q["query_sha256"]=digest({k:v for k,v in q.items()
                              if k!="query_sha256"})
    return q


class ResearchStrategyPlugin(unittest.TestCase):
    def setUp(self):
        self.work=json.loads((FIXTURES/"strategies.json").read_text())
        self.policy=h.research_signal_policy()
        self.original=synthetic_query()
        self.receipt=self.work[0]["payload"]["definition"]
        self.plugin=h.register_strategy_plugin(
            self.receipt,
            config_digest=self.work[0]["payload"]["config_digest"],
            source_spec_receipt=self.work[0])

    def evaluate(self, plugin=None, query=None, policy=None, replay=None):
        q=self.original if query is None else query
        with patch.object(h,"query_local",return_value=(
            q if replay is None else replay)) as local:
            out=h.evaluate_strategy_plugin(
                self.plugin if plugin is None else plugin,q,
                warehouse_root="/synthetic-unmounted",
                policy=self.policy if policy is None else policy)
        self.assertEqual(local.call_count,1)
        self.assertTrue(local.call_args.kwargs["sqlite_immutable"])
        self.assertFalse(local.call_args.kwargs["require_complete"])
        return out

    def test_frozen_two_and_distinct_manual_strategy_shared_adapter(self):
        loaded=[]
        for fixture in self.work:
            plug=h.register_strategy_plugin(
                fixture["payload"]["definition"],
                config_digest=fixture["payload"]["config_digest"],
                source_spec_receipt=fixture)
            out=self.evaluate(plugin=plug)
            body=h.verify_factory_signal_batch(out).data
            self.assertEqual(body["event_count"],64)
            self.assertEqual(body["expected_bar_count"],64)
            self.assertEqual(sum(body["signal_counts"].values()),64)
            self.assertEqual(body["economic_attestation"],"NOT_ATTESTED")
            self.assertFalse(body["cost_or_pnl_computed"])
            self.assertEqual(body["factory_interface"],
                             "SIGNAL_ONLY_NEXT_ELIGIBLE_OPEN_NO_FILLS")
            self.assertTrue(all(e["next_open_is_fill"] is False
                                for e in body["events"]))
            loaded.append(Frozen.restore(plug).sha256)

        changed=copy.deepcopy(self.receipt["definition"])
        changed["strategy_id"]="h_manual_distinct_test"
        changed["indicators"][0]["parameters"]["period"]=5
        changed["entry"]["right"]["value"]=99
        new=StrategyDefinition(changed,registry=IndicatorRegistryV2())
        manual=h.register_strategy_plugin(
            new.to_dict(),config_digest=h.manual_config_digest(new.to_dict()),
            origin="MANUAL")
        self.assertNotIn(Frozen.restore(manual).sha256,loaded)
        self.assertIsNone(Frozen.restore(manual).data["source_spec_sha256"])
        third=h.verify_factory_signal_batch(self.evaluate(plugin=manual))
        self.assertEqual(third.data["strategy_id"],"h_manual_distinct_test")
        self.assertEqual(third.data["event_count"],64)

    def test_replay_is_deterministic_and_causal_without_lookahead(self):
        first=self.evaluate()
        second=self.evaluate()
        self.assertEqual(first,second)
        a=h.verify_factory_signal_batch(first).data
        self.assertEqual([e["bar_open_ms"] for e in a["events"]],
                         list(range(START,START+64*900000,900000)))
        self.assertTrue(all(e["bar_close_ms"]<a["decision_cutoff_ms"]
                            and e["historical_known_at_ms"] is None
                            for e in a["events"]))
        future=synthetic_query(n=65)
        future["bars"][-1]["close"]=future["bars"][-1]["open"]+0.5
        future=reseal_query(future)
        b=h.verify_factory_signal_batch(
            self.evaluate(query=future)).data
        self.assertEqual([e["signal_state"] for e in a["events"]],
                         [e["signal_state"] for e in b["events"][:64]])

    def test_parameter_and_definition_hash_drift_rejected(self):
        altered=copy.deepcopy(self.plugin)
        altered["payload"]["config_digest"]="0"*64
        with self.assertRaises(ValueError):
            self.evaluate(plugin=altered)
        forged=Frozen.build(altered["payload"]).receipt()
        # Even a re-sealed Work235 config change must fail its frozen pin.
        with self.assertRaises(ValueError):
            self.evaluate(plugin=forged)
        altered=copy.deepcopy(self.plugin)
        altered["payload"]["definition_digest"]="0"*64
        forged=Frozen.build(altered["payload"]).receipt()
        with self.assertRaises(ValueError):
            self.evaluate(plugin=forged)
        changed=copy.deepcopy(self.receipt)
        changed["definition"]["indicators"][0]["parameters"]["period"]=50
        with self.assertRaises(ValueError):
            h.register_strategy_plugin(changed,config_digest="f"*64)

    def test_independent_policy_approval_and_trading_never_self_granted(self):
        for key,value in (
            ("independent_owner_approval_sha256","a"*64),
            ("historical_pit","ATTESTED"),
            ("trading_authority","LIVE"),
            ("holdout","OPEN"),
            ("economic_attestation","APPROVED"),
        ):
            with self.subTest(key=key):
                changed=copy.deepcopy(self.policy["payload"])
                changed[key]=value
                with self.assertRaises(ValueError):
                    self.evaluate(policy=Frozen.build(changed).receipt())
        with self.assertRaises(ValueError):
            h.register_strategy_plugin(self.receipt,
                config_digest="f"*64,origin="DISCOVERER_CANDIDATE")
        candidate=h.register_strategy_plugin(
            self.receipt,
            config_digest=self.work[0]["payload"]["config_digest"],
            source_spec_receipt=self.work[0],
            origin="DISCOVERER_CANDIDATE",candidate_sha256="a"*64)
        self.assertEqual(Frozen.restore(candidate).data["policy_status"],
                         "RESEARCH_ONLY_NO_INDEPENDENT_APPROVAL")

    def test_closed_envelopes_reject_extra_fields_and_forged_candidate(self):
        bad=copy.deepcopy(self.plugin["payload"])
        bad["private_data_passthrough"]="should-never-cross-boundary"
        with self.assertRaises(ValueError):
            self.evaluate(plugin=Frozen.build(bad).receipt())
        bad=copy.deepcopy(self.plugin["payload"])
        bad["input_origin"]="DISCOVERER_CANDIDATE"
        with self.assertRaises(ValueError):
            self.evaluate(plugin=Frozen.build(bad).receipt())
        batch=self.evaluate()
        bad=copy.deepcopy(batch["payload"])
        bad["f5_signed_approval_sha256"]="a"*64
        with self.assertRaises(ValueError):
            h.verify_factory_signal_batch(Frozen.build(bad).receipt())
        bad=copy.deepcopy(batch["payload"])
        bad["research_asof_basis"]="PIT_ATTESTED"
        with self.assertRaises(ValueError):
            h.verify_factory_signal_batch(Frozen.build(bad).receipt())
        bad=copy.deepcopy(batch["payload"])
        bad["events"][0]["private_price"]=100.0
        bad["events"][0]["event_sha256"]=digest({
            k:v for k,v in bad["events"][0].items()
            if k!="event_sha256"})
        with self.assertRaises(ValueError):
            h.verify_factory_signal_batch(Frozen.build(bad).receipt())

    def test_missing_bars_quarantined_and_not_miscounted_as_no_signal(self):
        partial=synthetic_query(missing_index=2)
        out=h.verify_factory_signal_batch(self.evaluate(query=partial)).data
        self.assertEqual(out["coverage"],"PARTIAL")
        self.assertEqual(out["missing_bar_count"],1)
        self.assertEqual(out["observed_bar_count"],63)
        self.assertEqual(out["signal_counts"]["UNKNOWN"],64)
        self.assertEqual(out["signal_counts"]["NO_SIGNAL"],0)
        self.assertEqual(out["quarantine"],"ALL_EVENTS_UNKNOWN_SOURCE_GAP")
        self.assertTrue(all(not e["source_observed"] for e in out["events"]))

    def test_absent_policy_and_receipts_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"H_POLICY_REQUIRED"):
            h.evaluate_strategy_plugin(
                self.plugin,self.original,warehouse_root="/synthetic",
                policy=None)
        with self.assertRaisesRegex(ValueError,"H_PLUGIN_RECEIPT_REQUIRED"):
            h.evaluate_strategy_plugin(
                None,self.original,warehouse_root="/synthetic",
                policy=self.policy)
        with self.assertRaisesRegex(ValueError,
                                    "H_FACTORY_BATCH_RECEIPT_REQUIRED"):
            h.verify_factory_signal_batch(None)
        owner_policy=h.research_signal_policy(
            source_class="OWNER_LOCAL_RECOVERY_DIAGNOSTIC")
        batch=self.evaluate(policy=owner_policy)
        self.assertEqual(batch["payload"]["source_class"],
                         "OWNER_LOCAL_RECOVERY_DIAGNOSTIC")
        self.assertEqual(batch["payload"]["trading_authority"],"NONE")

    def test_adversarial_grid_source_future_and_replay_rejected(self):
        for label,mutate in (
            ("duplicate",lambda q: q["bars"].__setitem__(1,
                                          dict(q["bars"][0]))),
            ("future",lambda q: q["bars"][0].__setitem__(
                "bar_close_ms",q["decision_cutoff_ms"])),
            ("no_pit",lambda q: q.__setitem__("historical_pit","ATTESTED")),
            ("bad_prices",lambda q: q["bars"][0].__setitem__("low",-1.0)),
            ("bad_cutoff",lambda q: q.__setitem__(
                "decision_cutoff_ms",q["start_ms"])),
            ("missing",lambda q: q["missing_bar_opens"].append(START)),
        ):
            q=copy.deepcopy(self.original)
            mutate(q)
            reseal_query(q)
            with self.subTest(label=label),self.assertRaises(ValueError):
                self.evaluate(query=q)
        forged=synthetic_query()
        forged["bars"][4]["close"]=forged["bars"][4]["open"]+0.5
        reseal_query(forged)
        with self.assertRaises(ValueError):
            self.evaluate(query=forged,replay=self.original)

    def test_factory_rejects_duplicates_event_seals_and_approval(self):
        original=self.evaluate()
        for key,value in (
            ("selected",True),
            ("source_ack_sha256","c"*64),
            ("cost_or_pnl_computed",True),
        ):
            bad=copy.deepcopy(original["payload"])
            bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):
                h.verify_factory_signal_batch(Frozen.build(bad).receipt())
        for change in ("duplicate","future","unsealed"):
            bad=copy.deepcopy(original["payload"])
            if change=="duplicate":
                bad["events"][1]=copy.deepcopy(bad["events"][0])
            elif change=="future":
                bad["events"][-1]["bar_close_ms"]=bad["decision_cutoff_ms"]
            else:
                bad["events"][0]["signal_state"]="ENTRY_SIGNAL"
            with self.subTest(change=change),self.assertRaises(ValueError):
                h.verify_factory_signal_batch(Frozen.build(bad).receipt())


if __name__=="__main__":
    unittest.main()
