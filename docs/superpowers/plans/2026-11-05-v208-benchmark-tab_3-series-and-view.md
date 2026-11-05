# v208 — Benchmark tab, part 3: session alignment, deployed return, response assembly

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v208 — Benchmark tab](../specs/2026-11-05-v208-benchmark-tab.md) (its *Amendment after the code brief* overrides earlier spec text)
**Index:** [2026-11-05-v208-benchmark-tab_0-index.md](2026-11-05-v208-benchmark-tab_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation, the task ledger and the **response contract** live there; every task below implicitly includes them.

Tasks V208-8..V208-10 (V208-10 is split into V208-10 and V208-10b). All
three modules are **pure**: no I/O, no clock reads, no config reads. Order:
V208-8 → V208-9 → V208-10 → V208-10b. V208-9 also needs V208-3's
`equity.session_trade_pnl`; V208-10 needs V208-7's `benchmark.py` and
V208-5's `BENCHMARK_SYMBOLS`.

Conventions used in this part:

- **Returns are fractions** inside `benchmark_series.py` and every dataclass
  here (`0.0123` = +1.23 %). Only the response dicts V208-10/10b build carry
  percentages (`× 100`, rounded to 4 dp by `benchmark_view.pct`).
- `rows` are `equity_samples_repo().list_rows()` dicts: UTC-aware `at`,
  float money columns, `id`, `source`, `kind`. A NULL promoted column is an
  **absent key** (`merge_doc`), so read `open_notional` /
  `open_notional_approx` with `row.get(...)`.
- A row's session is its **New York calendar date**:
  `row["at"].astimezone(US_MARKET_TZ).date()`. Rows sort by
  `(row["at"], row.get("id") or 0)`, the order `mtm_candles` uses.
- Sessions come from `nyse_calendar().sessions(start, end)`; the caller
  passes them in. A day not in the passed sessions is ignored (a holiday
  live sample never becomes a session).
- `bars` are `BenchmarkBarRepository.list_range(...)` dicts: every `BAR_KEYS`
  key present (NULL as `None`), `session` a `date`, `day_pct` a fraction.
- Fixture calendar: 2026-11-02 Mon … 2026-11-06 Fri; 2026-11-26 Thu is an
  NYSE holiday; 2026-11-27 Fri closes at 13:00 ET.

Tests in this part need no database: `python scripts/dev/testrun.py file <test>`
only (suite `analytics`, `tests/analytics/` already exists with `__init__.py`).

# Phase D — series and view


### Task V208-8: `benchmark_series.py`: account closes, session alignment, gaps, `base_balance` breaks

**Model:** opus — the gap and break rules decide which returns every stat counts; a wrong span silently pairs a two-day bot return with a one-day index return.

**Files:**
- Create: `swingbot/core/analytics/benchmark_series.py`
- Create: `tests/analytics/test_benchmark_series.py` (suite `analytics`)

**Interfaces:**
- Consumes (existing code):
  - `swingbot.core.tracking.equity_candles.mtm_candles(rows, "1D") -> list[dict]` (candle `t` = NY ISO date, `c` = 2-dp float close), reused unchanged.
  - `swingbot.core.tracking.equity.RealizedLeg(at: datetime, amount: Decimal, trade_id)`, `equity.to_decimal(value) -> Decimal | None`.
  - `swingbot.core.market.session.US_MARKET_TZ`; `nyse_calendar()` (tests only).
- Produces (V208-9 extends the module, V208-10/10b consume; names final):
  - `bot_session_closes(rows: list[dict], sessions: Sequence[date]) -> dict[date, float]` — the 1D `mtm_candles` close of each NY date that is in `sessions`; any other date (weekend backfill, NYSE-holiday live sample) is dropped.
  - `BREAK_TOLERANCE = Decimal("0.01")`
  - `base_balance_breaks(rows: list[dict], legs: list[RealizedLeg], sessions: Sequence[date]) -> set[date]`
  - `@dataclass(frozen=True) AlignedDay(session: date, bot_close: float | None, bot_ret: float | None, span: int, index_ret: dict[str, float | None], index_proxy: dict[str, bool], missing: bool, base_break: bool)` with property `one_session -> bool` = `span == 1 and not missing and not base_break and bot_ret is not None` (the ledger's rule plus "has a return": the first session has none).
  - `align(sessions: Sequence[date], closes: dict[date, float], index_pct: dict[str, dict[date, tuple[float | None, bool]]], breaks: set[date]) -> list[AlignedDay]` — one `AlignedDay` per session, in order.
  - Private `_ny_day(at) -> date` and `_session_points(rows, sessions) -> dict[date, list[dict]]` (point rows by NY session date, sorted by `(at, id or 0)`); V208-9's public `rows_by_session` returns the latter.

Rules (spec § Bot · account daily series, § Gaps; Global Constraints):

- `index_pct[symbol][session] = (day_pct, proxy)`; a session absent from the
  inner dict means "no bar" and reads as `(None, False)`.
- A session **with** a close and a previous close (the latest earlier session
  in `sessions` that had one): `bot_ret = close / previous − 1`, `span` =
  sessions since that previous close (1 = the very next session).
  - `span == 1`: `index_ret[sym]` = that session's own `day_pct`; `index_proxy[sym]` its own flag.
  - `span > 1`: `index_ret[sym]` = `Π(1 + day_pct) − 1` over the `span`
    sessions (the missing ones and this one); `None` if any of them has no
    `day_pct`. `index_proxy[sym]` = any of them is a proxy day.
- A session with a close but **no** previous close (the first): `bot_ret = None`, `span = 1`, `index_ret` = own `day_pct`.
- A session **without** a close: `missing = True`, `bot_close = bot_ret = None`,
  `span = 1`, `index_ret[sym] = None` for every symbol (the pair completes on
  the next close, which carries the compounded value), `index_proxy` = own
  flag. Missing sessions before the first close open no span.
- `base_break = session in breaks`; `bot_ret` keeps its raw value (V208-10 excludes it).
- `base_balance_breaks`: for each session in `sessions` with a point row and a
  previous session with one (the latest earlier one), `Δrealized =
  realized_balance(last point) − realized_balance(previous last point)`,
  `legs = Σ leg.amount for prev.at < leg.at ≤ last.at`; a break when
  `|Δrealized − legs| > BREAK_TOLERANCE` (Decimal via `to_decimal`). The first
  session is never a break.

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_benchmark_series.py`:

```python
"""v208 V208-8: account closes, session alignment, gaps, base_balance breaks."""
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import count

import pytest

from swingbot.core.analytics import benchmark_series as bs
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar
from swingbot.core.tracking.equity import RealizedLeg
from swingbot.core.tracking.equity_candles import mtm_candles

MON, TUE, WED, THU, FRI = (date(2026, 11, d) for d in (2, 3, 4, 5, 6))
WEEK = [MON, TUE, WED, THU, FRI]
_ids = count(1)


def _at(day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(timezone.utc)


def _row(day, hh, mm, equity, *, realized=None, source="live", kind="point"):
    return {"id": next(_ids), "at": _at(day, hh, mm), "equity": equity,
            "realized_balance": equity if realized is None else realized,
            "unrealized_pnl": 0.0, "open_n": 0, "skipped_n": 0, "source": source, "kind": kind}


def _book():
    return [
        _row(MON, 9, 30, 10_000.0, source="backfill"), _row(MON, 16, 0, 10_100.0, source="backfill"),
        _row(MON, 9, 30, 10_400.0, source="backfill", kind="day_high"),
        _row(TUE, 9, 35, 10_120.0), _row(TUE, 15, 55, 10_201.0),
        _row(TUE, 9, 35, 9_000.0, kind="day_low"),
        _row(WED, 10, 0, 10_150.0), _row(WED, 15, 55, 10_098.99),
    ]


def test_daily_closes_equal_the_dashboard_1d_closes():
    rows = _book()
    dashboard = {date.fromisoformat(c["t"]): c["c"] for c in mtm_candles(rows, "1D")}
    assert bs.bot_session_closes(rows, WEEK) == dashboard
    assert bs.bot_session_closes(rows, WEEK) == {MON: 10_100.0, TUE: 10_201.0, WED: 10_098.99}


def test_a_holiday_live_sample_never_becomes_a_session():
    wed, thanksgiving, fri = date(2026, 11, 25), date(2026, 11, 26), date(2026, 11, 27)
    sessions = nyse_calendar().sessions(wed, fri)
    assert thanksgiving not in sessions
    rows = [_row(wed, 15, 55, 10_000.0), _row(thanksgiving, 11, 0, 10_500.0), _row(fri, 12, 55, 10_050.0)]
    assert bs.bot_session_closes(rows, sessions) == {wed: 10_000.0, fri: 10_050.0}


def test_a_weekend_backfill_candle_is_skipped():
    sat = date(2026, 11, 7)
    rows = [_row(FRI, 16, 0, 10_000.0, source="backfill"), _row(sat, 16, 0, 10_300.0, source="backfill")]
    assert bs.bot_session_closes(rows, WEEK) == {FRI: 10_000.0}


SPY = {MON: (0.001, False), TUE: (0.01, False), WED: (0.02, True), THU: (-0.01, False), FRI: (0.005, False)}


def test_one_session_days_pair_with_the_index_day():
    days = bs.align(WEEK, {MON: 100.0, TUE: 101.0, WED: 102.01, THU: 101.0, FRI: 102.0}, {"SPY": SPY}, set())
    assert [d.session for d in days] == WEEK
    first, tue = days[0], days[1]
    assert (first.bot_ret, first.span, first.one_session) == (None, 1, False)
    assert first.index_ret == {"SPY": 0.001}
    assert tue.bot_ret == pytest.approx(0.01) and tue.span == 1 and tue.one_session
    assert tue.index_ret == {"SPY": 0.01} and tue.index_proxy == {"SPY": False}


def test_a_missing_bot_session_is_a_gap_and_the_index_compounds_over_the_span():
    days = bs.align(WEEK, {MON: 100.0, TUE: 101.0, THU: 103.02, FRI: 104.0}, {"SPY": SPY}, set())
    wed, thu = days[2], days[3]
    assert wed.missing and wed.bot_close is None and wed.bot_ret is None
    assert wed.index_ret == {"SPY": None} and wed.index_proxy == {"SPY": True}
    assert not wed.one_session
    assert thu.span == 2 and not thu.missing and not thu.one_session
    assert thu.bot_ret == pytest.approx(103.02 / 101.0 - 1)
    assert thu.index_ret["SPY"] == pytest.approx(1.02 * 0.99 - 1)
    assert thu.index_proxy == {"SPY": True}           # a proxy day inside the span
    assert days[4].span == 1 and days[4].one_session


def test_a_span_with_an_unpriced_index_day_has_no_index_return():
    spy = {day: value for day, value in SPY.items() if day != WED}
    days = bs.align(WEEK, {MON: 100.0, TUE: 101.0, THU: 103.0}, {"SPY": spy}, set())
    assert days[3].span == 2 and days[3].index_ret == {"SPY": None}


def test_sessions_before_the_first_close_are_missing_and_open_no_span():
    days = bs.align(WEEK, {WED: 100.0, THU: 101.0}, {"SPY": SPY}, set())
    assert [d.missing for d in days] == [True, True, False, False, True]
    assert (days[2].bot_ret, days[2].span) == (None, 1)
    assert days[3].span == 1 and days[3].one_session


def test_no_closes_at_all_is_every_session_missing():
    assert all(d.missing and d.bot_ret is None for d in bs.align(WEEK, {}, {"SPY": SPY}, set()))


def test_a_base_break_keeps_its_raw_return_but_is_never_one_session():
    days = bs.align(WEEK, {MON: 100.0, TUE: 110.0}, {"SPY": SPY}, {TUE})
    assert days[1].base_break and days[1].bot_ret == pytest.approx(0.1) and not days[1].one_session


def _close(day, realized):
    return _row(day, 15, 55, realized, realized=realized)


@pytest.mark.parametrize("jump, leg, breaks", [
    (500.0, None, {WED}),                           # base_balance edited: no leg explains it
    (500.0, Decimal("500"), set()),                 # a closed trade explains it
    (500.01, Decimal("500"), set()),                # within the 0.01 tolerance
    (500.02, Decimal("500"), {WED}),                # just past it
])
def test_base_balance_breaks(jump, leg, breaks):
    rows = [_close(MON, 10_000.0), _close(TUE, 10_000.0), _close(WED, 10_000.0 + jump)]
    legs = [] if leg is None else [RealizedLeg(_at(WED, 11), leg, "t1")]
    assert bs.base_balance_breaks(rows, legs, WEEK) == breaks


def test_a_leg_before_the_previous_close_does_not_explain_a_jump():
    rows = [_close(TUE, 10_000.0), _close(WED, 10_500.0)]
    legs = [RealizedLeg(_at(TUE, 15, 0), Decimal("500"), "t1")]
    assert bs.base_balance_breaks(rows, legs, WEEK) == {WED}


def test_a_break_is_measured_across_a_missing_session():
    rows = [_close(MON, 10_000.0), _close(WED, 10_300.0)]
    legs = [RealizedLeg(_at(TUE, 12), Decimal("300"), "t1")]
    assert bs.base_balance_breaks(rows, legs, WEEK) == set()
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_series.py`
Expected: FAIL — `ImportError: cannot import name 'benchmark_series'`.

- [ ] **Step 3: Create `swingbot/core/analytics/benchmark_series.py`**

Module docstring: v208; pure (no I/O, clock or config); fractions only; a
row's session is its NY calendar date; the close is `mtm_candles`' so the tab
equals the Dashboard.

- `_ny_day(at)` = `at.astimezone(US_MARKET_TZ).date()`.
- `_session_points(rows, sessions)`: keep `row["kind"] == "point"` rows whose
  `_ny_day(row["at"])` is in `set(sessions)`; group by that day; sort each
  group by `(row["at"], row.get("id") or 0)` (the order `mtm_candles` uses).
- `bot_session_closes`: `{date.fromisoformat(c["t"]): c["c"] for c in
  mtm_candles(rows, "1D")}` filtered to `set(sessions)`. Never re-derive the
  close: the Dashboard equality is the contract.
- `base_balance_breaks`: walk `sessions` in order over `_session_points`,
  remembering the previous close row; the window sum is a helper
  `_legs_between(legs, start, end) -> Decimal`.
- `align` is the one algorithm the rules need a body for:

```python
def align(sessions, closes, index_pct, breaks):
    days, prev_close, pending = [], None, []
    for session in sessions:
        own = {sym: by_day.get(session, (None, False)) for sym, by_day in index_pct.items()}
        close = closes.get(session)
        if close is None:
            days.append(_missing_day(session, own, session in breaks))
            if prev_close is not None:
                pending.append(own)
            continue
        span_days = pending + [own]
        bot_ret = None if prev_close is None else close / prev_close - 1
        days.append(AlignedDay(session, close, bot_ret, len(span_days),
                               _compound(span_days), _any_proxy(span_days),
                               False, session in breaks))
        prev_close, pending = close, []
    return days
```

with `_missing_day(session, own, base_break)` (`index_ret` all `None`,
`index_proxy` the own flags), `_compound(span_days) -> dict[str, float | None]`
(per symbol `Π(1 + pct) − 1`, `None` when any `pct` is `None`; a one-day span
returns the own `pct` unchanged, so no float drift) and
`_any_proxy(span_days) -> dict[str, bool]`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_series.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0; every new function < 15.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/benchmark_series.py tests/analytics/test_benchmark_series.py
git commit -m "feat(v208): benchmark_series -- account closes, session alignment, gaps, base_balance breaks"
```

### Task V208-9: `benchmark_series.py`: exposure + Bot · deployed

**Model:** opus — the deployed denominator, the 5% no-chain floor and the −100% clip are the quant panel's redesign; each edge case changes what the dashed line claims.

**Files:**
- Modify: `swingbot/core/analytics/benchmark_series.py` (created by V208-8)
- Create: `tests/analytics/test_benchmark_deployed.py` (suite `analytics`)

**Interfaces:**
- Consumes:
  - V208-8: `_session_points(rows, sessions)`, `_ny_day(at)`.
  - V208-3: `equity.session_trade_pnl(legs: list[RealizedLeg], prev_at: datetime, at: datetime, prev_unrealized: Decimal, unrealized: Decimal) -> Decimal` (Σ `leg.amount` for `prev_at < leg.at ≤ at` plus `unrealized − prev_unrealized`).
  - Existing: `equity.to_decimal`, `session.session_close(d) -> time` (13:00 on a half day), `session.US_MARKET_TZ`.
  - Row fields: `open_notional` and `open_notional_approx` are **absent keys** when NULL (`merge_doc`); read them with `row.get(...)`.
- Produces (V208-10/10b consume; names final):
  - `DEPLOYED_MIN_SHARE = 0.05`
  - `rows_by_session(rows: list[dict], sessions: Sequence[date]) -> dict[date, list[dict]]` = `_session_points(rows, sessions)` (point rows only, NY day, `(at, id)` order; a session without rows is absent).
  - `@dataclass(frozen=True) Exposure(pct: float | None, open_n: int, approx: bool)` — `pct` a fraction of equity.
  - `exposure_by_session(by_day: dict[date, list[dict]]) -> dict[date, Exposure]` — one entry per `by_day` key.
  - `@dataclass(frozen=True) Deployed(ret: float | None, clipped: bool, approx: bool, reason: str | None)`; reasons are exactly `"no_exposure"`, `"below_min"`, `"missing"` (`ret is None` iff `reason is not None`).
  - `deployed_returns(by_day: dict[date, list[dict]], legs: list[RealizedLeg], sessions: Sequence[date]) -> dict[date, Deployed]` — one entry per session in `sessions`.

Rules (spec § Exposure and Bot · deployed; Global Constraints):

- **Exposure** = time-weighted mean of `open_notional / equity` over the
  session's point rows that have an `open_notional` and `equity > 0`. A
  sample's weight is the time to the next such sample; the last one's is the
  time to the session close (`datetime.combine(day, session_close(day),
  US_MARKET_TZ)`, floored at 0). All weights 0 (a lone 16:00 backfill close)
  → the plain mean. No usable sample → `pct = None`. `open_n` = max `open_n`
  over all the session's point rows; `approx` = any usable row has
  `open_notional_approx` true.
- **Deployed** for session `s` with point rows `points` (last = `close`) and
  `prev` = the last point row of the latest earlier session in `by_day`:
  1. no rows for `s`, or no `prev` → `Deployed(None, False, False, "missing")`;
  2. `P = session_trade_pnl(legs, prev["at"], close["at"], to_decimal(prev["unrealized_pnl"]), to_decimal(close["unrealized_pnl"]))`;
  3. `D` = max of the non-`None` `open_notional` over `points` and `prev`; none present → `"missing"`;
  4. `D <= 0` → `"no_exposure"`; `D < DEPLOYED_MIN_SHARE × close["equity"]` → `"below_min"`;
  5. else `ret = float(P) / D`; `ret < −1.0` → `ret = −1.0`, `clipped = True`.
  `approx` = any of `points + [prev]` has `open_notional_approx` true (set on every outcome where those rows exist).
- `P` never reads a balance, so a `base_balance` edit gives `P = 0` (test).

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_benchmark_deployed.py`:

```python
"""v208 V208-9: exposure (time-weighted) and Bot · deployed (peak denominator)."""
from datetime import date, datetime, timezone
from decimal import Decimal
from itertools import count

import pytest

from swingbot.core.analytics import benchmark_series as bs
from swingbot.core.market.session import US_MARKET_TZ
from swingbot.core.tracking.equity import RealizedLeg

MON, TUE, WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
HALF_DAY = date(2026, 11, 27)
_ids = count(1)


def _at(day, hh, mm=0):
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(timezone.utc)


def _row(day, hh, mm, *, notional=None, equity=10_000.0, unrealized=0.0, realized=10_000.0,
         open_n=0, approx=None, kind="point", source="live"):
    row = {"id": next(_ids), "at": _at(day, hh, mm), "equity": equity, "realized_balance": realized,
           "unrealized_pnl": unrealized, "open_n": open_n, "skipped_n": 0, "source": source, "kind": kind}
    if notional is not None:                 # a NULL column is an absent key (merge_doc)
        row["open_notional"] = notional
    if approx is not None:
        row["open_notional_approx"] = approx
    return row


def test_rows_by_session_keeps_point_rows_in_time_order():
    late, early = _row(TUE, 15, 55), _row(TUE, 9, 35)
    rows = [late, _row(TUE, 9, 35, kind="day_high"), early, _row(date(2026, 11, 7), 16, 0)]
    assert bs.rows_by_session(rows, [MON, TUE]) == {TUE: [early, late]}


def test_exposure_is_time_weighted_to_the_close():
    by_day = {TUE: [_row(TUE, 9, 30, notional=0.0, open_n=0),
                    _row(TUE, 15, 0, notional=5_000.0, open_n=2)]}
    exp = bs.exposure_by_session(by_day)[TUE]
    assert exp.pct == pytest.approx(0.5 * 1.0 / 6.5)        # 5.5 h at 0 %, 1 h at 50 %
    assert (exp.open_n, exp.approx) == (2, False)


def test_a_half_day_weights_to_the_1300_close():
    by_day = {HALF_DAY: [_row(HALF_DAY, 9, 30, notional=0.0), _row(HALF_DAY, 12, 0, notional=5_000.0)]}
    assert bs.exposure_by_session(by_day)[HALF_DAY].pct == pytest.approx(0.5 * 1.0 / 3.5)


def test_a_lone_close_sample_falls_back_to_its_own_value():
    by_day = {TUE: [_row(TUE, 16, 0, notional=2_000.0, approx=True, source="backfill")]}
    assert bs.exposure_by_session(by_day)[TUE] == bs.Exposure(pytest.approx(0.2), 0, True)


def test_no_open_notional_means_no_exposure_value_not_zero():
    exp = bs.exposure_by_session({TUE: [_row(TUE, 10, 0, open_n=1), _row(TUE, 15, 55, open_n=3)]})[TUE]
    assert (exp.pct, exp.open_n, exp.approx) == (None, 3, False)


def _deployed(by_day, legs=()):
    return bs.deployed_returns(by_day, list(legs), [MON, TUE, WED])


def test_an_intraday_round_trip_is_divided_by_its_peak_notional():
    by_day = {MON: [_row(MON, 15, 55, notional=0.0)],
              TUE: [_row(TUE, 10, 0, notional=10_000.0, unrealized=50.0),
                    _row(TUE, 12, 0, notional=0.0), _row(TUE, 15, 55, notional=0.0)]}
    out = _deployed(by_day, [RealizedLeg(_at(TUE, 11, 30), Decimal("200"), "t1")])
    assert out[TUE] == bs.Deployed(pytest.approx(0.02), False, False, None)
    assert bs.exposure_by_session(by_day)[TUE].pct == pytest.approx(2 / 6)   # the time-weighted view


def test_a_zero_exposure_day_is_not_chained():
    by_day = {MON: [_row(MON, 15, 55, notional=0.0)], TUE: [_row(TUE, 15, 55, notional=0.0)]}
    assert _deployed(by_day)[TUE] == bs.Deployed(None, False, False, "no_exposure")


@pytest.mark.parametrize("notional, expected", [
    (499.0, bs.Deployed(None, False, False, "below_min")),     # under 5 % of 10 000
    (500.0, bs.Deployed(pytest.approx(0.1), False, False, None)),
])
def test_the_five_percent_floor(notional, expected):
    by_day = {MON: [_row(MON, 15, 55, notional=notional)],
              TUE: [_row(TUE, 15, 55, notional=notional, unrealized=notional * 0.1)]}
    assert bs.DEPLOYED_MIN_SHARE == 0.05
    assert _deployed(by_day)[TUE] == expected


def test_a_short_gapping_past_minus_100_percent_is_clipped_and_flagged():
    by_day = {MON: [_row(MON, 15, 55, notional=1_000.0)],
              TUE: [_row(TUE, 15, 55, notional=0.0, realized=7_500.0, equity=7_500.0)]}
    out = _deployed(by_day, [RealizedLeg(_at(TUE, 9, 31), Decimal("-2500"), "short1")])
    assert out[TUE] == bs.Deployed(-1.0, True, False, None)


def test_a_base_balance_edit_never_enters_the_deployed_return():
    by_day = {MON: [_row(MON, 15, 55, notional=2_000.0, unrealized=40.0)],
              TUE: [_row(TUE, 15, 55, notional=2_000.0, unrealized=40.0, realized=10_500.0)]}
    assert _deployed(by_day)[TUE] == bs.Deployed(0.0, False, False, None)


def test_missing_inputs_are_missing_never_zero():
    no_notional = {MON: [_row(MON, 15, 55)], TUE: [_row(TUE, 15, 55, open_n=1)]}
    out = _deployed(no_notional)
    assert out[MON] == bs.Deployed(None, False, False, "missing")    # no previous session
    assert out[TUE] == bs.Deployed(None, False, False, "missing")    # no open_notional at all
    assert out[WED] == bs.Deployed(None, False, False, "missing")    # no rows


def test_a_gap_measures_from_the_last_session_with_rows_and_approx_is_carried():
    by_day = {MON: [_row(MON, 16, 0, notional=1_000.0, approx=True, source="backfill")],
              WED: [_row(WED, 15, 55, notional=1_000.0, unrealized=30.0)]}
    assert _deployed(by_day)[WED] == bs.Deployed(pytest.approx(0.03), False, True, None)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_deployed.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'rows_by_session'`.

- [ ] **Step 3: Extend `swingbot/core/analytics/benchmark_series.py`**

Add the constant, both dataclasses and the three public functions with the
signatures above, plus private helpers so each stays well under 15:
`_close_at(day) -> datetime` (UTC instant of `session_close(day)` in NY),
`_weights(points, day) -> list[float]` (seconds; the rule above),
`_usable(points) -> list[dict]` (has `open_notional`, `equity > 0`),
`_approx(rows) -> bool`, `_peak_notional(rows) -> float | None`, and
`_deployed_day(points, prev, legs) -> Deployed` (steps 2–5). Docstrings name
the spec rule each implements ("peak, not mean: a one-hour round trip is not
inflated ~6.5×"; "trade P&L only: base_balance and cash never enter").

- [ ] **Step 4: Run both series test files and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_deployed.py`
then `python scripts/dev/testrun.py file tests/analytics/test_benchmark_series.py`
Expected: PASS, 0 failed, both.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/benchmark_series.py tests/analytics/test_benchmark_deployed.py
git commit -m "feat(v208): benchmark_series -- exposure and Bot deployed return (peak denominator, 5% floor, -100% clip)"
```

### Task V208-10: `benchmark_view.py`: session state, range clamp, rebase, series, markers, exposure

**Model:** opus — the rebase point, the no-lookahead cut for today and the first-day rule decide every number on the chart; V208-10b and the SPA build on this frame.

**Files:**
- Create: `swingbot/core/analytics/benchmark_view.py`
- Create: `tests/analytics/test_benchmark_view.py` (suite `analytics`)

**Interfaces:**
- Consumes:
  - V208-8/9 (`benchmark_series as bs`): `bot_session_closes`, `base_balance_breaks`, `align`, `AlignedDay`, `rows_by_session`, `exposure_by_session`, `Exposure`, `deployed_returns`, `Deployed`.
  - V208-5: `swingbot.core.marketdata.benchmarks.BENCHMARK_SYMBOLS` (`("SPY", "QQQ", "^IXIC", "^DJI")`), `TOTAL_RETURN` (`frozenset({"SPY", "QQQ"})`).
  - Existing `swingbot.core.market.session`: `now_et`, `is_nyse_regular_session`, `session_close`, `nyse_calendar` (pure: built from the frozen holiday table), `US_MARKET_TZ`.
- Produces (V208-10b and V208-11 consume; names final):
  - `SERIES_KEYS = ("bot_account", "bot_deployed", "SPY", "QQQ", "^IXIC", "^DJI")`; `LABELS` = `{"bot_account": "Bot · account", "bot_deployed": "Bot · deployed", "SPY": "SPY", "QQQ": "QQQ", "^IXIC": "Nasdaq Comp. (price)", "^DJI": "Dow (price)"}`.
  - `pct(x: float | None) -> float | None` — `None` → `None`, else `round(x * 100, 4)`.
  - `@dataclass(frozen=True) BenchmarkInputs(rows: list[dict], legs: list[RealizedLeg], bars: list[dict], sessions: list[date], now: datetime, account_currency: str, mixed_tickers: list[str], refresher_on: bool)` — docstring states what V208-11 loads: `rows` = `equity_samples_repo().list_rows()`; `legs` = `equity.realized_legs(equity.main_book(trades))`; `sessions` = `nyse_calendar().sessions(live_since, market_today(now))` (`[]` when there are no rows); `bars` = `benchmark_bars_repo().list_range(BENCHMARK_SYMBOLS, sessions[0], sessions[-1])`; `now` aware UTC. Sessions before the first row's NY date are tolerated (ignored).
  - `view_session_state(now: datetime) -> str` — `"open"` when `is_nyse_regular_session(now)`; `"closed"` when today (NY) is an NYSE session and NY time ≥ `session_close(today)`; else `"pre"` (before the open, weekends, holidays).
  - `live_since_of(rows: list[dict]) -> date | None` — NY date of the earliest row (any source, any kind).
  - `completed_sessions(inputs: BenchmarkInputs, state: str) -> list[date]` — every session `< today`, plus today when `state == "closed"` and all four `BENCHMARK_SYMBOLS` have a `final` bar for today.
  - `@dataclass(frozen=True) RangeSpec(sessions: list[date], base: date | None, live_since: date | None, clamped: bool, is_all: bool)`.
  - `clamp_range(completed: list[date], live_since: date | None, start: date | None, end: date | None) -> RangeSpec`.
  - `index_pct(bars: list[dict], *, final_only: bool = True) -> dict[str, dict[date, tuple[float | None, bool]]]` — a key for every `BENCHMARK_SYMBOLS` symbol; `proxy = source_symbol != symbol`.
  - `@dataclass(frozen=True) Frame(rng: RangeSpec, days: list[AlignedDay], base_close: float | None, closes: dict[date, float], deployed: dict[date, Deployed], exposure: dict[date, Exposure], pct: dict[str, dict[date, tuple[float | None, bool]]])` — `days` = the in-range sessions only; `closes`, `deployed`, `exposure` cover every session up to today (the Today card reads today's partial values from them); `pct` holds final bars only.
  - `build_frame(inputs: BenchmarkInputs, rng: RangeSpec) -> Frame`.
  - `deployed_counts(day: AlignedDay, dep: Deployed | None) -> bool` — the deployed line chains this day: `not day.missing and day.bot_ret is not None and dep is not None and dep.ret is not None`.
  - `build_series(frame: Frame) -> tuple[list[dict], list[dict], list[dict]]` — `(series, markers, exposure)` in the response-contract shapes.

Rules (spec § Bot · account daily series, § Gaps, § Exposure; Global Constraints; Review Focus 2):

- **Clamp.** `eligible` = completed sessions `≥ live_since`. Range = eligible
  sessions in `[max(start, eligible[0]), end]` (`start`/`end` `None` = open).
  `clamped` = `start is not None and start < eligible[0]`. `is_all` = (`start`
  is `None` or `≤ eligible[0]`) and (`end` is `None` or `≥ eligible[-1]`).
  `base` = the eligible session just before the range's first, else `None`.
  No eligible or no in-range session → `RangeSpec([], None, live_since, False, start is None and end is None)`.
- **Frame.** `today = now_et(now).date()`; `upto` = `inputs.sessions` `≤ today`
  and `≥ live_since`. `closes = bs.bot_session_closes(rows, upto)`. Align over
  `through` = `upto` sessions `≤ rng.sessions[-1]` (from `live_since`, so a
  gap at the range start still finds the earlier close), breaks from
  `bs.base_balance_breaks(rows, legs, through)`; keep the in-range days.
  **First-day rule:** the first non-missing in-range day whose `span` exceeds
  its position + 1 (its return reaches before the range) gets
  `dataclasses.replace(day, bot_ret=None)`: no return is counted, the bot
  line starts at 0 on that close. `deployed` and `exposure` from
  `bs.rows_by_session(rows, upto)`.
- **Points** (`_point(date, cum, day, *, span=1, missing=False, proxy=False,
  approx=False, clipped=False)`; `cum`/`day` go through `pct`). When
  `rng.base` exists every series starts with a base point (`cum 0.0`, `day
  None`); the bot lines' base point is `cum None, missing True` when
  `base_close` is `None`. In-range, per series:
  - *bot_account:* missing → `cum None, day None, missing`; counted
    (`bot_ret` set, not `base_break`) → chained; `base_break` or `bot_ret
    None` → `cum` carries flat, `day None`. `span` from the day.
  - *bot_deployed:* missing day → missing point; `deployed_counts` → chained,
    `approx`/`clipped` from the `Deployed`; else flat, `day None`, `approx` kept.
  - *index:* own `(pct, proxy)` from `frame.pct`; `pct None` → `cum None, day
    None, missing`; the first in-range session when `rng.base` is `None` is
    `cum 0.0, day None` (both sides lose that return: N one fewer).
    Non-final bars never reach `frame.pct` (no-lookahead).
- Series dicts: `{"key", "label": LABELS[key], "kind": "bot" | "index",
  "total_return": key not in ("^IXIC", "^DJI"), "points"}`, in `SERIES_KEYS`
  order. Markers: `{"date", "kind": "base_balance"}` per in-range `base_break`.
  Exposure: one `{"date", "pct", "open_n", "approx"}` per in-range session
  (`pct` through `pct()`; no `Exposure` → `None, 0, False`).

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_benchmark_view.py`:

```python
"""v208 V208-10: session state, clamp, rebase, series, markers, exposure."""
from datetime import date, datetime, timezone
from itertools import count

import pytest

from swingbot.core.analytics import benchmark_view as bv
from swingbot.core.market.session import US_MARKET_TZ

UTC = timezone.utc
MON, TUE, WED, THU, FRI = (date(2026, 11, d) for d in (2, 3, 4, 5, 6))
WEEK = [MON, TUE, WED, THU, FRI]
OPEN_FRI = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)          # 10:00 ET
CLOSED_FRI = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)        # 17:00 ET
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")
_ids = count(1)


def _row(day, hh, mm, equity, *, realized=10_000.0, notional=None):
    at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(UTC)
    row = {"id": next(_ids), "at": at, "equity": equity, "realized_balance": realized,
           "unrealized_pnl": equity - realized, "open_n": 1, "skipped_n": 0,
           "source": "live", "kind": "point"}
    if notional is not None:
        row["open_notional"] = notional
    return row


def _bar(symbol, day, pct, *, final=True):
    return {"symbol": symbol, "session": day, "close": None, "adj_close": None, "day_pct": pct,
            "source_symbol": symbol, "final": final, "as_of": OPEN_FRI}


ROWS = [_row(MON, 15, 55, 10_000.0, notional=5_000.0), _row(TUE, 15, 55, 10_100.0),
        _row(THU, 15, 55, 10_302.0), _row(FRI, 10, 0, 10_400.0)]            # WED missing
BARS = [_bar("SPY", d, p) for d, p in ((MON, 0.001), (TUE, 0.01), (WED, 0.02), (THU, -0.01))] \
    + [_bar("SPY", FRI, 0.005, final=False)]


def _inputs(rows=ROWS, bars=BARS, now=OPEN_FRI, sessions=WEEK):
    return bv.BenchmarkInputs(rows=list(rows), legs=[], bars=list(bars), sessions=list(sessions),
                              now=now, account_currency="USD", mixed_tickers=[], refresher_on=True)


def _series(inputs, start=None, end=None):
    completed = bv.completed_sessions(inputs, bv.view_session_state(inputs.now))
    rng = bv.clamp_range(completed, bv.live_since_of(inputs.rows), start, end)
    series, markers, exposure = bv.build_series(bv.build_frame(inputs, rng))
    return {s["key"]: s for s in series}, markers, exposure


def _pts(series, key):
    return [(p["date"], p["cum_pct"], p["day_pct"], p["span"], p["missing"]) for p in series[key]["points"]]


def test_pct_is_a_rounded_percentage():
    assert bv.pct(0.012345678) == 1.2346 and bv.pct(None) is None and bv.pct(0.0) == 0.0


@pytest.mark.parametrize("now, state", [
    (datetime(2026, 11, 4, 15, 0, tzinfo=UTC), "open"),
    (datetime(2026, 11, 4, 12, 0, tzinfo=UTC), "pre"),
    (datetime(2026, 11, 4, 21, 0, tzinfo=UTC), "closed"),     # 16:00 ET
    (datetime(2026, 11, 7, 15, 0, tzinfo=UTC), "pre"),        # Saturday
    (datetime(2026, 11, 26, 17, 0, tzinfo=UTC), "pre"),       # Thanksgiving
    (datetime(2026, 11, 27, 17, 30, tzinfo=UTC), "open"),     # half day, 12:30 ET
    (datetime(2026, 11, 27, 18, 30, tzinfo=UTC), "closed"),   # half day, 13:30 ET
])
def test_view_session_state(now, state):
    assert bv.view_session_state(now) == state


def test_today_joins_only_once_closed_with_four_final_bars():
    final_fri = [_bar(s, FRI, 0.0) for s in SYMBOLS]
    assert bv.completed_sessions(_inputs(bars=final_fri), "open") == [MON, TUE, WED, THU]
    assert bv.completed_sessions(_inputs(bars=final_fri, now=CLOSED_FRI), "closed") == WEEK
    one_late = final_fri[:3] + [_bar("^DJI", FRI, 0.0, final=False)]
    assert bv.completed_sessions(_inputs(bars=one_late, now=CLOSED_FRI), "closed") == [MON, TUE, WED, THU]


@pytest.mark.parametrize("live, start, end, expected", [
    (MON, None, None, bv.RangeSpec([MON, TUE, WED, THU], None, MON, False, True)),
    (TUE, date(2026, 10, 1), None, bv.RangeSpec([TUE, WED, THU], None, TUE, True, True)),
    (MON, WED, THU, bv.RangeSpec([WED, THU], TUE, MON, False, False)),
    (MON, MON, WED, bv.RangeSpec([MON, TUE, WED], None, MON, False, False)),
])
def test_clamp_range(live, start, end, expected):
    assert bv.clamp_range([MON, TUE, WED, THU], live, start, end) == expected


def test_clamp_range_with_no_live_book():
    assert bv.clamp_range([], None, None, None) == bv.RangeSpec([], None, None, False, True)


def test_the_all_range_starts_on_the_first_close_and_counts_one_fewer_return():
    series, _, _ = _series(_inputs())
    bot = _pts(series, "bot_account")
    assert [p[0] for p in bot] == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert bot[0] == ("2026-11-02", 0.0, None, 1, False)
    assert bot[1] == ("2026-11-03", pytest.approx(1.0), pytest.approx(1.0), 1, False)
    assert bot[2] == ("2026-11-04", None, None, 1, True)                 # missing, never 0 %
    assert bot[3] == ("2026-11-05", pytest.approx(3.02), pytest.approx(2.0), 2, False)
    spy = _pts(series, "SPY")
    assert spy[0][1:3] == (0.0, None) and spy[3][1] == pytest.approx(1.9898)
    assert "2026-11-06" not in [p[0] for p in spy]                       # non-final today stays out
    assert [s["key"] for s in series.values()] == list(bv.SERIES_KEYS)
    assert (series["^DJI"]["label"], series["^DJI"]["total_return"]) == ("Dow (price)", False)
    assert series["QQQ"]["total_return"] and series["bot_deployed"]["kind"] == "bot"


def test_a_range_rebases_on_the_prior_close_and_counts_its_first_return():
    series, _, _ = _series(_inputs(), start=TUE, end=THU)
    assert _pts(series, "bot_account")[:2] == [("2026-11-02", 0.0, None, 1, False),
                                               ("2026-11-03", pytest.approx(1.0), pytest.approx(1.0), 1, False)]
    assert _pts(series, "SPY")[1][2] == pytest.approx(1.0)


def test_a_gap_reaching_before_the_range_counts_no_return():
    series, _, _ = _series(_inputs(), start=THU)
    assert _pts(series, "bot_account") == [("2026-11-04", None, None, 1, True),
                                           ("2026-11-05", 0.0, None, 2, False)]
    assert _pts(series, "SPY") == [("2026-11-04", 0.0, None, 1, False),
                                   ("2026-11-05", pytest.approx(-1.0), pytest.approx(-1.0), 1, False)]


def test_a_base_balance_session_carries_flat_and_gets_a_marker():
    rows = [_row(MON, 15, 55, 10_000.0), _row(TUE, 15, 55, 10_600.0, realized=10_500.0),
            _row(THU, 15, 55, 10_812.0, realized=10_500.0)]
    series, markers, _ = _series(_inputs(rows=rows))
    bot = _pts(series, "bot_account")
    assert bot[1] == ("2026-11-03", 0.0, None, 1, False)
    assert bot[3][1:3] == (pytest.approx(2.0), pytest.approx(2.0))
    assert markers == [{"date": "2026-11-03", "kind": "base_balance"}]


def test_deployed_below_the_floor_carries_flat_and_is_not_missing():
    rows = [_row(MON, 15, 55, 10_000.0, notional=100.0), _row(TUE, 15, 55, 10_100.0, notional=100.0)]
    dep = _pts(_series(_inputs(rows=rows))[0], "bot_deployed")
    assert dep[1] == ("2026-11-03", 0.0, None, 1, False)


def test_deployed_chains_on_its_peak_denominator():
    dep = _pts(_series(_inputs())[0], "bot_deployed")
    assert dep[1][1:3] == (pytest.approx(2.0), pytest.approx(2.0))       # P 100 / D 5 000


def test_exposure_rows_are_percentages_and_missing_is_none():
    _, _, exposure = _series(_inputs())
    assert [e["date"] for e in exposure] == ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"]
    assert exposure[0] == {"date": "2026-11-02", "pct": 50.0, "open_n": 1, "approx": False}
    assert exposure[2] == {"date": "2026-11-04", "pct": None, "open_n": 0, "approx": False}


def test_no_live_book_is_empty_points_never_zeros():
    series, markers, exposure = _series(_inputs(rows=[], bars=[], sessions=[]))
    assert all(s["points"] == [] for s in series.values()) and markers == [] and exposure == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_view.py`
Expected: FAIL — `ImportError: cannot import name 'benchmark_view'`.

- [ ] **Step 3: Create `swingbot/core/analytics/benchmark_view.py`**

Module docstring: v208; pure (no I/O, no clock: `now` is an input); fractions
inside, percentages only at the response edge via `pct`; a `final = false`
bar and today's partial candle never enter `Frame.days` (no-lookahead).

Write the constants, dataclasses and functions above with these private
helpers (each < 15): `_today(now) -> date`, `_final_today(bars, today) ->
bool`, `_trim_first_span(days) -> list[AlignedDay]`, `_point(...)`,
`_bot_points(frame)`, `_deployed_points(frame)`, `_index_points(frame, sym)`,
`_base_point(frame, *, bot: bool) -> list[dict]`, `_chain(cum, r) -> float`
(`(1 + cum) * (1 + r) - 1`), `_markers(frame)`, `_exposure_rows(frame)`.
`build_frame` with no in-range sessions returns `Frame(rng, [], None, closes,
deployed, exposure, pct)` (still filled for the Today card).

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_view.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/benchmark_view.py tests/analytics/test_benchmark_view.py
git commit -m "feat(v208): benchmark_view -- session state, range clamp, rebase, series, markers, exposure"
```

### Task V208-10b: `benchmark_view.py`: stats, vs, capture, daily rows, Today card, status, `build_benchmark`

**Model:** opus — this assembles the one response the tab renders; which pairs reach beta/alpha/capture/Beat?, the headline flag, and the `—` vs `0%` rules are integrity calls, not formatting.

**Files:**
- Modify: `swingbot/core/analytics/benchmark_view.py` (created by V208-10)
- Create: `tests/analytics/test_benchmark_response.py` (suite `analytics`)

**Interfaces:**
- Consumes:
  - V208-10: `BenchmarkInputs`, `SERIES_KEYS`, `pct`, `view_session_state`, `live_since_of`, `completed_sessions`, `clamp_range`, `RangeSpec`, `build_frame`, `Frame`, `deployed_counts`, `build_series`.
  - V208-7 (`benchmark as bm`): `total_return`, `cumulative`, `max_drawdown`, `money_drawdown`, `losing_streak`, `sharpe`, `beta`, `alpha`, `capture`, `beat_count`, `Estimate`, `Capture`, `BeatCount`, `CAPTURE_REASON`.
  - V208-5: `BENCHMARK_SYMBOLS`. Existing `session.session_close`, `US_MARKET_TZ`.
- Produces (V208-11 serves it; the index's **response contract** is the shape):
  - `build_benchmark(inputs: BenchmarkInputs, *, start: date | None, end: date | None, capture: str) -> dict` — every contract key except `daily_has_more` (V208-11 adds it after paging); `daily` complete, newest first. Raises `ValueError("capture must be one of ...")` when `capture not in BENCHMARK_SYMBOLS` (V208-11 validates first; this is the backstop).
  - `stat(value: float | None, n: int, reason: str | None = None) -> dict` — `{"value", "n", "reason"}`.
  - `last_closed_session(sessions: Sequence[date], now: datetime) -> date | None` — latest session whose NY `session_close` instant is `≤ now`.
  - `benchmarks_status(bars: list[dict], last_closed: date | None, refresher_on: bool) -> tuple[str, date | None]`.

Rules (spec § Stats, § API Today card contract, § Gaps; Global Constraints):

- **Account returns** `r` = in-range days with `bot_ret` set and not
  `base_break`, in order (span rows included). `total_pct`, `max_dd_pct`,
  `losing_streak`, `money_dd` use `r`; `sharpe` only the `one_session` days.
  `money_dd`: anchor = `frame.base_close`, else the first in-range
  `bot_close`; closes `anchor × (1 + c)` for `c` in `[0.0] +
  bm.cumulative(r)` (a break carries flat, never a money jump); value
  `round(bm.money_drawdown(...), 2)`; no anchor → `None`.
- **Deployed returns** = in-range days where `deployed_counts(day,
  frame.deployed.get(day.session))`; `sharpe` on those with `span == 1`.
  `approx_share` = `pct(share of in-range sessions whose Deployed.approx)`
  (`None` without sessions); `money_dd = stat(None, n, "account line only")`.
  `bot_account.approx_share` is `None`.
- **Index returns** = own `day_pct` (final bars, `frame.pct`) of the in-range
  sessions, skipping `None`s and, when `rng.base` is `None`, the first
  session. Index entries carry only `total_pct`, `max_dd_pct`, `sharpe`.
- Stat values: `total_pct`/`max_dd_pct`/`up_pct`/`down_pct` and alpha →
  `pct(...)`; `sharpe`, beta `value`/`se`, alpha `t`, `ratio` →
  `round(x, 4)` (`None` stays `None`); every guarded result keeps its `n`
  and `reason`.
- **vs[sym]**: pairs = in-range `one_session` days with `index_ret[sym]` set.
  `lead_pp = stat(round(pct(bot_total) − pct(idx_total), 4), n_bot)`
  (`None` if either total is `None`); `beta = {"value", "se", "n",
  "reason"}`; `alpha = {"value", "t", "n", "reason", "headline"}`,
  `headline = rng.is_all and sym == "SPY"`.
- **capture**: the same pairs for the `capture` index → `bm.capture`,
  `bm.beat_count`; `up_pct = stat(pct(up), up_n, reason)`, `down_pct =
  stat(pct(down), down_n, reason)`, `ratio = stat(round(ratio, 4), up_n +
  down_n, reason)`, plus `index`, `up_n`, `down_n`, `beat` (BeatCount fields).
- **daily** (newest first, every in-range session): `lines` has every
  `SERIES_KEYS` key — `bot_account` = `pct(bot_ret)` when counted else
  `None`; `bot_deployed` = `pct(ret)` when `deployed_counts` else `None`;
  each index its own `pct(day_pct)` (missing bot sessions still show index
  cells); `exposure_pct`, `open_n` from `frame.exposure` (`None`, `0`);
  `beat` = `bot_ret > index_ret[capture]` on a `one_session` day with that
  index return, else `None`; `span`, `missing`.
- **today**: `session` = today (NY) when the state is not `"pre"` and today
  is in `inputs.sessions`; otherwise the last completed session; neither →
  `{"session": None, "final": False, "lines": {}}`. `final` = `session in
  completed`. `bot_account` = `pct(closes[session] / closes[prev] − 1)`
  where `prev` is the latest earlier session with a close; no close today
  (or no `prev`) → `pct None` — **never 0**. `bot_deployed` =
  `pct(frame.deployed[session].ret)`. Index lines from the bar for
  `(sym, session)` final or not: `{"pct": pct(day_pct), "final":
  bar["final"]}`; no bar → `{"pct": None, "final": False}`. Bot lines'
  `final` = the card's `final`.
- **Status**: no bars → `("empty", None)`. `last` = newest `final` bar
  session over all symbols. Refresher off and (`last is None` or `last <
  last_closed`) → `"stale"`; else `"ok"`. `benchmarks_last_session` = `last`
  as ISO.
- `range` = `{"from", "to"}` (first/last in-range session, ISO or `None`),
  `live_since`, `sessions_n` (in-range sessions), `clamped`, `is_all`.
  `as_of = inputs.now.isoformat()`; `account_currency` and
  `list(mixed_tickers)` passed through.

- [ ] **Step 1: Write the failing tests**

`tests/analytics/test_benchmark_response.py`:

```python
"""v208 V208-10b: stats, vs, capture, daily rows, Today card, status, the response."""
from datetime import date, datetime, timezone
from itertools import count

import pytest

from swingbot.core.analytics import benchmark as bm
from swingbot.core.analytics import benchmark_view as bv
from swingbot.core.market.session import US_MARKET_TZ, nyse_calendar

UTC = timezone.utc
THU, FRI = date(2026, 11, 5), date(2026, 11, 6)
SESS = nyse_calendar().sessions(date(2026, 6, 1), THU)[-71:]      # 71 closes -> 70 returns
PRE_FRI = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)                # 07:00 ET
OPEN_FRI = datetime(2026, 11, 6, 15, 0, tzinfo=UTC)               # 10:00 ET
CLOSED_FRI = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)             # 17:00 ET
SYMBOLS = ("SPY", "QQQ", "^IXIC", "^DJI")
_ids = count(1)


def _idx(i):
    return 0.01 if i % 2 else -0.008             # 35 up / 35 down sessions over i = 1..70


def _bot(i):
    return 0.5 * _idx(i) + 0.0004 * (i % 3)


def _row(day, equity, *, hh=15, mm=55, realized=10_000.0, notional=None):
    at = datetime(day.year, day.month, day.day, hh, mm, tzinfo=US_MARKET_TZ).astimezone(UTC)
    row = {"id": next(_ids), "at": at, "equity": equity, "realized_balance": realized,
           "unrealized_pnl": equity - realized, "open_n": 1, "skipped_n": 0, "source": "live", "kind": "point"}
    if notional is not None:
        row["open_notional"] = notional
    return row


def _book(skip=(), jump_at=None, notional=None):
    rows, equity, realized = [], 10_000.0, 10_000.0
    for i, day in enumerate(SESS):
        equity *= 1 + (_bot(i) if i else 0.0)
        if i == jump_at:                          # a base_balance edit: no leg explains it
            realized += 500.0
            equity += 500.0
        if i not in skip:
            rows.append(_row(day, round(equity, 2), realized=realized, notional=notional))
    return rows


def _bar(symbol, day, pct, final=True):
    return {"symbol": symbol, "session": day, "close": None, "adj_close": None, "day_pct": pct,
            "source_symbol": symbol, "final": final, "as_of": OPEN_FRI}


def _bars(fri=True, final_fri=False):
    bars = [_bar(s, d, _idx(i)) for s in SYMBOLS for i, d in enumerate(SESS)]
    return bars + ([_bar(s, FRI, 0.004, final_fri) for s in SYMBOLS] if fri else [])


def _inputs(rows=None, bars=None, now=OPEN_FRI, refresher_on=True, currency="USD", mixed=(), sessions=None):
    return bv.BenchmarkInputs(rows=_book() if rows is None else rows, legs=[],
                              bars=_bars() if bars is None else bars,
                              sessions=[*SESS, FRI] if sessions is None else sessions, now=now,
                              account_currency=currency, mixed_tickers=list(mixed), refresher_on=refresher_on)


def _body(inputs, start=None, end=None, capture="SPY"):
    return bv.build_benchmark(inputs, start=start, end=end, capture=capture)


def _day(body, i):
    return next(r for r in body["daily"] if r["date"] == SESS[i].isoformat())


def test_the_response_carries_every_contract_key():
    body = _body(_inputs())
    assert set(body) == {"range", "as_of", "session_state", "account_currency", "mixed_tickers",
                         "benchmarks_status", "benchmarks_last_session", "today", "series", "markers",
                         "exposure", "stats", "vs", "capture", "daily"}
    assert body["range"] == {"from": SESS[0].isoformat(), "to": THU.isoformat(),
                             "live_since": SESS[0].isoformat(), "sessions_n": 71,
                             "clamped": False, "is_all": True}
    assert (body["as_of"], body["session_state"]) == (OPEN_FRI.isoformat(), "open")
    assert set(body["stats"]) == set(bv.SERIES_KEYS) and set(body["vs"]) == set(SYMBOLS)
    assert set(body["stats"]["bot_account"]) == {"total_pct", "max_dd_pct", "sharpe", "money_dd",
                                                 "losing_streak", "approx_share"}
    assert set(body["stats"]["SPY"]) == {"total_pct", "max_dd_pct", "sharpe"}
    assert body["stats"]["bot_account"]["total_pct"]["n"] == 70
    assert body["stats"]["bot_account"]["approx_share"] is None
    assert body["stats"]["bot_account"]["money_dd"]["value"] <= 0


def test_beta_alpha_lead_and_the_headline_on_the_all_range():
    body = _body(_inputs())
    spy = body["vs"]["SPY"]
    assert set(spy) == {"lead_pp", "beta", "alpha"}
    assert (spy["beta"]["n"], spy["beta"]["reason"]) == (70, None)
    assert spy["beta"]["value"] == pytest.approx(0.5, abs=0.05) and spy["beta"]["se"] is not None
    assert spy["alpha"]["n"] == 70 and spy["alpha"]["value"] is not None
    assert spy["alpha"]["headline"] is True and body["vs"]["QQQ"]["alpha"]["headline"] is False
    lead = body["stats"]["bot_account"]["total_pct"]["value"] - body["stats"]["SPY"]["total_pct"]["value"]
    assert spy["lead_pp"]["value"] == pytest.approx(lead, abs=1e-3)


def test_short_ranges_keep_n_and_say_why():
    body = _body(_inputs(), start=SESS[-19])
    beta, alpha = body["vs"]["SPY"]["beta"], body["vs"]["SPY"]["alpha"]
    assert (beta["value"], beta["n"], beta["reason"]) == (None, 19, "needs ≥ 20 sessions")
    assert (alpha["value"], alpha["reason"], alpha["headline"]) == (None, "needs ≥ 60 sessions", False)
    assert body["stats"]["bot_account"]["sharpe"] == {"value": None, "n": 19, "reason": "needs ≥ 20 sessions"}
    assert body["capture"]["up_pct"]["value"] is None
    assert body["capture"]["up_pct"]["reason"] == bm.CAPTURE_REASON
    assert (body["range"]["is_all"], body["range"]["sessions_n"]) == (False, 19)


def test_a_missing_session_counts_toward_total_but_never_toward_pairs():
    body = _body(_inputs(rows=_book(skip={40})))
    assert body["stats"]["bot_account"]["total_pct"]["n"] == 69
    assert body["vs"]["SPY"]["beta"]["n"] == 68
    gap, span = _day(body, 40), _day(body, 41)
    assert gap["missing"] and gap["lines"]["bot_account"] is None and gap["beat"] is None
    assert gap["lines"]["SPY"] == pytest.approx(bv.pct(_idx(40)))      # the index cell still shows
    assert span["span"] == 2 and span["beat"] is None and span["lines"]["bot_account"] is not None


def test_a_base_balance_session_is_left_out_of_every_stat():
    body = _body(_inputs(rows=_book(jump_at=30)))
    assert body["stats"]["bot_account"]["total_pct"]["n"] == 69
    assert body["vs"]["SPY"]["beta"]["n"] == 69
    assert body["markers"] == [{"date": SESS[30].isoformat(), "kind": "base_balance"}]
    assert _day(body, 30)["lines"]["bot_account"] is None


def test_capture_and_beat_use_the_selected_index():
    cap = _body(_inputs(), capture="QQQ")["capture"]
    assert cap["index"] == "QQQ" and (cap["up_n"], cap["down_n"]) == (35, 35)
    assert cap["up_pct"]["reason"] is None and cap["up_pct"]["value"] == pytest.approx(50.0, abs=5.0)
    assert cap["ratio"]["value"] == pytest.approx(cap["up_pct"]["value"] / cap["down_pct"]["value"], rel=1e-3)
    assert cap["beat"] == {"up_days": 35, "up_beat": 0, "down_days": 35, "down_beat": 35}


def test_daily_rows_are_newest_first_and_complete():
    daily = _body(_inputs())["daily"]
    assert [r["date"] for r in daily] == [d.isoformat() for d in reversed(SESS)]
    assert set(daily[0]) == {"date", "lines", "exposure_pct", "open_n", "beat", "span", "missing"}
    assert set(daily[0]["lines"]) == set(bv.SERIES_KEYS)
    assert daily[-1]["lines"]["bot_account"] is None        # the first live session has no prior close


def test_deployed_stats_carry_the_approximated_share():
    rows = _book(notional=3_000.0)
    for row in rows[:36]:
        row["open_notional_approx"] = True
    stats = _body(_inputs(rows=rows))["stats"]["bot_deployed"]
    assert stats["total_pct"]["n"] == 70
    # sessions 1..36 (36 via its approx previous close); session 0 has no previous close -> not approx
    assert stats["approx_share"] == pytest.approx(36 / 71 * 100, abs=1e-3)
    assert stats["money_dd"] == {"value": None, "n": 70, "reason": "account line only"}


def test_today_while_open_with_a_sample():
    prev = _book()[-1]["equity"]
    today = _body(_inputs(rows=_book() + [_row(FRI, 10_100.0, hh=10, mm=0)]))["today"]
    assert (today["session"], today["final"]) == ("2026-11-06", False)
    assert today["lines"]["bot_account"] == {"pct": pytest.approx(bv.pct(10_100.0 / prev - 1)), "final": False}
    assert today["lines"]["SPY"] == {"pct": 0.4, "final": False}


def test_today_while_open_without_a_sample_is_a_dash_never_zero():
    today = _body(_inputs())["today"]
    assert today["lines"]["bot_account"] == {"pct": None, "final": False}
    assert today["lines"]["SPY"]["pct"] == 0.4


def test_before_the_open_the_card_is_the_last_completed_session_and_final():
    today = _body(_inputs(now=PRE_FRI, bars=_bars(fri=False)))["today"]
    assert (today["session"], today["final"]) == (THU.isoformat(), True)
    assert today["lines"]["bot_account"]["final"] is True
    assert today["lines"]["SPY"] == {"pct": bv.pct(_idx(70)), "final": True}


def test_after_the_close_with_final_bars_today_is_final_and_joins_the_series():
    body = _body(_inputs(rows=_book() + [_row(FRI, 10_100.0)], now=CLOSED_FRI, bars=_bars(final_fri=True)))
    assert (body["today"]["session"], body["today"]["final"]) == ("2026-11-06", True)
    assert body["daily"][0]["date"] == "2026-11-06" and body["range"]["to"] == "2026-11-06"


def test_benchmark_status_empty_stale_ok():
    empty = _body(_inputs(bars=[], refresher_on=False))
    assert (empty["benchmarks_status"], empty["benchmarks_last_session"]) == ("empty", None)
    assert empty["stats"]["SPY"]["total_pct"] == {"value": None, "n": 0, "reason": None}
    ok = _body(_inputs())
    assert (ok["benchmarks_status"], ok["benchmarks_last_session"]) == ("ok", THU.isoformat())
    behind = [b for b in _bars() if b["session"] != THU]
    stale = _body(_inputs(bars=behind, refresher_on=False))
    assert (stale["benchmarks_status"], stale["benchmarks_last_session"]) == ("stale", SESS[-2].isoformat())
    assert _body(_inputs(bars=behind))["benchmarks_status"] == "ok"        # refresher on: catching up


def test_no_live_book_is_an_empty_response_not_zeros():
    body = _body(_inputs(rows=[], bars=[], sessions=[]))
    assert body["range"] == {"from": None, "to": None, "live_since": None, "sessions_n": 0,
                             "clamped": False, "is_all": True}
    assert body["stats"]["bot_account"]["total_pct"] == {"value": None, "n": 0, "reason": None}
    assert body["daily"] == [] and body["today"] == {"session": None, "final": False, "lines": {}}


def test_banner_inputs_pass_through_and_capture_is_checked():
    body = _body(_inputs(currency="EUR", mixed=("SAP.DE",)))
    assert (body["account_currency"], body["mixed_tickers"]) == ("EUR", ["SAP.DE"])
    with pytest.raises(ValueError, match="capture"):
        _body(_inputs(), capture="IWM")
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_response.py`
Expected: FAIL — `AttributeError: module ... has no attribute 'build_benchmark'`.

- [ ] **Step 3: Extend `swingbot/core/analytics/benchmark_view.py`**

Add the four public functions above and private helpers, each < 15:
`_r4(x) -> float | None`, `_account_returns(frame) -> list[tuple[AlignedDay, float]]`,
`_deployed_in_range(frame) -> list[tuple[AlignedDay, Deployed]]`,
`_index_returns(frame, sym) -> list[float]`, `_estimate(est) -> dict`,
`_line_stats(r, one) -> dict` (total/max_dd/sharpe), `_account_stats(frame)`,
`_deployed_stats(frame)`, `build_stats(frame) -> dict`,
`_pairs(frame, sym) -> tuple[list[float], list[float]]`,
`build_vs(frame) -> dict`, `build_capture(frame, capture) -> dict`,
`_daily_row(frame, day, capture) -> dict`, `build_daily(frame, capture) -> list[dict]`,
`_card_session(inputs, state, completed) -> date | None`,
`build_today(inputs, frame, state, completed) -> dict`, `_range(rng) -> dict`.
`build_benchmark` only orchestrates: validate `capture`, `state =
view_session_state(now)`, `completed`, `rng = clamp_range(completed,
live_since_of(rows), start, end)`, `frame = build_frame(inputs, rng)`,
`build_series`, then the dict in contract key order.

- [ ] **Step 4: Run all three part-3 test files and confirm they pass**

Run: `python scripts/dev/testrun.py file tests/analytics/test_benchmark_response.py`
then `python scripts/dev/testrun.py file tests/analytics/test_benchmark_view.py`
Expected: PASS, 0 failed, both.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/benchmark_view.py tests/analytics/test_benchmark_response.py
git commit -m "feat(v208): benchmark_view -- stats, vs, capture, daily rows, Today card, status, build_benchmark"
```
