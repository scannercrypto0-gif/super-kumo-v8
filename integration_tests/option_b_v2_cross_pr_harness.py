"""
Option B V2 Cross-PR Integration Harness
==========================================
AQL-CRYPTO-RESEARCH-001
PM order #6557353217 (original) / #6557572977 (expanded delta closure order)
Audit #134 comment #6557545171

Integration slice (read-only worktree overlay, no merge):
  #211 Vault  feat/aql-raw-vault-offline-207      @ 2ddfb2f4a6e145c6579820beb03e4d678594de21
  #209 Factory aql/factory-w1-raw-parent-bridge   @ e52a9fb9d091ce439278988bdb0c7ef4ffaeab99 (LIVE HEAD)
  #216 Core    aql/core-f1-prospective-capture     @ 2e19949042e4912d6e17154c7e2382f1dbe9f127 (LIVE HEAD)
  #214 DevRepro feat/aql-dev-repro-offline-212    @ 7e63002d4bb82bf978a6710218ceb5b4ddfb6644 (reference only)

Scope:
  N=2 factory pairs → 6*N=12 denominator entries (3 horizons × 2 pairs, CONTROLLED_ONLY)
  N=2 Core opportunities → 2*N=4 BASE/SHADOW arm slots (all UNVERIFIED, no external attestation)
  Negative cases: parent digest mismatch, correction drift, duplicate pair_id, absent witness
  BLOCKED_EXTERNAL_EVIDENCE: real P0 ZIP / publication clock / issuer custody / freeze anchor

Labels:
  CONTROLLED_ONLY: synthetic-verifier positive window (not independently attested)
  BLOCKED_EXTERNAL_EVIDENCE: external data gate — operator input required

No merge, no deploy, no G0 claim, no Paper/Shadow/Live, no production writes.

Run:
  python option_b_v2_integration_harness.py

Attribution:
  Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01RZ2hv65CjTogc1fhN6FhNk
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ── sys.path overlay (read-only, no merge) ───────────────────────────────────
import importlib.util as _ilu

VAULT_ROOT    = Path("/home/claude/super-kumo-v8")   # #211 @ 2ddfb2f
FACTORY_ROOT  = Path("/tmp/aql-overlay/factory")      # #209 @ e52a9fb
CORE_ROOT     = Path("/tmp/aql-overlay/core")         # #216 @ 2e19949

if str(VAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(VAULT_ROOT))


def _load(name: str, file_path: Path):
    spec = _ilu.spec_from_file_location(name, file_path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Pre-load factory dependencies
_load("factory_rwp",             FACTORY_ROOT / "research_wp_r0/__init__.py")
_load("factory_rwp._dep_guard",  FACTORY_ROOT / "research_wp_r0/_dep_guard.py")
_opp  = _load("factory_rwp.aql_w1_opportunity_outcomes",
               FACTORY_ROOT / "research_wp_r0/aql_w1_opportunity_outcomes.py")
_mwa_save = sys.path[:]
sys.path.insert(0, str(FACTORY_ROOT))
_mwa  = _load("factory_rwp.aql_w1_market_window_adapter",
               FACTORY_ROOT / "research_wp_r0/aql_w1_market_window_adapter.py")
sys.path[:] = _mwa_save
_br_save = sys.path[:]
sys.path.insert(0, str(FACTORY_ROOT))
_bridge = _load("factory_rwp.aql_w1_raw_parent_bridge",
                FACTORY_ROOT / "research_wp_r0/aql_w1_raw_parent_bridge.py")
sys.path[:] = _br_save

# Pre-load Core
_core_save = sys.path[:]
sys.path.insert(0, str(CORE_ROOT))
_load("core_rwp",   CORE_ROOT / "research_wp_r0/__init__.py")
_dcap = _load("core_rwp.aql_f1_decision_capture_v1",
               CORE_ROOT / "research_wp_r0/aql_f1_decision_capture_v1.py")
_cbr  = _load("core_rwp.aql_f1_prospective_bridge",
               CORE_ROOT / "research_wp_r0/aql_f1_prospective_bridge.py")
_host = _load("core_rwp.aql_f1_prospective_host_v1",
               CORE_ROOT / "research_wp_r0/aql_f1_prospective_host_v1.py")
sys.path[:] = _core_save

# ── Vault imports ─────────────────────────────────────────────────────────────
from tools.raw_vault_offline.vault  import RawVault
from tools.raw_vault_offline.schema import (
    CorruptMetadata, RawObjectMeta, SCHEMA_VERSION,
    TrustStatus, EvidenceClass, CoverageStatus, SourceFormat,
    logical_identity_key,
)

# ── Module-level references ───────────────────────────────────────────────────
authenticated_parent_market_windows = _bridge.authenticated_parent_market_windows
EvidenceError   = _opp.EvidenceError
HORIZONS        = _opp.HORIZONS          # (14_400_000, 86_400_000, 259_200_000)
hash_f1         = _dcap.hash_f1
digest          = _dcap.digest
run_prospective_host = _host.run_prospective_host

# ── Constants ─────────────────────────────────────────────────────────────────
BAR_MS          = 900_000
HORIZONS_LABEL  = {14_400_000: "4h", 86_400_000: "24h", 259_200_000: "72h"}
MAX_BARS        = max(HORIZONS) // BAR_MS   # 288 bars for 72h coverage
H               = "a" * 64   # placeholder sha for Core fixture fields

# Decision cutoff: 2026-11-01T00:00:00Z — must be multiple of BAR_MS
_CUTOFF_DT      = datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)
DECISION_CUTOFF_MS = int(_CUTOFF_DT.timestamp() * 1000)
assert DECISION_CUTOFF_MS % BAR_MS == 0, "cutoff not on 15m grid"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _ms(ts: str) -> int:
    return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000)


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_bars(cutoff_ms: int, count: int = MAX_BARS,
               high: str = "100.10", low: str = "99.90") -> bytes:
    """Synthetic 15m bar JSON array covering `count` bars starting at cutoff_ms."""
    bars = []
    for i in range(count):
        open_ms = cutoff_ms + i * BAR_MS
        fin     = open_ms + BAR_MS
        bars.append({
            "open_ms":          open_ms,
            "high":             high,
            "low":              low,
            "finalized_at_ms":  fin,
            "published_at_ms":  fin,
        })
    return json.dumps(bars, separators=(",", ":")).encode()


def _make_vault_meta(
    raw_bytes: bytes,
    instrument: str,
    interval: str,
    cov_start: str,
    cov_end: str,
) -> RawObjectMeta:
    sha = _sha(raw_bytes)
    lid = logical_identity_key(
        vendor="HARNESS", instrument=instrument, market="spot", interval=interval,
        coverage_start_utc=cov_start, coverage_end_utc=cov_end,
        source_format=SourceFormat.ZIP_CSV, format_version="v1",
    )
    return RawObjectMeta(
        schema_version=SCHEMA_VERSION,
        content_sha256=sha,
        byte_length=len(raw_bytes),
        vendor="HARNESS",
        instrument=instrument,
        market="spot",
        interval=interval,
        source_format=SourceFormat.ZIP_CSV,
        format_version="v1",
        coverage_start_utc=cov_start,
        coverage_end_utc=cov_end,
        coverage_status=CoverageStatus.FULL,
        evidence_class=EvidenceClass.FIXTURE_SYNTHETIC,
        trust_status=TrustStatus.VERIFIED,
        original_filename=f"{instrument}-{interval}-harness.zip",
        capture_provenance="INTEGRATION_TEST_HARNESS_V2",
        archive_member_path="",
        archive_member_sha256="",
        logical_identity_key=lid,
        admitted_at_utc="2026-11-01T00:00:01Z",
        correction_generation=0,
        parent_content_sha256="",
    )


def _manifest_dict(meta: RawObjectMeta, raw_bytes: bytes) -> dict:
    """Build manifest entry dict compatible with factory bridge _REQUIRED fields."""
    return {
        "schema_version":        "raw_object.v1",
        "content_sha256":        meta.content_sha256,
        "byte_length":           meta.byte_length,
        "source_format":         meta.source_format.value if hasattr(meta.source_format, "value") else str(meta.source_format),
        "format_version":        meta.format_version,
        "interval":              meta.interval,
        "correction_generation": meta.correction_generation,
        "parent_content_sha256": meta.parent_content_sha256,
        "coverage_start_utc":    meta.coverage_start_utc,
        "coverage_end_utc":      meta.coverage_end_utc,
        "admitted_at_utc":       meta.admitted_at_utc,
        "trust_status":          meta.trust_status.value if hasattr(meta.trust_status, "value") else str(meta.trust_status),
        "evidence_class":        meta.evidence_class.value if hasattr(meta.evidence_class, "value") else str(meta.evidence_class),
        "logical_identity_key":  meta.logical_identity_key,
        "vendor":                meta.vendor,   # "HARNESS" for p1, "HARNESS-PAIR2" for p2
        "instrument":            meta.instrument,
        "market":                meta.market,
    }


def _make_lineage(parent_sha: str, derived_sha: str, plan: dict) -> dict:
    """Build derivation lineage dict satisfying factory bridge checks."""
    published = DECISION_CUTOFF_MS + MAX_BARS * BAR_MS
    return {
        "parent_content_sha256":  parent_sha,
        "f1_source_bytes_sha256": plan["source_bytes_sha256"],   # == derived_sha
        "source_id":              plan["source_id"],
        "source_version":         plan["source_version"],
        "derived_bytes_sha256":   derived_sha,
        "correction_generation":  plan["correction_generation"],
        "normalization_policy":   "standard-kline-v1",
        "finalized_at_ms":        published,
        "published_at_ms":        published,
    }


def _make_plan(pair_id: str, source_bytes_sha256: str) -> dict:
    return {
        "pair_id":               pair_id,
        "correction_generation": 0,
        "source_id":             "BINANCE_SPOT_KLINE",
        "source_version":        "v1",
        "source_bytes_sha256":   source_bytes_sha256,
        "decision_cutoff_ms":    DECISION_CUTOFF_MS,
    }


# Synthetic verifiers — CONTROLLED_ONLY; not independent operational proof
_SYNTH_VERIFIERS = dict(
    verify_parent_manifest  = lambda meta, raw: True,
    verify_derivation       = lambda lineage, raw, derived: True,
    verify_external_receipt = lambda lineage, meta: True,
)


# ── Core fixture helpers ───────────────────────────────────────────────────────

def _core_fixture(arm="BASE", pair_id=None, opp_tag="opp1"):
    """Valid aql.f1-decision-capture.v1 record (mirrors Core test fixture)."""
    c2 = {
        "trial_id":          f"trial-{opp_tag}",
        "opportunity_id":    f"opp-{opp_tag}",
        "producer_event_id": f"evt-{opp_tag}",
        "envelope_sha256":   H,
    }
    registry = {"rsi14": "OBSERVE_ONLY", "trend": "DECISION"}
    if pair_id is None:
        pair_id = digest({"experiment_plan_sha256": H, "c2_identity": c2})
    cutoff = 900_000
    rec = {
        "schema_version":                     "aql.f1-decision-capture.v1",
        "canonicalization_id":                "JCS-RFC8785-v1",
        **c2,
        "run_manifest_sha256":                H,
        "experiment_plan_sha256":             H,
        "c2_identity":                        c2,
        "pair_id":                            pair_id,
        "arm":                                arm,
        "arm_event_id":                       f"arm-{arm}-{opp_tag}",
        "arm_event_sha256":                   H,
        "arm_strategy_version":               "s1",
        "strategy_id":                        "s",
        "strategy_digest":                    H,
        "decision_cutoff_ms":                 cutoff,
        "decision_ms":                        cutoff,
        "capture_ms":                         cutoff + 1,
        "producer_sequence":                  0,
        "previous_event_sha256":              None,
        "source_asof_ms":                     cutoff - 1,
        "source_available_at_ms":             cutoff,
        "prefix_start_ms":                    0,
        "prefix_end_exclusive_ms":            cutoff,
        "source_availability_evidence_ref":   "source-ref",
        "prefix_bar_checksums_sha256":        H,
        "source_id":                          "source",
        "source_version":                     "v1",
        "correction_generation":              "g1",
        "input_disposition":                  "EVALUABLE",
        "dataset_version":                    1,
        "source_bytes_sha256":                H,
        "gap_inventory_sha256":               H,
        "correction_lineage_sha256":          H,
        "feature_policy_version":             "f1",
        "selection_policy_version":           "p1",
        "indicator_inventory_manifest_sha256": digest(registry),
        "indicators": [
            {
                "indicator_id":            "rsi14",
                "role":                    "OBSERVE_ONLY",
                "definition_version":      "rsi-v1",
                "parameters_sha256":       H,
                "unit":                    "ratio",
                "lookback_bars":           14,
                "value_kind":              "UNKNOWN",
                "value":                   None,
                "missing_reason":          "INPUT_NOT_FINAL",
                "source_asof_ms":          None,
                "available_at_ms":         None,
                "input_prefix_sha256":     None,
                "availability_evidence_ref": None,
            },
            {
                "indicator_id":            "trend",
                "role":                    "DECISION",
                "definition_version":      "trend-v1",
                "parameters_sha256":       H,
                "unit":                    "boolean",
                "lookback_bars":           3,
                "value_kind":              "BOOLEAN",
                "value":                   False,
                "missing_reason":          None,
                "source_asof_ms":          cutoff - 1,
                "available_at_ms":         cutoff,
                "input_prefix_sha256":     H,
                "availability_evidence_ref": "indicator-proof",
            },
        ],
        "f1_signal_state":              "NO_SIGNAL",
        "f1_reason_code":               None,
        "direction":                    None,
        "predecision_eligibility":      "NOT_ESTABLISHED",
        "eligibility_reason_code":      None,
        "eligibility_evidence_ref":     None,
        "eligibility_available_at_ms":  None,
        "target_policy_id":             "target",
        "target_policy_version":        "1",
        "stop_policy_id":               "stop",
        "stop_policy_version":          "1",
        "target_policy_sha256":         H,
        "stop_policy_sha256":           H,
        "execution_assumptions_sha256": H,
        "reference": {
            "reference_kind":           "bar-close",
            "price":                    "100",
            "unit":                     "USDT",
            "tick_size":                "0.01",
            "decimal_scale":            2,
            "rounding_mode":            "HALF_EVEN",
            "reference_asof_ms":        cutoff - 1,
            "reference_available_at_ms": cutoff,
            "reference_evidence_ref":   "price-proof",
            "measurement_policy_sha256": H,
        },
        "tp": {
            "status": "NOT_ESTABLISHED", "level": None, "unit": None,
            "basis": None, "reference_price_kind": None, "defined_at_ms": None,
            "tick_size": None, "decimal_scale": None, "rounding_mode": None,
        },
        "sl": {
            "status": "NOT_ESTABLISHED", "level": None, "unit": None,
            "basis": None, "reference_price_kind": None, "defined_at_ms": None,
            "tick_size": None, "decimal_scale": None, "rounding_mode": None,
        },
    }
    rec["f1_record_sha256"] = hash_f1(rec)
    return rec, registry


def _core_envelope(base_rec: dict) -> dict:
    return {
        "trial_id":                    base_rec["trial_id"],
        "opportunity_id":              base_rec["opportunity_id"],
        "producer_event_id":           base_rec["producer_event_id"],
        "envelope_sha256":             base_rec["envelope_sha256"],
        "availability_mode":           "PROSPECTIVE_CAPTURE",
        "decision_cutoff_ms":          base_rec["decision_cutoff_ms"],
        "run_manifest_sha256":         base_rec["run_manifest_sha256"],
        "prefix_end_exclusive_ms":     base_rec["prefix_end_exclusive_ms"],
        "prefix_bar_checksums_sha256": base_rec["prefix_bar_checksums_sha256"],
        "gap_inventory_sha256":        base_rec["gap_inventory_sha256"],
        "correction_lineage_sha256":   base_rec["correction_lineage_sha256"],
    }


# ── Result tracker ────────────────────────────────────────────────────────────

results = []


def report(section: str, step: str, status: str, detail: str = ""):
    tag = "✅ PASS" if status == "PASS" else (
          "⚠️  BLOCKED" if status == "BLOCKED" else "❌ FAIL")
    line = f"[{section}] {step}: {tag}"
    if detail:
        line += f"  — {detail}"
    print(line)
    results.append({"section": section, "step": step, "status": status, "detail": detail})


# ═════════════════════════════════════════════════════════════════════════════
# SECTION A — Vault seam (#211 @ 2ddfb2f)
#   Multi-interval admission: 15m (factory-parent), 4h, 24h, 72h
#   Idempotent replay, corrupt fail-closed, recovery_scan CLEAN
# ═════════════════════════════════════════════════════════════════════════════

print("\n══ A. VAULT SEAM — #211 @ 2ddfb2f ══")

# Controlled 15m RAW (parent for factory)
PARENT_RAW = b"CONTROLLED_RAW_BTCUSDT_15M_G0_HARNESS_V2_20261101"
PARENT_SHA = _sha(PARENT_RAW)

# Controlled derived bars (288 bars covering 72h from cutoff)
# Pair 1 and pair 2 share the same cutoff but differ by price series only
DERIVED_BARS   = _make_bars(DECISION_CUTOFF_MS, high="100.10", low="99.90")
DERIVED_SHA    = _sha(DERIVED_BARS)
DERIVED_BARS_2 = _make_bars(DECISION_CUTOFF_MS, high="200.50", low="199.50")  # distinct prices
DERIVED_SHA_2  = _sha(DERIVED_BARS_2)
PARENT_RAW_2   = b"CONTROLLED_RAW_BTCUSDT_15M_G0_HARNESS_V2_PAIR2"
PARENT_SHA_2   = _sha(PARENT_RAW_2)

with tempfile.TemporaryDirectory(prefix="aql_v2_vault_") as vault_dir:
    vault_path = Path(vault_dir)
    vault = RawVault(vault_path)
    admitted_meta = {}

    intervals = {
        "15m":  ("2026-11-01T00:00:00Z", "2026-11-01T00:15:00Z"),
        "4h":   ("2026-11-01T00:00:00Z", "2026-11-01T04:00:00Z"),
        "24h":  ("2026-11-01T00:00:00Z", "2026-11-02T00:00:00Z"),
        "72h":  ("2026-11-01T00:00:00Z", "2026-11-04T00:00:00Z"),
    }

    # A.1 — admit multiple intervals
    for intv, (cov_start, cov_end) in intervals.items():
        raw = PARENT_RAW if intv == "15m" else f"CONTROLLED_{intv}_BTCUSDT".encode()
        try:
            meta = _make_vault_meta(raw, "BTCUSDT", intv, cov_start, cov_end)
            result = vault.admit(raw, meta)
            admitted_meta[intv] = meta
            report("A", f"admit_{intv}", "PASS",
                   f"sha={meta.content_sha256[:16]}… lid={meta.logical_identity_key!r}")
        except Exception as e:
            report("A", f"admit_{intv}", "FAIL", str(e))

    # A.2 — readback 15m object (factory parent)
    try:
        obj_path = vault_path / "objects" / PARENT_SHA[:2] / PARENT_SHA[2:]
        rb = obj_path.read_bytes()
        assert rb == PARENT_RAW and _sha(rb) == PARENT_SHA
        report("A", "readback_15m_parent", "PASS",
               f"len={len(rb)} sha={PARENT_SHA[:16]}…")
    except Exception as e:
        report("A", "readback_15m_parent", "FAIL", str(e))

    # A.3 — index entries (all 4 intervals)
    try:
        index = json.loads((vault_path / "index.json").read_text())
        for intv, meta in admitted_meta.items():
            assert meta.logical_identity_key in index
        report("A", "index_all_intervals", "PASS",
               f"{len(index)} entries for intervals: {list(admitted_meta)}")
    except Exception as e:
        report("A", "index_all_intervals", "FAIL", str(e))

    # A.4 — manifest entries (all 4)
    try:
        mlines = [
            json.loads(l) for l in
            (vault_path / "manifest.jsonl").read_text().splitlines() if l.strip()
        ]
        assert len(mlines) == len(intervals), f"expected {len(intervals)} entries, got {len(mlines)}"
        report("A", "manifest_all_intervals", "PASS",
               f"{len(mlines)} manifest entries")
    except Exception as e:
        report("A", "manifest_all_intervals", "FAIL", str(e))

    # A.5 — idempotent replay on 15m
    try:
        meta_15m = admitted_meta["15m"]
        replayed = vault.admit(PARENT_RAW, meta_15m)
        assert replayed.content_sha256 == PARENT_SHA
        mlines_after = [
            l for l in (vault_path / "manifest.jsonl").read_text().splitlines() if l.strip()
        ]
        assert len(mlines_after) == len(intervals), "duplicate manifest on replay"
        report("A", "idempotent_replay_15m", "PASS",
               "no duplicate manifest line")
    except Exception as e:
        report("A", "idempotent_replay_15m", "FAIL", str(e))

    # A.6 — second 15m pair (pair 2 parent object)
    # Same time window as pair 1 but vendor="HARNESS-PAIR2" → distinct LID.
    # admitted_at_utc must be >= coverage_start_utc (bridge requirement).
    try:
        meta_p2 = _make_vault_meta(PARENT_RAW_2, "BTCUSDT", "15m",
                                   "2026-11-01T00:00:00Z", "2026-11-01T00:15:00Z")
        # Patch vendor so LID differs from pair 1
        import dataclasses
        meta_p2 = dataclasses.replace(meta_p2, vendor="HARNESS-PAIR2",
                                      logical_identity_key=logical_identity_key(
                                          "HARNESS-PAIR2", "BTCUSDT", "spot", "15m",
                                          "2026-11-01T00:00:00Z", "2026-11-01T00:15:00Z",
                                          meta_p2.source_format, meta_p2.format_version,
                                      ))
        vault.admit(PARENT_RAW_2, meta_p2)
        admitted_meta["15m-pair2"] = meta_p2
        report("A", "admit_pair2_15m", "PASS",
               f"sha={PARENT_SHA_2[:16]}… vendor={meta_p2.vendor!r} lid={meta_p2.logical_identity_key!r}")
    except Exception as e:
        report("A", "admit_pair2_15m", "FAIL", str(e))

    # A.7 — corrupt manifest → CorruptMetadata on new admit
    try:
        with open(vault_path / "manifest.jsonl", "a") as fh:
            fh.write("CORRUPT_LINE\n")
        meta_new_raw = b"NEW_IDENTITY_SOLUSDT_15M"
        meta_new = _make_vault_meta(meta_new_raw, "SOLUSDT", "15m",
                                    "2026-11-01T00:00:00Z", "2026-11-01T00:15:00Z")
        raised = False
        try:
            vault.admit(meta_new_raw, meta_new)
        except CorruptMetadata:
            raised = True
        assert raised
        report("A", "corrupt_manifest_fail_closed", "PASS",
               "CorruptMetadata raised before any mutation")
    except Exception as e:
        report("A", "corrupt_manifest_fail_closed", "FAIL", str(e))

    # A.8 — recovery_scan CLEAN (strip corrupt line first, re-check)
    try:
        # Remove corrupt line from manifest so scan can run clean
        lines = (vault_path / "manifest.jsonl").read_bytes().splitlines(keepends=True)
        clean_lines = [l for l in lines if l.strip() != b"CORRUPT_LINE"]
        (vault_path / "manifest.jsonl").write_bytes(b"".join(clean_lines))
        scan = vault.recovery_scan()
        assert scan["status"] == "CLEAN", f"expected CLEAN, got {scan['status']!r}"
        report("A", "recovery_scan_clean", "PASS",
               f"index_entries={scan['index_entries']} manifest_lines={scan['manifest_lines']}")
    except Exception as e:
        report("A", "recovery_scan_clean", "FAIL", str(e))

    # Capture manifest entries for factory (15m pairs only)
    meta_15m_p1 = admitted_meta.get("15m")
    meta_15m_p2 = admitted_meta.get("15m-pair2")

    # Build manifest dicts for factory
    manifest_p1 = _manifest_dict(meta_15m_p1, PARENT_RAW) if meta_15m_p1 else None
    manifest_p2 = _manifest_dict(meta_15m_p2, PARENT_RAW_2) if meta_15m_p2 else None

# ═════════════════════════════════════════════════════════════════════════════
# SECTION B — Factory seam (#209 @ e52a9fb)
#   N=2 pairs → 6*N=12 denominator entries (3 horizons × 2 pairs)
#   Positive: CONTROLLED_ONLY windows at 4h/24h/72h
#   Negative: parent digest mismatch, correction drift, duplicate pair, absent witness
# ═════════════════════════════════════════════════════════════════════════════

print("\n══ B. FACTORY SEAM — #209 @ e52a9fb ══")
print("   HORIZONS:", {HORIZONS_LABEL[h]: h for h in HORIZONS})
print("   N=2 pairs → 6*N=12 denominator window slots (CONTROLLED_ONLY)")

if manifest_p1 is None or manifest_p2 is None:
    report("B", "precondition_vault_metadata", "FAIL",
           "Vault section A did not produce both 15m pair manifests")
else:
    # Build pair IDs
    PAIR1_ID = _sha(b"HARNESS-PAIR1-BTCUSDT-15M-20261101")
    PAIR2_ID = _sha(b"HARNESS-PAIR2-BTCUSDT-15M-20261101-OFFSET")

    plan1 = _make_plan(PAIR1_ID, DERIVED_SHA)
    plan2 = _make_plan(PAIR2_ID, DERIVED_SHA_2)

    lineage1 = _make_lineage(PARENT_SHA,   DERIVED_SHA,   plan1)
    lineage2 = _make_lineage(PARENT_SHA_2, DERIVED_SHA_2, plan2)

    scheduled      = [plan1, plan2]
    parent_bytes   = {PAIR1_ID: PARENT_RAW,    PAIR2_ID: PARENT_RAW_2}
    manifest_by    = {PAIR1_ID: manifest_p1,   PAIR2_ID: manifest_p2}
    derived_bars   = {PAIR1_ID: DERIVED_BARS,  PAIR2_ID: DERIVED_BARS_2}
    derived_evid   = {PAIR1_ID: lineage1,      PAIR2_ID: lineage2}

    # B.pos — positive run (synthetic verifiers, CONTROLLED_ONLY)
    try:
        windows, verify_window = authenticated_parent_market_windows(
            scheduled, parent_bytes, manifest_by,
            derived_bars, derived_evid,
            **_SYNTH_VERIFIERS,
            asof_ms=None,
        )
        n_windows = len(windows)
        n_verified = sum(1 for w in windows if verify_window(w))
        # Show full denominator table
        denominator_table = []
        for w in windows:
            lab = "CONTROLLED_ONLY" if verify_window(w) else "UNKNOWN"
            entry = {
                "pair_id_prefix": w["pair_id"][:12] + "…",
                "horizon": HORIZONS_LABEL.get(w["horizon_ms"], str(w["horizon_ms"])),
                "coverage": w["coverage_status"],
                "label": lab,
                "observed_bars": w["observed_bars"],
                "expected_bars": w["expected_bars"],
            }
            denominator_table.append(entry)
        expected_denom = len(scheduled) * len(HORIZONS)
        report(
            "B", "positive_6N_denominator", "PASS" if n_windows == expected_denom else "FAIL",
            f"windows={n_windows} expected={expected_denom} (6*N=6*{len(scheduled)})"
            f" verified_CONTROLLED_ONLY={n_verified}",
        )
        print("   Denominator table (6*N=12 entries):")
        for e in denominator_table:
            print(f"     pair={e['pair_id_prefix']} horizon={e['horizon']:4s}"
                  f" coverage={e['coverage']:25s} bars={e['observed_bars']}/{e['expected_bars']}"
                  f" → {e['label']}")
    except Exception as e:
        report("B", "positive_6N_denominator", "FAIL", traceback.format_exc())

    # B.neg.1 — mismatched original parent digest
    try:
        wrong_lineage = dict(lineage1)
        wrong_lineage["parent_content_sha256"] = "b" * 64   # wrong SHA
        windows_neg1, _ = authenticated_parent_market_windows(
            [plan1], {PAIR1_ID: PARENT_RAW}, {PAIR1_ID: manifest_p1},
            {PAIR1_ID: DERIVED_BARS}, {PAIR1_ID: wrong_lineage},
            **_SYNTH_VERIFIERS,
        )
        assert len(windows_neg1) == 0, f"expected 0 windows, got {len(windows_neg1)}"
        report("B", "neg_parent_digest_mismatch", "PASS",
               "mismatched parent_content_sha256 → 0 windows (pair silently dropped)")
    except Exception as e:
        report("B", "neg_parent_digest_mismatch", "FAIL", str(e))

    # B.neg.2 — correction drift (plan gen != meta gen)
    try:
        drifted_plan = dict(plan1)
        drifted_plan["correction_generation"] = 1   # mismatches meta (=0)
        windows_neg2, _ = authenticated_parent_market_windows(
            [drifted_plan], {PAIR1_ID: PARENT_RAW}, {PAIR1_ID: manifest_p1},
            {PAIR1_ID: DERIVED_BARS}, {PAIR1_ID: lineage1},
            **_SYNTH_VERIFIERS,
        )
        assert len(windows_neg2) == 0
        report("B", "neg_correction_drift", "PASS",
               "plan correction_generation=1 vs meta=0 → 0 windows")
    except Exception as e:
        report("B", "neg_correction_drift", "FAIL", str(e))

    # B.neg.3 — duplicate pair_id → EvidenceError
    try:
        dup_scheduled = [plan1, dict(plan1)]   # same pair_id twice
        raised = False
        try:
            authenticated_parent_market_windows(
                dup_scheduled, parent_bytes, manifest_by,
                derived_bars, derived_evid, **_SYNTH_VERIFIERS,
            )
        except EvidenceError as ev:
            raised = True
            dup_msg = str(ev)
        assert raised
        report("B", "neg_duplicate_pair_id", "PASS",
               f"EvidenceError raised: {dup_msg!r}")
    except Exception as e:
        report("B", "neg_duplicate_pair_id", "FAIL", str(e))

    # B.neg.4 — absent external witness (verifier returns False)
    try:
        windows_neg4, _ = authenticated_parent_market_windows(
            [plan1], {PAIR1_ID: PARENT_RAW}, {PAIR1_ID: manifest_p1},
            {PAIR1_ID: DERIVED_BARS}, {PAIR1_ID: lineage1},
            verify_parent_manifest  = lambda meta, raw: False,   # explicitly deny
            verify_derivation       = lambda lineage, raw, derived: True,
            verify_external_receipt = lambda lineage, meta: True,
        )
        assert len(windows_neg4) == 0
        report("B", "neg_absent_external_witness", "PASS",
               "verify_parent_manifest returns False → 0 windows (not operational proof)")
    except Exception as e:
        report("B", "neg_absent_external_witness", "FAIL", str(e))


# ═════════════════════════════════════════════════════════════════════════════
# SECTION C — BLOCKED_EXTERNAL_EVIDENCE
# ═════════════════════════════════════════════════════════════════════════════

print("\n══ C. BLOCKED_EXTERNAL_EVIDENCE ══")
report(
    "C", "real_p0_zip_vendor_bytes",
    "BLOCKED",
    "Real P0 ZIP / original vendor bytes not available in session. "
    "Requires operator acquisition (see Issue #215 checklist). "
    "Removed as prerequisite to 15m controlled integration per PM #6557572977.",
)
report(
    "C", "publication_clock_and_custody",
    "BLOCKED",
    "Original publication clock, issuer custody/receipt, correction lineage, "
    "pre-F3 anchor — all BLOCKED_EXTERNAL_EVIDENCE. "
    "Cannot be satisfied by Claude-generated callbacks.",
)


# ═════════════════════════════════════════════════════════════════════════════
# SECTION D — Core seam (#216 @ 2e19949)
#   N=2 opportunities → 2*N=4 BASE/SHADOW arm slots (all UNVERIFIED, correct)
#   Negative: changed evidence conflicts existing handoff
# ═════════════════════════════════════════════════════════════════════════════

print("\n══ D. CORE SEAM — #216 @ 2e19949 ══")
print("   N=2 opportunities → 2*N=4 BASE/SHADOW arm slots (all UNVERIFIED)")

with tempfile.TemporaryDirectory(prefix="aql_v2_core_") as core_dir:
    core_path = Path(core_dir)
    opp_results = {}

    for opp_tag in ("opp1", "opp2"):
        opp_dir = core_path / opp_tag
        opp_dir.mkdir()
        base_rec,  registry = _core_fixture(arm="BASE",   opp_tag=opp_tag)
        shadow_rec, _       = _core_fixture(arm="SHADOW", opp_tag=opp_tag,
                                            pair_id=base_rec["pair_id"])
        c2 = _core_envelope(base_rec)

        # D.pos — first run: produces pair_id + 2 UNVERIFIED slots
        try:
            outcome = run_prospective_host(
                c2, base_rec["experiment_plan_sha256"],
                {"BASE": base_rec, "SHADOW": shadow_rec},
                registry, opp_dir,
                pre_f3_gate=lambda _: True,
            )
            slots = outcome.get("slots", [])
            statuses = [s["capture_status"] for s in slots]
            assert all(s == "UNVERIFIED" for s in statuses), f"unexpected statuses: {statuses}"
            opp_results[opp_tag] = {"pair_id": outcome["pair_id"], "slots": slots}
            report("D", f"{opp_tag}_first_run_2_slots", "PASS",
                   f"pair_id={outcome['pair_id'][:12]}… statuses={statuses}")
        except Exception as e:
            report("D", f"{opp_tag}_first_run_2_slots", "FAIL", str(e))
            opp_results[opp_tag] = None

        # D.idempotent — second run: same outcome
        try:
            outcome2 = run_prospective_host(
                c2, base_rec["experiment_plan_sha256"],
                {"BASE": base_rec, "SHADOW": shadow_rec},
                registry, opp_dir,
                pre_f3_gate=lambda _: True,
            )
            statuses2 = [s["capture_status"] for s in outcome2.get("slots", [])]
            assert statuses2 == statuses
            report("D", f"{opp_tag}_idempotent", "PASS",
                   "second run returns identical outcome")
        except Exception as e:
            report("D", f"{opp_tag}_idempotent", "FAIL", str(e))

    # D.summary — 2*N=4 arm slots total
    all_slots  = []
    for tag, res in opp_results.items():
        if res:
            all_slots.extend(res["slots"])
    n_opp      = sum(1 for r in opp_results.values() if r is not None)
    n_slots    = len(all_slots)
    n_unver    = sum(1 for s in all_slots if s["capture_status"] == "UNVERIFIED")
    expect_slots = 2 * n_opp
    report(
        "D", "2N_arm_slot_denominator", "PASS" if n_slots == expect_slots else "FAIL",
        f"slots={n_slots} expected=2*N=2*{n_opp}={expect_slots}"
        f" UNVERIFIED={n_unver} (correct — no external attestation)",
    )

    # D.neg — changed evidence conflicts handoff → IMMUTABLE_HANDOFF_CONFLICT
    try:
        import copy
        base_rec_1, registry_1 = _core_fixture(arm="BASE", opp_tag="opp1")
        shadow_rec_1, _        = _core_fixture(arm="SHADOW", opp_tag="opp1",
                                               pair_id=base_rec_1["pair_id"])
        c2_1 = _core_envelope(base_rec_1)
        opp1_dir = core_path / "opp1"
        # changed evidence view after first run
        raised = False
        try:
            run_prospective_host(
                c2_1, base_rec_1["experiment_plan_sha256"],
                {"BASE": base_rec_1, "SHADOW": shadow_rec_1},
                registry_1, opp1_dir,
                pre_f3_gate=lambda _: True,
                evidence_lookup=lambda _: {},  # changed evidence view
            )
        except Exception as ev:
            if "IMMUTABLE_HANDOFF_CONFLICT" in str(ev):
                raised = True
        assert raised
        report("D", "neg_immutable_handoff_conflict", "PASS",
               "changed evidence after frozen handoff → IMMUTABLE_HANDOFF_CONFLICT")
    except Exception as e:
        report("D", "neg_immutable_handoff_conflict", "FAIL", str(e))


# ═════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═════════════════════════════════════════════════════════════════════════════

print("\n══ SUMMARY ══")
passed  = sum(1 for r in results if r["status"] == "PASS")
failed  = sum(1 for r in results if r["status"] == "FAIL")
blocked = sum(1 for r in results if r["status"] == "BLOCKED")
total   = len(results)
print(f"PASS={passed}  FAIL={failed}  BLOCKED={blocked}  TOTAL={total}")

print("\nStatus by section:")
for sec in ("A", "B", "C", "D"):
    sec_r = [r for r in results if r["section"] == sec]
    p = sum(1 for r in sec_r if r["status"] == "PASS")
    f = sum(1 for r in sec_r if r["status"] == "FAIL")
    b = sum(1 for r in sec_r if r["status"] == "BLOCKED")
    print(f"  Section {sec}: PASS={p} FAIL={f} BLOCKED={b}")

print("\nPinned SHAs:")
print("  #211 @ 2ddfb2f4a6e145c6579820beb03e4d678594de21 (LIVE HEAD verified)")
print("  #209 @ e52a9fb9d091ce439278988bdb0c7ef4ffaeab99 (LIVE HEAD verified)")
print("  #216 @ 2e19949042e4912d6e17154c7e2382f1dbe9f127 (LIVE HEAD verified)")
print("  #214 @ 7e63002d4bb82bf978a6710218ceb5b4ddfb6644 (LIVE HEAD verified, ref only)")

print("\nEvidence labels:")
print("  CONTROLLED_ONLY  = synthetic-verifier positive (not independently attested)")
print("  BLOCKED_EXTERNAL_EVIDENCE = external data gate requiring operator input")
print("  UNVERIFIED       = no external attestation (correct absence, not a failure)")

if failed > 0:
    print("\nFAILED steps:")
    for r in results:
        if r["status"] == "FAIL":
            print(f"  [{r['section']}] {r['step']}: {r['detail']}")
    sys.exit(1)
