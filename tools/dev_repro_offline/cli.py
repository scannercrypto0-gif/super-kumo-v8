"""
Stage 11 — One-Command Operator Workflow CLI
Dry-run by default; --execute required to actually run tests.
Outputs JSON evidence bundle + Markdown summary.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .fingerprint import collect as collect_fingerprint, save as save_fingerprint
from .manifest import build_w1_manifest, save_manifest, load_manifest
from .preflight import run_preflight
from .runner import run_manifest
from .evidence import build_evidence_bundle, save_bundle
from .w1_coordinator import build_w1_coordinator_report
from .triage import triage_report as build_triage_report
from .portability import detect_platform, write_wrappers


def _now_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _find_repo_root() -> str:
    """Walk upward from cwd to find .git directory."""
    p = Path(os.getcwd())
    for candidate in [p] + list(p.parents):
        if (candidate / ".git").exists():
            return str(candidate)
    return os.getcwd()


def run(
    *,
    dry_run: bool = True,
    output_dir: Optional[str] = None,
    repo_root: Optional[str] = None,
    expected_sha: Optional[str] = None,
) -> int:
    """
    Full operator workflow.
    Returns exit code: 0 = success, 1 = preflight failed, 2 = tests failed.
    """
    root = repo_root or _find_repo_root()
    tag  = _now_tag()
    out  = Path(output_dir or os.path.join(root, "evidence", f"repro-{tag}"))
    out.mkdir(parents=True, exist_ok=True)

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    print(f"\n[AQL dev_repro_offline] {mode} | {tag}")
    print(f"  repo_root : {root}")
    print(f"  output_dir: {out}")

    # Stage 2 — fingerprint
    print("\n[1/6] Collecting environment fingerprint …")
    fp = collect_fingerprint(root)
    save_fingerprint(fp, out / "fingerprint.json")
    print(f"      digest={fp.digest[:16]}…")

    # Stage 3 — manifest
    print("[2/6] Building test manifest …")
    manifest_path = out / "manifest.json"
    manifest = build_w1_manifest(base_sha=fp.git.head_sha)
    save_manifest(manifest, manifest_path)
    blocked = manifest.blocked_entries()
    allowed = manifest.allowed_entries()
    print(f"      EXPECTED={len(allowed)} BLOCKED={len(blocked)}")

    # Stage 4 — preflight
    print("[3/6] Running preflight checks …")
    preflight = run_preflight(repo_root=root, expected_sha=expected_sha)
    print(f"      {preflight.summary()}")
    if preflight.overall.value == "FAIL":
        print("  ⚠  Preflight FAILED — recording failure in evidence (continuing to collect).")

    _write_preflight_report(preflight, out / "preflight.json")

    # Stage 5 — runner
    print(f"[4/6] Running manifest ({mode}) …")
    run_report = run_manifest(manifest, root, dry_run=dry_run)
    print(f"      {run_report.summary()}")

    # Stage 7 — W1 coordinator
    print("[5/6] Building W1 coordinator report …")
    w1 = build_w1_coordinator_report(run_report, fp.git.head_sha)
    w1_path = out / "w1_coordinator.txt"
    w1_path.write_text(w1.summary(), encoding="utf-8")
    print("      W1 coordinator summary written.")

    # Stage 6 — evidence bundle
    print("[6/6] Assembling evidence bundle …")
    bundle = build_evidence_bundle(
        fp, manifest, preflight, run_report,
        notes=f"mode={mode} sha={fp.git.head_sha}",
    )
    bundle_path = out / "evidence_bundle.json"
    save_bundle(bundle, bundle_path)
    print(f"      bundle_id={bundle.bundle_id} digest={bundle.digest[:16]}…")

    # Triage any failures
    triage = build_triage_report(run_report)
    if triage.entries:
        triage_path = out / "triage.json"
        triage_path.write_text(
            json.dumps(
                [{"entry_id": e.entry_id, "category": e.category.value,
                  "evidence": e.evidence, "hint": e.remediation_hint}
                 for e in triage.entries],
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"      {triage.summary()}")

    # Markdown summary
    _write_md_summary(fp, preflight, run_report, w1, bundle, triage, out / "SUMMARY.md",
                      dry_run=dry_run)

    # Platform wrappers
    info = detect_platform()
    write_wrappers(out / "scripts", info)

    print(f"\n✓ Evidence written to: {out}")
    fail_count = sum(1 for r in run_report.results
                     if r.status.value in ("FAIL", "TIMEOUT", "ERROR"))
    return 2 if fail_count else 0


def _write_preflight_report(preflight, path: Path) -> None:
    data = {
        "overall": preflight.overall.value,
        "head_sha": preflight.head_sha,
        "branch": preflight.branch,
        "checks": [
            {"id": c.check_id, "status": c.status.value,
             "detail": c.detail, "remediation": c.remediation}
            for c in preflight.checks
        ],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _write_md_summary(fp, preflight, run_report, w1, bundle, triage, path: Path,
                      *, dry_run: bool) -> None:
    mode = "DRY-RUN" if dry_run else "EXECUTED"
    lines = [
        "# AQL dev_repro_offline — Run Summary",
        "",
        f"**Mode**: {mode}",
        f"**Date**: {bundle.created_at_utc}",
        f"**HEAD SHA**: `{fp.git.head_sha}`",
        f"**Branch**: `{fp.git.branch}`",
        f"**Bundle ID**: `{bundle.bundle_id}`",
        f"**Bundle Digest**: `{bundle.digest[:32]}…`",
        "",
        "## Preflight",
        f"Overall: **{preflight.overall.value}**",
        "",
    ]
    for c in preflight.checks:
        lines.append(f"- `{c.check_id}` {c.status.value}: {c.detail}")
    lines += [
        "",
        "## Test Run",
        run_report.summary(),
        "",
    ]
    for r in run_report.results:
        lines.append(f"- `{r.entry_id}` → **{r.status.value}**"
                     + (f" ({r.notes[:80]})" if r.notes else ""))
    lines += [
        "",
        "## W1 Component Status",
        "```",
        w1.summary(),
        "```",
        "",
        "## Triage",
    ]
    if triage.entries:
        for e in triage.entries:
            lines.append(
                f"- `{e.entry_id}` [{e.category.value}]: {e.evidence[:80]}"
            )
    else:
        lines.append("No failures to triage.")
    lines += [
        "",
        "---",
        "*Generated by AQL-CLAUDE-DEV-ENV-REPRO-001 (#212)*",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="AQL dev_repro_offline — offline reproducibility toolkit"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true", default=True,
                      help="[DEFAULT] Check preflight and manifest without running tests.")
    mode.add_argument("--execute", dest="dry_run", action="store_false",
                      help="Actually run allowed tests (requires explicit opt-in).")
    parser.add_argument("--output-dir", default=None, help="Where to write evidence.")
    parser.add_argument("--repo-root",  default=None, help="Path to repository root.")
    parser.add_argument("--expected-sha", default=None,
                        help="Expected HEAD SHA prefix for validation.")
    args = parser.parse_args(argv)

    return run(
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        repo_root=args.repo_root,
        expected_sha=args.expected_sha,
    )


if __name__ == "__main__":
    sys.exit(main())
