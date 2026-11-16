"""v228 V228-1: pin the archive time basis on real production rows.

compute_excursion (V228-2) compares journal times (aware UTC ISO strings)
with archive bar indexes. These tests prove what load_normalized hands it:
a naive index in UTC, each bar stamped with its START, for an
Alpaca-eligible ticker (AAPL) and a Yahoo-only one (GC=F), across the
2026-11-01 DST change. They also pin the two traps in
data_store._normalize_cached: mixed offsets -> None, and a single non-UTC
offset -> local wall-clock (which is why every archive must stay +00:00)."""
from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.marketdata.data_store import load_normalized

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "v228" / "archive"
FRAMES = ("5min", "15min", "hourly")
TICKERS = ("AAPL", "GC=F")
STEM = {"AAPL": "AAPL", "GC=F": "GC_F"}


def _raw_stamps(frame: str, ticker: str) -> list[str]:
    path = FIXTURES / frame / f"{STEM[ticker]}.csv"
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) > 1, f"{path} holds no data rows -- re-run V228-1 Step 1"
    return [row[0] for row in rows[1:]]


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("ticker", TICKERS)
def test_every_archived_stamp_carries_a_utc_offset(frame, ticker):
    stamps = _raw_stamps(frame, ticker)
    offenders = [s for s in stamps if not s.endswith("+00:00")]
    assert offenders == []


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("ticker", TICKERS)
def test_load_normalized_returns_the_file_stamps_as_naive_utc(frame, ticker):
    df = load_normalized(ticker, frame, base_dir=str(FIXTURES))
    assert df is not None
    assert df.index.tz is None
    expected = pd.DatetimeIndex(pd.to_datetime(_raw_stamps(frame, ticker), utc=True)).tz_localize(None)
    expected = expected[~expected.duplicated(keep="last")].sort_values()
    assert list(df.index) == list(expected)
    assert df.index.is_monotonic_increasing


def _session(df: pd.DataFrame, day: str) -> pd.DatetimeIndex:
    return df.index[df.index.normalize() == pd.Timestamp(day)]


@pytest.mark.parametrize("frame,last_start", [
    ("5min", ("19:55", "20:55")),
    ("15min", ("19:45", "20:45")),
    ("hourly", ("19:30", "20:30")),
])
def test_aapl_bars_are_stamped_with_their_start_across_the_dst_change(frame, last_start):
    df = load_normalized("AAPL", frame, base_dir=str(FIXTURES))
    before, after = _session(df, "2026-10-30"), _session(df, "2026-11-03")
    # 09:30 New York is 13:30 UTC in daylight time and 14:30 UTC in standard time.
    assert before[0].strftime("%H:%M") == "13:30"
    assert after[0].strftime("%H:%M") == "14:30"
    # The last bar STARTS one bar before the 16:00 New York close.
    assert (before[-1].strftime("%H:%M"), after[-1].strftime("%H:%M")) == last_start


def test_aapl_session_row_counts_match_the_production_check():
    counts = {f: len(load_normalized("AAPL", f, base_dir=str(FIXTURES))) for f in FRAMES}
    assert counts == {"5min": 156, "15min": 52, "hourly": 14}


def _rewrite_offsets(tmp_path: Path, offset_for) -> Path:
    """Copy the AAPL 5min fixture with every stamp moved to a local offset."""
    src = FIXTURES / "5min" / "AAPL.csv"
    with src.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    out_rows = [rows[0]]
    for row in rows[1:]:
        ts = pd.Timestamp(row[0])
        local = ts.tz_convert(offset_for(ts))
        out_rows.append([local.isoformat(sep=" "), *row[1:]])
    target = tmp_path / "5min"
    target.mkdir(parents=True)
    with (target / "AAPL.csv").open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(out_rows)
    return tmp_path


def test_mixed_offsets_make_load_normalized_return_none(tmp_path):
    dst_end = pd.Timestamp("2026-11-01", tz="UTC")
    base = _rewrite_offsets(tmp_path, lambda ts: "-04:00" if ts < dst_end else "-05:00")
    assert load_normalized("AAPL", "5min", base_dir=str(base)) is None


def test_a_single_non_utc_offset_is_read_as_local_wall_clock(tmp_path):
    """The trap the +00:00 assertion guards: tz_localize(None) keeps the
    wall-clock, so a New York-offset file would read 09:30, not 14:30."""
    base = _rewrite_offsets(tmp_path, lambda ts: "-05:00")
    df = load_normalized("AAPL", "5min", base_dir=str(base))
    assert df is not None
    assert _session(df, "2026-11-03")[0].strftime("%H:%M") == "09:30"


def test_the_fixture_tree_is_not_written_by_the_loader():
    before = sorted(p.relative_to(FIXTURES) for p in FIXTURES.rglob("*"))
    for frame in FRAMES:
        load_normalized("AAPL", frame, base_dir=str(FIXTURES))
    assert sorted(p.relative_to(FIXTURES) for p in FIXTURES.rglob("*")) == before
