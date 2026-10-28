"""Offline launch/preflight tests: successful preflight always preserves HOLD."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import pytest
from aql.evidence_outbox import encode, digest
from aql.guardian_launch import LaunchError, SCHEMA, file_hash, preflight
from aql.guardian_receipt import VAULT_ID


@pytest.fixture
def contract(tmp_path, monkeypatch):
    for key in list(os.environ):
        if key.upper().startswith('RCLONE_'): monkeypatch.delenv(key)
    root = Path(__file__).resolve().parents[1]
    cfg = tmp_path/'rclone.conf'
    cfg.write_text('[atlas_vault]\ntype=alias\nremote=atlas:ATLAS-EVIDENCE-VAULT\n'
                   '[atlas]\ntype=drive\ntoken=SECRET_NOT_PRINTED\n', encoding='utf-8')
    exe = tmp_path/'rclone.exe'; exe.write_bytes(b'never executed')
    outbox = tmp_path/'outbox'; outbox.mkdir()
    paths = ('src/aql/guardian_launch.py', 'src/aql/guardian_receipt.py',
             'src/aql/evidence_guardian.py', 'src/aql/evidence_outbox.py',
             'src/aql/archive/local.py', 'scripts/evidence_guardian.py')
    pin = lambda p: dict(path=str(p), sha256=file_hash(p))
    doc = dict(schema=SCHEMA, remote='atlas_vault:', vault_id=VAULT_ID,
               alias_target='atlas:ATLAS-EVIDENCE-VAULT', working_directory=str(Path.cwd()),
               outbox=str(outbox), log_path=str(tmp_path/'guardian.log'),
               service_identity='SYNTHETIC_USER', rclone_config=pin(cfg),
               rclone_executable=pin(exe), python_executable=pin(Path(sys.executable).resolve()),
               python_version=platform.python_version(),
               code_files={p:file_hash(root/p) for p in paths},
               operator_declaration_ref='PENDING', audit_approval_ref='NOT_GRANTED',
               continuous_enablement='HOLD')
    return tmp_path/'contract.json', doc


def write(contract):
    path, doc = contract; blob = encode(doc); path.write_bytes(blob)
    return path, digest(blob)


def test_preflight_is_read_only_never_an_authorization(contract, monkeypatch):
    path, sha = write(contract)
    before = {p:p.read_bytes() for p in path.parent.rglob('*') if p.is_file()}
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: pytest.fail('no command permitted'))
    result = preflight(path, sha, identity='SYNTHETIC_USER')
    assert result['status'] == 'LOCAL_PREFLIGHT_VERIFIED_NOT_AUTHORIZED'
    assert result['continuous_enablement'] == 'HOLD'
    assert result['effective_remote_identity'] == 'OPERATOR_EVIDENCE_REQUIRED'
    assert {p:p.read_bytes() for p in path.parent.rglob('*') if p.is_file()} == before
    assert 'SECRET' not in json.dumps(result)


@pytest.mark.parametrize('field,value,code', [
    ('remote', 'atlas:', 'TARGET_MISMATCH'),
    ('vault_id', 'child-not-root', 'TARGET_MISMATCH'),
    ('alias_target', 'atlas:another', 'TARGET_MISMATCH'),
    ('continuous_enablement', 'ENABLED', 'CONTINUOUS_ENABLEMENT_HOLD'),
    ('service_identity', 'other', 'SERVICE_IDENTITY_MISMATCH'),
    ('working_directory', str(Path.home()), 'WORKING_DIRECTORY_MISMATCH'),
    ('code_files', {}, 'CODE_PIN_SET_MISMATCH'),
    ('python_version', '0.0', 'PYTHON_RUNTIME_MISMATCH'),
    ('operator_declaration_ref', '', 'REVIEW_REFERENCE_REQUIRED'),
])
def test_contract_wrong_target_or_control_rejected(contract, field, value, code):
    contract[1][field] = value
    path, sha = write(contract)
    with pytest.raises(LaunchError, match=code): preflight(path, sha, identity='SYNTHETIC_USER')


@pytest.mark.parametrize('item', ['rclone_config', 'rclone_executable', 'python_executable'])
def test_config_and_executable_drift_rejected(contract, item):
    path, sha = write(contract)
    # Change pin in the contract, not a real installed executable.
    contract[1][item]['sha256'] = '0'*64
    path, sha = write(contract)
    with pytest.raises(LaunchError, match='DRIFT'): preflight(path, sha, identity='SYNTHETIC_USER')


def test_expected_contract_digest_must_be_external(contract):
    path, sha = write(contract)
    with pytest.raises(LaunchError, match='CONTRACT_DRIFT'):
        preflight(path, '0'*64, identity='SYNTHETIC_USER')


def test_reviewed_code_pin_mismatch_fails_without_source_edit(contract):
    contract[1]['code_files']['src/aql/evidence_outbox.py'] = '0'*64
    path, sha = write(contract)
    with pytest.raises(LaunchError, match='CODE_DRIFT'):
        preflight(path, sha, identity='SYNTHETIC_USER')


def test_alias_config_and_environment_cannot_override_pin(contract, monkeypatch):
    doc = contract[1]; config = Path(doc['rclone_config']['path'])
    config.write_text('[atlas_vault]\ntype=alias\nremote=atlas:WRONG\n[atlas]\ntype=drive\n')
    doc['rclone_config']['sha256'] = file_hash(config)
    path, sha = write(contract)
    with pytest.raises(LaunchError, match='ALIAS_CONFIG_MISMATCH'):
        preflight(path, sha, identity='SYNTHETIC_USER')
    config.write_text('[atlas_vault]\ntype=alias\nremote=atlas:ATLAS-EVIDENCE-VAULT\n[atlas]\ntype=drive\n')
    doc['rclone_config']['sha256'] = file_hash(config); path, sha = write(contract)
    monkeypatch.setenv('RCLONE_CONFIG_ATLAS_VAULT_REMOTE', 'SECRET')
    with pytest.raises(LaunchError, match='RCLONE_ENVIRONMENT_OVERRIDE'):
        preflight(path, sha, identity='SYNTHETIC_USER')


def test_malformed_config_does_not_leak_parser_content(contract):
    doc = contract[1]; config = Path(doc['rclone_config']['path'])
    config.write_text('token=SECRET_NOT_PRINTED')
    doc['rclone_config']['sha256'] = file_hash(config); path, sha = write(contract)
    with pytest.raises(LaunchError) as exc: preflight(path, sha, identity='SYNTHETIC_USER')
    assert str(exc.value) == 'PREFLIGHT_INVALID_OR_INACCESSIBLE'


@pytest.mark.parametrize('args', [[], ['--once'], ['--outbox', 'MUST_NOT_CREATE', '--remote', 'atlas_vault:']])
def test_actual_cli_has_no_continuous_or_once_launch_path(tmp_path, args):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=str(root/'src'))
    result = subprocess.run([sys.executable, str(root/'scripts/evidence_guardian.py'), *args],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert json.loads(result.stdout)['status'] == 'CONTINUOUS_ENABLEMENT_HOLD'
    assert list(tmp_path.iterdir()) == []
