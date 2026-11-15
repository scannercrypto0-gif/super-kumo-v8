"""Join versioned delayed archive evidence to immutable receipt-time evidence."""
from contextlib import closing
from decimal import Decimal

from aql.observation.contracts import digest
from aql.observation.durable_bridge_v1 import DurableG2Bridge, require, sha

FIELDS = ("open", "high", "low", "close", "base_volume")


class Reconciliation(DurableG2Bridge):
    """Reuse the native transactional, SHA-chained event store in isolated state."""

    def _replay(self, con, *, prospective=None):
        records = {}

        def ingest(kind, identity, record):
            require(kind == "archive_reconciliation" and identity == digest(record)
                    and identity not in records, "RECONCILIATION_CHAIN")
            require(record["previous"] is None or record["previous"] in records,
                    "RECONCILIATION_PARENT")
            records[identity] = record

        _, _, tail = super()._replay(con, prospective=ingest)
        return records, {}, tail

    def append(self, archive, receipt, *, manifest, cutoff_ms):
        """Use already-verified archive rows and the original retained receipt envelope."""
        require(manifest["evidence_class"] in ("TEST_ONLY", "RETROSPECTIVE_NON_PIT")
                and manifest["rights_status"] == {
                    "TEST_ONLY": "TEST_ONLY", "RETROSPECTIVE_NON_PIT": "VERIFIED_FOR_EXACT_USE"
                }[manifest["evidence_class"]]
                and bool(manifest["rights_ref"])
                and (manifest["evidence_class"] == "TEST_ONLY" or
                     bool(manifest.get("owner_authorization_ref"))), "SOURCE_RIGHTS_GATE")
        require(receipt["is_final"] is True and all(sha(receipt[key]) for key in
                ("source_sha256", "ack_sha256", "decision_sha256", "config_sha256", "code_sha256")),
                "RECEIPT_PARENT")
        require(type(cutoff_ms) is int and receipt["end_exclusive_ms"] <= receipt["received_ms"]
                <= receipt["committed_ms"] <= receipt["decision_cutoff_ms"] <= cutoff_ms,
                "RECEIPT_CUTOFF")
        key = {name: receipt[name] for name in ("market", "interval", "open_ms", "end_exclusive_ms")}
        manifest_pin = digest(manifest)
        require(key["market"] == manifest["market"] and key["interval"] == manifest["native_interval"]
                and manifest["start_ms"] <= key["open_ms"] < key["end_exclusive_ms"]
                <= min(manifest["end_exclusive_ms"], cutoff_ms), "RECONCILIATION_SCOPE")
        if archive is not None:
            require(all(archive[name] == value for name, value in key.items())
                    and archive["is_final"] is True
                    and archive["source_manifest_sha256"] == manifest_pin
                    and archive["sha256"] == digest({k: v for k, v in archive.items() if k != "sha256"}),
                    "ARCHIVE_PARENT")
        archive_sha = archive["sha256"] if archive else None
        comparison = "GAP" if archive is None else (
            "MATCH" if all(Decimal(str(archive[field])) == Decimal(str(receipt[field]))
                           for field in FIELDS) else "DIFFERENCE")
        with closing(self._connect()) as con, con:
            con.execute("BEGIN IMMEDIATE")
            records, _, tail = self._replay(con)
            peers = [(pin, row) for pin, row in records.items() if row["key"] == key]
            for pin, row in peers:
                require(row["receipt"] == receipt, "ORIGINAL_RECEIPT_CHANGED")
                if row["version"] == manifest["source_version"]:
                    require(row["manifest_sha256"] == manifest_pin and row["archive_sha256"] == archive_sha,
                            "ARCHIVE_VERSION_REUSED")
                    return {**row, "sha256": pin}
            previous = peers[-1][0] if peers else None
            category = "CORRECTED_ARCHIVE_VERSION" if previous else comparison
            record = dict(key=key, receipt=receipt, version=manifest["source_version"],
                          manifest_sha256=manifest_pin, archive_sha256=archive_sha, previous=previous,
                          category=category, comparison=comparison, evidence_class=manifest["evidence_class"],
                          mode="RESEARCH_DELAYED", live_monitor="NOT_QUALIFIED",
                          actionability="CURRENT_ENTRY_BLOCKED", current_entry="NO_CURRENT_ENTRY",
                          historical_known_at=None, trading_authority="NONE")
            pin = digest(record)
            self._append(con, "archive_reconciliation", pin, record, tail)
            return {**record, "sha256": pin}
