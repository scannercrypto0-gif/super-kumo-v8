"""End-to-end pinned retrospective archive replay acceptance (synthetic ZIP only)."""
import csv
import hashlib
import io
from zipfile import ZipFile

import pytest

from research_wp_r0.pinned_ema_research import run_pinned_ema_development


def make_archive(tmp_path):
    prices = [100.0] * 24 + [105.0] * 6 + [90.0] * 8 + [110.0] * 5
    stream = io.StringIO()
    writer = csv.writer(stream)
    start = 1704067200000
    for i, p in enumerate(prices):
        opening = start + i * 60000
        writer.writerow([opening, p, p + 1, p - 1, p, 10,
                         opening + 59999, 0, 1, 0, 0, 0])
    path = tmp_path / "BTCUSDT-1m-fixture.zip"
    with ZipFile(path, "w") as z:
        z.writestr("BTCUSDT-1m-fixture.csv", stream.getvalue())
    return path, hashlib.sha256(path.read_bytes()).hexdigest(), start


def test_pinned_end_to_end_is_deterministic_and_oos_locked(tmp_path):
    path, sha, start = make_archive(tmp_path)
    args = dict(archive_sha256=sha, source_reference="test-fixture-not-real",
                split_cutoff_ms=start + 38 * 60000)
    first = run_pinned_ema_development(path, **args)
    second = run_pinned_ema_development(path, **args)
    assert first == second
    assert first["oos"] == "LOCKED_NOT_EVALUATED"
    assert first["archive_receipt"]["availability"] == "RETROSPECTIVE_NOT_CONFIRMED"
    assert first["development_report"]["closed_trade_count"] >= 1
    assert all(t["exit_open_ms"] < args["split_cutoff_ms"]
               for t in first["development_report"]["trades"])


def test_tampered_archive_refused_before_replay(tmp_path):
    path, sha, start = make_archive(tmp_path)
    with pytest.raises(ValueError, match="checksum"):
        run_pinned_ema_development(path, archive_sha256="f" * 64,
                                   source_reference="fixture",
                                   split_cutoff_ms=start + 38 * 60000)


def test_archive_gap_refused_before_replay(tmp_path):
    path, _, start = make_archive(tmp_path)
    with ZipFile(path) as z:
        csv_data = z.read(z.namelist()[0]).decode()
    lines = csv_data.splitlines()
    del lines[26]
    with ZipFile(path, "w") as z:
        z.writestr("BTCUSDT-1m-fixture.csv", "\n".join(lines) + "\n")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="gaps"):
        run_pinned_ema_development(path, archive_sha256=sha,
                                   source_reference="fixture",
                                   split_cutoff_ms=start + 38 * 60000)
