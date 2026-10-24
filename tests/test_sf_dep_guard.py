"""
SF-IND-01 dependency-guard regression tests.
=============================================
Verifies that the AST import guard in ``research_wp_r0/_dep_guard.py``
correctly allows or rejects imports.

These tests exercise the **same code path** used by sf-ind-01-fast.yml
(the guard is imported directly, not mocked), so a CI failure on the
workflow and a test failure here always point to the same bug.

Test plan
---------
A  Allow-list — imports that MUST pass (stdlib, project-internal, relative)
R  Reject-list — imports that MUST be detected as unauthorised
G  Golden — the actual indicator_library.py must be clean
BUG  Specific regression cases that the old guard would have missed

Issue: #59 (SF-IND-01 CI fix)
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research_wp_r0._dep_guard import check_file, check_source


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ok(src: str) -> bool:
    """Return True if source has no unauthorised imports."""
    return check_source(src) == []


def _bad(src: str) -> bool:
    """Return True if source has at least one unauthorised import."""
    return len(check_source(src)) > 0


# ===========================================================================
# A — Allow-list (must pass)
# ===========================================================================

class TestAllowed(unittest.TestCase):
    """All of these imports must be allowed by the guard."""

    # --- stdlib ---
    def test_os(self):
        self.assertTrue(_ok('import os'))

    def test_json(self):
        self.assertTrue(_ok('import json'))

    def test_hashlib(self):
        self.assertTrue(_ok('import hashlib'))

    def test_dataclasses(self):
        self.assertTrue(_ok('import dataclasses'))

    def test_typing(self):
        self.assertTrue(_ok('import typing'))

    def test_math(self):
        self.assertTrue(_ok('import math'))

    def test_from_future(self):
        self.assertTrue(_ok('from __future__ import annotations'))

    def test_from_os(self):
        self.assertTrue(_ok('from os import path'))

    def test_from_os_path(self):
        self.assertTrue(_ok('from os.path import join'))

    def test_multi_stdlib_only(self):
        # All names in list are stdlib — must pass
        self.assertTrue(_ok('import os, json'))

    def test_stdlib_dotted(self):
        self.assertTrue(_ok('import os.path'))

    # --- project-internal ---
    def test_project_internal(self):
        self.assertTrue(_ok('import research_wp_r0'))

    def test_project_internal_dotted(self):
        self.assertTrue(_ok('import research_wp_r0.foo'))

    def test_from_project_internal(self):
        self.assertTrue(_ok('from research_wp_r0 import bar'))

    def test_from_project_internal_dotted(self):
        self.assertTrue(_ok('from research_wp_r0.historical_library import CustodyAccessor'))

    # --- relative imports (all internal by definition) ---
    def test_relative_single_dot(self):
        self.assertTrue(_ok('from . import something'))

    def test_relative_single_dot_module(self):
        self.assertTrue(_ok('from .foo import bar'))

    def test_relative_double_dot(self):
        self.assertTrue(_ok('from .. import baz'))

    def test_relative_double_dot_module(self):
        self.assertTrue(_ok('from ..util import helper'))


# ===========================================================================
# R — Reject-list (must be detected)
# ===========================================================================

class TestRejected(unittest.TestCase):
    """All of these imports must be flagged as unauthorised."""

    def test_numpy(self):
        self.assertTrue(_bad('import numpy'))

    def test_pandas(self):
        self.assertTrue(_bad('import pandas'))

    def test_scipy(self):
        self.assertTrue(_bad('import scipy'))

    def test_matplotlib(self):
        self.assertTrue(_bad('import matplotlib'))

    def test_from_pandas(self):
        self.assertTrue(_bad('from pandas import DataFrame'))

    def test_from_pandas_dotted(self):
        self.assertTrue(_bad('from pandas.core import DataFrame'))

    def test_from_matplotlib(self):
        self.assertTrue(_bad('from matplotlib.pyplot import show'))

    def test_unknown_package(self):
        self.assertTrue(_bad('import totally_unknown_package_xyz'))

    def test_from_unknown(self):
        self.assertTrue(_bad('from totally_unknown_xyz import something'))

    def test_dotted_third_party(self):
        # 'import numpy.linalg' — root is 'numpy', must be caught
        self.assertTrue(_bad('import numpy.linalg'))

    def test_requests(self):
        self.assertTrue(_bad('import requests'))

    def test_from_requests(self):
        self.assertTrue(_bad('from requests import Session'))


# ===========================================================================
# BUG — Regression cases for the old guard's specific defects
# ===========================================================================

class TestBugRegressions(unittest.TestCase):
    """
    These are the exact cases that the old guard (names[0] only) would
    have missed.  They must now all be caught.
    """

    def test_multi_import_bad_is_second(self):
        # BUG: old guard checked only names[0], which was 'os' — numpy missed.
        # ``import os, numpy`` must be flagged.
        bad = check_source('import os, numpy')
        self.assertIn('numpy', bad,
                      msg='numpy must be detected in "import os, numpy"')

    def test_multi_import_bad_is_first(self):
        # Symmetric case: numpy first — must still be caught.
        bad = check_source('import numpy, os')
        self.assertIn('numpy', bad,
                      msg='numpy must be detected in "import numpy, os"')

    def test_multi_import_both_bad(self):
        # Both names are unauthorised.
        bad = check_source('import numpy, pandas')
        self.assertGreaterEqual(len(bad), 2,
                                msg='Both numpy and pandas must be detected')
        roots = {b.split('.')[0] for b in bad}
        self.assertIn('numpy', roots)
        self.assertIn('pandas', roots)

    def test_multi_import_three_names(self):
        # Three names: os (ok), numpy (bad), json (ok).
        bad = check_source('import os, numpy, json')
        self.assertIn('numpy', bad,
                      msg='numpy must be detected in "import os, numpy, json"')
        self.assertNotIn('os', bad)
        self.assertNotIn('json', bad)

    def test_importfrom_relative_not_flagged(self):
        # Relative imports were sometimes handled ambiguously; must NOT flag.
        bad = check_source('from .historical_library import CustodyAccessor')
        self.assertEqual(bad, [],
                         msg='Relative imports must not be flagged')


# ===========================================================================
# G — Golden: actual production files must pass
# ===========================================================================

class TestGoldenFiles(unittest.TestCase):
    """
    The real indicator_library.py must pass the guard that governs it.

    Note: ``_dep_guard.py`` is CI tooling that uses stdlib modules (``ast``,
    ``sys``, ``pathlib``, ``typing``) beyond the narrow allow-list appropriate
    for research library code.  It is intentionally excluded from the self-check
    — the guard's allow-list describes *research library* constraints, not the
    constraint on the guard tool itself.
    """

    _ROOT = pathlib.Path(__file__).parent.parent

    def test_indicator_library_clean(self):
        lib_path = self._ROOT / 'research_wp_r0' / 'indicator_library.py'
        bad = check_file(lib_path)
        self.assertEqual(bad, [],
                         msg=f'Unexpected deps in indicator_library.py: {bad}')


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == '__main__':
    unittest.main(verbosity=2)
