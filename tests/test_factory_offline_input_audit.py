import unittest
from research_wp_r0.historical_evaluation_bridge import OfflineInputs
from research_wp_r0.offline_input_audit import audit_offline_inputs
from research_wp_r0.strategy_definition import digest


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


class TestInputAudit(unittest.TestCase):
    def test_deterministic_and_not_evaluated(self):
        data = OfflineInputs(fixture())
        with self.assertRaises(ValueError):
            audit_offline_inputs(data, expected_digest=data.digest)  # placeholder hashes rejected

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
