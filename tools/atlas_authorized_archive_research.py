"""Native Core, Scanner and Factory orchestration for a pinned daily archive."""
import hashlib
import inspect
import io
import json
import os
import platform
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from aql.observation.contracts import digest
from research_wp_r0.aql_archive_custody_bridge_v1 import OfflineBridgeStager
from research_wp_r0.aql_authenticated_historical_admission_v1 import PIN_SCHEMA
from research_wp_r0.aql_core_backbone_local_v1 import admit_local_original, query_local
from research_wp_r0.aql_core_research_query_seam_v1 import REQUEST_SCHEMA
from research_wp_r0.aql_native_price_custody_query_v1 import query_price_custody
from research_wp_r0.historical_library import HistoricalLibrary
from research_wp_r0.aql_factory_e_research_results_store_v1 import build_experiment, register_experiment, read_experiment
from tools.atlas_prospective_observe import FIXTURE
from tools.historical_source_qa import qa
from tools.scanner_strategy_f import research_e2e_diagnostic as scanner
from tools.scanner_strategy_f.research_strategy_plugin import _definition

sha = lambda raw: hashlib.sha256(raw).hexdigest()


def require(value, code):
    if not value:
        raise ValueError(code)


def put(path, doc):
    encoded = json.dumps(doc, sort_keys=True, separators=(",", ":"), allow_nan=False)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def verify(root, experiment):
    record = json.loads((root / "result.json").read_text())
    decisions = json.loads((root / "scanner.json").read_text())
    manifest = json.loads((root / "source.json").read_text())
    factory = read_experiment(root / "factory.sqlite", experiment, detached_snapshot=True)
    require(record["sha256"] == digest({k:v for k,v in record.items() if k != "sha256"}), "RESULT_SEAL")
    require(digest(decisions) == record["scanner_sha256"] == factory["parent_receipt_sha256"]
            and digest(manifest) == record["source_manifest_sha256"] == factory["source_sha256"]
            and factory["sha256"] == record["factory_sha256"]
            and factory["orders_created"] == factory["paper_positions"] == 0
            and factory["actual_fills"] is None, "RESULT_PARENT_DRIFT")
    return record


def run(root, source, job):
    ARCHIVE, ZIP_SHA, CHECK_SHA = (job[k] for k in ("archive", "archive_sha256", "checksum_sha256"))
    START, END, CUTOFF = (job[k] for k in ("start_ms", "end_ms", "cutoff_ms"))
    EXPERIMENT = job["experiment"]
    paths = source / ARCHIVE, source / (ARCHIVE + ".CHECKSUM")
    raw, checksum = (qa.read_small(path, limit) for path, limit in zip(paths, (qa.MAX_ZIP, 512)))
    require(sha(raw) == ZIP_SHA and sha(checksum) == CHECK_SHA, "ORIGINAL_BYTE_PIN")
    manifest = dict(schema="aql.historical-source-manifest.v1", market=list(qa.MARKET),
                    native_interval="1m", start_ms=START, end_exclusive_ms=END, timestamp_unit="us" if START >= 1735689600000 else "ms",
                    evidence_class="RETROSPECTIVE_NON_PIT", pit="NOT_ATTESTED",
                    source_version=ZIP_SHA, rights_ref=job["rights_ref"],
                    rights_status="VERIFIED_FOR_EXACT_USE", owner_authorization_ref=job["authorization_ref"],
                    retention_scope=job["retention_scope"],
                    publisher_first_available_at_ms=None, archive_sha256=ZIP_SHA, checksum_sha256=CHECK_SHA)
    manifest_sha = digest(manifest)
    with patch.object(qa, "read_small", side_effect=(raw, checksum)):
        admitted = qa.admit(*paths, manifest, manifest_sha)
    require(len(admitted["records"]) == 1440 and not admitted["missing_opens_ms"], "ADMITTED_GRID")
    member = ARCHIVE[:-4] + ".csv"
    with ZipFile(io.BytesIO(raw)) as archive:
        member_sha = sha(archive.read(member))
    pin = dict(schema=PIN_SCHEMA, source_kind="BINANCE_KLINES_ZIP", original_object_id=EXPERIMENT,
               original_sha256=ZIP_SHA, provenance_reference="RETAINED_VISION_CHECKSUM_OWNER_AUTHORIZED",
               captured_at_ms=None, claimed_available_at_ms=None, expected_inventory_sha256=None,
               vault_object_metadata=None, universe_manifest_sha256=None, universe_member_count=None,
               test_only=False, archive_name=ARCHIVE, csv_member_name=member,
               csv_member_sha256=member_sha, checksum_file_sha256=CHECK_SHA)
    spec = dict(dataset_id=EXPERIMENT, version=1, symbol="BTCUSDT", interval="1m", exchange="BINANCE",
                market="SPOT", source_label="BINANCE_VISION_RETAINED", start_ms=START,
                end_exclusive_ms=END, as_of_ms=CUTOFF, parent_source_sha256=None,
                correction_reason=None, test_only=False)
    root.mkdir()
    put(root / "source.json", manifest)
    core = root / "core"
    custody = admit_local_original(core, raw, checksum, pin, spec, decision_cutoff_ms=CUTOFF)
    with closing(sqlite3.connect(core / "warehouse.sqlite")) as db:
        require(db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0] == 0, "CORE_CHECKPOINT")
    local = query_local(core, EXPERIMENT, 1, START, END, CUTOFF, required_source_sha256=ZIP_SHA,
                        require_complete=True, sqlite_immutable=True)
    library = HistoricalLibrary()
    OfflineBridgeStager(core / "stage").replay_committed(library)
    request = dict(schema=REQUEST_SCHEMA, dataset_id=EXPERIMENT, version=1, start_ms=START,
                   end_exclusive_ms=END, decision_cutoff_ms=CUTOFF, require_complete=True, confirmed_only=False)
    native = query_price_custody(library, request, expected_source_sha256=ZIP_SHA,
                                 expected_manifest_integrity_sha256=custody["manifest_integrity_sha256"])
    require(native["status"] == "OK" and local["coverage"] == "COMPLETE" and
            native["manifest_integrity_sha256"] == local["manifest_integrity_sha256"], "CORE_PARENT")
    require(len(native["bars"]) == len(local["bars"]) == 1440, "CORE_COUNT")
    for n,l,q in zip(native["bars"],local["bars"],admitted["records"],strict=True):
        require(n["bar_open_ms"] == l["bar_open_ms"] == q["open_ms"] and
                n["bar_close_ms"] == l["bar_close_ms"] == q["end_exclusive_ms"]-1 and
                all(n[k] == l[k] == float(q[k if k != "volume" else "base_volume"])
                    for k in ("open","high","low","close","volume")), "CORE_ROW_DRIFT")
    derived = qa.derive(admitted, "15m", CUTOFF)
    require(len(derived["records"]) == 96 and not derived["withheld"], "DERIVED_GRID")
    bars = [dict(bar_open_ms=b["open_ms"], bar_close_ms=b["end_exclusive_ms"]-1,
                 **{k:float(b[k if k != "volume" else "base_volume"])
                    for k in ("open","high","low","close","volume")}) for b in derived["records"]]
    fixture = json.loads(FIXTURE.read_text())[0]
    spec = fixture["payload"]
    definition = _definition(spec["definition"])
    output = scanner._eval_strategy(definition, bars)
    require(all(scanner._eval_strategy(definition, bars[:i])[-1] == output[i-1]
                for i in range(1, len(bars)+1)), "SCANNER_PREFIX_DRIFT")
    decisions = [dict(open_ms=b["open_ms"], historical_bar_end_ms=b["end_exclusive_ms"],
                      derived_sha256=b["sha256"], state=state,
                      historical_known_at_ms=None)
                 for b,(closed,state) in zip(derived["records"], output, strict=True)
                 if b["end_exclusive_ms"]-1 == closed]
    require(len(decisions) == 96, "SCANNER_GRID")
    receipt = dict(source_manifest_sha256=manifest_sha, core245=native["price_query_sha256"],
                   core253=local["query_sha256"], decision_cutoff_ms=CUTOFF,
                   evidence_class="RETROSPECTIVE_NON_PIT", strategy_sha256=spec["definition"]["digest"],
                   config_sha256=spec["config_digest"], decisions=decisions, current_entry="NO_CURRENT_ENTRY")
    scanner_sha = digest(receipt)
    put(root / "scanner.json", receipt)
    record = build_experiment(experiment_id=EXPERIMENT, lane="SCANNER",
              source_status="RETROSPECTIVE_SOURCE_ADMITTED_NOT_PIT", source_sha256=manifest_sha,
              source_query_245_sha256=receipt["core245"], source_query_253_sha256=receipt["core253"],
              strategy_definition_sha256=receipt["strategy_sha256"], config_sha256=receipt["config_sha256"],
              code_sha256=digest([sha(Path(__file__).read_bytes()), sha(Path(inspect.getfile(scanner)).read_bytes())]),
              environment_sha256=digest(platform.python_version()), parent_receipt_sha256=scanner_sha,
              attempts=[dict(attempt_id="one-day-ordered-census", candidate_id=spec["strategy_id"],
                             state="NOT_VERIFIED", source_receipt_sha256=scanner_sha)],
              evidence_class="RETROSPECTIVE_NON_PIT")
    db_path = root / "factory.sqlite"
    ack = register_experiment(db_path, record)
    require(read_experiment(db_path, EXPERIMENT) == record, "FACTORY_READBACK")
    put(root / "factory-ack.json", ack)
    body = dict(source_manifest_sha256=manifest_sha, core245=receipt["core245"], core253=receipt["core253"],
                archive_sha256=ZIP_SHA, checksum_sha256=CHECK_SHA, native_rows=1440, derived_rows=96,
                census=dict(Counter(d["state"] for d in decisions)), scanner_sha256=scanner_sha,
                factory_sha256=record["sha256"], factory_ack=ack, lab="NOT_ELIGIBLE_SPLIT_LOOKAHEAD",
                evidence_class="RETROSPECTIVE_NON_PIT", current_entry="NO_CURRENT_ENTRY",
                orders=0, actual_fills=None)
    pending = root / "result.pending"
    put(pending, {**body, "sha256":digest(body)})
    os.link(pending, root / "result.json")
    pending.unlink()
    return verify(root, EXPERIMENT)
