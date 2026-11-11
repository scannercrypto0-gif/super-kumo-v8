"""
Stage 8 — Asynchronous archival simulation and crash/restart recovery.

Design
------
- Bounded offline queue: durable intent written before any work begins
- Receipt written only after object is verified in vault
- ACK = read-back verification; no ACK → item stays pending
- Crash simulation: kill between intent and receipt → item re-processed
- Idempotency: re-processing same sha256 is harmless (vault is content-addressed)
- Failed retry: permanent-fail queue with reason
- Retention policy dry-run: reports what WOULD be evicted; never deletes objects
- No network, no live exchange, no production data

Queue state machine
-------------------
PENDING  → PROCESSING → VERIFIED (→ ACKED)
                      ↘ FAILED   (→ PERMANENT_FAIL after max_retries)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from .vault import RawVault
from .schema import VaultError


# ── queue item state machine ──────────────────────────────────────────────────

class QueueItemState(str, Enum):
    PENDING        = "PENDING"         # intent written, not yet processed
    PROCESSING     = "PROCESSING"      # work in progress (crash-sensitive window)
    VERIFIED       = "VERIFIED"        # admitted + read-back verified
    ACKED          = "ACKED"           # confirmed by caller
    FAILED         = "FAILED"          # last attempt failed, eligible for retry
    PERMANENT_FAIL = "PERMANENT_FAIL"  # max_retries exhausted


@dataclass
class QueueItem:
    item_id: str
    content_sha256: str              # must match vault object
    meta_dict: dict                  # serialised RawObjectMeta fields
    enqueued_at_utc: str
    state: str = QueueItemState.PENDING
    attempts: int = 0
    max_retries: int = 3
    last_error: Optional[str] = None
    verified_at_utc: Optional[str] = None
    acked_at_utc: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QueueItem":
        return cls(**d)


# ── queue persistence (JSONL, one item per line, append-only intent log) ──────

QUEUE_FILENAME = "archival_queue.jsonl"   # durable intent log
RECEIPT_FILENAME = "archival_receipts.jsonl"

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class ArchivalQueue:
    """
    Durable offline archival queue with crash-recovery semantics.

    Recovery contract
    -----------------
    On __init__, any item in state PROCESSING is reset to PENDING:
    the intent was written but work may not have completed.
    Items in VERIFIED remain VERIFIED; the vault is the source of truth.
    """

    def __init__(self, queue_dir: Path, vault: RawVault, max_size: int = 1000):
        self._dir = Path(queue_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._queue_path = self._dir / QUEUE_FILENAME
        self._receipt_path = self._dir / RECEIPT_FILENAME
        self._vault = vault
        self._max_size = max_size
        self._recover_on_init()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load_items(self) -> dict[str, QueueItem]:
        """Load all queue items, keyed by item_id. Last state wins on replay."""
        items: dict[str, QueueItem] = {}
        if not self._queue_path.exists():
            return items
        for line in self._queue_path.read_text("utf-8").splitlines():
            line = line.strip()
            if line:
                item = QueueItem.from_dict(json.loads(line))
                items[item.item_id] = item   # later line overwrites earlier
        return items

    def _append_item(self, item: QueueItem) -> None:
        """Append current item state to the JSONL log (durable intent/update)."""
        line = json.dumps(item.to_dict(), sort_keys=True, separators=(",", ":")) + "\n"
        with open(self._queue_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def _append_receipt(self, item: QueueItem) -> None:
        line = json.dumps({
            "item_id": item.item_id,
            "content_sha256": item.content_sha256,
            "state": item.state,
            "verified_at_utc": item.verified_at_utc,
            "acked_at_utc": item.acked_at_utc,
        }, sort_keys=True, separators=(",", ":")) + "\n"
        with open(self._receipt_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    # ── crash recovery ────────────────────────────────────────────────────────

    def _recover_on_init(self) -> int:
        """Reset any PROCESSING items to PENDING (crash recovery). Returns count."""
        items = self._load_items()
        recovered = 0
        for item in items.values():
            if item.state == QueueItemState.PROCESSING:
                item.state = QueueItemState.PENDING
                self._append_item(item)
                recovered += 1
        return recovered

    # ── public API ────────────────────────────────────────────────────────────

    def enqueue(
        self,
        content_sha256: str,
        meta_dict: dict,
        *,
        max_retries: int = 3,
    ) -> QueueItem:
        """
        Write a durable intent before any processing begins.
        Object must already be admitted to vault before enqueue.
        """
        items = self._load_items()
        if len(items) >= self._max_size:
            raise OverflowError(
                f"Queue full: {len(items)} >= max_size {self._max_size}"
            )
        # idempotency: if same sha256 already VERIFIED or ACKED, skip
        for existing in items.values():
            if (existing.content_sha256 == content_sha256
                    and existing.state in (QueueItemState.VERIFIED, QueueItemState.ACKED)):
                return existing

        item = QueueItem(
            item_id=str(uuid.uuid4()),
            content_sha256=content_sha256,
            meta_dict=meta_dict,
            enqueued_at_utc=_now_utc(),
            state=QueueItemState.PENDING,
            max_retries=max_retries,
        )
        self._append_item(item)
        return item

    def process_next(self) -> Optional[QueueItem]:
        """
        Process the next PENDING item.

        Workflow
        --------
        1. Mark PROCESSING (durable) — crash here → recovered to PENDING on restart
        2. Read-back verify object from vault
        3. On success: mark VERIFIED + write receipt
        4. On failure: mark FAILED or PERMANENT_FAIL

        Returns the processed item, or None if no PENDING items.
        """
        items = self._load_items()
        pending = [
            i for i in items.values()
            if i.state == QueueItemState.PENDING
        ]
        if not pending:
            return None

        item = pending[0]

        # Step 1: mark PROCESSING (durable)
        item.state = QueueItemState.PROCESSING
        item.attempts += 1
        self._append_item(item)

        # Step 2: read-back verify
        try:
            raw = self._vault.read(item.content_sha256)
            # successful read proves integrity
            item.state = QueueItemState.VERIFIED
            item.verified_at_utc = _now_utc()
            item.last_error = None
            self._append_item(item)
            self._append_receipt(item)
        except Exception as exc:
            error_msg = str(exc)
            if item.attempts >= item.max_retries:
                item.state = QueueItemState.PERMANENT_FAIL
            else:
                item.state = QueueItemState.FAILED
            item.last_error = error_msg
            self._append_item(item)

        return item

    def ack(self, item_id: str) -> QueueItem:
        """Caller confirms receipt. Transitions VERIFIED → ACKED."""
        items = self._load_items()
        item = items.get(item_id)
        if item is None:
            raise KeyError(f"item_id {item_id!r} not found in queue")
        if item.state != QueueItemState.VERIFIED:
            raise ValueError(
                f"Cannot ACK item in state {item.state!r}; must be VERIFIED"
            )
        item.state = QueueItemState.ACKED
        item.acked_at_utc = _now_utc()
        self._append_item(item)
        self._append_receipt(item)
        return item

    def retry_failed(self) -> list[QueueItem]:
        """Reset all FAILED (not PERMANENT_FAIL) items back to PENDING."""
        items = self._load_items()
        retried = []
        for item in items.values():
            if item.state == QueueItemState.FAILED:
                item.state = QueueItemState.PENDING
                self._append_item(item)
                retried.append(item)
        return retried

    def snapshot(self) -> dict:
        """Return a summary of current queue states."""
        items = self._load_items()
        counts: dict[str, int] = {}
        for item in items.values():
            counts[item.state] = counts.get(item.state, 0) + 1
        return {
            "total": len(items),
            "by_state": counts,
            "queue_path": str(self._queue_path),
        }

    def all_items(self) -> list[QueueItem]:
        return list(self._load_items().values())


# ── retention policy dry-run ──────────────────────────────────────────────────

@dataclass
class RetentionReport:
    """Result of a retention policy dry-run. Never deletes anything."""
    policy_name: str
    evaluated_at_utc: str
    total_objects: int
    would_evict: list[str]     # content_sha256 values
    would_retain: list[str]
    eviction_reason: dict[str, str]  # sha256 → reason
    dry_run: bool = True       # always True — no deletion ever performed here


def retention_dry_run(
    vault: RawVault,
    *,
    max_objects: Optional[int] = None,
    older_than_days: Optional[float] = None,
    policy_name: str = "default",
) -> RetentionReport:
    """
    Simulate retention eviction without deleting any objects.

    Parameters
    ----------
    max_objects     : if set, mark oldest entries beyond this count for eviction
    older_than_days : if set, mark entries whose admitted_at is older than N days
    policy_name     : label for the report

    Returns
    -------
    RetentionReport — dry_run=True, no mutation of vault or queue.
    """
    entries = vault.manifest_entries()
    total = len(entries)
    would_evict: list[str] = []
    would_retain: list[str] = []
    reasons: dict[str, str] = {}

    now_ts = time.time()

    for i, entry in enumerate(entries):
        sha = entry.get("content_sha256", "")
        evict = False
        reason = ""

        if max_objects is not None and i < total - max_objects:
            evict = True
            reason = f"max_objects={max_objects}: position {i} of {total}"

        if older_than_days is not None:
            admitted_raw = entry.get("admitted_at_utc", "")
            try:
                admitted_ts = datetime.fromisoformat(
                    admitted_raw.replace("Z", "+00:00")
                ).timestamp()
                age_days = (now_ts - admitted_ts) / 86400
                if age_days > older_than_days:
                    evict = True
                    reason = (reason + "; " if reason else "") + (
                        f"older_than_days={older_than_days}: age={age_days:.1f}d"
                    )
            except (ValueError, AttributeError):
                pass

        if evict:
            would_evict.append(sha)
            reasons[sha] = reason
        else:
            would_retain.append(sha)

    return RetentionReport(
        policy_name=policy_name,
        evaluated_at_utc=_now_utc(),
        total_objects=total,
        would_evict=would_evict,
        would_retain=would_retain,
        eviction_reason=reasons,
        dry_run=True,
    )
