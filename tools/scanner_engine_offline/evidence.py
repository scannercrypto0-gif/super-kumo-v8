"""G5 — Immutable evidence receipts and content-addressed checkpoint store.

Every scan result is captured as an EvidenceReceipt:
  - SHA-256 of canonical sorted-key JSON bytes
  - Claim-before-attempt: receipt ID assigned before computation begins
  - Append-and-readback: written to bounded in-memory spool; readback verifies integrity

BoundedSpool: last N receipts retained in memory (FIFO eviction).
  Default capacity: 500 receipts (≈ one medium scan session)

Replay model:
  SpoolCheckpoint serialises the full spool to a dict; restore_from_checkpoint
  rebuilds it with full integrity re-verification.  Any corrupt receipt → REJECTED.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from .contracts import _utc, canonical_bytes, sha256_hex, SCHEMA_VERSION

_DEFAULT_CAPACITY = 500
_DEFAULT_SPOOL_ID = "AQL-SCANNER-SPOOL-V1"

UTC = timezone.utc


# ── Evidence receipt ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EvidenceReceipt:
    """Immutable record of one scan result.

    receipt_id     — SHA-256 of canonical_payload; assigned at claim time
    claim_at       — wall clock when receipt was allocated (before computation)
    committed_at   — wall clock when payload was written (after computation)
    scanner_id     — identifies the scanner run
    symbol         — market symbol
    profile        — scoring profile
    stage          — lifecycle stage reached
    score          — Decimal string or None
    score_status   — SCORED | SCORE_UNAVAILABLE
    payload_digest — SHA-256 of the full payload dict (same as receipt_id when intact)
    """
    receipt_id: str
    claim_at: datetime
    committed_at: datetime
    scanner_id: str
    symbol: str
    profile: str
    stage: str
    score: str | None
    score_status: str
    payload: dict         # the full serialised output (envelope as_dict)
    payload_digest: str   # SHA-256 of canonical_bytes(payload)

    def verify_integrity(self) -> bool:
        """Return True if stored payload_digest matches re-computed digest."""
        return sha256_hex(canonical_bytes(self.payload)) == self.payload_digest

    def as_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "receipt_id": self.receipt_id,
            "claim_at": self.claim_at.isoformat(),
            "committed_at": self.committed_at.isoformat(),
            "scanner_id": self.scanner_id,
            "symbol": self.symbol,
            "profile": self.profile,
            "stage": self.stage,
            "score": self.score,
            "score_status": self.score_status,
            "payload_digest": self.payload_digest,
        }


def _claim_receipt_id(
    scanner_id: str,
    symbol: str,
    profile: str,
    claim_at: datetime,
    run_id: str = "",
) -> str:
    """Deterministic receipt ID before computation: hash of identity fields.

    P0-03 fix: run_id is included so distinct runs at the same cutoff cannot
    produce the same receipt_id for different payloads.
    """
    seed = canonical_bytes({
        "scanner_id": scanner_id,
        "symbol": symbol,
        "profile": profile,
        "claim_at": claim_at.isoformat(),
        "run_id": run_id,
    })
    return sha256_hex(seed)


def commit_receipt(
    scanner_id: str,
    symbol: str,
    profile: str,
    stage: str,
    score: str | None,
    score_status: str,
    payload: dict,
    claim_at: datetime,
    committed_at: datetime | None = None,
    run_id: str = "",
) -> EvidenceReceipt:
    """Create and commit a receipt for a completed scan result.

    P0-03 fix: run_id included in receipt_id derivation to prevent same-ID
    collision across runs at the same cutoff.
    P1-01 fix: committed_at defaults to claim_at (not wall clock) for
    deterministic research output; callers may pass explicit value.
    """
    claim_at = _utc(claim_at)
    if committed_at is None:
        committed_at = claim_at  # deterministic: not wall clock
    else:
        committed_at = _utc(committed_at)
    receipt_id = _claim_receipt_id(scanner_id, symbol, profile, claim_at, run_id)
    payload_digest = sha256_hex(canonical_bytes(payload))
    return EvidenceReceipt(
        receipt_id=receipt_id,
        claim_at=claim_at,
        committed_at=committed_at,
        scanner_id=scanner_id,
        symbol=symbol,
        profile=profile,
        stage=stage,
        score=score,
        score_status=score_status,
        payload=payload,
        payload_digest=payload_digest,
    )


# ── Bounded spool ──────────────────────────────────────────────────────────────

@dataclass
class BoundedSpool:
    """Thread-unsafe bounded in-memory receipt spool.

    Oldest receipts are evicted when capacity is exceeded.
    All receipts verified on append; corrupt writes raise ValueError.
    """
    capacity: int = _DEFAULT_CAPACITY
    spool_id: str = _DEFAULT_SPOOL_ID
    _receipts: list[EvidenceReceipt] = field(default_factory=list, repr=False)
    _index: dict[str, EvidenceReceipt] = field(default_factory=dict, repr=False)

    def append(self, receipt: EvidenceReceipt) -> EvidenceReceipt:
        """Append a receipt; verify integrity; evict oldest if over capacity.

        P0-03 fix: duplicate receipt_id with DIFFERENT payload digest raises
        ValueError(RECEIPT_ID_CONFLICT) rather than silently returning stale result.
        Same receipt_id with same digest is idempotent (exact replay).
        """
        if not receipt.verify_integrity():
            raise ValueError(
                f"INTEGRITY_FAILURE:receipt_id={receipt.receipt_id}")
        if receipt.receipt_id in self._index:
            existing = self._index[receipt.receipt_id]
            if existing.payload_digest != receipt.payload_digest:
                raise ValueError(
                    f"RECEIPT_ID_CONFLICT:receipt_id={receipt.receipt_id}"
                    f",existing_digest={existing.payload_digest}"
                    f",new_digest={receipt.payload_digest}"
                )
            return existing  # exact idempotent replay
        self._receipts.append(receipt)
        self._index[receipt.receipt_id] = receipt
        if len(self._receipts) > self.capacity:
            evicted = self._receipts.pop(0)
            self._index.pop(evicted.receipt_id, None)
        return receipt

    def get(self, receipt_id: str) -> EvidenceReceipt | None:
        return self._index.get(receipt_id)

    def __len__(self) -> int:
        return len(self._receipts)

    def __iter__(self) -> Iterator[EvidenceReceipt]:
        return iter(list(self._receipts))

    def to_checkpoint(self) -> "SpoolCheckpoint":
        return SpoolCheckpoint(
            spool_id=self.spool_id,
            capacity=self.capacity,
            receipt_count=len(self._receipts),
            receipts=[r.as_dict() | {"payload": r.payload}
                      for r in self._receipts],
        )


# ── Checkpoint / replay ────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SpoolCheckpoint:
    """Serialisable spool snapshot for replay."""
    spool_id: str
    capacity: int
    receipt_count: int
    receipts: list[dict]

    def as_dict(self) -> dict:
        return {
            "spool_id": self.spool_id,
            "capacity": self.capacity,
            "receipt_count": self.receipt_count,
            "receipts": self.receipts,
        }


def restore_from_checkpoint(
    checkpoint: SpoolCheckpoint,
) -> tuple[BoundedSpool, list[str]]:
    """Rebuild a BoundedSpool from a checkpoint.

    Returns (spool, rejected_ids) where rejected_ids lists any receipts
    that failed integrity verification (skipped, not restored).
    """
    spool = BoundedSpool(capacity=checkpoint.capacity, spool_id=checkpoint.spool_id)
    rejected: list[str] = []
    for rec_dict in checkpoint.receipts:
        try:
            receipt = EvidenceReceipt(
                receipt_id=rec_dict["receipt_id"],
                claim_at=_utc(datetime.fromisoformat(rec_dict["claim_at"])),
                committed_at=_utc(datetime.fromisoformat(rec_dict["committed_at"])),
                scanner_id=rec_dict["scanner_id"],
                symbol=rec_dict["symbol"],
                profile=rec_dict["profile"],
                stage=rec_dict["stage"],
                score=rec_dict.get("score"),
                score_status=rec_dict["score_status"],
                payload=rec_dict["payload"],
                payload_digest=rec_dict["payload_digest"],
            )
            spool.append(receipt)
        except (KeyError, ValueError, TypeError) as exc:
            rid = rec_dict.get("receipt_id", "UNKNOWN")
            rejected.append(f"{rid}:{exc}")
    return spool, rejected
