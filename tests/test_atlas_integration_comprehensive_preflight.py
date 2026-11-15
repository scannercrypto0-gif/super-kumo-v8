"""Fail-closed comprehensive preflight: aggregate independent issues, no private leakage."""
import unittest
from tools.atlas_integration_comprehensive_preflight import collect, ORDER

class ComprehensivePreflightTests(unittest.TestCase):
    def test_collect_all_independent_failures_and_block_dependents(self):
        checks = {name:(lambda: True) for name in ORDER[:-1]}
        checks["PIN_MANIFEST"] = lambda: False
        checks["SCANNER_MONTH_SCOPE"] = lambda: False
        result = collect(checks)
        rows = {x["check_id"]:x["status"] for x in result["checks"]}
        self.assertEqual(rows["PIN_MANIFEST"],"FAIL")
        self.assertEqual(rows["SCANNER_COHORT_SIGNATURE"],"BLOCKED_DEPENDENCY")
        self.assertEqual(rows["SCANNER_MONTH_SCOPE"],"BLOCKED_DEPENDENCY")
        self.assertEqual(rows["ORIGINAL_PRIVATE_SOURCE"],"BLOCKED_EXTERNAL_INPUT")
        self.assertEqual(result["trading_authority"],"NONE")

    def test_independent_failures_both_reported(self):
        checks = {name:(lambda: True) for name in ORDER[:-1]}
        checks["SCANNER_MONTH_SCOPE"] = lambda: False
        checks["FACTORY_REAL_KERNEL_CONTRACT"] = lambda: False
        rows = {x["check_id"]:x["status"] for x in collect(checks)["checks"]}
        self.assertEqual(rows["SCANNER_MONTH_SCOPE"],"FAIL")
        self.assertEqual(rows["FACTORY_REAL_KERNEL_CONTRACT"],"FAIL")
        self.assertEqual(rows["OWNER_PRIVACY_SANITIZER"],"PASS")

    def test_private_exception_text_is_never_emitted(self):
        def fail():
            raise ValueError("E:/ATLAS/private/secret-original-OHLCV")
        checks = {name:(lambda: True) for name in ORDER[:-1]}
        checks["PIN_MANIFEST"] = fail
        result = collect(checks)
        self.assertNotIn("secret-original",repr(result))
        self.assertEqual(result["checks"][0]["status"],"FAIL")

    def test_actual_cross_owner_static_contracts(self):
        report=collect()
        self.assertEqual(report["checks"][-1]["status"],"BLOCKED_EXTERNAL_INPUT")
        self.assertEqual(report["counts"]["FAIL"],0,report["checks"])

if __name__=="__main__":
    unittest.main()
