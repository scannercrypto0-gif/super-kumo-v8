"""Isolated synthetic producer report tests: no host, network, or real archive."""
import json

import pytest

from aql.warehouse.producer_report import publish_bounded
from aql.warehouse.daily import import_one_retained
from tests.test_warehouse import fixture, warehouse, START, DAY
from aql.warehouse.storage import seal


def _args(tmp_path, **overrides):
    roots = (tmp_path / "reports", tmp_path / "original-warehouse")
    roots[0].mkdir(exist_ok=True)
    roots[1].mkdir(exist_ok=True)
    args = dict(report_root=roots[0], protected_root=roots[1],
                lane="HISTORY", identity="run-a", sequence=3,
                observed_ms=START + DAY, published_ms=START + DAY + 100,
                status="COMMITTED_CHECKPOINT", reason="CONTINUATION_PENDING",
                counters=dict(archives_this_run=3),
                full_history_verified=False)
    args.pop("full_history_verified")
    args.update(overrides)
    return args


def test_atomic_report_is_create_only_and_replay_conflict_rejected(tmp_path):
    args = _args(tmp_path)
    one = publish_bounded(**args)
    two = publish_bounded(**args)
    assert one["sha256"] == two["sha256"] and two["replay"]
    path = args["report_root"] / one["name"]
    assert seal(path.read_bytes()) == one["sha256"]
    assert len(list(args["report_root"].iterdir())) == 1
    assert json.loads(path.read_bytes())["full_history_verified"] is False
    with pytest.raises(ValueError, match="REPLAY_CONFLICT"):
        publish_bounded(**{**args, "status": "FULL_HISTORY_VERIFIED"})
    assert seal(path.read_bytes()) == one["sha256"]


@pytest.mark.parametrize("changed", [
    dict(report_root=None),
    dict(sequence=-1),
    dict(sequence=True),
    dict(observed_ms=START + DAY + 101),
    dict(status="RUN\nFORGED"),
    dict(source_sha256="fake"),
    dict(counters=dict(gaps=-1)),
    dict(identity="../evil"),
])
def test_fail_closed_before_report_creation(tmp_path, changed):
    args = _args(tmp_path)
    if changed["report_root"] is None if "report_root" in changed else False:
        changed = {"report_root": args["protected_root"]}
    with pytest.raises((TypeError, ValueError)):
        publish_bounded(**{**args, **changed})
    assert list(args["report_root"].iterdir()) == []


def test_report_root_must_preexist_and_not_overlap_original(tmp_path):
    args = _args(tmp_path)
    with pytest.raises(ValueError, match="MUST_PREEXIST"):
        publish_bounded(**{**args, "report_root": tmp_path / "does-not-exist"})
    nested = args["protected_root"] / "report"
    nested.mkdir()
    with pytest.raises(ValueError, match="ROOT_OVERLAP"):
        publish_bounded(**{**args, "report_root": nested})


def test_daily_report_only_after_real_synthetic_import_and_registry(tmp_path):
    raw, checksum = fixture()
    inp = tmp_path / "retained"
    inp.mkdir()
    f = inp / "BTCUSDT-1m-2024-01-01.zip"
    f.write_bytes(raw)
    (inp / (f.name + ".CHECKSUM")).write_bytes(checksum)
    w = warehouse(tmp_path / "wh")
    out = tmp_path / "reports"
    out.mkdir()
    ret = import_one_retained(w, f, source_day_ms=START,
                              expected_zip_sha256=seal(raw),
                              expected_checksum_sha256=seal(checksum),
                              observed_ms=START + DAY, report_root=out)
    assert ret["this_run"][0]["status"] == "ARCHIVE_IMPORTED"
    reports = list(out.glob("daily-*.json"))
    assert len(reports) == 1
    evidence = json.loads(reports[0].read_bytes())
    assert evidence["schema"] == "aql.mcp.producer-bounded-report.v1"
    assert evidence["source_sha256"] == seal(raw)
    assert evidence["receipt_sha256"] == ret["warehouse_receipt_sha256"]
    assert evidence["registry_sha256"] == ret["registry"]["snapshot_sha256"]
    assert evidence["publisher_import_registry_verified"] is True
    assert evidence["task_state"] is None
    assert evidence["source_day_ms"] == START
    assert evidence["trading_authority"] == "NONE"


def test_daily_wrong_checksum_cannot_create_report_or_import(tmp_path):
    raw, checksum = fixture()
    inp = tmp_path / "retained"
    inp.mkdir()
    f = inp / "BTCUSDT-1m-2024-01-01.zip"
    f.write_bytes(raw)
    (inp / (f.name + ".CHECKSUM")).write_bytes(checksum)
    w = warehouse(tmp_path / "wh")
    out = tmp_path / "reports"
    out.mkdir()
    with pytest.raises(ValueError, match="DAILY_INPUT_PIN_MISMATCH"):
        import_one_retained(w, f, source_day_ms=START,
                            expected_zip_sha256="0" * 64,
                            expected_checksum_sha256=seal(checksum),
                            observed_ms=START + DAY, report_root=out)
    assert list(out.iterdir()) == []
