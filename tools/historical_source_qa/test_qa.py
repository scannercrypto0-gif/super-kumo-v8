import csv
from datetime import datetime, timezone
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from tools.historical_source_qa import qa


def utc(value):
    return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()) * 1000


def native(start, width=qa.MINUTE, unit=1, volume="0.00000000000000000001", trades="1"):
    return [str(start * unit), "100.01", "100.03", "100.00", "100.02", volume,
            str((start + width) * unit - 1), volume, trades, "0", "0", "0"]


class HistoricalQA(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=".")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).absolute()
        self.start = utc("2024-02-05")

    def archive(self, rows, interval="1m", start=None, end=None, unit="ms", version="fixture-v1"):
        start = self.start if start is None else start
        end = start + qa.FIXED[interval] * len(rows) if end is None else end
        path = self.root / f"BTCUSDT-{interval}-{version}.zip"
        raw = io.StringIO()
        csv.writer(raw, lineterminator="\n").writerows(rows)
        with ZipFile(path, "w") as archive:
            info = ZipInfo(path.stem + ".csv", (2024, 1, 1, 0, 0, 0))
            info.create_system = 3
            archive.writestr(info, raw.getvalue())
        checksum = path.with_suffix(".zip.CHECKSUM")
        checksum.write_bytes(f"{qa.sha_bytes(path.read_bytes())}  {path.name}\n".encode())
        manifest = dict(schema="aql.historical-source-manifest.v1", market=list(qa.MARKET),
                        native_interval=interval, start_ms=start, end_exclusive_ms=end,
                        evidence_class="TEST_ONLY", timestamp_unit=unit, pit="NOT_ATTESTED",
                        source_version=version, rights_ref="LOCALLY_GENERATED", rights_status="TEST_ONLY",
                        owner_authorization_ref=None, publisher_first_available_at_ms=None,
                        archive_sha256=qa.sha_bytes(path.read_bytes()),
                        checksum_sha256=qa.sha_bytes(checksum.read_bytes()))
        return path, checksum, manifest

    def admission(self, rows, **options):
        path, checksum, manifest = self.archive(rows, **options)
        return qa.admit(path, checksum, manifest, qa.digest(manifest))

    def minutes(self, count):
        return [native(self.start + i * qa.MINUTE) for i in range(count)]

    def test_all_fixed_intervals_and_exact_decimal(self):
        source = self.admission(self.minutes(1440))
        for interval, count in [("5m",288),("15m",96),("1h",24),("4h",6),("1d",1)]:
            with self.subTest(interval=interval):
                derived = qa.derive(source, interval, self.start + qa.DAY)
                self.assertEqual(len(derived["records"]), count)
                row = derived["records"][0]
                self.assertEqual(row["trades"], 1440 // count)
                self.assertEqual(len(row["parent_sha256"]), 1440 // count)
                self.assertEqual(row["base_volume"], f"0.{1440 // count:020d}")
                self.assertIsNone(row["publisher_first_available_at_ms"])

    def test_calendar_leap_month_and_monday_week(self):
        self.start = utc("2024-02-01")
        source = self.admission(self.minutes(29 * 1440))
        month = qa.derive(source,"1M",utc("2024-03-01"))
        self.assertEqual(month["records"][0]["end_exclusive_ms"],utc("2024-03-01"))
        self.assertEqual(len(month["records"][0]["parent_sha256"]),29*1440)
        week = qa.derive(source,"1w",utc("2024-03-01"))
        self.assertEqual([r["open_ms"] for r in week["records"]],
                         [utc(f"2024-02-{day:02}") for day in (5,12,19)])
        self.assertEqual(len(week["withheld"]),2)
        self.assertEqual(qa.bounds(utc("2024-12-31"),"1M")[1],utc("2025-01-01"))

    def test_gap_zero_trade_future_and_incomplete(self):
        rows = self.minutes(16)
        rows[0] = native(self.start,volume="0",trades="0")
        del rows[5]
        source = self.admission(rows,end=self.start+16*qa.MINUTE)
        self.assertEqual(source["records"][0]["missingness"],"OBSERVED_ZERO_TRADES")
        self.assertEqual(source["missing_opens_ms"],[self.start+5*qa.MINUTE])
        derived = qa.derive(source,"15m",self.start+16*qa.MINUTE)
        self.assertEqual(derived["records"],[])
        self.assertEqual([r["reason"] for r in derived["withheld"]],["INCOMPLETE_GRID","AFTER_CUTOFF"])
        complete = self.admission(self.minutes(15))
        self.assertFalse(qa.derive(complete,"15m",self.start+15*qa.MINUTE-1)["records"])

    def test_native_control_exact_match_and_mismatch(self):
        source = self.admission(self.minutes(15))
        derived = qa.derive(source,"15m",self.start+15*qa.MINUTE)
        row = native(self.start,15*qa.MINUTE,volume="0.00000000000000000015",trades="15")
        control = self.admission([row],interval="15m")
        self.assertEqual(qa.compare_native_15m(derived,control)["status"],"MATCH")
        print("FIXTURE_PARITY_SHA256=" + qa.digest(derived))
        row[4] = "100.01"
        control = self.admission([row],interval="15m",version="v2")
        self.assertEqual(qa.compare_native_15m(derived,control)["mismatches"][0]["fields"],["close"])
        control["records"][0]["market"][0] = "FOREIGN"
        with self.assertRaisesRegex(ValueError,"MARKET_IDENTITY"):
            qa.compare_native_15m(derived,control)

    def test_duplicate_reorder_revision_and_bytes(self):
        rows = self.minutes(2)
        for invalid in ([rows[0],rows[0]], list(reversed(rows))):
            with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_REORDERED"):
                self.admission(invalid)
        old = self.admission(rows)
        rows[0][4] = "100.01"
        new = self.admission(rows,version="revision")
        self.assertEqual(qa.correction(old,new)["status"],"QUARANTINE_REVISION")
        self.assertEqual(old["records"][0]["close"],"100.02")
        path, checksum, manifest = self.archive(rows)
        path.write_bytes(path.read_bytes()+b"tamper")
        with self.assertRaisesRegex(ValueError,"BYTE_PIN"):
            qa.admit(path,checksum,manifest,qa.digest(manifest))

    def test_units_and_rights_negative(self):
        start = utc("2025-01-01")
        self.assertEqual(self.admission([native(start,unit=1000)],start=start,unit="us")["records"][0]["open_ms"],start)
        with self.assertRaisesRegex(ValueError,"TIMESTAMP_UNIT"):
            self.admission([native(start)],start=start)
        with self.assertRaisesRegex(ValueError,"UTC_GRID_OR_UNIT"):
            self.admission([native(start)],start=start,unit="us")
        path, checksum, manifest = self.archive(self.minutes(1))
        pinned = qa.digest(manifest)
        original = checksum.read_bytes()
        checksum.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError,"BYTE_PIN"):
            qa.admit(path,checksum,manifest,pinned)
        checksum.write_bytes(original)
        with self.assertRaisesRegex(ValueError,"MANIFEST_PIN"):
            qa.admit(path,checksum,{**manifest,"source_version":"tampered"},pinned)
        for changes, reason in [
            ({"rights_ref":None},"MISSING_RIGHTS_OR_VERSION"),
            ({"evidence_class":"RETROSPECTIVE_NON_PIT"},"RIGHTS_OR_OWNER_GATE"),
            ({"pit":"ATTESTED"},"FALSE_PIT"),
            ({"publisher_first_available_at_ms":1},"FALSE_PIT"),
            ({"market":["BINANCE","PERP","BTCUSDT","BTC","USDT","UTC"]},"MARKET_IDENTITY"),
        ]:
            altered = {**manifest,**changes}
            with self.subTest(reason=reason),self.assertRaisesRegex(ValueError,reason):
                qa.admit(path,checksum,altered,qa.digest(altered))

    def test_live_contract_through_existing_marketbar_parser(self):
        from src.aql.models.bar import MarketBar
        source = self.admission(self.minutes(15))
        historical = qa.derive(source,"15m",self.start+15*qa.MINUTE)["records"][0]
        for final in (False,True):
            with patch("src.aql.models.bar.time.time",return_value=(historical["end_exclusive_ms"]+20)/1000):
                live = MarketBar.from_binance_ws_kline({
                    "s":"BTCUSDT","i":"15m","t":self.start,"T":historical["end_exclusive_ms"]-1,
                    "o":"100.01","h":"100.03","l":"100.00","c":"100.02","v":"0.1","x":final})
            projected = {**historical,"product":"BINANCE_SPOT_WS","interval":live.interval,
                         "open_ms":live.bar_open,"end_exclusive_ms":live.bar_close+1,"is_final":live.is_final,
                         "exchange_event_at_ms":live.bar_close,"received_at_ms":live.ingested_at,
                         "committed_at_ms":None}
            self.assertIs(qa.validate_envelope(projected)["is_final"], final)
            with self.assertRaisesRegex(ValueError,"UNSUPPORTED_EVIDENCE_PROMOTION"):
                qa.validate_envelope({**projected,"publisher_first_available_at_ms":live.bar_close})


if __name__ == "__main__":
    unittest.main()
