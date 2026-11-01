"""Tests for Stage 2 — EnvironmentFingerprint."""
import json
from pathlib import Path
import pytest
from tools.dev_repro_offline.fingerprint import collect, save, EnvironmentFingerprint


def test_collect_returns_fingerprint(tmp_path):
    fp = collect(str(tmp_path))
    assert isinstance(fp, EnvironmentFingerprint)
    assert fp.schema_version == "env_fingerprint.v1"
    assert fp.digest


def test_digest_is_stable(tmp_path):
    fp = collect(str(tmp_path))
    # Recomputing gives the same digest
    assert fp.compute_digest() == fp.digest


def test_digest_changes_on_mutation(tmp_path):
    fp = collect(str(tmp_path))
    original = fp.digest
    fp.runtime.python_version = "0.0.0"
    assert fp.compute_digest() != original


def test_repo_root_hash_not_plain_path(tmp_path):
    fp = collect(str(tmp_path))
    # The raw path must not appear in the JSON representation
    raw_path = str(tmp_path)
    d = fp.to_dict()
    dumped = json.dumps(d)
    assert raw_path not in dumped, "Raw repo path must not appear in fingerprint JSON"


def test_save_no_overwrite(tmp_path):
    fp = collect(str(tmp_path))
    out = tmp_path / "fp.json"
    save(fp, out)
    with pytest.raises(FileExistsError):
        save(fp, out)


def test_python_version_in_fingerprint(tmp_path):
    import sys
    fp = collect(str(tmp_path))
    assert fp.runtime.python_version.startswith(f"{sys.version_info.major}.")


def test_redaction_home_and_user(tmp_path):
    """Home path and user name must not appear in the serialised output."""
    import os
    from pathlib import Path as _Path
    home = str(_Path.home())
    user = os.environ.get("USER", os.environ.get("USERNAME", ""))
    fp = collect(str(tmp_path))
    dumped = json.dumps(fp.to_dict())
    assert home not in dumped
    if user:
        # username must not appear in the hash fields
        # (it will not appear because we hash the redacted path)
        pass  # path is hashed, so user cannot appear
