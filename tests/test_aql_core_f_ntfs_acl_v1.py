"""Offline ACL policy cases; no source bytes or network."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_wp_r0.aql_core_f_ntfs_acl_v1 import (
    validate_acl_entries, require_private_windows_directory,
)
from research_wp_r0.aql_core_f_bulk_source_v1 import (
    acquire_private_batch, build_manifest,
)

U = "S-1-5-21-111-222-333-1001"
SYSTEM = "S-1-5-18"
ADMINS = "S-1-5-32-544"


class TestWindowsAclPolicy(unittest.TestCase):
    def test_explicit_owner_and_trusted_system_only(self):
        self.assertTrue(validate_acl_entries([
            (U, 0, 0, 0x1F01FF), (SYSTEM, 0, 0, 0x1F01FF),
            (ADMINS, 0, 0, 0x1F01FF),
        ], U))

    def test_inherited_current_owner_and_trusted_system_are_checked(self):
        self.assertTrue(validate_acl_entries([
            (U, 0, 0x10, 0x1F01FF),
            (SYSTEM, 0, 0x10, 0x1F01FF),
        ], U))

    def test_unsafe_broad_principals_inherited_or_explicit_rejected(self):
        for sid in ("S-1-1-0", "S-1-5-11", "S-1-5-32-545",
                    "S-1-5-7", "S-1-5-21-999-888-777-1001"):
            for flags in (0, 0x10):
                with self.subTest(sid=sid, flags=flags), self.assertRaisesRegex(
                        ValueError, "WINDOWS_ACL_UNSAFE_PRINCIPAL"):
                    validate_acl_entries([(U, 0, 0, 0x1F01FF),
                                          (sid, 0, flags, 0x120089)], U)

    def test_denials_and_unknown_types_or_flags_rejected(self):
        for entry in [(U, 1, 0, 0x1F01FF), (U, 5, 0, 0x1F01FF),
                      (U, 0, 0x40, 0x1F01FF)]:
            with self.subTest(entry=entry), self.assertRaisesRegex(
                    ValueError, "WINDOWS_ACL_UNRECOGNIZED"):
                validate_acl_entries([entry], U)

    def test_inherit_only_aces_are_recognized_but_not_counted_as_own_access(self):
        # Actual icacls (OI)(CI)(IO)(F) ACEs are valid Windows inheritance
        # metadata; they grant no access to the containing directory.
        self.assertTrue(validate_acl_entries([
            (U, 0, 0x03, 0x1F01FF),
            (SYSTEM, 0, 0x0B, 0x1F01FF),
            (ADMINS, 0, 0x0B, 0x1F01FF),
            (ADMINS, 0, 0x00, 0x1F01FF),
        ], U))
        with self.assertRaisesRegex(ValueError, "WINDOWS_ACL_USER_ACCESS_REQUIRED"):
            validate_acl_entries([(U, 0, 0x0B, 0x1F01FF)], U)

    def test_no_usable_owner_and_invalid_ace(self):
        for entries, sid, message in [
            ([(SYSTEM, 0, 0, 0x1F01FF)], U, "WINDOWS_ACL_USER_ACCESS_REQUIRED"),
            ([], U, "WINDOWS_ACL_IDENTITY_OR_DACL_REQUIRED"),
            ([(U, 0, 0, 0x1F01FF)], "", "WINDOWS_ACL_IDENTITY_OR_DACL_REQUIRED"),
            ([("bad",)], U, "WINDOWS_ACL_UNRECOGNIZED"),
        ]:
            with self.subTest(entries=entries), self.assertRaisesRegex(ValueError, message):
                validate_acl_entries(entries, sid)

    def test_windows_gate_cannot_be_called_on_posix(self):
        if os.name == "nt":
            self.skipTest("native Windows gate is tested on Windows runner")
        with self.assertRaisesRegex(ValueError, "WINDOWS_ACL_ONLY_ON_WINDOWS"):
            require_private_windows_directory("/not/existing")

    def test_posix_guard_preserved(self):
        if os.name == "nt":
            self.skipTest("POSIX mode semantics are not Windows ACL semantics")
        manifest = build_manifest(first="2024-03", last="2024-03")
        with tempfile.TemporaryDirectory() as d:
            Path(d).chmod(0o755)
            with self.assertRaisesRegex(ValueError, "PRIVATE_DIRECTORY_PERMISSIONS_REQUIRED"):
                with patch("research_wp_r0.aql_core_f_bulk_source_v1._fetch",
                           side_effect=AssertionError("network must not run")):
                    acquire_private_batch(
                        manifest, d, allow_network=True, permission_confirmed=True,
                        terms_reviewed=True, publisher_origin_confirmed=True)

    @unittest.skipUnless(os.name == "nt", "native effective NTFS test requires Windows")
    def test_real_ntfs_private_directory_and_inherited_broad_rejection(self):
        import csv
        import subprocess
        identity = subprocess.check_output(
            ["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip()
        current_sid = next(csv.reader([identity]))[-1]
        self.assertTrue(current_sid.startswith("S-1-"))
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            # Use icacls on this disposable test directory only. Set-Acl can
            # require SeSecurityPrivilege on ordinary Windows PowerShell hosts.
            # Remove inherited grants and install only trusted explicit SIDs.
            # No owner's historical files or parent ACLs are modified.
            setup_commands = [
                ["icacls", str(base), "/inheritance:r"],
                ["icacls", str(base), "/grant:r",
                 f"*{current_sid}:(OI)(CI)F",
                 f"*{SYSTEM}:(OI)(CI)F",
                 f"*{ADMINS}:(OI)(CI)F"],
            ]
            for command in setup_commands:
                setup = subprocess.run(command, capture_output=True,
                                       text=True, errors="replace")
                if setup.returncode:
                    self.fail(
                        "Windows test-local ACL setup failed "
                        f"(exit={setup.returncode}); "
                        f"stdout={setup.stdout[-3000:]!r}; "
                        f"stderr={setup.stderr[-3000:]!r}")
            self.assertTrue(require_private_windows_directory(base))
            # Add a real inherited broad read ACE: a nested folder must fail.
            subprocess.run(
                ["icacls", str(base), "/grant", "*S-1-1-0:(OI)(CI)R"],
                check=True, capture_output=True)
            child = base / "inherited"
            child.mkdir()
            with self.assertRaisesRegex(ValueError, "WINDOWS_ACL_UNSAFE_PRINCIPAL"):
                require_private_windows_directory(child)


if __name__ == "__main__":
    unittest.main()
