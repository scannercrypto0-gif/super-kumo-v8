"""Scoped TEST_ONLY source cohort builder for scanner/Core D contract testing.

A fixture-only native-format ZIP/CSV with a Work235-permitted research symbol.
The verifier receives genuine Core-produced RAW/Vault/warehouse #245/#253
receipts. No vendor provenance, historical PIT, market validation or trading.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from research_wp_r0.aql_archive_custody_bridge_v1 import digest as core_digest
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
from research_wp_r0.historical_library import HistoricalLibrary
from tools.raw_vault_offline.vault import RawVault
from tools.strategy_service_offline.common import require
from tools.scanner_strategy_d.core_query_adapter import scan_same_core_source, WIDTH_MS

SOURCE_SYMBOL = "AAA"
SOURCE_NAME = "AAA-15m-2024-02"
SOURCE_START = 1706745600000
SOURCE_ROWS = 10
COHORT_SCHEMA = "aql.scanner-d.permitted-core-test-cohort.v1"


def _sha(buf):
    return hashlib.sha256(buf).hexdigest()


def _original_format_test_zip():
    # Native 12-column kline format, NEVER an actual Binance source.
    rows=[]
    for i in range(SOURCE_ROWS):
        start=SOURCE_START+i*WIDTH_MS
        close=100+2*i
        rows.append(",".join(str(x) for x in (
            start,close,close+1,close-1,close,2,
            start+WIDTH_MS-1,500+i,10+i,2+i,200+i,0)))
    csv=("\n".join(rows)+"\n").encode("ascii")
    name=SOURCE_NAME+".zip"
    member=SOURCE_NAME+".csv"
    buf=BytesIO()
    with ZipFile(buf,"w",compression=ZIP_DEFLATED) as archive:
        archive.writestr(member,csv)
    raw=buf.getvalue()
    checksum=(_sha(raw)+"  "+name+"\n").encode("ascii")
    return raw,checksum,csv,name,member


def create_permitted_core_test_cohort(core_root, vault_root, work235_specs,
                                      governance_actions, *, symbol_budget=1):
    """Build a *new* independent TEST_ONLY fixture using actual Core APIs.

    This is deliberately a standalone research fixture, not a fake replacement
    for the restricted Core 'authorized-original-transfer' BTCUSDT API. The
    below direct admission reuses Core RAW→warehouse and is explicitly
    limited to test fixture bytes.
    """
    from research_wp_r0.aql_core_d_same_source_witness_v1 import create_core_d_research_witness

    require(type(work235_specs) is list and work235_specs,
            "D_POLICY_REQUIRED")
    from tools.strategy_service_offline.screening import StrategyScreeningSpec
    for receipt in work235_specs:
        pol=StrategyScreeningSpec.restore_spec(receipt).data
        require(SOURCE_SYMBOL in pol["dna"]["dna"]["scanner_profile"]["allowed_symbols"]
                and "fixture" in pol["dna"]["dna"]["scanner_profile"]["allowed_venues"]
                and pol["dna"]["dna"]["provenance"]["allowed_sources"]==["generator"]
                and pol["dna"]["dna"]["provenance"]["source_generation_id"]=="fixture_v1",
                "D_FROZEN_POLICY_SOURCE_SCOPE_NOT_PERMITTED")
    root=__import__("pathlib").Path(core_root)
    vault=RawVault(__import__("pathlib").Path(vault_root))
    raw,checksum,csv,archive_name,member=_original_format_test_zip()
    cutoff=SOURCE_START+SOURCE_ROWS*WIDTH_MS
    ds="AQL-D-SYNTHETIC-AAA-15M-COHORT-v1"
    pin={
        "schema":"aql.core.external-original-byte-pin.v1",
        "source_kind":"BINANCE_KLINES_ZIP",
        "original_object_id":ds,
        "original_sha256":_sha(raw),
        "provenance_reference":"TEST_ONLY_IN_MEMORY",
        "captured_at_ms":None,"claimed_available_at_ms":None,
        "expected_inventory_sha256":None,"vault_object_metadata":None,
        "universe_manifest_sha256":None,"universe_member_count":None,
        "test_only":True,"archive_name":archive_name,
        "csv_member_name":member,"csv_member_sha256":_sha(csv),
        "checksum_file_sha256":_sha(checksum),
    }
    spec={
        "dataset_id":ds,"version":1,"symbol":SOURCE_SYMBOL,"interval":"15m",
        "exchange":"BINANCE","market":"SPOT",
        "source_label":"SYNTHETIC_TEST_ONLY_NOT_PUBLISHER",
        "start_ms":SOURCE_START,"end_exclusive_ms":cutoff,
        "as_of_ms":cutoff,"parent_source_sha256":None,
        "correction_reason":None,"test_only":True,
    }
    warehouse=admit_local_original(
        root,raw,checksum,pin,spec,decision_cutoff_ms=cutoff,vault=vault)
    local=query_local(root,ds,1,SOURCE_START,cutoff,cutoff,
        required_source_sha256=_sha(raw),require_complete=True)
    lib=HistoricalLibrary()
    original=admit_original_bytes(
        raw,pin,spec,
        stager=OfflineBridgeStager(root/"independent-core-245-test"),
        library=lib,decision_cutoff_ms=cutoff,
        checksum_file_bytes=checksum)
    req={
        "schema":REQUEST_SCHEMA,"dataset_id":ds,"version":1,
        "start_ms":SOURCE_START,"end_exclusive_ms":cutoff,
        "decision_cutoff_ms":cutoff,
        "require_complete":False,"confirmed_only":False,
    }
    native=query_price_custody(
        lib,req,expected_source_sha256=_sha(raw),
        expected_manifest_integrity_sha256=original["manifest_integrity_sha256"])
    mapping=bind_dual_query_identities(native,local,warehouse)
    clocks=[{
        "bar_open_ms":bar["bar_open_ms"],
        "bar_checksum":bar["bar_checksum"],
        "available_at_ms":bar["bar_close_ms"]+1,
    } for bar in local["bars"]]
    witness=create_core_d_research_witness(
        root,warehouse,native,local,mapping,
        scanner_source_id="generator",
        scanner_generation_id="fixture_v1",
        scanner_market="fixture",
        research_universe_members=[{
            "symbol":SOURCE_SYMBOL,"eligible":True,
            "membership_available_ms":cutoff,
        }],
        synthetic_available_at_ms_by_bar=clocks)
    handoff=scan_same_core_source(
        root,warehouse,native,local,mapping,witness,work235_specs,
        governance_actions=governance_actions,symbol_budget=symbol_budget)
    service=handoff.data["scanner_c_canonical_service_receipt"]["payload"]
    statuses=[x["payload"]["scanner_nomination_status"]
              for x in service["strategy_route_requests"]]
    require(len(statuses)==len(work235_specs)
            and all(x in ("SELECTED","REJECTED","UNKNOWN") for x in statuses),
            "D_ELIGIBLE_SYMBOL_STILL_INELIGIBLE_OR_UNSCANNED")
    body={
        "schema":COHORT_SCHEMA,"fixture_origin":"SCANNER_OWNER_TEST_ONLY",
        "warehouse":warehouse,"native_price_query":native,
        "local_query":local,"identity_map":mapping,
        "core_d_issued_witness":witness,
        "scanner_d_handoff":handoff.receipt(),
        "scanner_nomination_statuses":statuses,
        "source_zip_sha256":warehouse["source_zip_sha256"],
        "core_245_price_query_sha256":native["price_query_sha256"],
        "core_253_query_local_sha256":local["query_sha256"],
        "scanner_raw_sha256":handoff.data["scanner_raw_sha256"],
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "strategy_secretary_state":"NOT_ENQUEUED",
        "factory_lab_execution":"NOT_PERFORMED",
        "trading_authority":"NONE",
    }
    return {**body,"cohort_sha256":core_digest(body)}
