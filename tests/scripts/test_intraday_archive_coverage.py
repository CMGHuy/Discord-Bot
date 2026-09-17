import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import intraday_archive_coverage as cov  # noqa: E402
from swingbot.core.marketdata.data_store import cache_path  # noqa: E402


def _write_intraday(base_dir, symbol, tf, first_day, sessions, bars_per_session=4):
    days = pd.bdate_range(first_day, periods=sessions)
    stamps = [day + pd.Timedelta(hours=14, minutes=30 + 15 * k)
              for day in days for k in range(bars_per_session)]
    frame = pd.DataFrame({"Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0,
                          "Volume": 100.0}, index=pd.DatetimeIndex(stamps, name="Datetime"))
    frame.to_csv(cache_path(symbol, tf, base_dir=str(base_dir)))


def test_coverage_reports_depth_and_a_stale_symbol(tmp_path):
    _write_intraday(tmp_path, "AAPL", "15min", "2026-07-01", 50)
    _write_intraday(tmp_path, "MSFT", "15min", "2026-07-01", 50)
    _write_intraday(tmp_path, "OLD", "15min", "2026-07-01", 40)   # stops 10 sessions early
    report = cov.coverage(str(tmp_path), timeframes=("15min",))
    tf = report["15min"]
    assert tf["symbols"] == 3
    assert tf["earliest"] == "2026-07-01"
    assert tf["latest"] == str(pd.bdate_range("2026-07-01", periods=50)[-1].date())
    assert tf["median_sessions"] == 50
    assert tf["stale"] == ["OLD"]


def test_an_empty_timeframe_reports_zero_not_a_crash(tmp_path):
    report = cov.coverage(str(tmp_path), timeframes=("5min",))
    assert report["5min"] == {"symbols": 0, "earliest": None, "latest": None,
                              "median_sessions": None, "stale": [], "unreadable": []}


def test_a_zero_row_cache_file_is_skipped_not_counted(tmp_path):
    # A file that exists and parses cleanly but has no data rows -- the
    # frame.empty guard, distinct from a file that fails to parse at all.
    empty_path = cache_path("EMPTY", "5min", base_dir=str(tmp_path))
    pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"]).to_csv(empty_path)
    _write_intraday(tmp_path, "AAPL", "5min", "2026-07-01", 5)

    report = cov.coverage(str(tmp_path), timeframes=("5min",))
    tf = report["5min"]
    assert tf["symbols"] == 1
    assert tf["unreadable"] == []


def test_a_malformed_cache_file_is_surfaced_as_unreadable_not_zero(tmp_path):
    _write_intraday(tmp_path, "AAPL", "5min", "2026-07-01", 5)
    _write_intraday(tmp_path, "MSFT", "5min", "2026-07-01", 5)
    # A truncated/corrupt file -- e.g. the writer was killed mid-write.
    # pandas raises EmptyDataError on a genuinely empty file; this must not
    # take down the sweep, nor be reported as "zero bars for BAD".
    bad_path = cache_path("BAD", "5min", base_dir=str(tmp_path))
    Path(bad_path).write_text("")

    report = cov.coverage(str(tmp_path), timeframes=("5min",))
    tf = report["5min"]
    assert tf["symbols"] == 2
    assert tf["unreadable"] == ["BAD"]


def test_render_and_main_exit_zero(tmp_path, capsys):
    _write_intraday(tmp_path, "AAPL", "5min", "2026-07-01", 5)
    assert cov.main(["--base-dir", str(tmp_path), "--timeframes", "5min"]) == 0
    out = capsys.readouterr().out
    assert "5min" in out and "symbols=1" in out
