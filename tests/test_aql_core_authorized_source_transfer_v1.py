"""Core #253: owner A private-source transfer interface; CI is TEST_ONLY.

Uses unchanged pinned #211 RawVault and #227 Scanner code, plus actual Core
backbone. Never includes real 2024 source or owner-private ZIP in GitHub.
"""
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile,ZIP_DEFLATED

from tools.raw_vault_offline.vault import RawVault
from research_wp_r0.aql_core_authorized_source_transfer_v1 import (
    run_authorized_original_intake,BackboneError,
)
from research_wp_r0.aql_core_secretary_routing_v1 import (
    acknowledge_nomination,poll_nomination,route_trace,
)

START=1706745600000
WIDTH=900000
N=4
SHA=lambda b:hashlib.sha256(b).hexdigest()


def synthetic_test_only():
    rows=[]
    for k in range(N):
        t=START+k*WIDTH
        rows.append(",".join(str(v) for v in (
            t, 100+k,102+k,99+k,101+k,5+k,t+WIDTH-1,
            500+k,10+k,2+k,200+k,0,
        )))
    csv=("\n".join(rows)+"\n").encode()
    archive="BTCUSDT-15m-2024-02.zip"
    member="BTCUSDT-15m-2024-02.csv"
    sink=BytesIO()
    with ZipFile(sink,"w",compression=ZIP_DEFLATED) as z:
        z.writestr(member,csv)
    raw=sink.getvalue()
    checksum=(SHA(raw)+"  "+archive+"\n").encode()
    witness={
        "dataset_id":"BINANCE-SPOT-BTCUSDT-15M-2024-02-DEV-v1",
        "version":1,"symbol":"BTCUSDT","interval":"15m",
        "exchange":"BINANCE","market":"SPOT",
        "archive_name":archive,"csv_member_name":member,
        "archive_sha256":SHA(raw),"checksum_sha256":SHA(checksum),
        "csv_member_sha256":SHA(csv),
        "archive_bytes":len(raw),"checksum_bytes":len(checksum),
        "start_ms":START,"end_exclusive_ms":START+N*WIDTH,
        "observed_bars":N,"capture_observed_at_ms":1790000000000,
    }
    return raw,checksum,witness


class AuthorizedTransferGate(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"core253"
        self.vault=RawVault(Path(self.tmp.name)/"raw211")
        self.raw,self.checksum,self.witness=synthetic_test_only()
        self.cutoff=START+N*WIDTH+10000

    def runit(self,raw=None,cs=None,witness=None,**kwargs):
        return run_authorized_original_intake(
            self.root,
            self.raw if raw is None else raw,
            self.checksum if cs is None else cs,
            self.witness if witness is None else witness,
            vault=self.vault,cutoff_ms=self.cutoff,
            message_id="TEST_2024_02",
            test_only=True,**kwargs,
        )

    def test_real_api_bytes_to_raw_query_native_scanner_secretary(self):
        receipt,w,q,msg=self.runit()
        self.assertEqual(receipt["status"],"TEST_ONLY_CORE_AND_SECRETARY_PENDING")
        self.assertEqual(receipt["source_classification"],"TEST_ONLY_FIXTURE")
        self.assertEqual(receipt["warehouse_status"],"OFFLINE_LOCAL_WAREHOUSE_COMMITTED")
        self.assertEqual(receipt["bar_count"],N)
        self.assertEqual(q["source_bytes_sha256"],SHA(self.raw))
        self.assertEqual(w["vault"]["vault"],"EXISTING_PINNED_RAW_VAULT")
        self.assertEqual(self.vault.read(SHA(self.raw)),self.raw)
        self.assertEqual(msg["envelope"]["scanner_nomination"]["stage"],"UNKNOWN")
        self.assertEqual(msg["envelope"]["scanner_nomination"]["score_status"],
                         "SCORE_UNAVAILABLE")
        self.assertEqual(msg["envelope"]["secretary_trading_authority"],"NONE")
        self.assertEqual(len(route_trace(self.root,"TEST_2024_02")),1)
        self.assertEqual(receipt["factory_lab_paper"],
                         "NOT_CONNECTED_UNTIL_OWNER_FACTORY_RUN")
        self.assertEqual(receipt["historical_pit"],"NOT_ATTESTED")
        self.assertEqual(self.runit()[0],receipt)
        self.assertEqual(len(self.vault.manifest_entries()),1)

    def test_private_original_integrity_refusal_without_partial_vault(self):
        with self.assertRaisesRegex(BackboneError,
                                    "AUTHORIZED_ORIGINAL_BYTES_MISSING_OR_SIZE_DRIFT"):
            self.runit(raw=self.raw+b"z")
        changed=bytes([self.raw[0]^1])+self.raw[1:]
        with self.assertRaisesRegex(BackboneError,"AUTHORIZED_RETAINED_SHA_DRIFT"):
            self.runit(raw=changed)
        with self.assertRaisesRegex(BackboneError,"AUTHORIZED_PUBLISHER_CHECKSUM_DRIFT"):
            wrong=(self.witness["archive_sha256"]+"  wrong.zip\n").encode()
            wit={**self.witness,"checksum_sha256":SHA(wrong),"checksum_bytes":len(wrong)}
            self.runit(cs=wrong,witness=wit)
        self.assertEqual(len(self.vault.manifest_entries()),0)

    def test_strict_intake_cutoff_and_no_raw_stage_only(self):
        with self.assertRaisesRegex(BackboneError,"AUTHORIZED_RETROSPECTIVE_CUTOFF_SCOPE"):
            run_authorized_original_intake(
                self.root,self.raw,self.checksum,self.witness,
                vault=self.vault,cutoff_ms=START, test_only=True,
            )
        with self.assertRaisesRegex(BackboneError,"PINNED_RAW_VAULT_REQUIRED"):
            run_authorized_original_intake(
                self.root,self.raw,self.checksum,self.witness,
                vault=None,cutoff_ms=self.cutoff, test_only=True,
            )
        with self.assertRaisesRegex(BackboneError,"AUTHORIZED_UNBOUNDED"):
            self.runit(witness={**self.witness,"observed_bars":4097})

    def test_deliberate_caller_ack_does_not_activate_factory_trading(self):
        receipt,w,q,msg=self.runit()
        id="TEST_2024_02"
        result=acknowledge_nomination(
            self.root,message_id=id,payload_sha256=msg["envelope"]["payload_sha256"],
            acknowledgement_sha256="a"*64,
        )
        self.assertEqual(result["state"],"ACKED")
        self.assertEqual([r["state"] for r in route_trace(self.root,id)],
                         ["PENDING","ACKED"])
        self.assertIsNone(poll_nomination(self.root,now_ms=0))
        self.assertEqual(receipt["factory_lab_paper"],
                         "NOT_CONNECTED_UNTIL_OWNER_FACTORY_RUN")


if __name__=="__main__":
    unittest.main()
