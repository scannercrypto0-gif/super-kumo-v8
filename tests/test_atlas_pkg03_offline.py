"""Bounded meaningful acceptance tests for the isolated current-head seam."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from atlas_pkg03_stage import PINS, digest, stage, verify


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    target = tmp_path_factory.mktemp("pkg03") / "receipt"
    result = subprocess.run([sys.executable, "-B", str(ROOT / "tools/atlas_pkg03_smoke.py"),
                             "--repo", str(ROOT), "--output", str(target)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    return target


def test_joint_actual_component_receipt_and_process_death(completed):
    receipt = json.loads((completed / "delivery.json").read_text())
    assert receipt["sha256"] == digest({k: v for k, v in receipt.items() if k != "sha256"})
    assert receipt["pins"] == PINS
    assert [p["returncode"] for p in receipt["processes"]] == [0, 73, 0]
    result = receipt["result"]
    assert result["status"] == "PASS_ENGINEERING_INTEGRATED_OFFLINE"
    assert sum(result["decision_census"].values()) == 24
    assert result["decision_census"]["UNKNOWN"] > 0
    assert result["decision_census"]["ENTRY_SIGNAL"] > 0
    assert result["g1_source_unchanged"] is True
    assert result["replayed_events"] == result["duplicate_retries"] == 3
    assert result["assumed_fills"] == 2
    assert result["duplicate_fills"] == result["skipped_commands"] == 0
    assert result["synthetic_horizon_census"]["mature"] > 0
    assert result["synthetic_horizon_census"]["pending"] > 0
    assert result["real_4_24_72_horizons"] == "NOT_OBSERVED_BY_THIS_RUN"
    assert result["trading_authority"] == "NONE"
    assert {r["case"] for r in result["negatives"]} == {
        "receipt_tamper", "source_revision", "future_cutoff", "forged_live_scope",
        "provisional_bar", "future_bar", "unverified_clock", "foreign_source_symbol",
        "duplicate_command_conflict", "skipped_first_eligible_bar"}


def test_manifest_binds_exact_importable_source_bytes(completed):
    root = completed / "overlay"
    manifest = verify(root)
    required = {
        "src/aql/foundation/readiness.py": "g287",
        "src/aql/journal/durable_journal.py": "g287",
        "src/aql/storage/operational_store.py": "g287",
        "tools/scanner_strategy_f/research_strategy_plugin.py": "scanner277",
        "src/aql/observation/prospective.py": "g286",
        "src/aql/observation/forward_evidence.py": "g289",
        "src/aql/paper_sim/engine.py": "g288",
    }
    for name, role in required.items():
        row = manifest["files"][name]
        assert row["role"] == role and row["commit"] == PINS[role]
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == row["sha256"]
    path = root / "src/aql/paper_sim/engine.py"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b"\n# tampered\n")
        with pytest.raises(ValueError, match="SOURCE_BYTES_DRIFT"):
            verify(root)
    finally:
        path.write_bytes(original)


def test_stage_refuses_existing_destination(tmp_path):
    with pytest.raises(ValueError, match="DESTINATION_MUST_BE_NEW"):
        stage(ROOT, tmp_path)


def test_manifest_tampering_cannot_change_pin_or_source_owner(completed):
    path = completed / "overlay/source-overlay.json"
    original = path.read_bytes()
    try:
        document = json.loads(original)
        document["pins"]["g289"] = "0" * 40
        path.write_text(json.dumps(document))
        with pytest.raises(ValueError, match="MANIFEST_DRIFT"):
            verify(path.parent)
    finally:
        path.write_bytes(original)


def test_unmanifested_python_import_is_rejected(completed):
    root = completed / "overlay"
    path = root / "sitecustomize.py"
    try:
        path.write_text("raise RuntimeError('injected')\n")
        with pytest.raises(ValueError, match="UNMANIFESTED_SOURCE"):
            verify(root)
    finally:
        path.unlink()


def test_resealed_manifest_cannot_replace_parent_retained_identity(completed):
    path = completed / "overlay/source-overlay.json"
    original = path.read_bytes()
    document = json.loads(original)
    expected = document["sha256"]
    try:
        document["merge_performed"] = True
        document["sha256"] = digest({k: v for k, v in document.items() if k != "sha256"})
        path.write_text(json.dumps(document))
        with pytest.raises(ValueError, match="MANIFEST_DRIFT"):
            verify(path.parent, expected_sha=expected)
    finally:
        path.write_bytes(original)


def test_pinned_strategy_evaluator_and_forbidden_ack_pit_authority(completed):
    """Addendum: exercise actual contracts, not a claim-only scope assertion."""
    overlay = completed / "overlay"
    verify(overlay)
    code = r'''
import copy,json,pathlib,sys
from aql.paper_sim.adapter import signals_from_prospective
from aql.paper_sim.engine import PaperSimulator
from aql.observation.contracts import digest
root=pathlib.Path(sys.argv[1]);read=json.loads((root/'run/g2-read.json').read_text())
plan=json.loads((root/'run/commands.json').read_text());results=[]
def rejected(name,fn):
    try:fn()
    except ValueError as exc:results.append({'case':name,'reason':str(exc)})
    else:raise AssertionError('NEGATIVE_ACCEPTED:'+name)
for field,value in [('evaluator_sha256','f'*64),('strategy_version','unreviewed-version')]:
    changed=copy.deepcopy(read);changed['run'][field]=value
    changed['sha256']=digest({k:v for k,v in changed.items() if k!='sha256'})
    rejected(field+'_mismatch',lambda d=changed:signals_from_prospective(
        d,expected_sha=d['sha256'],expected_run=read['run'],as_of_ms=d['as_of_ms']))
for name,field,value in [('forbidden_ACK','source_ack_sha256','f'*64),
                         ('fake_PIT','historical_pit','ATTESTED'),
                         ('forbidden_trading_authority','trading_authority','LIVE')]:
    watch=copy.deepcopy(plan['commands'][0][1]);watch['signal'][field]=value
    path=root/(name+'.jsonl');sim=PaperSimulator(path)
    rejected(name,lambda w=watch,s=sim:s.apply(s.identity(w),'watch',w))
    assert not path.exists() and sim.states=={}
(root/'supplemental-rejections.json').write_text(json.dumps(results,sort_keys=True,indent=2)+'\n')
print(json.dumps(results,sort_keys=True))
'''
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join((str(overlay / "src"), str(overlay)))
    result = subprocess.run([sys.executable, "-B", "-c", code, str(completed)],
                            env=env, cwd=overlay, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert len(rows) == 5
    assert {r["reason"] for r in rows} == {
        "PAPER_SIM_PINNED_SYNTHETIC_RUN", "PAPER_SIM_SIGNAL_FIELDS", "PAPER_SIM_OFFLINE_ONLY"}
