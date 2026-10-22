"""R18: keep CI routing fast without losing always-on research coverage."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAST = ROOT / ".github/workflows/research-unified-fast.yml"
HEAVY = ROOT / ".github/workflows/research-targeted-performance.yml"


class WorkflowRoutingTests(unittest.TestCase):
    def test_fast_gate_always_runs_full_research_suite(self):
        source = FAST.read_text(encoding="utf-8")
        self.assertIn("python -B -m unittest discover -s tests -p 'test_research_wp_r*.py'", source)
        self.assertIn("matrix:", source)
        self.assertIn("ubuntu-latest, windows-latest", source)
        self.assertIn("cancel-in-progress: true", source)

    def test_deep_smoke_only_when_explicitly_requested(self):
        source = FAST.read_text(encoding="utf-8")
        condition = "if: ${{ github.event_name == 'workflow_dispatch' && inputs.deep_smoke == true }}"
        self.assertEqual(source.count(condition), 3)
        self.assertIn("default: false", source)

    def test_heavy_benchmarks_have_targeted_change_filter(self):
        source = HEAVY.read_text(encoding="utf-8")
        self.assertIn('      - "research_wp_r0/durable_journal.py"', source)
        self.assertIn('      - "research_wp_r0/journal_benchmark.py"', source)
        self.assertIn('      - "research_wp_r0/group_commit_experiment.py"', source)
        self.assertNotIn('      - "tests/test_research_wp_r*.py"', source)
        self.assertIn("research_wp_r0.group_commit_experiment", source)
        self.assertIn("--sizes 16,32,64 --repeats 3", source)
        self.assertIn("ubuntu-latest", source)
        self.assertIn("windows-latest", source)
        self.assertIn("cancel-in-progress: true", source)


if __name__ == "__main__":
    unittest.main()
