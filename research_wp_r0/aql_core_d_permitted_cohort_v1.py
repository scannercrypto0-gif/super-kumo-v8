"""Core D policy-permitted synthetic same-source cohort, issuer-owned software proof.

One bounded original-FORMAT test ZIP for an already permitted Work235 fixture
symbol. Original B original-source intake is intentionally NOT reused because
it authorizes exclusively original BTCUSDT Feb/Aug source. This new path calls
existing generic immutable #211 RawVault / #226 Core warehouse and native
#245 query without modifying their contracts. Never imply publisher authenticity.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager, digest
from research_wp_r0.aql_authenticated_historical_admission_v1 import admit_original_bytes
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_core_dual_query_identity_map_v1 import bind_dual_query_identities
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.historical_library import HistoricalLibrary
from research_wp_r0.aql_core_d_same_source_witness_v1 import create_core_d_research_witness
from tools.raw_vault_offline.vault import RawVault
from tools.strategy_service_offline.common import Frozen
from tools.strategy_service_offline.screening import StrategyScreeningSpec

SCHEMA="aql.core.d.permitted-synthetic-cohort.v1"
WIDTH=900_000
START=1706745600000


def _deny(ok, reason):
    if not ok:
        raise ValueError("CORE_D_COHORT_"+reason)


def _hash(x):
    return sha256(x).hexdigest()


def create_permitted_synthetic_cohort(core_root, raw_root, work_specs, *,
                                      symbol="AAA", count=8,
                                      start_ms=START, source_id="generator",
                                      generation_id="CORE_D_PERMITTED_V1",
                                      clock_delta_ms=1):
    """Create-and-admit ONE strictly synthetic permitted-symbol cohort.

    All ZIP/CHECKSUM bytes are freshly produced for an *explicit synthetic
    test*, no Binance publisher proof and no authentic historical quote.
    These derived bytes must never be passed to original-source Work ingest.
    """
    _deny(type(work_specs) is list and len(work_specs)>0,"POLICY_REQUIRED")
    policies=[StrategyScreeningSpec.restore_spec(v).data for v in work_specs]
    allowed=set.intersection(*[
        set(w["dna"]["dna"]["scanner_profile"]["allowed_symbols"])
        for w in policies])
    _deny(symbol in allowed and symbol in {"AAA","BBB","CCC","DDD","EEE"},
          "FROZEN_WORK_POLICY_SYMBOL")
    _deny(all(w["market"]=="fixture"
              and w["scope"]=="TEST_ONLY_UNAPPROVED_POLICY"
              and w["paper_approval"]=="NOT_FOUND"
              for w in policies),"WORK_POLICY_SCOPE")
    _deny(type(count) is int and 4<=count<=256
          and type(start_ms) is int and start_ms>=0 and start_ms%WIDTH==0
          and type(clock_delta_ms) is int and 0<clock_delta_ms<=1000,
          "BOUNDED_WINDOW")
    _deny(type(source_id) is str and source_id=="generator"
          and type(generation_id) is str and generation_id.startswith("CORE_D_")
          and len(generation_id)<=96,"TEST_ONLY_GENERATION")
    end=start_ms+count*WIDTH
    cutoff=end+10_000
    csv_rows=[]
    for i in range(count):
        t=start_ms+i*WIDTH
        # FIXTURE NUMBERS: cannot be mistaken for exchange actual candles.
        o=100+i
        csv_rows.append(",".join(str(x) for x in
            (t,o,o+2,o-1,o+1,5+i,t+WIDTH-1,500+i,10+i,2+i,200+i,0)))
    member=f"{symbol}-15m-2024-02.csv"
    archive=f"{symbol}-15m-2024-02.zip"
    _deny(start_ms==START,"FIXTURE_MONTH_SCOPE")
    buf=BytesIO()
    with ZipFile(buf,"w",compression=ZIP_DEFLATED) as z:
        z.writestr(member,("\n".join(csv_rows)+"\n").encode("ascii"))
    zip_bytes=buf.getvalue()
    checksum=(_hash(zip_bytes)+"  "+archive+"\n").encode("ascii")
    csv_bytes=("\n".join(csv_rows)+"\n").encode("ascii")
    dataset=f"AQL-D-TEST-ONLY-{symbol}-15M-COHORT-v1"
    pin={
        "schema":"aql.core.external-original-byte-pin.v1",
        "source_kind":"BINANCE_KLINES_ZIP",
        "original_object_id":dataset,"original_sha256":_hash(zip_bytes),
        "provenance_reference":"CORE_D_GENERATED_SYNTHETIC_NOT_PUBLISHER",
        "captured_at_ms":None,"claimed_available_at_ms":None,
        "expected_inventory_sha256":None,"vault_object_metadata":None,
        "universe_manifest_sha256":None,"universe_member_count":None,
        "test_only":True,"archive_name":archive,
        "csv_member_name":member,"csv_member_sha256":_hash(csv_bytes),
        "checksum_file_sha256":_hash(checksum),
    }
    spec={
        "dataset_id":dataset,"version":1,"symbol":symbol,"interval":"15m",
        "exchange":"BINANCE","market":"SPOT",
        "source_label":"CORE_D_SYNTHETIC_FIXTURE_ONLY",
        "start_ms":start_ms,"end_exclusive_ms":end,
        "as_of_ms":cutoff,"parent_source_sha256":None,
        "correction_reason":None,"test_only":True,
    }
    vault=RawVault(raw_root)
    warehouse=admit_local_original(
        core_root,zip_bytes,checksum,pin,spec,
        decision_cutoff_ms=cutoff,vault=vault)
    _deny(vault.read(_hash(zip_bytes))==zip_bytes
          and warehouse["source_zip_sha256"]==_hash(zip_bytes)
          and warehouse["status"]=="OFFLINE_LOCAL_WAREHOUSE_COMMITTED",
          "IMMUTABLE_VAULT_READBACK")
    local=query_local(core_root,dataset,1,start_ms,end,cutoff,
                      required_source_sha256=_hash(zip_bytes),require_complete=True)
    lib=HistoricalLibrary()
    admission=admit_original_bytes(
        zip_bytes,pin,spec,
        stager=OfflineBridgeStager(core_root/"d_native_independent"),
        library=lib,decision_cutoff_ms=cutoff,
        checksum_file_bytes=checksum)
    request={
        "schema":REQUEST_SCHEMA,"dataset_id":dataset,"version":1,
        "start_ms":start_ms,"end_exclusive_ms":end,
        "decision_cutoff_ms":cutoff,"require_complete":False,
        "confirmed_only":False,
    }
    native=query_price_custody(
        lib,request,expected_source_sha256=_hash(zip_bytes),
        expected_manifest_integrity_sha256=admission["manifest_integrity_sha256"])
    _deny(native["status"]=="OK","NATIVE_QUERY")
    mapping=bind_dual_query_identities(native,local,warehouse)
    clocks=[{"bar_open_ms":b["bar_open_ms"],
             "bar_checksum":b["bar_checksum"],
             "available_at_ms":b["bar_close_ms"]+clock_delta_ms}
            for b in local["bars"]]
    members=[{"symbol":symbol,"eligible":True,
              "membership_available_ms":cutoff}]
    witness=create_core_d_research_witness(
        core_root,warehouse,native,local,mapping,
        scanner_source_id=source_id,
        scanner_generation_id=generation_id,
        scanner_market="fixture",
        research_universe_members=members,
        synthetic_available_at_ms_by_bar=clocks)
    result={
        "schema":SCHEMA,
        "cohort_evidence_class":"SYNTHETIC_TEST_ONLY_NOT_PUBLISHER",
        "source_kind":"GENERATED_NATIVE_FORMAT_ZIP_NOT_AUTHENTIC_MARKET",
        "symbol":symbol,"timeframe":"15m",
        "source_zip_sha256":_hash(zip_bytes),
        "raw_vault_committed":True,
        "source_bars":len(local["bars"]),
        "warehouse_receipt_sha256":warehouse["receipt_sha256"],
        "core_245_price_query_sha256":native["price_query_sha256"],
        "core_253_query_local_sha256":local["query_sha256"],
        "core_d_witness_sha256":witness["sha256"],
        "historical_known_at_ms":None,"historical_pit":"NOT_ATTESTED",
        "trading_authority":"NONE",
    }
    return {
        "receipt":{**result,"cohort_sha256":digest(result)},
        "warehouse":warehouse,"native":native,"local":local,
        "mapping":mapping,"witness":witness,
    }
