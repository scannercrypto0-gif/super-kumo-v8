"""Owner174 fresh source -> identified Factory DATA ONLY consumer.

No acceptance of cached/forged metadata reports as capabilities. Every public
handoff freshly executes the existing173 input inspection then rehashes the
snapshot used for rows with the original pins and existing155 importer.
"""
from dataclasses import dataclass, asdict
import json
import subprocess

from research_wp_r0.realdev_research_data import (
    CONSUMER,SCOPE,OWNER,ResearchPermit,accept_prefix,digest,ResearchOnlyDenied,
)
from .dev_source import DevSourceEnvelope,import_bytes
from .realdev_integration import (
    IntegrationCapability,RuntimePin,observe_runtime,inspect_local_pair,read_pinned_file,
    validate_receipt,RAW_SHA,RECEIPT_SHA,START,END,EXPERIMENT,
    SCHEMA,FACTORY_SHA,FACTORY_COMPATIBILITY,
)

BASE_CORE = "22d03f4d3434fbce149c4d66349b33149789613a"


@dataclass(frozen=True)
class ResearchCapability:
    experiment_id: str
    permission: str
    owner_scope: str
    consumer_id: str
    runtime: RuntimePin
    input_inspection: IntegrationCapability
    prefix_start_ms: int
    prefix_end_ms_exclusive: int
    decision_cutoff_ms: int
    warmup_input_count: int


def require(ok,reason):
    if not ok:
        raise ResearchOnlyDenied(reason)


def validate_research_capability(c,runtime,request):
    require(request==SCOPE,"CORE_DEFAULT_DENY_OR_EXECUTION_SCOPE")
    require(type(c) is ResearchCapability,"CORE_EXPLICIT_RESEARCH_CAPABILITY")
    require(c.experiment_id==EXPERIMENT and c.permission==SCOPE and c.owner_scope==OWNER
        and c.consumer_id==CONSUMER,"CORE_RESEARCH_IDENTITY")
    require(type(c.runtime) is RuntimePin and c.runtime==runtime,"CORE_STALE_RUNTIME_HEAD")
    require(type(c.input_inspection) is IntegrationCapability and c.input_inspection.runtime==runtime,
            "CORE_FRESH_INSPECTION_REQUIRED")
    require(type(c.prefix_start_ms) is int and c.prefix_start_ms==START
        and type(c.prefix_end_ms_exclusive) is int and START<c.prefix_end_ms_exclusive<=END
        and c.prefix_end_ms_exclusive%60000==0,"CORE_PREFIX")
    require(type(c.decision_cutoff_ms) is int and c.prefix_end_ms_exclusive<=c.decision_cutoff_ms<=2**53-1,
            "CORE_FUTURE_PREFIX")
    require(type(c.warmup_input_count) is int
        and 22<=c.warmup_input_count<=(c.prefix_end_ms_exclusive-START)//60000,"CORE_WARMUP")


def handoff_local_pair(raw_path,receipt_path,*,checkout,capability=None,request=None):
    """Return Factory ResearchData only. Source bytes stay private/local/in memory."""
    require(request==SCOPE,"CORE_DEFAULT_DENY_OR_EXECUTION_SCOPE")
    require(type(capability) is ResearchCapability,"CORE_EXPLICIT_RESEARCH_CAPABILITY")
    runtime=observe_runtime(checkout)
    subprocess.run(["git","merge-base","--is-ancestor",BASE_CORE,"HEAD"],cwd=checkout,check=True)
    validate_research_capability(capability,runtime,request)
    inspection=inspect_local_pair(raw_path,receipt_path,checkout=checkout,
        capability=capability.input_inspection,request="DEV_INTEGRATION_ONLY")
    # The snapshot actually supplying rows must match BOTH original pins again;
    # a file replacement between the metadata check and this read cannot slip in.
    raw,_=read_pinned_file(raw_path,68923,RAW_SHA)
    issued,_=read_pinned_file(receipt_path,4203,RECEIPT_SHA)
    receipt=json.loads(issued)
    validate_receipt(receipt,raw_sha=RAW_SHA,raw_size=len(raw),pinned_original=True)
    envelope=DevSourceEnvelope(dict(schema="core-dev-source-1",scope="DEV_ONLY",origin="BINANCE_VISION",
        market="SPOT",symbol="BTCUSDT",interval="1m",start_ms=START,end_ms_exclusive=END,
        bytes_ref="chatgpt-library:file_00000000084c8208b5d65c8fc803426c:version0",
        archive_sha256=RAW_SHA,archive_size=68923,format="binance-spot-zip-12-ms-v1",
        member="BTCUSDT-1m-2024-01-01.csv",checksum_provenance="SAME_PUBLISHER_REPORTED",
        normalization="ohlcv-ms-float64-grid-1",source_version="UNKNOWN",correction_status="UNKNOWN",
        issuer_first_available_at="UNKNOWN",bounded_UTC="UNKNOWN",independent_custody="UNKNOWN"))
    history=import_bytes(envelope,raw)
    full_hash=history.receipt["normalized_ohlcv_sha256"]
    require(full_hash==inspection.spec["normalized_seven_field_sha256"],"CORE_INSPECTION_SOURCE_DRIFT")
    bars=history.range_query(capability.prefix_start_ms,capability.prefix_end_ms_exclusive,
                             capability.decision_cutoff_ms)
    rows=tuple((b.bar_open,b.bar_close,b.open,b.high,b.low,b.close,b.volume) for b in bars)
    metadata=dict(schema="core-factory-research-prefix-1",experiment_id=EXPERIMENT,consumer_id=CONSUMER,
        source_kind="ORIGINAL_LOCAL_PAIR",runtime=asdict(runtime),code_sha=runtime.head,base_core_sha=BASE_CORE,
        factory_sha=FACTORY_SHA,mapping_schema=SCHEMA,compatibility_profile=FACTORY_COMPATIBILITY,
        symbol="BTCUSDT",interval_ms=60000,timezone="UTC",source_start_ms=START,source_end_ms_exclusive=END,
        prefix_start_ms=capability.prefix_start_ms,prefix_end_ms_exclusive=capability.prefix_end_ms_exclusive,
        decision_cutoff_ms=capability.decision_cutoff_ms,warmup_input_count=capability.warmup_input_count,
        raw_archive_sha256=RAW_SHA,raw_archive_size=68923,issued_receipt_sha256=RECEIPT_SHA,
        issued_receipt_size=4203,retained_archive_version=0,inspection_report_sha256=inspection.digest,
        full_normalized7_sha256=full_hash,source_id=receipt["source_id"],issued_receipt_id=receipt["receipt_id"])
    expected=dict(code_sha=runtime.head,runtime_sha256=digest(asdict(runtime)),raw_archive_sha256=RAW_SHA,
        issued_receipt_sha256=RECEIPT_SHA,inspection_report_sha256=inspection.digest,
        full_normalized7_sha256=full_hash,prefix_normalized7_sha256=digest(rows))
    result=accept_prefix(rows,metadata=metadata,expected=expected,
        permit=ResearchPermit(EXPERIMENT,OWNER,CONSUMER,runtime.head,expected["runtime_sha256"]),request=request)
    require(observe_runtime(checkout)==runtime,"CORE_CODE_CHANGED_DURING_HANDOFF")
    return result


def replay_handoff(report,*,expected_digest,**invocation):
    from research_wp_r0.realdev_research_data import ResearchData
    require(type(report) is ResearchData and report.receipt_sha256==expected_digest,"HANDOFF_COMMITMENT")
    fresh=handoff_local_pair(**invocation)
    require(fresh.payload==report.payload,"HANDOFF_REPLAY_MISMATCH")
    return fresh
