"""V229-1: the time basis -- archive parsing, 15:30 ET across DST, half days,
the five-session horizon and the archive's last bar."""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import bars  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min, write_bars  # noqa: E402

REAL_DIR = ROOT / "tests" / "fixtures" / "v229" / "5min"
UTC = "UTC"


@pytest.mark.parametrize("day, expected", [
    (dt.date(2026, 10, 30), "2026-10-30 19:30"),  # EDT: UTC-4
    (dt.date(2026, 11, 2), "2026-11-02 20:30"),   # EST after the 2026-11-01 change
    (dt.date(2026, 3, 6), "2026-03-06 20:30"),    # EST before the 2026-03-08 change
    (dt.date(2026, 3, 9), "2026-03-09 19:30"),    # EDT after it
])
def test_deferral_start_moves_with_daylight_saving(day, expected):
    assert bars.deferral_start(day) == pd.Timestamp(expected, tz=UTC)


@pytest.mark.parametrize("day", [dt.date(2026, 11, 27),   # half day after Thanksgiving
                                 dt.date(2026, 11, 26),   # Thanksgiving
                                 dt.date(2026, 11, 7)])   # Saturday
def test_no_deferral_start_on_half_days_and_closed_days(day):
    assert bars.deferral_start(day) is None


def test_session_open_and_close_in_utc():
    assert bars.session_open(dt.date(2026, 11, 3)) == pd.Timestamp("2026-11-03 14:30", tz=UTC)
    assert bars.session_close_utc(dt.date(2026, 11, 3)) == pd.Timestamp("2026-11-03 21:00", tz=UTC)
    assert bars.session_close_utc(dt.date(2026, 11, 27)) == pd.Timestamp("2026-11-27 18:00", tz=UTC)


@pytest.mark.parametrize("day, expected", [
    (dt.date(2026, 11, 3), "2026-11-10 21:00"),   # 4, 5, 6, 9, 10
    (dt.date(2026, 11, 23), "2026-12-01 21:00"),  # skips Thanksgiving, counts the half day
    (dt.date(2026, 11, 19), "2026-11-27 18:00"),  # the fifth session IS the half day
])
def test_horizon_end_is_the_close_of_the_fifth_session_after(day, expected):
    assert bars.horizon_end(day) == pd.Timestamp(expected, tz=UTC)


def test_horizon_end_past_the_calendar_is_none():
    assert bars.horizon_end(dt.date(2030, 12, 30)) is None


def test_to_utc_reads_the_export_text_and_refuses_blanks():
    assert bars.to_utc("2026-10-30 14:35:12.123+00") == pd.Timestamp("2026-10-30 14:35:12.123", tz=UTC)
    for bad in ("", "   ", None, "not a time"):
        with pytest.raises(ValueError):
            bars.to_utc(bad)


def test_et_date_and_time_convert_from_utc():
    ts = pd.Timestamp("2026-11-04 02:30", tz=UTC)  # 21:30 ET on the 3rd
    assert bars.et_date(ts) == dt.date(2026, 11, 3)
    assert bars.et_time(ts) == dt.time(21, 30)


def test_load_bars_round_trips_a_synthetic_archive(tmp_path):
    write_bars(tmp_path, "AAPL", five_min(["2026-11-03"]))
    out = bars.load_bars(tmp_path, "AAPL")
    assert list(out.columns) == list(bars.COLUMNS)
    assert str(out.index.tz) == UTC
    assert out.index[0] == et("2026-11-03 09:30") and out.index[-1] == et("2026-11-03 15:55")
    assert len(out) == 78


def test_load_bars_missing_file_is_none_and_safe_symbol_is_used(tmp_path):
    assert bars.load_bars(tmp_path, "MSFT") is None
    write_bars(tmp_path, "GC=F", five_min(["2026-11-03"]))
    assert (tmp_path / "GC_F.csv").is_file()
    assert bars.load_bars(tmp_path, "GC=F") is not None


def test_load_bars_drops_extended_hours_and_sorts(tmp_path):
    frame = five_min(["2026-11-03"])
    extra = frame.iloc[:1].copy()
    extra.index = pd.DatetimeIndex([et("2026-11-03 08:00")], name="Datetime")
    write_bars(tmp_path, "AAPL", pd.concat([frame.iloc[::-1], extra]))
    out = bars.load_bars(tmp_path, "AAPL")
    assert out.index.is_monotonic_increasing
    assert out.index[0] == et("2026-11-03 09:30") and len(out) == 78


def test_load_bars_refuses_naive_stamps_and_missing_columns(tmp_path):
    (tmp_path / "NAIVE.csv").write_text(
        "Datetime,Open,High,Low,Close,Volume\n2026-11-03 14:30:00,1,1,1,1,1\n", encoding="utf-8")
    with pytest.raises(bars.ArchiveError, match="offset"):
        bars.load_bars(tmp_path, "NAIVE")
    (tmp_path / "COLS.csv").write_text(
        "Datetime,Open,High\n2026-11-03 14:30:00+00:00,1,1\n", encoding="utf-8")
    with pytest.raises(bars.ArchiveError, match="Low"):
        bars.load_bars(tmp_path, "COLS")


def test_real_archive_file_carries_utc_offsets_and_bar_start_stamps():
    raw = (REAL_DIR / "AAPL.csv").read_text(encoding="utf-8").splitlines()
    assert raw[1].split(",", 1)[0].endswith("+00:00")
    out = bars.load_bars(REAL_DIR, "AAPL")
    days = [bars.et_date(t) for t in out.index]
    first = {d: out.index[days.index(d)] for d in (dt.date(2026, 10, 30), dt.date(2026, 11, 3))}
    assert first[dt.date(2026, 10, 30)] == pd.Timestamp("2026-10-30 13:30", tz=UTC)  # EDT open
    assert first[dt.date(2026, 11, 3)] == pd.Timestamp("2026-11-03 14:30", tz=UTC)   # EST open
    assert bars.deferral_start(dt.date(2026, 11, 3)) in out.index


def test_archive_last_bar_is_the_latest_last_line(tmp_path):
    write_bars(tmp_path, "AAPL", five_min(["2026-11-03"]))
    write_bars(tmp_path, "MSFT", five_min(["2026-11-03", "2026-11-04"]))
    (tmp_path / "EMPTY.csv").write_text("Datetime,Open,High,Low,Close,Volume\n", encoding="utf-8")
    assert bars.archive_last_bar(tmp_path) == et("2026-11-04 15:55").isoformat()
    assert bars.archive_last_bar(tmp_path / "absent") is None
