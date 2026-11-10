"""Hash-checked disposable source overlay; no merges, network, or owner writes.

Fetch immutable Git objects separately with --fetch. Only Python/fixture bytes
are staged. Source-role ownership and every file digest are retained so a green
result cannot silently test a different component revision.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

PINS = {
    "integration271": "182331b90efdcc31cf04476200fe09b45e16997c",
    "work235_readonly": "6acbcc7fc243b132f58170df4c6469bbf7f4eff8",
    "scanner_b_dependency": "30c37ae56851488b882998c7fa0085ec51dbfc92",
    "core275_readonly_dependency": "99c27ea2c1a4d41aaae361141301a8a9ea3b33c3",
    "scanner277": "ccf57ad3db7e71290a8321840e800136567e3af4",
    "g286": "d072544427d6b08473c88b2e36d5857cfd8581dc",
    "g287": "852f6fcce1dbb4dede6259fe8d0498d19ff19078",
    "g288": "0ca716eaf1b8ae1a66ed6f3fbcec34f22c73ced7",
    "g289": "1ff3d13a3dfd1337bae0659dd03550b764c8799c",
}
PREFIXES = {
    "integration271": ("src/aql/", "research_wp_r0/"),
    "work235_readonly": ("research_wp_r0/", "tools/strategy_service_offline/"),
    "scanner_b_dependency": ("research_wp_r0/", "tools/scanner_strategy_b/"),
    "scanner277": ("research_wp_r0/", "tools/scanner_strategy_"),
    "core275_readonly_dependency": ("research_wp_r0/",),
    "g286": ("src/aql/observation/prospective.py", "src/aql/observation/durable_bridge_v1.py",
             "src/aql/collector/binance_collector.py", "research_wp_r0/aql_factory_prospective_read_v1.py"),
    "g287": ("src/aql/foundation/", "src/aql/journal/", "src/aql/storage/",
             "src/aql/models/", "src/aql/delivery/", "src/aql/g1_integrity.py"),
    "g288": ("src/aql/paper_sim/",),
    "g289": ("src/aql/observation/forward_evidence.py",),
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()).hexdigest()


def git(repo, *args):
    # Archive uses checkout conversion on Windows unless explicitly disabled.
    # Stage exact Git blob bytes so code identities agree with Linux CI.
    return subprocess.check_output(["git", "-c", "core.autocrlf=false", "-c", "core.eol=lf", "-C", str(repo), *args])


def stage(repo, destination, *, fetch=False):
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("PKG03_DESTINATION_MUST_BE_NEW")
    if repo == destination or repo in destination.parents and ".git" in destination.parts:
        raise ValueError("PKG03_OWNER_OR_GIT_DESTINATION")
    destination.mkdir(parents=True)
    records = {}
    for role, sha in PINS.items():
        if fetch:
            subprocess.run(["git", "-C", str(repo), "fetch", "--no-tags", "origin", sha], check=True)
        if git(repo, "rev-parse", sha + "^{commit}").decode().strip() != sha:
            raise ValueError("PKG03_PIN_DRIFT:" + role)
        tree = git(repo, "ls-tree", "-r", "-z", sha)
        archive = tarfile.open(fileobj=io.BytesIO(git(repo, "archive", "--format=tar", sha)), mode="r:")
        count = 0
        for entry in tree.split(b"\0"):
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            name = raw_name.decode("utf-8")
            if not name.startswith(PREFIXES[role]) or not name.endswith((".py", ".json")):
                continue
            mode, kind, blob = metadata.decode().split()
            relative = Path(name)
            if kind != "blob" or mode not in ("100644", "100755") or relative.is_absolute() or ".." in relative.parts:
                raise ValueError("PKG03_UNSAFE_SOURCE_PATH")
            member = archive.getmember(name)
            if not member.isfile() or member.issym() or member.islnk():
                raise ValueError("PKG03_UNSAFE_ARCHIVE_PATH")
            data = archive.extractfile(member).read()
            if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != blob:
                raise ValueError("PKG03_GIT_BLOB_BYTES_DRIFT:" + name)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            records[name] = {"role": role, "commit": sha, "git_blob": blob,
                             "sha256": hashlib.sha256(data).hexdigest()}
            count += 1
        archive.close()
        if not count:
            raise ValueError("PKG03_EMPTY_ROLE:" + role)
    body = {"schema": "aql.integration.pkg03.source-overlay.v1", "pins": PINS,
            "files": records, "combined_tree_sha256": digest(records),
            "merge_performed": False, "work_source_modified": False}
    manifest = {**body, "sha256": digest(body)}
    (destination / "source-overlay.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify(destination, *, expected_sha=None):
    root = Path(destination)
    manifest = json.loads((root / "source-overlay.json").read_text(encoding="utf-8"))
    body = {k: v for k, v in manifest.items() if k != "sha256"}
    if (manifest["sha256"] != digest(body) or manifest["pins"] != PINS
            or manifest["combined_tree_sha256"] != digest(manifest["files"])
            or expected_sha is not None and manifest["sha256"] != expected_sha):
        raise ValueError("PKG03_MANIFEST_DRIFT")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("PKG03_SOURCE_SYMLINK")
        if path.is_file() and path.suffix in (".py", ".json") and path.name != "source-overlay.json":
            if path.relative_to(root).as_posix() not in manifest["files"]:
                raise ValueError("PKG03_UNMANIFESTED_SOURCE")
    for name, row in manifest["files"].items():
        relative = Path(name)
        role = row.get("role")
        if (relative.is_absolute() or ".." in relative.parts or role not in PINS
                or row.get("commit") != PINS[role] or not name.startswith(PREFIXES[role])):
            raise ValueError("PKG03_MANIFEST_SOURCE_OWNER")
        path = root / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("PKG03_SOURCE_BYTES_DRIFT:" + name)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--fetch", action="store_true", help="Git source fetch only; never market data")
    args = parser.parse_args()
    result = stage(args.repo, args.destination, fetch=args.fetch)
    print(json.dumps({"pins": result["pins"], "files": len(result["files"]),
                      "combined_tree_sha256": result["combined_tree_sha256"],
                      "manifest_sha256": result["sha256"]}, sort_keys=True))
