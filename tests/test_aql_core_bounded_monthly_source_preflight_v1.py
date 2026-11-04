"""No network/private original bytes: bounded source preflight adversarial tests."""
import hashlib
from io import BytesIO
import unittest
from zipfile import ZipFile,ZIP_DEFLATED
from research_wp_r0.aql_core_bounded_monthly_source_preflight_v1 import (
    SourcePreflightError,month_window,source_urls,verify_native_month,
    stage_one_month,
)
from tempfile import TemporaryDirectory


def sample(month="2024-03", missing=False, corrupt=False):
    start,end=month_window(month)
    width=900000
    count=(end-start)//width
    rows=[]
    for i in range(count-(1 if missing else 0)):
        t=start+i*width
        rows.append(",".join(map(str,(
            t,100,101,99,100,10,t+width-1,1000,1,1,1,0,
        ))))
    csv=("\n".join(rows)+"\n").encode()
    u=source_urls(month)
    sink=BytesIO()
    with ZipFile(sink,"w",compression=ZIP_DEFLATED) as z:
        z.writestr(u["archive_name"][:-4]+".csv",csv)
    raw=sink.getvalue()
    sha=hashlib.sha256(raw).hexdigest()
    cs=(sha+"  "+u["archive_name"]+"\n").encode()
    if corrupt:
        cs=("0"*64+"  "+u["archive_name"]+"\n").encode()
    return raw,cs


class NativeMonthlyPreflight(unittest.TestCase):
    def test_one_new_month_full_native_grid_and_determinism(self):
        raw,cs=sample()
        x=verify_native_month("2024-03",raw,cs,provenance="TEST_ONLY")
        self.assertEqual(x,verify_native_month("2024-03",raw,cs,provenance="TEST_ONLY"))
        self.assertEqual(x["expected_bars"],2976)
        self.assertEqual(x["observed_bars"],2976)
        self.assertEqual(x["coverage"],"COMPLETE")
        self.assertEqual(x["historical_pit"],"NOT_ATTESTED")
        self.assertEqual(x["vault_ingestion"],"NOT_EXECUTED_BY_PREFLIGHT")
        self.assertIsNone(x["historical_known_at_ms"])

    def test_existing_original_months_not_refetched(self):
        for month in ("2024-02","2024-08"):
            with self.assertRaisesRegex(SourcePreflightError,"ALREADY_PINNED"):
                month_window(month)

    def test_checksum_tamper_rejected(self):
        raw,cs=sample(corrupt=True)
        with self.assertRaisesRegex(SourcePreflightError,"PUBLISHER_CHECKSUM"):
            verify_native_month("2024-03",raw,cs,provenance="TEST_ONLY")

    def test_missing_native_bar_rejected(self):
        raw,cs=sample(missing=True)
        with self.assertRaisesRegex(SourcePreflightError,"MISSING_OR_EXTRA"):
            verify_native_month("2024-03",raw,cs,provenance="TEST_ONLY")

    def test_network_requires_explicit_opt_in(self):
        with TemporaryDirectory() as root:
            with self.assertRaisesRegex(SourcePreflightError,"NETWORK_OPT_IN_REQUIRED"):
                stage_one_month("2024-03",root)
            with self.assertRaisesRegex(SourcePreflightError,"ALREADY_PINNED"):
                stage_one_month("2024-02",root)

    def test_month_out_of_scope(self):
        for month in ("2023-12","2025-01","2024-13","../../2024-03"):
            with self.assertRaisesRegex(SourcePreflightError,"MONTH_OUTSIDE"):
                source_urls(month)


if __name__=="__main__":
    unittest.main()
