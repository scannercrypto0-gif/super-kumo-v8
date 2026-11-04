"""Core #253 owner-approved A: private original-byte intake + native Scanner/Secretary.

This API accepts already-retained owner-authorized original source bytes and
an independent retained source manifest row. It does NOT retrieve, embed,
log or publish private source. Reuses pinned #211 RawVault and existing
Core #226/#253 processing; Scanner #227 native sealed contract is emitted as
UNKNOWN where independent historical universe/strategy evidence is missing.
Actual Factory ACK is separate; no fake real E2E/PIT/scientific approval.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import (
    admit_local_original, query_local, require, BackboneError,
)
from research_wp_r0.aql_core_secretary_routing_v1 import (
    enqueue_nomination, poll_nomination, route_trace,
)

PIN_SCHEMA = "aql.core.external-original-byte-pin.v1"
SCHEMA = "aql.core.authorized-original-intake.v1"
HEX = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z0-9_.:-]{1,160}$")
TIMEFRAME_WIDTH = {"15m": 900_000}
MAX_SOURCE = 8_000_000


def _check_identity(v):
    require(type(v) is str and IDENT.fullmatch(v) is not None,
            "AUTHORIZED_INTAKE_IDENTITY")


def _check_sha(v):
    require(type(v) is str and HEX.fullmatch(v) is not None,
            "AUTHORIZED_INTAKE_SHA")


def _shape(witness):
    """Explicit minimum source pin read from retained, preexisting inventory.

    Raw source bytes alone or a same-run newly generated hash cannot attest
    vendor origin. Caller must supply retained inventory separately.
    """
    fields = {
        "dataset_id","version","symbol","interval","exchange","market",
        "archive_name","csv_member_name","archive_sha256",
        "checksum_sha256","csv_member_sha256","archive_bytes",
        "checksum_bytes","start_ms","end_exclusive_ms","observed_bars",
        "capture_observed_at_ms",
    }
    require(type(witness) is dict and set(witness)==fields,
            "AUTHORIZED_RETAINED_INVENTORY_FIELDS")
    for k in ("dataset_id","symbol","interval","exchange","market",
              "archive_name","csv_member_name"):
        _check_identity(witness[k])
    for k in ("archive_sha256","checksum_sha256","csv_member_sha256"):
        _check_sha(witness[k])
    require(witness["exchange"]=="BINANCE" and witness["market"]=="SPOT"
            and witness["symbol"]=="BTCUSDT" and witness["interval"] in TIMEFRAME_WIDTH,
            "AUTHORIZED_SCOPE_NOT_APPROVED")
    require(witness["archive_name"]=="BTCUSDT-15m-"+(
            "2024-02" if witness["start_ms"]==1706745600000 else
            "2024-08" if witness["start_ms"]==1722470400000 else "NONE")+".zip",
            "AUTHORIZED_ARCHIVE_IDENTITY")
    require(witness["csv_member_name"] ==
            witness["archive_name"].removesuffix(".zip")+".csv",
            "AUTHORIZED_MEMBER_IDENTITY")
    width=TIMEFRAME_WIDTH[witness["interval"]]
    require(type(witness["version"]) is int and witness["version"]==1
            and all(type(witness[k]) is int and witness[k]>=0
                    for k in ("archive_bytes","checksum_bytes","start_ms",
                              "end_exclusive_ms","observed_bars"))
            and type(witness["capture_observed_at_ms"]) is int
            and witness["capture_observed_at_ms"]>witness["end_exclusive_ms"],
            "AUTHORIZED_INVENTORY_TIMING")
    require(0<witness["archive_bytes"]<=MAX_SOURCE
            and 0<witness["checksum_bytes"]<=512
            and 0<witness["observed_bars"]<=4096
            and witness["end_exclusive_ms"]-witness["start_ms"] ==
                witness["observed_bars"]*width,
            "AUTHORIZED_UNBOUNDED_OR_INCOMPLETE_WINDOW")


def run_authorized_original_intake(
    root, original_zip_bytes:bytes, original_checksum_bytes:bytes,
    retained_source_witness:dict, *, vault, cutoff_ms:int,
    strategy_id:str="HISTORICAL_UNAPPROVED", strategy_version:str="v1",
    message_id:str="HISTORICAL_UNKNOWN",
):
    """Real-original bytes→Vault RAW COMMITTED→Core query→native Scanner UNKNOWN→Secretary PENDING.

    A genuine Factory policy and position ledger is not simulated here.
    Source witness must be retained *prior* to this call by an authorized
    controller. This module NEVER upgrades 2024 historical known-at.
    """
    _shape(retained_source_witness)
    w=retained_source_witness
    require(type(original_zip_bytes) is bytes
            and type(original_checksum_bytes) is bytes
            and len(original_zip_bytes)==w["archive_bytes"]
            and len(original_checksum_bytes)==w["checksum_bytes"],
            "AUTHORIZED_ORIGINAL_BYTES_MISSING_OR_SIZE_DRIFT")
    require(hashlib.sha256(original_zip_bytes).hexdigest()==w["archive_sha256"]
            and hashlib.sha256(original_checksum_bytes).hexdigest()==w["checksum_sha256"],
            "AUTHORIZED_RETAINED_SHA_DRIFT")
    claimed=(w["archive_sha256"]+"  "+w["archive_name"]).encode("ascii")
    require(original_checksum_bytes.strip()==claimed,
            "AUTHORIZED_PUBLISHER_CHECKSUM_DRIFT")
    require(vault is not None and hasattr(vault,"admit") and
            hasattr(vault,"read") and hasattr(vault,"manifest_entries"),
            "PINNED_RAW_VAULT_REQUIRED_NOT_STAGE_ONLY")
    require(type(cutoff_ms) is int and cutoff_ms>=w["end_exclusive_ms"]
            and cutoff_ms<w["capture_observed_at_ms"],
            "AUTHORIZED_RETROSPECTIVE_CUTOFF_SCOPE")
    # The availability field deliberately stays null: contemporaneous 2024
    # custody evidence cannot be inferred from a 2026 observed download.
    pin={
        "schema":PIN_SCHEMA,"source_kind":"BINANCE_KLINES_ZIP",
        "original_object_id":w["dataset_id"],
        "original_sha256":w["archive_sha256"],
        "provenance_reference":"RETAINED_WORK247_OWNER_TRANSFER",
        "captured_at_ms":None,"claimed_available_at_ms":None,
        "expected_inventory_sha256":None,"vault_object_metadata":None,
        "universe_manifest_sha256":None,"universe_member_count":None,
        "test_only":False,"archive_name":w["archive_name"],
        "csv_member_name":w["csv_member_name"],
        "csv_member_sha256":w["csv_member_sha256"],
        "checksum_file_sha256":w["checksum_sha256"],
    }
    spec={
        "dataset_id":w["dataset_id"],"version":1,"symbol":w["symbol"],
        "interval":w["interval"],"exchange":w["exchange"],
        "market":w["market"],"source_label":"RETAINED_NATIVE_RETROSPECTIVE",
        "start_ms":w["start_ms"],
        "end_exclusive_ms":w["end_exclusive_ms"],
        "as_of_ms":cutoff_ms,
        "parent_source_sha256":None,"correction_reason":None,
        "test_only":False,
    }
    original=admit_local_original(
        root,original_zip_bytes,original_checksum_bytes,pin,spec,
        decision_cutoff_ms=cutoff_ms,vault=vault,
    )
    require(original["status"]=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
            and original["vault"]["vault"]=="EXISTING_PINNED_RAW_VAULT"
            and original["source_zip_sha256"]==w["archive_sha256"]
            and original["csv_member_sha256"]==w["csv_member_sha256"]
            and original["checksum_file_sha256"]==w["checksum_sha256"]
            and original["coverage"]=="COMPLETE"
            and original["bar_count"]==w["observed_bars"],
            "AUTHORIZED_RAW_CUSTODY_NOT_COMMITTED")
    prices=query_local(
        root,w["dataset_id"],1,w["start_ms"],w["end_exclusive_ms"],
        cutoff_ms,required_source_sha256=w["archive_sha256"],
        require_complete=True,
    )
    require(prices["coverage"]=="COMPLETE"
            and prices["available_bar_count"]==w["observed_bars"]
            and prices["source_availability"]=="RETROSPECTIVE_NON_PIT"
            and prices["historical_pit"]=="NOT_ATTESTED",
            "AUTHORIZED_PRICE_QUERY_FALSE_AUTHORITY")
    # Genuine #227 Scanner sealed native envelope with NO synthetic
    # price features, NO fabricated bid/ask/universe snapshot, and UNKNOWN.
    from tools.scanner_engine_offline.contracts import (
        ScannerNominationEnvelope,SourceManifest,
    )
    cutoff=datetime.fromtimestamp(cutoff_ms/1000, timezone.utc)
    manifest=SourceManifest(
        dataset_id=w["dataset_id"],dataset_sha=w["archive_sha256"],
        schema_version="AQL-SCANNER-V1",cutoff_at=cutoff,created_at=cutoff,
    )
    nomination=ScannerNominationEnvelope(
        scanner_id="CORE_253_AUTHENTIC_SOURCE_UNKNOWN",
        candidate_id=w["symbol"]+":"+cutoff.isoformat(),
        profile_id="NO_INDEPENDENT_UNIVERSE",
        market="BINANCE:SPOT:USDT",cutoff_at=cutoff,
        availability_class="RETROSPECTIVE_NON_PIT",stage="UNKNOWN",
        source_manifest=manifest.as_dict(),feature_snapshot={},
        reasons=["NO_HISTORICALLY_ATTESTED_MARKET_UNIVERSE",
                 "NO_CONFIRMED_STRATEGY_DECISION"],
        coverage={
            "source_grid":"COMPLETE","historical_known_at":"NOT_ATTESTED",
            "universe":"UNKNOWN","scanner_score":"NOT_COMPUTED",
        },
        score=None,score_status="SCORE_UNAVAILABLE",
        publishable=False,delivery_authorized=False,
    )
    nomination.seal()
    queue=enqueue_nomination(
        root,nomination.as_dict(),strategy_id=strategy_id,
        strategy_version=strategy_version,warehouse_receipt=original,
        lane="SLOW",idempotency_key=message_id,
    )
    queued=poll_nomination(root,now_ms=0,lane="SLOW")
    require(queued is not None and queued["message_id"]==message_id
            and queued["envelope"]["source_zip_sha256"]==w["archive_sha256"]
            and queued["envelope"]["scanner_nomination"]["stage"]=="UNKNOWN",
            "AUTHORIZED_SECRETARY_HANDED_OFF_WRONG_SOURCE")
    events=route_trace(root,message_id)
    require(events[-1]["state"]=="PENDING","SECRETARY_FALSE_DELIVERY_ACK")
    body={
        "schema":SCHEMA,"status":"AUTHORIZED_ORIGINAL_CORE_AND_SECRETARY_PENDING",
        "dataset_id":w["dataset_id"],
        "source_zip_sha256":w["archive_sha256"],
        "native_csv_member_sha256":w["csv_member_sha256"],
        "checksum_file_sha256":w["checksum_sha256"],
        "warehouse_receipt_sha256":original["receipt_sha256"],
        "warehouse_status":original["status"],
        "core_query_sha256":prices["query_sha256"],
        "source_coverage":prices["coverage"],
        "bar_count":prices["available_bar_count"],
        "strategy_id":strategy_id,"strategy_version":strategy_version,
        "scanner_nomination_digest":nomination.digest,
        "scanner_stage":"UNKNOWN","secretary_message_id":message_id,
        "secretary_payload_sha256":queue["payload_sha256"],
        "secretary_status":"PENDING_FACTORY_CONSUMER_ACK",
        "factory_lab_paper":"NOT_CONNECTED_UNTIL_OWNER_FACTORY_RUN",
        "historical_pit":"NOT_ATTESTED",
        "scientific_result":"INSUFFICIENT_EVIDENCE",
        "trading_authority":"NONE",
    }
    return {**body,"transfer_receipt_sha256":digest(body)},original,prices,queued
