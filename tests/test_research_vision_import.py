"""Offline pinned Vision ingestion tests; generated records only."""
import hashlib
import tempfile
import unittest
from pathlib import Path

from aql.research_bar_store import ResearchBarStore
from aql.research_vision_import import import_pinned_vision_csv


def line(i):
    opened = i * 60000
    return ",".join(map(str, [opened, "10", "12", "9", "11", "2", opened + 59999,
                              "20", "3", "1", "10", "0"]))


class VisionImportTest(unittest.TestCase):
    def test_pinned_import_replay_and_negative(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "native.csv"
            path.write_text(line(0) + "\n" + line(1) + "\n", encoding="utf-8")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with ResearchBarStore(Path(tmp) / "bars.sqlite") as store:
                args = dict(symbol="BTCUSDT", expected_sha256=digest, available_at_ms=180000)
                result = import_pinned_vision_csv(store, path, **args)
                self.assertEqual(result["rows"], 2)
                self.assertEqual(result["source_authenticity"], "NOT_INDEPENDENTLY_ATTESTED")
                self.assertEqual(import_pinned_vision_csv(store, path, **args)["rows"], 2)
                self.assertIsNotNone(store.read("BTCUSDT", "1m", 60000))
                with self.assertRaisesRegex(ValueError, "SOURCE_PIN_MISMATCH"):
                    import_pinned_vision_csv(store, path, symbol="BTCUSDT",
                                             expected_sha256="0"*64, available_at_ms=180000)
                path.write_text(line(0) + "\n" + line(2) + "\n", encoding="utf-8")
                new_digest = hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaisesRegex(ValueError, "VISION_GAP_DUPLICATE"):
                    import_pinned_vision_csv(store, path, symbol="BTCUSDT",
                                             expected_sha256=new_digest, available_at_ms=180000)
                self.assertIsNone(store.read("BTCUSDT", "1m", 120000))


if __name__ == "__main__":
    unittest.main()
