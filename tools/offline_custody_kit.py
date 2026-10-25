"""Offline custody kit: dry-run first, no authority/custody or evaluation claim."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import getpass
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import stat
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from research_wp_r0.custody_manifest_builder import build_custody_manifest
from research_wp_r0.custody_anchor_verifier import verify_custody_bundle

MAX_FILES = 4096
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MANIFEST = 'custody-manifest.json'


def checked(path):
    if os.fspath(path).startswith(('\\\\', '//')):
        raise ValueError('Network/UNC custody paths unsupported by offline kit')
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Symlink/reparse path rejected')
    return path


def identity(path):
    s = path.stat()
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns


def safe_name(name):
    for part in name.split('/'):
        stem = part.split('.')[0].upper()
        if (not part or part in ('.', '..') or part.endswith((' ', '.')) or
                any(c in part for c in '\\:<>"|?*') or any(ord(c) < 32 for c in part) or
                stem in ('CON', 'PRN', 'AUX', 'NUL') or re.fullmatch(r'(COM|LPT)[1-9]', stem)):
            raise ValueError('Unsafe cross-platform evidence path')


def inventory(root):
    root = checked(root)
    if not root.is_dir():
        raise ValueError('Existing finalized bundle directory required')
    files = {}; folded = set(); total = 0; nodes = 0
    pending = [(root, 0)]
    while pending:
        folder, depth = pending.pop()
        if depth > 16:
            raise ValueError('Evidence depth bound exceeded')
        for path in folder.iterdir():
            nodes += 1
            if nodes > MAX_FILES * 2:
                raise ValueError('Directory entry bound exceeded')
            checked(path)
            name = path.relative_to(root).as_posix(); safe_name(name)
            if name.casefold() in folded:
                raise ValueError('Case-insensitive path collision')
            folded.add(name.casefold())
            s = path.lstat()
            if stat.S_ISDIR(s.st_mode):
                pending.append((path, depth+1))
            elif stat.S_ISREG(s.st_mode):
                total += s.st_size
                if s.st_size > MAX_FILE or total > MAX_TOTAL or len(files) >= MAX_FILES:
                    raise ValueError('Evidence size/file bound exceeded')
                files[name] = identity(path)
            else:
                raise ValueError('Only regular files/directories supported')
    if not files:
        raise ValueError('Empty evidence bundle')
    return files, total


def disjoint(a, b):
    return a != b and a not in b.parents and b not in a.parents


def check_anchor(source, anchor):
    anchor = checked(anchor)
    if not disjoint(source, anchor) or not anchor.is_file() or anchor.stat().st_size > 128:
        raise ValueError('Small separately retained anchor outside source required')
    return anchor


def copy_file(source, target):
    before = identity(source); count = 0
    with source.open('rb') as inp, target.open('xb') as out:
        while chunk := inp.read(1024*1024):
            count += len(chunk)
            if count > MAX_FILE:
                raise ValueError('Source grew beyond file limit')
            out.write(chunk)
        out.flush(); os.fsync(out.fileno())
    if identity(source) != before or count != before[2]:
        raise ValueError('Source changed during copy; partial target retained')


def receipt_replay(root, relative, plan_digest, checkpoint):
    """Read-only replay of existing Factory receipts, NEVER a strategy evaluator."""
    from research_wp_r0.attempt_ledger import AttemptLedger
    from research_wp_r0.frozen_research_plan import verify_research_plan
    safe_name(relative)
    path = checked(root / relative)
    if root not in path.parents or not path.is_file():
        raise ValueError('Ledger must be inside verified restored bundle')
    if any(Path(str(path)+suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('Replay requires a finalized standalone SQLite snapshot, no live sidecars')
    # No constructor: it can write pragmas/schema. Reuse only the merged reader.
    probe = object.__new__(AttemptLedger); probe.expected_checkpoint = checkpoint
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)) as db:
        events, actual = probe._read(db)
        sealed = db.execute('SELECT plan_digest,plan_bytes FROM frozen_plan_policy WHERE id=1').fetchone()
        policy = db.execute('SELECT require_admission FROM ledger_policy WHERE id=1').fetchone()
        if not sealed or sealed[0] != plan_digest or not policy or policy[0] != 1:
            raise ValueError('Expected frozen plan/protected policy absent')
        plan = verify_research_plan(bytes(sealed[1]), plan_digest)
        AttemptLedger._frozen_membership(plan, events)
    states = {}
    for event in events:
        states[event['state']] = states.get(event['state'], 0)+1
    return {'status': 'LOCAL_RECEIPTS_REPLAYED', 'events': len(events), 'states': states,
            'checkpoint': list(actual), 'evaluation_status': 'NOT_EVALUATED'}


def run(action, source, *, anchor=None, target=None, execute=False, quiescent=False,
        ledger=None, plan_digest=None, checkpoint=None):
    source = checked(source)
    before, size = inventory(source)
    report = {'schema': 'atlas-offline-custody-report-1', 'action': action,
              'status': 'DRY_RUN_PLAN_ONLY',
              'mode': 'EXECUTE' if execute else 'DRY_RUN', 'source': str(source),
              'source_files': len(before), 'source_bytes': size,
              'independent_custody_verified': False, 'anchor_protection': 'NOT_ATTESTED',
              'research_data_pit': 'NOT_ATTESTED', 'research_evaluation_replay': 'NOT_PERFORMED_NO_EVALUATOR',
              'git_repository_recovery': 'NOT_TESTED_FILE_HASHES_ARE_NOT_GIT_FSCK',
              'source_quiescence': 'OWNER_ASSERTED' if quiescent else 'NOT_ATTESTED',
              'receipt_replay': {'status': 'NOT_REQUESTED'}}
    if execute and not quiescent:
        raise ValueError('Execution requires explicit quiescent-source confirmation')
    if action == 'manifest':
        if MANIFEST in before:
            raise FileExistsError('Manifest exists; never overwrite')
        if execute:
            report.update(build_custody_manifest(source))
            report['status'] = 'MANIFEST_CREATED_NOT_CUSTODY_ACCEPTANCE'
        else:
            report['would_create'] = str(source/MANIFEST)
        return report
    if action != 'restore' or anchor is None or target is None:
        raise ValueError('Restore requires explicit source, external anchor and new target')
    anchor = check_anchor(source, anchor); anchor_before = anchor.read_bytes()
    anchor_id = identity(anchor)
    target = checked(target)
    if target.exists() or not target.parent.is_dir() or not disjoint(source, target) or not disjoint(anchor, target):
        raise ValueError('New target with existing parent, separate from source/anchor required')
    if MANIFEST not in before:
        raise ValueError('Finalized manifest missing')
    report.update(verify_custody_bundle(source, anchor))
    report.update(anchor=str(anchor), target=str(target), anchor_external_to_bundle=True)
    if inventory(source)[0] != before:
        raise ValueError('Source drift during verification')
    if ledger is not None:
        if (not re.fullmatch('[0-9a-f]{64}', plan_digest or '') or type(checkpoint) is not tuple or
                len(checkpoint) != 2 or type(checkpoint[0]) is not int or checkpoint[0] < 0 or
                not re.fullmatch('[0-9a-f]{64}', checkpoint[1] or '')):
            raise ValueError('Receipt replay requires separately supplied plan digest and checkpoint')
        report['source_receipt_preflight'] = receipt_replay(source, ledger, plan_digest, checkpoint)
    if not execute:
        report['would_copy_files'] = len(before)
        return report
    target.mkdir()  # Partial target retained on failure; never delete/overwrite.
    for name in sorted(before):
        destination = target/name; destination.parent.mkdir(parents=True, exist_ok=True)
        copy_file(checked(source/name), destination)
    if anchor.read_bytes() != anchor_before or identity(anchor) != anchor_id:
        raise ValueError('Anchor changed during restore; do not accept partial target')
    if inventory(source)[0] != before:
        raise ValueError('Source changed during restore; target not accepted')
    report['restored_content'] = verify_custody_bundle(target, anchor)
    if ledger is not None:
        report['receipt_replay'] = receipt_replay(target, ledger, plan_digest, checkpoint)
        verify_custody_bundle(target, anchor)  # Read-only replay must not alter bundle bytes.
    report['status'] = 'LOCAL_RESTORE_VERIFIED_NOT_CUSTODY_ACCEPTANCE'
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('manifest', 'restore'))
    p.add_argument('--source', required=True); p.add_argument('--anchor'); p.add_argument('--target')
    p.add_argument('--execute', action='store_true'); p.add_argument('--quiescent', action='store_true')
    p.add_argument('--report'); p.add_argument('--ledger'); p.add_argument('--plan-digest')
    p.add_argument('--data-class', choices=('SYNTHETIC_TEST','OWNER_SUPPLIED_UNVERIFIED'), default='OWNER_SUPPLIED_UNVERIFIED')
    p.add_argument('--checkpoint-sequence', type=int); p.add_argument('--checkpoint-hash')
    a = p.parse_args(argv)
    try:
        report_path = checked(a.report) if a.report else None
        if report_path:
            if report_path.exists() or not report_path.parent.is_dir():
                raise ValueError('New report file/existing parent required')
            for path in (a.source, a.target, a.anchor):
                if path and not disjoint(report_path, checked(path)):
                    raise ValueError('Report must be outside source/restore/anchor')
        checkpoint = None
        if a.checkpoint_sequence is not None or a.checkpoint_hash is not None:
            if a.checkpoint_sequence is None or a.checkpoint_sequence < 0 or not re.fullmatch('[0-9a-f]{64}', a.checkpoint_hash or ''):
                raise ValueError('Explicit valid checkpoint pair required')
            checkpoint = (a.checkpoint_sequence, a.checkpoint_hash)
        report = run(a.action, a.source, anchor=a.anchor, target=a.target,
                     execute=a.execute, quiescent=a.quiescent, ledger=a.ledger,
                     plan_digest=a.plan_digest, checkpoint=checkpoint)
        report.update(observed_at_utc=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
                      os=platform.platform(), tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      execution_identity=getpass.getuser(), custodian_identity='NOT_ATTESTED',
                      anchor_acl_evidence='NOT_COLLECTED', retention_policy='NOT_ATTESTED',
                      data_class=a.data_class, report_signoff='NOT_ATTESTED_UNSIGNED_OBSERVATION')
        for key, command in (('git_version', ['git','--version']), ('tool_git_sha', ['git','-C',str(REPO),'rev-parse','HEAD'])):
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            report[key] = result.stdout.strip() if result.returncode == 0 else 'UNKNOWN'
        raw = json.dumps(report, sort_keys=True, indent=2)+'\n'
        if report_path and a.execute:
            with report_path.open('x', encoding='utf-8') as handle:
                handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        print(raw)
        return 0
    except (ValueError, OSError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(json.dumps({'status':'FAILED_NO_ACCEPTANCE', 'error':str(error),
                          'independent_custody_verified':False, 'partial_target':'PRESERVE_IF_CREATED'}), file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
