#!/usr/bin/env python3
"""Validate PR data from the trusted base checkout. Never execute proposed code."""
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}")
POLICY = ".github/anti-redo-policy.json"
REVIEW_MARKER = "ATLAS-ANTI-REDO-V2\n"
PROOFS = {"REAL_GAP": "PROCEED_TO_APPROVAL", "REUSE_WITH_ADAPTER": "CONNECT_EXISTING"}
EVIDENCE_ROLES = {"source", "test", "workflow", "fixture"}


class Blocked(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Blocked(message)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_keys)


def git(*args):
    return subprocess.check_output(["git", *args])


def object_at(commit, path):
    require(SHA.fullmatch(commit) and valid_path(path), "invalid object locator")
    raw = git("ls-tree", "-z", commit, "--", ":(literal)" + path)
    if not raw:
        return None
    metadata, actual = raw[:-1].split(b"\t", 1)
    mode, kind, oid = metadata.decode().split()
    require(actual.decode() == path, "ambiguous Git path")
    return (mode, oid) if kind == "blob" else None


def valid_path(path):
    return isinstance(path, str) and bool(path) and all(
        part not in {"", ".", ".."} for part in path.split("/")
    ) and not any(ord(char) < 32 or char == "\\" for char in path)


def changed_paths(base, head):
    bases = git("merge-base", "--all", base, head).decode().splitlines()
    require(len(bases) == 1, "ambiguous merge base")
    raw = git("diff", "--no-ext-diff", "--no-renames", "--name-only", "-z", bases[0], head, "--")
    return raw.decode().split("\0")[:-1]


def text_fields(obj, fields):
    return all(isinstance(obj.get(k), str) and obj[k].strip() for k in fields)


def unique_strings(values):
    return isinstance(values, list) and all(isinstance(v, str) and v for v in values) and len(set(values)) == len(values)


def pure_doc(path, docs, blob):
    # Exact reviewed blob pairs only. Policy/config/executable paths always need a record.
    parts = path.lower().split("/")
    return (path in docs and path.endswith(".md") and not any(p.startswith(".") for p in parts)
            and (len(parts) == 1 or parts[0] == "docs") and parts[:3] != ["docs", "pm", "anti-redo"]
            and blob == ("100644", docs[path]))


def manifest_digest(manifest):
    payload = {key: value for key, value in manifest.items() if key != "manifest_id"}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


def approvals(reviews, head):
    latest = {}
    for review in sorted(reviews, key=lambda r: r["id"]):
        state = review["state"]
        if state in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
            latest[review["user"]["id"]] = review
    return {uid: review for uid, review in latest.items()
            if review["state"] == "APPROVED" and review["commit_id"] == head
            and review["user"]["type"] == "User"}


def check_evidence(record, policy, head, blob_at, verify_run):
    reused = record["tests_reused"]
    supplied = record["evidence"]
    require(unique_strings(reused) and isinstance(supplied, dict) and set(supplied) == set(reused),
            "INVENTORY_REQUIRED: evidence IDs do not reconcile")
    for eid in reused:
        known = policy["evidence"].get(eid)
        require(isinstance(known, dict) and supplied[eid] == known,
                "INVENTORY_REQUIRED: unverified evidence identity")
        commit, objects = known["source_sha"], known["objects"]
        require(SHA.fullmatch(commit) and text_fields(known, ("runner", "run_url"))
                and set(objects) == EVIDENCE_ROLES,
                "INVENTORY_REQUIRED: incomplete trusted evidence")
        require(known["workflow_path"] in objects["workflow"] and verify_run(known),
                "INVENTORY_REQUIRED: CI run or runner identity unavailable")
        for entries in objects.values():
            require(isinstance(entries, dict) and entries, "INVENTORY_REQUIRED: missing evidence objects")
            for path, sha in entries.items():
                require(valid_path(path) and SHA.fullmatch(sha) and
                        blob_at(commit, path) == blob_at(head, path) == ("100644", sha),
                        "INVENTORY_REQUIRED: accepted source/test/workflow/fixture bytes changed")


def check_override(record, scope, now):
    if "override" not in record:
        return
    override = record["override"]
    require(isinstance(override, dict) and set(override) == {"scope", "reason", "expires_utc"}
            and override["scope"] == scope and text_fields(override, ("reason", "expires_utc")),
            "invalid override scope")
    expiry = override["expires_utc"]
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", expiry)
            and dt.datetime.fromisoformat(expiry) > now, "expired or invalid override")


def validate(policy, revision, paths, reviews, blob_at, ref_at, verify_run, now):
    require(policy["version"] == 2 and policy["repository"] == revision["repository"]
            and policy["base_ref"] == revision["base_ref"], "trusted policy scope mismatch")
    require(SHA.fullmatch(revision["head_sha"]) and SHA.fullmatch(revision["base_sha"]),
            "invalid revision")
    require(unique_strings(paths) and paths and all(map(valid_path, paths)), "missing or invalid diff")
    head = revision["head_sha"]
    sensitive = {path for path in paths if not pure_doc(path, policy["pure_docs"], blob_at(head, path))}
    signed = approvals(reviews, head)
    manifests = [(uid, decode(review["body"][len(REVIEW_MARKER):]))
                 for uid, review in signed.items() if uid in policy["pm_ids"]
                 and (review.get("body") or "").startswith(REVIEW_MARKER)]
    if not sensitive:
        require(not manifests, "unrelated assignment records")
        return 0, len(paths)
    require(len(manifests) == 1, "missing or ambiguous authenticated PM manifest")
    pm, manifest = manifests[0]
    require(manifest["revision"] == revision, "PR/head/base mismatch or stale base")
    require(manifest["manifest_id"] == manifest_digest(manifest), "invalid PM manifest digest")
    records = manifest["records"]
    require(isinstance(records, list) and records, "missing assignment records")
    covered, tasks = set(), set()
    for record in records:
        require(text_fields(record, ("task", "changed_seam", "authority", "rollback", "overlap_review",
                                     "owner_handoff", "crosswalk")), "missing reviewed task fields")
        task, changed, ids, contracts = (record[k] for k in ("task", "paths", "capability_ids", "contract_ids"))
        require(task not in tasks and all(unique_strings(v) and v for v in (changed, ids, contracts)),
                "invalid assignment scope")
        require(set(changed) <= sensitive and not covered.intersection(changed), "unrelated or multiply covered path")
        require(unique_strings(record["lookups"]) and record["lookups"]
                and unique_strings(record["later_decisions"]) and record["later_decisions"],
                "missing continuity or lookup evidence")
        require(PROOFS.get(record["proof"]) == record["disposition"] and record["proof"] in PROOFS,
                "disposition does not permit implementation review")
        require(isinstance(record["new_tests"], list) and all(
            text_fields(case, ("assertion", "rationale", "invalidation")) for case in record["new_tests"]
        ), "missing test rationale")
        pins = record["head_pins"]
        require(set(pins) == set(ids), "capability pin mismatch")
        allowed_contracts = set()
        for cid in ids:
            entry = policy["capabilities"].get(cid)
            require(entry is not None and SHA.fullmatch(entry["head_sha"]) and
                    pins[cid] == entry["head_sha"] == ref_at(entry["ref"]),
                    "INVENTORY_REQUIRED: unknown or stale capability")
            owned_contracts = set(entry["contracts"]) & set(contracts)
            require(owned_contracts, "capability has no scoped contract")
            allowed_contracts.update(owned_contracts)
            # Bind the component's authenticated approval to this exact PM manifest and task.
            require(any(
                (review.get("body") or "").strip() == f"ATLAS-COMPONENT-V2 {manifest['manifest_id']} {task}"
                for uid, review in signed.items() if uid != pm and uid in entry["owner_ids"]
            ), "missing authenticated component signoff")
        require(allowed_contracts == set(contracts), "unknown contract")
        check_evidence(record, policy, head, blob_at, verify_run)
        check_override(record, dict(revision, task=task, paths=changed, capability_ids=ids, contract_ids=contracts), now)
        tasks.add(task)
        covered.update(changed)
    require(covered == sensitive, "uncovered changed path")
    return len(records), len(paths)


def api(route):
    req = urllib.request.Request(
        "https://api.github.com/repos/" + os.environ["GITHUB_REPOSITORY"] + route,
        headers={"Authorization": "Bearer " + os.environ["GH_TOKEN"], "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return decode(response.read())


def verified_run(evidence):
    run_id, job_id = evidence["run_id"], evidence["job_id"]
    require(type(run_id) is int and type(job_id) is int and min(run_id, job_id) > 0,
            "INVENTORY_REQUIRED: invalid CI run or job ID")
    run = api(f"/actions/runs/{run_id}")
    job = api(f"/actions/jobs/{job_id}")
    return (run["head_sha"] == job["head_sha"] == evidence["source_sha"]
            and run["conclusion"] == job["conclusion"] == "success"
            and run["id"] == job["run_id"] == run_id and job["id"] == job_id
            and run["html_url"] == evidence["run_url"] and run["path"] == evidence["workflow_path"]
            and job["name"] == evidence["job_name"] and sorted(job["labels"]) == sorted(evidence["labels"]))


def review_pages(number):
    result = []
    for page in range(1, 101):
        chunk = api(f"/pulls/{number}/reviews?per_page=100&page={page}")
        require(isinstance(chunk, list), "malformed reviews response")
        result.extend(chunk)
        if len(chunk) < 100:
            return result
    raise Blocked("review pagination limit")


def revision_of(pr):
    require(pr["state"] == "open", "PR is no longer open")
    return {"repository": pr["base"]["repo"]["full_name"], "pr": pr["number"],
            "base_ref": pr["base"]["ref"], "base_sha": pr["base"]["sha"], "head_sha": pr["head"]["sha"]}


def expected_revision(event, event_name, read_pr):
    if event_name == "pull_request_target":
        expected = revision_of(event["pull_request"])
        require(revision_of(read_pr(expected["pr"])) == expected, "stale event base or head")
        return expected
    require(event_name == "workflow_dispatch", "trusted event unavailable")
    inputs = event["inputs"]
    number = inputs["pr_number"]
    require(isinstance(number, str) and re.fullmatch(r"[1-9][0-9]{0,9}", number),
            "invalid PR input")
    expected = revision_of(read_pr(int(number)))
    require(expected["head_sha"] == inputs["head_sha"] and
            expected["base_sha"] == inputs["base_sha"], "stale dispatch base or head")
    return expected


def live():
    event = decode(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
    expected = expected_revision(event, os.environ["GITHUB_EVENT_NAME"],
                                 lambda number: api(f"/pulls/{number}"))
    number = expected["pr"]
    base, head = expected["base_sha"], expected["head_sha"]
    require(git("rev-parse", "HEAD").decode().strip() == base == os.environ["GITHUB_WORKFLOW_SHA"],
            "validator checkout or workflow is not the pinned trusted base")
    policy_blob = object_at(base, POLICY)
    require(policy_blob is not None and policy_blob[0] == "100644", "trusted base policy is absent")
    policy = decode(git("cat-file", "blob", policy_blob[1]))
    git("fetch", "--no-tags", "origin", f"refs/pull/{number}/head")
    require(git("rev-parse", "FETCH_HEAD").decode().strip() == head, "fetched PR head changed")

    def ref_at(ref):
        require(re.fullmatch(r"heads/[A-Za-z0-9_./-]+", ref) and ".." not in ref, "invalid trusted capability ref")
        return api("/git/ref/" + ref)["object"]["sha"]

    reviews = review_pages(number)
    result = validate(policy, expected, changed_paths(base, head), reviews, object_at, ref_at, verified_run, dt.datetime.now(dt.timezone.utc))
    require(revision_of(api(f"/pulls/{number}")) == expected and review_pages(number) == reviews,
            "revision or review state changed during check")
    receipt = dict(expected, records=result[0], changed_paths=result[1],
                   approvals_sha256=manifest_digest({"reviews": reviews}))
    print("TRUSTED_VALIDATION_PASS " + json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    try:
        live()
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError) as exc:
        print(f"ENFORCEMENT_BLOCKED: {exc}", file=sys.stderr)
        sys.exit(1)
