# v189 part 1 — Metrics and calendar: one R, the leg contribution, net-R labels, the golden fixture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier.

**Bump:** bot patch, ui patch
**Edge:** none (integrity)
**Spec:** [2026-10-23-v189-book-integrity-partial-truth-design.md](../specs/2026-10-23-v189-book-integrity-partial-truth-design.md) — its `## Corrections from the code brief` section wins.
**Index:** [2026-10-23-v189-book-integrity-partial-truth_0-index.md](2026-10-23-v189-book-integrity-partial-truth_0-index.md) — Goal, Global Constraints, Contracts, `## Parallelisation` and the task ledger live there; every task below implicitly includes the index's Global Constraints.

**Scope of this part:** V189-1..V189-4 — the worktree and prod-db replica; `metrics.r_multiple` as the one trade-level R with `leg_contribution_r`, `banked_contribution_r` and `open_trade_r` beside it; `net_outcome` and the shared golden fixture with the backtest parity pin; the retrospective on `metrics.r_multiple`; the Calendar summing leg contributions.

**Working directory.** Every command below runs inside the worktree `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` (created in V189-1 Step 1). Agent shells reset their cwd and drop variables between calls, so `cd "$WT"` below means: set `WT=E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` in the same command (`WT=...; cd "$WT" && ...`) or substitute the path.

**Golden-fixture note (decided while writing this part, 2026-10-23).** The index's fixture sketch gives `calendar_day.trade_count = 2` and `win_rate = 50.0`. Under `pnl_calendar`'s existing day semantics (each realized leg of a scaled-out trade is its own row with its own outcome, `day_summary.trade_count = len(rows)`, `win_rate` over row outcomes), the golden manual-close trade with both legs on the day plus the −1R loss is **three** rows (TP1 leg win, runner leg win, loss), so `trade_count = 3` and `win_rate = 66.67`. The `net_r = 1.5` and `net_pnl_amount = 1050.0` keys need both legs on that day, so the day cannot be read as two rows. V189-2 writes the fixture with `trade_count: 3` and `win_rate: 66.66666666666667`; spec Correction 2 (calendar counts legs; the counting unit is the metric spec's question) is why. No other part reads `calendar_day`.

---

# Phase 1 — One R

### Task V189-1: Worktree, prod-db replica; one trade-level R and the leg contribution

**Model:** opus — first task of a cross-cutting plan: gates on v187, creates the worktree, and restructures the one shared R function every metric reads.

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (`r_multiple`, today at `:173-218`; new helpers beside it)
- Modify: `swingbot/core/tracking/performance.py` (`closed_r_multiple`, today at `:332-379`)
- Create: `tests/analytics/test_metrics_leg_contribution.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (used by V189-2, V189-3, V189-4, V189-18, V189-20 and part 3):
  - worktree `.claude/worktrees/2026-10-23-v189-book-integrity-partial-truth` on branch `2026-10-23-v189-book-integrity-partial-truth`
  - `metrics.leg_contribution_r(leg: dict) -> float | None` — `fraction * r`; None when either is missing
  - `metrics._blended_r_raw(trade: dict) -> float | None` — `r_multiple`'s body, never rounded (legs and single exit)
  - `metrics.r_multiple(trade: dict) -> float | None` — `round(raw, 2)` when the trade has legs, `raw` otherwise (results unchanged)
  - `metrics.banked_contribution_r(legs: list[dict] | None) -> float | None` — sum of `leg_contribution_r`; None for no legs or any None contribution
  - `metrics.open_trade_r(trade: dict, quote: float | None) -> float | None` — banked contribution plus the open fraction's live R at `quote`
  - `performance.closed_r_multiple(t)` returns `round(metrics.r_multiple(t), 2)` (None passes through)

- [ ] **Step 1: Check v187 is merged, then create the worktree**

```bash
cd E:/Documents/Private/Projects/Discord-Bot && git grep -n "PENDING_CANCEL_EVENTS" main -- swingbot/core/planning/plan_manager.py
```

Expected: at least one line (the v187 `PENDING_CANCEL_EVENTS = frozenset({...})`). **If it prints nothing, stop and report `BLOCKED: v187 is not merged on main`** — the whole plan builds on v187 (index § Global Constraints).

Then:

```bash
cd E:/Documents/Private/Projects/Discord-Bot && git worktree list && git worktree add .claude/worktrees/2026-10-23-v189-book-integrity-partial-truth -b 2026-10-23-v189-book-integrity-partial-truth main
```

If `git worktree list` already shows this worktree, reuse it and skip the `add` (resume rule, `docs/claude/document-lifecycle.md`).

- [ ] **Step 2: Replicate the production database**

Run the `/replicate-prod-db` skill once (partner rule: a task that runs tests against the database replicates first; every pytest test here uses the autouse Postgres fixture). Expected: the skill's row-count check passes. Not repeated in later tasks of this plan.

- [ ] **Step 3: Write the failing tests**

Create `tests/analytics/test_metrics_leg_contribution.py`:

```python
"""v189 D1: one trade-level R (`metrics.r_multiple`) and one leg
contribution (`fraction x r`) that every leg sum uses.

Golden geometry (spec § Testing): 100 shares, entry 100, stop 95 (1R = $5),
TP1 110 on half the position (+2R), runner on the other half. Every value
below is hand-computed.
"""
import math

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.tracking.performance import closed_r_multiple

TP1_LEG = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}
#: A price with a long binary expansion, so rounding would show.
ODD_PRICE = 101.0 + 1.0 / 3.0


def _trade(legs=None, *, exit_price=None, direction="bullish", entry=100.0, stop=95.0):
    trade = {"direction": direction, "entry": entry, "stop_loss": stop,
             "exit_price": exit_price, "shares": 100}
    if legs is not None:
        trade["legs"] = [dict(leg) for leg in legs]
    return trade


# --- leg_contribution_r ------------------------------------------------------

def test_leg_contribution_is_fraction_times_r():
    assert metrics.leg_contribution_r(TP1_LEG) == pytest.approx(1.0)
    assert metrics.leg_contribution_r({"fraction": 0.5, "r": -2.4}) == pytest.approx(-1.2)


@pytest.mark.parametrize("leg", [{"fraction": 0.5}, {"r": 2.0}, {}])
def test_leg_contribution_is_none_when_fraction_or_r_is_missing(leg):
    assert metrics.leg_contribution_r(leg) is None


# --- _blended_r_raw / r_multiple ---------------------------------------------

def test_blended_raw_is_unrounded_and_r_multiple_rounds_legs_only():
    # Runner at the v39 floor 106.666..: r = 1.3333.., net = 1 + 0.6666.. = 1.6666..
    floor = 100.0 + (2.0 / 3.0) * 10.0
    trade = _trade([TP1_LEG, {"fraction": 0.5, "exit_price": floor,
                              "r": (floor - 100.0) / 5.0, "reason": "tp1_runner_be"}],
                   exit_price=floor)
    assert metrics._blended_r_raw(trade) == pytest.approx(5.0 / 3.0, abs=1e-12)
    assert metrics.r_multiple(trade) == 1.67


def test_single_exit_r_multiple_stays_unrounded():
    trade = _trade(exit_price=ODD_PRICE)
    expected = (ODD_PRICE - 100.0) / 5.0
    assert metrics._blended_r_raw(trade) == expected
    assert metrics.r_multiple(trade) == expected


def test_missing_leg_r_is_derived_from_the_leg_exit_price():
    trade = _trade([{"fraction": 0.5, "exit_price": 110.0},
                    {"fraction": 0.5, "exit_price": 115.0}], exit_price=115.0)
    assert metrics._blended_r_raw(trade) == pytest.approx(2.5)
    assert metrics.r_multiple(trade) == 2.5


def test_bearish_legs_are_signed_in_the_trades_favour():
    trade = _trade([{"fraction": 0.5, "exit_price": 90.0},
                    {"fraction": 0.5, "exit_price": 102.0}],
                   direction="bearish", stop=105.0, exit_price=102.0)
    # (100-90)/5 = +2 on half, (100-102)/5 = -0.4 on half -> 0.8
    assert metrics.r_multiple(trade) == 0.8


@pytest.mark.parametrize("trade", [
    {"direction": "bullish", "entry": None, "stop_loss": 95.0, "exit_price": 110.0},
    {"direction": "bullish", "entry": 100.0, "stop_loss": None, "exit_price": 110.0},
    {"direction": "sideways", "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0},
    {"direction": "bullish", "entry": 100.0, "stop_loss": 100.0, "exit_price": 110.0},
    {"direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "exit_price": None},
    {"direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
     "legs": [{"fraction": 0.5, "r": None, "exit_price": None}]},
])
def test_uncomputable_trades_stay_none(trade):
    assert metrics._blended_r_raw(trade) is None
    assert metrics.r_multiple(trade) is None


# --- banked_contribution_r ---------------------------------------------------

def test_banked_contribution_sums_the_realized_legs():
    assert metrics.banked_contribution_r([TP1_LEG]) == pytest.approx(1.0)
    assert metrics.banked_contribution_r(
        [TP1_LEG, {"fraction": 0.5, "r": 3.0}]) == pytest.approx(2.5)


@pytest.mark.parametrize("legs", [None, [], [TP1_LEG, {"fraction": 0.5}]])
def test_banked_contribution_is_none_without_legs_or_with_a_missing_r(legs):
    assert metrics.banked_contribution_r(legs) is None


# --- open_trade_r ------------------------------------------------------------

def test_open_partial_blends_banked_and_live_runner():
    trade = _trade([TP1_LEG])
    # 1.0 banked + 0.5 x (113 - 100) / 5 = 1.0 + 1.3 = 2.3
    assert metrics.open_trade_r(trade, 113.0) == pytest.approx(2.3)


def test_open_trade_without_legs_is_the_whole_position_live_r():
    assert metrics.open_trade_r(_trade(), 103.0) == pytest.approx(0.6)


def test_open_bearish_partial_is_signed_per_direction():
    trade = _trade([{"fraction": 0.5, "exit_price": 90.0, "r": 2.0}],
                   direction="bearish", stop=105.0)
    # 1.0 + 0.5 x (100 - 97) / 5 = 1.3
    assert metrics.open_trade_r(trade, 97.0) == pytest.approx(1.3)


@pytest.mark.parametrize("quote", [None, math.nan, math.inf])
def test_open_trade_r_is_none_without_a_finite_quote(quote):
    assert metrics.open_trade_r(_trade([TP1_LEG]), quote) is None


def test_open_trade_r_is_none_without_a_risk_basis():
    assert metrics.open_trade_r(_trade([TP1_LEG], stop=100.0), 113.0) is None


def test_open_trade_r_is_none_when_a_banked_leg_has_no_r():
    assert metrics.open_trade_r(_trade([{"fraction": 0.5, "exit_price": 110.0}]), 113.0) is None


# --- performance.closed_r_multiple delegates ---------------------------------

def test_closed_r_multiple_is_metrics_r_multiple_rounded():
    legged = _trade([TP1_LEG, {"fraction": 0.5, "exit_price": 115.0, "r": 3.0}],
                    exit_price=115.0)
    single = _trade(exit_price=ODD_PRICE)
    assert closed_r_multiple(legged) == metrics.r_multiple(legged) == 2.5
    assert closed_r_multiple(single) == round(metrics.r_multiple(single), 2) == 0.27


def test_closed_r_multiple_passes_none_through():
    assert closed_r_multiple(_trade()) is None


def test_closed_r_multiple_no_longer_guesses_a_direction():
    """The old private copy treated any non-bullish direction as bearish;
    the one shared R returns None for a malformed direction (D1)."""
    assert closed_r_multiple(_trade(exit_price=110.0, direction=None)) is None
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_metrics_leg_contribution.py
```

Expected: FAIL with `AttributeError: module 'swingbot.core.analytics.metrics' has no attribute 'leg_contribution_r'` (and the other new names); of the `closed_r_multiple` tests only the direction case fails.

- [ ] **Step 5: Implement the metrics helpers**

In `swingbot/core/analytics/metrics.py`, add `import math` to the imports:

```python
from datetime import datetime
import math

import numpy as np
```

Replace the whole `def r_multiple(trade: dict) -> float | None:` function (today `:173-218`) with:

```python
def leg_contribution_r(leg: dict) -> float | None:
    """One realized leg's share of its trade's R: ``fraction x r``.

    v189 D1: every place that sums legs (the Calendar's leg rows, the banked
    figure on an open PARTIAL) adds contributions, never leg Rs at full
    size -- a +2R TP1 on half the position contributes +1R. None when the
    leg carries no ``fraction`` or no ``r``; a caller that can derive the
    leg's R from its exit price passes it in as ``r``.
    """
    fraction, r = leg.get("fraction"), leg.get("r")
    if fraction is None or r is None:
        return None
    return float(fraction) * float(r)


def _risk_basis(trade: dict) -> tuple[float, float, bool] | None:
    """(entry, risk per share, is_bull), or None for a trade whose R cannot
    be measured: a missing entry or stop, a direction that is not exactly
    ``bullish``/``bearish``, or a zero stop distance."""
    entry, stop = trade.get("entry"), trade.get("stop_loss")
    if entry is None or stop is None:
        return None
    direction = trade.get("direction")
    if direction not in ("bullish", "bearish"):
        return None
    risk = abs(entry - stop)
    if risk == 0:
        return None
    return entry, risk, direction == "bullish"


def _signed_r(price: float, entry: float, risk: float, is_bull: bool) -> float:
    raw = (price - entry) if is_bull else (entry - price)
    return raw / risk


def _legs_raw(legs: list[dict], entry: float, risk: float, is_bull: bool) -> float | None:
    """Fraction-weighted sum of the legs' R, a missing leg ``r`` derived from
    that leg's exit price; None when a leg has neither."""
    total = 0.0
    for leg in legs:
        leg_r = leg.get("r")
        if leg_r is None:
            leg_exit = leg.get("exit_price")
            if leg_exit is None:
                return None
            leg_r = _signed_r(leg_exit, entry, risk, is_bull)
        total += leg.get("fraction", 0) * leg_r
    return total


def _blended_r_raw(trade: dict) -> float | None:
    """`r_multiple`'s value before any rounding.

    v189 D2: `net_outcome` compares this, not the rounded figure, so the
    ±`SCRATCH_EPS_R` band is not quantised by ``round(..., 2)``.
    """
    basis = _risk_basis(trade)
    if basis is None:
        return None
    entry, risk, is_bull = basis
    legs = trade.get("legs")
    if legs:
        return _legs_raw(legs, entry, risk, is_bull)
    exit_price = trade.get("exit_price")
    if exit_price is None:
        return None
    return _signed_r(exit_price, entry, risk, is_bull)


def r_multiple(trade: dict) -> float | None:
    """THE single shared trade-level R-multiple -- every other stat in this
    module and in aggregate.py/calibration.py that needs "how many risk
    units did this trade make or lose" calls this instead of re-deriving
    it, per the Global Constraint "one definition per stat" (v189 D1:
    `performance.closed_r_multiple` delegates here too).

    For a scaled-out trade, blends each leg's fraction-weighted ``r`` (or
    derives a missing leg ``r`` from that leg's exit price), rounded to 2 dp.
    Otherwise r = (exit - entry) / (entry - stop_loss), sign-flipped for a
    bearish trade so a positive r always means "in the trade's favor"
    regardless of direction, unrounded. None when any required price is
    missing, direction is not exactly ``bullish`` or ``bearish``, or when the
    stop distance is exactly 0 (a malformed record -- dividing by zero risk
    is meaningless, not infinite). The unrounded value is `_blended_r_raw`.
    """
    raw = _blended_r_raw(trade)
    if raw is None:
        return None
    return round(raw, 2) if trade.get("legs") else raw


def banked_contribution_r(legs: list[dict] | None) -> float | None:
    """The realized legs' contribution to the trade's R (v189 B3): the sum of
    `leg_contribution_r`. +1.00R for a +2R TP1 on half the position.

    Not ``banked_r`` -- that row field keeps its meaning, the TP1 leg's own
    R. None when there are no legs or any leg lacks ``fraction`` or ``r``.
    """
    if not legs:
        return None
    parts = [leg_contribution_r(leg) for leg in legs]
    if any(part is None for part in parts):
        return None
    return sum(parts)


def open_trade_r(trade: dict, quote: float | None) -> float | None:
    """The blended R of a still-open trade at ``quote`` (v189 B3).

    ``banked_contribution_r(legs)`` plus the open fraction ``1 - Σ fraction``
    times the live move ``(quote - entry) / |entry - stop_loss|``, signed per
    direction. A trade with no legs is the whole position at ``quote``. None
    without a finite quote, without a risk basis, or when a banked leg has
    no ``r``. Unrounded; the display rounds.
    """
    if quote is None or not math.isfinite(quote):
        return None
    basis = _risk_basis(trade)
    if basis is None:
        return None
    entry, risk, is_bull = basis
    legs = trade.get("legs") or []
    banked = banked_contribution_r(legs) if legs else 0.0
    if banked is None:
        return None
    open_fraction = max(0.0, 1.0 - sum(leg.get("fraction", 0) for leg in legs))
    return banked + open_fraction * _signed_r(float(quote), entry, risk, is_bull)
```

- [ ] **Step 6: Delegate `closed_r_multiple`**

In `swingbot/core/tracking/performance.py`, replace the whole `def closed_r_multiple(t: dict) -> float | None:` function (today `:332-379`, complexity 14) with:

```python
def closed_r_multiple(t: dict) -> float | None:
    """Realized R-multiple for a closed trade, rounded to 2 dp.

    v189 D1: a thin delegate to `metrics.r_multiple`, the one trade-level R
    (fraction-weighted across legs, against the ORIGINALLY-planned risk,
    entry -> the plan's starting stop_loss). This used to be a second copy
    of the same blend; the only behaviour difference is that a record whose
    direction is not exactly ``bullish``/``bearish`` now returns None instead
    of being priced as a short.

    Imported lazily: `swingbot.core.analytics`'s package ``__init__`` pulls in
    modules that import this one.
    """
    from swingbot.core.analytics import metrics
    r = metrics.r_multiple(t)
    return None if r is None else round(r, 2)
```

- [ ] **Step 7: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_metrics_leg_contribution.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_metrics_legged_trades.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_metrics_derived.py
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py
```

Expected: all PASS. The last three files pin that `r_multiple` and `closed_r_multiple` results are unchanged for well-formed trades. If an existing test fed `closed_r_multiple` a trade with no `direction`, it now gets None: give that fixture its direction, never re-add the guess.

- [ ] **Step 8: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS. `closed_r_multiple` drops from 14 to 2; `r_multiple` and each new helper are well below 15.

- [ ] **Step 9: Commit**

```bash
cd "$WT" && git add swingbot/core/analytics/metrics.py swingbot/core/tracking/performance.py tests/analytics/test_metrics_leg_contribution.py && git commit -m "feat(metrics): one trade-level R with leg contribution, banked and open-trade R (v189 D1)"
```

### Task V189-2: Net-R labels for scaled-out closes; golden fixture; backtest parity pin

**Model:** sonnet — one pure function plus a data fixture and its tests, fully specified here; no cross-module design.

**Files:**
- Modify: `swingbot/core/analytics/metrics.py` (constants and `net_outcome`, beside V189-1's helpers)
- Create: `tests/analytics/golden_partial_trade.json`
- Create: `tests/analytics/test_net_outcome.py`
- Create: `tests/analytics/test_golden_partial_trade_metrics.py`

**Interfaces:**
- Consumes (V189-1): `metrics._blended_r_raw(trade) -> float | None`, `metrics.r_multiple`, `metrics.banked_contribution_r(legs)`, `metrics.open_trade_r(trade, quote)`.
- Produces:
  - `metrics.SCRATCH_EPS_R: float = 0.01`
  - `metrics.LABEL_BASIS_SINCE: str | None = None` (V189-26 sets the date)
  - `metrics.net_outcome(trade: dict) -> tuple[str, str | None]` — for closes with two or more realized legs: `("win", None)` when the unrounded net R is `> +0.01`, `("loss", None)` when `< -0.01`, `("closed", "scratch")` inside the band (edges exclusive, so exactly ±0.01 is scratch), `("closed", "unscored")` plus a WARNING naming `trade.get("id") or trade.get("plan_id")` when the net is None or not finite. Used by V189-10 (`_plan_outcome`), V189-11 (manual close), V189-20 (`label_counts`).
  - `tests/analytics/golden_partial_trade.json` — the index § Contracts shape, with `calendar_day.trade_count = 3` and `calendar_day.win_rate = 66.66666666666667` (see this part's header note). Read by V189-4, V189-10, V189-11, V189-18, V189-19, V189-21, V189-22.
  - Test helpers in `tests/analytics/test_golden_partial_trade_metrics.py`, importable by later tests: `FIXTURE_PATH`, `load_golden() -> dict`, `closed_case(name) -> dict`, `open_case(name) -> dict`, `golden_closed_trade(case, *, closed_at=None, trade_id="golden-1", runner_reason="manual") -> dict`, `golden_open_trade(*, trade_id="golden-open") -> dict`.

- [ ] **Step 1: Write the golden fixture**

Create `tests/analytics/golden_partial_trade.json` with exactly this content (it is the index's contract; only `calendar_day.trade_count` and `calendar_day.win_rate` differ, verified in Step 2):

```json
{
  "trade": {"ticker": "GOLD", "direction": "bullish", "shares": 100, "tp1_fraction": 0.5,
            "entry": 100.0, "stop_loss": 95.0, "tp1": 110.0, "tp2": 120.0, "risk_per_share": 5.0,
            "tp1_leg": {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}},
  "tolerance": 0.005,
  "closed_cases": [
    {"name": "floor",  "runner_exit": 106.66666666666667, "runner_r": 1.3333, "net_r": 1.6667, "realized_pnl_amount": 833.33, "pnl_pct": 8.33,  "status": "win",  "close_reason": null},
    {"name": "gap",    "runner_exit": 88.0,  "runner_r": -2.4, "net_r": -0.2, "realized_pnl_amount": -100.0, "pnl_pct": -1.0, "status": "loss", "close_reason": null, "backtest_label": "win"},
    {"name": "time_exit", "runner_exit": 112.0, "runner_r": 2.4, "net_r": 2.2, "realized_pnl_amount": 1100.0, "pnl_pct": 11.0, "status": "win", "close_reason": null},
    {"name": "manual", "runner_exit": 115.0, "runner_r": 3.0, "net_r": 2.5, "realized_pnl_amount": 1250.0, "pnl_pct": 12.5, "status": "win", "close_reason": null}
  ],
  "open_cases": [
    {"name": "quote_113", "quote": 113.0, "shares": 50, "entry_shares": 100, "r_multiple": 2.3, "banked_r": 2.0,
     "banked_contribution_r": 1.0, "banked_amount": 500.0, "unrealized_pnl_amount": 650.0,
     "working_stop": 106.66666666666667, "risk_of_loss_amount": 0.0, "open_profit_to_stop": 316.67},
    {"name": "no_quote", "quote": null, "shares": 50, "entry_shares": 100, "r_multiple": null, "banked_r": 2.0,
     "banked_contribution_r": 1.0, "banked_amount": 500.0, "unrealized_pnl_amount": null,
     "working_stop": 106.66666666666667, "risk_of_loss_amount": 0.0, "open_profit_to_stop": null}
  ],
  "missing_leg_r_case": {"legs": [{"fraction": 0.5, "exit_price": 110.0}, {"fraction": 0.5, "exit_price": 115.0}], "net_r": 2.5},
  "calendar_day": {"golden_case": "manual",
                   "other_trade": {"ticker": "LOSS", "direction": "bullish", "shares": 100, "entry": 50.0, "stop_loss": 48.0, "exit_price": 48.0, "status": "loss"},
                   "net_r": 1.5, "net_pnl_amount": 1050.0, "trade_count": 3, "win_rate": 66.66666666666667},
  "label_table": [
    {"net_r": 0.02, "status": "win", "close_reason": null},
    {"net_r": 0.005, "status": "closed", "close_reason": "scratch"},
    {"net_r": 0.0, "status": "closed", "close_reason": "scratch"},
    {"net_r": -0.005, "status": "closed", "close_reason": "scratch"},
    {"net_r": -0.02, "status": "loss", "close_reason": null}
  ]
}
```

- [ ] **Step 2: Verify the two calendar keys against today's day semantics (stop-and-ask gate)**

The index requires `calendar_day.trade_count` and `win_rate` to be checked against `pnl_calendar` before the file is committed. Run, in the worktree, against the code as it is now (before V189-4):

```bash
cd "$WT" && python - <<'PYEOF'
from swingbot.core.analytics import pnl_calendar as pc
day = "2026-08-03T20:00:00+00:00"
leg = lambda f, x, r, why: {"fraction": f, "exit_price": x, "r": r, "reason": why, "closed_at": day}
gold = {"id": "g", "ticker": "GOLD", "strategy": "S/R Confluence", "direction": "bullish",
        "shares": 100, "entry": 100.0, "stop_loss": 95.0, "exit_price": 115.0, "status": "win",
        "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": day, "realized_pnl_amount": 1250.0,
        "legs": [leg(0.5, 110.0, 2.0, "tp1"), leg(0.5, 115.0, 3.0, "manual")],
        "target_sources": [], "stop_sources": []}
loss = {"id": "l", "ticker": "LOSS", "strategy": "S/R Confluence", "direction": "bullish",
        "shares": 100, "entry": 50.0, "stop_loss": 48.0, "exit_price": 48.0, "status": "loss",
        "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": day, "realized_pnl_amount": -200.0,
        "target_sources": [], "stop_sources": []}
rows = pc.joined_rows([gold, loss], [])
print(pc.day_summary("2026-08-03", rows))
PYEOF
```

Expected: `'trade_count': 3` and `'win_rate': 66.66666666666667` (and, before V189-4, `'net_r': 4.0`, `'net_pnl_amount': 1050.0`). If `trade_count` or `win_rate` print anything else, **stop and ask** the controller (index § Golden fixture) — do not edit the fixture to match.

- [ ] **Step 3: Write the failing tests**

Create `tests/analytics/test_net_outcome.py`:

```python
"""v189 D2: a close with two or more realized legs is labelled by the sign
of its UNROUNDED net R, with a ±SCRATCH_EPS_R scratch band (edges
exclusive) and `closed`/`unscored` when the net cannot be trusted."""
import logging
import math

import pytest

from swingbot.core.analytics import metrics
from tests.analytics.test_golden_partial_trade_metrics import load_golden


def _two_leg(net_r, *, trade_id="t-1"):
    """Golden geometry; TP1 +2R on half, runner r chosen so the blend is net_r."""
    runner_r = 2.0 * net_r - 2.0
    return {"id": trade_id, "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                     {"fraction": 0.5, "exit_price": 100.0 + 5.0 * runner_r,
                      "r": runner_r, "reason": "tp1_runner_be"}]}


def test_constants():
    assert metrics.SCRATCH_EPS_R == 0.01
    assert metrics.LABEL_BASIS_SINCE is None


@pytest.mark.parametrize("row", load_golden()["label_table"], ids=lambda r: str(r["net_r"]))
def test_label_table(row):
    assert metrics.net_outcome(_two_leg(row["net_r"])) == (row["status"], row["close_reason"])


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_band_edges_are_exclusive(sign):
    # 0.5 x 0.01 + 0.5 x 0.01 is exactly float(0.01): the edge itself.
    edge = sign * metrics.SCRATCH_EPS_R
    trade = {"id": "edge", "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
             "legs": [{"fraction": 0.5, "r": edge}, {"fraction": 0.5, "r": edge}]}
    assert metrics._blended_r_raw(trade) == edge
    assert metrics.net_outcome(trade) == ("closed", "scratch")


def test_threshold_uses_the_unrounded_blend():
    """+0.012 rounds to 0.01 (the edge, scratch) but is above the band: win.
    -0.012 likewise: loss."""
    assert metrics.r_multiple(_two_leg(0.012)) == 0.01
    assert metrics.net_outcome(_two_leg(0.012)) == ("win", None)
    assert metrics.net_outcome(_two_leg(-0.012)) == ("loss", None)


def test_missing_risk_basis_is_unscored_with_a_warning(caplog):
    trade = _two_leg(1.0, trade_id="no-stop")
    trade["stop_loss"] = None
    with caplog.at_level(logging.WARNING, logger="swingbot.core.analytics.metrics"):
        assert metrics.net_outcome(trade) == ("closed", "unscored")
    assert "no-stop" in caplog.text


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_leg_r_is_unscored_never_a_scratch(bad, caplog):
    trade = _two_leg(1.0, trade_id="nan-leg")
    trade["legs"][1]["r"] = bad
    with caplog.at_level(logging.WARNING, logger="swingbot.core.analytics.metrics"):
        assert metrics.net_outcome(trade) == ("closed", "unscored")
    assert "nan-leg" in caplog.text


def test_non_finite_exit_price_on_a_leg_without_r_is_unscored():
    trade = _two_leg(1.0)
    trade["legs"][1] = {"fraction": 0.5, "exit_price": math.nan, "reason": "manual"}
    assert metrics.net_outcome(trade) == ("closed", "unscored")


def test_warning_names_the_plan_id_when_the_trade_has_no_id(caplog):
    trade = _two_leg(1.0)
    trade.pop("id")
    trade["plan_id"] = "plan-77"
    trade["direction"] = None
    with caplog.at_level(logging.WARNING, logger="swingbot.core.analytics.metrics"):
        assert metrics.net_outcome(trade) == ("closed", "unscored")
    assert "plan-77" in caplog.text


def test_never_falls_back_to_the_tp1_touch_rule():
    """A runner reason starting `tp1_` used to mean `win` whatever the net."""
    trade = _two_leg(-0.2)
    assert trade["legs"][1]["reason"].startswith("tp1_")
    assert metrics.net_outcome(trade) == ("loss", None)
```

Create `tests/analytics/test_golden_partial_trade_metrics.py`:

```python
"""v189 golden partial trade, metrics side (spec § Testing).

`golden_partial_trade.json` is the one fixture backend and frontend tests
share; every number in it is hand-computed (1R = $5/share, each leg 50
shares, TP1 +2R on 50% = +1.0R and $500). The helpers below are imported
by later v189 tests (calendar, plan manager, manual close, trades rows).
"""
import json
from pathlib import Path

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.tracking.equity import open_shares, unrealized_pnl_amount
from swingbot.core.tracking.performance import closed_pnl_pct, settle_legs
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_v2_walk import ENTRY, FREE, TP1_BAR, _plan

FIXTURE_PATH = Path(__file__).with_name("golden_partial_trade.json")


def load_golden() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def closed_case(name: str) -> dict:
    return next(c for c in load_golden()["closed_cases"] if c["name"] == name)


def open_case(name: str) -> dict:
    return next(c for c in load_golden()["open_cases"] if c["name"] == name)


def _base(trade_id: str) -> dict:
    g = load_golden()["trade"]
    return {"id": trade_id, "ticker": g["ticker"], "direction": g["direction"],
            "shares": g["shares"], "entry": g["entry"], "stop_loss": g["stop_loss"],
            "take_profit": g["tp1"], "target2": g["tp2"], "tp1_fraction": g["tp1_fraction"],
            "strategy": "S/R Confluence", "target_sources": [], "stop_sources": [],
            "opened_at": "2026-08-01T14:00:00+00:00"}


def golden_closed_trade(case: dict, *, closed_at: str | None = None,
                        trade_id: str = "golden-1", runner_reason: str = "manual") -> dict:
    """The golden trade closed through `case`'s runner exit, legs written the
    way the live engine writes them (each leg with its own r)."""
    g = load_golden()["trade"]
    runner_r = (case["runner_exit"] - g["entry"]) / g["risk_per_share"]
    legs = [dict(g["tp1_leg"]),
            {"fraction": 1.0 - g["tp1_fraction"], "exit_price": case["runner_exit"],
             "r": runner_r, "reason": runner_reason}]
    if closed_at is not None:
        for leg in legs:
            leg["closed_at"] = closed_at
    trade = {**_base(trade_id), "exit_price": case["runner_exit"], "legs": legs,
             "status": case["status"], "close_reason": case["close_reason"],
             "closed_at": closed_at}
    trade["realized_pnl_amount"] = settle_legs(trade)
    return trade


def golden_open_trade(*, trade_id: str = "golden-open") -> dict:
    """The golden trade with TP1 banked and the runner still open."""
    g = load_golden()["trade"]
    return {**_base(trade_id), "exit_price": None, "legs": [dict(g["tp1_leg"])],
            "status": "open", "closed_at": None, "realized_pnl_amount": None}


TOL = load_golden()["tolerance"]
CLOSED = [c["name"] for c in load_golden()["closed_cases"]]
OPEN = [c["name"] for c in load_golden()["open_cases"]]


@pytest.mark.parametrize("name", CLOSED)
def test_closed_case_r_figures(name):
    case = closed_case(name)
    trade = golden_closed_trade(case)
    assert trade["legs"][1]["r"] == pytest.approx(case["runner_r"], abs=TOL)
    assert metrics._blended_r_raw(trade) == pytest.approx(case["net_r"], abs=TOL)
    assert metrics.r_multiple(trade) == pytest.approx(case["net_r"], abs=TOL)


@pytest.mark.parametrize("name", CLOSED)
def test_closed_case_dollars_and_pct_on_whole_position_notional(name):
    case = closed_case(name)
    trade = golden_closed_trade(case)
    assert trade["realized_pnl_amount"] == pytest.approx(case["realized_pnl_amount"], abs=0.01)
    # pnl_pct basis: realized dollars over 100 x 100 = $10,000 (closed_pnl_pct).
    assert closed_pnl_pct(trade) == pytest.approx(case["pnl_pct"], abs=TOL)


@pytest.mark.parametrize("name", CLOSED)
def test_closed_case_label(name):
    case = closed_case(name)
    assert metrics.net_outcome(golden_closed_trade(case)) == (case["status"], case["close_reason"])


def test_floor_case_is_the_v39_runner_floor():
    g = load_golden()["trade"]
    assert closed_case("floor")["runner_exit"] == pytest.approx(runner_floor(g["entry"], g["tp1"]))


def test_missing_leg_r_case_derives_r_from_exit_prices():
    golden = load_golden()
    trade = {**_base("missing-r"), "legs": golden["missing_leg_r_case"]["legs"]}
    assert metrics.r_multiple(trade) == pytest.approx(golden["missing_leg_r_case"]["net_r"])


@pytest.mark.parametrize("name", OPEN)
def test_open_case_metrics(name):
    case = open_case(name)
    trade = golden_open_trade()
    g = load_golden()["trade"]
    assert trade["legs"][0]["r"] == case["banked_r"]
    assert metrics.banked_contribution_r(trade["legs"]) == pytest.approx(case["banked_contribution_r"])
    assert settle_legs(trade) == pytest.approx(case["banked_amount"])
    assert open_shares(trade["shares"], trade["legs"]) == case["shares"]
    assert trade["shares"] == case["entry_shares"]
    assert case["working_stop"] == pytest.approx(runner_floor(g["entry"], g["tp1"]))
    blended = metrics.open_trade_r(trade, case["quote"])
    if case["r_multiple"] is None:
        assert blended is None
    else:
        assert blended == pytest.approx(case["r_multiple"], abs=TOL)


def test_open_quote_case_unrealized_and_profit_to_stop():
    case = open_case("quote_113")
    trade = golden_open_trade()
    held = open_shares(trade["shares"], trade["legs"])
    assert unrealized_pnl_amount(trade["entry"], trade["direction"], held, case["quote"]) == \
        pytest.approx(case["unrealized_pnl_amount"])
    # Open profit to stop: 50 x (113 - 106.67) = 316.67; risk of loss: the
    # working stop is above entry, so nothing below entry can be lost.
    assert held * (case["quote"] - case["working_stop"]) == \
        pytest.approx(case["open_profit_to_stop"], abs=0.01)
    assert max(0.0, trade["entry"] - case["working_stop"]) * held == case["risk_of_loss_amount"]


# --- the parity pin: live and backtest label the gap case differently --------

@pytest.fixture
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def test_backtest_still_labels_the_gap_case_win(_pinned):
    """D2 is live-only (spec D2, last bullet). exit_sim_v2 labels a scaled-out
    trade by the TP1 event, so the runner gapping to an open of 88 is a `win`
    there while the live label is `loss`. If this fails, the closed
    acceptance gates have moved: stop, do not edit exit_sim_v2."""
    case = closed_case("gap")
    gap_bar = (case["runner_exit"], case["runner_exit"] + 1.0,
               case["runner_exit"] - 1.0, case["runner_exit"])
    df = make_ohlcv([ENTRY, TP1_BAR, gap_bar])
    res = walk_v2(df, 0, 100.0, _plan(tp1_fraction=0.5), 10, FREE, scale_out=True)
    assert res.legs[1]["exit_price"] == case["runner_exit"]
    assert res.r_total == pytest.approx(case["net_r"], abs=TOL)
    assert res.outcome == case["backtest_label"] == "win"
    assert metrics.net_outcome(golden_closed_trade(case)) == ("loss", None)
```

- [ ] **Step 4: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_net_outcome.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_golden_partial_trade_metrics.py
```

Expected: FAIL with `AttributeError: ... has no attribute 'net_outcome'` / `'SCRATCH_EPS_R'`. In the golden file the r, dollar, open-case and parity tests already pass (they read V189-1's helpers); only `test_closed_case_label` and the last line of the parity test fail.

- [ ] **Step 5: Implement `net_outcome`**

In `swingbot/core/analytics/metrics.py`, add `import logging` to the imports and a module logger under them:

```python
from datetime import datetime
import logging
import math

import numpy as np

log = logging.getLogger(__name__)
```

Below `EXIT_REASONS`/`_EXIT_REASON_ALIASES` (module constants block), add:

```python
#: v189 D2: the live scratch band for a close with two or more realized
#: legs. Net R strictly inside ±SCRATCH_EPS_R is `closed`/`scratch`. Live
#: only -- exit_sim_v2 keeps its own event labels (the metric-definitions
#: spec owns reconciling them).
SCRATCH_EPS_R: float = 0.01

#: v189 D6: the date (ISO, UTC) from which scaled-out closes are labelled by
#: net R; earlier ones were labelled by the TP1 touch and were not
#: backfilled. Set by the release task; None until deployed.
LABEL_BASIS_SINCE: str | None = None
```

After `open_trade_r`, add:

```python
def net_outcome(trade: dict) -> tuple[str, str | None]:
    """(status, close_reason) for a close with two or more realized legs
    (v189 D2): the sign of the UNROUNDED blended net R (`_blended_r_raw`).

    ``> +SCRATCH_EPS_R`` is ``("win", None)``, ``< -SCRATCH_EPS_R`` is
    ``("loss", None)``, anything inside the band (edges included) is
    ``("closed", "scratch")``. A net that cannot be computed (no risk basis,
    a leg with neither r nor exit price) or is not finite (a NaN/inf leg r
    or exit price) is ``("closed", "unscored")`` with a warning naming the
    trade -- never a fallback to the old "TP1 touched means win" rule, and
    never a silent scratch. Single-leg closes do not come here: they keep
    their existing labels.
    """
    raw = _blended_r_raw(trade)
    if raw is None or not math.isfinite(raw):
        log.warning("net_outcome: trade %s has no computable net R; labelled closed/unscored",
                    trade.get("id") or trade.get("plan_id"))
        return "closed", "unscored"
    if raw > SCRATCH_EPS_R:
        return "win", None
    if raw < -SCRATCH_EPS_R:
        return "loss", None
    return "closed", "scratch"
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_net_outcome.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_golden_partial_trade_metrics.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_metrics_leg_contribution.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
```

Expected: all PASS. `test_override_verdict.py` hashes `exit_sim.py`/`exit_sim_v2.py`/`lifecycle.py`; it passing proves none of them was touched.

- [ ] **Step 7: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS (`net_outcome` is 5).

- [ ] **Step 8: Commit**

```bash
cd "$WT" && git add swingbot/core/analytics/metrics.py tests/analytics/golden_partial_trade.json tests/analytics/test_net_outcome.py tests/analytics/test_golden_partial_trade_metrics.py && git commit -m "feat(metrics): net-R labels for scaled-out closes, golden partial-trade fixture, backtest parity pin (v189 D2)"
```

### Task V189-3: Retrospective uses metrics.r_multiple; delete its private copy

**Model:** sonnet — a mechanical swap of one private function for the shared one at five call sites, with a behaviour test.

**Files:**
- Modify: `swingbot/core/tracking/retrospective.py` (delete `_r_multiple`, today `:188-198`; call sites today `:329, 524, 620, 972, 983, 984`)
- Create: `tests/tracking/test_retrospective_legged_r.py`

**Interfaces:**
- Consumes (V189-1): `metrics.r_multiple(trade) -> float | None`. Consumes (V189-2): `tests.analytics.test_golden_partial_trade_metrics.closed_case`, `golden_closed_trade`.
- Produces: `retrospective._r_multiple` no longer exists; the daily recap's R for a scaled-out trade is the fraction-weighted blend.

- [ ] **Step 1: Write the failing test**

Create `tests/tracking/test_retrospective_legged_r.py`:

```python
"""v189 D1: the daily recap's R is `metrics.r_multiple`, so a scaled-out
trade counts its TP1 leg instead of pricing only the runner's exit."""
import datetime as dt

from swingbot.core.presentation import tokens
from swingbot.core.tracking import retrospective as retro
from tests.analytics.test_golden_partial_trade_metrics import closed_case, golden_closed_trade

MONDAY = dt.date(2026, 10, 19)                 # a weekday: no Sunday-only parts
CLOSED_AT = "2026-10-19T18:00:00+00:00"        # 20:00 Berlin, same day


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))
    monkeypatch.setattr(retro, "_berlin_today", lambda: MONDAY)


def _avg_r_line(messages) -> str:
    text = "\n".join(messages)
    return next(line for line in text.splitlines() if line.startswith("**Avg R-multiple:**"))


def test_the_private_copy_is_gone():
    assert not hasattr(retro, "_r_multiple")


def test_scaled_out_trade_is_blended_not_runner_only(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    trade = golden_closed_trade(closed_case("manual"), closed_at=CLOSED_AT)
    # TP1 +2R on half + runner +3R on half = 2.5R. The runner-only figure was 3.0R.
    messages = retro.build_daily_retrospective([trade], today=MONDAY)
    assert _avg_r_line(messages) == f"**Avg R-multiple:** {tokens.fmt_r(2.5)}"


def test_gap_loss_is_the_small_net_not_the_runner_gap(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    trade = golden_closed_trade(closed_case("gap"), closed_at=CLOSED_AT)
    # Net -0.2R; pricing the runner's 88 exit alone read -2.4R.
    messages = retro.build_daily_retrospective([trade], today=MONDAY)
    assert _avg_r_line(messages) == f"**Avg R-multiple:** {tokens.fmt_r(-0.2)}"


def test_single_exit_trade_is_unchanged(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    trade = {"id": "single", "ticker": "LOSS", "direction": "bullish", "status": "loss",
             "entry": 100.0, "stop_loss": 95.0, "exit_price": 96.5, "shares": 10,
             "opened_at": "2026-10-16T14:00:00+00:00", "closed_at": CLOSED_AT,
             "realized_pnl_amount": -35.0, "strategy": "S/R Confluence",
             "target_sources": [], "stop_sources": []}
    messages = retro.build_daily_retrospective([trade], today=MONDAY)
    assert _avg_r_line(messages) == f"**Avg R-multiple:** {tokens.fmt_r(-0.7)}"
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_retrospective_legged_r.py
```

Expected: FAIL — `test_the_private_copy_is_gone` (the attribute exists), `test_scaled_out_trade_is_blended_not_runner_only` (prints `3.0R`), `test_gap_loss_is_the_small_net_not_the_runner_gap` (prints the −2.4R form). `test_single_exit_trade_is_unchanged` already PASSES and must keep passing.

- [ ] **Step 3: Swap the private copy for the shared R**

In `swingbot/core/tracking/retrospective.py`:

1. Add the import beside the existing analytics import (`from swingbot.core.analytics import calibration`, today `:29`):

```python
from swingbot.core.analytics import calibration
from swingbot.core.analytics import metrics
```

2. Delete the whole `def _r_multiple(trade: dict) -> float | None:` function (today `:188-198`).

3. Replace every remaining `_r_multiple(t)` call with `metrics.r_multiple(t)` — exactly these six expressions:

```python
        r_multiples = [r for t in all_trades if (r := metrics.r_multiple(t)) is not None]   # was :329
    r_mults   = [r for t in closed_today if (r := metrics.r_multiple(t)) is not None]        # was :524
                r    = metrics.r_multiple(t)                                                # was :620
    r_mults = [r for t in losses if (r := metrics.r_multiple(t)) is not None]                # was :972
    win_rs = [r for t in wins if (r := metrics.r_multiple(t)) is not None]                   # was :983
    loss_rs = [r for t in losses if (r := metrics.r_multiple(t)) is not None]                # was :984
```

Keep each line's existing indentation; the trailing `# was` comments above are for orientation only and are not written into the file. Then confirm nothing else referenced it:

```bash
cd "$WT" && git grep -n "_r_multiple" -- swingbot/core/tracking/retrospective.py
```

Expected: no line containing a bare `_r_multiple(` (only `metrics.r_multiple(` and the unrelated `r_multiples` list name).

The single-exit R is now unrounded where it used to be rounded to 2 dp; every consumer rounds or formats it afterwards (`round(..., 2)` on averages, `tokens.fmt_r` on the closed-today row, `ruin.simulate` takes floats), so no rendered figure changes for a single-exit trade.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_retrospective_legged_r.py
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_retrospective_v2.py
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_retrospective_live_loss.py
```

Expected: all PASS.

- [ ] **Step 5: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS. `build_daily_retrospective` (106), `_analyse` (72) and `_collect_weekly_risk_stats` (21) are baselined; swapping a call adds no branch, so none grows.

- [ ] **Step 6: Commit**

```bash
cd "$WT" && git add swingbot/core/tracking/retrospective.py tests/tracking/test_retrospective_legged_r.py && git commit -m "fix(retrospective): daily recap R uses metrics.r_multiple, private copy deleted (v189 D1)"
```

# Phase 2 — The Calendar adds contributions

### Task V189-4: Calendar sums leg contributions

**Model:** opus — changes a shared leg-expansion helper read by the Dashboard, equity and the Calendar, and the R every calendar sum adds; the blast radius needs judgement.

**Files:**
- Modify: `swingbot/core/tracking/performance.py` (`expand_trade_legs`, today `:400-469`; `expand_realized_legs` docstring, today `:484-500`)
- Modify: `swingbot/core/analytics/pnl_calendar.py` (`_row_for`, today `:169-216`; new `_part_r` beside it)
- Modify: `tests/analytics/test_pnl_calendar.py` (three leg-R assertions, today `:338, :344, :362`)
- Modify: `tests/admin/test_api_v1_calendar.py` (two leg-R assertions, today `:309, :389`)
- Create: `tests/analytics/test_pnl_calendar_contributions.py`

**Interfaces:**
- Consumes (V189-1): `metrics.leg_contribution_r(leg) -> float | None`, `metrics.r_multiple`. Consumes (V189-2): `golden_partial_trade.json` (`calendar_day`, `missing_leg_r_case`, `tolerance`) and the helpers `load_golden`, `closed_case`, `golden_closed_trade` from `tests/analytics/test_golden_partial_trade_metrics.py`.
- Produces: every leg part from `performance.expand_trade_legs` (and so `expand_realized_legs`) carries `fraction` (the leg's share of the original position; the open remainder's share on the remainder row) and `leg_r` (the leg's stored `r`, None on the remainder). A trade with no legs still comes back as `[trade]`, unchanged, with neither key. Calendar rows' `r_multiple` for a leg row is `fraction × r`; day, month, weekday, breakdown, ticker and streak sums therefore add contributions. Dollar figures, counts and outcomes are unchanged.

- [ ] **Step 1: Write the failing tests**

Create `tests/analytics/test_pnl_calendar_contributions.py`:

```python
"""v189 B2: the Calendar adds each leg's CONTRIBUTION (fraction x r), never
the leg's R at full size. With the golden trade, TP1 (+2R on 50%) plus a
runner (+3R on 50%) is +2.5R, not +5R. A whole single-exit trade, dollars,
counts and outcomes are unchanged. Every expected value is hand-computed."""
import pytest

from swingbot.core.analytics.pnl_calendar import day_summary, day_totals, joined_rows
from swingbot.core.tracking.performance import expand_realized_legs, expand_trade_legs
from tests.analytics.test_golden_partial_trade_metrics import (closed_case, golden_closed_trade,
                                                               load_golden)

DAY = "2026-08-03"
CLOSED_AT = "2026-08-03T20:00:00+00:00"
TOL = load_golden()["tolerance"]


def _other_trade() -> dict:
    """The fixture's -1R single-exit loss: 100 sh, entry 50, stop 48, out at 48."""
    other = load_golden()["calendar_day"]["other_trade"]
    return {**other, "id": "loss-1", "strategy": "S/R Confluence",
            "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": CLOSED_AT,
            "realized_pnl_amount": round(other["shares"] * (other["exit_price"] - other["entry"]), 2),
            "target_sources": [], "stop_sources": []}


def _golden_day_rows() -> list[dict]:
    day = load_golden()["calendar_day"]
    gold = golden_closed_trade(closed_case(day["golden_case"]), closed_at=CLOSED_AT)
    return joined_rows([gold, _other_trade()], [])


# --- leg parts carry their weight ---------------------------------------------

def test_leg_parts_carry_fraction_and_leg_r():
    gold = golden_closed_trade(closed_case("manual"), closed_at=CLOSED_AT)
    parts = expand_trade_legs(gold)
    assert [(p["fraction"], p["leg_r"]) for p in parts] == [(0.5, 2.0), (0.5, 3.0)]


def test_the_open_remainder_part_carries_its_fraction_and_no_r():
    trade = {"status": "open", "shares": 100, "entry": 100.0, "direction": "bullish",
             "stop_loss": 95.0, "exit_price": None,
             "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}]}
    remainder = expand_trade_legs(trade)[-1]
    assert (remainder["status"], remainder["fraction"], remainder["leg_r"]) == ("open", 0.5, None)


def test_a_trade_without_legs_comes_back_unchanged():
    trade = _other_trade()
    assert expand_trade_legs(trade) == [trade]
    assert "fraction" not in expand_realized_legs(trade)[0]


# --- the golden day -------------------------------------------------------------

def test_golden_day_rows_carry_contributions():
    rows = _golden_day_rows()
    # TP1 0.5 x 2.0 = 1.0; runner 0.5 x 3.0 = 1.5; the loss (48-50)/2 = -1.0 whole.
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, 1.5, -1.0])
    assert [r["outcome"] for r in rows] == ["win", "win", "loss"]
    # Dollars per row: 50 x 10 = 500, the closing leg carries 1250 - 500 = 750, -200.
    assert [r["pnl_amount"] for r in rows] == [500.0, 750.0, -200.0]


def test_golden_day_summary_matches_the_fixture():
    expected = load_golden()["calendar_day"]
    summary = day_summary(DAY, _golden_day_rows())
    assert summary["net_r"] == pytest.approx(expected["net_r"], abs=TOL)
    assert summary["net_pnl_amount"] == pytest.approx(expected["net_pnl_amount"])
    assert summary["trade_count"] == expected["trade_count"]
    assert summary["win_rate"] == pytest.approx(expected["win_rate"], abs=TOL)


def test_golden_day_totals_add_contributions():
    totals = day_totals(_golden_day_rows())
    assert totals["total_r"] == pytest.approx(1.5)
    assert (totals["winners"], totals["losers"]) == (2, 1)
    assert totals["total_ccy"] == pytest.approx(1050.0)


# --- edges ----------------------------------------------------------------------

def test_a_leg_without_r_contributes_its_derived_r_times_its_fraction():
    golden = load_golden()
    gold = golden_closed_trade(closed_case("manual"), closed_at=CLOSED_AT)
    gold["legs"] = [{**leg, "closed_at": CLOSED_AT}
                    for leg in golden["missing_leg_r_case"]["legs"]]
    rows = joined_rows([gold], [])
    # 0.5 x (110-100)/5 = 1.0 and 0.5 x (115-100)/5 = 1.5; together the fixture's 2.5.
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, 1.5])
    assert day_summary(DAY, rows)["net_r"] == pytest.approx(golden["missing_leg_r_case"]["net_r"])


def test_a_bearish_leg_contribution_keeps_its_sign():
    trade = {"id": "short-1", "ticker": "SHRT", "strategy": "S/R Confluence",
             "direction": "bearish", "status": "loss", "shares": 10, "entry": 100.0,
             "stop_loss": 105.0, "exit_price": 103.0, "realized_pnl_amount": 35.0,
             "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": CLOSED_AT,
             "target_sources": [], "stop_sources": [],
             "legs": [{"fraction": 0.5, "exit_price": 90.0, "closed_at": CLOSED_AT},
                      {"fraction": 0.5, "exit_price": 103.0, "closed_at": CLOSED_AT}]}
    rows = joined_rows([trade], [])
    # 0.5 x (100-90)/5 = +1.0 ; 0.5 x (100-103)/5 = -0.3
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, -0.3])


def test_a_banked_leg_of_an_open_runner_counts_its_contribution():
    trade = {"id": "open-1", "ticker": "GOLD", "strategy": "S/R Confluence",
             "direction": "bullish", "status": "open", "shares": 100, "entry": 100.0,
             "stop_loss": 95.0, "exit_price": None, "realized_pnl_amount": None,
             "opened_at": "2026-08-01T14:00:00+00:00", "closed_at": None,
             "target_sources": [], "stop_sources": [],
             "legs": [{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1",
                       "closed_at": CLOSED_AT}]}
    rows = joined_rows([trade], [])
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0])
    assert rows[0]["pnl_amount"] == 500.0


def test_a_whole_trade_still_prefers_the_journal_r():
    entry = {"trade_id": "loss-1", "outcome": "loss", "r_realized": -0.9}
    rows = joined_rows([_other_trade()], [entry])
    assert [r["r_multiple"] for r in rows] == [-0.9]


def test_a_whole_trade_without_a_journal_entry_is_its_own_r():
    rows = joined_rows([_other_trade()], [])
    assert [r["r_multiple"] for r in rows] == pytest.approx([-1.0])
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar_contributions.py
```

Expected: FAIL — `KeyError: 'fraction'` in the two part tests, leg rows read `[2.0, 3.0, -1.0]`, the day reads `net_r` 4.0. The three whole-trade tests and the dollars/outcomes assertions already hold.

- [ ] **Step 3: Leg parts carry `fraction` and `leg_r`**

In `swingbot/core/tracking/performance.py`, `expand_trade_legs`: in the per-leg `rows.append({...})`, add the two keys after `"stop_loss": stop_loss,`:

```python
        rows.append({
            **trade,
            "legs": None,
            "shares": leg_shares,
            "exit_price": leg.get("exit_price"),
            "closed_at": leg.get("closed_at") or trade.get("closed_at"),
            "status": _leg_status(leg, entry, direction),
            "entry": entry,
            "direction": direction,
            "stop_loss": stop_loss,
            # v189 B2: the leg's share of the original position and its own
            # stored R, so a sum can add its contribution (fraction x r).
            "fraction": leg.get("fraction"),
            "leg_r": leg.get("r"),
        })
```

and in the open-remainder `rows.append({...})`:

```python
        rows.append({
            **trade,
            "legs": None,
            "shares": (
                round(shares * remaining_fraction, 4) if shares is not None else None
            ),
            "exit_price": None,
            "status": "open",
            "fraction": remaining_fraction,
            "leg_r": None,
        })
```

In the `expand_trade_legs` docstring, after the paragraph that starts `Each returned row carries no `legs` key of its own`, add:

```python
    v189 B2: each leg row also carries `fraction` (that leg's share of the
    original position; the remainder's share on the open row) and `leg_r`
    (the leg's stored `r`, None when it has none or on the open row), so
    anything that sums leg rows can weight them with
    `metrics.leg_contribution_r`. A trade with no legs gains neither key.
```

In the `expand_realized_legs` docstring, replace the last sentence `This is how the Dashboard's chips and the P&L calendar count a partial: as an individual trade, on the day it banked, with its own outcome and its own R (`metrics.r_multiple` on a row prices the leg's own exit).` with:

```python
    This is how the Dashboard's chips and the P&L calendar count a partial:
    as an individual trade, on the day it banked, with its own outcome. Its R
    on the calendar is its contribution (`fraction x r`, v189 B2), not the
    leg's R at full size.
```

- [ ] **Step 4: The calendar row's R is the contribution**

In `swingbot/core/analytics/pnl_calendar.py`, add `_part_r` immediately above `_row_for`:

```python
def _part_r(part: dict, entry: dict) -> float | None:
    """The R a calendar row adds to its day.

    A whole trade (one part) keeps today's rule: the journal's r_realized
    when present (computed by the same `metrics.r_multiple` at close), else
    `metrics.r_multiple`. A leg row adds its CONTRIBUTION (v189 B2):
    `fraction x r`, the leg's stored r or, when it has none, the leg's own
    exit priced by `metrics.r_multiple` (a leg row has `legs: None`, so that
    prices the single exit). A +2R TP1 on half the position adds +1R.
    """
    if part["leg_total"] == 1:
        journal_r = _float_or_none(entry.get("r_realized"))
        return journal_r if journal_r is not None else metrics.r_multiple(part)
    leg_r = part.get("leg_r")
    if leg_r is None:
        leg_r = metrics.r_multiple(part)
    return metrics.leg_contribution_r({"fraction": part.get("fraction"), "r": leg_r})
```

In `_row_for`, replace

```python
    whole = part["leg_total"] == 1
    r = _float_or_none(entry.get("r_realized")) if whole else None
    if r is None:
        r = metrics.r_multiple(part)
```

with

```python
    whole = part["leg_total"] == 1
    r = _part_r(part, entry)
```

and in `_row_for`'s docstring replace the sentence `A leg's R is the leg's own (`metrics.r_multiple` on a leg row prices that leg's exit); the journal only ever recorded the blended R of the whole position.` with `A leg's R is its contribution, fraction x r (`_part_r`, v189 B2); the journal only ever recorded the blended R of the whole position.` Also change `its own R` to `its own contribution to R` in the first paragraph of that docstring (`A leg is counted as an individual trade -- its own day, its own win/loss, its own contribution to R -- ...`).

- [ ] **Step 5: Update the existing leg-R pins**

In `tests/analytics/test_pnl_calendar.py` (fixture `_TP1` is +2R on 0.5, `_RUNNER` +1R on 0.5):

`test_a_scaled_out_trade_yields_one_row_per_leg_on_each_legs_own_day` — replace

```python
    # Each leg is an individual trade with its own R.
    assert [r["r_multiple"] for r in rows] == pytest.approx([2.0, 1.0])
```

with

```python
    # Each leg is its own row; its R is its contribution: 0.5 x 2 and 0.5 x 1.
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, 0.5])
```

Rename `test_a_legs_r_is_its_own_even_when_the_journal_has_the_blended_one` to `test_a_legs_r_is_its_contribution_even_when_the_journal_has_the_blended_one` and change its assertion to:

```python
    assert [r["r_multiple"] for r in rows] == pytest.approx([1.0, 0.5])
```

`test_a_banked_tp1_leg_of_a_still_open_runner_is_counted` — replace `assert row["r_multiple"] == pytest.approx(2.0)` with:

```python
    assert row["r_multiple"] == pytest.approx(1.0)    # 0.5 x +2R
```

In `tests/admin/test_api_v1_calendar.py`:

`test_a_banked_tp1_partial_counts_on_the_day_it_closed` — replace `assert leg["r_multiple"] == pytest.approx(2.0)` with:

```python
    assert leg["r_multiple"] == pytest.approx(1.0)    # contribution: 0.5 x +2R
```

`test_a_leg_row_on_the_day_route_carries_its_own_d1_fields` — replace the breakdown assertion with:

```python
    assert body["breakdown"]["exit_reason"] == [
        {"key": "tp1", "n": 1, "pnl_amount": 50.0, "r": 1.0, "win_rate": 100.0}]
```

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar_contributions.py
cd "$WT" && python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_calendar.py
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_expand_realized_legs.py
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_tradelog_v2.py
cd "$WT" && python scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
cd "$WT" && python scripts/dev/testrun.py file tests/tracking/test_origin_pooling.py
```

Expected: all PASS. The last four cover the other `expand_realized_legs` consumers (Dashboard realized parts, equity, origin pooling): the two new keys must not change any of their figures. If a Dashboard or equity test fails because it compares a whole part dict, the fix is in the test's expected dict (add the two keys), never by dropping the keys.

- [ ] **Step 7: Complexity gate**

```bash
cd "$WT" && python scripts/dev/complexity_gate.py
```

Expected: PASS. `_row_for` falls from 8 to about 6; `_part_r` is 4; `expand_trade_legs` gains no branch.

- [ ] **Step 8: Commit**

```bash
cd "$WT" && git add swingbot/core/tracking/performance.py swingbot/core/analytics/pnl_calendar.py tests/analytics/test_pnl_calendar_contributions.py tests/analytics/test_pnl_calendar.py tests/admin/test_api_v1_calendar.py && git commit -m "fix(calendar): sum leg contributions, not leg R at full size (v189 B2)"
```
