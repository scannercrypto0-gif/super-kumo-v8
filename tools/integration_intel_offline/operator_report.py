"""Stage 9 — Operator report: offline CLI producing JSON + Markdown.

Deterministic output. Explicit snapshot age. Read-only.
Never issues merge decisions or overrides PM priorities.
Threat model and limitations documented inline.
"""
from __future__ import annotations
import json
import textwrap
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Threat model (offline, read-only)
# ---------------------------------------------------------------------------
THREAT_MODEL = """
THREAT MODEL — AQL Integration Intel Toolkit
============================================
1. OFFLINE-FIRST: All analysis runs from a snapshot JSON file. No network
   calls at runtime. Network absence is the default safe state.
2. READ-ONLY: No git writes, no PR approvals, no merges, no deploys.
3. STALE DATA RISK: Snapshot may not reflect current GitHub state. Every
   report includes snapshot_age_hours and a STALENESS_WARNING if applicable.
4. EVIDENCE TRUST: Evidence entries are self-reported by PR authors unless
   labeled INDEPENDENT_AUDIT. The toolkit cannot independently verify CI
   results without network access — it classifies what is recorded.
5. CLAIM FIREWALL: Pattern-based only. May miss novel risk phrasings.
   REVIEW_REQUIRED is a flag, not a finding. Human review is required.
6. PATH ANALYSIS: Linux case-sensitive. Windows case-insensitive conflicts
   are flagged but not enforced. Always verify on target OS.
7. GOVERNANCE: This toolkit never declares a PR approved or a stage closed.
   Only the project owner (scannercrypto0-gif) has that authority.
8. ACCESS LIMITS: Cross-chat sources (ChatGPT/PM notebook #205) are
   inaccessible. Issue #207 RAW vault delivery status is UNKNOWN.
""".strip()

KNOWN_LIMITATIONS = [
    "Claim firewall is regex-based; novel risk phrasings may not be detected.",
    "Coverage plan proposes tests but cannot execute them.",
    "DAG cycle detection runs on declared depends_on only; implicit stacking may not be captured.",
    "Evidence entries are self-reported unless marked INDEPENDENT_AUDIT.",
    "Snapshot staleness is reported but not automatically remediated.",
    "Path collision analysis is Linux-native; Windows behavior may differ.",
    "Cross-chat sources (PM notebook #205) are inaccessible — disclosures may be incomplete.",
    "Issue #207 RAW vault delivery status is UNKNOWN.",
]


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_full_report(
    snapshot_meta: dict,
    dag_report: dict,
    collision_results: list[dict],
    evidence_report: dict,
    claim_results: list[dict],
    coverage_results: list[dict],
    readiness_report: dict,
    report_generated_at: str | None = None,
) -> dict:
    """Assemble the complete operator report as a dict (JSON-serializable)."""
    generated_at = report_generated_at or _now_utc_iso()
    snap_at = snapshot_meta.get("snapshot_at", "UNKNOWN")

    return {
        "report_kind": "AQL_INTEGRATION_INTEL_OFFLINE_REPORT",
        "report_version": "1",
        "generated_at": generated_at,
        "snapshot_at": snap_at,
        "snapshot_main_head_sha": snapshot_meta.get("main_head_sha", "UNKNOWN"),
        "access_limits": snapshot_meta.get("access_limits", []),
        "threat_model_summary": THREAT_MODEL,
        "known_limitations": KNOWN_LIMITATIONS,
        "dag": dag_report,
        "collisions": collision_results,
        "evidence_summary": evidence_report,
        "claim_firewall": claim_results,
        "coverage_plan": coverage_results,
        "release_readiness": readiness_report,
        "classification": (
            "READ_ONLY_OFFLINE_ANALYSIS__NOT_AN_APPROVAL__OWNER_DECISION_REQUIRED"
        ),
    }


def render_markdown(report: dict) -> str:
    """Render the operator report as a Markdown document."""
    rr = report.get("release_readiness", {})
    verdict = rr.get("verdict", "UNKNOWN")
    verdict_icon = "✅" if verdict == "READY_FOR_OWNER_REVIEW" else "🚫"

    blockers = rr.get("blockers", [])
    gates = rr.get("gates", [])
    collisions = report.get("collisions", [])
    claims = [r for r in report.get("claim_firewall", []) if r.get("verdict") == "REVIEW_REQUIRED"]
    dag = report.get("dag", {})
    cycles = dag.get("cycles", [])
    missing = dag.get("missing_parents", {})

    lines = [
        "# AQL Integration Intelligence Report",
        f"**Generated:** {report.get('generated_at', 'UNKNOWN')}  ",
        f"**Snapshot:** {report.get('snapshot_at', 'UNKNOWN')}  ",
        f"**main HEAD:** `{report.get('snapshot_main_head_sha', 'UNKNOWN')}`  ",
        f"**Classification:** {report.get('classification', '')}",
        "",
        f"## {verdict_icon} Release Readiness: {verdict}",
        "",
    ]

    if blockers:
        lines.append("### 🚫 Blockers")
        for b in blockers:
            lines.append(f"- **{b['name']}**: {b['evidence']}")
        lines.append("")

    lines += [
        "### Gate Summary",
        "| Gate | Status | Evidence |",
        "|------|--------|----------|",
    ]
    for g in gates:
        icon = {"PASS": "✅", "FAIL": "❌", "PENDING": "⏳", "WAIVED": "⚠️"}.get(g["status"], "?")
        lines.append(f"| {g['name']} | {icon} {g['status']} | {g['evidence']} |")

    lines += [
        "",
        "## DAG Analysis",
        f"- PR count: {dag.get('pr_count', '?')}",
        f"- Cycles: {len(cycles)} {'⚠️' if cycles else '✅'}",
        f"- Missing parents: {len(missing)} {'⚠️' if missing else '✅'}",
        f"- Candidate review order: {dag.get('candidate_review_order', 'N/A')}",
        f"- Ambiguous order: {dag.get('ambiguous_order', '?')}",
        "",
        "## Collision Analysis",
    ]
    if collisions:
        for c in collisions:
            lines.append(f"- PR#{c.get('pr_a')} × PR#{c.get('pr_b')}: **{c.get('kind')}**")
    else:
        lines.append("- ✅ No collisions detected")

    lines += [
        "",
        "## Claim Firewall",
    ]
    if claims:
        for r in claims:
            lines.append(f"- PR#{r.get('pr_number')}: {r.get('hit_count')} REVIEW_REQUIRED hit(s)")
    else:
        lines.append("- ✅ No REVIEW_REQUIRED claims found")

    lines += [
        "",
        "## Access Limits",
    ]
    for lim in report.get("access_limits", []):
        lines.append(f"- {lim}")

    lines += [
        "",
        "## Known Limitations",
    ]
    for lim in report.get("known_limitations", []):
        lines.append(f"- {lim}")

    lines += [
        "",
        "---",
        "> ⚠️ This report is read-only offline analysis. "
        "Only the project owner can approve merges or stage transitions.",
    ]

    return "\n".join(lines)


def render_json(report: dict, indent: int = 2) -> str:
    return json.dumps(report, indent=indent, ensure_ascii=False, default=str)
