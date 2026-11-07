"""Exact assembled #211 RawVault Windows release gate, fixtures only.

The source package is pinned to the independently fetched Windows-fix branch.
Do not run these tests against any owner historical, RAW vault or warehouse root.
"""
from __future__ import annotations
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from research_wp_r0.aql_core_f_ntfs_acl_v1 import require_private_windows_directory
from tools.raw_vault_offline.vault import RawVault, _vault_lock
from tools.raw_vault_offline.tests._helpers import make_meta

EXPECTED_GIT_BLOB = "6b5bcc1d684088934f5ed7110064380b8d2bc0cd"
EXPECTED_MODULE_PATH = "tools/raw_vault_offline/vault.py"


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


class CoreF5WindowsRawVaultRelease(unittest.TestCase):
    def test_exact_source_blob_import_path_and_immutable_f2_root(self):
        module = Path(sys.modules[RawVault.__module__].__file__).resolve()
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(module, root / EXPECTED_MODULE_PATH)
        self.assertEqual(git_blob_sha(module.read_bytes()), EXPECTED_GIT_BLOB)
        self.assertEqual(RawVault.__module__, "tools.raw_vault_offline.vault")

    def test_disposable_fsync_restart_idempotent_and_recovery(self):
        with tempfile.TemporaryDirectory(prefix="aql-f5-fixture-") as d:
            vault_root = Path(d) / "raw"
            vault = RawVault(vault_root)
            raw = b"F5 DISPOSABLE SYNTHETIC RAW FIXTURE ONLY"
            meta = make_meta(raw)
            with mock.patch(
                "tools.raw_vault_offline.vault.os.fsync",
                wraps=os.fsync
            ) as fsync:
                first = vault.admit(raw, meta)
                self.assertGreaterEqual(fsync.call_count, 2)
            self.assertEqual(vault.read(meta.content_sha256), raw)
            self.assertEqual(len(vault.manifest_entries()), 1)
            self.assertEqual(vault.recovery_scan()["status"], "CLEAN")
            restarted = RawVault(vault_root)
            self.assertEqual(restarted.admit(raw, meta), first)
            self.assertEqual(restarted.read(meta.content_sha256), raw)
            self.assertEqual(len(restarted.manifest_entries()), 1)

    @unittest.skipUnless(sys.platform == "win32", "Windows process lock and NTFS required")
    def test_disposable_real_cross_process_lock_timeout_and_crash_release(self):
        import csv
        identity = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip()
        sid = next(csv.reader([identity]))[-1]
        self.assertTrue(sid.startswith("S-1-"))
        with tempfile.TemporaryDirectory(prefix="aql-f5-win-") as d:
            base = Path(d) / "private"
            base.mkdir()
            # Harden only a disposable test path. Do not touch its parent.
            script = (
                "$ErrorActionPreference='Stop'; "
                "$dir=New-Object System.IO.DirectoryInfo($env:AQL_TEST_DIR); "
                "$acl=$dir.GetAccessControl(); "
                "$acl.SetAccessRuleProtection($true,$false); "
                "foreach($rule in @($acl.GetAccessRules($true,$true,"
                "[System.Security.Principal.SecurityIdentifier]))) { "
                "[void]$acl.RemoveAccessRuleSpecific($rule) }; "
                "foreach($s in @($env:AQL_TEST_SID,'S-1-5-18','S-1-5-32-544')) { "
                "$identity=New-Object System.Security.Principal.SecurityIdentifier($s); "
                "$rule=New-Object System.Security.AccessControl.FileSystemAccessRule("
                "$identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); "
                "$acl.AddAccessRule($rule) }; $dir.SetAccessControl($acl)"
            )
            result = subprocess.run(
                [str(Path(os.environ["SystemRoot"]) / "System32" /
                     "WindowsPowerShell" / "v1.0" / "powershell.exe"),
                 "-NoProfile", "-NonInteractive", "-Command", script],
                env={**os.environ,"AQL_TEST_DIR":str(base),"AQL_TEST_SID":sid},
                capture_output=True,text=True,errors="replace")
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            self.assertTrue(require_private_windows_directory(base))
            # Another process holds byte zero; parent must fail closed on timeout.
            # Compound statement needs real newline, not a semicolon before with.
            childcode = (
                "from pathlib import Path\n"
                "from tools.raw_vault_offline.vault import _vault_lock\n"
                "import sys,time\n"
                "with _vault_lock(Path(sys.argv[1])):\n"
                "    print('LOCKED',flush=True)\n"
                "    time.sleep(60)\n"
            )
            env = {**os.environ, "PYTHONPATH":str(Path(__file__).resolve().parents[1])}
            p = subprocess.Popen([sys.executable,"-u","-c",childcode,str(base)],
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 env=env,text=True)
            try:
                import queue, threading
                q=queue.Queue(maxsize=1)
                thread=threading.Thread(target=lambda:q.put(p.stdout.readline()),daemon=True)
                thread.start()
                self.assertEqual(q.get(timeout=15).strip(), "LOCKED")
                with self.assertRaises(TimeoutError):
                    with _vault_lock(base, timeout=0.3):
                        pass
                # Deliberately simulate OS-level crash, kernel must release lock.
                p.kill()
                p.wait(timeout=10)
                with _vault_lock(base, timeout=3):
                    pass
                v=RawVault(base)
                raw=b"ONLY-DISPOSABLE-AQL-F5-RAW"
                m=make_meta(raw)
                v.admit(raw,m)
                self.assertEqual(RawVault(base).read(m.content_sha256),raw)
                self.assertEqual(len(RawVault(base).manifest_entries()),1)
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=10)
                p.stdout.close()
                p.stderr.close()


if __name__=="__main__":
    unittest.main()
