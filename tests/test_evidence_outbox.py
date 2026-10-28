import json
import tempfile
import unittest
from pathlib import Path
from aql.evidence_outbox import EvidenceOutbox
from tests.guardian_fixtures import receipt

class EvidenceOutboxTests(unittest.TestCase):
    def test_offline_then_recovery_without_core_block(self):
        with tempfile.TemporaryDirectory() as d:
            q=EvidenceOutbox(d)
            key=q.enqueue({"ledger_head":"abc","version":1})
            self.assertEqual(key,q.enqueue({"ledger_head":"abc","version":1}))
            self.assertEqual([(key,"PENDING_EXTERNAL_ANCHOR")],
                             q.deliver(lambda *_: (_ for _ in ()).throw(ConnectionError("offline"))))
            self.assertEqual(1,q.pending_count())
            reopened=EvidenceOutbox(d)
            sent=[]
            result=reopened.deliver(lambda b,h:(sent.append((b,h)) or
                receipt(h)))
            self.assertEqual(1,len(sent))
            self.assertEqual(0,reopened.pending_count())
            self.assertEqual("REMOTE_RECEIPT_RECORDED_NOT_INDEPENDENTLY_VERIFIED",result[0][1])
            self.assertEqual([],reopened.deliver(lambda *_:self.fail("duplicate")))
    def test_remote_bad_receipt_does_not_ack(self):
        with tempfile.TemporaryDirectory() as d:
            q=EvidenceOutbox(d)
            q.enqueue({"a":1})
            self.assertEqual("PENDING_EXTERNAL_ANCHOR",
                             q.deliver(lambda *_:{"sha256":"wrong","remote_id":"x"})[0][1])
            self.assertEqual(1,q.pending_count())
    def test_tamper_stays_pending_and_no_upload(self):
        with tempfile.TemporaryDirectory() as d:
            q=EvidenceOutbox(d)
            key=q.enqueue({"a":1})
            (Path(d)/"pending"/(key+".json")).write_text('{"a":2}')
            self.assertEqual("TAMPERED_LOCAL",q.deliver(lambda *_:self.fail("tamper sent"))[0][1])
            self.assertEqual(1,q.pending_count())
    def test_distinct_versions_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            q=EvidenceOutbox(d)
            self.assertNotEqual(q.enqueue({"version":1}),q.enqueue({"version":2}))
            self.assertEqual(2,q.pending_count())
if __name__=="__main__":
    unittest.main()
