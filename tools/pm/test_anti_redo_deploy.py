"""Focused revision invalidation tests for the dispatch seam."""
import unittest
from unittest.mock import Mock

import anti_redo_gate as gate


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.base, self.head = "a" * 40, "b" * 40
        self.pr = {
            "state": "open", "number": 307,
            "base": {"ref": "main", "sha": self.base, "repo": {"full_name": "owner/repo"}},
            "head": {"sha": self.head},
        }
        self.read_pr = Mock(return_value=self.pr)
        self.event = {"inputs": {"pr_number": "307", "base_sha": self.base, "head_sha": self.head}}

    def test_dispatch_resolves_the_current_pr_at_exact_pins(self):
        self.assertEqual(gate.expected_revision(self.event, "workflow_dispatch", self.read_pr),
                         gate.revision_of(self.pr))
        self.read_pr.assert_called_once_with(307)

    def test_stale_base_or_head_blocks_review_dispatch(self):
        for field in ("base_sha", "head_sha"):
            with self.subTest(field=field), self.assertRaisesRegex(gate.Blocked, "stale dispatch"):
                event = {"inputs": dict(self.event["inputs"], **{field: "c" * 40})}
                gate.expected_revision(event, "workflow_dispatch", self.read_pr)

    def test_pr_controlled_workflow_event_is_rejected(self):
        with self.assertRaisesRegex(gate.Blocked, "trusted event"):
            gate.expected_revision(self.event, "pull_request_review", self.read_pr)
        self.read_pr.assert_not_called()

    def test_base_retarget_invalidates_queued_pr_event(self):
        event = {"pull_request": self.pr}
        self.read_pr.return_value = dict(self.pr, base=dict(self.pr["base"], ref="other"))
        with self.assertRaisesRegex(gate.Blocked, "stale event"):
            gate.expected_revision(event, "pull_request_target", self.read_pr)


if __name__ == "__main__":
    unittest.main()
