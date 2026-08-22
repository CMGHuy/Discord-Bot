Version: ui 1.8.0 · bot 1.3.2
Spec: docs/superpowers/specs/2026-08-21-v42-opex-day-caution-design.md
Bump: bot minor (1.3.2 → 1.4.0) — alert gating, alert content and trade-plan
risk parameters change observably on opex days. `ui` none (new settings render
themselves through the existing generic Settings page).
Edge: expectancy — sharpens the discriminator on opex days rather than adding
a new one, by raising the confidence/confluence bar and suppressing
near-close entries on a population the spec's own Problem section identifies
as elevated-whipsaw-risk. (Added retroactively 2026-08-22 — this plan
predates the `Edge:` header convention.)

# Opex-day caution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach the bot to recognise US options-expiration days and trade more
cautiously on them — a higher bar to alert, no new entries into the close, a
wider ATR stop and a smaller position — all behind one default-off flag.

**Architecture:** One new pure module, `swingbot/core/market/opex.py`, holding
both the calendar (a date → `"monthly" | "weekly" | None` classifier) and the
policy built on it (effective thresholds, suppression window, stop/size
multipliers, embed badge). Five existing call sites then consume it. Nothing
new is fetched, persisted or scheduled.

**Tech Stack:** Python 3.11 stdlib only — `datetime` and `zoneinfo`. No new
dependency; in particular **no `pandas_market_calendars`**.

## Global Constraints

- **Flag-gated, default off.** `OPEX_CAUTION_ENABLED` defaults to `false`.
  With it off every helper in `opex.py` returns the unmodified base value and
  the bot behaves exactly as it does today. This matches `REGIME_GATES_ENABLED`
  (`swingbot/config.py:598-604`) and `UNIFIED_CONFIDENCE` (`config.py:177-182`).
- **Every new config `Field` must also be added to `.env.example`.**
  `tests/test_env_example_sync.py::test_every_setting_appears_in_env_example`
  fails otherwise. Presence is asserted, values are not.
- **The opex date is a US date.** Classify against `America/New_York`, never
  `bot_core.SESSION_TZ` (Europe/Berlin) and never a naive `date.today()`.
- **The near-close anchor is 16:00 US/Eastern, not `SESSION_END_HOUR`.**
  `SESSION_END_HOUR` defaults to `23` **Berlin** (`config.py:121-123`), which
  is 17:00 ET — an hour *after* the US close. Anchoring the suppression window
  there would fire it entirely after the market had already closed.
- **Do not add `ctx_opex_tier` to `market_context.CTX_COLUMNS`.** See Task 1's
  docstring for the full reason; briefly, `market_context.get()` returns `None`
  whenever `REGIME_GATES_ENABLED` is off (`market_context.py:134-135`), which
  would let an unrelated flag silently disable this feature.
- **Never widen a structural stop.** `plan_engine.py:770-776` documents that
  only the ATR path takes a stop multiplier, because fib / Elliott / S-R stops
  sit behind real structure and scaling them slides the stop off the thing it
  exists to hide behind. Opex widening obeys the same rule.
- Verify with `python scripts/dev/testrun.py file <test file>` while iterating
  (~7s). Use the `test-runner` subagent for the full suite before the final
  commit. Green means `0 failed` **and** `0 xfailed`.

---

# Phase 1 — Calendar and policy core

No existing file is modified in this phase. Everything here is new, pure and
independently testable.

### Task 1: Opex calendar — tier classification

**Files:**
- Create: `swingbot/core/market/opex.py`
- Test: `tests/market/test_opex_calendar.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `MONTHLY: str`, `WEEKLY: str`, `US_MARKET_TZ: ZoneInfo`,
  `US_CLOSE_TIME: datetime.time`, `monthly_expiration(year: int, month: int) -> datetime.date`,
  `opex_tier(day: datetime.date) -> str | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_opex_calendar.py`:

```python
"""The opex calendar is pure date arithmetic -- no network, no mocking.

The two holiday collisions asserted here are real and were verified against
the NYSE calendar: 2026-06-19 (Juneteenth) and 2030-04-19 (Good Friday) are
both the nominal third Friday of their month AND full-day closures, so the
expiration moves to the preceding Thursday in each case.
"""
import datetime as dt

import pytest

from swingbot.core.market import opex


def d(iso: str) -> dt.date:
    return dt.date.fromisoformat(iso)


@pytest.mark.parametrize("iso", [
    "2026-08-21",   # 3rd Friday of Aug 2026
    "2026-01-16",   # 3rd Friday of Jan 2026 (month starting on a Thursday)
    "2026-05-15",   # 3rd Friday of May 2026 (month starting on a Friday)
    "2027-01-15",
])
def test_monthly_third_friday(iso):
    assert opex.opex_tier(d(iso)) == opex.MONTHLY


@pytest.mark.parametrize("iso", ["2026-08-07", "2026-08-14", "2026-08-28"])
def test_other_fridays_are_weekly(iso):
    assert opex.opex_tier(d(iso)) == opex.WEEKLY


@pytest.mark.parametrize("iso", [
    "2026-08-20",   # Thursday
    "2026-08-24",   # Monday
    "2026-08-22",   # Saturday
    "2026-08-23",   # Sunday
])
def test_non_fridays_are_none(iso):
    assert opex.opex_tier(d(iso)) is None


def test_holiday_third_friday_shifts_to_thursday():
    # Juneteenth 2026 falls on Friday 19 June, which is also the nominal
    # third Friday. The market is shut, so expiration moves to Thursday.
    assert opex.opex_tier(d("2026-06-19")) is None
    assert opex.opex_tier(d("2026-06-18")) == opex.MONTHLY
    assert opex.monthly_expiration(2026, 6) == d("2026-06-18")


def test_good_friday_third_friday_shifts_to_thursday():
    # Good Friday 2030 is 19 April, the third Friday of that month.
    assert opex.opex_tier(d("2030-04-19")) is None
    assert opex.opex_tier(d("2030-04-18")) == opex.MONTHLY


def test_holiday_friday_that_is_not_third_friday_is_not_weekly():
    # Good Friday 2026 (3 April) is the FIRST Friday. The market is shut, so
    # it is not a weekly expiration either.
    assert opex.opex_tier(d("2026-04-03")) is None
    assert opex.opex_tier(d("2026-04-17")) == opex.MONTHLY   # unaffected


def test_thursday_before_an_ordinary_holiday_friday_is_not_monthly():
    # 2026-07-03 is a closure (Independence Day observed) but the third
    # Friday of July 2026 is the 17th, so 2026-07-02 must stay None.
    assert opex.opex_tier(d("2026-07-02")) is None


def test_monthly_expiration_is_a_thursday_or_friday_every_month():
    for year in range(2026, 2031):
        for month in range(1, 13):
            got = opex.monthly_expiration(year, month)
            assert got.weekday() in (3, 4), (year, month, got)
            assert got.month == month
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_opex_calendar.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.market.opex'`

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/market/opex.py`:

```python
"""Options-expiration ("opex") calendar and the caution policy built on it.

WHY A MODULE AND NOT A CONTEXT COLUMN
-------------------------------------
`market_context` exists to align an EXTERNAL series -- SPY-derived regime --
onto a ticker's index without leaking tomorrow's value into today's bar; its
module docstring argues that at length. Opex has no external series. The tier
is a pure function of the bar's own date, so there is nothing to align and no
lookahead to guard against, and the machinery would buy nothing.

It would also cost something real. `market_context.get()` returns None
whenever `REGIME_GATES_ENABLED` is off, so putting `ctx_opex_tier` in
CTX_COLUMNS would wire this feature's on/off switch to an unrelated flag --
turning regime gating off would silently stop opex caution too, with nothing
anywhere saying so.

WHY US/EASTERN AND NOT SESSION_TZ
---------------------------------
The scanning session is Europe/Berlin (`bot_core.SESSION_TZ`), but an
expiration is a US-market event. Berlin runs six hours ahead of New York, so
the two calendars only agree during 15:30-22:00 Berlin. `SESSION_END_HOUR`
defaults to 23, which puts the tail of every session in the gap where the
Berlin date has already rolled over and the New York date has not.

The same reasoning fixes the near-close anchor at 16:00 America/New_York
rather than SESSION_END_HOUR: 23:00 Berlin is 17:00 ET, an hour after the
US close, so a window measured back from it would sit entirely after the
event it exists to protect against.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

US_MARKET_TZ = ZoneInfo("America/New_York")

#: US equity regular-session close. Half-days (the 13:00 closes around
#: Thanksgiving and Christmas) are deliberately not modelled: none of them is
#: ever a third Friday, and treating one as a full day only makes the
#: suppression window start later than needed on a day that is not an opex
#: day at all.
US_CLOSE_TIME = dt.time(16, 0)

MONTHLY = "monthly"
WEEKLY = "weekly"

#: NYSE full-day closures that land on a **Friday** -- the only ones that can
#: displace an expiration. A Friday holiday does two things: it cancels that
#: week's weekly expiration, and if it was the nominal third Friday it moves
#: the monthly expiration back to the Thursday.
#:
#: Fridays only, on purpose. This is not a general market calendar and must
#: not be used as one; `MAINTENANCE` below says how to extend it.
_FRIDAY_HOLIDAYS: frozenset[dt.date] = frozenset({
    dt.date(2026, 4, 3),     # Good Friday
    dt.date(2026, 6, 19),    # Juneteenth            (also the 3rd Friday)
    dt.date(2026, 7, 3),     # Independence Day observed (4 Jul is a Saturday)
    dt.date(2026, 12, 25),   # Christmas Day
    dt.date(2027, 1, 1),     # New Year's Day
    dt.date(2027, 3, 26),    # Good Friday
    dt.date(2027, 6, 18),    # Juneteenth observed  (19 Jun is a Saturday)
    dt.date(2027, 12, 24),   # Christmas observed   (25 Dec is a Saturday)
    dt.date(2028, 4, 14),    # Good Friday
    dt.date(2029, 3, 30),    # Good Friday
    dt.date(2030, 4, 19),    # Good Friday          (also the 3rd Friday)
})

#: MAINTENANCE: the table above is complete through this year and empty
#: after it, so from 1 Jan of the following year every Friday holiday is
#: silently treated as a normal expiration. Extend it by listing the NYSE
#: full-day closures that fall on a Friday -- in practice Good Friday every
#: year, plus whichever of New Year's Day, Juneteenth, Independence Day and
#: Christmas land on (or are observed on) a Friday.
LAST_YEAR_COVERED = 2030


def _third_friday(year: int, month: int) -> dt.date:
    """The nominal third Friday, before any holiday adjustment."""
    first = dt.date(year, month, 1)
    # weekday(): Monday is 0, Friday is 4.
    first_friday_offset = (4 - first.weekday()) % 7
    return first + dt.timedelta(days=first_friday_offset + 14)


def monthly_expiration(year: int, month: int) -> dt.date:
    """The month's standard equity/index expiration date.

    The third Friday, moved back to the Thursday when that Friday is a
    full-day closure -- the convention US exchanges use.
    """
    nominal = _third_friday(year, month)
    if nominal in _FRIDAY_HOLIDAYS:
        return nominal - dt.timedelta(days=1)
    return nominal


def opex_tier(day: dt.date) -> str | None:
    """Classify one calendar date.

    `MONTHLY` for the month's standard expiration, `WEEKLY` for any other
    Friday the market is open, `None` otherwise. Total: every date has an
    answer, so there is nothing here to raise.

    Quarterly "triple witching" (Mar/Jun/Sep/Dec) is deliberately folded into
    MONTHLY rather than given a third tier -- nothing in the policy layer
    would currently treat it differently.
    """
    if day == monthly_expiration(day.year, day.month):
        return MONTHLY
    if day.weekday() == 4 and day not in _FRIDAY_HOLIDAYS:
        return WEEKLY
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_opex_calendar.py`
Expected: PASS (all parametrised cases green)

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/opex.py tests/market/test_opex_calendar.py
git commit -m "feat(v44): opex calendar -- monthly/weekly tier classification"
```

---

### Task 2: Config fields and `.env.example`

**Files:**
- Modify: `swingbot/config.py` (add a new section after the "Trade Filters & Risk" block that ends at line 195)
- Modify: `.env.example`
- Test: `tests/test_opex_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.OPEX_CAUTION_ENABLED` (bool),
  `config.OPEX_MONTHLY_CONFIDENCE_BUMP` (int),
  `config.OPEX_MONTHLY_CONFLUENCE_BUMP` (int),
  `config.OPEX_WEEKLY_CONFLUENCE_BUMP` (int),
  `config.OPEX_NEAR_CLOSE_SUPPRESS_MINUTES` (int),
  `config.OPEX_STOP_WIDEN_PCT` (float),
  `config.OPEX_SIZE_REDUCTION_PCT` (float).

**Why these dials and not a generic "threshold bump":** the two gates this
feature tightens are both **integers** — `MIN_ALERT_CONFIDENCE_LEVEL` is a
`select` over `1..5` (`config.py:174-176`) and `MIN_TARGET_CONFLUENCE_COUNT`
is a `number` over `1..10` (`config.py:167-173`). A float bump has nowhere to
land. Monthly gets both dials; weekly gets the confluence dial only, which is
what makes it the lighter tier.

- [ ] **Step 1: Write the failing test**

Create `tests/test_opex_config.py`:

```python
"""The opex settings must exist, default safe, and be discoverable.

`.env.example` presence is already covered globally by
tests/test_env_example_sync.py; what is asserted here is the part that file
cannot check -- that the master switch ships OFF.
"""
from swingbot import config


OPEX_SETTINGS = (
    "OPEX_CAUTION_ENABLED",
    "OPEX_MONTHLY_CONFIDENCE_BUMP",
    "OPEX_MONTHLY_CONFLUENCE_BUMP",
    "OPEX_WEEKLY_CONFLUENCE_BUMP",
    "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES",
    "OPEX_STOP_WIDEN_PCT",
    "OPEX_SIZE_REDUCTION_PCT",
)


def test_every_opex_setting_is_defined():
    for name in OPEX_SETTINGS:
        assert hasattr(config, name), f"{name} missing from the config schema"


def test_master_switch_defaults_off():
    # Ships inert: every downstream helper short-circuits on this being
    # False, so the feature cannot change behaviour until it is validated
    # and turned on deliberately.
    assert config.OPEX_CAUTION_ENABLED is False


def test_bumps_are_non_negative_integers():
    for name in ("OPEX_MONTHLY_CONFIDENCE_BUMP",
                 "OPEX_MONTHLY_CONFLUENCE_BUMP",
                 "OPEX_WEEKLY_CONFLUENCE_BUMP",
                 "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES"):
        value = getattr(config, name)
        assert isinstance(value, int) and value >= 0, (name, value)


def test_reduction_percentages_are_in_range():
    assert 0 <= config.OPEX_STOP_WIDEN_PCT <= 100
    assert 0 <= config.OPEX_SIZE_REDUCTION_PCT < 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/test_opex_config.py`
Expected: FAIL — `AssertionError: OPEX_CAUTION_ENABLED missing from the config schema`

- [ ] **Step 3: Add the fields**

In `swingbot/config.py`, insert immediately after the `NEAR_CLOSE_THRESHOLD_PCT`
field (which ends at line 195), keeping the `Field(...)` shape used throughout:

```python
    # --- Options / Opex ---
    # Two tiers. Monthly (the third-Friday expiration, when every listed
    # equity and index option expires together) is when pinning and unwind
    # whipsaw are worst, so it takes all four behaviours. A plain weekly
    # Friday takes only the confluence bump, which is what makes it "light".
    Field("OPEX_CAUTION_ENABLED", "OPEX_CAUTION_ENABLED", "Options / Opex",
          "Opex-day caution enabled",
          type="checkbox", default="false",
          help="Trade more cautiously on options-expiration days: a higher bar to alert, "
               "no new entries into the US close, a wider ATR stop and a smaller position. "
               "Off = every day is treated identically, exactly as before. Enable only "
               "after VALIDATION."),
    Field("OPEX_MONTHLY_CONFIDENCE_BUMP", "OPEX_MONTHLY_CONFIDENCE_BUMP", "Options / Opex",
          "Monthly opex: confidence levels added",
          type="number", default="1", min=0, max=4, step=1,
          help="Added to 'Min confidence level to alert' on a monthly (third-Friday) expiration, "
               "capped at Lv5. 0 disables this tightening. Weekly expirations never take it."),
    Field("OPEX_MONTHLY_CONFLUENCE_BUMP", "OPEX_MONTHLY_CONFLUENCE_BUMP", "Options / Opex",
          "Monthly opex: strategies added",
          type="number", default="1", min=0, max=9, step=1,
          help="Added to 'Min strategies confirmed' on a monthly expiration, capped at 10."),
    Field("OPEX_WEEKLY_CONFLUENCE_BUMP", "OPEX_WEEKLY_CONFLUENCE_BUMP", "Options / Opex",
          "Weekly opex: strategies added",
          type="number", default="1", min=0, max=9, step=1,
          help="Added to 'Min strategies confirmed' on any other Friday expiration, capped at 10. "
               "This is the only tightening a weekly expiration applies."),
    Field("OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", "Options / Opex",
          "Monthly opex: no new entries within (minutes of the US close)",
          type="number", default="60", min=0, max=390, step=15,
          help="On a monthly expiration, stop opening new trades this many minutes before "
               "16:00 US/Eastern, when pinning and unwind volatility peak. 0 disables the window. "
               "Open trades are still monitored and can still close normally."),
    Field("OPEX_STOP_WIDEN_PCT", "OPEX_STOP_WIDEN_PCT", "Options / Opex",
          "Monthly opex: ATR stop widened by %",
          type="float", default="10.0", min=0, max=100, step=5,
          help="Widens the ATR-derived stop distance on a monthly expiration, to survive "
               "expiration-day whipsaw. Structure-derived stops (Fibonacci, Elliott, "
               "support/resistance) are deliberately NOT widened -- scaling those slides the "
               "stop off the level it exists to sit behind."),
    Field("OPEX_SIZE_REDUCTION_PCT", "OPEX_SIZE_REDUCTION_PCT", "Options / Opex",
          "Monthly opex: position size reduced by %",
          type="float", default="25.0", min=0, max=90, step=5,
          help="Cuts the suggested position size on a monthly expiration. Applies to both "
               "sizing modes: it scales risk-per-trade in 'risk_pct' mode and the allocation "
               "in 'account_pct' mode."),
```

- [ ] **Step 4: Add the same seven keys to `.env.example`**

Append to the appropriate section of `.env.example` (values may differ from
the schema defaults; only presence is asserted):

```bash
# --- Options / Opex ---
OPEX_CAUTION_ENABLED=false
OPEX_MONTHLY_CONFIDENCE_BUMP=1
OPEX_MONTHLY_CONFLUENCE_BUMP=1
OPEX_WEEKLY_CONFLUENCE_BUMP=1
OPEX_NEAR_CLOSE_SUPPRESS_MINUTES=60
OPEX_STOP_WIDEN_PCT=10.0
OPEX_SIZE_REDUCTION_PCT=25.0
```

- [ ] **Step 5: Run both tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/test_opex_config.py`
Expected: PASS

Run: `python scripts/dev/testrun.py file tests/test_env_example_sync.py`
Expected: PASS — this is the guard that catches a `Field` added without its
`.env.example` line.

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py .env.example tests/test_opex_config.py
git commit -m "feat(v44): opex caution settings, default off"
```

---

### Task 3: Policy helpers

**Files:**
- Modify: `swingbot/core/market/opex.py` (append below `opex_tier`)
- Test: `tests/market/test_opex_policy.py`

**Interfaces:**
- Consumes: Task 1's `opex_tier`, `MONTHLY`, `WEEKLY`, `US_MARKET_TZ`,
  `US_CLOSE_TIME`; Task 2's seven config settings.
- Produces:
  - `current_tier(now: dt.datetime | None = None) -> str | None`
  - `minutes_to_us_close(now: dt.datetime | None = None) -> float`
  - `effective_min_confidence_level(tier: str | None = ...) -> int`
  - `effective_min_confluence(base: int, tier: str | None = ...) -> int`
  - `suppress_new_entries(now=None, tier: str | None = ...) -> bool`
  - `stop_mult(tier: str | None = ...) -> float`
  - `size_mult(tier: str | None = ...) -> float`
  - `badge(tier: str | None = ...) -> tuple[str, str] | None`

Every `tier` parameter defaults to the sentinel `_UNSET`, meaning "resolve it
from the clock". Later tasks pass an explicit tier so one scan resolves the
calendar once instead of per ticker per horizon.

- [ ] **Step 1: Write the failing test**

Create `tests/market/test_opex_policy.py`:

```python
"""Policy layer: config + tier -> the numbers the scan pipeline uses.

Time is always injected. Nothing here reads the wall clock, so these tests
do not change behaviour on a real opex day.
"""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market import opex

MONTHLY_DAY = dt.datetime(2026, 8, 21, 12, 0, tzinfo=opex.US_MARKET_TZ)   # 3rd Fri
WEEKLY_DAY = dt.datetime(2026, 8, 14, 12, 0, tzinfo=opex.US_MARKET_TZ)    # plain Fri
PLAIN_DAY = dt.datetime(2026, 8, 20, 12, 0, tzinfo=opex.US_MARKET_TZ)     # Thursday


@pytest.fixture
def opex_on(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    monkeypatch.setattr(config, "OPEX_MONTHLY_CONFIDENCE_BUMP", 1)
    monkeypatch.setattr(config, "OPEX_MONTHLY_CONFLUENCE_BUMP", 1)
    monkeypatch.setattr(config, "OPEX_WEEKLY_CONFLUENCE_BUMP", 1)
    monkeypatch.setattr(config, "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", 60)
    monkeypatch.setattr(config, "OPEX_STOP_WIDEN_PCT", 10.0)
    monkeypatch.setattr(config, "OPEX_SIZE_REDUCTION_PCT", 25.0)


# -- the master switch ---------------------------------------------------

def test_everything_is_inert_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    assert opex.current_tier(MONTHLY_DAY) is None
    assert opex.effective_min_confidence_level() == 4
    assert opex.effective_min_confluence(2) == 2
    assert opex.suppress_new_entries(MONTHLY_DAY) is False
    assert opex.stop_mult() == 1.0
    assert opex.size_mult() == 1.0
    assert opex.badge() is None


# -- tier resolution -----------------------------------------------------

def test_current_tier_uses_the_us_date_not_the_local_one(opex_on):
    # 01:30 Berlin on Saturday 22 Aug is still 19:30 Friday 21 Aug in New
    # York -- still monthly opex. A naive date.today() would say Saturday.
    from zoneinfo import ZoneInfo
    berlin_saturday = dt.datetime(2026, 8, 22, 1, 30, tzinfo=ZoneInfo("Europe/Berlin"))
    assert opex.current_tier(berlin_saturday) == opex.MONTHLY


def test_current_tier_classifies_each_day(opex_on):
    assert opex.current_tier(MONTHLY_DAY) == opex.MONTHLY
    assert opex.current_tier(WEEKLY_DAY) == opex.WEEKLY
    assert opex.current_tier(PLAIN_DAY) is None


# -- thresholds ----------------------------------------------------------

def test_monthly_raises_confidence_and_confluence(opex_on):
    assert opex.effective_min_confidence_level(opex.MONTHLY) == 5
    assert opex.effective_min_confluence(2, opex.MONTHLY) == 3


def test_weekly_raises_confluence_only(opex_on):
    assert opex.effective_min_confidence_level(opex.WEEKLY) == 4
    assert opex.effective_min_confluence(2, opex.WEEKLY) == 3


def test_confidence_bump_is_capped_at_five(opex_on, monkeypatch):
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 5)
    assert opex.effective_min_confidence_level(opex.MONTHLY) == 5


def test_confluence_bump_is_capped_at_ten(opex_on):
    assert opex.effective_min_confluence(10, opex.MONTHLY) == 10


# -- the near-close window ----------------------------------------------

@pytest.mark.parametrize("hour,minute,expected", [
    (14, 59, False),   # 61 min out -- outside a 60-minute window
    (15, 0, True),     # exactly 60 min out -- boundary is inclusive
    (15, 30, True),
    (15, 59, True),
    (16, 1, False),    # after the close, nothing left to suppress
])
def test_suppression_window_boundaries(opex_on, hour, minute, expected):
    now = dt.datetime(2026, 8, 21, hour, minute, tzinfo=opex.US_MARKET_TZ)
    assert opex.suppress_new_entries(now) is expected


def test_weekly_never_suppresses(opex_on):
    near_close = dt.datetime(2026, 8, 14, 15, 30, tzinfo=opex.US_MARKET_TZ)
    assert opex.suppress_new_entries(near_close) is False


def test_zero_minutes_disables_the_window(opex_on, monkeypatch):
    monkeypatch.setattr(config, "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", 0)
    now = dt.datetime(2026, 8, 21, 15, 59, tzinfo=opex.US_MARKET_TZ)
    assert opex.suppress_new_entries(now) is False


# -- multipliers and badge ----------------------------------------------

def test_monthly_multipliers(opex_on):
    assert opex.stop_mult(opex.MONTHLY) == pytest.approx(1.10)
    assert opex.size_mult(opex.MONTHLY) == pytest.approx(0.75)


def test_weekly_leaves_stop_and_size_alone(opex_on):
    assert opex.stop_mult(opex.WEEKLY) == 1.0
    assert opex.size_mult(opex.WEEKLY) == 1.0


def test_badge_present_for_both_tiers(opex_on):
    monthly = opex.badge(opex.MONTHLY)
    weekly = opex.badge(opex.WEEKLY)
    assert monthly is not None and "OPEX" in monthly[0]
    assert weekly is not None
    assert monthly != weekly
    assert opex.badge(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/market/test_opex_policy.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.market.opex' has no attribute 'current_tier'`

- [ ] **Step 3: Append the policy layer to `swingbot/core/market/opex.py`**

```python
# ---------------------------------------------------------------------------
# Policy layer
#
# Everything below reads config. `_UNSET` distinguishes "caller did not say"
# from an explicit `None` meaning "not an opex day": a scan resolves the tier
# once and passes it down, rather than re-deriving it per ticker per horizon.
# ---------------------------------------------------------------------------

_UNSET = object()


def _enabled() -> bool:
    from swingbot import config
    return bool(getattr(config, "OPEX_CAUTION_ENABLED", False))


def current_tier(now: dt.datetime | None = None) -> str | None:
    """Today's tier, in US market time. None when the feature is off.

    `now` may carry any timezone -- it is converted before the date is taken,
    which is the whole point. A naive datetime is rejected rather than
    guessed at: assuming it meant UTC or local time is exactly the mistake
    this function exists to prevent.
    """
    if not _enabled():
        return None
    if now is None:
        now = dt.datetime.now(US_MARKET_TZ)
    elif now.tzinfo is None:
        raise ValueError(
            "opex.current_tier() needs an aware datetime -- a naive one has no "
            "defined US date. Pass tzinfo, or omit the argument entirely."
        )
    return opex_tier(now.astimezone(US_MARKET_TZ).date())


def _resolve(tier):
    return current_tier() if tier is _UNSET else tier


def minutes_to_us_close(now: dt.datetime | None = None) -> float:
    """Minutes until 16:00 America/New_York on `now`'s US date.

    Negative once the close has passed. Building the close from the
    already-converted local date is what makes this DST-correct on both
    sides without a table.
    """
    if now is None:
        now = dt.datetime.now(US_MARKET_TZ)
    local = now.astimezone(US_MARKET_TZ)
    close = dt.datetime.combine(local.date(), US_CLOSE_TIME, tzinfo=US_MARKET_TZ)
    return (close - local).total_seconds() / 60.0


def effective_min_confidence_level(tier=_UNSET) -> int:
    """`MIN_ALERT_CONFIDENCE_LEVEL`, raised on a monthly expiration.

    Capped at 5 because the level is a 1-5 select; a bump past the top of the
    scale would silently mean "never alert".
    """
    from swingbot import config
    base = int(config.MIN_ALERT_CONFIDENCE_LEVEL)
    if _resolve(tier) != MONTHLY:
        return base
    bump = int(getattr(config, "OPEX_MONTHLY_CONFIDENCE_BUMP", 0) or 0)
    return min(5, base + bump)


def effective_min_confluence(base: int, tier=_UNSET) -> int:
    """`base` (already resolved from config or a `!check` override), raised
    on either tier. Capped at 10, the top of the setting's own range."""
    from swingbot import config
    resolved = _resolve(tier)
    if resolved == MONTHLY:
        bump = getattr(config, "OPEX_MONTHLY_CONFLUENCE_BUMP", 0)
    elif resolved == WEEKLY:
        bump = getattr(config, "OPEX_WEEKLY_CONFLUENCE_BUMP", 0)
    else:
        return base
    return min(10, int(base) + int(bump or 0))


def suppress_new_entries(now: dt.datetime | None = None, tier=_UNSET) -> bool:
    """True inside the monthly-expiration near-close window.

    Monthly only, and only BEFORE the close: once 16:00 ET has passed the
    remaining figure goes negative and this returns False again. The bot's
    session runs to 23:00 Berlin (17:00 ET), so without that lower bound the
    window would keep firing for an hour after the event it guards.
    """
    from swingbot import config
    # Resolved against `now` rather than via _resolve(), so an injected clock
    # decides the tier and the window consistently -- otherwise a test could
    # pin the window to a Friday afternoon while the tier came from the real
    # wall clock.
    resolved = current_tier(now) if tier is _UNSET else tier
    if resolved != MONTHLY:
        return False
    window = float(getattr(config, "OPEX_NEAR_CLOSE_SUPPRESS_MINUTES", 0) or 0)
    if window <= 0:
        return False
    remaining = minutes_to_us_close(now)
    return 0 <= remaining <= window


def stop_mult(tier=_UNSET) -> float:
    """Multiplier for the ATR stop distance. 1.0 leaves it untouched."""
    from swingbot import config
    if _resolve(tier) != MONTHLY:
        return 1.0
    return 1.0 + float(getattr(config, "OPEX_STOP_WIDEN_PCT", 0.0) or 0.0) / 100.0


def size_mult(tier=_UNSET) -> float:
    """Multiplier for position size. 1.0 leaves it untouched."""
    from swingbot import config
    if _resolve(tier) != MONTHLY:
        return 1.0
    cut = float(getattr(config, "OPEX_SIZE_REDUCTION_PCT", 0.0) or 0.0)
    return max(0.0, 1.0 - cut / 100.0)


def badge(tier=_UNSET) -> tuple[str, str] | None:
    """`(title, body)` for the alert embed, or None off an expiration day.

    Posted on EVERY alert that day, whether or not the tightened gates
    changed the outcome -- following the `heat_blocked` precedent in
    embeds.py, where a constraint is flagged rather than hidden.
    """
    resolved = _resolve(tier)
    if resolved == MONTHLY:
        return (
            "⚠️ MONTHLY OPEX",
            "Monthly options expiration: pinning toward big round strikes and "
            "unwind volatility into the close are both elevated. Entry bar raised.",
        )
    if resolved == WEEKLY:
        return (
            "⚠️ Weekly opex",
            "Weekly options expiration. Pinning risk is milder than a monthly "
            "expiration, but present.",
        )
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_opex_policy.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/opex.py tests/market/test_opex_policy.py
git commit -m "feat(v44): opex policy -- thresholds, window, multipliers, badge"
```

---

# Phase 2 — Scan-pipeline wiring

Every task here modifies an existing file. Read `docs/claude/known-traps.md`
before starting: `scan_engine`/`scan_embeds` ordering is listed there.

### Task 4: Tighten the confidence and confluence gates

**Files:**
- Modify: `swingbot/core/scanning/engine.py:1220` (threshold resolution),
  `engine.py:830-831` (`_scan_one` signature), `engine.py:1139` (the call),
  `engine.py:1374` (`_scan_one` invocation)
- Modify: `swingbot/core/scanning/embeds.py:174` (`_build_requirement_checks`
  signature), `embeds.py:205-217` (the two comparisons)
- Test: `tests/scanning/test_opex_gates.py`

**Interfaces:**
- Consumes: `opex.effective_min_confidence_level`, `opex.effective_min_confluence`,
  `opex.current_tier` from Task 3.
- Produces: `_build_requirement_checks(scenario, target_confluence, conf,
  effective_min_confluence: int, effective_min_confidence: int)` — one new
  positional parameter, threaded from `_sync_run_scan` through `_scan_one`
  exactly as `effective_min_confluence` already is.

**Why here:** both gates already meet in one helper. `embeds.py:206` compares
`confluence_count >= effective_min_confluence` and `embeds.py:214` compares
`conf.level >= config.MIN_ALERT_CONFIDENCE_LEVEL`. The confluence side already
receives its threshold as a parameter resolved once per scan at
`engine.py:1220`; this task gives the confidence side the same shape rather
than reaching into `config` from inside the helper.

- [ ] **Step 1: Write the failing test**

Create `tests/scanning/test_opex_gates.py`:

```python
"""The two alert gates tighten on an opex day and are untouched off one."""
import datetime as dt

import pytest

from swingbot import config
from swingbot.core.market import opex
from swingbot.core.scanning import embeds


class _Conf:
    def __init__(self, level):
        self.level = level
        self.label = "High"
        self.score = 70
        self.breakdown = {}


class _Scenario:
    """Minimal stand-in -- only what _build_requirement_checks reads."""
    def __init__(self):
        self.ticker = "TEST"
        self.strategy = "RSI"
        self.horizon_key = "1m"


def _checks(conf_level, min_confluence, min_confidence, confluence=(("EMA",), 3)):
    families, count = confluence
    scenario = _Scenario()
    return embeds._build_requirement_checks(
        scenario, (families, count), _Conf(conf_level),
        min_confluence, min_confidence,
    )


def _passed(checks, key):
    return next(c.passed for c in checks if c.key == key)


def test_confidence_check_uses_the_effective_level():
    # Lv4 passes a Lv4 bar and fails the Lv5 bar an opex day imposes.
    assert _passed(_checks(4, 2, 4), "min_confidence") is True
    assert _passed(_checks(4, 2, 5), "min_confidence") is False


def test_confluence_check_uses_the_effective_count():
    assert _passed(_checks(4, 3, 4), "min_confluence") is True
    assert _passed(_checks(4, 4, 4), "min_confluence") is False


def test_thresholds_are_unchanged_off_an_opex_day(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 4)
    thursday = dt.datetime(2026, 8, 20, 12, 0, tzinfo=opex.US_MARKET_TZ)
    tier = opex.current_tier(thursday)
    assert tier is None
    assert opex.effective_min_confidence_level(tier) == 4
    assert opex.effective_min_confluence(2, tier) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_opex_gates.py`
Expected: FAIL — `TypeError: _build_requirement_checks() takes 4 positional arguments but 5 were given`

- [ ] **Step 3: Thread the effective confidence level through**

In `swingbot/core/scanning/embeds.py`, change the signature at line 174:

```python
def _build_requirement_checks(scenario, target_confluence: tuple, conf,
                              effective_min_confluence: int,
                              effective_min_confidence: int) -> list:
```

and the confidence check at line 214, so the helper no longer reads config
directly:

```python
        RequirementCheck(
            key="min_confidence", label="Min confidence level", passed=conf.level >= effective_min_confidence,
            detail=f"Lv{conf.level} {conf.label} (needs Lv{effective_min_confidence}+)",
        ),
```

In `swingbot/core/scanning/engine.py`, at line 1220, resolve the tier once per
scan and apply both bumps:

```python
    # One calendar lookup per scan, passed down rather than re-derived per
    # ticker per horizon. `None` off an opex day (and whenever the feature is
    # off) leaves both thresholds exactly as configured.
    opex_tier_today = opex.current_tier()
    effective_min_confluence = config.MIN_TARGET_CONFLUENCE_COUNT if min_confluence is None else min_confluence
    effective_min_confluence = opex.effective_min_confluence(
        effective_min_confluence, opex_tier_today)
    effective_min_confidence = opex.effective_min_confidence_level(opex_tier_today)
```

with `from swingbot.core.market import opex` added to the module's imports.

Widen `_scan_one`'s signature (line 830-831) to take
`effective_min_confidence: int` alongside `effective_min_confluence: int`,
pass it at the call site (line 1374), and forward it at line 1139:

```python
            requirements = _build_requirement_checks(
                scenario, target_confluence, conf,
                effective_min_confluence, effective_min_confidence)
```

- [ ] **Step 4: Run the new test and the existing scan suites**

Run: `python scripts/dev/testrun.py file tests/scanning/test_opex_gates.py`
Expected: PASS

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: PASS — this suite calls the scan pipeline end to end and is what
catches a missed call site of the widened signature.

Run: `python scripts/dev/testrun.py file tests/scanning/test_confidence_levels.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/engine.py swingbot/core/scanning/embeds.py tests/scanning/test_opex_gates.py
git commit -m "feat(v44): raise the confidence and confluence bars on opex days"
```

---

### Task 5: Suppress new entries into the close

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` (`_build_requirement_checks`, after
  the `min_confidence` check added in Task 4)
- Test: `tests/scanning/test_opex_gates.py` (extend)

**Interfaces:**
- Consumes: `opex.suppress_new_entries` from Task 3.
- Produces: a `RequirementCheck` with `key="opex_close_window"`, appended only
  while the window is active.

**Why a requirement check rather than a new suppression path:** a scan tick
both looks for new trades *and* monitors open ones (`config.py:126`), so
suppression must land on the entry, not the tick. `RequirementCheck` is
already exactly that mechanism — it feeds `all_requirements_met`
(`engine.py:184-187`), which gates posting at `engine.py:1647`, and it is
counted into `stats["failed_counts"]` at `engine.py:1141-1144`, so the funnel
summary explains the quiet hour instead of leaving it a mystery. Open-trade
monitoring is untouched.

- [ ] **Step 1: Write the failing test**

Append to `tests/scanning/test_opex_gates.py`:

```python
def test_close_window_check_appears_only_while_suppressing(monkeypatch):
    monkeypatch.setattr(embeds.opex, "suppress_new_entries", lambda: True)
    keys = [c.key for c in _checks(5, 2, 4)]
    assert "opex_close_window" in keys
    assert _passed(_checks(5, 2, 4), "opex_close_window") is False


def test_close_window_check_absent_outside_the_window(monkeypatch):
    monkeypatch.setattr(embeds.opex, "suppress_new_entries", lambda: False)
    keys = [c.key for c in _checks(5, 2, 4)]
    assert "opex_close_window" not in keys
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_opex_gates.py::test_close_window_check_appears_only_while_suppressing`
Expected: FAIL — `AttributeError: module 'swingbot.core.scanning.embeds' has no attribute 'opex'`

- [ ] **Step 3: Add the check**

Add `from swingbot.core.market import opex` to `embeds.py`'s imports, then
append inside `_build_requirement_checks`, immediately before `return checks`:

```python
    # Appended only while the window is open, so an ordinary day's embeds
    # and funnel counters keep exactly the shape they have today. A failing
    # check blocks the post via `all_requirements_met` and is counted in the
    # funnel, which is what makes the quiet hour explainable afterwards.
    if opex.suppress_new_entries():
        checks.append(RequirementCheck(
            key="opex_close_window", label="Outside the opex close window", passed=False,
            detail=(
                f"Monthly opex: no new entries within "
                f"{config.OPEX_NEAR_CLOSE_SUPPRESS_MINUTES} min of the 16:00 US/Eastern close."
            ),
        ))

    return checks
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_opex_gates.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/scanning/test_opex_gates.py
git commit -m "feat(v44): no new entries inside the monthly-opex close window"
```

---

### Task 6: Widen the ATR stop

**Files:**
- Modify: `swingbot/core/planning/plan_engine.py:777`
- Test: `tests/planning/test_opex_stop_size.py`

**Interfaces:**
- Consumes: `opex.stop_mult` from Task 3.
- Produces: no signature change — the opex multiplier composes into the
  existing `applied_stop_mult` local.

**Constraint (from `plan_engine.py:770-776`):** only the ATR branch takes a
multiplier. The Fibonacci, Elliott and S/R branches put their stop behind real
structure, and scaling those would slide the stop off the level it exists to
sit behind — a deliberate E31 decision this task must not quietly reverse.
Composing at line 777 respects that automatically, because that local is only
consumed by `_atr_plan`.

- [ ] **Step 1: Write the failing test**

Create `tests/planning/test_opex_stop_size.py`:

```python
"""Opex widens the ATR stop and shrinks the position.

The stop half is modelled on tests/edge/test_edge_stops.py, which covers the
same `stop_mult` seam for E31's MAE multiplier -- including its point that
`_atr_plan` is the SHARED sizing source for the live builder and the
backtest, so anything composed into it must stay flag-gated.
"""
import pytest

from swingbot import config
from swingbot.core.market import opex
from swingbot.core.planning.plan_engine import build_strategy_plan
from tests.helpers import make_ohlcv


@pytest.fixture(scope="module")
def df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


def _plan(df, **kw):
    return build_strategy_plan(df, len(df) - 1, ticker="TEST", strategy="RSI",
                               horizon_key="4w", direction="bullish", **kw)


@pytest.fixture
def monthly_opex(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(config, "OPEX_STOP_WIDEN_PCT", 10.0)
    monkeypatch.setattr(config, "OPEX_SIZE_REDUCTION_PCT", 25.0)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.MONTHLY)


def test_stop_is_wider_on_monthly_opex(df, monkeypatch, monthly_opex):
    """The whole point: same bar, same strategy, a stop further from entry.

    Compared as an absolute price rather than a distance because TradePlanV2
    has no single `entry` field (it carries `trigger_price` and
    `entry_price`); on a bullish plan the stop sits below entry, so widening
    can only move it DOWN.
    """
    wide = _plan(df)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: None)
    base = _plan(df)
    assert base is not None and wide is not None
    assert wide.stop_loss < base.stop_loss


def test_stop_is_bit_identical_when_the_flag_is_off(df, monkeypatch):
    """Inert by default -- and this is the assertion that proves the
    multiplier never leaks into the backtest's shared sizing path."""
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    off = _plan(df)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.MONTHLY)
    still_off = _plan(df)      # tier says monthly, but the flag rules
    assert off.stop_loss == still_off.stop_loss


def test_opex_composes_with_an_explicit_stop_mult(df, monthly_opex):
    """An explicit caller multiplier is kept and widened on top, not
    replaced -- 1.2 * 1.10, never 1.10."""
    both = _plan(df, stop_mult=1.2)
    only_caller = _plan(df, stop_mult=1.2 * 1.10)
    assert both.stop_loss == pytest.approx(only_caller.stop_loss, rel=1e-9)


def test_zero_widen_is_a_no_op(df, monthly_opex, monkeypatch):
    monkeypatch.setattr(config, "OPEX_STOP_WIDEN_PCT", 0.0)
    assert opex.stop_mult() == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_opex_stop_size.py`
Expected: FAIL — `test_stop_is_wider_on_monthly_opex` fails because both
plans produce the identical stop: `plan_engine` does not consult `opex` yet.

- [ ] **Step 3: Compose the multiplier**

In `swingbot/core/planning/plan_engine.py`, replace line 777:

```python
        # Opex composes ON TOP of whatever multiplier was already resolved --
        # an explicit caller override or E31's per-strategy MAE figure -- so
        # neither silently replaces the other. Off an opex day stop_mult() is
        # exactly 1.0 and this line is a no-op.
        applied_stop_mult = stop_mult if stop_mult is not None else _resolve_stop_mult(strategy)
        applied_stop_mult = (applied_stop_mult or 1.0) * opex.stop_mult()
```

with `from swingbot.core.market import opex` added to the module's imports.

- [ ] **Step 4: Run the test and the plan-engine suite**

Run: `python scripts/dev/testrun.py file tests/planning/test_opex_stop_size.py`
Expected: PASS

Run: `python scripts/dev/testrun.py file tests/scanning/test_engine_v2_plans.py`
Expected: PASS — with the flag off, `stop_mult()` returns 1.0, so every
existing plan's stop must be byte-identical. A failure here means the
multiplier leaked into the flag-off path.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/plan_engine.py tests/planning/test_opex_stop_size.py
git commit -m "feat(v44): widen the ATR stop on monthly opex (structural stops untouched)"
```

---

### Task 7: Reduce position size

**Files:**
- Modify: `swingbot/core/planning/account.py` (immediately after the edge-mode
  block that ends at line 491, before the `balance <= 0` guard at line 493)
- Test: `tests/planning/test_opex_stop_size.py` (extend)

**Interfaces:**
- Consumes: `opex.size_mult` from Task 3.
- Produces: no signature change to `compute_position_size`.

**Both modes must scale.** `risk_pct` mode derives shares from
`risk_amount / stop_distance` (line 508-511) while `account_pct` mode derives
them from `balance * position_pct` (line 501-502) and never reads `risk_pct` at
all. Scaling only `risk_pct` would leave `account_pct` users with no size
reduction and nothing saying so.

- [ ] **Step 1: Write the failing test**

Append to `tests/planning/test_opex_stop_size.py`:

```python
from swingbot.core.planning.account import compute_position_size

#: The mode key is `sizing_mode` (account.py:473), NOT `mode` -- an unknown
#: key would silently fall through to the risk_pct default and make the
#: account_pct case below pass for the wrong reason. Both absolute caps are
#: pinned to 0 so the schema's own defaults cannot clip these figures.
BASE_CFG = {
    "balance": 10_000.0,
    "risk_pct": 1.0,
    "position_pct": 20.0,
    "max_position_pct": 100.0,
    "max_position_value_absolute": 0.0,
    "max_risk_amount_absolute": 0.0,
    "sizing_mode": "risk_pct",
}


def test_risk_pct_mode_scales_down(monthly_opex):
    got = compute_position_size(100.0, 95.0, dict(BASE_CFG))
    # 1% of 10k = $100 risk / $5 stop = 20 shares, cut 25% -> 15
    assert got["shares"] == pytest.approx(15, abs=0.01)


def test_account_pct_mode_scales_down(monthly_opex):
    got = compute_position_size(100.0, 95.0,
                                {**BASE_CFG, "sizing_mode": "account_pct"})
    # 20% of 10k = $2000 / $100 = 20 shares, cut 25% -> 15
    assert got["shares"] == pytest.approx(15, abs=0.01)


def test_size_is_untouched_when_the_flag_is_off(monkeypatch):
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    got = compute_position_size(100.0, 95.0, dict(BASE_CFG))
    assert got["shares"] == pytest.approx(20, abs=0.01)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/planning/test_opex_stop_size.py`
Expected: FAIL — both opex cases return 20 shares, not 15.

- [ ] **Step 3: Apply the multiplier**

In `swingbot/core/planning/account.py`, insert after line 491 (the
`mode = "risk_pct"` that closes the edge-mode block) and before the
`if balance <= 0` guard:

```python
    # Opex size reduction, applied after the edge estimators so it composes
    # with kelly/vol_target rather than being overwritten by them. BOTH modes
    # are scaled: account_pct never reads risk_pct, so scaling only that one
    # would silently exempt every account_pct user.
    _opex_size_mult = opex.size_mult()
    if _opex_size_mult != 1.0:
        risk_pct *= _opex_size_mult
        position_pct *= _opex_size_mult
```

with `from swingbot.core.market import opex` added to the module's imports.

- [ ] **Step 4: Run the test and the sizing suite**

Run: `python scripts/dev/testrun.py file tests/planning/test_opex_stop_size.py`
Expected: PASS

Run: `python scripts/dev/testrun.py fast`
Expected: PASS — sizing is read by `engine.py:283`, `embeds.py:327`,
`embeds.py:414`, `performance.py:370` and `admin/dashboard.py:495`, so this is
the point to sweep the fast tier rather than one file.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/planning/account.py tests/planning/test_opex_stop_size.py
git commit -m "feat(v44): reduce position size on monthly opex, both sizing modes"
```

---

### Task 8: Badge the alert embed

**Files:**
- Modify: `swingbot/core/scanning/embeds.py` — `build_embed` (line 438-439),
  in the `sections["headline"]` block that begins at line 489
- Test: `tests/scanning/test_embeds_v3.py` (extend — it already owns
  `build_embed` coverage and carries the `make_item` / `_build` helpers and
  the autouse snapshot-isolation fixture this needs)

**Interfaces:**
- Consumes: `opex.badge` from Task 3.
- Produces: nothing consumed elsewhere.

The badge posts on **every** alert that day, whether or not the tightened
gates changed the outcome — the reader needs the context to apply their own
judgement. This follows the `heat_blocked` precedent directly above it
(`embeds.py:491-501`, "Blocking is FLAGGED, never hidden").

- [ ] **Step 1: Write the failing test**

Append to `tests/scanning/test_embeds_v3.py`, directly below
`test_no_heat_blocked_attr_adds_no_field` (line 452-455) so the opex cases sit
beside the precedent they follow. `make_item`, `_build` and the autouse
snapshot-isolation fixture already exist in this file:

```python
def test_monthly_opex_renders_a_headline_field(monkeypatch):
    # v44: flagged on every alert that day, exactly like heat_blocked above.
    # The tightened gates already decided what posts; this tells the reader
    # what kind of day the survivors were found on.
    from swingbot.core.market import opex
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.MONTHLY)
    embed = _build(make_item())
    opex_fields = [f for f in embed.fields if "OPEX" in f.name]
    assert len(opex_fields) == 1
    assert "expiration" in opex_fields[0].value.lower()


def test_weekly_opex_renders_a_distinct_headline_field(monkeypatch):
    from swingbot.core.market import opex
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: opex.WEEKLY)
    embed = _build(make_item())
    assert [f for f in embed.fields if "eekly opex" in f.name]


def test_no_opex_field_off_an_expiration_day(monkeypatch):
    from swingbot.core.market import opex
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", True)
    monkeypatch.setattr(opex, "current_tier", lambda *a, **k: None)
    embed = _build(make_item())
    assert not [f for f in embed.fields if "opex" in f.name.lower()]


def test_no_opex_field_when_the_flag_is_off(monkeypatch):
    # The whole feature is inert by default: even on a real third Friday the
    # embed must be byte-identical to today's.
    monkeypatch.setattr(config, "OPEX_CAUTION_ENABLED", False)
    embed = _build(make_item())
    assert not [f for f in embed.fields if "opex" in f.name.lower()]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: FAIL — `assert len(opex_fields) == 1` fails with `0`, because
`build_embed` does not yet add the field.

- [ ] **Step 3: Add the headline field**

In `swingbot/core/scanning/embeds.py`, inside `build_embed`, immediately after
the `heat_blocked` block (which ends at line 501):

```python
    # Flagged on every alert that day, exactly like heat_blocked above: the
    # tightened gates already decided what posts, and this tells the reader
    # what kind of day the survivors were found on so they can apply their
    # own judgement to entry timing.
    opex_note = opex.badge()
    if opex_note is not None:
        sections["headline"].append((opex_note[0], opex_note[1], False))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: PASS — including the file's ~40 pre-existing embed assertions,
which must be unchanged: with the flag off `badge()` returns None and no
embed gains a field.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/scanning/test_embeds_v3.py
git commit -m "feat(v44): flag opex days on every alert embed"
```

---

### Task 9: Full-suite gate and documentation

**Files:**
- Modify: `docs/claude/architecture.md` (one line in the scan-pipeline section)
- Modify: `VERSION.json` (`bot` 1.3.2 → 1.4.0)
- Modify: `data/version_history.json` (regenerated)

- [ ] **Step 1: Run the full suite via the subagent**

Dispatch the `test-runner` subagent so ~1150 progress lines stay out of
context. Expected: `0 failed`, `0 xfailed`. Reference baseline is
`1686 passed, 66 skipped, 0 failed`; the count will have risen by the tests
this plan adds, and a changed count is not a failure — only `failed` is.

- [ ] **Step 2: Confirm the feature is genuinely inert by default**

Run: `git stash list` (expect nothing pending), then confirm
`OPEX_CAUTION_ENABLED=false` is what `.env.example` ships and that
`config.OPEX_CAUTION_ENABLED is False` in a fresh interpreter:

```bash
python -c "from swingbot import config; print(config.OPEX_CAUTION_ENABLED)"
```
Expected: `False`

- [ ] **Step 3: Document the feature**

Add one line to the scan-pipeline section of `docs/claude/architecture.md`
naming `swingbot/core/market/opex.py` as the opex calendar + policy module,
and noting that it is deliberately NOT a `market_context` column.

- [ ] **Step 4: Bump the version and regenerate history**

Set `bot` to `1.4.0` in `VERSION.json`, then regenerate and commit
`data/version_history.json` in the same commit — the local gate runs before
the bump and structurally cannot catch a missed regeneration.

- [ ] **Step 5: Commit**

```bash
git add VERSION.json data/version_history.json docs/claude/architecture.md
git commit -m "chore(v44): bot 1.4.0 -- opex-day caution"
```

---

## Parallelisation

- **Sequential: Task 1 → Task 3.** Task 3 consumes `opex_tier`, `MONTHLY`,
  `WEEKLY`, `US_MARKET_TZ` and `US_CLOSE_TIME`, and appends to the same file.
- **Task 2 is independent of Tasks 1 and 3** by file (`config.py` +
  `.env.example` versus `opex.py`), but Task 3's tests read the settings it
  adds, so run it before Task 3 or the fixture has nothing to patch. Order
  1 → 2 → 3 is the simplest correct sequence.
- **Sequential: Task 4 before Task 5.** Both edit
  `_build_requirement_checks` in `embeds.py`; Task 5's check is appended to
  the list Task 4 reshapes. Two agents here would overwrite rather than
  merge — this working tree is shared.
- **Group A (parallel): Task 6 and Task 7.** `plan_engine.py` and
  `account.py`, no shared file, and neither consumes a symbol the other
  introduces (both consume only Task 3's helpers).
- **Task 8 is sequential after Task 5**, same file (`embeds.py`) — different
  function, but the same file is the test that matters.
- **Task 9 last**, by definition: it gates on everything above.

Phase 1 (Tasks 1-3) must complete before any of Phase 2 starts — every
Phase 2 task consumes Task 3's policy helpers.
