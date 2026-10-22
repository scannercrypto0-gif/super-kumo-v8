"""Twelve grouped Batch 01 checks, plus inherited unified research coverage."""
from dataclasses import asdict, replace
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research_wp_r0 import strategy_factory as sf
from research_wp_r0.durable_journal import DurableTrialJournal, JournalIntegrityError
from research_wp_r0.owner_checkpoints import export_checkpoint
from research_wp_r0.statistics import LabelWindow, holm, purged_forward_folds
from research_wp_r0.temporal_contract import TemporalOpportunity
from research_wp_r0.trial_holdout import Attempt, AttemptState, HoldoutEvent, TrialFamilyLedger

P = sf.Protocol.load()
E = P.spec["execution"]


def bars(*values):
    return tuple(sf.Bar(i, *v, "RANGE") for i, v in enumerate(values))


class Group01DeterministicGeneration(unittest.TestCase):
    def test_grid_is_complete_and_unique(self):
        cs = sf.candidates(P)
        self.assertEqual(len(cs), 12)
        self.assertEqual(len({c.candidate_id for c in cs}), 12)
        self.assertEqual(sf.candidates(sf.Protocol.load()), cs)

    def test_prefix_is_seeded_and_extension_invariant(self):
        self.assertEqual(sf.synthetic_prefix(P, 100), sf.synthetic_prefix(P, 150)[:100])


class Group02FamilyFreeze(unittest.TestCase):
    def test_nested_edits_cannot_mutate_frozen_bytes(self):
        before = P.digest
        edited = P.spec
        edited["execution"]["fee_per_side"] = 0
        edited["families"].clear()
        self.assertEqual(P.digest, before)
        self.assertEqual(len(sf.candidates(P)), 12)

    def test_cost_change_changes_family_identity(self):
        edited = P.spec
        edited["execution"]["fee_per_side"] *= 2
        changed = sf.Protocol(sf.canonical(edited))
        m = sf.temporal_manifest(P, sf.indices(P, "development"), "development")
        self.assertNotEqual(sf.frozen_family(P, m).digest, sf.frozen_family(changed, m).digest)


class Group03NoFutureLeakage(unittest.TestCase):
    def test_production_dispatch_passes_only_decision_prefix(self):
        rows = sf.synthetic_prefix(P,1152)
        expected = iter(sf.indices(P,"development"))
        def observe(candidate,prefix):
            i = next(expected)
            self.assertEqual(len(prefix),i+1)
            self.assertEqual(prefix[-1].index,i)
            return False
        with patch.object(sf,"signal",side_effect=observe):
            sf.records_for(sf.Candidate("momentum",8,0),rows,P,"development")

    def test_future_mutation_cannot_change_decision(self):
        rows = sf.synthetic_prefix(P, 100)
        changed = rows[:41] + tuple(replace(b, close=b.close*100) for b in rows[41:])
        for c in sf.candidates(P):
            self.assertEqual(sf.signal(c, rows[:41]), sf.signal(c, changed[:41]))

    def test_regime_truth_is_not_a_strategy_feature(self):
        rows = sf.synthetic_prefix(P, 50)
        for c in sf.candidates(P):
            self.assertEqual(sf.signal(c, rows), sf.signal(c, tuple(replace(b, regime="FAKE") for b in rows)))

    def test_final_value_received_late_is_rejected(self):
        t = sf.T
        with self.assertRaises(ValueError):
            TemporalOpportunity("x",t,t,t+timedelta(seconds=1),t+timedelta(minutes=10),
                                t+timedelta(minutes=10),t+timedelta(minutes=10),t+timedelta(minutes=10),"g")

    def test_entry_strictly_follows_decision(self):
        rows = sf.synthetic_prefix(P, 50)
        result = sf.execute(rows,20,True,E)
        self.assertGreater(sf.T+timedelta(minutes=result["entry_index"]),rows[20].available_at)


class Group04TemporalPurging(unittest.TestCase):
    def test_overlap_is_purged(self):
        windows = [LabelWindow(sf.T+timedelta(minutes=i),sf.T+timedelta(minutes=i+5)) for i in range(40)]
        folds = purged_forward_folds(windows, minimum_training=10, test_size=5)
        self.assertTrue(folds)
        for fold in folds:
            for i in fold.train_indices:
                self.assertLessEqual(windows[i].label_end_at, windows[fold.test_indices[0]].observation_at)

    def test_partition_windows_cannot_cross_boundaries(self):
        for partition,end in (("development",1152),("synthetic_validation",1536)):
            ids = sf.indices(P,partition)
            self.assertLess(ids[-1]+E["entry_ttl_bars"]+E["holding_bars"],end)
            if partition == "synthetic_validation":
                self.assertGreaterEqual(ids[0]-16,1152)


class Group05FeesAndSlippage(unittest.TestCase):
    def test_exact_two_sided_cost(self):
        cost = sf.execution_cost(100,110,E)
        s,f = E["slippage_per_side"],E["fee_per_side"]
        exact = (100*s+110*s+f*(100*(1+s)+110*(1-s)))/100
        self.assertAlmostEqual(cost,exact)
        self.assertGreater(cost,0)

    def test_higher_friction_cannot_improve_same_path(self):
        self.assertGreater(sf.execution_cost(100,99,dict(E,fee_per_side=.002)),sf.execution_cost(100,99,E))


class Group06NoFill(unittest.TestCase):
    def test_expiry_charges_no_trade_fee_and_never_fabricates_fill(self):
        rows = tuple(replace(b,entry_executable=False) for b in sf.synthetic_prefix(P,50))
        result = sf.execute(rows,20,True,E)
        self.assertEqual(result["state"],"NO_FILL_EXPIRED")
        self.assertIsNone(result["entry_index"])
        self.assertIsNone(result["net"])
        self.assertEqual(sf.metrics([result],12)["no_fill"],1)

    def test_no_signal_is_not_counted_as_failed_entry(self):
        result = sf.execute(sf.synthetic_prefix(P,50),20,False,E)
        m = sf.metrics([result],12)
        self.assertEqual((m["no_signal"],m["no_fill"],m["attempts"]),(1,0,0))


class Group07ExitRules(unittest.TestCase):
    def test_same_bar_stop_target_remains_ambiguous(self):
        rows = bars((100,100,100,100),(100,105,95,101),(100,100,100,100))
        r = sf.execute(rows,0,True,dict(E,holding_bars=1))
        self.assertEqual(r["state"],"AMBIGUOUS")
        self.assertIsNone(r["net"])
        self.assertLess(r["low_net"],r["high_net"])

    def test_gap_stop_uses_open_not_better_stop_price(self):
        rows = bars((100,100,100,100),(100,101,99,100),(95,96,94,95))
        r = sf.execute(rows,0,True,dict(E,holding_bars=2))
        self.assertEqual(r["state"],"GAP_STOP")
        self.assertAlmostEqual(r["gross"],-.05)

    def test_time_exit_and_intratrade_drawdown(self):
        rows = bars((100,100,100,100),(100,101,99,99),(99,100,98.5,99))
        r = sf.execute(rows,0,True,dict(E,holding_bars=2))
        self.assertEqual(r["state"],"TIME_EXIT")
        self.assertGreater(sf.max_drawdown([r]),.01)


class Group08Regimes(unittest.TestCase):
    def test_multiple_occurrences_and_off_target_labels(self):
        rows = sf.synthetic_prefix(P,1152)
        self.assertEqual({r.regime for r in rows},{"UP","DOWN","RANGE","VOLATILE"})
        self.assertGreater(len({b.index//64 for b in rows if b.regime=="UP"}),1)
        self.assertEqual(P.spec["families"][2]["target_regimes"],["RANGE"])


class Group09BaselinesAndRanking(unittest.TestCase):
    def test_random_baseline_reproducible(self):
        rows = sf.synthetic_prefix(P,100)
        c = sf.Candidate("random_baseline",8,0)
        values = [sf.signal(c,rows[:i+1]) for i in range(20,90)]
        self.assertEqual(values,[sf.signal(c,rows[:i+1]) for i in range(20,90)])
        self.assertIn(True,values)
        self.assertIn(False,values)

    def test_ranking_uses_adequacy_before_profit_and_ignores_validation(self):
        def row(name,adequate,pnl):
            return {"candidate_id":name,"development":{"sample_adequate_for_descriptive_screen":adequate,
              "net_bounds_sum":[pnl,pnl],"opportunities":20,
              "close_marked_lower_scenario_drawdown_initial_equity":.1},"synthetic_validation":{"pnl":1e9}}
        rows = [row("a",False,100),row("b",True,1)]
        self.assertEqual(sf.rank_development(rows),["b","a"])
        rows[0]["synthetic_validation"]["pnl"] = -1e9
        self.assertEqual(sf.rank_development(rows),["b","a"])

    def test_full_opportunity_comparison_detects_entry_selection_difference(self):
        rows = sf.synthetic_prefix(P,1152)
        selected = sf.records_for(sf.Candidate("momentum",16,.004),rows,P,"development")
        baseline = sf.records_for(sf.Candidate("random_baseline",8,0),rows,P,"development")
        manifest = sf.temporal_manifest(P,sf.indices(P,"development"),"development")
        report = sf.compare(selected,baseline,manifest,P)
        expected = (sum(r["low_net"] for r in selected)-sum(r["low_net"] for r in baseline))/len(selected)
        self.assertAlmostEqual(report["opportunity_accounting"]["realized_policy_net_lift"],expected)
        self.assertNotEqual(report["opportunity_accounting"]["realized_policy_net_lift"],0.)
        self.assertIsNotNone(report["opportunity_block_interval"])
        self.assertIsNone(report["opportunity_accounting"]["sector_interval"])


class Group10UncertaintyAndMultiplicity(unittest.TestCase):
    def test_ambiguous_pair_never_becomes_zero_in_population_bootstrap(self):
        rows = sf.synthetic_prefix(P,1152)
        rs = sf.records_for(sf.Candidate("momentum",8,0),rows,P,"development")
        baseline = [dict(r) for r in rs]
        rs[0] = dict(rs[0],state="AMBIGUOUS",net=None,gross=None,cost=None,low_net=-.02,high_net=.03)
        manifest = sf.temporal_manifest(P,sf.indices(P,"development"),"development")
        report = sf.compare(rs,baseline,manifest,P)
        self.assertIsNone(report["opportunity_block_interval"])
        self.assertEqual(report["opportunity_accounting"]["ambiguous_pairs"],1)

    def test_all_twelve_trials_in_one_correction(self):
        self.assertEqual(len(holm([1.]*len(sf.candidates(P)))),12)
        self.assertEqual(holm([.001,.02,.2]),(.003,.04,.2))

    def test_bootstrap_uses_existing_engine_and_preserves_ambiguity(self):
        rows = sf.synthetic_prefix(P,1152)
        rs = sf.records_for(sf.Candidate("momentum",8,0),rows,P,"development")
        manifest = sf.temporal_manifest(P,sf.indices(P,"development"),"development")
        report = sf.compare(rs,rs,manifest,P)
        self.assertEqual(report["paired_net_lift"],0.)
        self.assertIsNotNone(report["lift_interval"])
        self.assertEqual(report["lift_interval"]["lower"],0.)


class Group11HoldoutGates(unittest.TestCase):
    def test_reserved_partition_is_inaccessible(self):
        with self.assertRaises(PermissionError):
            sf.synthetic_prefix(P,1537)
        with self.assertRaises(PermissionError):
            sf.indices(P,"holdout")

    def test_existing_ledger_blocks_open_before_selection(self):
        manifest = sf.temporal_manifest(P,sf.indices(P,"development"),"development")
        ledger = TrialFamilyLedger(sf.frozen_family(P,manifest))
        with self.assertRaises(ValueError):
            ledger.holdout_event(HoldoutEvent("OPEN",sf.T+timedelta(days=1),"test-fixture"))


class Group12JournalReplayCheckpoint(unittest.TestCase):
    def test_complete_run_reproducibility_no_overwrite_and_artifact_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            one,two = Path(temp)/"one",Path(temp)/"two"
            first,_ = sf.run_batch(one)
            second,_ = sf.run_batch(two)
            self.assertEqual(first,second)
            self.assertEqual((one/"artifact_hashes.json").read_bytes(),(two/"artifact_hashes.json").read_bytes())
            self.assertTrue(sf.verify_batch(one))
            self.assertEqual(first["final_holdout"],"NOT_OPENED")
            self.assertIsNone(first["selected_for_promotion"])
            self.assertFalse(first["external_owner_custody_verified"])
            self.assertEqual(first["candidate_count"],12)
            for row in first["candidates"]:
                for partition in ("development","synthetic_validation"):
                    m=row[partition]
                    self.assertEqual(m["opportunities"],m["no_signal"]+m["attempts"])
                    self.assertEqual(m["attempts"],m["executed"]+m["no_fill"])
                    self.assertAlmostEqual(m["net_sum_known"],m["gross_sum_known"]-m["cost_sum_known"])
            with self.assertRaises(FileExistsError):
                sf.run_batch(one)
            forged = json.loads((two/"results.json").read_bytes())
            forged["candidates"][0]["synthetic_validation"]["net_sum_known"] += 1
            (two/"results.json").write_bytes(sf.canonical(forged)+b"\n")
            hashes = json.loads((two/"artifact_hashes.json").read_bytes())
            import hashlib
            hashes["results.json"] = hashlib.sha256((two/"results.json").read_bytes()).hexdigest()
            (two/"artifact_hashes.json").write_bytes(sf.canonical(hashes)+b"\n")
            with self.assertRaisesRegex(ValueError,"commitment differs"):
                sf.verify_batch(two)
            (two/"results.json").write_bytes(sf.canonical(first)+b"\n")
            detail = (two/"opportunities.jsonl").read_bytes().splitlines()
            altered = json.loads(detail[0])
            altered["decision_at"] = "1900-01-01T00:00:00+00:00"
            detail[0] = sf.canonical(altered)
            (two/"opportunities.jsonl").write_bytes(b"\n".join(detail)+b"\n")
            for name in ("results.json","opportunities.jsonl"):
                hashes[name] = hashlib.sha256((two/name).read_bytes()).hexdigest()
            (two/"artifact_hashes.json").write_bytes(sf.canonical(hashes)+b"\n")
            with self.assertRaisesRegex(ValueError,"Opportunity commitment differs"):
                sf.verify_batch(two)
            with (one/"results.json").open("ab") as f:
                f.write(b" ")
            with self.assertRaisesRegex(ValueError,"digest mismatch"):
                sf.verify_batch(one)

    def test_replay_and_local_anchor_detect_change(self):
        manifest = sf.temporal_manifest(P,sf.indices(P,"development"),"development")
        family = sf.frozen_family(P,manifest)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"journal.jsonl"
            with DurableTrialJournal(path,family) as j:
                j.record_attempt(Attempt(family.candidate_ids[0],AttemptState.COMPLETE,"result",
                                         sf.T+timedelta(days=1),1.),event_id="one")
                checkpoint = export_checkpoint(j)
                expected = asdict(j.report())
            with DurableTrialJournal(path,family,expected_head=checkpoint.head,
                                     expected_sequence=checkpoint.sequence) as j:
                self.assertEqual(asdict(j.report()),expected)
            data = path.read_bytes().replace(b'"result"',b'"forged"')
            path.write_bytes(data)
            with self.assertRaises(JournalIntegrityError):
                with DurableTrialJournal(path,family):
                    pass


if __name__ == "__main__":
    unittest.main()
