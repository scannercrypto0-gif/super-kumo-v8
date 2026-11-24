import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from aql.observation.contracts import digest
from tools.atlas_daily_health_evidence import verify_daily_success

DAY_MS = 86_400_000


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class DailyHealthEvidenceTests(unittest.TestCase):
    def evidence_tree(self, root):
        state = root / "state"
        state.mkdir()
        (state / "atlas-authorized-periodic-v1").write_text("", encoding="ascii")
        policy_path = root / "policy" / "policy.json"
        policy = dict(schema="atlas.vision.daily-research.v1",
                      first_open_ms=DAY_MS * 10, host="TESTHOST",
                      authorization_ref="owner-approved-test")
        write_json(policy_path, policy)
        source_day = int(datetime(2026, 11, 23, tzinfo=timezone.utc).timestamp() * 1000)
        date = datetime.fromtimestamp(source_day / 1000, timezone.utc).strftime("%Y-%m-%d")
        receipt = "3" * 64
        job = dict(start_ms=source_day, archive=f"BTCUSDT-1m-{date}.zip",
                   archive_sha256="a" * 64, checksum_sha256="b" * 64,
                   authorization_ref=policy["authorization_ref"], host=policy["host"])
        write_json(policy_path.parent / "daily" / f"day-{source_day}" / "job.json", job)
        write_json(policy_path.parent / "daily" / f"{source_day}.done.json",
                   dict(start_ms=source_day, receipt_sha256=receipt))
        (state / f"{source_day}.claim").write_text(digest(job), encoding="ascii")
        return state, policy_path, digest(policy), source_day, receipt

    def test_verified_completion_returns_only_source_pins(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"COMPUTERNAME": "TESTHOST"}):
            args = self.evidence_tree(Path(folder))
            result = verify_daily_success(*args[:4], args[4])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(result["source_zip_sha256"], "a" * 64)
        self.assertEqual(result["checksum_sha256"], "b" * 64)
        self.assertEqual(result["receipt_sha256"], "3" * 64)

    def test_mutated_job_fails_claim_link(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"COMPUTERNAME": "TESTHOST"}):
            args = self.evidence_tree(Path(folder))
            job_path = args[1].parent / "daily" / f"day-{args[3]}" / "job.json"
            job = json.loads(job_path.read_text(encoding="utf-8"))
            job["archive_sha256"] = "c" * 64
            write_json(job_path, job)
            with self.assertRaisesRegex(ValueError, "DAILY_EVIDENCE_LINK_UNPROVEN"):
                verify_daily_success(*args[:4], args[4])

    def test_receipt_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"COMPUTERNAME": "TESTHOST"}):
            args = self.evidence_tree(Path(folder))
            with self.assertRaisesRegex(ValueError, "DAILY_EVIDENCE_LINK_UNPROVEN"):
                verify_daily_success(args[0], args[1], args[2], args[3], "4" * 64)


if __name__ == "__main__":
    unittest.main()
