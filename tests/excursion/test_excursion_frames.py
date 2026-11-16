"""v228 V228-4: load_frames tells a missing archive from an unreadable one."""
from __future__ import annotations

import dataclasses

import pandas as pd
import pytest

from swingbot.core.analytics.excursion_frames import FrameSet, load_frames
from tests.conftest import make_ohlcv


def _bars(freq: str, periods: int = 6, start: str = "2026-11-12 14:30") -> pd.DataFrame:
    idx = pd.date_range(start, periods=periods, freq=freq, tz="UTC", name="Datetime")
    return pd.DataFrame({"Close": 100.0, "High": 100.5, "Low": 99.5, "Open": 100.0,
                         "Volume": 1000.0}, index=idx)


def _write(base, folder: str, stem: str, df: pd.DataFrame | None = None, text: str | None = None):
    (base / folder).mkdir(parents=True, exist_ok=True)
    path = base / folder / f"{stem}.csv"
    if text is not None:
        path.write_text(text, encoding="utf-8")
    else:
        df.to_csv(path)


def test_reads_every_intraday_archive_finest_first_as_naive_utc(tmp_path):
    for folder, freq in (("hourly", "60min"), ("5min", "5min"), ("15min", "15min")):
        _write(tmp_path, folder, "AAPL", _bars(freq))
    fs = load_frames("AAPL", base_dir=str(tmp_path))
    assert list(fs.frames) == ["5min", "15min", "hourly"]
    assert (fs.missing, fs.unreadable) == ((), ())
    assert fs.frames["5min"].index.tz is None
    assert fs.frames["5min"].index[0] == pd.Timestamp("2026-11-12 14:30")


def test_a_missing_file_and_an_unreadable_file_are_told_apart(tmp_path):
    _write(tmp_path, "5min", "AAPL", _bars("5min"))
    _write(tmp_path, "15min", "AAPL", text="Datetime,Close\nnot-a-date,1\n")
    fs = load_frames("AAPL", base_dir=str(tmp_path))
    assert list(fs.frames) == ["5min"]
    assert fs.missing == ("hourly",)
    assert fs.unreadable == ("15min",)


def test_a_passed_daily_frame_goes_last_and_wins_over_the_archive(tmp_path):
    daily = make_ohlcv([100.0, 101.0], start="2026-11-11")
    _write(tmp_path, "daily", "AAPL", _bars("1D", periods=2, start="2026-11-11"))
    fs = load_frames("AAPL", daily=daily, daily_from_archive=True, base_dir=str(tmp_path))
    assert list(fs.frames) == ["daily"]
    assert fs.frames["daily"] is daily
    assert fs.missing == ("5min", "15min", "hourly")


def test_an_empty_daily_frame_is_left_out_and_not_counted(tmp_path):
    fs = load_frames("AAPL", daily=pd.DataFrame(), base_dir=str(tmp_path))
    assert "daily" not in fs.frames and "daily" not in fs.missing


def test_daily_from_archive_reads_the_daily_folder_or_counts_it_missing(tmp_path):
    assert load_frames("AAPL", daily_from_archive=True, base_dir=str(tmp_path)).missing == (
        "5min", "15min", "hourly", "daily")
    _write(tmp_path, "daily", "AAPL", _bars("1D", periods=2, start="2026-11-11"))
    fs = load_frames("AAPL", daily_from_archive=True, base_dir=str(tmp_path))
    assert list(fs.frames) == ["daily"]


@pytest.mark.parametrize("ticker", ["XAUUSD", ""])
def test_spot_metals_and_blank_tickers_have_no_files(tmp_path, ticker):
    _write(tmp_path, "5min", "GC_F", _bars("5min"))
    fs = load_frames(ticker, base_dir=str(tmp_path))
    assert fs.frames == {} and fs.missing == ("5min", "15min", "hourly")


def test_a_future_symbol_maps_to_its_safe_file_name(tmp_path):
    _write(tmp_path, "5min", "GC_F", _bars("5min"))
    assert list(load_frames("GC=F", base_dir=str(tmp_path)).frames) == ["5min"]


def test_the_loader_creates_no_folders(tmp_path):
    load_frames("AAPL", daily_from_archive=True, base_dir=str(tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_frameset_is_frozen():
    fs = FrameSet(frames={}, missing=(), unreadable=())
    with pytest.raises(dataclasses.FrozenInstanceError):
        fs.missing = ("5min",)
