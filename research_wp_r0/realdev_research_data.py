"""Factory research inspection only. No engine import, model or execution API.

Core must freshly validate source bytes before calling this consumer. Injected
metadata/expected digests constrain cooperative callers, not authenticate an
issuer or hostile same-process caller. This API cannot authorize execution.
"""
from dataclasses import dataclass
import hashlib
import json
import re

from .historical_library import (
    HistoricalBar, HistoricalDataError, BarQuality, SourceType, DataAvailabilityKind, validate_bars,
)

CONSUMER = "factory-realdev-research-data-1"
SCOPE = "DEV_RESEARCH_DATA_ONLY"
EXPERIMENT = "AQL-CORE-REALDEV-001"
OWNER = "https://github.com/scannercrypto0-gif/super-kumo-v8/issues/174"
BASE = "22d03f4d3434fbce149c4d66349b33149789613a"
FACTORY = "eacb5e50150c6e6c64c8a41b8eaa410aebd71532"
PROFILE = "factory148-u160-whole-policy-null-1"
RAW = "4ec2915e610ab4e9a4d5e86a5ada1c15bbf6b5db343cdb385681d6ac97166a4e"
ISSUED = "ffce2bbe7890414d84360be80a0ac478795ae8d1a28085f8bb34075faca83386"


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",", ":"),allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class ResearchOnlyDenied(ValueError):
    pass


def require(ok,reason):
    if not ok:
        raise ResearchOnlyDenied(reason)


def is_sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}",value) is not None


@dataclass(frozen=True)
class ResearchPermit:
    experiment_id: str
    owner_scope: str
    consumer_id: str
    code_sha: str
    runtime_sha256: str


@dataclass(frozen=True)
class ResearchData:
    """Canonical rows/metadata only; no engine dictionary, quote or signal fields."""
    payload: bytes

    @property
    def spec(self):
        return json.loads(self.payload)

    @property
    def rows(self):
        return tuple(tuple(row) for row in self.spec["normalized7"])

    @property
    def receipt_sha256(self):
        return hashlib.sha256(self.payload).hexdigest()

    def request(self, scope=None):
        require(scope == SCOPE,"FACTORY_DEFAULT_DENY_OR_EXECUTION_SCOPE")
        return self.spec


def accept_prefix(normalized7, *, metadata, expected, permit=None, request=None):
    """Independent default-deny Factory endpoint; never call an engine downstream."""
    require(request == SCOPE,"FACTORY_DEFAULT_DENY_OR_EXECUTION_SCOPE")
    require(type(permit) is ResearchPermit,"FACTORY_EXPLICIT_PERMIT")
    require(permit.experiment_id == EXPERIMENT and permit.owner_scope == OWNER
            and permit.consumer_id == CONSUMER,"FACTORY_CONSUMER_IDENTITY")
    # Validate the same detached snapshot that will be returned. Caller mutation
    # of lists/dicts after checks cannot change the accepted data or claims.
    normalized7=json.loads(canonical(normalized7))
    metadata=json.loads(canonical(metadata))
    expected=json.loads(canonical(expected))
    fields = {"schema","experiment_id","consumer_id","source_kind","runtime","code_sha","base_core_sha",
        "factory_sha","mapping_schema","compatibility_profile","symbol","interval_ms","timezone",
        "source_start_ms","source_end_ms_exclusive","prefix_start_ms","prefix_end_ms_exclusive",
        "decision_cutoff_ms","warmup_input_count","raw_archive_sha256","raw_archive_size",
        "issued_receipt_sha256","issued_receipt_size","retained_archive_version",
        "inspection_report_sha256","full_normalized7_sha256"}
    require(type(metadata) is dict and set(metadata)==fields,"FACTORY_METADATA_SHAPE")
    require(type(expected) is dict and set(expected)=={
        "code_sha","runtime_sha256","raw_archive_sha256","issued_receipt_sha256",
        "inspection_report_sha256","full_normalized7_sha256","prefix_normalized7_sha256"},
        "FACTORY_EXPECTED_COMMITMENTS")
    m=metadata
    require(m["schema"]=="core-factory-research-prefix-1" and m["experiment_id"]==EXPERIMENT
        and m["consumer_id"]==CONSUMER and m["base_core_sha"]==BASE and m["factory_sha"]==FACTORY
        and m["mapping_schema"]=="core-factory-dev-map-2" and m["compatibility_profile"]==PROFILE,
        "FACTORY_CODE_SCHEMA_PROFILE")
    require(type(m["code_sha"]) is str and re.fullmatch(r"[0-9a-f]{40}",m["code_sha"])
        and m["code_sha"]==expected["code_sha"]==permit.code_sha,"FACTORY_STALE_HEAD")
    runtime=m["runtime"]
    require(type(runtime) is dict and set(runtime)=={"host","account","python","python_version","checkout","head"}
        and all(type(v) is str and bool(v) for v in runtime.values()) and runtime["head"]==m["code_sha"]
        and digest(runtime)==expected["runtime_sha256"]==permit.runtime_sha256,"FACTORY_RUNTIME")
    for key in ("raw_archive_sha256","issued_receipt_sha256","inspection_report_sha256","full_normalized7_sha256"):
        require(is_sha(m[key]) and m[key]==expected[key],"FACTORY_PROVENANCE_COMMITMENT")
    require(m["source_kind"] in ("ORIGINAL_LOCAL_PAIR","SYNTHETIC_CONTRACT_FIXTURE"),"FACTORY_SOURCE_KIND")
    if m["source_kind"]=="ORIGINAL_LOCAL_PAIR":
        require(m["raw_archive_sha256"]==RAW and m["raw_archive_size"]==68923
            and m["issued_receipt_sha256"]==ISSUED and m["issued_receipt_size"]==4203
            and m["source_start_ms"]==1704067200000 and m["source_end_ms_exclusive"]==1704153600000,
            "FACTORY_ORIGINAL_PIN")
    require(m["symbol"]=="BTCUSDT" and type(m["interval_ms"]) is int and m["interval_ms"]==60000
        and m["timezone"]=="UTC" and type(m["retained_archive_version"]) is int
        and m["retained_archive_version"]==0,"FACTORY_STREAM_IDENTITY")
    for key in ("source_start_ms","source_end_ms_exclusive","prefix_start_ms","prefix_end_ms_exclusive",
                "decision_cutoff_ms","warmup_input_count","raw_archive_size","issued_receipt_size"):
        require(type(m[key]) is int and 0<=m[key]<=2**53-1,"FACTORY_INTEGER_GEOMETRY")
    start,end=m["prefix_start_ms"],m["prefix_end_ms_exclusive"]
    require(start==m["source_start_ms"] and start%60000==0 and end%60000==0
        and start<end<=m["source_end_ms_exclusive"] and m["decision_cutoff_ms"]>=end
        and 22<=m["warmup_input_count"]<=(end-start)//60000<=1440,"FACTORY_PREFIX_CUTOFF_WARMUP")
    require(type(normalized7) in (list,tuple) and len(normalized7)==(end-start)//60000,
            "FACTORY_PREFIX_COUNT")
    bars=[]
    for i,row in enumerate(normalized7):
        require(type(row) in (list,tuple) and len(row)==7 and type(row[0]) is int
            and type(row[1]) is int and row[0]==start+i*60000 and row[1]==row[0]+59999
            and all(type(x) is float for x in row[2:]),"FACTORY_GRID_OR_RECORD")
        bars.append(HistoricalBar(symbol="BTCUSDT",interval="1m",bar_open=row[0],bar_close=row[1],
            open=row[2],high=row[3],low=row[4],close=row[5],volume=row[6],quality=BarQuality.FINAL,
            source=SourceType.FIXTURE,source_label=CONSUMER,observation_cutoff_ms=row[1]+1,
            ingest_time_ms=None,availability_kind=DataAvailabilityKind.RETROSPECTIVE))
    try:
        validate_bars(bars,"BTCUSDT","1m")
    except HistoricalDataError as exc:
        raise ResearchOnlyDenied("FACTORY_QUALITY") from exc
    require(is_sha(expected["prefix_normalized7_sha256"]) and digest(normalized7)==expected["prefix_normalized7_sha256"],
            "FACTORY_ROWS_COMMITMENT")
    return ResearchData(canonical({"schema":"factory-research-data-only-1","scope":SCOPE,
        "metadata":m,"normalized7":normalized7,"prefix_normalized7_sha256":digest(normalized7),
        "DEV_ONLY":True,"NOT_PIT":True,"NOT_EMPIRICALLY_VALIDATED":True,"actual_fill":False,
        "verified_source_timing":False,"real_pit_accepted":False,"empirical_eligible":False,
        "factory_execution_eligible":False,"issuer_first_available_at":"UNKNOWN",
        "correction_history":"UNKNOWN","bounded_UTC":"UNKNOWN","independent_custody":"UNKNOWN",
        "execution_policy":{k:"NOT_CONFIGURED" for k in ("source_lag","execution_delay","quote","spread",
            "slippage","fees","sizing","limit_expiry","tp_sl","intrabar_priority","sensitivity")},
        "warmup_meaning":"STRUCTURAL_INPUT_COUNT_NOT_STUDY_APPROVAL",
        "execution":"DENIED_NO_ENGINE_ENTRYPOINT"}))
