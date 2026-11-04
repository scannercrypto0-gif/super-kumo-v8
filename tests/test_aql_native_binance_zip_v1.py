"""Core #245: full native ZIP→original custody→price query TEST_ONLY gate.

This creates synthetic ZIP bytes in memory. It NEVER includes or reads the
retained Work-only 2024 originals. Original market provenance and PIT are
deliberately NOT_ATTESTED even when local SHA/checksum/CRC checks succeed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile
import unittest

from research_wp_r0.aql_archive_custody_bridge_v1 import (
    BridgeError, OfflineBridgeStager, raw_sha,
)
from research_wp_r0.aql_authenticated_historical_admission_v1 import (
    PIN_SCHEMA, SourceAdmissionError, admit_original_bytes,
)
from research_wp_r0.aql_native_price_custody_query_v1 import (
    PRICE_QUERY_SCHEMA, query_price_custody,
)
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.historical_library import HistoricalLibrary
from test_aql_archive_custody_bridge_v1 import START, N, WIDTH, spec


def native_source(*, change=0, bad_col=False, gap=False, future=False,
                  extra=False, filename=None):
    month = datetime.fromtimestamp(START/1000,timezone.utc).strftime("%Y-%m")
    basename=f"BTCUSDT-1m-{month}"
    csv_name=basename+".csv" if filename is None else filename
    rows=[]
    for i in range(N):
        opened=START+i*WIDTH+(WIDTH if gap and i == 2 else 0)
        if future and i == N-1:
            opened+=WIDTH
        row=[
            str(opened),str(100+i),str(102+i+change),str(99+i),
            str(101+i),str(5+i),str(opened+WIDTH-1),
            "505",str(10+i),"2","202","0"
        ]
        if bad_col and i==2:
            row=row[:-1]
        rows.append(",".join(row))
    csv_raw=("\n".join(rows)+"\n").encode()
    sink=BytesIO()
    with ZipFile(sink,"w",compression=ZIP_DEFLATED) as out:
        out.writestr(csv_name,csv_raw)
        if extra:
            out.writestr("unexpected.csv",b"1,2")
    source=sink.getvalue()
    checksum=(raw_sha(source)+"  "+basename+".zip\n").encode("ascii")
    pin={
        "schema":PIN_SCHEMA, "source_kind":"BINANCE_KLINES_ZIP",
        "original_object_id":"TEST_NATIVE_ZIP",
        "original_sha256":raw_sha(source),
        "provenance_reference":"TEST_ONLY_RETENTION",
        "captured_at_ms":START+N*WIDTH+10000,
        "claimed_available_at_ms":None,
        "expected_inventory_sha256":None,
        "vault_object_metadata":None,
        "universe_manifest_sha256":None,
        "universe_member_count":None,
        "test_only":True,
        "archive_name":basename+".zip",
        "csv_member_name":csv_name,
        "csv_member_sha256":raw_sha(csv_raw),
        "checksum_file_sha256":raw_sha(checksum),
    }
    return source,csv_raw,checksum,pin


def request(s, cutoff, *, confirmed_only=False):
    return {
        "schema":REQUEST_SCHEMA,"dataset_id":s["dataset_id"],
        "version":s["version"],"start_ms":s["start_ms"],
        "end_exclusive_ms":s["end_exclusive_ms"],
        "decision_cutoff_ms":cutoff,
        "require_complete":False,"confirmed_only":confirmed_only,
    }


class NativeZipCustodyGate(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.stager=OfflineBridgeStager(self.temp.name)
        self.library=HistoricalLibrary()
        self.s=spec(source_label="native-monthly-zip")
        self.raw,self.csv,self.checksum,self.pin=native_source()
        self.cutoff=START+N*WIDTH+2000

    def admit(self, *, raw=None, pin=None, checksum=None, s=None, cutoff=None):
        return admit_original_bytes(
            self.raw if raw is None else raw,
            self.pin if pin is None else pin,
            self.s if s is None else s,
            stager=self.stager,library=self.library,
            decision_cutoff_ms=self.cutoff if cutoff is None else cutoff,
            checksum_file_bytes=self.checksum if checksum is None else checksum,
        )

    def price(self, admitted, *, s=None, cutoff=None, confirmed_only=False):
        s=self.s if s is None else s
        return query_price_custody(
            self.library,request(
                s,self.cutoff if cutoff is None else cutoff,
                confirmed_only=confirmed_only,
            ),
            expected_source_sha256=admitted["source_bytes_sha256"],
            expected_manifest_integrity_sha256=admitted["manifest_integrity_sha256"],
        )

    def test_original_zip_crc_csv_checksum_and_price_query_idempotent(self):
        original=self.admit()
        self.assertEqual(original,self.admit())
        self.assertEqual(original["status"],"TEST_ONLY_INTEGRITY_VERIFIED")
        self.assertEqual(original["source_bytes_sha256"],raw_sha(self.raw))
        self.assertEqual(original["native_csv_member_sha256"],raw_sha(self.csv))
        self.assertEqual(original["native_checksum_file_sha256"],raw_sha(self.checksum))
        self.assertEqual(original["coverage"],"COMPLETE")
        self.assertEqual(original["authenticated_source"],"NOT_ATTESTED")
        self.assertEqual(original["confirmed_pit"],"NOT_ATTESTED")
        price=self.price(original)
        self.assertEqual(price["schema"],PRICE_QUERY_SCHEMA)
        self.assertEqual(price["status"],"OK")
        self.assertEqual(price["coverage"],"COMPLETE")
        self.assertEqual(price["available_bar_count"],N)
        self.assertEqual(price["bars"][0]["open"],100.)
        self.assertEqual(price["bars"][0]["close"],101.)
        self.assertEqual(price["bars"][0]["volume"],5.)
        self.assertIsNone(price["bars"][0]["historical_known_at_ms"])
        self.assertEqual(price["source_availability"],"RETROSPECTIVE_NON_PIT")
        self.assertEqual(price["factory_scientific_input"],
                         "BLOCKED_PENDING_INDEPENDENT_EVIDENCE")

    def test_real_format_without_test_flag_still_not_authenticated(self):
        s=spec(test_only=False,source_label="retained-native-unverified")
        pin={**self.pin,"test_only":False}
        result=self.admit(s=s,pin=pin)
        self.assertEqual(result["status"],"ORIGINAL_PIN_MATCHED_PROVENANCE_PENDING")
        self.assertEqual(result["confirmed_pit"],"NOT_ATTESTED")
        self.assertEqual(result["source_available_at_cutoff"],"NOT_ATTESTED")
        self.assertEqual(self.price(result,s=s)["status"],"OK")

    def test_modified_zip_and_wrong_member_hash_rejected(self):
        with self.assertRaisesRegex(SourceAdmissionError,"ORIGINAL_BYTE_SHA_MISMATCH"):
            self.admit(raw=self.raw+b"\x00")
        with self.assertRaisesRegex(BridgeError,"NATIVE_ZIP_MEMBER_SHA_MISMATCH"):
            self.admit(pin={**self.pin,"csv_member_sha256":"0"*64})
        with self.assertRaisesRegex(BridgeError,"NATIVE_ZIP_CHECKSUM_ASSERTION"):
            alt=(("0"*64)+"  "+self.pin["archive_name"]+"\n").encode()
            p={**self.pin,"checksum_file_sha256":raw_sha(alt)}
            self.admit(pin=p,checksum=alt)

    def test_checksum_file_hash_and_missing_original_checksum_denied(self):
        with self.assertRaisesRegex(BridgeError,"NATIVE_ZIP_CHECKSUM_FILE_SHA_MISMATCH"):
            self.admit(checksum=self.checksum+b" ")
        with self.assertRaisesRegex(SourceAdmissionError,"NATIVE_ZIP_CHECKSUM_FILE_REQUIRED"):
            admit_original_bytes(
                self.raw,self.pin,self.s,stager=self.stager,
                library=self.library,decision_cutoff_ms=self.cutoff,
            )

    def test_path_traversal_and_multiple_member_denied(self):
        source, member, checksum, pin=native_source(filename="../escape.csv")
        with self.assertRaisesRegex(BridgeError,"NATIVE_ZIP_MEMBER_NAME"):
            self.admit(raw=source,pin=pin,checksum=checksum)
        source, member, checksum, pin=native_source(extra=True)
        with self.assertRaisesRegex(BridgeError,"NATIVE_ZIP_MEMBER_CENSUS"):
            self.admit(raw=source,pin=pin,checksum=checksum)

    def test_native_12_columns_and_grid_missing_or_future_rejected(self):
        for opts in ({"bad_col":True},{"gap":True},{"future":True}):
            with self.subTest(opts=opts):
                raw,member,cs,pin=native_source(**opts)
                with self.assertRaisesRegex(BridgeError,"NATIVE_ZIP_"):
                    self.admit(raw=raw,pin=pin,checksum=cs)

    def test_partial_and_unknown_price_grid_and_confirmed_fail_closed(self):
        admitted=self.admit(cutoff=START+WIDTH+1000)
        p=self.price(admitted,cutoff=START+WIDTH+1000)
        self.assertEqual(p["status"],"OK")
        self.assertEqual(p["coverage"],"PARTIAL")
        self.assertEqual(p["available_bar_count"],1)
        self.assertEqual(len(p["missing_bar_opens"]),N-1)
        self.assertEqual(self.price(admitted,cutoff=START)["coverage"],"UNKNOWN")
        denied=self.price(admitted,confirmed_only=True)
        self.assertEqual(denied["status"],"ERROR")
        self.assertEqual(denied["error"],"PRICE_QUERY_RETROSPECTIVE_ONLY")

    def test_price_pin_mismatch_and_tampered_bar_rejected(self):
        adm=self.admit()
        mismatch=query_price_custody(
            self.library,request(self.s,self.cutoff),
            expected_source_sha256="0"*64,
            expected_manifest_integrity_sha256=adm["manifest_integrity_sha256"],
        )
        self.assertEqual(mismatch["error"],"PRICE_QUERY_PIN_OR_SCOPE_MISMATCH")
        # Forbidden mutation of a stored bar must fail checksum at query.
        stored=self.library._datasets[self.s["dataset_id"]][1][0][0]
        object.__setattr__(stored,"close",900.)
        tampered=self.price(adm)
        self.assertEqual(tampered["status"],"ERROR")
        self.assertIn(tampered["error"],(
            "PRICE_QUERY_BAR_INVALID","PRICE_QUERY_CUSTODY_DRIFT",
            "PRICE_QUERY_CORE_QUERY_REJECTED",
        ))

    def test_correction_version_parent_and_replay_source_integrity(self):
        first=self.admit()
        raw,csv,checksum,pin=native_source(change=2)
        s=spec(version=2,source_label="native-monthly-zip",
               parent_source_sha256=raw_sha(self.raw),
               correction_reason="TEST_ONLY_NATIVE_CORRECTION")
        corrected=self.admit(raw=raw,pin=pin,s=s,checksum=checksum)
        self.assertNotEqual(first["source_bytes_sha256"],
                            corrected["source_bytes_sha256"])
        self.assertEqual(corrected["correction_parent_source_sha256"],
                         raw_sha(self.raw))
        fresh=HistoricalLibrary()
        self.stager.replay_committed(fresh)
        old=fresh.get_manifest(self.s["dataset_id"],1)
        new=fresh.get_manifest(self.s["dataset_id"],2)
        self.assertEqual(old.source_hash,raw_sha(self.raw))
        self.assertEqual(new.source_hash,raw_sha(raw))
        with self.assertRaises(BridgeError):
            raw2,csv2,cs2,pin2=native_source(change=4)
            self.admit(raw=raw2,pin=pin2,s=s,checksum=cs2)

    def test_claimed_future_availability_rejected_without_pit_upgrade(self):
        with self.assertRaisesRegex(SourceAdmissionError,"CLAIMED_SOURCE_UNAVAILABLE"):
            self.admit(pin={**self.pin,
                            "claimed_available_at_ms":self.cutoff+1})
        first=self.admit()
        self.assertEqual(first["source_available_at_cutoff"],"NOT_ATTESTED")


if __name__=="__main__":
    unittest.main()
