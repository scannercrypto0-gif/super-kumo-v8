"""Adversarial controls for the trusted validator; no GitHub or market traffic."""
import copy
import datetime as dt
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import anti_redo_gate as gate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.base, self.head, self.cap_head = "a" * 40, "b" * 40, "c" * 40
        self.cid = "FACTORY.ATTEMPT"
        self.workflow = ".github/workflows/anti-redo-gate.yml"
        self.validator = "tools/pm/anti_redo_gate.py"
        self.tests = "tools/pm/test_anti_redo_gate.py"
        self.source = "src/reuse.py"
        self.revision = dict(repository="owner/repo", pr=307, base_ref="main",
                             base_sha=self.base, head_sha=self.head)
        self.record = dict(task="Reuse existing ledger", paths=[self.source], capability_ids=[self.cid],
                           contract_ids=["attempt-v1"], head_pins={self.cid: self.cap_head}, tests_reused=[],
                           evidence={}, proof="REUSE_WITH_ADAPTER", disposition="CONNECT_EXISTING",
                           changed_seam="Receipt adapter", authority="Review only", rollback="Withdraw",
                           overlap_review="Inspected receipt contract", owner_handoff="Issue #205",
                           crosswalk="Use #78", lookups=["PR #78"], later_decisions=["PM #307"], new_tests=[])
        self.policy = dict(version=2, repository="owner/repo", base_ref="main", pm_ids=[1],
                           capabilities={self.cid: dict(head_sha=self.cap_head, ref="heads/main",
                                                        owner_ids=[2], contracts=["attempt-v1"])},
                           evidence={}, pure_docs={"docs/approved.md": "d" * 40})
        self.now = dt.datetime(2026, 11, 13, tzinfo=dt.timezone.utc)

    def reviews(self, revision=None):
        manifest = dict(revision=revision or self.revision, records=[self.record])
        manifest["manifest_id"] = gate.manifest_digest(manifest)
        return [
            dict(id=1, state="APPROVED", commit_id=self.head, user={"id": 1, "type": "User"},
                 body=gate.REVIEW_MARKER + json.dumps(manifest)),
            dict(id=2, state="APPROVED", commit_id=self.head, user={"id": 2, "type": "User"},
                 body=f"ATLAS-COMPONENT-V2 {manifest['manifest_id']} {self.record['task']}"),
        ]

    def check(self, paths=None, reviews=None, blobs=None, refs=None):
        return gate.validate(self.policy, self.revision, paths if paths is not None else [self.source],
                             reviews if reviews is not None else self.reviews(),
                             lambda sha, path: (blobs or {}).get((sha, path)),
                             refs or (lambda _: self.cap_head), lambda e: e["runner"] == "Ubuntu / Python 3.13", self.now)

    def test_real_sensitive_path_requires_review_and_passes_exact_binding(self):
        self.assertEqual(self.check(), (1, 1))

    def test_unrelated_record_cannot_cover_other_file(self):
        with self.assertRaisesRegex(gate.Blocked, "unrelated"):
            self.check(paths=["src/other.py"])

    def test_uncovered_path(self):
        with self.assertRaisesRegex(gate.Blocked, "uncovered"):
            self.check(paths=[self.source, "src/other.py"])

    def test_expired_override(self):
        self.record["override"] = dict(scope=dict(self.revision, **{
            k: self.record[k] for k in ("task", "paths", "capability_ids", "contract_ids")
        }), reason="Different contracts", expires_utc="2026-11-12T23:59:59Z")
        with self.assertRaisesRegex(gate.Blocked, "expired"):
            self.check()
        self.record["override"]["expires_utc"] = "2026-11-13T00:01:00Z"
        self.assertEqual(self.check(), (1, 1))
        self.record["override"]["scope"]["paths"] = []
        with self.assertRaisesRegex(gate.Blocked, "scope"):
            self.check()

    def test_self_changes_cannot_be_exempted(self):
        for path in (self.validator, self.tests, self.workflow, gate.POLICY,
                     "docs/pm/anti-redo/gate.md", "docs/hidden.sh", "docs/other.md"):
            with self.subTest(path=path), self.assertRaisesRegex(gate.Blocked, "authenticated PM"):
                self.check(paths=[path], reviews=[])

    def test_stale_base_pr_and_head_mismatch(self):
        for key, value in (("base_sha", "e" * 40), ("pr", 99), ("head_sha", "f" * 40)):
            with self.subTest(key=key), self.assertRaisesRegex(gate.Blocked, "mismatch"):
                self.check(reviews=self.reviews(dict(self.revision, **{key: value})))

    def test_stale_capability(self):
        with self.assertRaisesRegex(gate.Blocked, "stale capability"):
            self.check(refs=lambda _: "e" * 40)

    def test_forged_or_dismissed_signoffs(self):
        reviews = self.reviews()
        for patch_values in (dict(user={"id": 9, "type": "User"}), dict(state="DISMISSED"),
                             dict(commit_id=self.base), dict(body="free text")):
            with self.subTest(patch_values=patch_values), self.assertRaisesRegex(gate.Blocked, "component signoff"):
                self.check(reviews=reviews[:1] + [dict(reviews[1], id=3, **patch_values)])

    def test_pure_doc_requires_exact_trusted_blob(self):
        path = "docs/approved.md"
        self.assertEqual(self.check([path], [], {(self.head, path): ("100644", "d" * 40)}), (0, 1))
        for blob in (None, ("100755", "d" * 40), ("100644", "f" * 40)):
            with self.assertRaisesRegex(gate.Blocked, "authenticated PM"):
                self.check([path], [], {(self.head, path): blob})

    def test_missing_base_policy_never_loads_candidate(self):
        event = {"pull_request": {"state": "open", "number": 307,
                 "base": {"repo": {"full_name": "owner/repo"}, "ref": "main", "sha": self.base},
                 "head": {"sha": self.head}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "event.json"
            path.write_text(json.dumps(event), encoding="utf-8")
            with patch.dict(os.environ, GITHUB_EVENT_NAME="pull_request_target", GITHUB_EVENT_PATH=str(path),
                            GITHUB_WORKFLOW_SHA=self.base), patch.object(gate, "git", return_value=self.base.encode()), \
                 patch.object(gate, "api", return_value=event["pull_request"]), \
                 patch.object(gate, "object_at", return_value=None) as read:
                with self.assertRaisesRegex(gate.Blocked, "base policy is absent"):
                    gate.live()
                read.assert_called_once_with(self.base, gate.POLICY)

    def test_falsified_evidence_and_tampered_objects(self):
        paths = dict(source=self.source, test=self.tests, workflow=self.workflow, fixture="tests/fixture.json")
        oid = "d" * 40
        known = dict(source_sha=self.cap_head, runner="Ubuntu / Python 3.13", run_url="https://example.test/run", run_id=100, job_id=200,
                     workflow_path=self.workflow, job_name="tests", labels=["ubuntu-latest"],
                     objects={role: {path: oid} for role, path in paths.items()})
        self.policy["evidence"]["CI-1"] = known
        self.record.update(tests_reused=["CI-1"], evidence={"CI-1": copy.deepcopy(known)})
        blobs = {(sha, path): ("100644", oid) for sha in (self.cap_head, self.head) for path in paths.values()}
        self.assertEqual(self.check(blobs=blobs), (1, 1))
        self.record["evidence"]["CI-1"]["runner"] = "Untrusted runner"
        with self.assertRaisesRegex(gate.Blocked, "unverified evidence identity"):
            self.check(blobs=blobs)
        self.record["evidence"]["CI-1"]["runner"] = known["runner"]
        for path in paths.values():
            with self.subTest(path=path), self.assertRaisesRegex(gate.Blocked, "bytes changed"):
                self.check(blobs=dict(blobs) | {(self.head, path): ("100644", "e" * 40)})

    def test_ci_job_must_match_run_and_runner_metadata(self):
        evidence = dict(run_id=100, job_id=200, source_sha=self.head, run_url="https://example.test/run",
                        workflow_path=self.workflow, job_name="tests", labels=["ubuntu-latest"])
        run = dict(id=100, head_sha=self.head, conclusion="success",
                   html_url=evidence["run_url"], path=self.workflow)
        job = dict(id=200, run_id=100, head_sha=self.head, conclusion="success",
                   name="tests", labels=["ubuntu-latest"])
        with patch.object(gate, "api", side_effect=[run, job]):
            self.assertTrue(gate.verified_run(evidence))
        for altered in (dict(job, run_id=101), dict(job, labels=["self-hosted"]),
                        dict(job, head_sha=self.base), dict(job, conclusion="failure")):
            with patch.object(gate, "api", side_effect=[run, altered]):
                self.assertFalse(gate.verified_run(evidence))

    def test_merge_base_diff_includes_rename_and_delete_excludes_base_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)

            def git(*args):
                return subprocess.check_output(["git", "-C", tmp, *args], stderr=subprocess.PIPE)

            git("init", "-q", "-b", "main")
            git("config", "user.email", "fixture@example.test")
            git("config", "user.name", "Fixture")
            for path in ("old.md", "deleted.py"):
                (repo / path).write_text("content", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "common")
            git("checkout", "-qb", "topic")
            git("mv", "old.md", "new.md")
            git("rm", "deleted.py")
            git("commit", "-qm", "rename and delete")
            head = git("rev-parse", "HEAD").decode().strip()
            git("checkout", "-q", "main")
            (repo / "base_only").touch()
            git("add", ".")
            git("commit", "-qm", "advance base")
            base = git("rev-parse", "HEAD").decode().strip()
            with patch.object(gate, "git", side_effect=git):
                self.assertCountEqual(gate.changed_paths(base, head), ["old.md", "new.md", "deleted.py"])


if __name__ == "__main__":
    unittest.main()
