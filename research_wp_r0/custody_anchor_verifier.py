"""Read-only research custody anchor verification; no independent trust claim.

The anchor must be supplied from a separately protected channel. This tool
cannot establish that channel's ACLs, retention, independence or authenticity.
"""
import hashlib
import json
from pathlib import Path


def verify_custody_bundle(bundle_root, anchor_path):
    """Fail closed on unexpected manifest shapes, paths, or digest drift."""
    root = Path(bundle_root).resolve(strict=True)
    anchor = Path(anchor_path).resolve(strict=True)
    if not root.is_dir() or anchor.is_dir():
        raise ValueError("Invalid bundle or anchor")
    if root == anchor or root in anchor.parents:
        raise ValueError("Anchor must be outside bundle")
    manifest_file = root / "custody-manifest.json"
    raw = manifest_file.read_bytes()
    expected = anchor.read_text(encoding="ascii").strip()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Invalid anchor SHA256")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError("Manifest differs from external anchor")
    manifest = json.loads(raw)
    if type(manifest) is not dict or set(manifest) != {"schema", "files"}:
        raise ValueError("Invalid custody manifest")
    if manifest["schema"] != "atlas-custody-v1" or type(manifest["files"]) is not list or not manifest["files"]:
        raise ValueError("Invalid custody schema or empty inventory")
    seen = set()
    for row in manifest["files"]:
        if type(row) is not dict or set(row) != {"path", "sha256"}:
            raise ValueError("Invalid inventory row")
        name, checksum = row["path"], row["sha256"]
        if type(name) is not str or not name or "\\" in name or name.startswith("/"):
            raise ValueError("Invalid path")
        if type(checksum) is not str or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
            raise ValueError("Invalid file SHA256")
        parts = name.split("/")
        if any(p in ("", ".", "..") for p in parts) or name == "custody-manifest.json" or name in seen:
            raise ValueError("Unsafe or duplicate path")
        seen.add(name)
        candidate = (root / name).resolve(strict=True)
        if root not in candidate.parents or not candidate.is_file() or candidate.is_symlink():
            raise ValueError("Unsafe or missing file")
        if hashlib.sha256(candidate.read_bytes()).hexdigest() != checksum:
            raise ValueError("Evidence file digest mismatch")
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual_files != seen | {"custody-manifest.json"}:
        raise ValueError("Unexpected or missing bundle files")
    return {"file_count": len(seen), "manifest_sha256": actual,
            "content_verified": True, "independent_custody_verified": False}
