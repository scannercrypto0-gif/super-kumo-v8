"""Pinned #309 runtime integration for saved-only accounting."""
import json
import os

import pytest


@pytest.mark.skipif(not os.environ.get("CYCLE_DEPS"), reason="requires staged #309 dependencies")
def test_ordered_scanner_accounting_and_legacy_readback(tmp_path):
    from tools.atlas_saved_strategy_report import verify_saved_accounting
    from tools.first_research_cycle.test_market import canonical, fixture, invoke, sha
    from tools.first_research_cycle.verify_run import verify

    source = tmp_path / "source"
    root = tmp_path / "result"
    plan = fixture(source)
    process = invoke(source, plan, root, crash=True)
    assert process.returncode == 73, process.stdout + process.stderr
    process = invoke(source, plan, root)
    assert process.returncode == 0, process.stdout + process.stderr
    saved_result = (root / "result.json").read_bytes()
    process = invoke(source, plan, root)
    assert process.returncode == 0, process.stdout + process.stderr
    assert (root / "result.json").read_bytes() == saved_result

    result = json.loads(saved_result)
    assert result["status"] == "PASS_ADAPTER_SIMULATION_ONLY"
    assert result["trading_authority"] == "NONE" and result["actual_fills"] is None
    source.rename(tmp_path / "detached-source")
    before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    checked = verify_saved_accounting(root, result)
    assert checked["verified_cost_rows"] == result["populations"]["cost_rows"]
    assert checked["scanner_membership"]["receipt_sha256"] == result["scanner_receipt_sha256"]
    assert {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()} == before

    path = root / "scanner-census.json"
    path.unlink()
    with pytest.raises(ValueError, match="SCANNER_PARENT_MISSING_OR_INVALID"):
        verify_saved_accounting(root, result)
    path.write_bytes(before[path.name].replace(b"SOURCE_BLOCKED", b"SOURCE_CHANGED"))
    with pytest.raises(ValueError, match="SCANNER_RECEIPT_SEAL"):
        verify_saved_accounting(root, result)
    path.unlink()

    result.pop("scanner_receipt_sha256")
    result.pop("sha256")
    legacy = {**result, "sha256": sha(result)}
    (root / "result.json").write_bytes(canonical(legacy))
    expected = verify(root)
    assert "scanner_membership" not in expected
    assert verify_saved_accounting(root, legacy) == expected
    assert not path.exists()
