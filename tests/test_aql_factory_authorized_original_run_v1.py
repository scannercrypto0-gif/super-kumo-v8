"""Private original intake: synthetic fixtures never match actual Work #247 pins."""
import unittest
import tempfile
import pathlib
import json
from unittest.mock import patch
from datetime import datetime,timezone
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from research_wp_r0.aql_factory_authorized_original_run_v1 import (
 OriginalAccessError,PINS,preflight,
 verify_original,month_spec,run_source_only)

def fixture():
    member=b"1706745600000,100,102,99,101,5,1706746499999,505,10,2,202,0\n"
    out=BytesIO()
    with ZipFile(out,"w",ZIP_DEFLATED) as z:
        z.writestr("BTCUSDT-15m-2024-02.csv",member)
    raw=out.getvalue();h=sha256(raw).hexdigest()
    checks=(h+"  BTCUSDT-15m-2024-02.zip\n").encode()
    return raw,checks,(h,sha256(member).hexdigest(),
        sha256(checks).hexdigest(),1,"TEST_ONLY")

class OwnerOriginalGate(unittest.TestCase):
    def test_fixture_preflight_cannot_promote_to_real(self):
        raw,checks,expected=fixture()
        self.assertEqual(preflight(raw,checks,"2024-02",expected)["bar_count"],1)
        with self.assertRaises(OriginalAccessError):
            verify_original(raw,checks,"2024-02")

    def test_published_month_pins_unmodified(self):
        self.assertEqual(set(PINS),{"2024-02","2024-08"})
        self.assertEqual([PINS[m][3] for m in sorted(PINS)],[2784,2976])
        self.assertEqual(PINS["2024-02"][0],
            "55066890cd3a76c97c05e94213311b17a4146d697f6abe8762b3edae8495b20e")

    def test_bad_archive_checksum_member_and_wrong_month_rejected(self):
        raw,checks,pins=fixture()
        for rr,cc,pp,month in [
            (raw+b"x",checks,pins,"2024-02"),
            (raw,b"invalid",pins,"2024-02"),
            (raw,checks,(pins[0],"f"*64,pins[2],1,"TEST"),"2024-02"),
            (raw,checks,(pins[0],pins[1],"f"*64,1,"TEST"),"2024-02"),
            (raw,checks,pins,"2024-08"),
        ]:
            with self.subTest(month=month):
                with self.assertRaises(OriginalAccessError):
                    preflight(rr,cc,month,pp)
        with self.assertRaises(OriginalAccessError):
            verify_original(raw,checks,"2024-03")

    def test_exact_work247_dataset_identity_and_pit_never_claimed(self):
        cutoff=int(datetime(2026,11,4,tzinfo=timezone.utc).timestamp()*1000)
        for month in PINS:
            spec=month_spec(month,cutoff,{"dataset_id":PINS[month][4]})
            self.assertEqual(spec["dataset_id"],PINS[month][4])
            self.assertFalse(spec["test_only"])
            self.assertEqual(spec["interval"],"15m")
            self.assertIsNone(spec["correction_reason"])
        with self.assertRaises(OriginalAccessError):
            month_spec("2024-02",1706745600000,{"dataset_id":PINS["2024-02"][4]})

    def test_private_cli_real_argument_names_are_parsed(self):
        # Pure CLI plumbing test. Stubbed synthetic receipt: never claims
        # original access or actual Core/RAW execution.
        from research_wp_r0 import aql_factory_authorized_original_run_v1 as m
        with tempfile.TemporaryDirectory(prefix="aql254-cli-") as tmp:
            root=pathlib.Path(tmp)
            original=root/"BTCUSDT-15m-2024-02.zip"
            checks=root/"BTCUSDT-15m-2024-02.zip.CHECKSUM"
            target=root/"CLI_TEST_ONLY.json"
            original.write_bytes(b"fake-not-original")
            checks.write_bytes(b"fake-checksum")
            args=["--month","2024-02","--original-zip",str(original),
                  "--checksum-file",str(checks),"--core-checkout",str(root),
                  "--raw-checkout",str(root),"--core-root",str(root/"core"),
                  "--raw-root",str(root/"raw"),"--receipt-out",str(target),
                  "--cutoff-ms","1793775600000"]
            with patch.dict("os.environ",{
                   "AQL_AUTHORIZED_ORIGINAL_CORE_FACTORY_RUNNER":
                       "OWNER_APPROVED_PRIVATE_ONLY"}), patch.object(
                   m,"run_source_only",return_value={
                       "schema":"SYNTHETIC_STUB_ONLY",
                       "orders_created":0}) as fake:
                self.assertEqual(m.main(args),0)
                self.assertEqual(fake.call_count,1)
            self.assertEqual(json.loads(target.read_text())["schema"],
                             "SYNTHETIC_STUB_ONLY")

    def test_no_synthetic_substitution_in_private_runner(self):
        raw,checks,_=fixture()
        with self.assertRaises(OriginalAccessError):
            run_source_only(raw,checks,"2024-02",1790000000000,
                            "/missing/core","/missing/raw","/x","/y")
if __name__=="__main__":unittest.main()
