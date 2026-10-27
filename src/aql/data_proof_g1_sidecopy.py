"""Opt-in post-G1-commit proof sidecopy; never affects G1 ACK.

The caller must supply a *real* journal/store commit receipt. This adapter does
not infer commit success from arrival, bar close or a D3 archive result.
"""
from dataclasses import dataclass
from concurrent.futures import Future

from aql.data_proof import ProofError
from aql.data_proof_exporter import BoundedEvidenceExporter


@dataclass(frozen=True)
class ProofSidecopyAdmission:
    accepted: bool
    status: str
    future: Future | None = None


class G1ProofSidecopy:
    def __init__(self, exporter: BoundedEvidenceExporter):
        self.exporter = exporter
        self.rejected = 0

    def observe_after_core(self, *, source_committed: bool,
                           local_commit_receipt_ref: str | None,
                           consumer: str, epoch: int, logical_bar_id: str,
                           gap_states: dict[str, str]) -> ProofSidecopyAdmission:
        if not source_committed or not local_commit_receipt_ref:
            self.rejected += 1
            return ProofSidecopyAdmission(False, "SOURCE_COMMIT_NOT_PROVEN")
        try:
            future = self.exporter.submit(
                consumer=consumer, epoch=epoch, logical_bar_id=logical_bar_id,
                gap_states=gap_states)
        except ProofError:
            self.rejected += 1
            return ProofSidecopyAdmission(False, "PROOF_EXPORT_UNAVAILABLE_OR_FULL")
        return ProofSidecopyAdmission(True, "QUEUED_NOT_DURABLE", future)

    @staticmethod
    def poll(admission: ProofSidecopyAdmission) -> str:
        if not admission.accepted or admission.future is None:
            return "NOT_ADMITTED"
        if not admission.future.done():
            return "PENDING"
        try:
            admission.future.result()
        except Exception:
            return "FAILED_REPLAY_REQUIRED"
        return "EXPORTED_LOCAL_ONLY"
