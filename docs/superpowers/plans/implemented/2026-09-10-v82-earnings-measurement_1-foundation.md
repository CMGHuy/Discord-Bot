# v82 — Earnings Blackout Measurement, Part 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Index, Global Constraints and Parallelisation: `2026-09-10-v82-earnings-measurement_0-index.md`.

**Bump:** ui patch
**Edge:** expectancy

## Parallelisation (this part)

- **Sequential:** M1 → M2 (M2 imports M1's calendar).
- **After M2:** M3 may run in parallel with Part 2's M4 and M5 (disjoint files).

---

### Task M1: Session calendar

**Files:**
- Modify: `swingbot/core/market/session.py` (append after `session_date`, lines 55-57; add `bisect`/`functools`/`Iterable` imports at the top)
- Test: `tests/market/test_session_calendar.py` (new)

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `session.NYSE_HOLIDAYS: frozenset[dt.date]`, `session.NYSE_FIRST_DATE = dt.date(2018, 1, 1)`, `session.NYSE_LAST_YEAR_COVERED = 2030`
  - `class SessionCalendar(sessions: Iterable[dt.date])` with `from_bar_index(index) -> SessionCalendar` (classmethod), `__len__`, `first`, `last`, `sessions(start, end) -> list[dt.date]`, `is_session(d) -> bool`, `position_on_or_after(d) -> int | None`, `position_on_or_before(d) -> int | None`, `session_on_or_after(d) -> dt.date | None`, `next_session(d) -> dt.date | None`, `sessions_between(asof, target) -> int | None`
  - `nyse_calendar() -> SessionCalendar` (cached)

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_session_calendar.py`:

```python
"""v82 M1: the NYSE session calendar and the bar-index calendar."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from swingbot.core.market import opex
from swingbot.core.market.session import (
    NYSE_HOLIDAYS, NYSE_LAST_YEAR_COVERED, SessionCalendar, nyse_calendar,
)

D = dt.date.fromisoformat
ROOT = Path(__file__).resolve().parents[2]
SPY_CACHE = ROOT / "data" / "backtest_cache" / "SPY.csv"


def test_friday_to_monday_is_one_session():
    assert nyse_calendar().sessions_between(D("2026-09-11"), D("2026-09-14")) == 1


def test_same_session_is_zero():
    assert nyse_calendar().sessions_between(D("2026-09-14"), D("2026-09-14")) == 0


def test_thanksgiving_is_skipped():
    assert nyse_calendar().sessions_between(D("2026-11-25"), D("2026-11-27")) == 1


def test_weekend_asof_rolls_back_and_weekend_target_rolls_forward():
    cal = nyse_calendar()
    assert cal.sessions_between(D("2026-09-12"), D("2026-09-14")) == 1  # Sat reads as Fri
    assert cal.sessions_between(D("2026-09-11"), D("2026-09-13")) == 1  # Sun target reads as Mon


def test_next_session_skips_an_observed_holiday():
    assert nyse_calendar().next_session(D("2026-07-02")) == D("2026-07-06")


def test_is_session():
    cal = nyse_calendar()
    assert cal.is_session(D("2026-09-14"))
    assert not cal.is_session(D("2026-09-12"))      # Saturday
    assert not cal.is_session(D("2026-11-26"))      # Thanksgiving


def test_no_holiday_falls_on_a_weekend():
    assert all(d.weekday() < 5 for d in NYSE_HOLIDAYS)


def test_table_has_not_run_out():
    end = dt.date(NYSE_LAST_YEAR_COVERED, 12, 31)
    assert dt.date.today() <= end - dt.timedelta(days=90), (
        f"extend session.NYSE_HOLIDAYS and opex._FRIDAY_HOLIDAYS past {end}")


def test_opex_friday_table_agrees_with_the_nyse_table():
    expected = {d for d in NYSE_HOLIDAYS if d.weekday() == 4 and d.year >= 2026}
    assert opex._FRIDAY_HOLIDAYS == expected


def test_bar_index_constructor_and_empty_calendar():
    cal = SessionCalendar.from_bar_index(pd.DatetimeIndex(["2026-01-02", "2026-01-05"]))
    assert len(cal) == 2
    assert cal.first == D("2026-01-02") and cal.last == D("2026-01-05")
    assert cal.sessions_between(D("2026-01-02"), D("2026-01-05")) == 1
    assert cal.position_on_or_after(D("2026-01-06")) is None
    assert cal.position_on_or_before(D("2026-01-01")) is None
    with pytest.raises(ValueError):
        SessionCalendar([])


@pytest.mark.skipif(not SPY_CACHE.exists(),
                    reason="data/backtest_cache is untracked; runs on main (M7)")
def test_table_matches_the_cached_spy_bar_index():
    df = pd.read_csv(SPY_CACHE, index_col="Date", parse_dates=True)
    bars = SessionCalendar.from_bar_index(df.index)
    start, end = D("2018-06-01"), bars.last
    assert nyse_calendar().sessions(start, end) == bars.sessions(start, end)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_session_calendar.py`
Expected: FAIL — `ImportError: cannot import name 'NYSE_HOLIDAYS'`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/market/session.py`, change the imports block to:

```python
from __future__ import annotations

import bisect
import datetime as dt
import functools
from collections.abc import Iterable
from zoneinfo import ZoneInfo

from swingbot import config
```

Append after `session_date`:

```python
#: NYSE full-day closures, NYSE_FIRST_DATE's year through NYSE_LAST_YEAR_COVERED
#: (v82). Weekend holidays are observed on the adjacent weekday, except New
#: Year's Day on a Saturday, which NYSE does not observe. Includes the two
#: unscheduled national days of mourning (2018-12-05, 2025-01-09).
#: tests/market/test_session_calendar.py checks 2018-06 onward against the
#: cached SPY bar index and checks opex._FRIDAY_HOLIDAYS against this table.
#: MAINTENANCE: extend both tables together; the guard test fails 90 days
#: before this one runs out.
NYSE_HOLIDAYS: frozenset[dt.date] = frozenset(dt.date.fromisoformat(d) for d in (
    "2018-01-01", "2018-01-15", "2018-02-19", "2018-03-30", "2018-05-28",
    "2018-07-04", "2018-09-03", "2018-11-22", "2018-12-05", "2018-12-25",
    "2019-01-01", "2019-01-21", "2019-02-18", "2019-04-19", "2019-05-27",
    "2019-07-04", "2019-09-02", "2019-11-28", "2019-12-25",
    "2020-01-01", "2020-01-20", "2020-02-17", "2020-04-10", "2020-05-25",
    "2020-07-03", "2020-09-07", "2020-11-26", "2020-12-25",
    "2021-01-01", "2021-01-18", "2021-02-15", "2021-04-02", "2021-05-31",
    "2021-07-05", "2021-09-06", "2021-11-25", "2021-12-24",
    "2022-01-17", "2022-02-21", "2022-04-15", "2022-05-30", "2022-06-20",
    "2022-07-04", "2022-09-05", "2022-11-24", "2022-12-26",
    "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29",
    "2023-06-19", "2023-07-04", "2023-09-04", "2023-11-23", "2023-12-25",
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17", "2025-04-18",
    "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01", "2025-11-27",
    "2025-12-25",
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
    "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26", "2027-05-31",
    "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24",
    "2028-01-17", "2028-02-21", "2028-04-14", "2028-05-29", "2028-06-19",
    "2028-07-04", "2028-09-04", "2028-11-23", "2028-12-25",
    "2029-01-01", "2029-01-15", "2029-02-19", "2029-03-30", "2029-05-28",
    "2029-06-19", "2029-07-04", "2029-09-03", "2029-11-22", "2029-12-25",
    "2030-01-01", "2030-01-21", "2030-02-18", "2030-04-19", "2030-05-27",
    "2030-06-19", "2030-07-04", "2030-09-02", "2030-11-28", "2030-12-25",
))
NYSE_FIRST_DATE = dt.date(2018, 1, 1)
NYSE_LAST_YEAR_COVERED = 2030


class SessionCalendar:
    """An ordered run of trading sessions (v82).

    Positions are indexes into that run, so "sessions between" is a
    subtraction. An `asof` date that is not a session rolls BACK to the last
    session on or before it (a Saturday reads as Friday); a target date rolls
    FORWARD (a report dated Saturday reacts on Monday).
    """

    def __init__(self, sessions: Iterable[dt.date]):
        self._sessions: tuple[dt.date, ...] = tuple(sorted(set(sessions)))
        if not self._sessions:
            raise ValueError("SessionCalendar needs at least one session")

    @classmethod
    def from_bar_index(cls, index) -> "SessionCalendar":
        """The sessions a daily OHLCV frame actually traded -- the
        measurement's calendar, exact for history."""
        import pandas as pd
        return cls(ts.date() for ts in pd.DatetimeIndex(index))

    def __len__(self) -> int:
        return len(self._sessions)

    @property
    def first(self) -> dt.date:
        return self._sessions[0]

    @property
    def last(self) -> dt.date:
        return self._sessions[-1]

    def sessions(self, start: dt.date, end: dt.date) -> list[dt.date]:
        lo = bisect.bisect_left(self._sessions, start)
        hi = bisect.bisect_right(self._sessions, end)
        return list(self._sessions[lo:hi])

    def is_session(self, d: dt.date) -> bool:
        i = bisect.bisect_left(self._sessions, d)
        return i < len(self._sessions) and self._sessions[i] == d

    def position_on_or_after(self, d: dt.date) -> int | None:
        i = bisect.bisect_left(self._sessions, d)
        return i if i < len(self._sessions) else None

    def position_on_or_before(self, d: dt.date) -> int | None:
        i = bisect.bisect_right(self._sessions, d) - 1
        return i if i >= 0 else None

    def session_on_or_after(self, d: dt.date) -> dt.date | None:
        i = self.position_on_or_after(d)
        return None if i is None else self._sessions[i]

    def next_session(self, d: dt.date) -> dt.date | None:
        """The first session strictly after `d`."""
        i = bisect.bisect_right(self._sessions, d)
        return self._sessions[i] if i < len(self._sessions) else None

    def sessions_between(self, asof: dt.date, target: dt.date) -> int | None:
        """Sessions from `asof`'s session forward to `target`'s: next session
        = 1, same session = 0, negative when the target is behind."""
        a = self.position_on_or_before(asof)
        b = self.position_on_or_after(target)
        if a is None or b is None:
            return None
        return b - a


@functools.lru_cache(maxsize=1)
def nyse_calendar() -> SessionCalendar:
    """Every NYSE session from NYSE_FIRST_DATE through NYSE_LAST_YEAR_COVERED."""
    day, end = NYSE_FIRST_DATE, dt.date(NYSE_LAST_YEAR_COVERED, 12, 31)
    sessions = []
    while day <= end:
        if day.weekday() < 5 and day not in NYSE_HOLIDAYS:
            sessions.append(day)
        day += dt.timedelta(days=1)
    return SessionCalendar(sessions)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_session_calendar.py`
Expected: PASS, with `test_table_matches_the_cached_spy_bar_index` SKIPPED in the worktree. **If you run it where `data/backtest_cache/SPY.csv` exists and it fails, the holiday table or the cache is wrong — print the symmetric difference of the two session lists, report it, and fix the table only if a date in it is genuinely wrong. Never loosen the test.**

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/session.py tests/market/test_session_calendar.py
git commit -m "feat(v82): NYSE session calendar and bar-index calendar"
```

---

### Task M2: Earnings calendar

**Files:**
- Modify: `swingbot/core/market/events.py` (append `get_earnings_datetimes` after `_fetch_next_earnings_datetime`, line 163)
- Create: `swingbot/core/market/earnings_calendar.py`
- Modify: `tests/market/test_events.py` (the `clean_cache` fixture, lines 47-55; append four tests)
- Test: `tests/market/test_earnings_calendar.py` (new)

**Interfaces:**
- Consumes (M1): `SessionCalendar`, `nyse_calendar()`, `now_et(now)`.
- Produces:
  - `events.get_earnings_datetimes(ticker: str) -> list[dt.datetime]`
  - `earnings_calendar.BEFORE_OPEN = "before_open"`, `AFTER_CLOSE = "after_close"`, `UNCONFIRMED = "unconfirmed"`, `TIMINGS`, `CSV_FIELDS = ("report_date", "timing", "report_ts_et")`, `EARNINGS_CSV_DIR: Path` (`<repo>/market_data/earnings`)
  - `Report(date: dt.date, timing: str)`, `Label(date: dt.date, timing: str, sessions: int)` — frozen dataclasses
  - `classify_timing(ts: dt.datetime) -> str`, `report_from_timestamp(ts) -> Report`
  - `reaction_session(report, calendar) -> dt.date | None`
  - `next_reaction_distance(asof_pos: int, reaction_positions: Sequence[int]) -> int | None` (positions sorted ascending)
  - `sessions_to_reaction_from(asof: dt.date, reactions: Iterable[dt.date], calendar) -> int | None`
  - `is_exposed(distance: int | None, k: int) -> bool`
  - `CsvSource(directory=EARNINGS_CSV_DIR)` with `.reports(ticker) -> list[Report]`, `.has_data(ticker) -> bool`; `LiveSource()` with `.reports(ticker)`
  - `next_report(ticker, asof, *, source, calendar=None) -> Report | None`
  - `sessions_to_reaction(ticker, asof, *, source, calendar=None) -> int | None`
  - `earnings_label(ticker, now=None, *, source=None, calendar=None) -> Label | None`

- [ ] **Step 1: Write the failing tests**

In `tests/market/test_events.py`, replace the `clean_cache` fixture body so it clears both caches:

```python
@pytest.fixture(autouse=True)
def clean_cache():
    """`_earnings_datetime_cache` is a module-level dict with a 6h TTL --
    real across every test in this process, not per-test. Every test here
    uses "AAPL", so without this the second test to run would see the
    first test's cached result instead of exercising its own fake ticker.
    v82: `_earnings_datetimes_cache` has the same lifetime, same reason."""
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()
    yield
    events._earnings_datetime_cache.clear()
    events._earnings_datetimes_cache.clear()
```

Append to `tests/market/test_events.py`:

```python
# --- v82: get_earnings_datetimes -------------------------------------------

def test_get_earnings_datetimes_keeps_past_and_future_sorted(monkeypatch):
    tz = dt.timezone(dt.timedelta(hours=-4))
    past = dt.datetime(2026, 7, 30, 16, 0, tzinfo=tz)
    today_before_open = dt.datetime(2026, 9, 10, 6, 0, tzinfo=tz)
    future = dt.datetime(2026, 10, 29, 16, 0, tzinfo=tz)
    frame = _frame(future, past, today_before_open)
    monkeypatch.setattr(events.yf, "Ticker", lambda symbol: _FakeTicker(frame))
    assert events.get_earnings_datetimes("AAPL") == [past, today_before_open, future]


def test_get_earnings_datetimes_never_fetches_for_an_etf(monkeypatch):
    monkeypatch.setattr(events, "is_etf", lambda t: True)

    def boom(symbol):
        raise AssertionError("fetched earnings for an ETF")

    monkeypatch.setattr(events.yf, "Ticker", boom)
    assert events.get_earnings_datetimes("SPY") == []


def test_get_earnings_datetimes_failure_is_empty(monkeypatch):
    class Broken:
        def get_earnings_dates(self, limit=8):
            raise RuntimeError("yahoo down")

    monkeypatch.setattr(events.yf, "Ticker", lambda symbol: Broken())
    assert events.get_earnings_datetimes("AAPL") == []


def test_get_earnings_datetimes_is_cached(monkeypatch):
    tz = dt.timezone(dt.timedelta(hours=-4))
    calls = []

    def fake(symbol):
        calls.append(symbol)
        return _FakeTicker(_frame(dt.datetime(2026, 10, 29, 16, 0, tzinfo=tz)))

    monkeypatch.setattr(events.yf, "Ticker", fake)
    events.get_earnings_datetimes("AAPL")
    events.get_earnings_datetimes("AAPL")
    assert calls == ["AAPL"]
```

Create `tests/market/test_earnings_calendar.py`:

```python
"""v82 M2: the one earnings calendar -- timing, reaction session, distance,
exposure, sources and the display label."""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from swingbot.core.market import earnings_calendar as ec
from swingbot.core.market.session import nyse_calendar

ET = ZoneInfo("America/New_York")
D = dt.date.fromisoformat


class FakeSource:
    def __init__(self, *reports):
        self._reports = list(reports)

    def reports(self, ticker):
        return sorted(self._reports, key=lambda r: r.date)


def _now(date: str, hour: int = 10) -> dt.datetime:
    return dt.datetime.fromisoformat(date).replace(hour=hour, tzinfo=ET)


@pytest.mark.parametrize("hour, minute, expected", [
    (6, 0, ec.BEFORE_OPEN), (9, 29, ec.BEFORE_OPEN), (9, 30, ec.UNCONFIRMED),
    (15, 0, ec.UNCONFIRMED), (16, 0, ec.AFTER_CLOSE), (21, 0, ec.AFTER_CLOSE),
])
def test_classify_timing(hour, minute, expected):
    assert ec.classify_timing(dt.datetime(2026, 10, 29, hour, minute, tzinfo=ET)) == expected


def test_classify_timing_converts_to_eastern():
    assert ec.classify_timing(dt.datetime(2026, 10, 29, 20, 0, tzinfo=dt.timezone.utc)) == ec.AFTER_CLOSE


def test_naive_timestamp_reads_as_eastern():
    assert ec.classify_timing(dt.datetime(2026, 10, 29, 7, 0)) == ec.BEFORE_OPEN


def test_report_from_timestamp_uses_the_eastern_date():
    late_utc = dt.datetime(2026, 10, 30, 1, 0, tzinfo=dt.timezone.utc)  # 21:00 EDT on the 29th
    assert ec.report_from_timestamp(late_utc) == ec.Report(D("2026-10-29"), ec.AFTER_CLOSE)


@pytest.mark.parametrize("date, timing, reaction", [
    ("2026-09-15", ec.BEFORE_OPEN, "2026-09-15"),
    ("2026-09-15", ec.AFTER_CLOSE, "2026-09-16"),
    ("2026-09-15", ec.UNCONFIRMED, "2026-09-16"),
    ("2026-09-11", ec.AFTER_CLOSE, "2026-09-14"),   # Friday after close -> Monday
    ("2026-11-25", ec.AFTER_CLOSE, "2026-11-27"),   # skips Thanksgiving
    ("2026-09-12", ec.BEFORE_OPEN, "2026-09-14"),   # dated Saturday -> Monday
])
def test_reaction_session(date, timing, reaction):
    assert ec.reaction_session(ec.Report(D(date), timing), nyse_calendar()) == D(reaction)


def test_next_reaction_distance():
    assert ec.next_reaction_distance(10, [3, 10, 70]) == 0
    assert ec.next_reaction_distance(11, [3, 10, 70]) == 59
    assert ec.next_reaction_distance(71, [3, 10, 70]) is None
    assert ec.next_reaction_distance(5, []) is None


@pytest.mark.parametrize("distance, k, exposed", [
    (None, 5, False), (0, 5, False), (1, 1, True), (2, 1, False), (5, 5, True), (6, 5, False),
])
def test_is_exposed(distance, k, exposed):
    assert ec.is_exposed(distance, k) is exposed


def test_sessions_to_reaction_picks_the_earliest_ahead():
    src = FakeSource(ec.Report(D("2026-07-30"), ec.AFTER_CLOSE),
                     ec.Report(D("2026-09-15"), ec.AFTER_CLOSE),
                     ec.Report(D("2026-10-29"), ec.AFTER_CLOSE))
    # Fri 11 Sep -> reaction Wed 16 Sep: Mon, Tue, Wed
    assert ec.sessions_to_reaction("NVDA", D("2026-09-11"), source=src) == 3


def test_sessions_to_reaction_on_the_reaction_session_is_zero():
    src = FakeSource(ec.Report(D("2026-09-15"), ec.BEFORE_OPEN))
    assert ec.sessions_to_reaction("NVDA", D("2026-09-15"), source=src) == 0


def test_sessions_to_reaction_with_nothing_ahead_is_none():
    src = FakeSource(ec.Report(D("2026-07-30"), ec.AFTER_CLOSE))
    assert ec.sessions_to_reaction("NVDA", D("2026-09-11"), source=src) is None


def test_next_report():
    early = ec.Report(D("2026-09-15"), ec.AFTER_CLOSE)     # reacts Wed 16 Sep
    later = ec.Report(D("2026-12-01"), ec.BEFORE_OPEN)
    assert ec.next_report("NVDA", D("2026-09-16"), source=FakeSource(later, early)) == early
    assert ec.next_report("NVDA", D("2026-09-17"), source=FakeSource(later, early)) == later


def test_label_on_the_session_before_a_monday_report():
    src = FakeSource(ec.Report(D("2026-09-14"), ec.AFTER_CLOSE))
    assert ec.earnings_label("NVDA", _now("2026-09-11"), source=src) == \
        ec.Label(D("2026-09-14"), ec.AFTER_CLOSE, 1)


def test_label_on_report_day():
    src = FakeSource(ec.Report(D("2026-09-14"), ec.BEFORE_OPEN))
    assert ec.earnings_label("NVDA", _now("2026-09-14"), source=src).sessions == 0


def test_no_label_two_sessions_out():
    src = FakeSource(ec.Report(D("2026-09-14"), ec.AFTER_CLOSE))
    assert ec.earnings_label("NVDA", _now("2026-09-10"), source=src) is None


def test_no_label_for_a_report_already_past_on_a_weekend():
    src = FakeSource(ec.Report(D("2026-09-11"), ec.AFTER_CLOSE))
    assert ec.earnings_label("NVDA", _now("2026-09-12"), source=src) is None


def test_weekend_view_of_a_monday_report_is_next_session():
    src = FakeSource(ec.Report(D("2026-09-14"), ec.BEFORE_OPEN))
    assert ec.earnings_label("NVDA", _now("2026-09-12"), source=src).sessions == 1


def test_no_reports_no_label():
    assert ec.earnings_label("SPY", _now("2026-09-14"), source=FakeSource()) is None


def test_csv_source_reads_the_frozen_format(tmp_path):
    (tmp_path / "NVDA.csv").write_text(
        "report_date,timing,report_ts_et\n"
        "2026-10-29,after_close,2026-10-29T16:00:00-04:00\n"
        "2026-07-30,before_open,2026-07-30T06:00:00-04:00\n", encoding="utf-8")
    src = ec.CsvSource(tmp_path)
    assert src.reports("nvda") == [ec.Report(D("2026-07-30"), ec.BEFORE_OPEN),
                                   ec.Report(D("2026-10-29"), ec.AFTER_CLOSE)]
    assert src.has_data("NVDA") and not src.has_data("AAPL")
    assert src.reports("AAPL") == []


def test_csv_source_rejects_an_unknown_timing(tmp_path):
    (tmp_path / "X.csv").write_text(
        "report_date,timing,report_ts_et\n2026-10-29,midday,2026-10-29T12:00:00-04:00\n",
        encoding="utf-8")
    with pytest.raises(ValueError):
        ec.CsvSource(tmp_path).reports("X")


def test_live_source_builds_reports_from_events(monkeypatch):
    from swingbot.core.market import events
    monkeypatch.setattr(events, "get_earnings_datetimes", lambda t: [
        dt.datetime(2026, 9, 10, 6, 0, tzinfo=ET), dt.datetime(2026, 10, 29, 16, 0, tzinfo=ET)])
    assert ec.LiveSource().reports("AAPL") == [ec.Report(D("2026-09-10"), ec.BEFORE_OPEN),
                                               ec.Report(D("2026-10-29"), ec.AFTER_CLOSE)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_earnings_calendar.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.market.earnings_calendar'`.

Run: `python scripts/dev/testrun.py file tests/market/test_events.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.market.events' has no attribute '_earnings_datetimes_cache'`.

- [ ] **Step 3: Write the implementation**

Append to `swingbot/core/market/events.py`, after `_fetch_next_earnings_datetime`:

```python
#: v82: same lifetime and rationale as `_earnings_datetime_cache` above.
_earnings_datetimes_cache: dict[str, tuple[list[dt.datetime], float]] = {}


def get_earnings_datetimes(ticker: str) -> list[dt.datetime]:
    """Every earnings timestamp Yahoo returns for `ticker` -- recent past AND
    upcoming, ascending, timezone-aware (v82).

    `get_next_earnings_datetime` keeps only timestamps >= now, which drops a
    before-open report on its own day; the earnings calendar needs that
    report to label "earnings today". Cached per ticker for
    `_EARNINGS_DATETIME_CACHE_TTL_SECONDS`; an ETF returns [] without a
    fetch; any failure returns [] (and is cached, like its sibling)."""
    if is_etf(ticker):
        return []
    key = ticker.upper()
    now_monotonic = time.monotonic()
    cached = _earnings_datetimes_cache.get(key)
    if cached and (now_monotonic - cached[1]) < _EARNINGS_DATETIME_CACHE_TTL_SECONDS:
        return list(cached[0])

    result: list[dt.datetime] = []
    for candidate in candidate_symbols(ticker):
        try:
            frame = yf.Ticker(candidate).get_earnings_dates(limit=8)
        except Exception as e:
            log.debug("Earnings-dates fetch failed for %s: %s", candidate, e)
            continue
        if frame is None or frame.empty:
            continue
        result = sorted(ts.to_pydatetime() for ts in frame.index)
        break
    _earnings_datetimes_cache[key] = (result, now_monotonic)
    return list(result)
```

Create `swingbot/core/market/earnings_calendar.py`:

```python
"""The one place the bot answers "when does this ticker report, and how many
sessions away is that?" (v82).

A report's REACTION SESSION is the first session whose open can price it: the
report date for a before-open report, the next session for an after-close or
unconfirmed one. The blackout gate, the display label and the v82 measurement
all read these functions; nothing else computes days-to-earnings.

Sources: `LiveSource` (Yahoo via events.get_earnings_datetimes, 6h cache) and
`CsvSource` (market_data/earnings/<SYM>.csv, written by
scripts/data/fetch_earnings_dates.py in the frozen CSV_FIELDS format).
"""
from __future__ import annotations

import bisect
import csv
import datetime as dt
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from swingbot.core.market.session import SessionCalendar, now_et, nyse_calendar

BEFORE_OPEN = "before_open"
AFTER_CLOSE = "after_close"
UNCONFIRMED = "unconfirmed"
TIMINGS = (BEFORE_OPEN, AFTER_CLOSE, UNCONFIRMED)

#: Frozen by spec v82 B3 -- the fetch script writes it, CsvSource reads it.
CSV_FIELDS = ("report_date", "timing", "report_ts_et")
EARNINGS_CSV_DIR = Path(__file__).resolve().parents[3] / "market_data" / "earnings"

_OPEN = dt.time(9, 30)
_CLOSE = dt.time(16, 0)


@dataclass(frozen=True)
class Report:
    date: dt.date
    timing: str


@dataclass(frozen=True)
class Label:
    date: dt.date
    timing: str
    sessions: int        # 0 = the report is today's session, 1 = the next session


def classify_timing(ts: dt.datetime) -> str:
    """ET time of day: before 09:30 -> before_open; 16:00 or later ->
    after_close; anything in between (Yahoo's 15:00 estimated-date stamp
    included) -> unconfirmed. A naive timestamp is read as ET."""
    t = now_et(ts).time()
    if t < _OPEN:
        return BEFORE_OPEN
    if t >= _CLOSE:
        return AFTER_CLOSE
    return UNCONFIRMED


def report_from_timestamp(ts: dt.datetime) -> Report:
    et = now_et(ts)
    return Report(et.date(), classify_timing(et))


def reaction_session(report: Report, calendar: SessionCalendar) -> dt.date | None:
    if report.timing == BEFORE_OPEN:
        return calendar.session_on_or_after(report.date)
    return calendar.next_session(report.date)


def next_reaction_distance(asof_pos: int, reaction_positions: Sequence[int]) -> int | None:
    """THE exposure arithmetic: sessions from `asof_pos` to the earliest
    reaction position at or after it (0 = the reaction is that session), or
    None when none lies ahead. `reaction_positions` must be sorted."""
    i = bisect.bisect_left(reaction_positions, asof_pos)
    if i == len(reaction_positions):
        return None
    return reaction_positions[i] - asof_pos


def sessions_to_reaction_from(asof: dt.date, reactions: Iterable[dt.date],
                              calendar: SessionCalendar) -> int | None:
    asof_pos = calendar.position_on_or_before(asof)
    if asof_pos is None:
        return None
    positions = sorted({p for p in (calendar.position_on_or_after(r) for r in reactions)
                        if p is not None})
    return next_reaction_distance(asof_pos, positions)


def is_exposed(distance: int | None, k: int) -> bool:
    """Spec v82 B2: a signal is exposed at K iff its next reaction is 1..K
    sessions ahead. 0 is not exposed: that session's open already priced it."""
    return distance is not None and 1 <= distance <= k


class EarningsSource(Protocol):
    def reports(self, ticker: str) -> list[Report]: ...


class CsvSource:
    """market_data/earnings/<SYM>.csv, read once per ticker per instance."""

    def __init__(self, directory: Path | str = EARNINGS_CSV_DIR):
        self._dir = Path(directory)
        self._cache: dict[str, list[Report]] = {}

    def _path(self, ticker: str) -> Path:
        return self._dir / f"{ticker.upper()}.csv"

    def has_data(self, ticker: str) -> bool:
        return self._path(ticker).exists()

    def reports(self, ticker: str) -> list[Report]:
        key = ticker.upper()
        if key not in self._cache:
            path = self._path(key)
            out: list[Report] = []
            if path.exists():
                with open(path, newline="", encoding="utf-8") as fh:
                    for row in csv.DictReader(fh):
                        if row["timing"] not in TIMINGS:
                            raise ValueError(f"{path}: unknown timing {row['timing']!r}")
                        out.append(Report(dt.date.fromisoformat(row["report_date"]), row["timing"]))
            self._cache[key] = sorted(out, key=lambda r: r.date)
        return list(self._cache[key])


class LiveSource:
    """Yahoo, through events.get_earnings_datetimes (ETFs -> [])."""

    def reports(self, ticker: str) -> list[Report]:
        from swingbot.core.market import events
        found = {report_from_timestamp(ts) for ts in events.get_earnings_datetimes(ticker)}
        return sorted(found, key=lambda r: (r.date, r.timing))


def next_report(ticker: str, asof: dt.date, *, source: EarningsSource,
                calendar: SessionCalendar | None = None) -> Report | None:
    """The earliest report whose reaction session is on or after `asof`'s."""
    calendar = calendar or nyse_calendar()
    asof_pos = calendar.position_on_or_before(asof)
    if asof_pos is None:
        return None
    best: tuple[int, Report] | None = None
    for report in source.reports(ticker):
        session = reaction_session(report, calendar)
        pos = None if session is None else calendar.position_on_or_after(session)
        if pos is None or pos < asof_pos:
            continue
        if best is None or pos < best[0]:
            best = (pos, report)
    return None if best is None else best[1]


def sessions_to_reaction(ticker: str, asof: dt.date, *, source: EarningsSource,
                         calendar: SessionCalendar | None = None) -> int | None:
    calendar = calendar or nyse_calendar()
    reactions = [s for s in (reaction_session(r, calendar) for r in source.reports(ticker))
                 if s is not None]
    return sessions_to_reaction_from(asof, reactions, calendar)


def earnings_label(ticker: str, now: dt.datetime | None = None, *,
                   source: EarningsSource | None = None,
                   calendar: SessionCalendar | None = None) -> Label | None:
    """Plan A's display rule: the report DATE is today's session (0) or the
    next session (1). A report dated before today never labels, so a Friday
    report is not "today" on Saturday."""
    source = source or LiveSource()
    calendar = calendar or nyse_calendar()
    today = now_et(now).date()
    today_pos = calendar.position_on_or_before(today)
    if today_pos is None:
        return None
    best: Label | None = None
    for report in source.reports(ticker):
        if report.date < today:
            continue
        pos = calendar.position_on_or_after(report.date)
        if pos is None:
            continue
        n = pos - today_pos
        if 0 <= n <= 1 and (best is None or n < best.sessions):
            best = Label(report.date, report.timing, n)
    return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/market/test_earnings_calendar.py`
Expected: PASS.

Run: `python scripts/dev/testrun.py file tests/market/test_events.py`
Expected: PASS (the pre-existing `get_next_earnings_datetime` tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/events.py swingbot/core/market/earnings_calendar.py tests/market/test_events.py tests/market/test_earnings_calendar.py
git commit -m "feat(v82): one earnings calendar -- reaction session, distance, exposure, label"
```

---

### Task M3: Rename the blackout field, freeze it, rewrite the gate

**Files:**
- Modify: `swingbot/config.py:661-667` (the Field), `:893` and `:900` (`_SEARCH_CLASSES`)
- Modify: `swingbot/scan_params.py:31`, `:76`
- Modify: `swingbot/core/edge/gates.py:1-3` (docstring), `:32-47`
- Modify: `.env.example:410-412`
- Modify: `scripts/backtest/wf_components.py:91-92`
- Modify: `tests/edge/test_edge_gates.py:32-43`, `tests/backtesting/test_knob_observability.py:13`, `tests/test_scan_params_coverage.py` (append)

**Interfaces:**
- Consumes (M2): `earnings_calendar.is_exposed`, `LiveSource`, `sessions_to_reaction`; (M1) `session.now_et`.
- Produces: `config.EARNINGS_BLACKOUT_SESSIONS: int` (default 0, `search_class="frozen"`); `ScanParams.earnings_blackout_sessions: int`; `gates.in_earnings_blackout(symbol, now=None, sessions=None, sessions_to_reaction_fn=None) -> bool`, where `sessions_to_reaction_fn(symbol, now) -> int | None`.

- [ ] **Step 1: Write the failing tests**

In `tests/edge/test_edge_gates.py`, replace lines 32-43 (both earnings tests) with:

```python
def test_earnings_blackout_window():
    from swingbot.core.edge.gates import in_earnings_blackout

    def at(distance):
        return lambda symbol, now: distance

    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(1)) is True
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(3)) is True
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(4)) is False
    # 0: the reaction session's open already priced the report
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(0)) is False
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(None)) is False
    assert in_earnings_blackout("NVDA", sessions=0, sessions_to_reaction_fn=at(1)) is False  # off


def test_earnings_blackout_passes_now_through():
    import datetime as dt
    from swingbot.core.edge.gates import in_earnings_blackout
    seen = []
    now = dt.datetime(2026, 9, 14, 10, 0)
    in_earnings_blackout("NVDA", now=now, sessions=2,
                         sessions_to_reaction_fn=lambda symbol, when: seen.append(when) or 1)
    assert seen == [now]


def test_earnings_blackout_etf_exempt():
    from swingbot.core.edge.gates import in_earnings_blackout
    # the live source returns no reports for an ETF, without a fetch
    assert in_earnings_blackout("SPY", sessions=5) is False
```

Append to `tests/test_scan_params_coverage.py`:

```python
def test_earnings_blackout_is_frozen_by_its_pre_registration():
    field = next(field for field in config.FIELDS if field.attr == "EARNINGS_BLACKOUT_SESSIONS")
    assert field.search_class == "frozen"
    assert field.default == "0"
    assert "EARNINGS_BLACKOUT_SESSIONS" not in config.searchable_attrs()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/edge/test_edge_gates.py`
Expected: FAIL — `TypeError: in_earnings_blackout() got an unexpected keyword argument 'sessions'`.

Run: `python scripts/dev/testrun.py file tests/test_scan_params_coverage.py`
Expected: FAIL — `StopIteration` (no field named `EARNINGS_BLACKOUT_SESSIONS`).

- [ ] **Step 3: Write the implementation**

`swingbot/config.py` — replace the Field at lines 661-667 with:

```python
    Field("EARNINGS_BLACKOUT_SESSIONS", "EARNINGS_BLACKOUT_SESSIONS", "Universe & Scanning",
          "Earnings blackout (sessions before the reaction)",
          type="number", default="0", min=0, max=5, step=1,
          help="Blocks a new setup when the ticker's next earnings reaction session -- the report "
               "day for a before-open report, the next session for an after-close one -- is 1 to "
               "this many trading sessions away (0 = off). ETFs never block. Pre-registered by "
               "spec v82: stays 0 unless its one VALIDATION shot passes, and is not yet wired "
               "into the scan path (v82 Plan A)."),
```

`swingbot/config.py` — in `_SEARCH_CLASSES["searchable"]`, change line 893 from

```python
        "EARNINGS_BLACKOUT_DAYS", "REGIME_GATES_ENABLED",
```

to

```python
        "REGIME_GATES_ENABLED",
```

and change line 900 from

```python
    "frozen": {"MIN_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO"},
```

to

```python
    # EARNINGS_BLACKOUT_SESSIONS: its value is set by spec v82's pre-registered
    # funnel, never by a config grid.
    "frozen": {"MIN_RISK_REWARD_RATIO", "MAX_RISK_REWARD_RATIO",
               "EARNINGS_BLACKOUT_SESSIONS"},
```

`swingbot/scan_params.py` — line 31 becomes `    earnings_blackout_sessions: int` and line 76 becomes `            earnings_blackout_sessions=config.EARNINGS_BLACKOUT_SESSIONS,`.

`swingbot/core/edge/gates.py` — replace lines 1-3 with:

```python
"""Entry gates driven by distributions, not vibes: overnight gap noise
(this task), earnings blackout (E18, re-expressed over spec v82's exposure
rule). Each is a pure function; wiring is always flag-gated and
validated before it can touch live behavior."""
```

and replace lines 32-47 (`_default_days_to_earnings` and `in_earnings_blackout`) with:

```python
def _live_sessions_to_reaction(symbol: str, now) -> int | None:
    from swingbot.core.market import earnings_calendar
    from swingbot.core.market.session import now_et
    return earnings_calendar.sessions_to_reaction(
        symbol, now_et(now).date(), source=earnings_calendar.LiveSource())


def in_earnings_blackout(symbol: str, now=None, sessions: int | None = None,
                         sessions_to_reaction_fn=None) -> bool:
    """Spec v82 B2 on the live source: blocked iff the next earnings reaction
    session is 1..`sessions` sessions ahead of `now`'s session. `now` is
    honoured (the pre-v82 gate ignored it). Not wired into the scan path."""
    from swingbot.core.market.earnings_calendar import is_exposed
    window = sessions if sessions is not None else getattr(config, "EARNINGS_BLACKOUT_SESSIONS", 0)
    if window <= 0:
        return False
    fn = sessions_to_reaction_fn or _live_sessions_to_reaction
    return is_exposed(fn(symbol, now), window)
```

`.env.example` — replace lines 410-412 with:

```
# New setups are blocked when the ticker's next earnings reaction session is
# 1 to this many trading sessions away (0 = off). Pre-registered by spec v82;
# stays 0 unless its validation shot passes.
EARNINGS_BLACKOUT_SESSIONS=0
```

`scripts/backtest/wf_components.py` — replace lines 91-92 with:

```python
    "EARNINGS_BLACKOUT_SESSIONS":
        "Spec v82 pre-registers this gate and measures it with its own "
        "instrument, scripts/backtest/measure_earnings_blackout.py -- this "
        "harness never calls the scan path the gate lives in.",
```

`tests/backtesting/test_knob_observability.py` — delete line 13 (the `"EARNINGS_BLACKOUT_DAYS": ...` entry). The field is no longer `searchable`, so it must not appear in `EXEMPT` (`test_every_exempt_entry_is_searchable`).

- [ ] **Step 4: Run tests to verify they pass**

Run each:

```
python scripts/dev/testrun.py file tests/edge/test_edge_gates.py
python scripts/dev/testrun.py file tests/test_scan_params_coverage.py
python scripts/dev/testrun.py file tests/backtesting/test_knob_observability.py
python scripts/dev/testrun.py file tests/test_env_example_sync.py
```

Expected: PASS for all four (the knob-observability file's slow parametrized cases may be deselected by the runner's tier; `test_every_exempt_entry_is_searchable` and `test_exempt_reasons_are_substantive` must run and pass). `test_env_example_sync.py` asserts `.env.example` lists every schema key and no unknown one — it fails if the `.env.example` edit above was missed.

- [ ] **Step 5: Prove the old name is gone**

Run: `git grep -n -E "EARNINGS_BLACKOUT_DAYS|earnings_blackout_days|_default_days_to_earnings" -- ':!docs' ':!swingbot/admin/version_history.json'`
Expected: no output. (Historical results docs under `docs/` keep the old name — they record what was true then.)

- [ ] **Step 6: Check production's `.env` (read-only)**

If `scripts/ops/ssh-hetzner.sh` exists on this machine, run:

```bash
bash scripts/ops/ssh-hetzner.sh "grep -n EARNINGS_BLACKOUT /opt/swing-bot/.env || echo 'not set'"
```

- `not set` or `EARNINGS_BLACKOUT_DAYS=0` → record it in the task report; the old key is ignored by `config._apply_env` (it reads only defined Fields) and changes nothing.
- A **non-zero** `EARNINGS_BLACKOUT_DAYS` → **stop and tell the human partner**: someone set a blackout that never ran. Do not edit production.
- If the script is absent, record "production .env not checked — ssh helper absent" for the partner.

- [ ] **Step 7: Commit**

```bash
git add swingbot/config.py swingbot/scan_params.py swingbot/core/edge/gates.py .env.example scripts/backtest/wf_components.py tests/edge/test_edge_gates.py tests/backtesting/test_knob_observability.py tests/test_scan_params_coverage.py
git commit -m "feat(v82): EARNINGS_BLACKOUT_SESSIONS -- frozen, sessions not days, gate over B2's rule"
```
