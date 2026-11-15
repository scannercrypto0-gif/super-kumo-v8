"""Runnable, socket-free delayed archive and reconciliation fixture."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import socket
from unittest.mock import patch

from aql.observation.contracts import digest
from tools.atlas_bounded_research_cycle import execute, FIXTURE, STEP
from tools.atlas_delayed_reconciliation import Reconciliation
from tools.atlas_prospective_observe import dedicated_root
from tools.historical_source_qa import qa
from tools.historical_source_qa.test_qa import HistoricalQA, native

START = 1735689600000


def proof(root):
    root = dedicated_root(root, "atlas-delayed-fixture-v1")
    fixture = json.loads(FIXTURE.read_text())[0]
    source = HistoricalQA()
    source.root = root
    native_rows = [native(START + i * STEP, width=STEP, unit=1000, volume="4") for i in range(4)]
    for row in native_rows:
        row[1:5] = ["99.5", "100.5", "98.5", "99.5"]
    live = execute(root / "receipt-fixture", fixture=fixture, start=START)
    archive, checksum, manifest = source.archive(native_rows, interval="15m", start=START, unit="us")
    admitted = qa.admit(archive, checksum, manifest, digest(manifest))
    research = execute(root / "archive-fixture", fixture=fixture, admission=admitted)
    item = admitted["records"][0]
    frame = dict(market=list(qa.MARKET), interval="15m", open_ms=START,
                 end_exclusive_ms=START + STEP, is_final=True, open="99.5", high="100.5",
                 low="98.5", close="99.5", base_volume="4")
    receipt = dict(frame, source_sha256=digest(frame), ack_sha256=live["ack_sha256"][0],
                   decision_sha256=live["scanner_sha256"][0], config_sha256=live["plan"]["config_sha256"],
                   code_sha256=sha256(Path(__file__).with_name(
                       "atlas_bounded_research_cycle.py").read_bytes()).hexdigest(),
                   received_ms=START + STEP, committed_ms=START + STEP + 2,
                   decision_cutoff_ms=START + STEP + 3)
    cutoff = START + 4 * STEP + 3
    ledger = Reconciliation(root / "reconciliation.sqlite")
    original = ledger.append(item, receipt, manifest=manifest, cutoff_ms=cutoff)
    assert original["category"] == "MATCH"
    native_rows[0][2] = "101"
    second, check2, manifest2 = source.archive(native_rows, interval="15m", start=START,
                                               unit="us", version="fixture-v2")
    corrected = qa.admit(second, check2, manifest2, digest(manifest2))
    revision = ledger.append(corrected["records"][0], receipt, manifest=manifest2, cutoff_ms=cutoff)
    assert revision["category"] == "CORRECTED_ARCHIVE_VERSION"
    assert revision["comparison"] == "DIFFERENCE" and revision["previous"] == original["sha256"]
    assert original["receipt"] == revision["receipt"] == receipt
    assert Reconciliation(ledger.db).append(item, receipt, manifest=manifest, cutoff_ms=cutoff) == original
    assert revision["current_entry"] == "NO_CURRENT_ENTRY"
    def rejects(reason, action):
        try:
            action()
        except ValueError as exc:
            assert reason in str(exc), str(exc)
        else:
            raise AssertionError(reason)
    denied = dict(manifest, rights_status="DENIED")
    rejects("FIXTURE_RIGHTS", lambda: qa.admit(archive, checksum, denied, digest(denied)))
    wrong_unit = dict(manifest, timestamp_unit="ms")
    rejects("TIMESTAMP_UNIT", lambda: qa.admit(archive, checksum, wrong_unit, digest(wrong_unit)))
    rejects("BYTE_PIN", lambda: qa.admit(archive, check2, manifest, digest(manifest)))
    rejects("RECEIPT_CUTOFF", lambda: ledger.append(item, receipt, manifest=manifest, cutoff_ms=START))
    rejects("RECEIPT_PARENT", lambda: ledger.append(item, dict(receipt, is_final=False),
                                                    manifest=manifest, cutoff_ms=cutoff))
    rejects("ORIGINAL_RECEIPT_CHANGED", lambda: ledger.append(item, dict(receipt, decision_sha256="0"*64),
                                                             manifest=manifest, cutoff_ms=cutoff))
    gap_manifest = dict(manifest, source_version="fixture-gap")
    gap = ledger.append(None, receipt, manifest=gap_manifest, cutoff_ms=cutoff)
    assert gap["comparison"] == "GAP"
    return {"grade": "TEST_ONLY", "mode": "RESEARCH_DELAYED", "current_entry": "NO_CURRENT_ENTRY",
            "factory_output": research["factory"], "factory_admission": research["factory_admission"],
            "strict_pit_oos": "BLOCKED", "archive_manifest_sha256": digest(manifest),
            "archive_input_sha256": research["plan"]["inputs_sha256"], "research_sha256": research["sha256"],
            "initial": original, "correction": revision, "gap": gap,
            "negative_cases": 6, "provider_calls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    args = parser.parse_args()
    with patch.object(socket, "socket", side_effect=AssertionError("NETWORK_DISABLED")):
        print(json.dumps(proof(args.state), sort_keys=True))


if __name__ == "__main__":
    main()
