# v161 Trade scout, part 1b: categorical cuts (TS4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Split from part 1 to keep every file under 1500 lines; the task is unchanged and whole.

**Spec:** [`docs/superpowers/specs/2026-10-15-v161-trade-scout-design.md`](../specs/2026-10-15-v161-trade-scout-design.md)
**Index:** [`2026-10-15-v161-trade-scout_0-index.md`](2026-10-15-v161-trade-scout_0-index.md) — Global Constraints, Parallelisation, Shared contracts and the Task ledger bind this task.
**Bump:** none
**Edge:** none (integrity)

Paths: `$R` = `E:/Documents/Private/Projects/Discord-Bot`, `$WT` = `$R/.claude/worktrees/2026-10-15-v161-trade-scout`. Never `cd`. The import convention (`autopsy` package with `scripts/reports` on `sys.path`) and keyword construction of `BookRow` (every field defaulted) are stated at the top of part 1.

# Phase B (continued): categorical cuts

### Task TS4: Categorical cuts: strategy, regime, calendar, events, volatility, timing

**Model:** sonnet — fourteen small key functions in one module over PIT-frozen fields; behaviour fixed by the spec's cut list and Data availability block.

**Files:**
- Create: `scripts/reports/autopsy/cuts.py`
- Create: `tests/scout/test_autopsy_cuts.py`

**Interfaces:**
- Consumes: TS2 `BookRow` (`strategy, horizon, direction, ticker, regime2_state, entry_date, exit_date, days_to_earnings, atr_pct` (percent), `session_bucket, plan_hour`); TS3 `cut_cells`. Existing: `swingbot/core/market/market_events.py:31 FOMC_DECISION_DATES` (2026-01-28 … 2027-12-08); `swingbot/core/market/opex.py:84 monthly_expiration(year, month) -> dt.date`; `swingbot/core/marketdata/universe.py:219 sector_map(name) -> {symbol: sector}` (`load` accepts `"sp500+etfs"`, returns `[]` for a missing file).
- Produces (ledger): `CATEGORICAL_CUT_NAMES` = `("strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday", "friday_entry", "weekend_hold", "earnings_proximity", "opex_week", "fomc_proximity", "atr_pct_bucket", "session_bucket", "alert_hour")`; `categorical_cuts(sector_of: Mapping[str, str]) -> tuple[tuple[str, Callable[[BookRow], str | None]], ...]` in that order; `load_sector_map() -> dict[str, str]` (`{}` when unavailable); `CUT_NOTES: dict[str, str]` with keys `sector_today`, `fomc_proximity`, `macro`, `earnings_proximity` (TS7 prints them in the header notes).

**Values (a key returns `None` when it cannot place the trade; TS3 counts those as uncovered):** `strategy_horizon` `"<strategy>|<horizon>"`; `weekday` `Mon`…`Fri` of the entry; `friday_entry` / `weekend_hold` `yes`/`no` (a Saturday falls strictly between entry and exit); `earnings_proximity` `past` (< 0) / `le_5d` / `6_20d` / `gt_20d` (days); `opex_week` `opex_week` when the entry's ISO week holds that month's standard expiration, else `other`; `fomc_proximity` `fomc_in_hold` when a decision date lies in `[entry, exit]`, else `no_fomc`, and `None` outside the table's coverage (before Jan 1 of its first year, or exit after its last date); `atr_pct_bucket` `lt_1.5` / `1.5_3` / `3_5` / `ge_5` (percent); `alert_hour` the Eastern hour `"09"`; `sector_today` from today's map (labelled not-PIT, never a regime-desk argument). CPI and NFP have no cut: `market_events.py` computes only forward approximations.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/scout/test_autopsy_cuts.py`:

```python
"""autopsy.cuts: the fourteen categorical cuts and their coverage rules."""
import datetime as dt
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "reports"))

from autopsy import cells, cuts  # noqa: E402
from autopsy.rows import BookRow  # noqa: E402
from swingbot.core.market.opex import monthly_expiration  # noqa: E402
from swingbot.core.marketdata import universe  # noqa: E402


def _keys(sector_of=None):
    return dict(cuts.categorical_cuts(sector_of or {}))


def test_the_cut_names_are_the_contract_in_order():
    assert [name for name, _ in cuts.categorical_cuts({})] == [
        "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday",
        "friday_entry", "weekend_hold", "earnings_proximity", "opex_week",
        "fomc_proximity", "atr_pct_bucket", "session_bucket", "alert_hour"]


def test_a_bare_row_is_uncovered_by_every_cut():
    assert all(key(BookRow()) is None for key in _keys().values())


def test_plain_field_cuts():
    row = BookRow(strategy="RSI", horizon="2w", direction="bullish", ticker="AAA",
                  regime2_state="bull_quiet", session_bucket="open", plan_hour=9)
    keys = _keys({"AAA": "Technology"})
    assert keys["strategy_horizon"](row) == "RSI|2w"
    assert (keys["direction"](row), keys["ticker"](row)) == ("bullish", "AAA")
    assert (keys["regime"](row), keys["session_bucket"](row)) == ("bull_quiet", "open")
    assert keys["sector_today"](row) == "Technology"
    assert keys["sector_today"](BookRow(ticker="ZZZ")) is None
    assert keys["alert_hour"](row) == "09"


def test_weekday_friday_entry_and_weekend_hold():
    keys = _keys()
    thursday = BookRow(entry_date="2026-03-19", exit_date="2026-03-23")
    friday = BookRow(entry_date="2026-03-20", exit_date="2026-03-20")
    assert (keys["weekday"](thursday), keys["friday_entry"](thursday)) == ("Thu", "no")
    assert (keys["weekday"](friday), keys["friday_entry"](friday)) == ("Fri", "yes")
    assert keys["weekend_hold"](thursday) == "yes"
    assert keys["weekend_hold"](friday) == "no"
    assert keys["weekend_hold"](BookRow(entry_date="2026-03-19")) is None


@pytest.mark.parametrize("days, bucket", [(-2, "past"), (0, "le_5d"), (5, "le_5d"),
                                          (6, "6_20d"), (20, "6_20d"), (21, "gt_20d")])
def test_earnings_buckets(days, bucket):
    assert _keys()["earnings_proximity"](BookRow(days_to_earnings=days)) == bucket


def test_opex_week_is_the_iso_week_of_the_monthly_expiration():
    assert monthly_expiration(2026, 3) == dt.date(2026, 3, 20)
    key = _keys()["opex_week"]
    assert key(BookRow(entry_date="2026-03-17")) == "opex_week"
    assert key(BookRow(entry_date="2026-03-24")) == "other"


def test_fomc_in_hold_and_coverage():
    key = _keys()["fomc_proximity"]
    assert key(BookRow(entry_date="2026-03-16", exit_date="2026-03-20")) == "fomc_in_hold"
    assert key(BookRow(entry_date="2026-03-02", exit_date="2026-03-06")) == "no_fomc"
    assert key(BookRow(entry_date="2025-12-29", exit_date="2026-01-30")) is None
    assert key(BookRow(entry_date="2027-12-01", exit_date="2028-01-05")) is None


@pytest.mark.parametrize("atr_pct, bucket", [(0.9, "lt_1.5"), (1.5, "1.5_3"), (2.99, "1.5_3"),
                                             (3.0, "3_5"), (5.0, "ge_5")])
def test_atr_pct_buckets(atr_pct, bucket):
    assert _keys()["atr_pct_bucket"](BookRow(atr_pct=atr_pct)) == bucket


def test_the_sector_map_degrades_to_empty(monkeypatch):
    def broken(name):
        raise OSError("no universe file")
    monkeypatch.setattr(universe, "sector_map", broken)
    assert cuts.load_sector_map() == {}


def test_the_sector_map_is_upper_cased_and_drops_blanks(monkeypatch):
    monkeypatch.setattr(universe, "sector_map", lambda name: {"aaa": "Tech", "BBB": ""})
    assert cuts.load_sector_map() == {"AAA": "Tech"}


def test_notes_label_sector_fomc_and_the_omitted_macro_cuts():
    assert "not point-in-time" in cuts.CUT_NOTES["sector_today"]
    assert "CPI and NFP omitted" in cuts.CUT_NOTES["macro"]
    assert "2026-01-01" in cuts.CUT_NOTES["fomc_proximity"]
    assert "earnings_proximity" in cuts.CUT_NOTES


def test_a_categorical_cut_feeds_cut_cells():
    trades = [BookRow(row_kind="trade", ticker="AAA", direction=d, entry_date=f"2026-03-0{i + 2}",
                      gross_r=r, net_r=r)
              for i, (d, r) in enumerate([("bullish", 1.0), ("bearish", -1.0), ("bullish", 0.5)])]
    out = cells.cut_cells("direction", trades, _keys()["direction"], n_resamples=50, seed=42)
    assert [(c.id, c.n) for c in out] == [("direction=bearish", 1), ("direction=bullish", 2)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_autopsy_cuts.py`
Expected: FAIL — `ImportError: cannot import name 'cuts' from 'autopsy'`.

- [ ] **Step 3: Write the implementation**

Create `$WT/scripts/reports/autopsy/cuts.py`:

```python
"""Categorical cuts of the closed trades (spec section 1).

Each cut is (name, key): the key returns the trade's cell value, or None when
it cannot place the trade (counted as uncovered, in neither arm). Every input is
frozen at issuance (risk_features) or a calendar fact; the one exception is
sector_today, today's mapping, labelled not point-in-time in CUT_NOTES.
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, Mapping

from swingbot.core.market.market_events import FOMC_DECISION_DATES
from swingbot.core.market.opex import monthly_expiration

from .rows import BookRow

Key = Callable[[BookRow], "str | None"]

CATEGORICAL_CUT_NAMES = (
    "strategy_horizon", "direction", "ticker", "sector_today", "regime", "weekday",
    "friday_entry", "weekend_hold", "earnings_proximity", "opex_week", "fomc_proximity",
    "atr_pct_bucket", "session_bucket", "alert_hour",
)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
#: (exclusive upper bound, label); a value at or past the last bound gets the top label.
EARNINGS_BUCKETS = ((0, "past"), (6, "le_5d"), (21, "6_20d"))
ATR_PCT_BUCKETS = ((1.5, "lt_1.5"), (3.0, "1.5_3"), (5.0, "3_5"))
FOMC_FIRST = dt.date(min(FOMC_DECISION_DATES).year, 1, 1)
FOMC_LAST = max(FOMC_DECISION_DATES)

CUT_NOTES = {
    "sector_today": "sector_today: today's sector map, not point-in-time",
    "fomc_proximity": f"fomc_proximity: FOMC dates cover {FOMC_FIRST} to {FOMC_LAST}; "
                      "trades outside are uncovered",
    "macro": "CPI and NFP omitted: market_events.py carries no past dates",
    "earnings_proximity": "earnings_proximity: days_to_earnings is opportunistic; "
                          "trades without it are uncovered",
}


def _day(text: str | None) -> dt.date | None:
    return dt.date.fromisoformat(text[:10]) if text else None


def _bucket(value: float, table, top: str) -> str:
    return next((label for bound, label in table if value < bound), top)


def _attr(name: str) -> Key:
    return lambda t: getattr(t, name)


def _strategy_horizon(t: BookRow) -> str | None:
    return f"{t.strategy}|{t.horizon}" if t.strategy else None


def _weekday(t: BookRow) -> str | None:
    day = _day(t.entry_date)
    return None if day is None else WEEKDAYS[day.weekday()]


def _friday_entry(t: BookRow) -> str | None:
    day = _day(t.entry_date)
    return None if day is None else ("yes" if day.weekday() == 4 else "no")


def _weekend_hold(t: BookRow) -> str | None:
    start, end = _day(t.entry_date), _day(t.exit_date)
    if start is None or end is None:
        return None
    first_saturday = start + dt.timedelta(days=(5 - start.weekday()) % 7 or 7)
    return "yes" if first_saturday < end else "no"


def _earnings(t: BookRow) -> str | None:
    if t.days_to_earnings is None:
        return None
    return _bucket(t.days_to_earnings, EARNINGS_BUCKETS, "gt_20d")


def _opex_week(t: BookRow) -> str | None:
    day = _day(t.entry_date)
    if day is None:
        return None
    expiry = monthly_expiration(day.year, day.month)
    return "opex_week" if day.isocalendar()[:2] == expiry.isocalendar()[:2] else "other"


def _fomc(t: BookRow) -> str | None:
    start, end = _day(t.entry_date), _day(t.exit_date)
    if start is None or end is None or start < FOMC_FIRST or end > FOMC_LAST:
        return None
    return "fomc_in_hold" if any(start <= d <= end for d in FOMC_DECISION_DATES) else "no_fomc"


def _atr_pct(t: BookRow) -> str | None:
    return None if t.atr_pct is None else _bucket(t.atr_pct, ATR_PCT_BUCKETS, "ge_5")


def _alert_hour(t: BookRow) -> str | None:
    return None if t.plan_hour is None else f"{t.plan_hour:02d}"


def _sector(sector_of: Mapping[str, str]) -> Key:
    return lambda t: sector_of.get(t.ticker) if t.ticker else None


def categorical_cuts(sector_of: Mapping[str, str]) -> tuple[tuple[str, Key], ...]:
    keys = (_strategy_horizon, _attr("direction"), _attr("ticker"), _sector(sector_of),
            _attr("regime2_state"), _weekday, _friday_entry, _weekend_hold, _earnings,
            _opex_week, _fomc, _atr_pct, _attr("session_bucket"), _alert_hour)
    return tuple(zip(CATEGORICAL_CUT_NAMES, keys))


def load_sector_map() -> dict[str, str]:
    """Today's {TICKER: sector} for S&P 500 and ETFs; {} when unavailable."""
    from swingbot.core.marketdata import universe
    try:
        mapping = universe.sector_map("sp500+etfs")
    except (OSError, ValueError, KeyError):
        return {}
    return {str(s).upper(): sec for s, sec in mapping.items() if sec}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/dev/testrun.py file tests/scout/test_autopsy_cuts.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout/scripts/reports/autopsy/cuts.py`
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout add scripts/reports/autopsy/cuts.py tests/scout/test_autopsy_cuts.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-15-v161-trade-scout commit -m "feat(v161): autopsy categorical cuts

TS4. Strategy x horizon, direction, ticker, today's sector (labelled),
regime, calendar, earnings, OPEX week, FOMC with coverage, ATR% and timing.
CPI and NFP omitted: no past dates in market_events.py.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

Expected: the last command shows the main tree unchanged by this task.
