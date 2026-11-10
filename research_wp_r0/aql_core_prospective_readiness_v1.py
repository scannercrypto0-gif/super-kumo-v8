"""Bounded Core prospective admission rehearsal; never a real-source authority.

Reuse frozen_research_plan and G1 DurableJournal receipts. No downloader,
warehouse, evaluator, OOS release API or external witness backend is provided.
The caller retains the freeze digest independently. Local hashes and mocked
clocks/witnesses demonstrate safety behavior, NOT genuine PIT evidence.
"""
from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re

from aql.g1_integrity import content, fingerprint
from aql.journal.durable_journal import DurableJournal
from aql.models.bar import MarketBar
from research_wp_r0.aql_archive_custody_bridge_v1 import canonical, decode, digest
from research_wp_r0.frozen_research_plan import verify_research_plan

SCHEMA = "aql.core.prospective-readiness.synthetic.v1"
DAY_MS = 86_400_000
HEX = re.compile(r"[0-9a-f]{64}\Z")
IDENT = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
SOURCE_FIELDS = {"provider", "source_version", "symbol", "market", "interval",
                 "source_label", "rights_reference", "rights_sha256",
                 "observed_at_ms", "available_at_ms", "committed_at_ms",
                 "evidence_class"}
TIME_FIELDS = {"freeze_at_ms", "first_eligible_open_ms", "train_end_ms",
               "validation_end_ms", "oos_start_ms", "oos_end_ms", "step_ms",
               "embargo_ms"}
BINDINGS = {"evaluator_sha256", "search_space_sha256",
            "all_attempt_inventory_sha256", "risk_exit_sha256"}


class ReadinessError(ValueError):
    """Stable non-sensitive rejection code."""


def need(ok, code):
    if not ok:
        raise ReadinessError(code)


def _ms(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def _sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _safe(path):
    path = Path(path).absolute()
    for p in (path, *path.parents):
        if p.exists() or p.is_symlink():
            need(not p.is_symlink() and not
                 (getattr(p.lstat(), "st_file_attributes", 0) & 0x400),
                 "REPARSE_CUSTODY_DENIED")
    return path


def _validate(body, plan_raw):
    need(type(body) is dict and set(body) == {
        "schema", "mode", "source", "times", "bindings", "plan_sha256",
        "plan_bytes_sha256", "journal_instance_id", "witness",
        "real_cohort_status", "trading_authority"}, "FREEZE_FIELDS")
    need(body["schema"] == SCHEMA and body["mode"] == "SYNTHETIC_PROVIDER_MOCK_ONLY"
         and body["real_cohort_status"] == "BLOCKED_OWNER_AUTHORIZATION"
         and body["trading_authority"] == "NONE", "REAL_ACQUISITION_NOT_AUTHORIZED")
    need(_sha(body["plan_sha256"]) and _sha(body["plan_bytes_sha256"]), "PLAN_PIN")
    plan = verify_research_plan(plan_raw, body["plan_sha256"])
    need(hashlib.sha256(plan_raw).hexdigest() == body["plan_bytes_sha256"], "PLAN_BYTES")
    source, times, bindings = body["source"], body["times"], body["bindings"]
    need(type(source) is dict and set(source) == SOURCE_FIELDS, "SOURCE_FIELDS")
    need(source["evidence_class"] == "SYNTHETIC_PROVIDER_MOCK"
         and type(source["source_label"]) is str and source["source_label"].startswith("MOCK:"),
         "RETROSPECTIVE_OR_G2_NOT_PROSPECTIVE_OOS")
    need(all(type(source[k]) is str and IDENT.fullmatch(source[k]) is not None
             for k in ("provider", "source_version", "symbol", "market", "interval",
                       "source_label", "rights_reference"))
         and _sha(source["rights_sha256"]), "SOURCE_VERSION_RIGHTS_REQUIRED")
    need(type(times) is dict and set(times) == TIME_FIELDS
         and all(_ms(v) for v in times.values()), "TIME_FIELDS")
    need(all(_ms(source[k]) for k in
             ("observed_at_ms", "available_at_ms", "committed_at_ms")), "SOURCE_TIME_FIELDS")
    # available_at = source publication; observed_at = local receipt observation.
    need(source["available_at_ms"] <= source["observed_at_ms"] <=
         source["committed_at_ms"] <= times["freeze_at_ms"], "SOURCE_NOT_AVAILABLE_AT_FREEZE")
    need(0 < times["step_ms"] <= DAY_MS and times["embargo_ms"] >= 3 * DAY_MS,
         "PREDECLARED_EMBARGO_REQUIRED")
    need(times["freeze_at_ms"] < times["first_eligible_open_ms"] <
         times["train_end_ms"] < times["validation_end_ms"]
         and times["validation_end_ms"] + times["embargo_ms"] <= times["oos_start_ms"]
         < times["oos_end_ms"], "FREEZE_FIRST_SAMPLE_OR_SPLIT_CHRONOLOGY")
    need(all(times[k] % times["step_ms"] == 0 for k in
             ("first_eligible_open_ms", "train_end_ms", "validation_end_ms",
              "oos_start_ms", "oos_end_ms")), "SPLIT_GRID")
    need(type(bindings) is dict and set(bindings) == BINDINGS
         and all(_sha(v) for v in bindings.values()), "EVALUATOR_SEARCH_ATTEMPT_RISK_EXIT_PINS")
    need(plan["dataset_digest"] == digest(source) and plan["split_digest"] == digest(times)
         and plan["protocol_digest"] == digest(bindings), "FROZEN_PLAN_SCOPE_BINDING")
    witness = body["witness"]
    need(type(witness) is dict and set(witness) ==
         {"kind", "witnessed_at_ms", "reference", "commitment_sha256"}
         and witness["kind"] == "MOCK_EXTERNAL_PREFREEZE_WITNESS"
         and type(witness["reference"]) is str and
         IDENT.fullmatch(witness["reference"]) is not None
         and _ms(witness["witnessed_at_ms"])
         and times["freeze_at_ms"] <= witness["witnessed_at_ms"] <
             times["first_eligible_open_ms"], "PREFREEZE_WITNESS_REQUIRED")
    commitment = {k: v for k, v in body.items() if k != "witness"}
    need(witness["commitment_sha256"] == digest(commitment), "WITNESS_FREEZE_BINDING")
    need(type(body["journal_instance_id"]) is str and
         re.fullmatch(r"[0-9a-f]{32}", body["journal_instance_id"]) is not None,
         "JOURNAL_IDENTITY")


def seal_readiness(path, *, journal, plan_raw, plan_sha256, source, times,
                   bindings, witnessed_at_ms):
    """Create once before any journal row; caller must pin returned SHA elsewhere.

    Idempotent same-byte replay is allowed. A different plan/source/time cannot
    replace the seal. Clock and witness are explicitly MOCK inputs in this API.
    """
    need(type(journal) is DurableJournal, "EXISTING_G1_JOURNAL_REQUIRED")
    path = _safe(path)
    body = dict(schema=SCHEMA, mode="SYNTHETIC_PROVIDER_MOCK_ONLY", source=source,
                times=times, bindings=bindings, plan_sha256=plan_sha256,
                plan_bytes_sha256=hashlib.sha256(plan_raw).hexdigest(),
                journal_instance_id=journal.instance_id,
                real_cohort_status="BLOCKED_OWNER_AUTHORIZATION", trading_authority="NONE")
    body["witness"] = dict(kind="MOCK_EXTERNAL_PREFREEZE_WITNESS",
                           witnessed_at_ms=witnessed_at_ms,
                           reference="fixture-witness-only", commitment_sha256=digest(body))
    _validate(body, plan_raw)
    raw = canonical(body)
    if path.exists():
        need(path.is_file() and path.read_bytes() == raw, "FROZEN_SEAL_CANNOT_REPLACE")
    else:
        # Serialize the empty-journal check with existing G1 writers. This is
        # local software ordering, not an external wall-clock attestation.
        conn = journal._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            need(conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0] == 0,
                 "FREEZE_AFTER_FIRST_BAR_DENIED")
            with path.open("xb") as f:
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            conn.execute("COMMIT")
        finally:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            conn.close()
    return digest(body)


def admit_sample(path, *, expected_freeze_sha256, plan_raw, journal, stable_key,
                 observed_at_ms, available_at_ms, decision_cutoff_ms):
    """Read a bounded journal record and return provenance only, NEVER prices.

    OOS rows may remain in isolated custody but this consumer refuses to expose
    them. Replay after restart deterministically returns the same receipt.
    Supplied observed/available times are fixture assertions, not real witness.
    """
    path = _safe(path)
    need(path.is_file() and path.stat().st_size <= 100_000, "SEALED_FREEZE_MISSING")
    raw = path.read_bytes()
    body = decode(raw)
    need(_sha(expected_freeze_sha256) and digest(body) == expected_freeze_sha256
         and canonical(body) == raw, "FREEZE_PIN_MISMATCH")
    _validate(body, plan_raw)
    need(type(journal) is DurableJournal and journal.instance_id == body["journal_instance_id"],
         "JOURNAL_SOURCE_ISOLATION")
    need(type(stable_key) is str and len(stable_key) <= 200,
         "STABLE_KEY_REQUIRED")
    source, times = body["source"], body["times"]
    # Hard row bound; no whole warehouse traversal or private source access.
    rows = journal.replay(symbol=source["symbol"], interval=source["interval"],
                          final_only=False, limit=4097)
    need(len(rows) <= 4096, "BOUNDED_COHORT_EXCEEDED")
    found = [b for b in rows if b.stable_key() == stable_key]
    need(len(found) == 1, "COMMITTED_ELIGIBLE_SOURCE_REQUIRED")
    bar = found[0]
    need(type(bar.is_final) is bool and bar.is_final and
         bar.source == source["source_label"] and
         all(_ms(v) for v in (bar.bar_open, bar.bar_close, bar.ingested_at,
                             observed_at_ms, available_at_ms, decision_cutoff_ms))
         and bar.bar_open % times["step_ms"] == 0
         and bar.bar_close == bar.bar_open + times["step_ms"] - 1,
         "FINAL_SOURCE_GRID_REQUIRED")
    need(all(math.isfinite(v) for v in (bar.open, bar.high, bar.low, bar.close, bar.volume))
         and bar.low > 0 and bar.low <= min(bar.open, bar.close) <=
         max(bar.open, bar.close) <= bar.high and bar.volume >= 0, "PRICE_QUALITY")
    need(times["first_eligible_open_ms"] <= bar.bar_open < times["oos_end_ms"],
         "SAMPLE_NOT_STRICTLY_FUTURE_COHORT")
    need(bar.bar_close < available_at_ms <= observed_at_ms <= bar.ingested_at,
         "OBSERVED_AVAILABLE_INGEST_CHRONOLOGY")
    receipt = journal.commit_receipt(stable_key)
    committed = receipt.get("commit_return_observed_at_ms")
    need(receipt.get("status") == "SQLITE_COMMIT_RETURN_OBSERVED" and
         receipt.get("version") == receipt.get("record_contract_version") == 1
         and receipt.get("content_digest") == fingerprint(content(bar))
         and _ms(committed) and bar.ingested_at <= committed <= decision_cutoff_ms,
         "POST_COMMIT_CUTOFF_RECEIPT_REQUIRED")
    need(not (times["validation_end_ms"] <= bar.bar_open < times["oos_start_ms"]),
         "EMBARGO_SAMPLE_DENIED")
    need(bar.bar_open < times["oos_start_ms"], "OOS_SEALED_NO_PEEK")
    result = dict(schema=SCHEMA, status="PASS_SYNTHETIC_ADMISSION_ONLY",
                  freeze_sha256=expected_freeze_sha256, stable_key=stable_key,
                  content_sha256=receipt["content_digest"],
                  observed_at_ms=observed_at_ms, available_at_ms=available_at_ms,
                  commit_return_observed_at_ms=committed,
                  partition="TRAIN" if bar.bar_open < times["train_end_ms"] else "VALIDATION",
                  real_cohort_status="BLOCKED_OWNER_AUTHORIZATION",
                  independent_pit="NOT_ATTESTED", trading_authority="NONE")
    return {**result, "receipt_sha256": digest(result)}
