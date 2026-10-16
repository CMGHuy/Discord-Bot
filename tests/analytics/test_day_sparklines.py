"""v165 D4 -- the day page's price sparklines: window, ticks, staleness, caps.

Frames come from `tests.helpers.make_ohlcv` (business-day index; High/Low =
close +/- 1 %). One test reads a real CSV through `data_store.load_normalized`
with an explicit `base_dir`, the pattern of
tests/marketdata/test_frame_equivalence.py:21-25.

Calendar used throughout: 2026-07-20 is a Monday, so with `_frame()` bar i is
the i-th business day from it -- i7 = Wed 07-29, i10 = Mon 08-03,
i12 = Wed 08-05, i14 = Fri 08-07, i15 = Mon 08-10, i29 = Fri 08-28.
"""
import pandas as pd

from swingbot.core.analytics import day_sparklines as ds
from tests.helpers import make_ohlcv

KEY = "a" * 16 + ":0"


def _frame(periods=30, *, start="2026-07-20"):
    """Close of bar i is 100 + i."""
    return make_ohlcv([100.0 + i for i in range(periods)], start=start)


def _row(**over):
    row = {
        "trade_id": "a" * 16, "leg_index": 0, "ticker": "AAPL",
        "opened_at": "2026-08-03T14:00:00+00:00",
        "closed_at": "2026-08-05T20:00:00+00:00", "day": "2026-08-05",
        "entry_price": 110.0, "stop_price": 105.0, "tp1": 120.0, "tp2": None,
        "exit_price": 112.0,
    }
    row.update(over)
    return row


def test_series_key_is_trade_id_and_leg_index():
    assert ds.series_key(_row(leg_index=1)) == "a" * 16 + ":1"


def test_the_window_runs_three_bars_before_entry_to_three_after_exit():
    series, cut = ds.series_for(_row(), _frame())
    assert cut is False
    assert [c["date"] for c in series["closes"]] == [
        "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04",
        "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10"]
    assert series["closes"][0] == {"date": "2026-07-29", "close": 107.0}
    assert series["exit_bar"] == 5
    assert series["exit_date"] == "2026-08-05"
    assert series["last_bar"] == "2026-08-28"
    assert series["stale"] is False


def test_the_series_never_reaches_past_three_bars_after_the_exit():
    """No-lookahead: a historical card never shows a later price."""
    series, _ = ds.series_for(_row(), _frame())
    after = series["closes"][series["exit_bar"] + 1:]
    assert len(after) == ds.SPARK_PAD_BARS
    assert all(c["date"] > series["exit_date"] for c in after)
    assert max(c["date"] for c in series["closes"]) == "2026-08-10"


def test_the_series_keys_are_exactly_the_declared_ones():
    series, _ = ds.series_for(_row(), _frame())
    assert list(series) == ["closes", "exit_bar", "last_bar", "stale", "entry",
                            "stop", "tp1", "tp2", "exit", "exit_date"]


def test_entry_and_exit_bars_follow_utc_dates_across_a_local_date_mismatch():
    """22:00 New York on Mon 08-03 is Tue 08-04 in UTC, so the entry bar is
    08-04. A close at 01:00 UTC Saturday (Friday evening in New York) has
    calendar day 08-08, a Saturday: the exit bar is the last bar on or
    before it, Fri 08-07."""
    row = _row(opened_at="2026-08-03T22:00:00-04:00",
               closed_at="2026-08-08T01:00:00+00:00", day="2026-08-08")
    series, _ = ds.series_for(row, _frame())
    assert series["closes"][0]["date"] == "2026-07-30"      # i11 - 3 = i8
    assert series["exit_date"] == "2026-08-07"
    assert series["exit_bar"] == 6                          # i14 - i8
    assert series["closes"][-1]["date"] == "2026-08-12"     # i14 + 3 = i17


def test_ticks_are_the_recorded_prices():
    series, _ = ds.series_for(_row(), _frame())
    assert (series["entry"], series["stop"], series["tp1"], series["tp2"],
            series["exit"]) == (110.0, 105.0, 120.0, None, 112.0)


def test_ticks_are_nulled_when_entry_lies_outside_the_window_range():
    """A split or adjustment since entry: the recorded prices no longer sit
    on the adjusted closes, so only the close line is drawn."""
    series, _ = ds.series_for(_row(entry_price=55.0), _frame())
    assert (series["entry"], series["stop"], series["tp1"], series["tp2"],
            series["exit"]) == (None, None, None, None, None)
    assert len(series["closes"]) == 9


def test_a_missing_entry_price_nulls_every_tick():
    series, _ = ds.series_for(_row(entry_price=None), _frame())
    assert series["entry"] is None and series["exit"] is None


def test_a_cache_that_ends_before_the_exit_is_stale_and_stops_early():
    series, _ = ds.series_for(_row(), _frame(12))         # last bar i11 = 08-04
    assert series["stale"] is True
    assert series["last_bar"] == "2026-08-04"
    assert series["exit_date"] == "2026-08-04"
    assert series["closes"][-1]["date"] == "2026-08-04"
    assert series["exit_bar"] == len(series["closes"]) - 1


def test_no_frame_or_no_bars_in_the_window_is_none():
    assert ds.series_for(_row(), None) == (None, False)
    assert ds.series_for(_row(), _frame().iloc[0:0]) == (None, False)
    assert ds.series_for(_row(), _frame(5)) == (None, False)          # ends 07-24, before entry
    assert ds.series_for(_row(opened_at=None), _frame()) == (None, False)
    assert ds.series_for(_row(day="2026-07-31"), _frame()) == (None, False)  # exit before entry


def test_a_series_over_400_bars_keeps_the_last_400():
    frame = make_ohlcv([100.0] * 500, start="2024-01-01")
    dates = list(frame.index.strftime("%Y-%m-%d"))
    row = _row(opened_at=dates[0] + "T14:00:00+00:00", day=dates[495],
               closed_at=dates[495] + "T20:00:00+00:00", entry_price=100.0)
    series, cut = ds.series_for(row, frame)
    assert cut is True
    assert len(series["closes"]) == ds.SPARK_MAX_BARS
    assert series["closes"][0]["date"] == dates[99]
    assert series["closes"][-1]["date"] == dates[498]
    assert series["exit_bar"] == 396


def test_payload_takes_rows_in_close_order_and_caps_at_50():
    rows = [_row(trade_id=f"{i:016d}", closed_at=f"2026-08-05T20:{i:02d}:00+00:00")
            for i in range(ds.SPARK_MAX_ROWS + 1)]
    series, truncated = ds.sparklines_payload(list(reversed(rows)), lambda t: _frame())
    assert truncated is True
    assert len(series) == ds.SPARK_MAX_ROWS
    assert f"{0:016d}:0" in series
    assert f"{ds.SPARK_MAX_ROWS:016d}:0" not in series      # the latest close is the one cut


def test_payload_without_a_cut_is_not_truncated():
    series, truncated = ds.sparklines_payload([_row()], lambda t: _frame())
    assert truncated is False
    assert series[KEY]["exit_date"] == "2026-08-05"


def test_a_spot_metal_is_null_and_never_loaded():
    calls = []
    rows = [_row(ticker="XAUUSD"), _row(trade_id="b" * 16, ticker="AAPL")]
    series, _ = ds.sparklines_payload(rows, lambda t: calls.append(t) or _frame())
    assert series[KEY] is None
    assert series["b" * 16 + ":0"] is not None
    assert calls == ["AAPL"]


def test_a_missing_cache_file_is_null():
    series, truncated = ds.sparklines_payload([_row()], lambda t: None)
    assert series == {KEY: None}
    assert truncated is False


def test_reads_a_real_cached_csv_through_load_normalized(tmp_path):
    """Cache miss on the first read (CSV parse), hit on the second; both
    produce the same series."""
    from swingbot.core.marketdata import data_store
    base = str(tmp_path / "market_data")
    data_store.save_to_disk(_frame(), "AAPL", "daily", base_dir=base)

    def loader(ticker):
        return data_store.load_normalized(ticker, "daily", base_dir=base)

    first, _ = ds.sparklines_payload([_row()], loader)
    second, _ = ds.sparklines_payload([_row()], loader)
    assert first[KEY]["exit_date"] == "2026-08-05"
    assert first == second


def test_the_input_frame_is_not_mutated():
    frame = _frame()
    before = frame.copy(deep=True)
    ds.series_for(_row(), frame)
    pd.testing.assert_frame_equal(frame, before)


def test_truncating_the_frame_three_bars_past_the_exit_changes_nothing():
    """No-lookahead truncation test: bars after exit + 3 never reach the
    series. Only `last_bar`/`stale` describe the frame's end, so they move."""
    frame = _frame()
    full, _ = ds.series_for(_row(), frame)
    cut, _ = ds.series_for(_row(), frame.iloc[:12 + ds.SPARK_PAD_BARS + 1])  # exit i12
    drop = ("last_bar", "stale")
    assert {k: v for k, v in full.items() if k not in drop} == \
        {k: v for k, v in cut.items() if k not in drop}
