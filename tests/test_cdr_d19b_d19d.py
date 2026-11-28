import hashlib
from unittest.mock import patch

import pytest

from tools.atlas_ws_gap_inventory import inventory
from tools.atlas_ws_resilience_operator import rollback_stage


def test_nonallowlisted_receipt_filename_fails_closed(tmp_path):
    receipts=tmp_path/"receipts"
    receipts.mkdir()
    (receipts/"receipt.json").write_text("{}",encoding="utf-8")
    with pytest.raises(ValueError,match="GAP_RECEIPT_NAME_NOT_ALLOWLISTED"):
        inventory(receipts,start_ms=0,end_ms=900_000,as_of_ms=900_000)


def test_receipt_census_cap_fails_closed_without_partial_inventory(tmp_path):
    receipts=tmp_path/"bounded-receipts"
    receipts.mkdir()
    (receipts/"1.json").write_text("{}",encoding="utf-8")
    (receipts/"2.json").write_text("{}",encoding="utf-8")
    with patch("tools.atlas_ws_gap_inventory.MAX_RECEIPTS",1):
        with pytest.raises(ValueError,match="GAP_RECEIPT_CENSUS_BOUND"):
            inventory(receipts,start_ms=0,end_ms=900_000,as_of_ms=900_000)


def test_isolated_rollback_restores_candidate_config_and_preserves_hold(tmp_path):
    root=tmp_path/"root"
    backup=root/"backup"
    root.mkdir();backup.mkdir()
    runtime=tmp_path/"runtime.py"
    config=root/"config.json"
    old_runtime=b"old runtime\n"
    new_runtime=b"candidate runtime\n"
    old_config=b'{"tree":"old"}\n'
    new_config=b'{"tree":"candidate"}\n'
    runtime.write_bytes(new_runtime)
    config.write_bytes(new_config)
    (backup/"file-0000").write_bytes(old_runtime)
    (backup/"config.json").write_bytes(old_config)
    hold=b'{"status":"HOLD"}\n'
    (root/"hold.json").write_bytes(hold)
    marker=root/"operator-deployment.in-progress"
    marker.write_bytes(b"marker\n")
    manifest={
        "files":[{"path":str(runtime),"backup":"file-0000",
            "old_sha256":hashlib.sha256(old_runtime).hexdigest(),
            "new_sha256":hashlib.sha256(new_runtime).hexdigest()}],
        "config_sha256":hashlib.sha256(old_config).hexdigest(),
        "config_path":str(config),
    }

    rollback_stage(root,backup,manifest)

    assert runtime.read_bytes()==old_runtime
    assert config.read_bytes()==old_config
    assert (root/"hold.json").read_bytes()==hold
    assert not marker.exists()
    assert (backup/"deployment-marker.rolled-back.json").exists()

