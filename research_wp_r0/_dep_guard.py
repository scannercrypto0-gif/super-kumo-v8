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
Checks every import alias. Relative imports are resolved against the source
package and must remain inside a verified first-party package. Dotted
first-party modules must exist on disk; nothing is imported or executed.
This is a static dependency policy, not a sandbox for dynamic Python code.

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

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _internal_module(name: str) -> bool:
    parts = name.split('.')
    if parts[0] not in PROJECT_INTERNAL:
        return False
    path = REPO_ROOT.joinpath(*parts)
    return path.with_suffix('.py').is_file() or (path / '__init__.py').is_file()


def _allowed(name: str) -> bool:
    root = name.split('.')[0]
    return root in STDLIB or _internal_module(name)


def check_source(src: str, *, package: str = 'research_wp_r0') -> List[str]:
    """Check import dependencies without importing inspected modules.

    Synthetic snippets default to the indicator package; check_file derives the
    real context from its path. Relative imports cannot escape that package.
    Imported attributes are not a runtime symbol/type check.
    """
    bad: List[str] = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            bad.extend(alias.name for alias in node.names if not _allowed(alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level:
                parts = package.split('.') if package else []
                if node.level > len(parts):
                    bad.append('.' * node.level + module)
                    continue
                module = '.'.join(parts[:len(parts) - node.level + 1] +
                                  ([module] if module else []))
            if not _allowed(module):
                bad.append(module)
            elif module in PROJECT_INTERNAL:
                # "from . import X" must resolve an actual local module.
                bad.extend(module + '.' + alias.name for alias in node.names
                           if not _internal_module(module + '.' + alias.name))
    return bad


def check_file(path: "str | pathlib.Path") -> List[str]:
    path = pathlib.Path(path).resolve()
    try:
        relative = path.relative_to(REPO_ROOT)
        parts = relative.with_suffix('').parts
        package = '.'.join(parts[:-1])
    except ValueError:
        package = ''
    return check_source(path.read_text(encoding='utf-8'), package=package)


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
