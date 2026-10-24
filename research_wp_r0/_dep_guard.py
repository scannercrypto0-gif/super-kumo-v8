"""
SF-IND-01 dependency guard — static AST check for third-party imports.
=======================================================================
Replaces the inline ``python -c`` snippet that was in sf-ind-01-fast.yml.
Extracting it here makes the guard code testable and version-controlled
alongside the library it guards.

Usage (CLI):
    python research_wp_r0/_dep_guard.py [<file> ...]

Exits 0 if no unauthorised imports found; non-zero otherwise.

Guard rules
-----------
* ``import a``                 → checks root of 'a'
* ``import a, b``              → checks root of 'a' AND root of 'b'
                                 (the old guard only checked 'a' — this is the
                                 bug that allowed ``import os, numpy`` through)
* ``import a.b``               → checks root 'a'
* ``from a import b``          → checks root 'a'
* ``from a.b import c``        → checks root 'a'
* ``from . import b``          → relative → allowed (internal to package)
* ``from .a import b``         → relative → allowed (internal to package)
* ``from ..a import b``        → relative → allowed (internal to package)

All names in ``STDLIB`` and ``PROJECT_INTERNAL`` are allowed; everything
else is rejected.

Issue: #59 (SF-IND-01 CI fix)
"""
from __future__ import annotations

import ast
import pathlib
import sys
from typing import List

# ---------------------------------------------------------------------------
# Allow-lists
# ---------------------------------------------------------------------------

# Standard-library root names that are permitted in research library code.
# Extend here if a new stdlib module is genuinely needed and justified.
STDLIB: frozenset = frozenset({
    '__future__', 'abc', 'collections', 'dataclasses', 'datetime',
    'enum', 'functools', 'hashlib', 'itertools', 'json', 'math',
    'operator', 'os', 'pathlib', 're', 'struct', 'time', 'typing',
    'uuid', 'warnings',
})

# Project-internal packages (same repo, not third-party).
# These may appear as ``import research_wp_r0`` or ``from research_wp_r0…``.
PROJECT_INTERNAL: frozenset = frozenset({'research_wp_r0'})


# ---------------------------------------------------------------------------
# Core check functions
# ---------------------------------------------------------------------------

def check_source(src: str) -> List[str]:
    """
    Parse *src* as Python source and return a list of unauthorised import
    root names.  An empty return list means the source is clean.

    Parameters
    ----------
    src : str
        Raw Python source code to analyse.

    Returns
    -------
    list[str]
        Unauthorised import names (the full dotted name, not just the root),
        in encounter order.  May contain duplicates if the same name appears
        in multiple import statements.
    """
    tree = ast.parse(src)
    bad: List[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # --- FIX: iterate ALL aliases, not just names[0] ---
            # Old code: ``node.names[0].name`` missed everything after the
            # first name in ``import os, numpy`` (only 'os' was checked).
            for alias in node.names:
                root = alias.name.split('.')[0]
                if root and root not in STDLIB and root not in PROJECT_INTERNAL:
                    bad.append(alias.name)

        elif isinstance(node, ast.ImportFrom):
            # Relative imports (level > 0) are always internal to the package.
            # ``from . import foo``, ``from .bar import baz``,
            # ``from ..util import x`` — all fine.
            if node.level and node.level > 0:
                continue
            module = node.module or ''
            root = module.split('.')[0]
            if root and root not in STDLIB and root not in PROJECT_INTERNAL:
                bad.append(module)

    return bad


def check_file(path: "str | pathlib.Path") -> List[str]:
    """
    Read *path* and return unauthorised import root names (empty = clean).

    Parameters
    ----------
    path : str or pathlib.Path
        File to check (must be valid Python source).
    """
    src = pathlib.Path(path).read_text(encoding='utf-8')
    return check_source(src)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

def _main(args: List[str]) -> int:
    """
    Check one or more files.  Defaults to ``research_wp_r0/indicator_library.py``
    when no arguments are given (backward-compatible with the old inline script).
    """
    paths = args if args else ['research_wp_r0/indicator_library.py']
    any_bad = False
    for p in paths:
        bad = check_file(p)
        if bad:
            print(f'External deps found in {p}: {bad}', file=sys.stderr)
            any_bad = True
    if any_bad:
        return 1
    print('No external (third-party) dependencies — OK')
    return 0


if __name__ == '__main__':
    sys.exit(_main(sys.argv[1:]))
