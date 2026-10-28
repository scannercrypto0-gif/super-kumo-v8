"""Read-only local launch-contract preflight. No operational enablement path.

An externally retained expected contract hash is mandatory; a hash inside the
same editable document is not approval. Even a passing preflight returns HOLD.
No rclone invocation, network access, task/service installation or ACL changes.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from aql.archive.local import check_path
from aql.guardian_receipt import REMOTE, VAULT_ID

SCHEMA = 'aql-guardian-launch-review-v1'


class LaunchError(ValueError):
    pass


def file_hash(path):
    h = hashlib.sha256()
    with check_path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _absolute(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise LaunchError('ABSOLUTE_PATH_REQUIRED')
    return check_path(value)


def _identity():
    if os.name == 'nt':
        # Fixed OS command only; do not inspect credentials/config output.
        exe = Path(os.environ['SystemRoot']) / 'System32' / 'whoami.exe'
        return subprocess.run([str(exe)], check=True, capture_output=True,
                              text=True, timeout=5).stdout.strip()
    import getpass
    return getpass.getuser()


def preflight(contract_path, expected_sha256, *, identity=None):
    """Verify fixed local config/executable/code pins without touching outbox.

    Remote alias resolution is NOT proven: an independently reviewed read-only
    effective-target inventory remains a separate operator evidence gate.
    """
    try:
        if file_hash(contract_path) != expected_sha256:
            raise LaunchError('CONTRACT_DRIFT')
        doc = json.loads(check_path(contract_path).read_bytes())
        required = {'schema', 'remote', 'vault_id', 'alias_target', 'working_directory',
                    'outbox', 'log_path', 'service_identity', 'rclone_config',
                    'rclone_executable', 'python_executable', 'python_version',
                    'code_files', 'operator_declaration_ref', 'audit_approval_ref',
                    'continuous_enablement'}
        if not isinstance(doc, dict) or set(doc) != required or doc['schema'] != SCHEMA:
            raise LaunchError('INVALID_CONTRACT')
        if (doc['remote'] != REMOTE or doc['vault_id'] != VAULT_ID
                or doc['alias_target'] != 'atlas:ATLAS-EVIDENCE-VAULT'):
            raise LaunchError('TARGET_MISMATCH')
        if doc['continuous_enablement'] != 'HOLD':
            raise LaunchError('CONTINUOUS_ENABLEMENT_HOLD')
        if str(_absolute(doc['working_directory'])) != str(Path.cwd()):
            raise LaunchError('WORKING_DIRECTORY_MISMATCH')
        if doc['service_identity'].casefold() != (identity or _identity()).casefold():
            raise LaunchError('SERVICE_IDENTITY_MISMATCH')
        outbox, log = _absolute(doc['outbox']), _absolute(doc['log_path'])
        if not outbox.is_dir() or not log.parent.is_dir() or log == outbox or outbox in log.parents:
            raise LaunchError('INVALID_OUTBOX_OR_LOG_PATH')
        for item in ('rclone_config', 'rclone_executable', 'python_executable'):
            pin = doc[item]
            if not isinstance(pin, dict) or set(pin) != {'path', 'sha256'}:
                raise LaunchError('INVALID_FILE_PIN')
            if file_hash(_absolute(pin['path'])) != pin['sha256']:
                raise LaunchError('LOCAL_CONFIG_OR_EXECUTABLE_DRIFT')
        if (_absolute(doc['python_executable']['path']) != Path(sys.executable).resolve()
                or doc['python_version'] != platform.python_version()):
            raise LaunchError('PYTHON_RUNTIME_MISMATCH')
        # Bind the actual source dependency set, not caller-selected arbitrary files.
        root = Path(__file__).resolve().parents[2]
        expected_code = ('src/aql/guardian_launch.py', 'src/aql/guardian_receipt.py',
                         'src/aql/evidence_guardian.py', 'src/aql/evidence_outbox.py',
                         'src/aql/archive/local.py', 'scripts/evidence_guardian.py')
        if set(doc['code_files']) != set(expected_code):
            raise LaunchError('CODE_PIN_SET_MISMATCH')
        for relative, sha in doc['code_files'].items():
            if file_hash(root / relative) != sha:
                raise LaunchError('CODE_DRIFT')
        cfg = configparser.ConfigParser(interpolation=None, strict=True)
        cfg.read_string(check_path(doc['rclone_config']['path']).read_text(encoding='utf-8'))
        if (cfg['atlas_vault']['type'] != 'alias'
                or cfg['atlas_vault']['remote'] != doc['alias_target']
                or cfg['atlas']['type'] != 'drive'
                or cfg['atlas'].get('root_folder_id', '') not in ('', VAULT_ID)):
            raise LaunchError('ALIAS_CONFIG_MISMATCH')
        # Environment overrides can supersede reviewed config. Fail closed even
        # for innocuous rclone variables; never print names or values.
        if any(k.upper().startswith('RCLONE_') for k in os.environ):
            raise LaunchError('RCLONE_ENVIRONMENT_OVERRIDE')
        for field in ('operator_declaration_ref', 'audit_approval_ref'):
            if not isinstance(doc[field], str) or not doc[field]:
                raise LaunchError('REVIEW_REFERENCE_REQUIRED')
        return dict(status='LOCAL_PREFLIGHT_VERIFIED_NOT_AUTHORIZED',
                    contract_sha256=expected_sha256, continuous_enablement='HOLD',
                    effective_remote_identity='OPERATOR_EVIDENCE_REQUIRED',
                    executable_version='SHA256_PINNED_NOT_EXECUTED',
                    windows_acl='OPERATOR_EVIDENCE_REQUIRED')
    except LaunchError:
        raise
    except Exception:
        # JSON, config, subprocess and OS exceptions may embed secrets or paths.
        raise LaunchError('PREFLIGHT_INVALID_OR_INACCESSIBLE') from None
