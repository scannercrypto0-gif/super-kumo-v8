import tempfile
import unittest
from pathlib import Path
from aql.binance_observer import ObserverLedger, verify_bundle
from aql.evidence_outbox import EvidenceOutbox
from tests.guardian_fixtures import receipt

class LedgerOutboxIntegrationTests(unittest.TestCase):
    def test_snapshot_offline_restart_then_recover(self):
        with tempfile.TemporaryDirectory() as d:
            ledger = ObserverLedger(Path(d) / "observer.sqlite")
            outbox = EvidenceOutbox(Path(d) / "outbox")
            key = ledger.queue_external_evidence(outbox)
            self.assertEqual(key, ledger.queue_external_evidence(outbox))
            self.assertEqual(1, outbox.pending_count())
            self.assertEqual("PENDING_EXTERNAL_ANCHOR",
                             outbox.deliver(lambda *_: None)[0][1])
            ledger.close()
            restarted = EvidenceOutbox(Path(d) / "outbox")
            def sender(bundle, sha):
                verify_bundle(bundle, bundle["ledger_head"])
                return receipt(sha)
            result = restarted.deliver(sender)
            self.assertEqual("REMOTE_RECEIPT_RECORDED_NOT_INDEPENDENTLY_VERIFIED",
                             result[0][1])
            self.assertEqual(0, restarted.pending_count())
            self.assertEqual([], restarted.deliver(sender))

if __name__ == "__main__":
    unittest.main()
