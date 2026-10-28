"""Proof sidecopy acceptance: no G1 ACK authority, fail-closed on backpressure."""
from concurrent.futures import Future

from aql.data_proof_g1_sidecopy import G1ProofSidecopy


class FakeExporter:
    def __init__(self, outcome="pending"):
        self.outcome = outcome
        self.calls = []

    def submit(self, **kwargs):
        self.calls.append(kwargs)
        future = Future()
        if self.outcome == "full":
            future.set_exception(RuntimeError("evidence queue full"))
        elif self.outcome == "failed":
            future.set_exception(RuntimeError("export failed"))
        elif self.outcome == "ok":
            future.set_result({"manifest_sha256": "local"})
        return future


def _observe(adapter, **overrides):
    kwargs = dict(source_committed=True, local_commit_receipt_ref="journal:committed",
                  consumer="factory", epoch=1, logical_bar_id="BTC:1m:0",
                  gap_states={"BTC:1m:0": "CONFIRMED"})
    kwargs.update(overrides)
    return adapter.observe_after_core(**kwargs)


def test_no_commit_no_enqueue():
    exporter = FakeExporter()
    adapter = G1ProofSidecopy(exporter)
    result = _observe(adapter, source_committed=False)
    assert not result.accepted and result.status == "SOURCE_COMMIT_NOT_PROVEN"
    assert not exporter.calls
    assert not _observe(adapter, local_commit_receipt_ref=None).accepted
    assert not exporter.calls


def test_full_queue_is_not_success():
    exporter = FakeExporter("full")
    adapter = G1ProofSidecopy(exporter)
    result = _observe(adapter)
    assert not result.accepted
    assert result.status == "PROOF_EXPORT_UNAVAILABLE_OR_FULL"
    assert adapter.poll(result) == "NOT_ADMITTED"


def test_pending_and_completed_remain_local_only():
    pending = G1ProofSidecopy(FakeExporter())
    admitted = _observe(pending)
    assert admitted.accepted and admitted.status == "QUEUED_NOT_DURABLE"
    assert pending.poll(admitted) == "PENDING"
    success = G1ProofSidecopy(FakeExporter("ok"))
    assert success.poll(_observe(success)) == "EXPORTED_LOCAL_ONLY"


def test_immediate_failure_is_rejected():
    adapter = G1ProofSidecopy(FakeExporter("failed"))
    result = _observe(adapter)
    assert not result.accepted
    assert adapter.poll(result) == "NOT_ADMITTED"
