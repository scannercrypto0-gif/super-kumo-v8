"""P0 real archive intake contract tests; local fixtures are NOT real market data."""
import csv
import hashlib
import io
from zipfile import ZipFile

import pytest

from research_wp_r0.retrospective_kline_intake import inspect_binance_spot_zip


def archive(tmp_path, *, microseconds=False, gap=False):
    rows = []
    for i in (0, 2) if gap else (0, 1):
        opening = 1704067200000 + i * 60000
        closing = opening + 59999
        if microseconds:
            opening *= 1000
            closing = closing * 1000 + 999
        rows.append([opening, 100, 105, 95, 102, 5, closing, 0, 1, 0, 0, 0])
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerows(rows)
    path = tmp_path / "BTCUSDT-1m-test.zip"
    with ZipFile(path, "w") as z:
        z.writestr("BTCUSDT-1m-test.csv", stream.getvalue())
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("microseconds", [False, True])
def test_verified_archive_and_timestamp_units(tmp_path, microseconds):
    path, sha = archive(tmp_path, microseconds=microseconds)
    receipt, bars = inspect_binance_spot_zip(path, expected_sha256=sha)
    assert receipt.count == 2 and receipt.gap_count == 0
    assert bars[1][0] - bars[0][0] == 60000
    assert receipt.availability == "RETROSPECTIVE_NOT_CONFIRMED"


def test_gaps_visible_not_silently_filled(tmp_path):
    path, sha = archive(tmp_path, gap=True)
    receipt, bars = inspect_binance_spot_zip(path, expected_sha256=sha)
    assert receipt.gap_count == 1
    assert len(bars) == 2


def test_independent_archive_commitment_required(tmp_path):
    path, sha = archive(tmp_path)
    with pytest.raises(ValueError, match="checksum"):
        inspect_binance_spot_zip(path, expected_sha256="f" * 64)
    with pytest.raises(ValueError, match="SHA256"):
        inspect_binance_spot_zip(path, expected_sha256="")
