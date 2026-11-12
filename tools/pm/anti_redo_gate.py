#!/usr/bin/env python3
"""Fail-closed ATLAS pre-assignment reuse gate; stdlib-only, offline."""
import argparse
import json
import pathlib
import re
import sys

HEX = re.compile(r"^[0-9a-f]{40}$")
DECISIONS = {"BLOCKED_DUPLICATE_RISK", "ALREADY_COVERED", "CONNECT_EXISTING", "INVENTORY_REQUIRED", "PROCEED_TO_APPROVAL"}
PROOF_TO_DECISION = {
    "DUPLICATE_OVERLAP": {"BLOCKED_DUPLICATE_RISK"},
    "COVERED": {"ALREADY_COVERED"},
    "REUSE_WITH_ADAPTER": {"CONNECT_EXISTING"},
    "UNKNOWN": {"INVENTORY_REQUIRED"},
    "REAL_GAP": {"PROCEED_TO_APPROVAL"},
}
MANDATORY = {"task", "capability_ids", "main_sha", "head_pins", "lookups", "crosswalk", "owner", "owner_handoff", "later_decisions", "changed_seam", "proof", "tests_reused", "new_tests", "authority", "rollback", "overlap_review", "disposition"}
# Docs-only changes don't create a build task. A new implementation must carry a
# human-reviewed record; this tool never grants execution or merge authority.
DOC_PREFIXES = ("docs/", ".github/ISSUE_TEMPLATE/", ".github/PULL_REQUEST_TEMPLATE")
DOC_FILES = ("README.md", "LICENSE", ".gitignore", ".github/workflows/anti-redo-gate.yml", "tools/pm/anti_redo_gate.py", "tools/pm/test_anti_redo_gate.py")

def load(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

def validate(record, known, main, heads):
    errors = []
    missing = MANDATORY - set(record)
    if missing:
        errors.append("missing fields: " + ",".join(sorted(missing)))
    ids = record.get("capability_ids")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(map(str, ids))):
        errors.append("missing or repeated capability IDs")
        ids = []
    unknown = set(ids) - known
    if unknown:
        errors.append("unknown capability IDs: " + ",".join(sorted(unknown)))
    if record.get("main_sha") != main:
        errors.append("stale main SHA")
    pins = record.get("head_pins")
    if not isinstance(pins, dict) or not pins:
        errors.append("missing head pins")
        pins = {}
    for cid in ids:
        if cid not in pins:
            errors.append("missing head pin for " + cid)
        elif not HEX.fullmatch(str(pins[cid])):
            errors.append("invalid head pin for " + cid)
        elif cid in heads and pins[cid] != heads[cid]:
            errors.append("stale head pin for " + cid)
    proof, decision = record.get("proof"), record.get("disposition")
    if decision not in DECISIONS or decision not in PROOF_TO_DECISION.get(proof, set()):
        errors.append("proof/disposition mismatch")
    for key in ("task", "crosswalk", "owner", "owner_handoff", "changed_seam", "authority", "rollback", "overlap_review"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            errors.append("empty " + key)
    for key in ("lookups", "later_decisions"):
        if not isinstance(record.get(key), list) or not record[key]:
            errors.append("missing " + key)
    if not isinstance(record.get("tests_reused"), list):
        errors.append("missing tests_reused list")
    new_tests = record.get("new_tests")
    if not isinstance(new_tests, list):
        errors.append("missing new_tests list")
    else:
        for case in new_tests:
            if not isinstance(case, dict) or not all(isinstance(case.get(k), str) and case[k].strip() for k in ("assertion", "rationale", "invalidation")):
                errors.append("new test missing justification")
    if record.get("tests_reused"):
        reuse = record.get("test_reuse_verification")
        if not isinstance(reuse, list) or len(reuse) != len(record["tests_reused"]):
            errors.append("missing exact test/fixture/runner verification")
        else:
            for item in reuse:
                if not isinstance(item, dict) or not all(isinstance(item.get(k), str) and item[k].strip() for k in ("evidence_id", "source_sha", "test_identity", "workflow_identity", "fixture_identity", "environment", "reviewer")):
                    errors.append("incomplete test reuse verification")
    if decision == "PROCEED_TO_APPROVAL":
        if not record.get("pm_approval_reference") or not record.get("component_review_reference"):
            errors.append("missing human signoffs (approval is not execution authority)")
    if record.get("override"):
        override = record["override"]
        if not isinstance(override, dict) or not all(isinstance(override.get(k), str) and override[k].strip() for k in ("pm", "component_owner", "reason", "expires_utc", "pinned_revision")):
            errors.append("invalid scoped override")
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", override["expires_utc"]):
            errors.append("invalid override expiry")
        elif override["pinned_revision"] != record.get("main_sha"):
            errors.append("stale override")
    return errors

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--changed", nargs="*", default=[])
    args = parser.parse_args()
    root = pathlib.Path(args.root)
    base = root / "docs/pm/anti-redo"
    try:
        caps, coverage = load(base / "capabilities.json"), load(base / "coverage-manifest.json")
        entries = caps["entries"]
        known = {e["id"] for e in entries}
        heads = {e["id"]: e["head"] for e in entries}
        main_sha = coverage["main_sha"]
        if caps["main_sha"] != main_sha or not HEX.fullmatch(main_sha):
            raise ValueError("registry baseline inconsistent")
        changed = [p for p in args.changed if p]
        source_changed = [p for p in changed if p not in DOC_FILES and not p.lower().endswith((".md", ".mdx", ".rst", ".txt")) and not p.startswith(DOC_PREFIXES) and not p.startswith("tools/pm/anti_redo_gate") and p != "tools/pm/test_anti_redo_gate.py"]
        records = sorted((base / "assignments").glob("*.json")) if (base / "assignments").exists() else []
        if source_changed and not records:
            raise ValueError("code changed without a pre-assignment record: " + ", ".join(source_changed[:12]))
        errors = []
        for path in records:
            record = load(path)
            errors += [str(path) + ": " + e for e in validate(record, known, main_sha, heads)]
        if errors:
            raise ValueError("; ".join(errors))
        print("ANTI_REDO_GATE_PASS: validated %d assignment record(s), %d changed code path(s); human semantic review still required" % (len(records), len(source_changed)))
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("ANTI_REDO_GATE_BLOCKED: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
