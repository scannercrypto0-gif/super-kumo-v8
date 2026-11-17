"""Verify the frozen candidate bundle using a disposable Git repository."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

SOURCE = "https://github.com/scannercrypto0-gif/super-kumo-v8.git"
DEPENDENCIES = {
    "discoverer": "9b60eb00aa890ecbd7e617925896e02963c1b5e3",
    "factory": "04b63cc9b406b1f3eae2ac7de5d43ebda26dbfdf",
    "scanner": "ccf57ad3db7e71290a8321840e800136567e3af4",
    "core": "d072544427d6b08473c88b2e36d5857cfd8581dc",
}


def require(value, code):
    if not value:
        raise ValueError(code)


def verify(dossier, clone, upstream, output):
    for line in (dossier / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        require(Path(name).name == name, "INVALID_CHECKSUM_PATH")
        require(hashlib.sha256((dossier / name).read_bytes()).hexdigest() == expected,
                f"DOSSIER_CHECKSUM_{name}")
    manifest = json.loads((dossier / "ordered-merge-manifest.json").read_bytes())
    base = manifest["main"]
    batches = manifest["ordered_batches"]
    clone.mkdir()
    env = os.environ.copy()

    def git(*args, data=None, binary=False):
        value = subprocess.check_output(["git", "-C", str(clone), *args], input=data, env=env)
        return value if binary else value.decode().strip()

    git("init", "-q")
    git("config", "core.autocrlf", "false")
    git("config", "transfer.fsckObjects", "true")
    git("remote", "add", "origin", SOURCE)
    git("fetch", "--no-tags", "origin", "refs/heads/main:refs/remotes/origin/main",
        *(f"refs/pull/{b['source_pr']}/head:refs/remotes/source/{b['source_pr']}" for b in batches),
        *DEPENDENCIES.values())
    require(git("rev-parse", "refs/remotes/origin/main") == base, "MAIN_ADVANCED")
    bundle = dossier / "candidates.bundle"
    git("bundle", "verify", str(bundle))
    advertised = dict(reversed(line.split()) for line in git("bundle", "list-heads", str(bundle)).splitlines())
    expected = {f"refs/heads/consolidation-review/{b['batch'].lower()}": b["candidate"] for b in batches}
    require(advertised == expected, "BUNDLE_REF_SET")
    git("fetch", "--no-tags", str(bundle), "refs/heads/consolidation-review/*:refs/heads/review/*")
    git("fsck", "--strict", "--no-dangling")
    index_dir = TemporaryDirectory()
    env["GIT_INDEX_FILE"] = str(Path(index_dir.name) / "reconstructed-index")
    seen = set()
    parent = base
    rows = []
    for batch in batches:
        tag, source, candidate = (batch[name] for name in ("batch", "source_head", "candidate"))
        require(git("rev-parse", f"refs/remotes/source/{batch['source_pr']}") == source,
                f"{tag}_SOURCE_HEAD_MOVED")
        require(git("merge-base", base, source) == base, f"{tag}_SOURCE_BASE")
        commit_body = git("cat-file", "commit", candidate, binary=True)
        exact = git("hash-object", "-t", "commit", "--stdin", data=commit_body)
        require(exact == candidate and git("show", "-s", "--format=%P", candidate) == parent == batch["base"],
                f"{tag}_COMMIT_OR_PARENT")
        paths = batch["paths"]
        require(not seen.intersection(paths), f"{tag}_PATH_COLLISION")
        seen.update(paths)
        require(git("diff", "--name-only", parent, candidate).splitlines() == paths,
                f"{tag}_PATH_SET")
        history = git("log", "--format=%H", f"{base}..{source}", "--", *paths).splitlines()
        require(history == batch["source_commits"], f"{tag}_SOURCE_HISTORY")
        require(git("show", "-s", "--format=%an%x00%ae%x00%aI", candidate)
                == git("show", "-s", "--format=%an%x00%ae%x00%aI", source), f"{tag}_AUTHOR")
        git("read-tree", parent)
        blobs = {}
        for path in paths:
            entry = git("ls-tree", source, "--", path)
            require(entry and entry == git("ls-tree", candidate, "--", path), f"{tag}_BLOB_MODE_{path}")
            meta, _ = entry.split("\t", 1)
            mode, kind, blob = meta.split()
            require(kind == "blob" and mode in ("100644", "100755"), f"{tag}_FILE_TYPE")
            git("update-index", "--add", "--cacheinfo", f"{mode},{blob},{path}")
            blobs[path] = {"mode": mode, "blob": blob}
        require(git("write-tree") == batch["tree"] == git("rev-parse", f"{candidate}^{{tree}}"),
                f"{tag}_TREE_RECONSTRUCTION")
        git("diff", "--check", parent, candidate)
        rows.append({"id": tag, "parent": parent, "candidate": exact, "tree": batch["tree"],
                     "source": source, "blobs": blobs})
        parent = exact
    git("read-tree", parent)
    rollback = []
    for batch in reversed(batches):
        patch = git("diff", "--binary", batch["base"], batch["candidate"], binary=True)
        git("apply", "--cached", "--reverse", data=patch)
        previous = git("rev-parse", f"{batch['base']}^{{tree}}")
        require(git("write-tree") == previous, f"{batch['batch']}_ROLLBACK")
        rollback.append({"undo": batch["batch"], "restored_tree": previous})
    env.pop("GIT_INDEX_FILE")
    index_dir.cleanup()
    git("checkout", "-q", "--detach", parent)
    require(git("rev-parse", "HEAD") == parent and not git("status", "--porcelain"), "CHECKOUT_IDENTITY")
    upstream.mkdir()
    for name in ("prospective.py", "durable_bridge_v1.py"):
        (upstream / name).write_bytes(git("show", f"{DEPENDENCIES['core']}:src/aql/observation/{name}",
                                          binary=True))
    proof = {"main": base, "candidate": parent, "batches": rows, "rollback": rollback,
             "test_dependencies": DEPENDENCIES, "frozen_manifest_sha256":
                 hashlib.sha256((dossier / "ordered-merge-manifest.json").read_bytes()).hexdigest()}
    output.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {len(rows)} batches and reversed to {base}; checkout {parent}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("dossier", "clone", "upstream", "output"):
        cli.add_argument(key, type=Path)
    args = cli.parse_args()
    verify(*(getattr(args, key).resolve() for key in ("dossier", "clone", "upstream", "output")))
