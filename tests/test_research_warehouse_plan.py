import tempfile
import unittest
from pathlib import Path
from aql.research_warehouse_plan import plan_warehouse


class WarehousePlanTests(unittest.TestCase):
    def test_capacity_preflight_does_not_create_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ATLAS" / "DataWarehouse"
            result = plan_warehouse(root, cap_bytes=1000000, reserve_bytes=0)
            self.assertEqual(result["status"], "CAPACITY_PREFLIGHT_PASS")
            self.assertEqual(result["new_data_budget_bytes"], 1000000)
            self.assertEqual(result["host_mutations"], 0)
            self.assertFalse(root.exists())

    def test_invalid_cap_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "WAREHOUSE_CAP_INVALID"):
                plan_warehouse(tmp, cap_bytes=0)

    def test_symlink_parent_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp) / "real"
            parent.mkdir()
            link = Path(tmp) / "link"
            try:
                link.symlink_to(parent, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlink privileges unavailable")
            with self.assertRaisesRegex(ValueError, "WAREHOUSE_SYMLINK_DENIED"):
                plan_warehouse(link / "warehouse")


if __name__ == "__main__":
    unittest.main()
