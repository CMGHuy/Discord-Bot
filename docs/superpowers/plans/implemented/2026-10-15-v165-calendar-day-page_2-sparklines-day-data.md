# v165 P&L calendar day page. Implementation Plan, part 2: sparklines and day data (CD6..CD9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `grep -n "^### Task CD7:" -A 300 docs/superpowers/plans/2026-10-15-v165-calendar-day-page_2-sparklines-day-data.md`.

**Spec:** [`docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md`](../specs/2026-10-15-v165-calendar-day-page-design.md) (this part covers D4 sparklines, the data half of D5, and the D7 copy constants)
**Index:** [`2026-10-15-v165-calendar-day-page_0-index.md`](2026-10-15-v165-calendar-day-page_0-index.md) — Global Constraints, Review Focus, `## Parallelisation`, the task ledger (every cross-task name below is fixed there) and `## Where to work` (`$WT` = the worktree, `$R` = the main tree; never `cd`, use absolute paths).

Order inside this part: CD6 is the last task of the Python chain (after CD5). CD7 and CD8 may start right after CD1 and run in parallel with each other and with CD2–CD6. **CD9 (needs CD7 and CD8) lives in [`_2b-day-store.md`](2026-10-15-v165-calendar-day-page_2b-day-store.md)**: with it this file would pass the 1500-line cap, and a task is never compressed to fit.

# Phase B: sparklines (end of the Python chain)

### Task CD6: D4 sparklines: pure window module and `GET /calendar/pnl/day/sparklines`

**Model:** opus — window clip is no-lookahead territory; crosses `analytics` and `marketdata`

**Files:**
- Create: `swingbot/core/analytics/day_sparklines.py`
- Create: `tests/analytics/test_day_sparklines.py`
- Modify: `swingbot/admin/api_v1/calendar.py` (append one route after `calendar_pnl_day`)
- Modify: `tests/admin/test_api_v1_calendar.py` (append one fixture and the sparkline route tests at the end of the file)

**Interfaces:**
- Consumes (CD2, `pnl_calendar` rows): `trade_id`, `leg_index`, `ticker`, `opened_at`, `closed_at`, `day`, `entry_price`, `stop_price`, `tp1`, `tp2`, `exit_price`. Existing: `pnl_calendar.load_rows()`, `pnl_calendar.filter_rows(rows, *, strategy, horizon)`, `api_v1/calendar.py` `_reject_unknown_params()`, `_date_param()`, `_filter_args()`; `swingbot.core.marketdata.spot_metals.is_spot_metal(symbol) -> bool` (`spot_metals.py:53`); `swingbot.core.marketdata.data_store.load_normalized(ticker, interval, base_dir=DATA_DIR) -> pd.DataFrame | None` (`data_store.py:285`).
- Produces (consumed by CD7's TypeScript types and by CD9/CD10/CD11 through the HTTP response):
  - `day_sparklines.SPARK_MAX_ROWS = 50`, `SPARK_MAX_BARS = 400`, `SPARK_PAD_BARS = 3`
  - `series_key(row: dict) -> str` → `"<trade_id>:<leg_index>"`
  - `series_for(row: dict, frame: pd.DataFrame | None) -> tuple[dict | None, bool]` (series, bar-cut flag)
  - `sparklines_payload(day_rows: list[dict], loader: Callable[[str], pd.DataFrame | None]) -> tuple[dict[str, dict | None], bool]`
  - series dict, keys exactly in this order: `{"closes": [{"date": "YYYY-MM-DD", "close": float}], "exit_bar": int, "last_bar": str, "stale": bool, "entry", "stop", "tp1", "tp2", "exit": float | None, "exit_date": str}`
  - route `GET /api/v1/calendar/pnl/day/sparklines?date=&strategy=&horizon=` → `{as_of, date, truncated, series}`. A day with no rows is a **200 with `series: {}`** (the page asks only after the day route answered 200, so a 404 here would only add a second empty-state path).

**Rules this task implements (spec D4):**
- Bars come **only** from the injected loader; the route passes `lambda t: data_store.load_normalized(t, "daily")` — the same injection `swingbot/core/analytics/gate_counterfactual_inputs.py:179` uses. The pure module imports no `data_store`, no fetcher, no `backtest_cache`, no `load_from_disk` (known-traps § Two OHLCV caches).
- Spot metal (`spot_metals.is_spot_metal`, checked **before** the loader is called), missing file (`None`), missing `opened_at`, or a window with no bars → `None`.
- Entry bar = first bar whose (normalised) date is on/after the **UTC date** of `opened_at`; exit bar = last bar on/before the row's `day` (already the UTC-date `day_of(closed_at)`). Exit bar before entry bar → `None`.
- Window = `[entry_i − 3, exit_i + 3]`, clipped to the frame, **never later than exit + 3** (no "today" price on a historical card — no-lookahead). `exit_bar` is the exit bar's index inside the returned `closes`; the 3 bars after it are context the page draws dimmed.
- Ticks = the recorded row prices (`entry_price`, `stop_price` = final stop, `tp1`, `tp2`, `exit_price`). When `entry_price` is `None` or outside the window's `[min Low, max High]`, **all five** are `None`.
- `last_bar` = the frame's last bar date; `stale = last_bar < row["day"]`. `exit_date` = the exit bar's date (where the exit dot sits).
- Caps: rows sorted by `closed_at` (missing sorts first), first 50 kept, rows beyond the cap get no key; a window over 400 bars keeps the **last** 400 (the exit end). Either cut → `truncated: true`.
- Only the slice is serialised; the full frame is a local that goes out of scope per row (no per-ticker memo — a memo would retain full frames).

- [ ] **Step 1: Write the failing pure-module tests**

Create `tests/analytics/test_day_sparklines.py` (suite `edge-analytics`, no `suites.toml` change):

```python
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_day_sparklines.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.analytics.day_sparklines'`.

- [ ] **Step 3: Write the pure module**

Create `swingbot/core/analytics/day_sparklines.py`:

```python
"""v165 D4 -- price sparklines for the calendar day page.

Spec: docs/superpowers/specs/2026-10-15-v165-calendar-day-page-design.md (D4).

Pure: bars arrive through an injected `loader(ticker) -> frame | None`. The
admin route passes `data_store.load_normalized(ticker, "daily")` -- the
process-cached `market_data/` reader -- and nothing else. This module never
fetches, never reads `backtest_cache`, never calls `load_from_disk`
(known-traps: two OHLCV caches).

**No lookahead on a historical card:** the window ends 3 bars after the exit
bar, never at "today". Those 3 bars are context the page draws dimmed; the
response marks where the exit is (`exit_bar`).
"""
from __future__ import annotations

import datetime as dt
from typing import Callable

import pandas as pd

from swingbot.core.marketdata import spot_metals

SPARK_MAX_ROWS = 50
SPARK_MAX_BARS = 400
SPARK_PAD_BARS = 3

#: series field -> calendar row field. Order is the response's key order.
_TICKS = (("entry", "entry_price"), ("stop", "stop_price"), ("tp1", "tp1"),
          ("tp2", "tp2"), ("exit", "exit_price"))


def series_key(row: dict) -> str:
    """`"<trade_id>:<leg_index>"` -- one key per calendar row, legs apart."""
    return f"{row['trade_id']}:{row['leg_index']}"


def _utc_date(stamp: str | None) -> str | None:
    """`YYYY-MM-DD` of an ISO stamp in UTC; a naive stamp is read as UTC."""
    if not stamp:
        return None
    try:
        moment = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).date().isoformat()


def _bounds(index: pd.DatetimeIndex, opened: str, day: str) -> tuple[int, int] | None:
    """(entry_i, exit_i): first bar on/after `opened`, last bar on/before `day`.

    Bars are keyed by exchange date (the frame's tz-naive daily index,
    normalised so a stray time-of-day cannot push a bar past its date)."""
    days = index.normalize()
    entry_i = int(days.searchsorted(pd.Timestamp(opened), side="left"))
    exit_i = int(days.searchsorted(pd.Timestamp(day), side="right")) - 1
    if entry_i >= len(days) or exit_i < entry_i:
        return None
    return entry_i, exit_i


def _ticks(row: dict, window: pd.DataFrame) -> dict:
    """The recorded prices, or all None when entry no longer sits on the bars
    (a split or adjustment since entry) -- then only the close line draws."""
    entry = row.get("entry_price")
    low, high = float(window["Low"].min()), float(window["High"].max())
    if entry is None or not low <= float(entry) <= high:
        return {name: None for name, _ in _TICKS}
    return {name: row.get(field) for name, field in _TICKS}


def series_for(row: dict, frame: pd.DataFrame | None) -> tuple[dict | None, bool]:
    """One row's series and whether the 400-bar cap cut it."""
    opened, day = _utc_date(row.get("opened_at")), row.get("day")
    if frame is None or frame.empty or opened is None or not day:
        return None, False
    bounds = _bounds(frame.index, opened, day)
    if bounds is None:
        return None, False
    entry_i, exit_i = bounds
    start = max(0, entry_i - SPARK_PAD_BARS)
    stop = min(len(frame), exit_i + SPARK_PAD_BARS + 1)
    cut = stop - start > SPARK_MAX_BARS
    if cut:
        start = stop - SPARK_MAX_BARS
    window = frame.iloc[start:stop]
    dates = list(window.index.strftime("%Y-%m-%d"))
    last_bar = frame.index[-1].strftime("%Y-%m-%d")
    return {
        "closes": [{"date": d, "close": round(float(c), 4)}
                   for d, c in zip(dates, window["Close"])],
        "exit_bar": exit_i - start,
        "last_bar": last_bar,
        "stale": last_bar < day,
        **_ticks(row, window),
        "exit_date": dates[exit_i - start],
    }, cut


def _series_or_none(row: dict, loader: Callable[[str], pd.DataFrame | None]) -> tuple[dict | None, bool]:
    ticker = (row.get("ticker") or "").strip()
    # Spot metals are never cached under their own name (v109): decided by
    # the shared helper, before any load.
    if not ticker or spot_metals.is_spot_metal(ticker):
        return None, False
    return series_for(row, loader(ticker))


def sparklines_payload(
    day_rows: list[dict], loader: Callable[[str], pd.DataFrame | None],
) -> tuple[dict[str, dict | None], bool]:
    """`({series_key: series | None}, truncated)` for one day's rows.

    Deterministic caps: rows in `closed_at` order, the first 50 kept; a
    window over 400 bars keeps its last 400. Either cut sets `truncated`."""
    ordered = sorted(day_rows, key=lambda r: r.get("closed_at") or "")
    truncated = len(ordered) > SPARK_MAX_ROWS
    series: dict[str, dict | None] = {}
    for row in ordered[:SPARK_MAX_ROWS]:
        value, cut = _series_or_none(row, loader)
        series[series_key(row)] = value
        truncated = truncated or cut
    return series, truncated
```

- [ ] **Step 4: Run the pure tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_day_sparklines.py`
Expected: PASS (17 tests).

- [ ] **Step 5: Write the failing route tests**

Append to the end of `tests/admin/test_api_v1_calendar.py`. The route reads bars only through `data_store.load_normalized`; the tests swap that module attribute — the established pattern of `tests/analytics/test_runner_path.py:162` and `tests/analytics/test_gate_counterfactual_inputs.py:225` (`monkeypatch.setattr(data_store, "load_normalized", ...)`). Pointing a `DATA_DIR` elsewhere would not work: `load_normalized`'s `base_dir` default is bound at definition time. The fixture also makes `load_from_disk` and `fetch_interval_data` fail the test, so a route that reached past the cached loader is caught.

```python
# ---- v165 D4: GET /calendar/pnl/day/sparklines -----------------------------

_SPARK = "/api/v1/calendar/pnl/day/sparklines"


@pytest.fixture
def bars(monkeypatch):
    """Cached daily bars: AAPL has 30 flat bars from Mon 2026-07-20 (close
    100, High 101, Low 99); every other ticker is an uncached miss. Returns
    the list of (ticker, interval) loads the route made."""
    from swingbot.core.marketdata import data_store
    from tests.helpers import make_ohlcv

    calls = []

    def _load(ticker, interval):
        calls.append((ticker, interval))
        return make_ohlcv([100.0] * 30, start="2026-07-20") if ticker == "AAPL" else None

    def _never(*args, **kwargs):
        pytest.fail("the sparklines route may read bars only through load_normalized")

    monkeypatch.setattr(data_store, "load_normalized", _load)
    monkeypatch.setattr(data_store, "load_from_disk", _never)
    monkeypatch.setattr(data_store, "fetch_interval_data", _never)
    return calls


def test_sparklines_require_auth(client):
    assert_error(client.get(f"{_SPARK}?date=2026-08-03"), "auth", 401)


def test_sparklines_response_shape(seed, logged_in, bars):
    """`_trade` opens Sat 08-01 (entry bar Mon 08-03 = i10) and closes 08-03
    (exit bar i10): window i7..i13 = Wed 07-29..Wed 08-05."""
    seed(trades=[_trade("a" * 16)])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03").get_json()
    assert_shape(body, {"as_of": str, "date": str, "truncated": bool, "series": dict})
    assert body["date"] == "2026-08-03"
    assert body["truncated"] is False
    series = body["series"]["a" * 16 + ":0"]
    assert_shape(series, {
        "closes": list, "exit_bar": int, "last_bar": str, "stale": bool,
        "entry": NULLABLE_NUMBER, "stop": NULLABLE_NUMBER, "tp1": NULLABLE_NUMBER,
        "tp2": NULLABLE_NUMBER, "exit": NULLABLE_NUMBER, "exit_date": str,
    }, where="series")
    assert_shape(series["closes"][0], {"date": str, "close": NULLABLE_NUMBER},
                 where="close")
    assert series["closes"][0]["date"] == "2026-07-29"
    assert series["closes"][-1]["date"] == "2026-08-05"
    assert (series["exit_bar"], series["exit_date"]) == (3, "2026-08-03")
    assert (series["entry"], series["stop"], series["tp1"], series["tp2"],
            series["exit"]) == (100.0, 95.0, 120.0, None, 110.0)
    assert series["stale"] is False
    assert bars == [("AAPL", "daily")]


def test_a_spot_metal_sparkline_is_null_without_a_load(seed, logged_in, bars):
    seed(trades=[{**_trade("a" * 16), "ticker": "XAUUSD"}])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03").get_json()
    assert body["series"] == {"a" * 16 + ":0": None}
    assert bars == []


def test_an_uncached_ticker_sparkline_is_null(seed, logged_in, bars):
    seed(trades=[{**_trade("a" * 16), "ticker": "MSFT"}])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03").get_json()
    assert body["series"] == {"a" * 16 + ":0": None}
    assert bars == [("MSFT", "daily")]


def test_sparklines_respect_the_strategy_filter(seed, logged_in, bars):
    seed(trades=[
        _trade("a" * 16, sources=("EMA20",)),
        _trade("b" * 16, closed_at="2026-08-03T21:00:00+00:00", sources=("VWAP",)),
    ])
    body = logged_in.get(f"{_SPARK}?date=2026-08-03&strategy=VWAP").get_json()
    assert list(body["series"]) == ["b" * 16 + ":0"]


def test_sparklines_for_a_day_with_no_closes_are_an_empty_200(seed, logged_in, bars):
    seed(trades=[_trade("a" * 16)])
    response = logged_in.get(f"{_SPARK}?date=2026-08-09")
    assert response.status_code == 200
    body = response.get_json()
    assert (body["series"], body["truncated"]) == ({}, False)
    assert bars == []


def test_sparklines_reject_a_bad_date_or_an_unknown_parameter(seed, logged_in, bars):
    seed(trades=[_trade("a" * 16)])
    assert_error(logged_in.get(_SPARK), "invalid", 400)
    assert_error(logged_in.get(f"{_SPARK}?date=2026-08"), "invalid", 400)
    assert_error(logged_in.get(f"{_SPARK}?date=2026-02-30"), "invalid", 400)
    assert_error(logged_in.get(f"{_SPARK}?date=2026-08-03&tickr=AAPL"), "invalid", 400)
```

- [ ] **Step 6: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: the seven new sparkline tests FAIL (the route does not exist yet, so Flask answers 404 and `assert_error`/`assert_shape`/the status check fail); every pre-existing test still passes.

- [ ] **Step 7: Add the route**

Append to `swingbot/admin/api_v1/calendar.py`, after `calendar_pnl_day` (and after any helper CD5 placed there):

```python
@api_v1.route("/calendar/pnl/day/sparklines", methods=["GET"])
@require_auth
def calendar_pnl_day_sparklines():
    """Daily-close sparklines for one day's rows -- the day page's cards.

    Separate from `/calendar/pnl/day` so the tiles render before any CSV is
    parsed. Bars come only from `data_store.load_normalized` (the bounded,
    process-cached `market_data/` reader): never a network fetch, never
    `backtest_cache`, never `load_from_disk`. Cost per view: one more
    `load_rows()` plus <= 50 cached frame loads; a short-TTL memo of
    `load_rows` is the named follow-up if it ever shows in admin latency.

    A day with no rows is an empty 200, not a 404: the page asks only after
    the day route answered, and an empty map already means "nothing to draw".
    """
    from swingbot.core.analytics import day_sparklines as ds
    from swingbot.core.analytics import pnl_calendar as pc
    from swingbot.core.marketdata import data_store

    _reject_unknown_params()
    date = _date_param()
    strategy, horizon = _filter_args()

    rows = pc.filter_rows(pc.load_rows(), strategy=strategy, horizon=horizon)
    day_rows = [r for r in rows if r["day"] == date]
    # Looked up on the module at call time, so the loader is the one
    # function a test (or a future cache layer) swaps.
    series, truncated = ds.sparklines_payload(
        day_rows, lambda ticker: data_store.load_normalized(ticker, "daily"))

    return jsonify({
        "as_of": dt.datetime.now(dt.timezone.utc).isoformat(),
        "date": date,
        "truncated": truncated,
        "series": series,
    })
```

`_FILTERS` is unchanged: it already allows `date`, `strategy`, `horizon` (and `month`, harmlessly).

- [ ] **Step 8: Run the route and module tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py`
Expected: PASS (all, including the seven new ones).
Run: `python $WT/scripts/dev/testrun.py file tests/analytics/test_day_sparklines.py`
Expected: PASS.

- [ ] **Step 9: Complexity check**

Run: `python -m radon cc -s -n C $WT/swingbot/core/analytics/day_sparklines.py $WT/swingbot/admin/api_v1/calendar.py`
Expected: no output (every function below C).

- [ ] **Step 10: Commit**

```bash
git -C $WT add swingbot/core/analytics/day_sparklines.py tests/analytics/test_day_sparklines.py swingbot/admin/api_v1/calendar.py tests/admin/test_api_v1_calendar.py
git -C $WT commit -m "feat(calendar): day sparklines from cached daily bars, clipped 3 bars past the exit

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.

# Phase C: frontend day data (runs beside CD2–CD6 once CD1 is done)

### Task CD7: Frontend models and API client for the day page

**Model:** haiku — types and one client method fully fixed by this ledger

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`CalendarTrade`, `CalendarDayTrades`, new types right after `CalendarDayTrades`)
- Modify: `frontend/src/app/api/api-client.ts` (imports; one method after `calendarPnlDay`)
- Modify: `frontend/src/app/api/api-client.spec.ts` (one `it` at the end of the `ApiClient — scope and analytics` describe)
- Modify: `frontend/src/app/workspaces/calendar/calendar.spec.ts` (the `TRADE` fixture and the `openDay` flush body)

**Interfaces:**
- Consumes: the response shapes fixed by CD2 (row fields), CD3 (`context`), CD4 (`breakdown`), CD6 (sparklines route). No Python code.
- Produces (exact; CD9–CD13 import these names from `frontend/src/app/api/models.ts` and `ApiClient`):
  - `CalendarTrade` gains `entry_price, exit_price, stop_price, tp1, tp2, shares, held_hours, return_pct: number | null` and `exit_reason: string`
  - `DayDelta {pnl_amount: number | null; r: number | null}`
  - `DayContext {percentile: number | null; history_days: number; vs_avg_day: DayDelta; vs_weekday_avg: DayDelta}`
  - `DayBreakdownRow {key: string; n: number; pnl_amount: number | null; r: number | null; win_rate: number | null}`
  - `DayBreakdownDimension = 'strategy' | 'horizon' | 'direction' | 'exit_reason'`
  - `DayBreakdown = Record<DayBreakdownDimension, DayBreakdownRow[]>`
  - `CalendarDayTrades` gains `context: DayContext; breakdown: DayBreakdown`
  - `SparkClose {date: string; close: number}`
  - `SparkSeries {closes: SparkClose[]; exit_bar: number; last_bar: string; stale: boolean; entry, stop, tp1, tp2, exit: number | null; exit_date: string}`
  - `CalendarDaySparklines {as_of: string; date: string; truncated: boolean; series: Record<string, SparkSeries | null>}`
  - `ApiClient.calendarPnlDaySparklines(query: {date: string; strategy?: string; horizon?: string}): Observable<CalendarDaySparklines>`

Frontend runs (from `## Where to work` in the index): `npm --prefix $WT/frontend run test -- --watch=false --include='<spec glob>'`; if the builder rejects `--include`, run `npm --prefix $WT/frontend run test -- --watch=false`. A `Timeout waiting for worker` is a known flake: re-run once.

- [ ] **Step 1: Write the failing client test**

In `frontend/src/app/api/api-client.spec.ts`, add this `it` as the last test inside `describe('ApiClient — scope and analytics', ...)` (immediately before the file's final `});`):

```ts
  it('calendarPnlDaySparklines GETs /calendar/pnl/day/sparklines with the date and only the set filters', () => {
    let got: unknown;
    api.calendarPnlDaySparklines({ date: '2026-08-03', strategy: 'VWAP' }).subscribe((r) => (got = r));
    const req = http.expectOne((r) => r.url.endsWith('/calendar/pnl/day/sparklines'));
    expect(req.request.method).toBe('GET');
    expect(req.request.params.get('date')).toBe('2026-08-03');
    expect(req.request.params.get('strategy')).toBe('VWAP');
    expect(req.request.params.has('horizon')).toBe(false);
    const body = {
      as_of: '2026-08-10T12:00:00Z',
      date: '2026-08-03',
      truncated: false,
      series: { ['a'.repeat(16) + ':0']: null },
    };
    req.flush(body);
    expect(got).toEqual(body);
  });
```

- [ ] **Step 2: Extend the calendar spec fixtures to the new row and day shape**

In `frontend/src/app/workspaces/calendar/calendar.spec.ts`, replace the `TRADE` fixture with (same values as before plus the D1 fields; prices match the Python `_trade` helper):

```ts
const TRADE: CalendarTrade = {
  trade_id: 'a'.repeat(16),
  ticker: 'AAPL',
  strategy: 'EMA20',
  horizon: '4w',
  direction: 'bullish',
  day: '2026-08-03',
  closed_at: '2026-08-03T20:00:00+00:00',
  outcome: 'win',
  pnl_amount: 50,
  r_multiple: 2,
  mfe_r: 2.4,
  mae_r: -0.3,
  exit_efficiency: 83,
  tags: ['clean-exit'],
  auto_lesson: 'Held to target.',
  plan_id: null,
  opened_at: '2026-08-01T14:30:00+00:00',
  leg_index: 0,
  leg_total: 1,
  entry_price: 100,
  exit_price: 110,
  stop_price: 95,
  tp1: 120,
  tp2: null,
  shares: 10,
  held_hours: 53.5,
  return_pct: 10,
  exit_reason: 'tp1',
};
```

and in `openDay` (the `describe('Calendar day drawer', ...)` helper) replace the `.flush({...})` body with one that carries the two new fields:

```ts
      .flush({ as_of: '2026-08-10T12:00:00Z', date: '2026-08-03', trades, trade_count: trades.length,
        winners: 0, losers: 0, total_r: null, total_ccy: null,
        win_rate: null, avg_trade_r: null, worst_drawdown_r: null,
        contributors: [], detractors: [],
        context: { percentile: null, history_days: 0,
          vs_avg_day: { pnl_amount: null, r: null },
          vs_weekday_avg: { pnl_amount: null, r: null } },
        breakdown: { strategy: [], horizon: [], direction: [], exit_reason: [] } });
```

- [ ] **Step 3: Run both specs to verify they fail**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/api/api-client.spec.ts' --include='src/app/workspaces/calendar/calendar.spec.ts'`
Expected: FAIL at compile — `Property 'calendarPnlDaySparklines' does not exist on type 'ApiClient'` and `Object literal may only specify known properties, and 'entry_price' does not exist in type 'CalendarTrade'`.

- [ ] **Step 4: Add the types**

In `frontend/src/app/api/models.ts`, append these members to `interface CalendarTrade`, after `leg_total: number;`:

```ts
  /** v165 D1 -- read from the leg part itself, never re-derived. Every
   *  figure is null when its input is missing (never 0). */
  entry_price: number | null;
  /** The leg's own exit for a leg row, the trade exit for a whole trade. */
  exit_price: number | null;
  /** The final recorded stop (a trailed or break-even runner's stop moved). */
  stop_price: number | null;
  tp1: number | null;
  tp2: number | null;
  /** Leg-scaled for a leg row. */
  shares: number | null;
  /** Null when either stamp is missing or the close precedes the open. */
  held_hours: number | null;
  /** Signed by direction: a short that fell is positive. Null on a missing or zero entry. */
  return_pct: number | null;
  /** One of metrics `EXIT_REASONS` (tp1, runner_tp2, runner_trail, runner_be,
   *  stop, scratch, timeout, reversed, other). */
  exit_reason: string;
```

Replace `interface CalendarDayTrades` with this version (two new members at the end) and add the new types directly after it:

```ts
export interface CalendarDayTrades {
  /** Instant the server composed this selected-day drill-down. */
  as_of: string;
  date: string;
  trades: CalendarTrade[];
  /** Summary fields are composed from exactly the same filtered rows as
   *  `trades`, so the pane cannot disagree with its drill-down list. */
  trade_count: number;
  winners: number;
  losers: number;
  total_r: number | null;
  total_ccy: number | null;
  win_rate: number | null;
  avg_trade_r: number | null;
  worst_drawdown_r: number | null;
  contributors: Array<{ ticker: string | null; r: number }>;
  detractors: Array<{ ticker: string | null; r: number }>;
  /** v165 D2 -- this day against the OTHER trading days under the filter. */
  context: DayContext;
  /** v165 D3 -- exactly the rows in `trades`, grouped four ways. */
  breakdown: DayBreakdown;
}

/** A difference from a reference day. Null when either side has no figure. */
export interface DayDelta {
  pnl_amount: number | null;
  r: number | null;
}

/** v165 D2. `percentile` is null below 20 other trading days (the page
 *  says why with `history_days`); the day is never in its own reference set. */
export interface DayContext {
  percentile: number | null;
  /** Other trading days with a non-null net P&L. */
  history_days: number;
  vs_avg_day: DayDelta;
  vs_weekday_avg: DayDelta;
}

/** One group of a day's rows. `win_rate` is 0-100 and null for a group with
 *  no decided rows; a null key arrives as `"unknown"`. */
export interface DayBreakdownRow {
  key: string;
  n: number;
  pnl_amount: number | null;
  r: number | null;
  win_rate: number | null;
}

export type DayBreakdownDimension = 'strategy' | 'horizon' | 'direction' | 'exit_reason';

/** Each dimension sorted by P&L descending, nulls last. */
export type DayBreakdown = Record<DayBreakdownDimension, DayBreakdownRow[]>;

export interface SparkClose {
  date: string;
  close: number;
}

/** v165 D4. Daily closes from 3 bars before entry to at most 3 bars after
 *  the exit bar (`exit_bar` indexes `closes`; later bars are context, drawn
 *  dimmed). Ticks are the recorded prices -- all null when entry no longer
 *  sits on the bars. `stale`: the cache ends before the exit day. */
export interface SparkSeries {
  closes: SparkClose[];
  exit_bar: number;
  last_bar: string;
  stale: boolean;
  entry: number | null;
  stop: number | null;
  tp1: number | null;
  tp2: number | null;
  exit: number | null;
  exit_date: string;
}

/** Keyed `"<trade_id>:<leg_index>"`. A null value: no cached bars (or a
 *  spot metal); a missing key: the row was past the 50-row cap. */
export interface CalendarDaySparklines {
  as_of: string;
  date: string;
  truncated: boolean;
  series: Record<string, SparkSeries | null>;
}
```

- [ ] **Step 5: Add the client method**

In `frontend/src/app/api/api-client.ts`, add `CalendarDaySparklines,` to the `from './models'` import list (alphabetical, directly before `CalendarDayTrades,`), and add this method directly after `calendarPnlDay(...)`:

```ts
  /** Daily-close sparklines for one day's rows (v165 D4). Fetched after the
   *  day itself so the page renders before any bar file is read. */
  calendarPnlDaySparklines(query: {
    date: string;
    strategy?: string;
    horizon?: string;
  }): Observable<CalendarDaySparklines> {
    let params = new HttpParams().set('date', query.date);
    if (query.strategy) params = params.set('strategy', query.strategy);
    if (query.horizon) params = params.set('horizon', query.horizon);
    return this.http.get<CalendarDaySparklines>(`${this.base}/calendar/pnl/day/sparklines`, {
      params,
    });
  }
```

- [ ] **Step 6: Run both specs to verify they pass**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/api/api-client.spec.ts' --include='src/app/workspaces/calendar/calendar.spec.ts'`
Expected: PASS (every existing test plus the new client test). If `--include` is rejected, run the whole frontend suite: `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

- [ ] **Step 7: Commit**

```bash
git -C $WT add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts frontend/src/app/workspaces/calendar/calendar.spec.ts
git -C $WT commit -m "feat(calendar-ui): day page types and the sparklines client call

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.

### Task CD8: Pure `month-context.ts` (rank, MTD, curve, prev/next, date validation, percentile view) and D7 copy constants

**Model:** sonnet — pure helpers with specs, rules fixed by D5/D7

**Files:**
- Create: `frontend/src/app/workspaces/calendar/day/month-context.ts`
- Create: `frontend/src/app/workspaces/calendar/day/month-context.spec.ts`
- Create: `frontend/src/app/workspaces/calendar/day/day-copy.ts`

**Interfaces:**
- Consumes: the existing `CalendarDay {date; net_pnl_amount: number | null; net_r: number | null; trade_count; win_rate}` from `frontend/src/app/api/models.ts` only (no CD7 type), so this task may run beside CD7.
- Produces (CD9, CD11, CD12, CD13 import these):
  - `month-context.ts`: `PERCENTILE_MIN_DAYS = 20`; `PERCENTILE_BAND_DAYS = 60`; `WIN_RATE_MIN_N = 5`; `isIsoDate(value: string | null | undefined): value is string`; `monthOf(date: string): string`; `adjacentTradingDay(days: CalendarDay[], date: string, step: 1 | -1): string | null`; `interface MonthContext {rank: number | null; rankOf: number; mtdPnl: number | null; mtdR: number | null; curve: {date: string; value: number}[]; dayIndex: number}`; `monthContext(days: CalendarDay[], date: string): MonthContext`; `ordinal(n: number): string`; `type PercentileView = {kind: 'hidden' | 'band' | 'exact'; text: string}`; `percentileView(percentile: number | null, historyDays: number): PercentileView`
  - `day-copy.ts`: `PAPER_CAPTION`, `ONE_DAY_CAVEAT`, `R_TOOLTIP`, `FINAL_STOP_LABEL = 'final stop'`, `legsSampleNote(rows: number): string`

**Rules (spec D5, D7; index Global Constraints):**
- A **trading day** is a `days` entry with `trade_count > 0` (the grid omits empty days, the guard is belt and braces). Prev/next walk trading days by date, so they work from a date that is not in the list (a 404 day).
- **Rank** = 1 + the number of trading days with a strictly higher non-null `net_pnl_amount` (ties share a rank), among days with a non-null net; `rankOf` = that count ("3rd best of 14 days"). A null-net day has `rank: null` and is absent from `curve` (null is never 0).
- **MTD** = the sum of non-null `net_pnl_amount` / `net_r` over trading days on or before `date`, rounded to 2 dp; `null` when none is non-null. On the month's last trading day it equals the month `totals` (pinned below).
- **Curve** = running sum of non-null `net_pnl_amount` per trading day in date order; `dayIndex` = this day's index in it, `-1` when absent.
- **Percentile view** (page side of D2/D7): `historyDays < 20` → hidden, text `Only N trading days so far — percentile hidden`; null percentile with enough days → hidden, text `—`; `historyDays < 60` → band (`Bottom|Middle|Top third of N other trading days · small sample`); else exact (`87th percentile of 212 other trading days`).
- Dates stay strings (the `calendar.helpers.ts` rule: never a `Date` round trip); `isIsoDate` uses `Date.UTC` only to learn a month's length.
- D7 copy is verbatim from the spec.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/workspaces/calendar/day/month-context.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import { CalendarDay } from '../../../api/models';
import {
  FINAL_STOP_LABEL,
  ONE_DAY_CAVEAT,
  PAPER_CAPTION,
  R_TOOLTIP,
  legsSampleNote,
} from './day-copy';
import {
  PERCENTILE_BAND_DAYS,
  PERCENTILE_MIN_DAYS,
  WIN_RATE_MIN_N,
  adjacentTradingDay,
  isIsoDate,
  monthContext,
  monthOf,
  ordinal,
  percentileView,
} from './month-context';

const day = (
  date: string,
  net: number | null,
  r: number | null,
  count = 1,
): CalendarDay => ({ date, net_pnl_amount: net, net_r: r, trade_count: count, win_rate: null });

/** Deliberately out of date order: the helpers must sort, not trust input. */
const AUGUST: CalendarDay[] = [
  day('2026-08-10', 120, 2.5),
  day('2026-08-03', 30, 1.2, 2),
  day('2026-08-05', -90, -1.8),
  day('2026-08-06', null, null),     // every row unpriced: a trading day with no net
  day('2026-08-07', 0, 0, 0),        // no closes: never a trading day
  day('2026-08-12', 30, 0.4),
];
/** What `/calendar/pnl?month=2026-08` would put in `totals` for AUGUST. */
const AUGUST_TOTALS = { net_pnl_amount: 90, net_r: 2.3 };

describe('isIsoDate', () => {
  it('accepts real calendar dates', () => {
    expect(isIsoDate('2026-08-03')).toBe(true);
    expect(isIsoDate('2024-02-29')).toBe(true);
    expect(isIsoDate('2026-12-31')).toBe(true);
  });

  it('rejects impossible, malformed and missing values', () => {
    for (const bad of ['2026-02-30', '2025-02-29', '2026-13-01', '2026-00-10', '2026-08-00',
                       '2026-8-3', 'abc', '', '2026-08-03T00:00', ' 2026-08-03']) {
      expect(isIsoDate(bad), bad).toBe(false);
    }
    expect(isIsoDate(null)).toBe(false);
    expect(isIsoDate(undefined)).toBe(false);
  });
});

describe('monthOf', () => {
  it('is the YYYY-MM prefix', () => {
    expect(monthOf('2026-08-03')).toBe('2026-08');
  });
});

describe('adjacentTradingDay', () => {
  it('steps to the neighbouring trading day', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-05', -1)).toBe('2026-08-03');
    expect(adjacentTradingDay(AUGUST, '2026-08-05', 1)).toBe('2026-08-06');
  });

  it('skips a day with no closes', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-06', 1)).toBe('2026-08-10');
    expect(adjacentTradingDay(AUGUST, '2026-08-10', -1)).toBe('2026-08-06');
  });

  it('works from a date that is not in the month (a 404 day)', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-04', -1)).toBe('2026-08-03');
    expect(adjacentTradingDay(AUGUST, '2026-08-04', 1)).toBe('2026-08-05');
  });

  it('is null at the month edge, so the store looks one month over', () => {
    expect(adjacentTradingDay(AUGUST, '2026-08-03', -1)).toBeNull();
    expect(adjacentTradingDay(AUGUST, '2026-08-12', 1)).toBeNull();
    expect(adjacentTradingDay([], '2026-08-12', 1)).toBeNull();
  });
});

describe('monthContext', () => {
  it('ranks the day among the month and accumulates month-to-date', () => {
    const ctx = monthContext(AUGUST, '2026-08-10');
    expect(ctx.rank).toBe(1);
    expect(ctx.rankOf).toBe(4);
    expect(ctx.mtdPnl).toBe(60);
    expect(ctx.mtdR).toBe(1.9);
    expect(ctx.curve).toEqual([
      { date: '2026-08-03', value: 30 },
      { date: '2026-08-05', value: -60 },
      { date: '2026-08-10', value: 60 },
      { date: '2026-08-12', value: 90 },
    ]);
    expect(ctx.dayIndex).toBe(2);
  });

  it('gives tied days the same rank', () => {
    expect(monthContext(AUGUST, '2026-08-03').rank).toBe(2);
    expect(monthContext(AUGUST, '2026-08-12').rank).toBe(2);
    expect(monthContext(AUGUST, '2026-08-05').rank).toBe(4);
  });

  it('MTD on the last trading day equals the month totals', () => {
    const ctx = monthContext(AUGUST, '2026-08-12');
    expect(ctx.mtdPnl).toBe(AUGUST_TOTALS.net_pnl_amount);
    expect(ctx.mtdR).toBe(AUGUST_TOTALS.net_r);
    expect(ctx.curve.at(-1)?.value).toBe(AUGUST_TOTALS.net_pnl_amount);
  });

  it('leaves a null-net day unranked and off the curve, never counted as 0', () => {
    const ctx = monthContext(AUGUST, '2026-08-06');
    expect(ctx.rank).toBeNull();
    expect(ctx.dayIndex).toBe(-1);
    expect(ctx.rankOf).toBe(4);
    expect(ctx.mtdPnl).toBe(-60);
  });

  it('is all-null on an empty month', () => {
    expect(monthContext([], '2026-08-03')).toEqual({
      rank: null, rankOf: 0, mtdPnl: null, mtdR: null, curve: [], dayIndex: -1,
    });
  });
});

describe('ordinal', () => {
  it('suffixes like English, teens included', () => {
    const cases: Array<[number, string]> = [
      [1, '1st'], [2, '2nd'], [3, '3rd'], [4, '4th'], [11, '11th'], [12, '12th'],
      [13, '13th'], [21, '21st'], [22, '22nd'], [23, '23rd'], [87, '87th'],
      [100, '100th'], [101, '101st'], [111, '111th'],
    ];
    for (const [n, text] of cases) expect(ordinal(n)).toBe(text);
  });
});

describe('percentileView', () => {
  it('shows the exact percentile with its N from 60 other days', () => {
    expect(percentileView(87.3, 212)).toEqual({
      kind: 'exact', text: '87th percentile of 212 other trading days',
    });
    expect(percentileView(50, PERCENTILE_BAND_DAYS).kind).toBe('exact');
  });

  it('shows only a third, flagged small sample, below 60 days', () => {
    expect(percentileView(50, 59)).toEqual({
      kind: 'band', text: 'Middle third of 59 other trading days · small sample',
    });
    expect(percentileView(10, PERCENTILE_MIN_DAYS).text).toContain('Bottom third');
    expect(percentileView(90, 30).text).toContain('Top third');
    expect(percentileView(100, 30).text).toContain('Top third');
  });

  it('hides the percentile below 20 days and says why', () => {
    expect(percentileView(null, 19)).toEqual({
      kind: 'hidden', text: 'Only 19 trading days so far — percentile hidden',
    });
    // Even if a figure arrived, the page never shows one on 19 days.
    expect(percentileView(55, 19).kind).toBe('hidden');
  });

  it('renders a dash when the day itself has no net', () => {
    expect(percentileView(null, 100)).toEqual({ kind: 'hidden', text: '—' });
  });

  it('pins the thresholds', () => {
    expect([PERCENTILE_MIN_DAYS, PERCENTILE_BAND_DAYS, WIN_RATE_MIN_N]).toEqual([20, 60, 5]);
  });
});

describe('D7 copy', () => {
  it('is the spec text, verbatim', () => {
    expect(PAPER_CAPTION).toBe('Paper trades · P&L before commissions, fees and tax');
    expect(ONE_DAY_CAVEAT).toBe('One day is not evidence of edge.');
    expect(R_TOOLTIP).toBe("R = the trade's initial risk (entry to stop). +1R made what was risked.");
    expect(FINAL_STOP_LABEL).toBe('final stop');
    expect(legsSampleNote(7)).toBe('7 rows · scale-out legs count separately');
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/month-context.spec.ts'`
Expected: FAIL at compile — `Cannot find module './month-context'` and `'./day-copy'`.

- [ ] **Step 3: Write the copy constants**

Create `frontend/src/app/workspaces/calendar/day/day-copy.ts`:

```ts
/* v165 D7 -- presentation honesty (financial-advisor seat). The spec's
 * exact strings, in one place, so the day page and the drawer cannot drift
 * apart and a spec asserts them verbatim. */

/** Top of the day page and the drawer's summary. `realized_pnl_amount`
 *  deducts no frictions (verified 2026-10-15). */
export const PAPER_CAPTION = 'Paper trades · P&L before commissions, fees and tax';

/** Fixed line in the "How this day compares" panel. */
export const ONE_DAY_CAVEAT = 'One day is not evidence of edge.';

/** Tooltip on every R figure's header. */
export const R_TOOLTIP = "R = the trade's initial risk (entry to stop). +1R made what was risked.";

/** The stop tick is the final recorded stop: a trailed or break-even
 *  runner's stop moved after entry. */
export const FINAL_STOP_LABEL = 'final stop';

/** The tiles' sample line when any row is a scale-out leg. */
export function legsSampleNote(rows: number): string {
  return `${rows} rows · scale-out legs count separately`;
}
```

- [ ] **Step 4: Write the month helpers**

Create `frontend/src/app/workspaces/calendar/day/month-context.ts`:

```ts
import { CalendarDay } from '../../../api/models';

/* v165 D5 -- everything the day page derives from the month response it
 * already holds (`/calendar/pnl?month=`), so rank, month-to-date and the
 * month line can never disagree with the grid. Pure and string-dated, the
 * `calendar.helpers.ts` rule: no Date round trip for a calendar date. */

/** Below this many other trading days the percentile is hidden (D2/D7). */
export const PERCENTILE_MIN_DAYS = 20;
/** Below this many the percentile shows only as a third, "small sample". */
export const PERCENTILE_BAND_DAYS = 60;
/** Breakdown rows with fewer rows than this grey out win% as `—`. */
export const WIN_RATE_MIN_N = 5;

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

/** A real calendar date in `YYYY-MM-DD`. `2026-02-30`, `2026-8-3` and
 *  `abc` are all false, so the page shows its empty state without asking. */
export function isIsoDate(value: string | null | undefined): value is string {
  const match = ISO_DATE.exec(value ?? '');
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const dayOfMonth = Number(match[3]);
  if (month < 1 || month > 12 || dayOfMonth < 1) return false;
  // Day 0 of the next month is this month's last day; UTC, so no DST edge.
  return dayOfMonth <= new Date(Date.UTC(year, month, 0)).getUTCDate();
}

export function monthOf(date: string): string {
  return date.slice(0, 7);
}

/** Days with at least one close, in date order. */
function tradingDays(days: CalendarDay[]): CalendarDay[] {
  return days
    .filter((d) => d.trade_count > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
}

/** The previous (`-1`) or next (`1`) trading day in `days`, or null at the
 *  month's edge. Comparison-based, so `date` need not be in `days`. */
export function adjacentTradingDay(
  days: CalendarDay[],
  date: string,
  step: 1 | -1,
): string | null {
  const dates = tradingDays(days).map((d) => d.date);
  if (step === 1) return dates.find((d) => d > date) ?? null;
  const before = dates.filter((d) => d < date);
  return before.length ? before[before.length - 1] : null;
}

export interface MonthContext {
  /** 1 = best day of the month; tied days share a rank. Null for a null-net day. */
  rank: number | null;
  /** Trading days with a non-null net -- the "of 14 days". */
  rankOf: number;
  mtdPnl: number | null;
  mtdR: number | null;
  /** Running month P&L per trading day with a net. */
  curve: { date: string; value: number }[];
  /** This day's index in `curve`, -1 when it is not on it. */
  dayIndex: number;
}

const round2 = (value: number): number => Math.round(value * 100) / 100;

function sumOrNull(values: Array<number | null>): number | null {
  const present = values.filter((v): v is number => v !== null);
  return present.length ? round2(present.reduce((a, b) => a + b, 0)) : null;
}

function rankOfDay(measured: CalendarDay[], date: string): number | null {
  const own = measured.find((d) => d.date === date);
  if (!own) return null;
  const net = own.net_pnl_amount as number;
  return 1 + measured.filter((d) => (d.net_pnl_amount as number) > net).length;
}

export function monthContext(days: CalendarDay[], date: string): MonthContext {
  const trading = tradingDays(days);
  const measured = trading.filter((d) => d.net_pnl_amount !== null);
  const upTo = trading.filter((d) => d.date <= date);
  let running = 0;
  const curve = measured.map((d) => {
    running = round2(running + (d.net_pnl_amount as number));
    return { date: d.date, value: running };
  });
  return {
    rank: rankOfDay(measured, date),
    rankOf: measured.length,
    mtdPnl: sumOrNull(upTo.map((d) => d.net_pnl_amount)),
    mtdR: sumOrNull(upTo.map((d) => d.net_r)),
    curve,
    dayIndex: curve.findIndex((p) => p.date === date),
  };
}

/** 1st, 2nd, 3rd, 4th, 11th, 12th, 13th, 21st ... */
export function ordinal(n: number): string {
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
  const suffix = ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th';
  return `${n}${suffix}`;
}

export type PercentileView = { kind: 'hidden' | 'band' | 'exact'; text: string };

const THIRDS = ['Bottom third', 'Middle third', 'Top third'] as const;

/** D2/D7: N always beside the figure; a band below 60 days; hidden below 20. */
export function percentileView(percentile: number | null, historyDays: number): PercentileView {
  if (historyDays < PERCENTILE_MIN_DAYS) {
    return { kind: 'hidden', text: `Only ${historyDays} trading days so far — percentile hidden` };
  }
  if (percentile === null) return { kind: 'hidden', text: '—' };
  if (historyDays < PERCENTILE_BAND_DAYS) {
    const third = THIRDS[Math.min(2, Math.floor(percentile / (100 / 3)))];
    return { kind: 'band', text: `${third} of ${historyDays} other trading days · small sample` };
  }
  return {
    kind: 'exact',
    text: `${ordinal(Math.round(percentile))} percentile of ${historyDays} other trading days`,
  };
}
```

- [ ] **Step 5: Run the spec to verify it passes**

Run: `npm --prefix $WT/frontend run test -- --watch=false --include='src/app/workspaces/calendar/day/month-context.spec.ts'`
Expected: PASS (all `describe` blocks). If `--include` is rejected, run `npm --prefix $WT/frontend run test -- --watch=false`, expected PASS.

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/workspaces/calendar/day/month-context.ts frontend/src/app/workspaces/calendar/day/month-context.spec.ts frontend/src/app/workspaces/calendar/day/day-copy.ts
git -C $WT commit -m "feat(calendar-ui): month context helpers and the D7 day-page copy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C $R status --short
```

Expected: the last command lists none of this task's files.

