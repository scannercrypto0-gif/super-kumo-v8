"""ATLAS Core D: byte-level synthetic same-source proof + canonical Scanner→Core route.

One TEST_ONLY cohort is independently read back from existing #211 RawVault,
compared to actual #245 and #253 queries, and reprojected into the *actual*
Scanner C JSON bytes. Only those exact rows may enter a research-only
strategy Secretary queue. No publisher checksum, historical PIT, operational
Scanner, trading approval, or broker capability is inferred.

The old historical original ZIP paired with an unrelated Scanner synthetic
JSON continues through C's existing disconnected WAIT interface unchanged.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
from zipfile import ZipFile, BadZipFile

from research_wp_r0.aql_archive_custody_bridge_v1 import digest
from research_wp_r0.aql_core_backbone_local_v1 import require
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import (
    make_strategy_route_request, enqueue_strategy_route,
    strategy_route_snapshot, _verify_source_ack,
    REQUEST_SCHEMA as INTERNAL_REQUEST_SCHEMA,
    APPROVAL_SCHEMA as INTERNAL_APPROVAL_SCHEMA,
)
from research_wp_r0.aql_core_backbone_local_v1 import _connect

SCHEMA = "aql.core.d.synthetic-same-source-proof.v1"
BRIDGE_SCHEMA = "aql.core.d.canonical-scanner-strategy-binding.v1"
WIDTH = 900_000
MAX_BARS = 4096
MAX_BYTES = 8_000_000
ROWS_FIELDS = frozenset((
    "symbol","timeframe","source_id","open_ms","close_ms","available_ms",
    "finalized","open","high","low","close","volume",
))


def _hash(value):
    return hashlib.sha256(value).hexdigest()


def _sealed(value, key):
    require(type(value) is dict and digest({k:v for k,v in value.items() if k!=key})
            == value.get(key),"CORE_D_PARENT_SEAL_MISMATCH")


def _source_ack_present(root, warehouse, source_ack):
    _sealed(source_ack,"receipt_sha256")
    con=_connect(root)
    try:
        mid=source_ack.get("message_id")
        row=con.execute("SELECT delivery_json FROM distribution_outbox WHERE message_id=?",
                        (mid,)).fetchone()
        require(row is not None,"CORE_D_SOURCE_ACK_NOT_DURABLE")
        envelope=json.loads(row[0])
        request={
            "source_ack_sha256":source_ack["receipt_sha256"],
            "strategy_id":envelope["strategy_id"],
            "strategy_version":envelope["strategy_version"],
            "source_zip_sha256":warehouse["source_zip_sha256"],
            "manifest_integrity_sha256":warehouse["manifest_integrity_sha256"],
            "warehouse_receipt_sha256":warehouse["receipt_sha256"],
            "scanner_nomination_sha256":envelope["scanner_nomination"]["digest"],
        }
        _verify_source_ack(con,request,source_ack,envelope["scanner_nomination"])
        return envelope
    finally:
        con.close()



def project_test_only_scanner_native15m(
    vault, *, synthetic_zip_bytes, native_price_query, core_local_query,
    identity_map, warehouse_receipt,
):
    """Produce the exact read-only Scanner B/C native15m input from Core query.

    This is a deterministic byte projection of TEST_ONLY, already-pinned
    Core 15m source bars. It uses the *existing* Core index and #211 vault.
    No new warehouse, publisher-source acquisition, resampling or PIT claim.
    """
    from tools.strategy_service_offline.common import canonical
    require(type(synthetic_zip_bytes) is bytes
            and 0<len(synthetic_zip_bytes)<=MAX_BYTES,
            "CORE_D_PROJECTION_SOURCE_BYTES_REQUIRED")
    _sealed(warehouse_receipt,"receipt_sha256")
    require(warehouse_receipt.get("test_only") is True
            and warehouse_receipt.get("status")==
                "OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
            and warehouse_receipt.get("symbol")=="AAA"
            and warehouse_receipt.get("interval")=="15m"
            and warehouse_receipt.get("availability")=="RETROSPECTIVE_NON_PIT"
            and warehouse_receipt.get("historical_known_at")=="NOT_ATTESTED",
            "CORE_D_PROJECTION_SYNTHETIC_SCOPE")
    zip_sha=_hash(synthetic_zip_bytes)
    require(zip_sha==warehouse_receipt["source_zip_sha256"]
            and vault.read(zip_sha)==synthetic_zip_bytes,
            "CORE_D_PROJECTION_VAULT_READBACK")
    mapping=bind_dual_query_identities(
        native_price_query,core_local_query,warehouse_receipt)
    require(mapping["identity_map_sha256"]==
            identity_map.get("identity_map_sha256"),
            "CORE_D_PROJECTION_QUERY_PARENT_DRIFT")
    try:
        with ZipFile(io.BytesIO(synthetic_zip_bytes)) as source:
            members=source.namelist()
            require(len(members)==1 and
                    members[0].startswith("AAA-15m-") and
                    members[0].endswith(".csv"),
                    "CORE_D_PROJECTION_TEST_MEMBER")
            original_csv=source.read(members[0])
            require(source.testzip() is None,
                    "CORE_D_PROJECTION_ZIP_CRC")
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("CORE_D_PROJECTION_TEST_ZIP_FORMAT") from exc
    require(_hash(original_csv)==warehouse_receipt["csv_member_sha256"],
            "CORE_D_PROJECTION_MEMBER_SHA")
    bars=core_local_query.get("bars")
    require(type(bars) is list and 0<len(bars)<=MAX_BARS
            and len(bars)==len(original_csv.splitlines())
            and len(bars)==warehouse_receipt["bar_count"],
            "CORE_D_PROJECTION_CENSUS")
    output=[]
    def number(value):
        require(type(value) in (int,float) and math.isfinite(value),
                "CORE_D_PROJECTION_FINITE_NUMBER")
        return int(value) if float(value).is_integer() else value
    for line,bar in zip(original_csv.splitlines(),bars):
        parts=line.split(b",")
        require(len(parts)==12 and parts[0].isdigit() and parts[6].isdigit(),
                "CORE_D_PROJECTION_NATIVE_CSV")
        opened=int(parts[0]); closed=int(parts[6])
        try:
            vals=tuple(float(parts[j]) for j in (1,2,3,4,5))
        except (ValueError,TypeError,OverflowError) as exc:
            raise ValueError("CORE_D_PROJECTION_BAD_CSV_PRICE") from exc
        require(all(math.isfinite(v) for v in vals)
                and opened==bar["bar_open_ms"]
                and closed==bar["bar_close_ms"]
                and closed==opened+WIDTH-1
                and tuple(bar[k] for k in ("open","high","low","close","volume"))==vals
                and bar["historical_known_at_ms"] is None,
                "CORE_D_PROJECTION_NATIVE_CORE_BAR_MISMATCH")
        output.append({
            "symbol":"AAA","timeframe":"15m","source_id":"generator",
            "open_ms":opened,"close_ms":closed,
            "available_ms":closed+1,"finalized":True,
            "open":number(vals[0]),"high":number(vals[1]),
            "low":number(vals[2]),"close":number(vals[3]),
            "volume":number(vals[4]),
        })
    raw=canonical({
        "schema":"aql.strategy-service.synthetic-bars.v1",
        "source_id":"generator","generation_id":"fixture_v1",
        "rows":output,
    })
    start=bars[0]["bar_open_ms"]
    end=bars[-1]["bar_close_ms"]+1
    cutoff=warehouse_receipt["decision_cutoff_ms"]
    require(all(output[i]["open_ms"]==start+i*WIDTH
                for i in range(len(output)))
            and end<=cutoff,
            "CORE_D_PROJECTION_GAP_OR_FUTURE")
    manifest={
        "schema":"aql.strategy-service.source.v1",
        "timeframe":"15m","market":"fixture",
        "source_id":"generator","generation_id":"fixture_v1",
        "start_ms":start,"end_exclusive_ms":end,
        "cutoff_ms":cutoff,"evidence_class":"TEST_ONLY",
        "external_verifier":"NOT_CONNECTED",
        "raw_sha256":_hash(raw),
    }
    universe={
        "schema":"aql.strategy-service.universe.v1",
        "count_unit":"SYMBOL","cutoff_ms":cutoff,
        "evidence_class":"TEST_ONLY",
        "source_raw_sha256":_hash(raw),
        "members":[{"symbol":"AAA","eligible":True,
                    "membership_available_ms":cutoff}],
    }
    body={
        "schema":"aql.core.d.read-only-scanner-native15m-projection.v1",
        "status":"READY_FOR_SCANNER_TEST_ONLY",
        "source_zip_sha256":zip_sha,
        "csv_member_sha256":_hash(original_csv),
        "raw_vault_readback":"MATCHED_TEST_ONLY",
        "warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "core_245_native_price_query_sha256":
            native_price_query["price_query_sha256"],
        "core_253_local_query_sha256":core_local_query["query_sha256"],
        "dual_query_map_sha256":identity_map["identity_map_sha256"],
        "scanner_raw_sha256":_hash(raw),
        "scanner_manifest_sha256":digest(manifest),
        "scanner_universe_sha256":digest(universe),
        "start_ms":start,"end_exclusive_ms":end,
        "cutoff_ms":cutoff,"bar_count":len(output),
        "source_id":"generator","generation_id":"fixture_v1",
        "symbol":"AAA","timeframe":"15m",
        "synthetic_available_at_not_historical_known_at":True,
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "original_publisher_attestation":"NONE",
        "operational_paper_authority":"NONE","trading_authority":"NONE",
    }
    return {
        "scanner_raw_bytes":raw,"scanner_manifest":manifest,
        "scanner_universe":universe,
        "projection_receipt":{
            **body,"projection_sha256":digest(body),
        },
    }

def verify_same_source_research(
    root, vault, *, synthetic_zip_bytes, local_test_checksum_bytes,
    scanner_raw_bytes, scanner_manifest, scanner_universe,
    scanner_projection_receipt,
    scanner_run_receipt, scanner_nomination_receipt,
    scanner_route_receipt, scanner_approval_receipt,
    work235_spec_receipt, native15m_policy_receipt,
    warehouse_receipt, native_price_query, core_local_query,
    identity_map, source_ack_receipt,
):
    """Only returns VERIFIED_TEST_ONLY when actual immutable input bytes agree.

    The synthetic ZIP has a locally generated .CHECKSUM solely to use existing
    native-format custody APIs. A local checksum is NOT a publisher checksum.
    """
    from tools.strategy_service_offline.common import Frozen, canonical
    from tools.scanner_strategy_c.approval_route import (
        verify_test_only_approval, verify_strategy_route_request,
    )
    require(type(synthetic_zip_bytes) is bytes and
            0<len(synthetic_zip_bytes)<=MAX_BYTES
            and type(local_test_checksum_bytes) is bytes and
            0<len(local_test_checksum_bytes)<=512
            and type(scanner_raw_bytes) is bytes and
            0<len(scanner_raw_bytes)<=MAX_BYTES,
            "CORE_D_BOUNDED_BYTES_REQUIRED")
    _sealed(warehouse_receipt,"receipt_sha256")
    _sealed(identity_map,"identity_map_sha256")
    _sealed(native_price_query,"price_query_sha256")
    _sealed(core_local_query,"query_sha256")
    require(warehouse_receipt.get("test_only") is True and
            warehouse_receipt.get("status")=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED"
            and warehouse_receipt.get("vault",{}).get("vault")==
                "EXISTING_PINNED_RAW_VAULT"
            and warehouse_receipt.get("historical_known_at")=="NOT_ATTESTED"
            and warehouse_receipt.get("availability")=="RETROSPECTIVE_NON_PIT"
            and warehouse_receipt.get("execution")=="DISABLED",
            "CORE_D_NON_TEST_OR_UNCOMMITTED_SOURCE")
    zip_sha=_hash(synthetic_zip_bytes)
    require(zip_sha==warehouse_receipt["source_zip_sha256"]
            and vault.read(zip_sha)==synthetic_zip_bytes,
            "CORE_D_RAW_VAULT_READBACK_MISMATCH")
    require(_hash(local_test_checksum_bytes)==
            warehouse_receipt["checksum_file_sha256"],
            "CORE_D_TEST_CHECKSUM_FILE_MISMATCH")
    month=None
    try:
        with ZipFile(io.BytesIO(synthetic_zip_bytes)) as archive:
            members=archive.namelist()
            require(len(members)==1 and members[0].startswith(
                warehouse_receipt["symbol"]+"-15m-")
                and members[0].endswith(".csv"),
                "CORE_D_NATIVE_MEMBER_NAME")
            csv=archive.read(members[0])
            require(archive.testzip() is None,"CORE_D_ZIP_CRC")
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("CORE_D_NATIVE_SYNTHETIC_ZIP_INVALID") from exc
    name=members[0]
    month=name[len(warehouse_receipt["symbol"]+"-15m-"):-4]
    expected_zip=warehouse_receipt["symbol"]+"-15m-"+month+".zip"
    require(local_test_checksum_bytes.strip()==
            (zip_sha+"  "+expected_zip).encode(),
            "CORE_D_LOCAL_TEST_CHECKSUM_ASSERTION")
    require(_hash(csv)==warehouse_receipt["csv_member_sha256"],
            "CORE_D_ORIGINAL_MEMBER_SHA_MISMATCH")

    regenerated=bind_dual_query_identities(
        native_price_query,core_local_query,warehouse_receipt)
    require(regenerated["identity_map_sha256"]==
              identity_map["identity_map_sha256"],
            "CORE_D_DUAL_QUERY_MAP_DRIFT")
    _sealed(scanner_projection_receipt,"projection_sha256")
    require(scanner_projection_receipt.get("schema")==
                "aql.core.d.read-only-scanner-native15m-projection.v1"
            and scanner_projection_receipt.get("status")==
                "READY_FOR_SCANNER_TEST_ONLY"
            and scanner_projection_receipt.get("source_zip_sha256")==zip_sha
            and scanner_projection_receipt.get("csv_member_sha256")==_hash(csv)
            and scanner_projection_receipt.get("warehouse_receipt_sha256")==
                warehouse_receipt["receipt_sha256"]
            and scanner_projection_receipt.get("dual_query_map_sha256")==
                identity_map["identity_map_sha256"]
            and scanner_projection_receipt.get("core_245_native_price_query_sha256")==
                native_price_query["price_query_sha256"]
            and scanner_projection_receipt.get("core_253_local_query_sha256")==
                core_local_query["query_sha256"]
            and scanner_projection_receipt.get("scanner_raw_sha256")==
                _hash(scanner_raw_bytes)
            and scanner_projection_receipt.get("scanner_manifest_sha256")==
                digest(scanner_manifest)
            and scanner_projection_receipt.get("scanner_universe_sha256")==
                digest(scanner_universe)
            and scanner_projection_receipt.get("bar_count")==
                warehouse_receipt["bar_count"]
            and scanner_projection_receipt.get("cutoff_ms")==
                warehouse_receipt["decision_cutoff_ms"]
            and scanner_projection_receipt.get("historical_known_at_ms") is None
            and scanner_projection_receipt.get("trading_authority")=="NONE",
            "CORE_D_READ_ONLY_PROJECTION_PARENT_DRIFT")
    bars=core_local_query["bars"]
    require(0<len(bars)<=MAX_BARS
            and len(csv.splitlines())==len(bars)==warehouse_receipt["bar_count"],
            "CORE_D_BAR_CENSUS_MISMATCH")

    approval=verify_test_only_approval(
        scanner_approval_receipt,work235_spec_receipt,native15m_policy_receipt)
    route=Frozen.restore(scanner_route_receipt)
    scanner_run=Frozen.restore(scanner_run_receipt)
    nomination=Frozen.restore(scanner_nomination_receipt)
    policy=Frozen.restore(native15m_policy_receipt)
    raw_request=route.data
    verify_strategy_route_request(
        scanner_route_receipt,work235_spec_receipt,native15m_policy_receipt,
        scanner_approval_receipt,scanner_run_receipt,scanner_nomination_receipt,
        source_custody_receipt_sha256=raw_request["source_custody_receipt_sha256"],
        core245_price_query_sha256=raw_request["core245_price_query_sha256"],
        core253_query_local_sha256=raw_request["core253_query_local_sha256"],
        source_zip_sha256=raw_request["source_zip_sha256"])
    require(approval.data["decision"]=="APPROVED_TEST_ONLY"
            and approval.data["governance_action"]=="APPROVE_TEST_ONLY"
            and approval.data["scope"]=="SYNTHETIC_OFFLINE_ENGINEERING_ONLY"
            and raw_request["strategy_route_status"]=="ROUTE_CANDIDATE_TEST_ONLY"
            and raw_request["strategy_secretary_status"]=="NOT_ENQUEUED"
            and raw_request["scanner_nomination_status"]=="SELECTED"
            and raw_request["scanner_operational_status"]=="UNKNOWN"
            and raw_request["historical_known_at_ms"] is None
            and raw_request["trading_authority"]=="NONE"
            and raw_request["paper_authority"]=="NONE",
            "CORE_D_APPROVAL_OR_ROUTE_NOT_ELIGIBLE_TEST_ONLY")
    require(scanner_run.data.get("source_status")=="SYNTHETIC_TEST_ONLY_NATIVE_15M"
            and scanner_run.data.get("operational_scanner_status")=="UNKNOWN"
            and nomination.data.get("operational_scanner_status")=="UNKNOWN",
            "CORE_D_SCANNER_AUTHORITY_DRIFT")
    require(raw_request["scanner_run_sha256"]==scanner_run.sha256
            and raw_request["scanner_nomination_sha256"]==nomination.sha256
            and raw_request["strategy_approval_sha256"]==approval.sha256
            and raw_request["native15m_policy_sha256"]==policy.sha256
            and raw_request["source_zip_sha256"]==zip_sha
            and raw_request["source_custody_receipt_sha256"]==
                warehouse_receipt["receipt_sha256"]
            and raw_request["core245_price_query_sha256"]==
                native_price_query["price_query_sha256"]
            and raw_request["core253_query_local_sha256"]==
                core_local_query["query_sha256"]
            and raw_request["core245_price_query_sha256"]!=
                raw_request["core253_query_local_sha256"],
            "CORE_D_SCANNER_CORE_PARENT_DRIFT")
    source_delivery=_source_ack_present(root,warehouse_receipt,source_ack_receipt)
    source_nomination=source_delivery["scanner_nomination"]
    require(source_nomination.get("source_manifest",{}).get("dataset_sha")==zip_sha
            and source_nomination.get("stage")=="UNKNOWN",
            "CORE_D_LEGACY_SOURCE_ROUTE_DRIFT")
    require(raw_request["strategy_id"]==source_delivery["strategy_id"]
            and raw_request["strategy_version"]==source_delivery["strategy_version"]
            and raw_request["strategy_version"]==policy.data["strategy_version"]
            and raw_request["config_digest"]==policy.data["config_digest"]
            and raw_request["definition_digest"]==policy.data["definition"]["digest"],
            "CORE_D_STRATEGY_IDENTITY_DRIFT")

    # Scanner test-only source manifest is a separate, explicitly namespaced
    # byte representation of the SAME exact sequence of generated OHLCV bars.
    require(type(scanner_manifest) is dict
            and scanner_manifest.get("schema")=="aql.strategy-service.source.v1"
            and scanner_manifest.get("evidence_class")=="TEST_ONLY"
            and scanner_manifest.get("timeframe")=="15m"
            and scanner_manifest.get("market")==raw_request["market"]
            and scanner_manifest.get("raw_sha256")==_hash(scanner_raw_bytes)
            and scanner_manifest.get("cutoff_ms")==raw_request["cutoff_ms"]
            and scanner_manifest.get("cutoff_ms")==warehouse_receipt["decision_cutoff_ms"]
            and scanner_manifest.get("start_ms")==bars[0]["bar_open_ms"]
            and scanner_manifest.get("end_exclusive_ms")==
                bars[-1]["bar_close_ms"]+1,
            "CORE_D_SCANNER_MANIFEST_SOURCE_DRIFT")
    require(type(scanner_universe) is dict
            and scanner_universe.get("schema")=="aql.strategy-service.universe.v1"
            and scanner_universe.get("evidence_class")=="TEST_ONLY"
            and scanner_universe.get("source_raw_sha256")==_hash(scanner_raw_bytes)
            and scanner_universe.get("cutoff_ms")==scanner_manifest["cutoff_ms"]
            and scanner_universe.get("members")==[{
                "symbol":warehouse_receipt["symbol"],"eligible":True,
                "membership_available_ms":scanner_manifest["cutoff_ms"]}],
            "CORE_D_SCANNER_UNIVERSE_DRIFT")
    # A signed Scanner run alone is not proof it consumed these raw bytes.
    # Replay the actual pinned Scanner B native15m kernel with the precise
    # owner policy, identical byte payload and complete one-symbol universe.
    from tools.scanner_strategy_b.native15m import scan_native15m
    expected_scan=scan_native15m(
        [native15m_policy_receipt],[work235_spec_receipt],
        scanner_raw_bytes,scanner_manifest,scanner_universe,
        cutoff_ms=warehouse_receipt["decision_cutoff_ms"],symbol_budget=1)
    require(expected_scan.sha256==scanner_run.sha256
            and expected_scan.data==scanner_run.data,
            "CORE_D_SCANNER_ACTUAL_EXECUTION_REPLAY_DRIFT")
    require(raw_request["source_raw_sha256"]==_hash(scanner_raw_bytes)
            and raw_request["source_manifest_sha256"]==digest(scanner_manifest)
            and raw_request["universe_sha256"]==digest(scanner_universe)
            and raw_request["symbol"]==warehouse_receipt["symbol"]
            and raw_request["timeframe"]==warehouse_receipt["interval"]=="15m"
            and raw_request["scanner_nomination_status"]==nomination.data["status"]
            and raw_request["denominator"]==1
            and sum(raw_request["strategy_census"].values())==1,
            "CORE_D_SCANNER_RAW_MANIFEST_OR_CENSUS_DRIFT")
    try:
        parsed=json.loads(scanner_raw_bytes)
    except (TypeError,ValueError) as exc:
        raise ValueError("CORE_D_SCANNER_RAW_JSON_INVALID") from exc
    require(type(parsed) is dict and set(parsed)=={
            "schema","source_id","generation_id","rows"}
            and parsed["schema"]=="aql.strategy-service.synthetic-bars.v1"
            and parsed["source_id"]==scanner_manifest.get("source_id")
            and parsed["generation_id"]==scanner_manifest.get("generation_id")
            and type(parsed["rows"]) is list and len(parsed["rows"])==len(bars)
            and canonical(parsed)==scanner_raw_bytes,
            "CORE_D_SCANNER_RAW_CANONICAL_BYTES")
    for i,(native_line,core_bar,scan_bar) in enumerate(
            zip(csv.splitlines(),bars,parsed["rows"])):
        fields=native_line.split(b",")
        require(len(fields)==12 and fields[0].isdigit() and fields[6].isdigit(),
                "CORE_D_NATIVE_12_COLUMNS")
        opens=int(fields[0]); close=int(fields[6])
        nums=[]
        try:
            nums=[float(fields[j]) for j in (1,2,3,4,5)]
        except (TypeError,ValueError,OverflowError) as exc:
            raise ValueError("CORE_D_ORIGINAL_NUMERIC_CSV") from exc
        require(all(math.isfinite(x) for x in nums)
                and opens==core_bar["bar_open_ms"]
                and close==core_bar["bar_close_ms"]
                and tuple(nums)==tuple(core_bar[k] for k in
                    ("open","high","low","close","volume"))
                and set(scan_bar)==ROWS_FIELDS
                and scan_bar["symbol"]==warehouse_receipt["symbol"]
                and scan_bar["timeframe"]=="15m"
                and scan_bar["source_id"]==scanner_manifest["source_id"]
                and scan_bar["open_ms"]==opens
                and scan_bar["close_ms"]==close
                and scan_bar["available_ms"]==close+1
                and scan_bar["finalized"] is True
                and tuple(scan_bar[k] for k in
                    ("open","high","low","close","volume"))==tuple(nums)
                and core_bar["historical_known_at_ms"] is None,
                "CORE_D_BAR_PROJECTION_MISMATCH")
    require(bars[-1]["bar_close_ms"]+1<=warehouse_receipt["decision_cutoff_ms"],
            "CORE_D_CUTOFF_IS_FUTURE")
    body={
        "schema":SCHEMA,"proof_class":"SAME_SOURCE_SYNTHETIC_TEST_ONLY",
        "proof_state":"VERIFIED_TEST_ONLY",
        "raw_vault_source_sha256":zip_sha,
        "local_synthetic_checksum_sha256":_hash(local_test_checksum_bytes),
        "publisher_checksum_attested":False,
        "publisher_authenticity":"NOT_ATTESTED",
        "zip_csv_member_sha256":_hash(csv),
        "scanner_consumed_raw_sha256":_hash(scanner_raw_bytes),
        "read_only_scanner_projection_sha256":
            scanner_projection_receipt["projection_sha256"],
        "scanner_manifest_sha256":digest(scanner_manifest),
        "scanner_universe_sha256":digest(scanner_universe),
        "scanner_run_sha256":scanner_run.sha256,
        "scanner_nomination_sha256":nomination.sha256,
        "scanner_c_route_sha256":route.sha256,
        "scanner_c_explicit_approval_sha256":approval.sha256,
        "native15m_policy_sha256":policy.sha256,
        "core_245_native_query_sha256":native_price_query["price_query_sha256"],
        "core_253_local_query_sha256":core_local_query["query_sha256"],
        "core_dual_query_map_sha256":identity_map["identity_map_sha256"],
        "core_warehouse_receipt_sha256":warehouse_receipt["receipt_sha256"],
        "source_only_ack_sha256":source_ack_receipt["receipt_sha256"],
        "strategy_id":raw_request["strategy_id"],
        "strategy_version":raw_request["strategy_version"],
        "config_digest":raw_request["config_digest"],
        "definition_digest":raw_request["definition_digest"],
        "symbol":raw_request["symbol"],"timeframe":"15m",
        "scanner_market":raw_request["market"],
        "core_market":warehouse_receipt["exchange"]+":"+warehouse_receipt["market"]+":USDT",
        "market_alias_scope":"SYNTHETIC_FIXTURE_ONLY_NOT_OPERATIONAL",
        "cutoff_ms":raw_request["cutoff_ms"],
        "bar_count":len(bars),
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "scanner_operational_status":"UNKNOWN",
        "source_ack_is_approval":False,
        "strategy_consumer_ack_sha256":None,
        "paper_execution":"NOT_ACTIVATED","trading_authority":"NONE",
    }
    return {**body,"same_source_proof_sha256":digest(body)}


def connect_canonical_test_only_strategy(
    root, *, same_source_inputs, now_ms, expires_at_ms, route_id,
):
    """Actual scanner Frozen explicit approval→Core C durable PENDING only.

    Builds a strictly named, sealed **Core D projection** of that already
    verified external Scanner C approval. Core D supplies a ROUTE TTL, not a
    fictitious Scanner approval expiry or authenticated policy signature.
    Factory must independently produce a separate consumer ACK.
    """
    from tools.strategy_service_offline.common import Frozen
    require(type(now_ms) is int and type(expires_at_ms) is int
            and now_ms<expires_at_ms<=now_ms+WIDTH,
            "CORE_D_BOUNDED_RESEARCH_ROUTE_TTL")
    proof=verify_same_source_research(root,**same_source_inputs)
    r=Frozen.restore(same_source_inputs["scanner_route_receipt"]).data
    approval=Frozen.restore(same_source_inputs["scanner_approval_receipt"])
    policy=same_source_inputs["native15m_policy_receipt"]
    warehouse=same_source_inputs["warehouse_receipt"]
    source_ack=same_source_inputs["source_ack_receipt"]
    source_nomination=_source_ack_present(root,warehouse,source_ack)["scanner_nomination"]
    request=make_strategy_route_request(
        identity_map=same_source_inputs["identity_map"],warehouse=warehouse,
        nomination=source_nomination,source_ack=source_ack,
        strategy_policy_receipt=policy,
        strategy_id=r["strategy_id"],strategy_version=r["strategy_version"],
        config_digest=r["config_digest"],
        strategy_definition_digest=r["definition_digest"],
        expires_at_ms=expires_at_ms,
    )
    request_body={k:v for k,v in request.items() if k!="request_sha256"}
    request_body.update({
        "canonical_scanner_c_route_sha256":proof["scanner_c_route_sha256"],
        "canonical_scanner_c_approval_sha256":proof["scanner_c_explicit_approval_sha256"],
        "canonical_scanner_c_nomination_sha256":proof["scanner_nomination_sha256"],
        "canonical_scanner_c_run_sha256":proof["scanner_run_sha256"],
        "same_source_proof_sha256":proof["same_source_proof_sha256"],
        "research_provenance_scope":"SAME_SOURCE_SYNTHETIC_TEST_ONLY",
    })
    request={**request_body,"request_sha256":digest(request_body)}
    approval_body={
        "schema":INTERNAL_APPROVAL_SCHEMA,
        "decision":"APPROVED_TEST_ONLY","scope":"TEST_ONLY",
        "approved_by":"EXPLICIT_RESEARCH_POLICY_GATE",
        "strategy_id":r["strategy_id"],
        "strategy_version":r["strategy_version"],
        "config_digest":r["config_digest"],
        "strategy_definition_digest":r["definition_digest"],
        "timeframe":"15m","symbol":r["symbol"],
        "source_zip_sha256":request["source_zip_sha256"],
        "manifest_integrity_sha256":request["manifest_integrity_sha256"],
        "core_245_price_query_sha256":request["core_245_price_query_sha256"],
        "core_253_query_local_sha256":request["core_253_query_local_sha256"],
        "scanner_nomination_sha256":request["scanner_nomination_sha256"],
        "source_ack_sha256":request["source_ack_sha256"],
        "policy_receipt_sha256":request["policy_receipt_sha256"],
        "request_sha256":request["request_sha256"],
        "cutoff_ms":request["cutoff_ms"],
        "issued_at_ms":now_ms,"expires_at_ms":expires_at_ms,
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "source_ack_is_approval":False,
        "paper_authority":"NONE","trading_authority":"NONE",
        "external_owner_approval_schema":"aql.scanner-c.strategy-approval.v1",
        "external_scanner_approval_sha256":approval.sha256,
        "core_d_approval_kind":"PROJECTION_ONLY_OF_EXPLICIT_SCANNER_C_ACTION",
        "core_d_route_ttl_not_scanner_approval_expiry":True,
        "same_source_proof_sha256":proof["same_source_proof_sha256"],
    }
    projected={**approval_body,"approval_sha256":digest(approval_body)}
    status=enqueue_strategy_route(
        root,request,same_source_inputs["identity_map"],warehouse,
        source_nomination,source_ack,policy,
        approval=projected,now_ms=now_ms,route_id=route_id)
    require(status["state"]=="PENDING_CONSUMER"
            and status["route_ready_for_isolated_lab"] is False
            and status["approval_sha256"]==projected["approval_sha256"]
            and status["consumer_ack_sha256"] is None
            and status["trading_authority"]=="NONE",
            "CORE_D_STRATEGY_ROUTE_NOT_ISOLATED_PENDING")
    body={
        "schema":BRIDGE_SCHEMA,
        "status":"PENDING_FACTORY_CONSUMER_TEST_ONLY",
        "same_source_proof_sha256":proof["same_source_proof_sha256"],
        "canonical_scanner_c_approval_sha256":approval.sha256,
        "canonical_scanner_c_route_sha256":proof["scanner_c_route_sha256"],
        "core_c_request_sha256":request["request_sha256"],
        "core_c_strategy_approval_projection_sha256":projected["approval_sha256"],
        "core_c_strategy_route_sha256":status["route_receipt_sha256"],
        "route_id":route_id,
        "source_only_ack_sha256":source_ack["receipt_sha256"],
        "factory_consumer_ack_sha256":None,
        "core_245_native_query_sha256":proof["core_245_native_query_sha256"],
        "core_253_local_query_sha256":proof["core_253_local_query_sha256"],
        "strategy_id":r["strategy_id"],
        "strategy_version":r["strategy_version"],
        "config_digest":r["config_digest"],
        "timeframe":"15m","symbol":r["symbol"],
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "operational_paper_authority":"NONE","trading_authority":"NONE",
        "orders_created":0,"paper_positions":0,"actual_fills":None,
    }
    return {**body,"canonical_bridge_sha256":digest(body)}


def read_factory_canonical_strategy_offer(
    root, *, same_source_inputs, canonical_bridge_receipt, now_ms,
):
    """Verified read-only Factory handoff, not a Factory consumer ACK.

    Recomputes the actual RAW->Core queries->Scanner bytes proof before
    reporting Core C's durable strategy offer and canonical owner SHA links.
    No source-only ACK, synthetic Scanner SELECTED or Core projected approval
    is allowed to stand in for a Factory consumer receipt.
    """
    from research_wp_r0.aql_core_c_strategy_secretary_route_v1 import _verify_stored
    _sealed(canonical_bridge_receipt, "canonical_bridge_sha256")
    proof=verify_same_source_research(root,**same_source_inputs)
    _check= require
    bridge=canonical_bridge_receipt
    _check(bridge.get("schema")==BRIDGE_SCHEMA
           and bridge.get("status")=="PENDING_FACTORY_CONSUMER_TEST_ONLY"
           and bridge.get("same_source_proof_sha256")==
               proof["same_source_proof_sha256"]
           and bridge.get("canonical_scanner_c_approval_sha256")==
               proof["scanner_c_explicit_approval_sha256"]
           and bridge.get("canonical_scanner_c_route_sha256")==
               proof["scanner_c_route_sha256"]
           and bridge.get("source_only_ack_sha256")==
               proof["source_only_ack_sha256"]
           and bridge.get("factory_consumer_ack_sha256") is None,
           "CORE_D_FACTORY_BRIDGE_PARENT_DRIFT")
    con=_connect(root)
    try:
        row,request,approval,trace=_verify_stored(con,bridge["route_id"])
    finally:
        con.close()
    _check(row[5]=="PENDING_CONSUMER" and row[7] is None
           and approval is not None
           and request["schema"]==INTERNAL_REQUEST_SCHEMA
           and request["request_sha256"]==bridge["core_c_request_sha256"]
           and request["canonical_scanner_c_route_sha256"]==
               proof["scanner_c_route_sha256"]
           and request["canonical_scanner_c_approval_sha256"]==
               proof["scanner_c_explicit_approval_sha256"]
           and request["same_source_proof_sha256"]==
               proof["same_source_proof_sha256"]
           and request["source_ack_sha256"]==
               proof["source_only_ack_sha256"]
           and approval["approval_sha256"]==
               bridge["core_c_strategy_approval_projection_sha256"]
           and approval["external_scanner_approval_sha256"]==
               proof["scanner_c_explicit_approval_sha256"]
           and approval["same_source_proof_sha256"]==
               proof["same_source_proof_sha256"]
           and approval["core_d_approval_kind"]==
               "PROJECTION_ONLY_OF_EXPLICIT_SCANNER_C_ACTION"
           and approval["core_d_route_ttl_not_scanner_approval_expiry"] is True,
           "CORE_D_STORED_STRATEGY_PARENT_DRIFT")
    snap=strategy_route_snapshot(root,bridge["route_id"],now_ms=now_ms)
    _check(snap["state"]=="PENDING_CONSUMER"
           and snap["route_receipt_sha256"]==
               bridge["core_c_strategy_route_sha256"]
           and snap["consumer_ack_sha256"] is None
           and snap["route_ready_for_isolated_lab"] is False
           and snap["trading_authority"]=="NONE",
           "CORE_D_FACTORY_OFFER_NOT_WAITING")
    body={
        "schema":"aql.core.d.factory-canonical-strategy-offer.v1",
        "status":"READY_FOR_EXPLICIT_FACTORY_RESEARCH_CONSUMER_ONLY",
        "route_id":bridge["route_id"],
        "canonical_bridge_sha256":bridge["canonical_bridge_sha256"],
        "same_source_proof_sha256":proof["same_source_proof_sha256"],
        "scanner_c_approval_sha256":proof["scanner_c_explicit_approval_sha256"],
        "scanner_c_route_sha256":proof["scanner_c_route_sha256"],
        "scanner_c_run_sha256":proof["scanner_run_sha256"],
        "scanner_c_nomination_sha256":proof["scanner_nomination_sha256"],
        "source_only_ack_sha256":proof["source_only_ack_sha256"],
        "core_c_strategy_request_sha256":request["request_sha256"],
        "core_c_approval_projection_sha256":approval["approval_sha256"],
        "core_c_strategy_route_sha256":snap["route_receipt_sha256"],
        "core_245_native_query_sha256":proof["core_245_native_query_sha256"],
        "core_253_local_query_sha256":proof["core_253_local_query_sha256"],
        "core_warehouse_receipt_sha256":proof["core_warehouse_receipt_sha256"],
        "scanner_raw_source_sha256":proof["scanner_consumed_raw_sha256"],
        "read_only_scanner_projection_sha256":
            proof["read_only_scanner_projection_sha256"],
        "source_zip_sha256":proof["raw_vault_source_sha256"],
        "strategy_id":request["strategy_id"],
        "strategy_version":request["strategy_version"],
        "config_digest":request["config_digest"],
        "strategy_definition_digest":request["strategy_definition_digest"],
        "symbol":request["symbol"],"timeframe":"15m",
        "cutoff_ms":request["cutoff_ms"],
        "expiry_ms":request["expires_at_ms"],
        "source_only_ack_is_strategy_approval":False,
        "scanner_approval_has_authenticated_issuer":False,
        "factory_consumer_ack_sha256":None,
        "lab_invoked":False,"paper_invoked":False,
        "orders_created":0,"paper_positions":0,"actual_fills":None,
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "operational_paper_authority":"NONE","trading_authority":"NONE",
    }
    return {**body,"factory_offer_sha256":digest(body)}
