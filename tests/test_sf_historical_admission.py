"""Synthetic-fixture-only SF-DEC-23/24/25 acceptance. Never access reserved OOS."""
from dataclasses import replace
import copy
import pytest

from research_wp_r0.content_identity import content_hash_v1
from research_wp_r0.historical_library import (
    HistoricalBar, DataAvailabilityKind, validate_bars, make_test_bar,
)
from research_wp_r0.sf_historical_admission import (
    DevBoundary, preflight_dev, verify_admission_report, human_summary,
)
from research_wp_r0.strategy_definition import digest

UNIT = dict(price_unit="USDT", volume_unit="BTC", session="24X7",
            normalization="NONE", adjustment="NONE")


def fixture(*, confirmed=False):
    bars = [make_test_bar(i, availability_kind=DataAvailabilityKind.RETROSPECTIVE)
            for i in range(4)]
    if confirmed:
        bars = [replace(b, availability_kind=DataAvailabilityKind.CONFIRMED,
                        ingest_time_ms=b.bar_close + 1,
                        observation_cutoff_ms=b.bar_close + 1)
                for b in bars]
    bars, manifest = validate_bars(bars, "BTCUSDT", "1m")
    manifest = replace(manifest, dataset_id="synthetic-dev",
                       exchange="fixture", market="spot")
    grant = DevBoundary(manifest.dataset_id, manifest.version,
                        bars[0].bar_open, bars[-1].bar_open,
                        manifest.manifest_integrity_hash, "synthetic:dev-only")
    expected = content_hash_v1(manifest, bars, **UNIT)
    return bars, manifest, grant, expected


def execute(*, confirmed=False):
    bars, manifest, grant, expected = fixture(confirmed=confirmed)
    cutoff = bars[-1].bar_close + 1 if confirmed else None
    return preflight_dev(manifest, bars, boundary=grant,
                         expected_content_hash=expected,
                         decision_cutoff_ms=cutoff, **UNIT)


def test_retrospective_only_development_and_digest():
    report = execute()
    assert report["tier"] == "RETROSPECTIVE_DEV"
    assert report["dev_eligible"] is False
    assert "DEV_PARTITION_AUTHORITY_NOT_VERIFIED" in report["blocked_reasons"]
    assert report["confirmed_pit_eligible"] is False
    assert report["availability"] == "HISTORICAL_ARRIVAL_UNKNOWN"
    assert "OOS LOCKED" in human_summary(report)
    assert verify_admission_report(report, expected_report_digest=report["report_digest"])


def test_confirmed_metadata_never_promoted():
    report = execute(confirmed=True)
    assert report["tier"] == "PIT_METADATA_VALID"
    assert report["confirmed_pit_eligible"] is False
    assert report["dev_eligible"] is False
    assert report["independent_custody"] == "NOT_VERIFIED"


def test_rehashed_fake_pit_or_oos_rejected():
    original = execute(confirmed=True)
    for field, value in (("tier", "CONFIRMED_PIT_VERIFIED"),
                         ("confirmed_pit_eligible", True),
                         ("oos_access", "UNLOCKED"),
                         ("independent_custody", "VERIFIED"),
                         ("state", "COMPLETE")):
        forged = copy.deepcopy(original)
        forged[field] = value
        forged["report_digest"] = digest({k: v for k, v in forged.items()
                                          if k != "report_digest"})
        with pytest.raises(ValueError):
            verify_admission_report(forged,
                                    expected_report_digest=forged["report_digest"])


def test_report_tamper_cannot_match_retained_commitment():
    report = execute()
    forged = copy.deepcopy(report)
    forged["source_reference"] = "changed"
    forged["report_digest"] = digest({k: v for k, v in forged.items()
                                     if k != "report_digest"})
    with pytest.raises(ValueError, match="Retained report digest mismatch"):
        verify_admission_report(forged,
                               expected_report_digest=report["report_digest"])


class Unreadable:
    def __iter__(self):
        raise AssertionError("attempted to read prohibited OOS/mixed bars")


def test_combined_range_rejected_before_iterating():
    bars, manifest, grant, expected = fixture()
    grant = replace(grant, dev_end_ms=bars[-2].bar_open)
    report = preflight_dev(manifest, Unreadable(), boundary=grant,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"
    assert report["blocked_reasons"] == ["DEV_PARTITION_NOT_VERIFIED"]


def test_missing_grant_rejected_before_iterating():
    _, manifest, _, expected = fixture()
    report = preflight_dev(manifest, Unreadable(), boundary=None,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"


def test_wrong_manifest_hash_refused_before_iterating():
    _, manifest, grant, expected = fixture()
    grant = replace(grant, manifest_integrity_hash="0" * 64)
    report = preflight_dev(manifest, Unreadable(), boundary=grant,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"


def test_data_outside_dev_refused():
    bars, manifest, grant, expected = fixture()
    new_bar = replace(bars[-1], bar_open=grant.dev_end_ms + 60000,
                      bar_close=bars[-1].bar_close + 60000)
    report = preflight_dev(manifest, bars[:-1] + [new_bar], boundary=grant,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"


def test_changed_content_or_units_refused():
    bars, manifest, grant, expected = fixture()
    report = preflight_dev(manifest, bars, boundary=grant,
                           expected_content_hash="1" * 64, **UNIT)
    assert report["blocked_reasons"] == ["CONTENT_IDENTITY_MISMATCH"]
    report = preflight_dev(manifest, bars, boundary=grant,
                           expected_content_hash=expected,
                           **dict(UNIT, volume_unit="OTHER"))
    assert report["tier"] == "BLOCKED"


def test_partial_data_rejected():
    bars, manifest, grant, expected = fixture()
    report = preflight_dev(manifest, bars[:2], boundary=grant,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"


def test_future_or_missing_cutoff_prevents_metadata_tier():
    bars, manifest, grant, expected = fixture(confirmed=True)
    report = preflight_dev(manifest, bars, boundary=grant,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"
    assert report["blocked_reasons"] == ["PIT_METADATA_INVALID"]
    report = preflight_dev(manifest, bars, boundary=grant,
                           expected_content_hash=expected,
                           decision_cutoff_ms=grant.dev_end_ms, **UNIT)
    assert report["tier"] == "BLOCKED"


def test_stable_replay_same_inputs():
    bars, manifest, grant, expected = fixture()
    one = preflight_dev(manifest, bars, boundary=grant,
                        expected_content_hash=expected, **UNIT)
    two = preflight_dev(manifest, bars, boundary=grant,
                        expected_content_hash=expected, **UNIT)
    assert one == two


def test_mixed_availability_cannot_be_downgraded():
    bars, _, _, _ = fixture()
    bars = list(bars)
    bars[0] = replace(bars[0], availability_kind=DataAvailabilityKind.CONFIRMED,
                      ingest_time_ms=bars[0].bar_close + 1,
                      observation_cutoff_ms=bars[0].bar_close + 1)
    bars, manifest = validate_bars(bars, "BTCUSDT", "1m")
    manifest = replace(manifest, dataset_id="synthetic-dev",
                       exchange="fixture", market="spot")
    grant = DevBoundary(manifest.dataset_id, manifest.version,
                        bars[0].bar_open, bars[-1].bar_open,
                        manifest.manifest_integrity_hash, "synthetic:dev-only")
    expected = content_hash_v1(manifest, bars, **UNIT)
    report = preflight_dev(manifest, bars, boundary=grant,
                           expected_content_hash=expected, **UNIT)
    assert report["tier"] == "BLOCKED"
    assert report["blocked_reasons"] == ["AVAILABILITY_CLASS_MIXED"]
