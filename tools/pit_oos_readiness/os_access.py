"""Linux native access rehearsal. Run only as root in a disposable CI runner."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import grp
import shutil
import subprocess
import sys
import tempfile

ROLES = {"operator": 62001, "researcher": 62002, "custodian": 62003}
READERS_GID = 62004
SEALED = b"generated sealed fixture sentinel; no cohort data\n"
METADATA = json.dumps({"state": "SEALED_UNOPENED", "sha256": sha256(SEALED).hexdigest()},
                      sort_keys=True).encode()


def provision(root):
    root.chmod(0o711)
    for role, uid in ROLES.items():
        directory = root / role
        directory.mkdir(mode=0o700)
        os.chown(directory, uid, uid)
    metadata = root / "metadata"
    metadata.mkdir(mode=0o750)
    os.chown(metadata, 0, READERS_GID)
    public = metadata / "commitment.json"
    public.write_bytes(METADATA)
    os.chown(public, 0, READERS_GID)
    public.chmod(0o440)
    vault = root / "vault"
    vault.mkdir(mode=0o750)
    os.chown(vault, 0, ROLES["custodian"])
    sealed = vault / "sealed"
    sealed.write_bytes(SEALED)
    os.chown(sealed, 0, ROLES["custodian"])
    sealed.chmod(0o440)
    (root / "researcher" / "linked-fixture").symlink_to(sealed)


CHILD = """
import errno, hashlib, json, os, pathlib, sys
root, action, target, own = sys.argv[1:]
path = pathlib.Path(root) / target
scratch = pathlib.Path(root) / own / 'scratch'
token = {
    k: v.strip() for k, v in (
        line.split(':', 1) for line in pathlib.Path('/proc/self/status').read_text().splitlines()
        if ':' in line)
    if k in {'CapEff', 'CapBnd', 'NoNewPrivs'}
}
result = dict(uid=os.geteuid(), gid=os.getegid(), groups=os.getgroups(), token=token)
try:
    if action == 'read':
        result['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif action == 'list':
        result['entries'] = sorted(os.listdir(path))
    elif action == 'write':
        with path.open('ab') as handle:
            handle.write(b'generated test')
    elif action == 'replace':
        scratch.write_bytes(b'generated replacement')
        scratch.replace(path)
    elif action == 'hardlink':
        os.link(path, scratch.with_name('hardlink'))
    elif action == 'chmod':
        path.chmod(0o777)
    else:
        raise ValueError(action)
    result['access'] = 'ALLOW'
except OSError as exc:
    result['errno'] = errno.errorcode.get(exc.errno, str(exc.errno))
    result['access'] = 'DENY'
print(json.dumps(result, sort_keys=True))
"""


def probe(executable, root, role, action, target, expected):
    uid = ROLES[role]
    cmd = [executable, f"--reuid={uid}", f"--regid={uid}",
           f"--groups={READERS_GID}", "--bounding-set=-all", "--inh-caps=-all",
           "--ambient-caps=-all", "--no-new-privs", sys.executable, "-I", "-c",
           CHILD, str(root), action, target, role]
    result = json.loads(subprocess.check_output(cmd, cwd="/", text=True, timeout=15))
    if (result["uid"] != uid or result["gid"] != uid or result["groups"] != [READERS_GID]
            or result["token"] != {"CapEff": "0000000000000000", "CapBnd": "0000000000000000",
                                   "NoNewPrivs": "1"}):
        raise RuntimeError(f"Unexpected effective identity: {result}")
    if result["access"] != expected or (expected == "DENY" and result["errno"] not in {"EACCES", "EPERM"}):
        raise RuntimeError(f"Unexpected access for {role}/{action}/{target}: {result}")
    if action == "read" and expected == "ALLOW":
        content = SEALED if target.endswith("/sealed") else METADATA
        if result["sha256"] != sha256(content).hexdigest():
            raise RuntimeError(f"Unexpected readback for {target}")
    return dict(result, role=role, action=action, target=target, expected=expected)


def run():
    if sys.platform != "linux" or os.geteuid() != 0:
        raise SystemExit("Requires an authorized disposable Linux runner with root provisioning")
    executable = shutil.which("setpriv")
    if not executable:
        raise SystemExit("setpriv is required")
    ids = {*ROLES.values(), READERS_GID}
    if ids & {entry.pw_uid for entry in pwd.getpwall()} or ids & {entry.gr_gid for entry in grp.getgrall()}:
        raise SystemExit("Reserved test identities collide with a runner account or group")
    with tempfile.TemporaryDirectory(prefix="aql-acl-") as folder:
        root = Path(folder)
        provision(root)
        cases = []
        for role in ROLES:
            cases.extend([(role, "read", "metadata/commitment.json", "ALLOW"),
                          (role, "write", f"{role}/notes", "ALLOW"),
                          (role, "list", role, "ALLOW"),
                          (role, "write", "metadata/commitment.json", "DENY"),
                          (role, "replace", "metadata/commitment.json", "DENY")])
            for other in ROLES.keys() - {role}:
                cases.extend([(role, "list", other, "DENY"),
                              (role, "write", f"{other}/notes", "DENY")])
        for role in ("operator", "researcher"):
            cases.append((role, "list", "vault", "DENY"))
            cases.extend((role, action, "vault/sealed", "DENY")
                         for action in ("read", "write", "replace", "hardlink", "chmod"))
        cases.extend([("researcher", "read", "researcher/linked-fixture", "DENY"),
                      ("custodian", "read", "vault/sealed", "ALLOW"),
                      ("custodian", "list", "vault", "ALLOW"),
                      ("custodian", "write", "vault/sealed", "DENY"),
                      ("custodian", "replace", "vault/sealed", "DENY"),
                      ("custodian", "chmod", "vault/sealed", "DENY")])
        checks = [probe(executable, root, *case) for case in sorted(cases)]
        if (root / "vault" / "sealed").read_bytes() != SEALED:
            raise RuntimeError("Sealed fixture changed")
    return dict(platform="linux", scope="DISPOSABLE_GENERATED_FIXTURE",
                checks=checks, fixture_sha256=sha256(SEALED).hexdigest(),
                original_holdout_prices_opened=0, real_pit_oos="BLOCKED")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    result = run()
    raw = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode()
    with args.report.open("xb") as report:
        report.write(raw)
    args.report.chmod(0o644)
    print(f"{len(result['checks'])} native checks passed; report SHA-256 {sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
