"""Tests for G1 — contracts.py: PIT admission, SourceManifest, envelope."""
import json
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from tools.scanner_engine_offline.contracts import (
    AdmittedBar, AdmissionResult, admit_bars, SourceManifest,
    ScannerNominationEnvelope, canonical_bytes, sha256_hex,
    AVAILABILITY_RETRO, AVAILABILITY_LIVE_PIT, AVAILABILITY_UNKNOWN,
    STAGE_NOMINATED, STAGE_SCREENED, SCHEMA_VERSION,
    _utc, _decimal,
)

UTC = timezone.utc
T0 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
T1 = datetime(2024, 1, 1, 11, 55, 0, tzinfo=UTC)  # 5 min before T0
T2 = datetime(2024, 1, 1, 11, 50, 0, tzinfo=UTC)  # 10 min before T0


def make_bar(**kwargs) -> AdmittedBar:
    defaults = dict(
        source_id="TEST",
        timeframe="5m",
        symbol="SOLUSDT",
        open_at=T2,
        close_at=T1,
        available_at=T1 + timedelta(seconds=1),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        base_volume=Decimal("500"),
        quote_volume=Decimal("50000"),
    )
    defaults.update(kwargs)
    return AdmittedBar(**defaults)


class TestAdmittedBarValidatePit:
    def test_clean_bar_passes(self):
        bar = make_bar()
        assert bar.validate_pit(T0) == []

    def test_bar_not_closed_at_cutoff(self):
        bar = make_bar(close_at=T0 + timedelta(minutes=5))
        errs = bar.validate_pit(T0)
        assert "BAR_NOT_CLOSED_AT_CUTOFF" in errs

    def test_bar_not_available_at_cutoff(self):
        bar = make_bar(available_at=T0 + timedelta(minutes=1))
        errs = bar.validate_pit(T0)
        assert "BAR_NOT_AVAILABLE_AT_CUTOFF" in errs

    def test_bar_available_before_close_rejected(self):
        bar = make_bar(available_at=T2 - timedelta(seconds=1))
        errs = bar.validate_pit(T0)
        assert "BAR_AVAILABLE_BEFORE_CLOSE" in errs

    def test_invalid_ohlc_ranges(self):
        bar = make_bar(open=Decimal("200"), close=Decimal("50"))
        errs = bar.validate_pit(T0)
        assert "BAR_OHLC_OUT_OF_RANGE" in errs

    def test_negative_volume_rejected(self):
        bar = make_bar(base_volume=Decimal("-1"))
        errs = bar.validate_pit(T0)
        assert "BAR_NEGATIVE_VOLUME" in errs

    def test_naive_datetime_raises(self):
        with pytest.raises(ValueError, match="TIMESTAMP_MUST_BE_TZ_AWARE"):
            make_bar(open_at=datetime(2024, 1, 1, 12, 0, 0))

    def test_unsupported_timeframe_raises(self):
        with pytest.raises(ValueError, match="UNSUPPORTED_TIMEFRAME"):
            make_bar(timeframe="3m")


class TestAdmitBars:
    def _make_bars(self, n: int) -> list[AdmittedBar]:
        bars = []
        for i in range(n):
            t = T0 - timedelta(minutes=5 * (n - i))
            bars.append(make_bar(
                open_at=t - timedelta(minutes=5),
                close_at=t,
                available_at=t + timedelta(seconds=1),
            ))
        return bars

    def test_all_admitted(self):
        bars = self._make_bars(5)
        result = admit_bars(bars, T0, source_id="S", availability_class=AVAILABILITY_RETRO)
        assert result.bars_admitted == 5
        assert result.rejected_count == 0
        assert result.is_clean

    def test_future_bar_rejected(self):
        bars = self._make_bars(4)
        future = make_bar(close_at=T0 + timedelta(minutes=10))
        bars.append(future)
        result = admit_bars(bars, T0, source_id="S", availability_class=AVAILABILITY_RETRO)
        assert result.rejected_count == 1
        assert result.bars_admitted == 4

    def test_unknown_availability_class_raises(self):
        bars = self._make_bars(2)
        with pytest.raises(ValueError, match="UNKNOWN_AVAILABILITY_CLASS"):
            admit_bars(bars, T0, source_id="S", availability_class="BOGUS")

    def test_admitted_sorted_ascending(self):
        bars = self._make_bars(5)
        result = admit_bars(bars[::-1], T0, source_id="S", availability_class=AVAILABILITY_RETRO)
        open_times = [b.open_at for b in result.admitted]
        assert open_times == sorted(open_times)


class TestSourceManifest:
    def test_manifest_sha_is_deterministic(self):
        m = SourceManifest(
            dataset_id="D1", dataset_sha="abc", schema_version=SCHEMA_VERSION,
            cutoff_at=T0, created_at=T0,
        )
        assert m.manifest_sha == m.manifest_sha

    def test_different_datasets_different_sha(self):
        m1 = SourceManifest("D1", "abc", SCHEMA_VERSION, T0, T0)
        m2 = SourceManifest("D2", "abc", SCHEMA_VERSION, T0, T0)
        assert m1.manifest_sha != m2.manifest_sha

    def test_naive_datetime_raises(self):
        with pytest.raises(ValueError, match="TIMESTAMP_MUST_BE_TZ_AWARE"):
            SourceManifest("D", "s", SCHEMA_VERSION,
                           datetime(2024, 1, 1), datetime(2024, 1, 1))


class TestScannerNominationEnvelope:
    def _make_env(self, **kwargs) -> ScannerNominationEnvelope:
        manifest = SourceManifest("D", "sha", SCHEMA_VERSION, T0, T0)
        defaults = dict(
            scanner_id="S1",
            candidate_id="SOLUSDT:2024",
            profile_id="INTRADAY",
            market="BINANCE:SPOT:USDT",
            cutoff_at=T0,
            availability_class=AVAILABILITY_RETRO,
            stage=STAGE_NOMINATED,
            source_manifest=manifest.as_dict(),
            feature_snapshot={"oc_5m": "1.5"},
            reasons=["TEST"],
            coverage={"ok": 1, "total": 1},
            score="72.00",
            score_status="SCORED",
        )
        defaults.update(kwargs)
        return ScannerNominationEnvelope(**defaults)

    def test_seal_sets_digest(self):
        env = self._make_env()
        assert env.digest is None
        env.seal()
        assert env.digest is not None
        assert len(env.digest) == 64

    def test_digest_is_deterministic(self):
        env1 = self._make_env().seal()
        env2 = self._make_env().seal()
        assert env1.digest == env2.digest

    def test_publishable_always_false(self):
        env = self._make_env(publishable=True).seal()
        assert env.as_dict()["publishable"] is False

    def test_delivery_authorized_always_false(self):
        env = self._make_env(delivery_authorized=True).seal()
        assert env.as_dict()["delivery_authorized"] is False

    def test_to_json_is_valid_json(self):
        env = self._make_env().seal()
        d = json.loads(env.to_json())
        assert d["schema_version"] == SCHEMA_VERSION

    def test_digest_changes_if_payload_changes(self):
        env1 = self._make_env(score="72.00").seal()
        env2 = self._make_env(score="73.00").seal()
        assert env1.digest != env2.digest


class TestHelpers:
    def test_canonical_bytes_sorted_keys(self):
        b1 = canonical_bytes({"b": 1, "a": 2})
        b2 = canonical_bytes({"a": 2, "b": 1})
        assert b1 == b2

    def test_sha256_hex_length(self):
        assert len(sha256_hex(b"hello")) == 64

    def test_decimal_rejects_bool(self):
        with pytest.raises(ValueError, match="BOOL_NOT_NUMERIC"):
            _decimal(True)

    def test_decimal_rejects_inf(self):
        with pytest.raises(ValueError, match="NON_FINITE_NUMERIC_VALUE"):
            _decimal(float("inf"))
