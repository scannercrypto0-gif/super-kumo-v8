"""Core F private Windows NTFS directory gate (no bypass switches).

Only the exact current process user SID, LocalSystem and builtin Administrators
may have ALLOW ACEs. Inherited ACEs are evaluated, not blindly ignored.
Check *actual* effective GENERIC_READ|GENERIC_WRITE on the directory using
the process token; never infer access from an asserted owner string or flags.
This deliberately errs on denial for unknown ACE types or principals.
"""
from __future__ import annotations

import os
from pathlib import Path

SAFE_SYSTEM_SIDS = frozenset(("S-1-5-18", "S-1-5-32-544"))
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_ATTRIBUTE_REPARSE_POINT = 0x400
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000


def validate_acl_entries(entries, current_user_sid):
    """Side-effect-free ACL policy used by real NTFS inspection and tests.

    entries: tuples (sid, ace_type, ace_flags, access_mask).
    Inherited ACEs undergo exactly the same checks as explicit entries.
    """
    if (not isinstance(current_user_sid, str)
            or not current_user_sid.startswith("S-1-")
            or not isinstance(entries, (list, tuple)) or not entries):
        raise ValueError("WINDOWS_ACL_IDENTITY_OR_DACL_REQUIRED")
    allowed_sids = SAFE_SYSTEM_SIDS | {current_user_sid}
    own_grant = False
    for entry in entries:
        if (not isinstance(entry, tuple) or len(entry) != 4
                or not isinstance(entry[0], str)
                or type(entry[1]) is not int or type(entry[2]) is not int
                or type(entry[3]) is not int):
            raise ValueError("WINDOWS_ACL_UNRECOGNIZED")
        sid, ace_type, flags, mask = entry
        # Type 0 = ACCESS_ALLOWED_ACE. Any denies, object ACE, callback ACE
        # or unrecognized DACL semantics must be audited, not guessed.
        if ace_type != 0 or flags & ~0x1F or mask < 0 or mask > 0xFFFFFFFF:
            raise ValueError("WINDOWS_ACL_UNRECOGNIZED")
        if sid not in allowed_sids:
            raise ValueError("WINDOWS_ACL_UNSAFE_PRINCIPAL")
        # INHERIT_ONLY_ACE (0x08) doesn't apply to this directory.
        if sid == current_user_sid and not (flags & 0x08) and mask:
            own_grant = True
    if not own_grant:
        raise ValueError("WINDOWS_ACL_USER_ACCESS_REQUIRED")
    return True


def require_private_windows_directory(root):
    if os.name != "nt":
        raise ValueError("WINDOWS_ACL_ONLY_ON_WINDOWS")
    # ctypes.WinDLL is deliberately imported only on native Windows.
    import ctypes
    from ctypes import wintypes

    root = Path(root).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError("PRIVATE_DIRECTORY_REQUIRED")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    cptr = ctypes.c_void_p
    P = ctypes.POINTER
    DWORD = wintypes.DWORD
    kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetFileAttributesW.restype = DWORD
    for part in (root, *root.parents):
        if not part.exists():
            continue
        attr = kernel32.GetFileAttributesW(str(part))
        if attr == 0xFFFFFFFF or attr & FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("WINDOWS_REPARSE_OR_UNREADABLE_PATH")

    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, DWORD, P(wintypes.HANDLE)]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, cptr, DWORD, P(DWORD)]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.ConvertSidToStringSidW.argtypes = [cptr, P(cptr)]
    advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [cptr]
    kernel32.LocalFree.restype = cptr
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    def sid_string(ptr):
        raw = cptr()
        if not ptr or not advapi32.ConvertSidToStringSidW(ptr, ctypes.byref(raw)):
            raise ValueError("WINDOWS_ACL_SID_CONVERSION_FAILED")
        try:
            return ctypes.wstring_at(raw.value)
        finally:
            kernel32.LocalFree(raw)

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
        raise ValueError("WINDOWS_TOKEN_QUERY_DENIED")
    try:
        size = DWORD()
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
        if not 8 <= size.value <= 65536:
            raise ValueError("WINDOWS_TOKEN_USER_INVALID")
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
            raise ValueError("WINDOWS_TOKEN_USER_INVALID")
        user_ptr = ctypes.cast(buffer, P(cptr)).contents.value
        current_sid = sid_string(cptr(user_ptr))
    finally:
        kernel32.CloseHandle(token)

    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR, ctypes.c_int, DWORD, P(cptr), P(cptr),
        P(cptr), P(cptr), P(cptr),
    ]
    advapi32.GetNamedSecurityInfoW.restype = DWORD
    advapi32.GetAce.argtypes = [cptr, DWORD, P(cptr)]
    advapi32.GetAce.restype = wintypes.BOOL

    class ACL(ctypes.Structure):
        _fields_ = [("revision", ctypes.c_ubyte), ("sbz1", ctypes.c_ubyte),
                    ("size", ctypes.c_ushort), ("count", ctypes.c_ushort),
                    ("sbz2", ctypes.c_ushort)]

    class ACE_HEAD(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ubyte), ("flags", ctypes.c_ubyte),
                    ("size", ctypes.c_ushort)]

    dacl = cptr()
    descriptor = cptr()
    rc = advapi32.GetNamedSecurityInfoW(str(root), 1, 4, None, None,
                                        ctypes.byref(dacl), None,
                                        ctypes.byref(descriptor))
    if rc != 0 or not descriptor:
        raise ValueError("WINDOWS_ACL_INSPECTION_FAILED")
    try:
        if not dacl:
            raise ValueError("WINDOWS_NULL_DACL_DENIED")
        acl = ctypes.cast(dacl, P(ACL)).contents
        if not 0 < acl.count <= 1024 or acl.size < ctypes.sizeof(ACL):
            raise ValueError("WINDOWS_ACL_UNRECOGNIZED")
        entries = []
        for idx in range(acl.count):
            raw_ace = cptr()
            if not advapi32.GetAce(dacl, idx, ctypes.byref(raw_ace)) or not raw_ace:
                raise ValueError("WINDOWS_ACL_UNRECOGNIZED")
            header = ctypes.cast(raw_ace, P(ACE_HEAD)).contents
            if header.size < 12 or header.type != 0:
                raise ValueError("WINDOWS_ACL_UNRECOGNIZED")
            addr = raw_ace.value
            mask = ctypes.c_uint32.from_address(addr + 4).value
            principal = sid_string(cptr(addr + 8))
            entries.append((principal, header.type, header.flags, mask))
        validate_acl_entries(entries, current_sid)
    finally:
        kernel32.LocalFree(descriptor)

    # OS access decision for the *real* current process token, separate from
    # inspection of the DACL. A caller-written boolean is never sufficient.
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR, DWORD, DWORD, cptr, DWORD, DWORD, wintypes.HANDLE
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.CreateFileW(str(root), GENERIC_READ | GENERIC_WRITE,
                                  0x00000007, None, 3,
                                  FILE_FLAG_BACKUP_SEMANTICS, None)
    if handle in (None, -1, ctypes.c_void_p(-1).value):
        raise ValueError("WINDOWS_EFFECTIVE_DIRECTORY_ACCESS_DENIED")
    kernel32.CloseHandle(handle)
    return True
