"""Stage 7 — Scientific and operational claim firewall.

Scans PR titles, bodies, and analysis notes for risk terms.
Emits REVIEW_REQUIRED for claims that assert scientific validity,
production readiness, or performance guarantees.
Never emits a scientific verdict. Negative fixtures required.
"""
from __future__ import annotations
import re
from typing import Literal

FirewallVerdict = Literal["REVIEW_REQUIRED", "NO_CONCERN_DETECTED", "CLAIM_FIREWALL_ERROR"]

# Terms that assert validated scientific or production claims
_RISK_PATTERNS: list[tuple[str, str]] = [
    (r"\bproven?\b", "asserts proof"),
    (r"\bguarantee[sd]?\b", "asserts guarantee"),
    (r"\bproduction[- ]ready\b", "asserts production readiness"),
    (r"\bstatistically significant\b", "asserts statistical significance"),
    (r"\boutperforms?\b", "asserts performance superiority"),
    (r"\bvalidated?\b", "asserts validation"),
    (r"\boptimal\b", "asserts optimality"),
    (r"\bscientifically\b", "asserts scientific claim"),
    (r"\bbacktested? successfully\b", "asserts backtest success"),
    (r"\bno false positives?\b", "absolute precision claim"),
    (r"\b100%\s+accurate\b", "absolute accuracy claim"),
    (r"\bready for (live|real|production)\b", "live-trading readiness claim"),
    (r"\bmerge[- ]ready\b", "merge-readiness claim"),
    (r"\bsafe to merge\b", "merge-safety claim"),
    (r"\bapproved\b", "approval claim — must be owner-explicit"),
]

_COMPILED = [(re.compile(pat, re.IGNORECASE), label) for pat, label in _RISK_PATTERNS]


def scan_text(text: str, source_label: str = "text") -> list[dict]:
    """Return list of firewall hits in text."""
    hits = []
    for pattern, label in _COMPILED:
        for m in pattern.finditer(text):
            hits.append({
                "source": source_label,
                "matched_text": m.group(0),
                "pattern_label": label,
                "position": m.start(),
                "verdict": "REVIEW_REQUIRED",
                "note": (
                    f"Claim requires human expert review before any action. "
                    f"This tool cannot verify: '{label}'."
                ),
            })
    return hits


def scan_pr_record(pr: dict) -> dict:
    """Scan a PR dict (title, body, analysis_note) for risk claims."""
    hits: list[dict] = []
    for field in ("title", "body", "analysis_note", "notes"):
        val = pr.get(field)
        if val and isinstance(val, str):
            hits.extend(scan_text(val, source_label=f"PR#{pr.get('number','?')}.{field}"))

    verdict: FirewallVerdict = "REVIEW_REQUIRED" if hits else "NO_CONCERN_DETECTED"
    return {
        "pr_number": pr.get("number"),
        "verdict": verdict,
        "hits": hits,
        "hit_count": len(hits),
        "classification": "CLAIM_SCAN_ONLY__NOT_A_SCIENTIFIC_VERDICT",
    }


def scan_snapshot_claims(prs: list[dict]) -> list[dict]:
    """Scan all PRs in snapshot; return results with at least one hit or all if none."""
    results = [scan_pr_record(pr) for pr in prs]
    # Always return all results so caller can build complete picture
    return results
