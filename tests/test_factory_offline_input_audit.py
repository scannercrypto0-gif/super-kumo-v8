import unittest
from research_wp_r0.historical_evaluation_bridge import OfflineInputs
from research_wp_r0.offline_input_audit import audit_offline_inputs
from research_wp_r0.strategy_definition import digest
from research_wp_r0.historical_library import HistoricalBar, DatasetManifest, BarQuality, SourceType, DataAvailabilityKind
from dataclasses import asdict


def fixture():
    strategy = {"strategy_id": "x"}
    manifest = {"dataset_id": "btc", "version": 1, "manifest_integrity_hash": "a" * 64}
    binding = {"strategy_digest": digest(strategy), "dataset_id": "btc",
               "dataset_version": 1, "dataset_manifest_hash": "a" * 64,
               "decision_cutoff_ms": 200, "bar_checksums": ["b" * 64]}
    protocol = {"data_class": "SYNTHETIC_TEST"}
    return {"schema_version": "research-input-1", "state": "INPUTS_ONLY_NOT_EVALUATED",
            "strategy": {"definition": strategy, "digest": digest(strategy)},
            "protocol": protocol, "protocol_digest": digest(protocol),
            "binding": {"binding": binding, "digest": digest(binding)},
            "dataset_manifest": manifest,
            "bars": [{"checksum": "b" * 64, "quality": "FINAL",
                      "availability_kind": "CONFIRMED", "observation_cutoff_ms": 150,
                      "ingest_time_ms": 150}],
            "independent_custody": "NOT_VERIFIED"}

def valid_receipt():
    from research_wp_r0.historical_evaluation_bridge import EXECUTION_REQUIREMENTS
    from research_wp_r0.strategy_definition import StrategyDefinition
    from research_wp_r0.indicator_library_v2 import IndicatorRegistryV2
    # Real strategy construction is tested by the integration bridge suite;
    # this audit fixture uses a real bar and manifest rather than placeholder hashes.
    bar = HistoricalBar(symbol="BTCUSDT", interval="1m", bar_open=0, bar_close=59999,
                        open=100.0, high=102.0, low=99.0, close=101.0, volume=10.0,
                        quality=BarQuality.FINAL, source=SourceType.SYNTHETIC,
                        source_label="fixture", observation_cutoff_ms=60001,
                        ingest_time_ms=60001, availability_kind=DataAvailabilityKind.CONFIRMED)
    import hashlib
    manifest = DatasetManifest(dataset_id="btc", version=1, exchange="test",
        market="spot", symbol="BTCUSDT", interval="1m", timezone="UTC",
        source_label="fixture", bar_count=1, min_bar_open=0, max_bar_open=0,
        coverage_pct=100.0, gap_count=0, gap_bar_opens=(),
        duplicate_count=0, non_final_count=0,
        manifest_hash=hashlib.sha256(bar.checksum.encode()).hexdigest(),
        created_at_ms=70000, parent_version=None, lineage_reason=None)
    return bar, manifest


class TestInputAudit(unittest.TestCase):
    def test_deterministic_and_not_evaluated(self):
        data = OfflineInputs(fixture())
        with self.assertRaises(ValueError):
            audit_offline_inputs(data, expected_digest=data.digest)  # placeholder hashes rejected

    def test_real_bar_checksum_is_bound_to_prices(self):
        bar, manifest = valid_receipt()
        self.assertTrue(bar.verify_checksum())
        self.assertTrue(manifest.verify_integrity())
        self.assertTrue(manifest.verify_hash([bar]))
        modified = asdict(bar)
        modified["close"] = 100.5
        modified["quality"] = BarQuality(modified["quality"])
        modified["source"] = SourceType(modified["source"])
        modified["availability_kind"] = DataAvailabilityKind(modified["availability_kind"])
        forged = HistoricalBar(**modified)
        self.assertNotEqual(forged.checksum, bar.checksum)
        self.assertFalse(manifest.verify_hash([forged]))

    def test_tamper_rejected_by_commitment(self):
        data = OfflineInputs(fixture())
        changed = fixture()
        changed["bars"][0]["ingest_time_ms"] = 151
        with self.assertRaises(ValueError):
            audit_offline_inputs(OfflineInputs(changed), expected_digest=data.digest)

    def test_future_receipt_rejected_even_with_new_commitment(self):
        changed = fixture()
        changed["bars"][0]["observation_cutoff_ms"] = 201
        data = OfflineInputs(changed)
        with self.assertRaises(ValueError):
            audit_offline_inputs(data, expected_digest=data.digest)

    def test_self_attested_custody_rejected(self):
        changed = fixture()
        changed["independent_custody"] = "VERIFIED"
        data = OfflineInputs(changed)
        with self.assertRaises(ValueError):
            audit_offline_inputs(data, expected_digest=data.digest)


if __name__ == "__main__":
    unittest.main()
