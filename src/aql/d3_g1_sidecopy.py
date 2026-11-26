"""Opt-in D3 observation adapter at the existing G1 journal/store boundary.

This adapter never changes G1 ACKs or retries. Archive failure is observable,
not silently converted into source or target confirmation.
"""
from __future__ import annotations

from concurrent.futures import Future
from dataclasses import dataclass
from typing import Mapping

from .d3_offline_archive import OfflineArchiveLane
from .d3_synthetic_archive import D3IntegrityError


@dataclass(frozen=True)
class ArchiveAdmission:
    accepted: bool
    reason: str
    future: Future | None = None


class G1ArchiveSidecopy:
    """Explicit opt-in post-core sidecopy; no implicit realtime installation.

    Call ONLY after the journal/store authority has independently committed its
    own work. Never use the result to decide whether to ACK a source event.
    """

    def __init__(self, lane: OfflineArchiveLane):
        self.lane = lane
        self.rejected = 0
        self.submitted = 0

    def observe_after_core(self, catalog: Mapping[str, object], *,
                           source_committed: bool, target_confirmed: bool) -> ArchiveAdmission:
        if not source_committed:
            self.rejected += 1
            return ArchiveAdmission(False, "SOURCE_NOT_COMMITTED")
        if not target_confirmed:
            # A sparse WITHHELD / IN_DOUBT catalog can still be archived as
            # evidence, but cannot be represented as confirmed target custody.
            rows = catalog.get("inventory")
            if not isinstance(rows, list) or any(
                not isinstance(row, dict) or row.get("state") == "CONFIRMED"
                for row in rows
            ):
                self.rejected += 1
                return ArchiveAdmission(False, "TARGET_NOT_CONFIRMED")
        future = self.lane.submit(catalog)
        if future is None:
            self.rejected += 1
            return ArchiveAdmission(False, "ARCHIVE_UNAVAILABLE_OR_FULL")
        self.submitted += 1
        return ArchiveAdmission(True, "QUEUED_NOT_DURABLE", future)

    @staticmethod
    def publication_result(admission: ArchiveAdmission):
        """Explicit caller polling; never implicitly promotes core receipts."""
        if not admission.accepted or admission.future is None:
            raise D3IntegrityError("archive not admitted")
        if not admission.future.done():
            return "PENDING"
        try:
            admission.future.result()
        except Exception:
            return "FAILED"
        return "PUBLISHED_LOCAL_ONLY"
