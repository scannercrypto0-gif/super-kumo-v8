"""Offline bridge G6 consolidated fixture: synthetic only, no real custody claims."""
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.aql.archive.contracts import canonical as archive_canonical, digest as archive_digest, market_envelope
from src.aql.models.bar import BarState, MarketBar
from research_wp_r0.historical_library import HistoricalLibrary, HistoricalDataError
from research_wp_r0.aql_archive_custody_bridge_v1 import (
    BridgeError, OfflineBridgeStager, canonical, custody_range, digest,
    export_archive_query, export_vault_csv, raw_sha, verify_packet,
)

START = 1700000040000
WIDTH = 60000
H = "a" * 64
N = 4


def spec(**changes):
    base = dict(dataset_id="BTCUSDT_1m_B3", version=1, symbol="BTCUSDT",
                interval="1m", exchange="BINANCE", market="SPOT",
                source_label="existing-sealed-archive",
                start_ms=START, end_exclusive_ms=START+N*WIDTH,
                as_of_ms=START+N*WIDTH+5000,
                parent_source_sha256=None, correction_reason=None,
                test_only=True)
    base.update(changes)
    return base


def archive_payload(*, gap=False, nonfinal=False, future=False, mutation=0):
    records=[]
    for i in range(N):
        if gap and i == 1:
            continue
        opened = START+i*WIDTH
        bar = MarketBar(symbol="BTCUSDT", interval="1m",
                        bar_open=opened, bar_close=opened+WIDTH-1,
                        open=100+i, high=102+i+mutation,
                        low=99+i, close=101+i, volume=5+i,
                        is_final=not(nonfinal and i==1),
                        source="original-journal",
                        ingested_at=opened+WIDTH+1000 if not(future and i==2)
                        else START+N*WIDTH+15000,
                        committed_at=None,state=BarState.RECEIVED).with_checksum()
        records.append(market_envelope(
            {"id":i+1,"stable_key":bar.stable_key(),
             "payload_json":json.dumps(bar.to_dict()),
             "checksum":bar.compute_checksum()},
            journal_id="JOURNAL-TEST",market="SPOT",build="TEST",policy="TEST",
            cutoff_ms=START+N*WIDTH+30000))
    raw=archive_canonical({
        "schema":"aql.offline-archive-query.v1",
        "inventory_hash":H,
        "selection":{"symbol":"BTCUSDT","interval":"1m",
                     "start_open_ms":START,
                     "end_open_ms_exclusive":START+N*WIDTH},
        "records":records,"count":len(records),
        "record_content_hash":archive_digest(records),
        "coverage":"ARCHIVED_RECORDS_ONLY_NOT_FULL_MARKET",
        "retrospective_only":True,"pit_eligibility":"NOT_ATTESTED",
        "independent_custody_verified":False})
    return raw


def exported(raw=None, the_spec=None):
    raw=archive_payload() if raw is None else raw
    p=export_archive_query(raw,expected_source_sha256=raw_sha(raw),
                           expected_inventory_hash=H,
                           spec=spec() if the_spec is None else the_spec)
    return p,raw


def staged(folder, packet=None, raw=None):
    if packet is None:
        packet,raw=exported()
    stager=OfflineBridgeStager(folder)
    key=stager.stage(packet,raw)
    return stager,key


def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat().replace("+00:00","Z")


def vault_payload(*,mutation=0):
    raw=("\n".join(
        f"{START+i*WIDTH},{START+(i+1)*WIDTH-1},100,{102+mutation},99,101,5"
        for i in range(N))+"\n").encode()
    meta={"schema_version":"raw_object.v1","content_sha256":raw_sha(raw),
          "byte_length":len(raw),"source_format":"RAW_CSV",
          "instrument":"BTCUSDT","market":"SPOT","interval":"1m",
          "vendor":"FIXTURE_TEST","format_version":"v1",
          "coverage_start_utc":iso(START),
          "coverage_end_utc":iso(START+N*WIDTH),
          "correction_generation":0,"parent_content_sha256":"",
          "trust_status":"UNVERIFIED","evidence_class":"FIXTURE_SYNTHETIC",
          "admitted_at_utc":iso(START+N*WIDTH+2000)}
    meta["logical_identity_key"] = digest({k: meta[k] for k in (
        "vendor","instrument","market","interval","coverage_start_utc",
        "coverage_end_utc","source_format","format_version")})
    return raw,meta


class OfflineArchiveCustodyBridgeG6(unittest.TestCase):
    def test_g1_archive_verified_export_deterministic(self):
        p,raw=exported()
        self.assertEqual(p,exported(raw)[0])
        self.assertEqual(p["packet_sha256"],
                         digest({k:v for k,v in p.items() if k!="packet_sha256"}))
        self.assertEqual(p["source_bytes_sha256"],raw_sha(raw))
        self.assertEqual(p["availability_class"],"RETROSPECTIVE_NOT_CONFIRMED")
        self.assertFalse(p["external_custody_verified"])
        self.assertEqual(len(p["bars"]),N)
        verify_packet(p,raw)

    def test_g2_single_staged_commit_query_and_idempotency(self):
        with TemporaryDirectory() as temp:
            stager,key=staged(temp)
            self.assertEqual(stager.advance(key,batch_size=2),(2,4))
            self.assertEqual(stager.advance(key,batch_size=2),(4,4))
            library=HistoricalLibrary()
            receipt=stager.commit(key,library)
            self.assertEqual(receipt["bar_count"],N)
            self.assertEqual(receipt["destination"],"HISTORICAL_LIBRARY_IN_MEMORY_ONLY")
            self.assertEqual(stager.commit(key,library),receipt)
            queried=custody_range(library,spec()["dataset_id"],START,
                                 START+N*WIDTH,START+N*WIDTH+2000)
            self.assertEqual(queried["status"],"COMPLETE")
            self.assertEqual(queried["available_bar_count"],4)
            self.assertEqual(queried["availability_class"],"SYNTHETIC_TEST")

    def test_g3_partial_cutoff_and_no_pit_upgrade(self):
        with TemporaryDirectory() as temp:
            stager,key=staged(temp)
            stager.advance(key,batch_size=N)
            library=HistoricalLibrary();stager.commit(key,library)
            q=custody_range(library,spec()["dataset_id"],START,START+N*WIDTH,
                           START+WIDTH+1000,require_complete=False)
            self.assertEqual(q["status"],"PARTIAL")
            self.assertEqual(q["available_bar_count"],1)
            self.assertEqual(len(q["missing_bar_opens"]),3)
            with self.assertRaisesRegex(BridgeError,"INCOMPLETE_OR_FUTURE"):
                custody_range(library,spec()["dataset_id"],START,
                              START+N*WIDTH,START+WIDTH+1000)
            with self.assertRaisesRegex(BridgeError,"INCOMPLETE_OR_FUTURE"):
                custody_range(library,spec()["dataset_id"],START,
                              START+N*WIDTH,START+N*WIDTH+2000,
                              confirmed_only=True)
            q=custody_range(library,spec()["dataset_id"],START,START+N*WIDTH,
                           START+N*WIDTH+2000,
                           confirmed_only=True,require_complete=False)
            self.assertEqual((q["status"],q["available_bar_count"]),("UNKNOWN",0))

    def test_g4_interruption_restarts_at_bounded_checkpoint(self):
        with TemporaryDirectory() as temp:
            s,key=staged(temp)
            self.assertEqual(s.advance(key,batch_size=1),(1,4))
            recovered=OfflineBridgeStager(temp)
            self.assertEqual(recovered.stage(*exported()),key)
            self.assertEqual(recovered.advance(key,batch_size=2),(3,4))
            with self.assertRaisesRegex(BridgeError,"INCOMPLETE_BATCH_CHECKPOINT"):
                recovered.commit(key,HistoricalLibrary())
            self.assertEqual(recovered.advance(key,batch_size=2),(4,4))
            lib=HistoricalLibrary()
            receipt=recovered.commit(key,lib)
            restarted=HistoricalLibrary()
            self.assertEqual(recovered.replay_committed(restarted),[receipt])
            self.assertEqual(restarted.get_manifest(spec()["dataset_id"]).source_hash,
                             exported()[0]["source_bytes_sha256"])

    def test_g5_correction_append_versions_and_reject_rewrite(self):
        with TemporaryDirectory() as temp:
            stager,key=staged(temp)
            stager.advance(key,batch_size=N)
            library=HistoricalLibrary();stager.commit(key,library)
            prior=library.get_manifest(spec()["dataset_id"],1)
            changed=archive_payload(mutation=3)
            corrected,rr=exported(changed,spec(version=2,
                                  parent_source_sha256=raw_sha(archive_payload()),
                                  correction_reason="ARCHIVE_NEW_VERSION"))
            second=stager.stage(corrected,rr)
            stager.advance(second,batch_size=N)
            receipt=stager.commit(second,library)
            self.assertEqual(receipt["version"],2)
            self.assertEqual(library.get_manifest(spec()["dataset_id"],1),prior)
            self.assertEqual(library.get_manifest(spec()["dataset_id"],2).parent_version,1)
            changed_again=archive_payload(mutation=4)
            colliding,rr=exported(changed_again,spec(version=2,
                                    parent_source_sha256=raw_sha(archive_payload()),
                                    correction_reason="OTHER_CORRECTION"))
            key3=stager.stage(colliding,rr);stager.advance(key3,batch_size=N)
            with self.assertRaisesRegex(BridgeError,"EXISTING_VERSION_CONTENT_CONFLICT"):
                stager.commit(key3,library)

    def test_g5_bad_correction_parent_fails(self):
        with TemporaryDirectory() as temp:
            s,key=staged(temp);s.advance(key,batch_size=N)
            lib=HistoricalLibrary();s.commit(key,lib)
            raw=archive_payload(mutation=2)
            p,r=exported(raw,spec(version=2,parent_source_sha256="c"*64,
                                  correction_reason="BAD_PARENT"))
            second=s.stage(p,r);s.advance(second,batch_size=N)
            with self.assertRaisesRegex(BridgeError,"CORRECTION_PARENT_SOURCE_MISMATCH"):
                s.commit(second,lib)

    def test_archive_payload_record_hash_tamper(self):
        raw=archive_payload()
        doc=json.loads(raw)
        doc["records"][0]["bar"]["close"]=900
        forged=archive_canonical(doc)
        with self.assertRaisesRegex(BridgeError,"ARCHIVE_RECORD_DIGEST"):
            exported(forged)

    def test_archive_record_rehashed_forged_availability_rejected(self):
        doc=json.loads(archive_payload())
        record=doc["records"][0]
        record["availability_kind"]="CONFIRMED"
        record["envelope_hash"]=digest({k:v for k,v in record.items()
                                        if k!="envelope_hash"})
        doc["record_content_hash"]=digest(doc["records"])
        with self.assertRaisesRegex(BridgeError,"ARCHIVE_AVAILABILITY_UPGRADE"):
            exported(archive_canonical(doc))

    def test_gap_and_nonfinal_fail_closed(self):
        with self.assertRaisesRegex(BridgeError,"INCOMPLETE_COHORT_COVERAGE"):
            exported(archive_payload(gap=True))
        # market_envelope itself must stop a non-final archive row.
        with self.assertRaises(ValueError):
            archive_payload(nonfinal=True)

    def test_future_receipt_rejected(self):
        with self.assertRaisesRegex(BridgeError,"FUTURE_OR_INCONSISTENT_RECEIPT"):
            exported(archive_payload(future=True))

    def test_source_sha_inventory_and_scope_pins(self):
        raw=archive_payload()
        with self.assertRaisesRegex(BridgeError,"ARCHIVE_SOURCE_BYTES_SHA_MISMATCH"):
            export_archive_query(raw,expected_source_sha256="f"*64,
                                 expected_inventory_hash=H,spec=spec())
        with self.assertRaisesRegex(BridgeError,"ARCHIVE_EVIDENCE_BOUNDARY"):
            export_archive_query(raw,expected_source_sha256=raw_sha(raw),
                                 expected_inventory_hash="f"*64,spec=spec())
        with self.assertRaisesRegex(BridgeError,"ARCHIVE_SCOPE_MISMATCH"):
            exported(raw,spec(symbol="ETHUSDT"))

    def test_stage_packet_and_source_bytes_tamper_rejected(self):
        with TemporaryDirectory() as temp:
            stager,key=staged(temp)
            folder=Path(temp)/key
            path=folder/"packet.json"
            doc=json.loads(path.read_bytes());doc["bars"][0]["close"]=888
            path.write_bytes(canonical(doc))
            with self.assertRaisesRegex(BridgeError,"PACKET_DIGEST_MISMATCH"):
                stager.advance(key)

    def test_stage_source_tamper_rejected(self):
        with TemporaryDirectory() as temp:
            stager,key=staged(temp)
            (Path(temp)/key/"source.bin").write_bytes(b"corrupt")
            with self.assertRaisesRegex(BridgeError,"PACKET_SOURCE_SHA_MISMATCH"):
                stager.advance(key)

    def test_checkpoint_tamper_rejected(self):
        with TemporaryDirectory() as temp:
            stager,key=staged(temp)
            path=Path(temp)/key/"checkpoint.json"
            doc=json.loads(path.read_bytes());doc["verified_rows"]=4
            path.write_bytes(canonical(doc))
            with self.assertRaisesRegex(BridgeError,"INVALID_STAGE_CHECKPOINT"):
                stager.advance(key)

    def test_vault_explicit_synthetic_boundary_and_csv(self):
        raw,meta=vault_payload()
        with self.assertRaisesRegex(BridgeError,"SYNTHETIC_NOT_REAL_SOURCE"):
            export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                             object_metadata=meta,spec=spec(test_only=False))
        p=export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                           object_metadata=meta,spec=spec())
        self.assertEqual(len(p["bars"]),4)
        self.assertEqual(p["source_meta"]["kind"],"RAW_VAULT_OBJECT")
        with TemporaryDirectory() as temp:
            s,key=staged(temp,p,raw)
            s.advance(key,batch_size=4)
            self.assertEqual(s.commit(key,HistoricalLibrary())["bar_count"],4)

    def test_vault_wrong_object_identity_or_format(self):
        raw,meta=vault_payload()
        meta["source_format"]="ZIP_CSV"
        with self.assertRaisesRegex(BridgeError,"VAULT_OBJECT_IDENTITY_OR_FORMAT"):
            export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                             object_metadata=meta,spec=spec())
        meta["source_format"]="RAW_CSV";meta["content_sha256"]="d"*64
        with self.assertRaisesRegex(BridgeError,"VAULT_OBJECT_IDENTITY_OR_FORMAT"):
            export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                             object_metadata=meta,spec=spec())

    def test_vault_correction_lineage_and_no_overwrite(self):
        raw,meta=vault_payload()
        meta["correction_generation"]=1
        meta["parent_content_sha256"]="a"*64
        with self.assertRaisesRegex(BridgeError,"VAULT_CORRECTION_LINEAGE"):
            export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                             object_metadata=meta,spec=spec())
        p=export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                           object_metadata=meta,spec=spec(version=2,
                                parent_source_sha256="a"*64,
                                correction_reason="RETAINED_CORRECTION"))
        self.assertEqual(p["spec"]["version"],2)

    def test_existing_archive_adapter_is_read_only_source_boundary(self):
        from unittest.mock import patch
        from research_wp_r0.aql_archive_custody_bridge_v1 import export_existing_archive_backup
        raw=archive_payload()
        with patch("src.aql.archive.offline.snapshot", return_value=raw) as snap:
            packet, same_raw=export_existing_archive_backup(
                "/detached/sealed-backup",expected_inventory_hash=H,spec=spec())
        self.assertEqual(same_raw,raw)
        self.assertEqual(packet,exported(raw)[0])
        self.assertEqual(snap.call_count,1)
        self.assertEqual(snap.call_args.kwargs["expected_digest"],H)

    def test_existing_vault_adapter_uses_original_readback_only(self):
        from research_wp_r0.aql_archive_custody_bridge_v1 import export_existing_raw_vault
        raw,meta=vault_payload()
        class OnlyReadVault:
            def read(self, content_sha256):
                if content_sha256!=raw_sha(raw):
                    raise ValueError("Wrong content pin")
                return raw
            def manifest_entries(self):
                return [meta]
        packet,same_raw=export_existing_raw_vault(
            OnlyReadVault(),content_sha256=raw_sha(raw),spec=spec())
        self.assertEqual(same_raw,raw)
        self.assertEqual(packet["source_meta"]["object"],meta)

    def test_vault_forged_identity_or_future_admission_rejected(self):
        raw,meta=vault_payload()
        meta["logical_identity_key"]="f"*64
        with self.assertRaisesRegex(BridgeError,"VAULT_LOGICAL_IDENTITY_MISMATCH"):
            export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                             object_metadata=meta,spec=spec())
        _,meta=vault_payload()
        meta["admitted_at_utc"]=iso(spec()["as_of_ms"]+1000)
        with self.assertRaisesRegex(BridgeError,"FUTURE_VAULT_ADMISSION"):
            export_vault_csv(raw,expected_source_sha256=raw_sha(raw),
                             object_metadata=meta,spec=spec())

    def test_invalid_price_after_source_rehash_rejected(self):
        raw,meta=vault_payload()
        bad=raw.replace(b",100,102,99,101,5",b",100,98,99,101,5")
        meta["content_sha256"]=raw_sha(bad);meta["byte_length"]=len(bad)
        with self.assertRaisesRegex(BridgeError,"INVALID_OHLCV"):
            export_vault_csv(bad,expected_source_sha256=raw_sha(bad),
                             object_metadata=meta,spec=spec())


if __name__=="__main__":
    unittest.main()
