"""Private original intake: synthetic fixtures never match actual Work #247 pins."""
import unittest
from datetime import datetime,timezone
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from research_wp_r0.aql_factory_authorized_original_run_v1 import (
 OriginalAccessError,PINS,CORE_DATASET_ALIASES,preflight,
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

    def test_core_dataset_alias_is_explicit_and_pit_never_claimed(self):
        cutoff=int(datetime(2026,11,4,tzinfo=timezone.utc).timestamp()*1000)
        for month in PINS:
            spec=month_spec(month,cutoff,{"dataset_id":PINS[month][4]})
            self.assertEqual(spec["dataset_id"],CORE_DATASET_ALIASES[month])
            self.assertNotEqual(spec["dataset_id"],PINS[month][4])
            self.assertFalse(spec["test_only"])
            self.assertEqual(spec["interval"],"15m")
            self.assertIsNone(spec["correction_reason"])
        with self.assertRaises(OriginalAccessError):
            month_spec("2024-02",1706745600000,{"dataset_id":PINS["2024-02"][4]})

    def test_no_synthetic_substitution_in_private_runner(self):
        raw,checks,_=fixture()
        with self.assertRaises(OriginalAccessError):
            run_source_only(raw,checks,"2024-02",1790000000000,
                            "/missing/core","/missing/raw","/x","/y")
if __name__=="__main__":unittest.main()
