"""Tests for G5 — evidence.py: receipts, spool, checkpoint/replay."""
import pytest
from datetime import datetime, timezone, timedelta

from tools.scanner_engine_offline.evidence import (
    EvidenceReceipt, BoundedSpool, commit_receipt,
    SpoolCheckpoint, restore_from_checkpoint,
)
from tools.scanner_engine_offline.contracts import sha256_hex, canonical_bytes

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

PAYLOAD = {"schema_version": "AQL-SCANNER-V1", "symbol": "SOLUSDT", "score": "72.00"}


def make_receipt(symbol: str = "SOLUSDT", score: str = "72.00") -> EvidenceReceipt:
    payload = dict(PAYLOAD, symbol=symbol, score=score)
    return commit_receipt(
        scanner_id="SCANNER-1",
        symbol=symbol,
        profile="INTRADAY",
        stage="NOMINATED",
        score=score,
        score_status="SCORED",
        payload=payload,
        claim_at=T0,
        committed_at=T0 + timedelta(seconds=1),
    )


class TestCommitReceipt:
    def test_receipt_created(self):
        r = make_receipt()
        assert r.receipt_id is not None
        assert len(r.receipt_id) == 64

    def test_payload_digest_matches(self):
        r = make_receipt()
        assert r.verify_integrity()

    def test_deterministic_receipt_id(self):
        r1 = make_receipt()
        r2 = make_receipt()
        assert r1.receipt_id == r2.receipt_id

    def test_different_symbols_different_ids(self):
        r1 = make_receipt("SOLUSDT")
        r2 = make_receipt("AVAXUSDT")
        assert r1.receipt_id != r2.receipt_id

    def test_as_dict_structure(self):
        r = make_receipt()
        d = r.as_dict()
        for key in ("receipt_id", "claim_at", "committed_at", "scanner_id",
                    "symbol", "profile", "stage", "score", "score_status", "payload_digest"):
            assert key in d


class TestBoundedSpool:
    def test_append_and_get(self):
        spool = BoundedSpool(capacity=10)
        r = make_receipt()
        spool.append(r)
        assert spool.get(r.receipt_id) is r

    def test_evicts_oldest_over_capacity(self):
        spool = BoundedSpool(capacity=3)
        receipts = [make_receipt(f"TOKEN{i}USDT") for i in range(5)]
        for r in receipts:
            spool.append(r)
        assert len(spool) == 3
        assert spool.get(receipts[0].receipt_id) is None  # evicted
        assert spool.get(receipts[-1].receipt_id) is not None

    def test_idempotent_append(self):
        spool = BoundedSpool(capacity=10)
        r = make_receipt()
        spool.append(r)
        spool.append(r)  # duplicate
        assert len(spool) == 1

    def test_corrupt_receipt_raises(self):
        spool = BoundedSpool(capacity=10)
        r = make_receipt()
        bad = EvidenceReceipt(
            receipt_id=r.receipt_id,
            claim_at=r.claim_at,
            committed_at=r.committed_at,
            scanner_id=r.scanner_id,
            symbol=r.symbol,
            profile=r.profile,
            stage=r.stage,
            score=r.score,
            score_status=r.score_status,
            payload={"tampered": True},
            payload_digest=r.payload_digest,  # stale digest
        )
        with pytest.raises(ValueError, match="INTEGRITY_FAILURE"):
            spool.append(bad)


class TestCheckpointReplay:
    def test_checkpoint_and_restore(self):
        spool = BoundedSpool(capacity=10)
        for i in range(5):
            spool.append(make_receipt(f"TOKEN{i}USDT"))
        cp = spool.to_checkpoint()
        restored, rejected = restore_from_checkpoint(cp)
        assert len(rejected) == 0
        assert len(restored) == 5

    def test_corrupt_receipt_skipped_on_restore(self):
        spool = BoundedSpool(capacity=10)
        spool.append(make_receipt("SOLUSDT"))
        cp = spool.to_checkpoint()
        # Corrupt the first receipt's payload_digest
        cp.receipts[0]["payload_digest"] = "deadbeef" * 8
        restored, rejected = restore_from_checkpoint(cp)
        assert len(rejected) == 1
        assert len(restored) == 0

    def test_restore_preserves_spool_id(self):
        spool = BoundedSpool(capacity=10, spool_id="MY-SPOOL")
        cp = spool.to_checkpoint()
        restored, _ = restore_from_checkpoint(cp)
        assert restored.spool_id == "MY-SPOOL"
