"""v222: the weekday ^VIX archiver (network stubbed)."""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ops"))
import archive_vix as av  # noqa: E402


def _daily(days, base=10.0):
    idx = pd.DatetimeIndex(pd.to_datetime(days)).tz_localize("UTC")
    return pd.DataFrame({"Open": base, "High": base + 1, "Low": base - 1, "Close": base}, index=idx)


def test_daily_first_run_starts_at_2016_and_second_run_only_tops_up(tmp_path):
    calls = []

    def dl(start, end, interval):
        calls.append(start)
        return _daily(["2026-11-05", "2026-11-06"], base=20.0 + len(calls))

    assert av.archive_daily(date(2026, 11, 6), download=dl, out=tmp_path) == 0
    assert calls[0] == date(2016, 1, 1)
    assert av.archive_daily(date(2026, 11, 9), download=dl, out=tmp_path) == 0
    assert calls[1] == date(2026, 10, 30)
    df = pd.read_csv(tmp_path / "VIX_daily.csv", index_col="Date", parse_dates=True)
    assert len(df) == 2 and df.index.is_unique and df["Close"].iloc[-1] == 22.0


def test_daily_empty_download_is_rc1_and_writes_nothing(tmp_path):
    assert av.archive_daily(date(2026, 11, 6), download=lambda *a: pd.DataFrame(), out=tmp_path) == 1
    assert not (tmp_path / "VIX_daily.csv").exists()


def test_merge_daily_new_rows_win_and_stay_sorted():
    old = av.merge_daily(None, _daily(["2026-11-04", "2026-11-05"], 10.0))
    out = av.merge_daily(old, _daily(["2026-11-05", "2026-11-06"], 30.0))
    assert list(out["Close"]) == [10.0, 30.0, 30.0]


def _minutes(day):
    idx = pd.date_range(f"{day} 14:30", periods=3, freq="1min", tz="UTC")
    return pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)


def test_intraday_writes_finished_days_once_and_skips_today(tmp_path):
    now = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)  # Monday morning

    def dl(start, end, interval):
        return pd.concat([_minutes("2026-11-05"), _minutes("2026-11-09")])

    assert av.archive_intraday(now, download=dl, out=tmp_path) >= 1
    names = sorted(p.name for p in (tmp_path / "intraday_1m").iterdir())
    assert names == ["VIX_2026-11-05_1m.csv"]
    assert av.archive_intraday(now, download=dl, out=tmp_path) == 0


def test_intraday_after_close_includes_today(tmp_path):
    now = datetime(2026, 11, 9, 22, 30, tzinfo=timezone.utc)
    av.archive_intraday(now, download=lambda *a: _minutes("2026-11-09"), out=tmp_path)
    assert (tmp_path / "intraday_1m" / "VIX_2026-11-09_1m.csv").exists()
