"""Single owner-authorized Bundle B cross-PR SOFTWARE-contract gate.

SYNTHETIC in-memory bytes only. This is not a new authentic-source E2E,
operational Work #235 15m, G0, or any trading/Paper activation.
The actual classes below are the pinned Core #226, Factory #255 and Scanner #257
contract tests. Running all in one process exposes cross-branch interface and
dependency drift without rewriting their code or rerunning accepted Feb/Aug.
"""
from __future__ import annotations

import unittest

from test_aql_core_dual_query_identity_map_v1 import DualQueryIdentity
from test_aql_factory_core_query_bridge_v1 import BundleBBridgeTests
from test_aql_factory_same_source_lab_paper_v1 import SameSourceLabPaperTests
from tools.scanner_strategy_b.test_integration import (
    Native15mGate, CoreSecretaryGate,
)
from tools.scanner_strategy_b.test_portfolio import PortfolioGate


def load_tests(loader, standard_tests, pattern):
    suite = unittest.TestSuite()
    for case in (DualQueryIdentity, BundleBBridgeTests,
                 SameSourceLabPaperTests, Native15mGate, CoreSecretaryGate,
                 PortfolioGate):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == "__main__":
    unittest.main()
