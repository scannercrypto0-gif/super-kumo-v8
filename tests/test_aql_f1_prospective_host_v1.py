"""Changed-seam integration against real Core modules, no synthetic imports.

Records are fixture data; success cannot establish independent operational PIT.
"""
import copy
import tempfile
import unittest
from pathlib import Path

from research_wp_r0.aql_f1_decision_capture_v1 import CaptureError, hash_f1
from research_wp_r0.aql_f1_prospective_host_v1 import (
    capture_then_call_f3, run_prospective_host,
)
from tests.test_aql_f1_decision_capture_v1 import fixture
from tests.test_aql_f1_prospective_bridge import envelope


class ProspectiveHostIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.base, self.registry = fixture()
        self.shadow, _ = fixture("SHADOW")
        self.c2 = envelope(self.base)
        self.plan = self.base["experiment_plan_sha256"]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.pre_f3 = True

    def run_host(self, arms=None, **kw):
        return run_prospective_host(
            self.c2, self.plan,
            {"BASE": self.base, "SHADOW": self.shadow} if arms is None else arms,
            self.registry, self.directory,
            pre_f3_gate=kw.pop("pre_f3_gate", lambda _: self.pre_f3),
            **kw,
        )

    def test_original_two_arm_unverified_and_idempotent(self):
        first = self.run_host()
        second = self.run_host()
        self.assertEqual(first, second)
        self.assertEqual([row["capture_status"] for row in first["slots"]],
                         ["UNVERIFIED", "UNVERIFIED"])
        self.assertEqual([(self.directory / (arm + ".jsonl")).read_bytes().count(b"\n")
                          for arm in ("base", "shadow")], [1, 1])
        self.assertTrue((self.directory / (first["pair_id"] + ".handoff.json")).is_file())

    def test_missing_shadow_retains_full_denominator(self):
        rows = self.run_host({"BASE": self.base, "SHADOW": None})["slots"]
        self.assertEqual([row["capture_status"] for row in rows],
                         ["UNVERIFIED", "MISSING_CAPTURE"])

    def test_post_f3_denied_before_any_write(self):
        self.pre_f3 = False
        with self.assertRaisesRegex(CaptureError, "F3_ALREADY_STARTED"):
            self.run_host()
        self.assertFalse((self.directory / "base.jsonl").exists())

    def test_gate_unavailable_and_historical_denied(self):
        with self.assertRaisesRegex(CaptureError, "PRE_F3_GATE_UNAVAILABLE"):
            self.run_host(pre_f3_gate=lambda _: 1 / 0)
        self.c2["availability_mode"] = "RETROSPECTIVE_NON_PIT"
        with self.assertRaisesRegex(CaptureError, "HISTORICAL"):
            self.run_host()

    def test_same_slot_conflicting_original_rejected(self):
        self.run_host()
        changed = copy.deepcopy(self.base)
        changed["f1_signal_state"] = "UNKNOWN"
        changed["f1_record_sha256"] = hash_f1(changed)
        with self.assertRaisesRegex(CaptureError, "JOURNAL_SAME_SLOT_CONFLICT"):
            self.run_host({"BASE": changed, "SHADOW": self.shadow})

    def test_torn_journal_fails_closed(self):
        (self.directory / "base.jsonl").write_bytes(b'{"truncated":')
        with self.assertRaisesRegex(CaptureError, "JOURNAL_TORN_WRITE"):
            self.run_host()

    def test_missing_external_evidence_is_unverified(self):
        outcome = self.run_host(evidence_lookup=lambda _: None,
            source_attestor=lambda _: True,
            freeze_attestor=lambda _: True,
            durable_anchor_verifier=lambda _: True,
            parent_witness=lambda _: True)
        self.assertTrue(all(x["capture_status"] == "UNVERIFIED" for x in outcome["slots"]))

    def test_changed_evidence_cannot_rewrite_existing_handoff(self):
        self.run_host()
        # A changed evidence-view is not allowed to rewrite an already
        # frozen handoff, even when the new proof still fails closed.
        with self.assertRaisesRegex(CaptureError, "IMMUTABLE_HANDOFF_CONFLICT"):
            self.run_host(evidence_lookup=lambda _: {})

    def test_capture_precedes_f3_callback(self):
        received = []
        def f3(handoff):
            file = self.directory / (handoff["pair_id"] + ".handoff.json")
            self.assertTrue(file.exists())
            received.append(handoff["handoff_sha256"])
            return "F3_CONTROLLED"
        handoff, result = capture_then_call_f3(
            f3_entrypoint=f3, c2=self.c2, plan_sha=self.plan,
            arm_records={"BASE": self.base, "SHADOW": self.shadow},
            registry=self.registry, journal_dir=self.directory,
            pre_f3_gate=lambda _: True)
        self.assertEqual(received, [handoff["handoff_sha256"]])
        self.assertEqual(result, "F3_CONTROLLED")

    def test_denied_gate_never_calls_f3(self):
        calls = []
        with self.assertRaisesRegex(CaptureError, "F3_ALREADY_STARTED"):
            capture_then_call_f3(
                f3_entrypoint=lambda x: calls.append(x), c2=self.c2,
                plan_sha=self.plan,
                arm_records={"BASE": self.base, "SHADOW": self.shadow},
                registry=self.registry, journal_dir=self.directory,
                pre_f3_gate=lambda _: False)
        self.assertEqual(calls, [])

    def test_symlinked_handoff_is_rejected(self):
        fake = self.directory / "outside"
        fake.write_text("protected")
        (self.directory / (self.base["pair_id"] + ".handoff.json")).symlink_to(fake)
        with self.assertRaisesRegex(CaptureError, "HANDOFF_PATH_UNSAFE"):
            self.run_host()
        self.assertEqual(fake.read_text(), "protected")


if __name__ == "__main__":
    unittest.main()
