# v229 — Deferred-entry counterfactual: Part 1b — tradeability and pair assembly (V229-4..V229-5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V229-5" -A 400 <this file>`); never read the file whole.

**Spec:** [2026-11-14-v229-deferred-entry-counterfactual-design.md](../specs/2026-11-14-v229-deferred-entry-counterfactual-design.md)
**Index:** [2026-11-15-v229-deferred-entry-counterfactual_0-index.md](2026-11-15-v229-deferred-entry-counterfactual_0-index.md) — Goal, `## Global Constraints`, `## Parallelisation`, the task ledger, the shared PAIR shape and the `## Handoff` resolutions bind every task below.

Part 1 of the ledger, second file: part 1 split at the 1500-line cap, never compressed. V229-1..V229-3 (time basis, simulator, arms) are in `2026-11-15-v229-deferred-entry-counterfactual_1-core.md`; the common test import pattern described there applies here too (put `scripts/reports` on `sys.path`, import `deferred_entry.<module>`).

# Phase 1 (continued) — tradeability

### Task V229-4: Tradeability record and event flags

**Model:** sonnet — disclosure fields with fixed definitions; arithmetic and calendar lookups, no gate depends on them.

**Files:**
- Create: `scripts/reports/deferred_entry/tradeability.py`
- Create: `tests/scripts/test_deferred_entry_tradeability.py`

**Interfaces:**
- Consumes: V229-3 `arms.ArmResult`, `arms.price_arms` (tests), `arms.deferral_bar` (tests); V229-2 `simulate.SIGN`; V229-1 `bars.ET`, `bars.BAR_MINUTES`, `bars.et_date`, `bars.session_open`, `bars.session_close_utc`, `bars.deferral_start`, `bars.horizon_end`, `bars.to_utc`, fixtures `et`, `five_min`; `swingbot.core.market.opex` (`opex_tier(d)`, `MONTHLY`, `monthly_expiration(y, m)`); `swingbot.core.market.market_events.FOMC_DECISION_DATES`; `swingbot.core.market.session` (`RTH_CLOSE`, `nyse_calendar().sessions_between`); `swingbot.core.market.events.get_earnings_datetimes(ticker)` (default lookup only, imported lazily).
- Produces (index ledger):
  - `FLAG_KEYS = ("earnings_after_close", "monthly_opex", "fomc", "event_day")`
  - `event_flags(ticker, entry_date, *, earnings_lookup=None) -> dict` with `earnings_after_close: bool | None` (None when the lookup fails), `monthly_opex: bool`, `fomc: bool`, `event_day: bool` (any of the three True)
  - `entry_bar_stopout(bars, *, opened_at, closed_at, live_reason) -> bool`
  - `plan_expired(plan_created_at, expiry_bars, entry_date) -> tuple[bool | None, int | None]` (`(expired, sessions_since_plan)`)
  - `day_extreme(bars, *, direction, session_start, deferral) -> float | None` (the day's adverse extreme so far: low for a long, high for a short; bars with `session_start <= index < deferral`)
  - `first_gap_r(bars, *, direction, risk, start, exit_ts) -> float | None`
  - `record(bars, *, direction, entry, stop, tp1, opened_at, deferral, arms, plan_created_at, expiry_bars, closed_at, live_reason, flags) -> dict` — `deferral` is the **deferral bar's start** (`arms.deferral_bar(...).name`, a bars index label); keys exactly: `fill_vs_entry_r, fill_above_entry, shifted_stop_above_day_low, day_low, day_low_vs_stop_r, price_1530_vs_entry_r, first_gap_r` (dict `{C, A, B}`), `bar_1530` (dict `{volume, range_r, open_vs_last_close_r}`), `plan_expired, sessions_since_plan, entry_bar_stopout` plus the four `FLAG_KEYS`.

**Definitions (spec § Tradeability record; all disclosure, gating nothing).** `sign` is +1 for a long, -1 for a short; `risk = |entry - stop|`; every `_r` is in the plan's R with `sign` applied (positive = favourable to the plan's side unless stated).

| Key | Definition |
|---|---|
| `fill_vs_entry_r` | `sign * (A.fill - entry) / risk` |
| `fill_above_entry` | `A.fill > entry` (raw price, both directions) — the split `analysis.split_deltas` uses |
| `day_low` | `day_extreme(...)` from the session open to the deferral bar (exclusive): the low for a long, the **high** for a short (the adverse extreme; the key keeps its name) |
| `shifted_stop_above_day_low` | `sign * (A.stop - day_low) > 0`: the shifted stop sits inside the range already traded |
| `day_low_vs_stop_r` | `sign * (day_low - stop) / risk` (negative: the original stop traded before 15:30, which is arm B's skip) |
| `price_1530_vs_entry_r` | `sign * (last close strictly before the deferral bar - entry) / risk` — the price as 15:30 arrived, "was the plan still live" |
| `first_gap_r[arm]` | first overnight gap inside the arm's holding window (from its start to its `exit_ts`): `sign * (first bar of the next session's open - previous bar's close) / risk`; `None` when the arm exited before any overnight or was skipped |
| `bar_1530.volume` / `.range_r` | the deferral bar's volume; `(High - Low) / risk` |
| `bar_1530.open_vs_last_close_r` | `sign * (deferral bar open - session's last 5-minute close) / risk`: positive means the 15:30 market fill was worse for the plan's side than a market-on-close fill (reads the rest of the session; disclosure only) |
| `plan_expired`, `sessions_since_plan` | Handoff 6: `sessions = nyse_calendar().sessions_between(ET date of plan_created_at, entry date)`, expired when `sessions >= int(expiry_bars)`; unparseable inputs give `None` |
| `entry_bar_stopout` | the live trade closed with a stop-class reason (`last_leg_reason`/`close_reason` starting `loss` or `stop`) before the end of the 5-minute bar containing `opened_at` — the stop-outs the control cannot see |
| `earnings_after_close` | any earnings stamp whose ET date is the entry date and ET time is at or after 16:00 (naive stamps read as ET); a failing lookup is `None`, never a failed pair |
| `monthly_opex` / `fomc` | `opex.opex_tier(d) == opex.MONTHLY` / `d in FOMC_DECISION_DATES` |

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_tradeability.py`:

```python
"""V229-4: the tradeability record -- shifted levels against the day so far,
overnight gaps, the 15:30 bar, plan validity, event days, entry-bar stops."""
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import arms  # noqa: E402
from deferred_entry import bars as tb  # noqa: E402
from deferred_entry import tradeability as tr  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.market import opex  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

D = dt.date(2026, 11, 3)
DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
OPENED = et("2026-11-03 10:02")
OVERRIDES = {
    "2026-11-03 11:00": (99.0, 99.2, 98.5, 99.0),      # day low so far 98.5 (stop 98 holds)
    "2026-11-03 15:25": (100.5, 100.7, 100.4, 100.6),  # price as 15:30 arrives
    "2026-11-03 15:30": (101.0, 101.05, 100.95, 101.0),
    "2026-11-04 09:30": (100.8, 100.85, 100.75, 100.8),  # overnight gap +0.8 over the 100 close
}
NO_FLAGS = {"earnings_after_close": False, "monthly_opex": False, "fomc": False, "event_day": False}


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)


def _record(frame, **extra):
    priced = arms.price_arms(frame, direction="bullish", entry=100.0, stop=98.0, tp1=104.0,
                             opened_at=OPENED, deferral=tb.deferral_start(D),
                             close=tb.session_close_utc(D), end=tb.horizon_end(D))
    bar = arms.deferral_bar(frame, tb.deferral_start(D), tb.session_close_utc(D))
    kwargs = dict(direction="bullish", entry=100.0, stop=98.0, tp1=104.0, opened_at=OPENED,
                  deferral=bar.name, arms=priced, plan_created_at="2026-11-02 14:00:00+00",
                  expiry_bars="5", closed_at=et("2026-11-03 13:00"), live_reason="tp1",
                  flags=NO_FLAGS)
    kwargs.update(extra)
    return tr.record(frame, **kwargs)


def test_record_has_exactly_the_ledger_keys():
    out = _record(five_min(DAYS, overrides=OVERRIDES))
    assert set(out) == {
        "fill_vs_entry_r", "fill_above_entry", "shifted_stop_above_day_low", "day_low",
        "day_low_vs_stop_r", "price_1530_vs_entry_r", "first_gap_r", "bar_1530",
        "plan_expired", "sessions_since_plan", "entry_bar_stopout", *tr.FLAG_KEYS}
    assert set(out["first_gap_r"]) == {"C", "A", "B"}
    assert set(out["bar_1530"]) == {"volume", "range_r", "open_vs_last_close_r"}


def test_record_values_on_a_crafted_day():
    out = _record(five_min(DAYS, overrides=OVERRIDES))
    assert out["fill_vs_entry_r"] == pytest.approx(0.5) and out["fill_above_entry"] is True
    assert out["day_low"] == pytest.approx(98.5)
    assert out["shifted_stop_above_day_low"] is True          # shifted stop 99 > 98.5
    assert out["day_low_vs_stop_r"] == pytest.approx(0.25)
    assert out["price_1530_vs_entry_r"] == pytest.approx(0.3)
    assert out["first_gap_r"] == pytest.approx({"C": 0.4, "A": 0.4, "B": 0.4})
    assert out["bar_1530"]["volume"] == 1000.0
    assert out["bar_1530"]["range_r"] == pytest.approx(0.05)
    assert out["bar_1530"]["open_vs_last_close_r"] == pytest.approx(0.5)
    assert (out["plan_expired"], out["sessions_since_plan"]) == (False, 1)
    assert out["entry_bar_stopout"] is False


def test_skipped_arm_b_and_same_day_exits_have_no_gap():
    frame = five_min(DAYS, overrides={"2026-11-03 11:00": (99.0, 99.0, 97.9, 98.5),
                                      "2026-11-04 09:30": (100.8, 100.85, 100.75, 100.8)})
    out = _record(frame)
    assert out["first_gap_r"]["B"] is None      # skipped
    assert out["first_gap_r"]["C"] is None      # stopped at 11:00 on the entry day
    assert out["first_gap_r"]["A"] == pytest.approx(0.4)
    assert out["day_low_vs_stop_r"] == pytest.approx(-0.05)


def test_no_lookahead_day_extreme_ignores_bars_from_1530():
    frame = five_min(DAYS, overrides={**OVERRIDES, "2026-11-03 15:40": (100.0, 100.0, 90.0, 95.0)})
    deferral = tb.deferral_start(D)
    kwargs = dict(direction="bullish", session_start=tb.session_open(D), deferral=deferral)
    assert tr.day_extreme(frame, **kwargs) == tr.day_extreme(frame[frame.index < deferral], **kwargs)
    assert tr.day_extreme(frame, **kwargs) == pytest.approx(98.5)
    short = dict(kwargs, direction="bearish")
    assert tr.day_extreme(frame, **short) == pytest.approx(100.7)


@pytest.mark.parametrize("closed, reason, expected", [
    ("2026-11-03 10:04", "loss", True),
    ("2026-11-03 10:04", "STOP", True),
    ("2026-11-03 10:06", "loss", False),
    ("2026-11-03 10:04", "tp1_partial", False),
    (None, "loss", False),
])
def test_entry_bar_stopout(closed, reason, expected):
    frame = five_min([D])
    closed_at = None if closed is None else et(closed)
    assert tr.entry_bar_stopout(frame, opened_at=OPENED, closed_at=closed_at,
                                live_reason=reason) is expected


@pytest.mark.parametrize("created, expiry, expected", [
    ("2026-10-28 14:00:00+00", "3", (True, 4)),    # 29, 30, Nov 2, Nov 3
    ("2026-10-28 14:00:00+00", "5", (False, 4)),
    ("2026-10-28 14:00:00+00", "", (None, 4)),
    ("", "5", (None, None)),
])
def test_plan_expired_under_its_own_rule(created, expiry, expected):
    assert tr.plan_expired(created, expiry, D) == expected


def _lookup(*stamps):
    return lambda ticker: list(stamps)


def test_earnings_after_the_close_on_the_entry_date():
    after = dt.datetime(2026, 11, 3, 16, 5, tzinfo=tb.ET)
    before = dt.datetime(2026, 11, 3, 8, 0, tzinfo=tb.ET)
    naive_after = dt.datetime(2026, 11, 3, 16, 30)
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(after))["earnings_after_close"] is True
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(before))["earnings_after_close"] is False
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(naive_after))["event_day"] is True
    other = dt.datetime(2026, 11, 4, 16, 5, tzinfo=tb.ET)
    assert tr.event_flags("AAPL", D, earnings_lookup=_lookup(other)) == NO_FLAGS


def test_a_failing_earnings_lookup_is_unknown_not_an_error():
    def boom(ticker):
        raise RuntimeError("network")
    out = tr.event_flags("AAPL", D, earnings_lookup=boom)
    assert out["earnings_after_close"] is None and out["event_day"] is False


def test_monthly_opex_and_fomc_days():
    opex_day = opex.monthly_expiration(2026, 11)
    assert tr.event_flags("AAPL", opex_day, earnings_lookup=_lookup())["monthly_opex"] is True
    fomc = tr.event_flags("AAPL", dt.date(2026, 10, 28), earnings_lookup=_lookup())
    assert fomc["fomc"] is True and fomc["event_day"] is True
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_tradeability.py`
Expected: collection error, `ImportError: cannot import name 'tradeability' from 'deferred_entry'`.

- [ ] **Step 3: Implement `tradeability.py`**

Create `scripts/reports/deferred_entry/tradeability.py`:

```python
"""v229 tradeability record (spec § Tradeability record). A deferred fill is
a different trade from the plan's, so each pair records what a follow-on
would need to judge it. Disclosure only: nothing here gates a verdict."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from swingbot.core.market import opex
from swingbot.core.market.market_events import FOMC_DECISION_DATES
from swingbot.core.market.session import RTH_CLOSE, nyse_calendar

from .bars import BAR_MINUTES, ET, et_date, session_close_utc, session_open, to_utc
from .simulate import SIGN

FLAG_KEYS = ("earnings_after_close", "monthly_opex", "fomc", "event_day")
_STOP_PREFIXES = ("loss", "stop")


def _default_earnings(ticker: str) -> list:
    from swingbot.core.market.events import get_earnings_datetimes
    return get_earnings_datetimes(ticker)


def _after_close_on(stamps, entry_date: dt.date) -> bool:
    for stamp in stamps:
        ts = pd.Timestamp(stamp)
        local = ts.tz_localize(ET) if ts.tzinfo is None else ts.tz_convert(ET)
        if local.date() == entry_date and local.time() >= RTH_CLOSE:
            return True
    return False


def event_flags(ticker: str, entry_date: dt.date, *, earnings_lookup=None) -> dict:
    lookup = earnings_lookup or _default_earnings
    try:
        earnings = _after_close_on(lookup(ticker) or [], entry_date)
    except Exception:  # noqa: BLE001 -- an unknown earnings date never fails a pair
        earnings = None
    monthly = opex.opex_tier(entry_date) == opex.MONTHLY
    fomc = entry_date in FOMC_DECISION_DATES
    return {"earnings_after_close": earnings, "monthly_opex": monthly, "fomc": fomc,
            "event_day": bool(earnings) or monthly or fomc}


def _entry_bar_start(bars, opened_at) -> pd.Timestamp:
    if bars is not None and not bars.empty:
        before = bars.index[bars.index <= opened_at]
        if len(before):
            return before[-1]
    return opened_at.floor(f"{BAR_MINUTES}min")


def entry_bar_stopout(bars, *, opened_at, closed_at, live_reason) -> bool:
    """The live trade was stopped inside the bar containing its entry."""
    reason = (live_reason or "").strip().lower()
    if closed_at is None or not reason.startswith(_STOP_PREFIXES):
        return False
    start = _entry_bar_start(bars, opened_at)
    return closed_at < start + pd.Timedelta(minutes=BAR_MINUTES)


def plan_expired(plan_created_at, expiry_bars, entry_date: dt.date) -> tuple[bool | None, int | None]:
    try:
        created = et_date(to_utc(plan_created_at))
    except ValueError:
        return None, None
    sessions = nyse_calendar().sessions_between(created, entry_date)
    if sessions is None:
        return None, None
    try:
        limit = int(float(expiry_bars))
    except (TypeError, ValueError):
        return None, sessions
    return sessions >= limit, sessions


def day_extreme(bars, *, direction: str, session_start, deferral) -> float | None:
    """The day's adverse extreme before 15:30: the low (long) or high (short)."""
    window = bars[(bars.index >= session_start) & (bars.index < deferral)]
    if window.empty:
        return None
    return float(window["Low"].min()) if SIGN[direction] > 0 else float(window["High"].max())


def first_gap_r(bars, *, direction: str, risk: float, start, exit_ts) -> float | None:
    """The first overnight gap inside [start, exit_ts], in R; None without one."""
    if start is None or exit_ts is None:
        return None
    window = bars[(bars.index >= start) & (bars.index <= to_utc(exit_ts))]
    days = window.index.tz_convert(ET).date
    for i in range(1, len(window)):
        if days[i] != days[i - 1]:
            gap = float(window["Open"].iloc[i]) - float(window["Close"].iloc[i - 1])
            return SIGN[direction] * gap / risk
    return None


def _last_close_before(bars, d: dt.date, deferral) -> float | None:
    window = bars[(bars.index >= session_open(d)) & (bars.index < deferral)]
    return None if window.empty else float(window["Close"].iloc[-1])


def _bar_1530(bars, d: dt.date, deferral, sign: int, risk: float) -> dict:
    bar = bars.loc[deferral]
    session = bars[(bars.index >= session_open(d)) & (bars.index < session_close_utc(d))]
    last_close = float(session["Close"].iloc[-1])
    return {"volume": float(bar["Volume"]),
            "range_r": (float(bar["High"]) - float(bar["Low"])) / risk,
            "open_vs_last_close_r": sign * (float(bar["Open"]) - last_close) / risk}


def _levels(sign: int, risk: float, entry: float, stop: float, arm_a, low) -> dict:
    return {
        "fill_vs_entry_r": sign * (arm_a.fill - entry) / risk,
        "fill_above_entry": bool(arm_a.fill > entry),
        "day_low": low,
        "shifted_stop_above_day_low": None if low is None else bool(sign * (arm_a.stop - low) > 0),
        "day_low_vs_stop_r": None if low is None else sign * (low - stop) / risk,
    }


def _gaps(bars, direction: str, risk: float, opened_at, deferral, arms: dict) -> dict:
    starts = {"C": opened_at, "A": deferral, "B": deferral if arms["B"].taken else None}
    return {name: first_gap_r(bars, direction=direction, risk=risk, start=starts[name],
                              exit_ts=arms[name].exit_ts) for name in ("C", "A", "B")}


def record(bars, *, direction: str, entry: float, stop: float, tp1: float, opened_at,
           deferral, arms: dict, plan_created_at, expiry_bars, closed_at, live_reason,
           flags: dict) -> dict:
    """The tradeability record of one pair; ``deferral`` is the 15:30 bar's start."""
    sign, risk, d = SIGN[direction], abs(entry - stop), et_date(opened_at)
    low = day_extreme(bars, direction=direction, session_start=session_open(d), deferral=deferral)
    last = _last_close_before(bars, d, deferral)
    expired, sessions = plan_expired(plan_created_at, expiry_bars, d)
    return {
        **_levels(sign, risk, entry, stop, arms["A"], low),
        "price_1530_vs_entry_r": None if last is None else sign * (last - entry) / risk,
        "first_gap_r": _gaps(bars, direction, risk, opened_at, deferral, arms),
        "bar_1530": _bar_1530(bars, d, deferral, sign, risk),
        "plan_expired": expired,
        "sessions_since_plan": sessions,
        "entry_bar_stopout": entry_bar_stopout(bars, opened_at=opened_at, closed_at=closed_at,
                                               live_reason=live_reason),
        **{key: flags[key] for key in FLAG_KEYS},
    }
```

`tp1` is accepted for the ledger signature and future fields; it is not read today (TP1 enters through `arms`).

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_tradeability.py`
Expected: every test passes, `0 failed`.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new function at or above 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/deferred_entry/tradeability.py tests/scripts/test_deferred_entry_tradeability.py
git commit -m "feat(v229): tradeability record and event-day flags (V229-4)"
```

# Phase 2 — export and pair assembly

### Task V229-5: Export reader, funnel and pair assembly

**Model:** opus — the population funnel decides which plans enter the verdict; the PAIR shape is the contract every part-2 module reads.

**Files:**
- Create: `scripts/reports/deferred_entry/pairs.py`
- Create: `tests/scripts/test_deferred_entry_pairs.py`

**Interfaces:**
- Consumes: V229-1 `bars.ET`, `bars.DEFER_AT`, `bars.to_utc`, `bars.et_date`, `bars.et_time`, `bars.deferral_start`, `bars.session_close_utc`, `bars.horizon_end`, fixtures `et`, `five_min`; V229-3 `arms.price_arms`, `arms.deferral_bar`; V229-4 `tradeability.record`, `tradeability.event_flags`; `swingbot.core.market.session` (`RTH_OPEN`, `session_close`, `nyse_calendar()` with `is_session`, `sessions`, `session_after`); `swingbot.core.scanning.risk_features.session_bucket(now)` (`now` already ET); `swingbot.core.backtesting.instrument.stats.iso_week_key(d)`.
- Produces (index ledger):
  - `REQUIRED_COLUMNS` — the export names this module reads: `("row_kind", "trade_id", "ticker", "direction", "entry_type", "plan_created_at", "expiry_bars", "opened_at", "entry", "stop_loss", "take_profit", "closed_at", "close_reason", "last_leg_reason", "outcome", "r_realized", "session_bucket")`
  - `REASONS = ("not_trade", "not_market", "entry_type_unknown", "bad_levels", "outside_session", "close_bucket", "no_coverage", "pending", "no_deferral_bar", "eligible")`
  - `DIRECTIONS = {"bullish": "bullish", "long": "bullish", "bearish": "bearish", "short": "bearish"}` (the export's domain per `scripts/reports/autopsy/rows.py:_SHORT`)
  - `read_export(path) -> list[dict[str, str]]` (`csv.DictReader`; `ValueError` naming every missing required column; extra columns, such as v228's column 39, are ignored)
  - `classify(row, bars, *, archive_end) -> str` (one of `REASONS`; `archive_end` is an ISO string or Timestamp, or None)
  - `build_pair(row, bars, *, rule_hash, earnings_lookup=None) -> dict` — the index's **PAIR** shape, for a row `classify` called `eligible`; JSON-serialisable.

**Funnel, in order (index Global Constraints "Population"; Handoff 10, 11):**

1. `not_trade` — `row_kind != "trade"` (plan rows carry no fill).
2. `entry_type_unknown` — blank `entry_type` (the plan join missed); never assumed market.
3. `not_market` — any other `entry_type`.
4. `bad_levels` — unknown direction, unparseable levels, or levels on the wrong side (`sign * (entry - stop) > 0` and `sign * (tp1 - entry) > 0` must both hold).
5. `outside_session` — `opened_at` unparseable, not an NYSE session day, or outside `[09:30, that day's close)` ET.
6. `close_bucket` — opened at or after 15:30 ET (already a late entry; the CLI prints these as context).
7. `pending` — the archive's last bar is earlier than `horizon_end - 15 minutes` (or there is no archive): the next run recounts it; never logged.
8. `no_coverage` — no bars file, the horizon past the calendar, a session between the entry date and the fifth session after it without a bar (on the entry date: no bar at or after `opened_at`), or no bar starting at or after `horizon_end - 15 minutes`.
9. `no_deferral_bar` — a half day on the entry date (`deferral_start` is None), or no bar in `[15:30 ET, close)`.
10. `eligible`.

Direction is **not** a funnel step: bearish rows are eligible here, and the CLI (V229-10) keeps them in memory as the disclosure (Handoff 15). `bucket` is recomputed from `opened_at` through `risk_features.session_bucket`, the live writer's own rule, rather than trusted from the export column.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_deferred_entry_pairs.py`:

```python
"""V229-5: reading the export by column name, the population funnel, and one
assembled pair in the shared PAIR shape."""
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "reports"))
from deferred_entry import pairs  # noqa: E402
from swingbot import config  # noqa: E402
from tests.scripts.v229_fixtures import et, five_min  # noqa: E402

DAYS = ["2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
ARCHIVE_END = et("2026-11-10 15:55").isoformat()
NO_EARNINGS = lambda ticker: []  # noqa: E731 -- never touch the network in tests
PAIR_KEYS = {"trade_id", "ticker", "direction", "opened_at", "entry_date", "iso_week", "bucket",
             "trade", "arms", "live", "tradeability", "coverage", "rule_hash"}


@pytest.fixture(autouse=True)
def _frictions(monkeypatch):
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)


def _row(**over):
    row = {"row_kind": "trade", "trade_id": "t-1", "plan_id": "p-1", "ticker": "AAPL",
           "strategy": "S/R Confluence", "horizon": "4w", "direction": "bullish",
           "plan_created_at": "2026-11-02 14:00:00+00", "entry_type": "market",
           "expiry_bars": "5", "opened_at": "2026-11-03 15:02:00+00",   # 10:02 ET
           "entry": "100.0", "stop_loss": "98.0", "take_profit": "104.0",
           "closed_at": "2026-11-03 16:30:00+00", "close_reason": "stop",
           "last_leg_reason": "loss", "outcome": "loss", "r_realized": "-1.02",
           "session_bucket": "open"}
    row.update(over)
    return row


def _classify(row, frame=None, archive_end=ARCHIVE_END):
    return pairs.classify(row, five_min(DAYS) if frame is None else frame, archive_end=archive_end)


def _write(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_read_export_reads_by_name_and_ignores_extra_columns(tmp_path):
    row = _row(excursion_source="archive")
    fields = list(reversed(list(row)))           # any order, 39th column present
    _write(tmp_path / "rows.csv", [row], fields)
    out = pairs.read_export(tmp_path / "rows.csv")
    assert out[0]["trade_id"] == "t-1" and out[0]["take_profit"] == "104.0"


def test_read_export_names_missing_columns(tmp_path):
    row = _row()
    fields = [f for f in row if f not in ("entry_type", "take_profit")]
    _write(tmp_path / "rows.csv", [{f: row[f] for f in fields}], fields)
    with pytest.raises(ValueError, match="entry_type.*take_profit"):
        pairs.read_export(tmp_path / "rows.csv")


@pytest.mark.parametrize("over, reason", [
    ({"row_kind": "plan"}, "not_trade"),
    ({"entry_type": ""}, "entry_type_unknown"),
    ({"entry_type": "stop_entry"}, "not_market"),
    ({"stop_loss": "101.0"}, "bad_levels"),
    ({"take_profit": "99.0"}, "bad_levels"),
    ({"direction": "sideways"}, "bad_levels"),
    ({"entry": ""}, "bad_levels"),
    ({"opened_at": "2026-11-03 13:00:00+00"}, "outside_session"),   # 08:00 ET
    ({"opened_at": "2026-11-07 15:00:00+00"}, "outside_session"),   # Saturday
    ({"opened_at": ""}, "outside_session"),
    ({"opened_at": "2026-11-03 20:31:00+00"}, "close_bucket"),      # 15:31 ET
    ({}, "eligible"),
    ({"direction": "long"}, "eligible"),
    ({"direction": "bearish", "stop_loss": "102.0", "take_profit": "96.0"}, "eligible"),
])
def test_static_funnel(over, reason):
    assert _classify(_row(**over)) == reason


def test_pending_until_the_archive_reaches_the_fifth_session():
    assert _classify(_row(), archive_end=et("2026-11-10 12:00").isoformat()) == "pending"
    assert _classify(_row(), archive_end=None) == "pending"
    assert _classify(_row(), archive_end=et("2026-11-10 15:45")) == "eligible"


def test_no_coverage_without_a_file_or_with_a_missing_session():
    assert pairs.classify(_row(), None, archive_end=ARCHIVE_END) == "no_coverage"
    frame = five_min([d for d in DAYS if d != "2026-11-05"])
    assert _classify(_row(), frame) == "no_coverage"
    short = five_min(DAYS)
    assert _classify(_row(), short[short.index < et("2026-11-10 14:00")]) == "no_coverage"


def test_no_deferral_bar_on_a_half_day_or_without_a_1530_bar():
    half = ["2026-11-27", "2026-11-30", "2026-12-01", "2026-12-02", "2026-12-03", "2026-12-04"]
    row = _row(opened_at="2026-11-27 15:02:00+00")                   # 10:02 ET, 13:00 close
    assert pairs.classify(row, five_min(half), archive_end=et("2026-12-04 15:55")) == "no_deferral_bar"
    frame = five_min(DAYS)
    gap = (frame.index >= et("2026-11-03 15:30")) & (frame.index < et("2026-11-03 16:00"))
    assert _classify(_row(), frame[~gap]) == "no_deferral_bar"


def test_every_reason_is_declared():
    assert set(pairs.REASONS) >= {"not_trade", "eligible", "pending", "no_coverage"}
    assert len(set(pairs.REASONS)) == len(pairs.REASONS) == 10


def _pair(row=None, frame=None):
    return pairs.build_pair(row or _row(), frame if frame is not None else five_min(DAYS),
                            rule_hash="0123abcd4567ef89", earnings_lookup=NO_EARNINGS)


def test_build_pair_has_the_pair_shape_and_serialises():
    out = _pair()
    assert set(out) == PAIR_KEYS
    assert json.loads(json.dumps(out)) == out
    assert (out["trade_id"], out["ticker"], out["direction"]) == ("t-1", "AAPL", "bullish")
    assert out["entry_date"] == "2026-11-03" and out["iso_week"] == "2026-W45"
    assert out["opened_at"] == et("2026-11-03 10:02").isoformat()
    assert out["trade"] == {"entry": 100.0, "stop_loss": 98.0, "take_profit": 104.0}
    assert set(out["arms"]) == {"C", "A", "B"} and out["arms"]["A"]["arm"] == "A"
    assert out["live"] == {"reason": "loss", "outcome": "loss", "r_realized": -1.02}
    assert out["rule_hash"] == "0123abcd4567ef89"
    assert out["coverage"] == {"bars_from": et("2026-11-03 10:05").isoformat(),
                               "bars_to": et("2026-11-10 15:55").isoformat(),
                               "deferral_bar": et("2026-11-03 15:30").isoformat()}
    assert out["tradeability"]["earnings_after_close"] is False


@pytest.mark.parametrize("opened, bucket", [("2026-11-03 15:02:00+00", "open"),
                                            ("2026-11-03 17:00:00+00", "midday")])
def test_bucket_is_recomputed_from_opened_at(opened, bucket):
    assert _pair(_row(opened_at=opened, session_bucket="close"))["bucket"] == bucket


def test_live_reason_falls_back_to_close_reason_and_blank_r_is_none():
    out = _pair(_row(last_leg_reason="", close_reason="manual", r_realized=""))
    assert out["live"]["reason"] == "manual" and out["live"]["r_realized"] is None


def test_bearish_pair_is_built_for_the_disclosure():
    out = _pair(_row(direction="short", stop_loss="102.0", take_profit="96.0"))
    assert out["direction"] == "bearish"
    assert out["arms"]["A"]["stop"] == pytest.approx(102.0)


def test_build_pair_refuses_a_row_with_bad_levels():
    with pytest.raises(ValueError, match="levels"):
        _pair(_row(stop_loss="101.0"))
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_pairs.py`
Expected: collection error, `ImportError: cannot import name 'pairs' from 'deferred_entry'`.

- [ ] **Step 3: Implement `pairs.py`**

Create `scripts/reports/deferred_entry/pairs.py`:

```python
"""v229 export reader, population funnel and pair assembly.

The export (scripts/ops/export_book_rows.sh rows) is read BY COLUMN NAME, so
today's 38 columns and v228's 39 both work; autopsy/rows.load_rows is never
used (v228 makes it refuse an older CSV). classify() names why each trade is
in or out -- every reason is counted, an absent archive file included
(known-traps: a silent skip would hide a measured answer)."""
from __future__ import annotations

import csv

import pandas as pd

from swingbot.core.backtesting.instrument.stats import iso_week_key
from swingbot.core.market.session import RTH_OPEN, nyse_calendar, session_close
from swingbot.core.scanning.risk_features import session_bucket

from .arms import deferral_bar, price_arms
from .bars import (DEFER_AT, ET, deferral_start, et_date, et_time, horizon_end,
                   session_close_utc, to_utc)
from .tradeability import event_flags, record

REQUIRED_COLUMNS = ("row_kind", "trade_id", "ticker", "direction", "entry_type",
                    "plan_created_at", "expiry_bars", "opened_at", "entry", "stop_loss",
                    "take_profit", "closed_at", "close_reason", "last_leg_reason", "outcome",
                    "r_realized", "session_bucket")
REASONS = ("not_trade", "not_market", "entry_type_unknown", "bad_levels", "outside_session",
           "close_bucket", "no_coverage", "pending", "no_deferral_bar", "eligible")
DIRECTIONS = {"bullish": "bullish", "long": "bullish", "bearish": "bearish", "short": "bearish"}
_SIGN = {"bullish": 1, "bearish": -1}
_LAST_BAR_SLACK = pd.Timedelta(minutes=15)
HOLD_SESSIONS = 5


def read_export(path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        present = set(reader.fieldnames or ())
        missing = [c for c in REQUIRED_COLUMNS if c not in present]
        if missing:
            raise ValueError(f"{path}: export lacks columns {', '.join(missing)}")
        return [dict(row) for row in reader]


def _text(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _float_or_none(text) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _levels(row: dict) -> tuple[str, float, float, float] | None:
    direction = DIRECTIONS.get(_text(row, "direction").lower())
    values = [_float_or_none(_text(row, k)) for k in ("entry", "stop_loss", "take_profit")]
    if direction is None or None in values:
        return None
    entry, stop, tp1 = values
    sign = _SIGN[direction]
    if sign * (entry - stop) <= 0 or sign * (tp1 - entry) <= 0:
        return None
    return direction, entry, stop, tp1


def _opened(row: dict) -> pd.Timestamp | None:
    try:
        return to_utc(_text(row, "opened_at"))
    except ValueError:
        return None


def _in_session(row: dict) -> bool:
    opened = _opened(row)
    if opened is None:
        return False
    d = et_date(opened)
    return nyse_calendar().is_session(d) and RTH_OPEN <= et_time(opened) < session_close(d)


_STATIC_CHECKS = (
    ("not_trade", lambda r: _text(r, "row_kind") != "trade"),
    ("entry_type_unknown", lambda r: not _text(r, "entry_type")),
    ("not_market", lambda r: _text(r, "entry_type").lower() != "market"),
    ("bad_levels", lambda r: _levels(r) is None),
    ("outside_session", lambda r: not _in_session(r)),
    ("close_bucket", lambda r: et_time(_opened(r)) >= DEFER_AT),
)


def _covered(bars, opened: pd.Timestamp, end: pd.Timestamp) -> bool:
    if bars is None or bars.empty:
        return False
    window = bars[(bars.index >= opened) & (bars.index < end)]
    if window.empty or window.index[-1] < end - _LAST_BAR_SLACK:
        return False
    have = set(window.index.tz_convert(ET).date)
    d = et_date(opened)
    cal = nyse_calendar()
    return all(s in have for s in cal.sessions(d, cal.session_after(d, HOLD_SESSIONS)))


def _coverage_reason(bars, opened: pd.Timestamp, archive_end) -> str:
    d = et_date(opened)
    end = horizon_end(d, HOLD_SESSIONS)
    if end is None:
        return "no_coverage"
    last = None if archive_end is None else to_utc(archive_end)
    if last is None or last < end - _LAST_BAR_SLACK:
        return "pending"
    if not _covered(bars, opened, end):
        return "no_coverage"
    if deferral_bar(bars, deferral_start(d), session_close_utc(d)) is None:
        return "no_deferral_bar"
    return "eligible"


def classify(row: dict, bars, *, archive_end) -> str:
    """The funnel reason of one export row (one of REASONS)."""
    for reason, failed in _STATIC_CHECKS:
        if failed(row):
            return reason
    return _coverage_reason(bars, _opened(row), archive_end)


def _live(row: dict) -> dict:
    return {"reason": _text(row, "last_leg_reason") or _text(row, "close_reason"),
            "outcome": _text(row, "outcome") or None,
            "r_realized": _float_or_none(_text(row, "r_realized") or None)}


def _closed_at(row: dict) -> pd.Timestamp | None:
    try:
        return to_utc(_text(row, "closed_at"))
    except ValueError:
        return None


def build_pair(row: dict, bars, *, rule_hash: str, earnings_lookup=None) -> dict:
    """One PAIR (index § Shared shapes) for a row classify() called eligible."""
    levels = _levels(row)
    if levels is None:
        raise ValueError(f"trade {_text(row, 'trade_id')}: bad levels")
    direction, entry, stop, tp1 = levels
    opened = to_utc(_text(row, "opened_at"))
    d = et_date(opened)
    deferral, close, end = deferral_start(d), session_close_utc(d), horizon_end(d, HOLD_SESSIONS)
    priced = price_arms(bars, direction=direction, entry=entry, stop=stop, tp1=tp1,
                        opened_at=opened, deferral=deferral, close=close, end=end)
    bar = deferral_bar(bars, deferral, close)
    live = _live(row)
    flags = event_flags(_text(row, "ticker"), d, earnings_lookup=earnings_lookup)
    trade_record = record(
        bars, direction=direction, entry=entry, stop=stop, tp1=tp1, opened_at=opened,
        deferral=bar.name, arms=priced, plan_created_at=_text(row, "plan_created_at"),
        expiry_bars=_text(row, "expiry_bars"), closed_at=_closed_at(row),
        live_reason=live["reason"], flags=flags)
    window = bars[(bars.index >= opened) & (bars.index < end)]
    return {
        "trade_id": _text(row, "trade_id"), "ticker": _text(row, "ticker"),
        "direction": direction, "opened_at": opened.isoformat(), "entry_date": d.isoformat(),
        "iso_week": iso_week_key(d),
        "bucket": session_bucket(opened.tz_convert(ET).to_pydatetime()),
        "trade": {"entry": entry, "stop_loss": stop, "take_profit": tp1},
        "arms": {name: result.to_dict() for name, result in priced.items()},
        "live": live,
        "tradeability": trade_record,
        "coverage": {"bars_from": window.index[0].isoformat(),
                     "bars_to": window.index[-1].isoformat(),
                     "deferral_bar": bar.name.isoformat()},
        "rule_hash": rule_hash,
    }
```

`build_pair` assumes `classify(...) == "eligible"`; the CLI (V229-10) never calls it otherwise. The ET entry date, not the UTC date, is the `entry_date` and the ISO-week cluster key (`week_cluster_bootstrap` clusters on it; Global Constraints "Statistic").

- [ ] **Step 4: Run the tests to see them pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_pairs.py`
Expected: every test passes, `0 failed`.

Run the whole part once more, narrowly, to confirm the five modules agree:

```bash
python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_bars.py
python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_simulate.py
python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_arms.py
python scripts/dev/testrun.py file tests/scripts/test_deferred_entry_tradeability.py
```

Expected: `0 failed` in each.

Run: `python scripts/dev/complexity_gate.py`
Expected: no new function at or above 15.

- [ ] **Step 5: Commit**

```bash
git add scripts/reports/deferred_entry/pairs.py tests/scripts/test_deferred_entry_pairs.py
git commit -m "feat(v229): export reader, population funnel and pair assembly (V229-5)"
```
