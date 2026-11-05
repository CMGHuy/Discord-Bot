# v192 — Wait for a reclaim when a market plan's next open gaps toward its stop, Part 1b: builders and replay

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`.

**Bump:** bot patch
**Edge:** expectancy — see the index.
**Spec:** [2026-10-24-v192-gap-toward-stop-reclaim-design.md](../specs/2026-10-24-v192-gap-toward-stop-reclaim-design.md)
**Index:** [2026-10-24-v192-gap-toward-stop-reclaim_0-index.md](2026-10-24-v192-gap-toward-stop-reclaim_0-index.md) — Goal, Global Constraints, § Contracts, Review Focus, Parallelisation and the task ledger live there and bind every task below. **Never read a part whole:** `grep -n "^### Task V192-6:" -A 400 <this file>`.

**Scope of this part (V192-5..V192-7):** the continuation of part 1 (`_1-foundations-and-replay.md`, V192-1..V192-4), split off because part 1 would pass 1500 lines. Builders building waiting market plans; the replay next-open market fill with its fill-bar check, hold cap and observer; the veto branch.

**Where commands run:** every command below runs from the worktree root `.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim` (created in V192-1). Subagent shells reset their cwd between calls: prefix each command with `cd E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-24-v192-gap-toward-stop-reclaim &&`. Never edit the main tree's files from a task.

**Complexity:** after every code task run `python scripts/dev/complexity_gate.py`; it must pass (index § Global Constraints).

---

# Phase 3 (continued) — The builders

### Task V192-5: Builders: waiting market plans under `MARKET_ENTRY_NEXT_OPEN`
**Model:** opus — the two constructors every alert, engine and replay shares; a wrong branch silently changes every market plan's fill or leaks a stamp into knob-off plans.

**Files:**
- Modify: `swingbot/core/planning/builders.py` (new helper `_settle_market_entry`; the two market activations at `:487-488` in `build_strategy_plan` and `:710-711` in `build_confluence_plan`)
- Create: `tests/planning/test_v192_builders_next_open.py`

**Interfaces:**
- Consumes: `gap_reclaim.next_open_applies(plan)`, `gap_reclaim.stamp_next_open(plan, df, index)`, `gap_reclaim.atr_at`, `gap_reclaim.reclaim_level_for` (V192-4); `TradePlanV2.waits_next_open`, `.reclaim_atr`, `.reclaim_level` (V192-3); `config.MARKET_ENTRY_NEXT_OPEN`, `config.GAP_RECLAIM_ATR` (V192-2); `record_transition`, `PlanStatus` (already imported in `builders.py:19`).
- Produces: with `MARKET_ENTRY_NEXT_OPEN` on, every market plan except v180 Turtle Soup comes out of both builders `status == PENDING`, `entry_price is None`, `waits_next_open is True`, empty `status_history`, `trigger_price` unchanged (strategy: the close at `index`; confluence: `scenario.entry`), and `reclaim_atr` / `reclaim_level` stamped when `effective_g() > 0` and ATR14 through the creating bar is usable. With the knob off nothing changes (V192-1 plan golden).

The creating bar: `build_strategy_plan(df, index, ...)` receives it as `index` (the engines pass a `window` frame, live passes the scan frame; `atr_at` slices `df.iloc[:index + 1]` either way); `build_confluence_plan` builds on `df.index[-1]`, so its bar is `len(df) - 1`.

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_v192_builders_next_open.py`

```python
"""V192-5: with MARKET_ENTRY_NEXT_OPEN on, both builders leave market plans PENDING
with no entry price and the next-open marker; GAP_RECLAIM_ATR > 0 adds a_t and X
from bars through the creating bar. Knob off is pinned by the V192-1 plan golden."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.builders import build_confluence_plan, build_strategy_plan
from swingbot.core.planning.plan_types import PlanStatus, plan_to_dict
from tests.backtesting.test_v74_fixture import load_v74_fixture
from tests.helpers import make_ohlcv

V192_KEYS = {"reclaim_atr", "reclaim_level", "reclaim_session", "waits_next_open"}
#: dict keys the knob is allowed to change on a market plan
WAITING_KEYS = {"plan_id", "status", "status_history", "entry_price"} | V192_KEYS


@pytest.fixture
def knobs(monkeypatch):
    def set_(next_open, g):
        monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", next_open)
        monkeypatch.setattr(config, "GAP_RECLAIM_ATR", g)
    return set_


def _wavy(entry, n=60):
    """Bars whose ATR14 is real (H - L = 4% of the price) and flat closes at `entry`."""
    return make_ohlcv([entry] * n, spread=0.02)


def _confluence(direction="bullish", entry=100.0, stop=98.4, target=104.0, df=None):
    if direction == "bearish":
        stop, target = 2 * entry - stop, 2 * entry - target
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    return build_confluence_plan(scenario, df if df is not None else _wavy(entry), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_knob_off_confluence_market_plan_is_active_as_today(knobs, direction):
    knobs(False, 0.0)
    plan = _confluence(direction)
    assert plan.entry_type == "market" and plan.status == PlanStatus.ACTIVE
    assert plan.entry_price == plan.trigger_price == 100.0
    assert [h["reason"] for h in plan.status_history] == ["market_entry"]
    assert not V192_KEYS & set(plan_to_dict(plan))


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_next_open_alone_builds_a_waiting_plan_without_a_veto(knobs, direction):
    knobs(True, 0.0)
    plan = _confluence(direction)
    assert plan.entry_type == "market" and plan.status == PlanStatus.PENDING
    assert plan.entry_price is None and plan.trigger_price == 100.0
    assert plan.waits_next_open is True and plan.status_history == []
    assert plan.reclaim_atr is None and plan.reclaim_level is None
    assert gr.waits_for_open(plan)


@pytest.mark.parametrize("direction, sign", [("bullish", -1), ("bearish", 1)])
def test_gap_knob_stamps_atr_and_level_from_the_creating_bar(knobs, direction, sign):
    knobs(True, 0.25)
    df = _wavy(100.0)
    plan = _confluence(direction, df=df)
    a_t = gr.atr_at(df, len(df) - 1)
    assert plan.reclaim_atr == a_t
    assert plan.reclaim_level == gr.reclaim_level_for(100.0, a_t, 0.25, direction)
    assert (plan.reclaim_level - 100.0) * sign > 0


def test_unusable_atr_leaves_the_plan_waiting_without_a_veto(knobs, monkeypatch):
    knobs(True, 0.25)
    monkeypatch.setattr(gr, "atr_at", lambda df, index: None)
    plan = _confluence()
    assert plan.waits_next_open is True and plan.status == PlanStatus.PENDING
    assert plan.reclaim_atr is None and plan.reclaim_level is None


def test_the_knob_moves_nothing_but_the_entry_state(knobs):
    knobs(False, 0.0)
    off = plan_to_dict(_confluence())
    knobs(True, 0.25)
    on = plan_to_dict(_confluence())
    assert {k: v for k, v in off.items() if k not in WAITING_KEYS} == {
        k: v for k, v in on.items() if k not in WAITING_KEYS}


def _strategy_pairs(limit=8):
    """(index, strategy, direction, knob-off plan, knob-on plan) over the v74 AAPL frame."""
    df = load_v74_fixture()["AAPL"]
    strategies = tuple(ALL_STRATEGIES) + (() if TURTLE_SOUP in ALL_STRATEGIES else (TURTLE_SOUP,))
    pairs = []
    for index in range(120, len(df), 11):
        for strategy in strategies:
            for direction in ("bullish", "bearish"):
                with pytest.MonkeyPatch.context() as mp:
                    mp.setattr(config, "MARKET_ENTRY_NEXT_OPEN", False)
                    mp.setattr(config, "GAP_RECLAIM_ATR", 0.0)
                    off = build_strategy_plan(df, index, ticker="AAPL", strategy=strategy,
                                              horizon_key="4w", direction=direction)
                    mp.setattr(config, "MARKET_ENTRY_NEXT_OPEN", True)
                    mp.setattr(config, "GAP_RECLAIM_ATR", 0.25)
                    on = build_strategy_plan(df, index, ticker="AAPL", strategy=strategy,
                                             horizon_key="4w", direction=direction)
                if off is not None:
                    pairs.append((index, strategy, direction, off, on))
            if sum(1 for p in pairs if p[3].entry_type == "market") >= limit:
                return df, pairs
    return df, pairs


@pytest.mark.slow
def test_strategy_builder_waits_only_for_market_plans():
    df, pairs = _strategy_pairs()
    market = [p for p in pairs if p[3].entry_type == "market" and p[1] != TURTLE_SOUP]
    assert len(market) >= 5, "the sweep must reach real market plans"
    for index, strategy, direction, off, on in pairs:
        d_off, d_on = plan_to_dict(off), plan_to_dict(on)
        if off.entry_type == "market" and strategy != TURTLE_SOUP:
            assert on.status == PlanStatus.PENDING and on.entry_price is None
            assert on.waits_next_open is True and on.trigger_price == off.trigger_price
            assert on.reclaim_atr == gr.atr_at(df, index)
            assert {k: v for k, v in d_off.items() if k not in WAITING_KEYS} == {
                k: v for k, v in d_on.items() if k not in WAITING_KEYS}
        else:                    # stop-entry, limit and Turtle Soup: untouched
            d_off.pop("plan_id"), d_on.pop("plan_id")
            assert d_off == d_on, (strategy, direction, index)


@pytest.mark.slow
def test_strategy_stamp_ignores_bars_after_the_creating_bar(knobs):
    """NO-LOOKAHEAD: the builder's a_t and X are unchanged when every bar after t moves."""
    knobs(True, 0.25)
    df, pairs = _strategy_pairs(limit=1)
    index, strategy, direction, _off, on = next(p for p in pairs if p[4].waits_next_open)
    moved = df.copy()
    moved.iloc[index + 1:, moved.columns.get_loc("High")] *= 1.5
    moved.iloc[index + 1:, moved.columns.get_loc("Low")] *= 0.5
    again = build_strategy_plan(moved, index, ticker="AAPL", strategy=strategy,
                                horizon_key="4w", direction=direction)
    assert (again.reclaim_atr, again.reclaim_level) == (on.reclaim_atr, on.reclaim_level)
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_v192_builders_next_open.py
```

Expected: FAIL — the knob-on plans come out `ACTIVE` with `entry_price == 100.0` and `waits_next_open is None`.

- [ ] **Step 3: Add the helper** — `swingbot/core/planning/builders.py`

Add `from . import gap_reclaim` beside the other relative imports (after `from . import reward_floor`), then this helper directly above `def build_strategy_plan`:

```python
def _settle_market_entry(plan: TradePlanV2, df, index: int, created_at: str) -> None:
    """A market plan's entry state. v192: with MARKET_ENTRY_NEXT_OPEN on (Turtle Soup
    excepted -- gap_reclaim.next_open_applies) the plan stays PENDING, waiting for
    the next open, with a_t and X stamped from bars through ``index``; otherwise it
    is filled at build, exactly as before. Stop-entry and limit plans pass through."""
    if plan.entry_type != "market":
        return
    if gap_reclaim.next_open_applies(plan):
        gap_reclaim.stamp_next_open(plan, df, index)
        return
    record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
```

- [ ] **Step 4: Call it from both builders**

In `build_strategy_plan`, replace

```python
    if entry_type == "market":
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=created_at)
```

with

```python
    _settle_market_entry(plan, df, index, created_at)
```

In `build_confluence_plan`, replace the same two lines with

```python
    _settle_market_entry(plan, df, len(df) - 1, created_at)
```

Nothing else in either builder changes: `entry_price=close if entry_type == "market" else None` still runs at construction (the stamp clears it), so the knob-off path is byte-identical; no later step in either builder reads `plan.entry_price` (`git grep -n "\.entry_price" swingbot/core/planning/builders.py swingbot/core/planning/params.py swingbot/core/planning/acceptance_levels.py` is empty).

- [ ] **Step 5: Run the tests, the goldens and the builder suites**

```bash
python scripts/dev/testrun.py file tests/planning/test_v192_builders_next_open.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_plan_engine_structure.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`build_strategy_plan` and `build_confluence_plan` each lose an `if`).

- [ ] **Step 6: Commit (in the worktree)**

```bash
git add swingbot/core/planning/builders.py tests/planning/test_v192_builders_next_open.py
git commit -m "feat(v192): builders leave market plans waiting for the next open under MARKET_ENTRY_NEXT_OPEN"
```

# Phase 4 — The replay next-open fill

### Task V192-6: Replay next-open market fill: fill-bar check, hold cap, observer
**Model:** opus — the replay fill both measurement arms run on; the fill-bar ordering, the runner hand-off and the hold cap decide every baseline trade's R.

**Files:**
- Create: `swingbot/core/planning/market_next_open.py`
- Create: `tests/planning/test_market_next_open.py`
- Modify: `swingbot/core/planning/exit_sim.py` (`_counts_fill_session` `:770`, `_market_exit` `:837`, the `simulate_exit` docstring's market paragraph; `from . import gap_reclaim` at the top)

**Interfaces:**
- Consumes: `gap_reclaim.waits_for_open`, `decide_at_open`, `gap_toward_stop`, `FILL_OPEN`, `RECLAIM_WAIT`, `GAP_NO_RECLAIM` (V192-4); from `exit_sim`: `ExitResult`, `_not_triggered(cancel_reason)`, `_WalkCtx(high, low, close, entry_index, entry_price, plan, is_bull, sign, risk, end, open_)`, `_runner_phase(df, ctx, tp1_index)`, `_runner_result(ctx, runner)`, `_single_leg_booking(outcome, rr, exit_price, entry_price, sign, risk, plan, entry_index, exit_index)`, `_walk_for(plan, scale_out)`; `lifecycle.stop_touched(plan, high, low)`; `plan_manager.gap_target_fill(bar_open, level, direction)`; `next_open_entry.GAP_TARGET_REASON` (`"gap_target"`).
- Produces (index § Contracts, exact):

```python
@dataclass(frozen=True)
class NextOpenDecision:
    ticker: str; strategy: str; horizon_key: str; source: str; direction: str
    signal_date: str; entry: float; stop: float; open_price: float | None
    atr: float | None; reclaim_level: float | None; gap_atr: float | None
    decision: str            # FILL_OPEN | RECLAIM_WAIT | OPEN_THROUGH_STOP | RISK_CAP | "no_bar"
    reclaimed: bool; ambiguous: bool; fill_price: float | None
def observing(callback) -> ContextManager[None]
def next_open_fill_bar(df, j: int, fill: float, plan, scale_out: bool,
                       max_holding_days: int) -> ExitResult | None
def next_open_market_exit(df, signal_index: int, plan, scale_out: bool,
                          max_holding_days: int) -> ExitResult
# exit_sim._market_exit: v180 first, then waits_for_open(plan) -> next_open_market_exit, else the close fill
# exit_sim._counts_fill_session(plan): ... or gap_reclaim.waits_for_open(plan)
```

`signal_date` is `str(df.index[signal_index].date())`, the same string the engines put in `ArmTrade.entry_date`, so V192-15's `row_key` pairs census rows with arm rows. `gap_atr = gap_toward_stop(plan, open) / plan.reclaim_atr` when both exist, else `None`.

**The fill bar** (`next_open_fill_bar`, both arms; index § Global Constraints, in this order):
1. the open at or beyond TP1 (bull `Open ≥ tp1`, bear `Open ≤ tp1`): v180's `next_open_entry._bar_exit` convention — the bracket's target fills at the open, booked at `gap_target_fill(open, tp1, direction)` (= the open), `outcome = "win"` if that R is positive else `"scratch"`, reason `gap_target`. For an open fill that is a 0R scratch. This comes first because the open precedes every intrabar touch (v180's order);
2. the stop touched on bar `j` → a full loss at the stop, −1R, even when TP1 is also touched (stop-first);
3. TP1 touched → single-leg: the TP1 win at `rr = |tp1 − fill| / risk`; scale-out (`scale_out and tp1_fraction < 1.0`, as `_walk_for` decides): the TP1 leg banked and `_runner_phase` continuing from bar `j`;
4. else `None` — the caller hands off to `_walk_for(plan, scale_out)(df, j, fill, plan, max_holding_days)`, which scans `j + 1 ..`.

`_fill_bar_exit`'s 0R `gap_through_stop` scratch is not reused: an open at or through the stop never fills (`not_triggered`, `open_through_stop`).

**Hold cap:** `_counts_fill_session(plan)` becomes true for a waiting market plan, so `_hold_cap_bars` gives `hold_cap_bars − 1` and the walk ends at `j + hold_cap_bars − 1` (fill session = session 1). A plan without `hold_cap_bars` (every confluence plan) keeps `max_holding_days` bars after the fill — `_hold_cap_bars` returns early, as the index records.

**The veto branch** is V192-7. This task routes `RECLAIM_WAIT` to `_reclaim_exit`, which in this task cancels `gap_no_reclaim` and reports `reclaimed=False`; V192-7 replaces its body with the same-session reclaim fill. No test of this task builds a plan with a `reclaim_level`, and nothing measures before V192-7 is committed (index § Parallelisation: V192-22 after V192-1..V192-19).

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_market_next_open.py`

```python
"""V192-6: a market plan waiting for its next open fills at Open[t+1] in replay (both
measurement arms), with an open-through-stop and risk-cap cancel, a fill-bar check of
TP1-at-the-open, the stop and TP1 (stop-first), the normal walk after the fill bar, and
the fill session counted as session 1 of a hold cap. Bullish and bearish."""
import pytest

from swingbot.core.market.strategy_types import HORIZONS, TURTLE_SOUP
from swingbot.core.planning import exit_sim
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning import market_next_open as mno
from swingbot.core.planning import next_open_entry as noe
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

SIGNAL = 30
FLAT = (100.0, 100.5, 99.5, 100.0)     # never reaches 98.5 / 101.5 or 103 / 97


def _bars(overrides=None, n=120):
    rows = [FLAT] * n
    for i, row in (overrides or {}).items():
        rows[i] = row
    return make_ohlcv(rows, start="2024-01-02")


def _bull(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", direction="bullish",
                entry_type="market", trigger_price=100.0, stop_loss=98.5, tp1=103.0,
                tp2=106.0, tp1_fraction=0.5, status=PlanStatus.PENDING, waits_next_open=True)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=94.0)
    base.update(kw)
    return _bull(**base)


def _run(df, plan, scale_out=True):
    return simulate_exit(df, SIGNAL, plan, scale_out=scale_out)


# --- dispatch ---------------------------------------------------------------------

def test_a_pending_market_plan_without_the_marker_keeps_the_close_fill():
    df = _bars({SIGNAL + 1: (99.0, 99.6, 98.9, 99.2)})
    res = _run(df, _bull(waits_next_open=None))
    assert res.entry_index == SIGNAL and res.entry_price == 100.0


def test_turtle_soup_keeps_the_v180_path_even_with_the_marker():
    shape = PLAN_SHAPES[TURTLE_SOUP]
    plan = _bull(source="strategy", strategy=TURTLE_SOUP, horizon_key="2w",
                 tp1_fraction=shape["tp1_fraction"], hold_cap_bars=shape["hold_cap_bars"],
                 stop_loss=98.0, tp1=104.0, tp2=None)
    df = _bars({SIGNAL + 1: (99.5, 100.2, 99.4, 100.0)})
    expected = noe.next_open_exit(df, SIGNAL, plan, exit_sim._hold_cap_bars(plan, 10))
    assert simulate_exit(df, SIGNAL, plan, scale_out=True, max_holding_days=10) == expected


# --- the open ---------------------------------------------------------------------

@pytest.mark.parametrize("make, bar", [
    (_bull, (99.8, 100.3, 99.6, 100.0)),
    (_bear, (100.2, 100.4, 99.7, 100.0)),
])
def test_fills_at_the_next_open(make, bar):
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.entry_index == SIGNAL + 1 and res.entry_price == bar[0]
    assert res.outcome == "timeout"


@pytest.mark.parametrize("make, opens", [(_bull, [98.5, 97.0]), (_bear, [101.5, 103.0])])
def test_an_open_at_or_through_the_stop_cancels(make, opens):
    for bar_open in opens:
        bar = (bar_open, bar_open + 0.5, bar_open - 0.5, bar_open)
        res = _run(_bars({SIGNAL + 1: bar}), make())
        assert res.outcome == "not_triggered"
        assert res.cancel_reason == gr.OPEN_THROUGH_STOP == "open_through_stop"
        assert res.legs == [] and res.entry_index is None


@pytest.mark.parametrize("make, bar_open", [(_bull, 101.0), (_bear, 99.0)])
def test_a_stop_past_the_ceiling_from_the_open_cancels(make, bar_open):
    """(101 - 98.5) / 101 = 2.5% and (101.5 - 99) / 99 = 2.5%, past the 2% confluence ceiling."""
    bar = (bar_open, bar_open + 0.3, bar_open - 0.3, bar_open)
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.outcome == "not_triggered" and res.cancel_reason == gr.RISK_CAP == "risk_cap"


def test_no_next_bar_is_not_triggered_without_a_reason():
    df = _bars(n=SIGNAL + 1)
    res = _run(df, _bull())
    assert res.outcome == "not_triggered" and res.cancel_reason is None


# --- the fill bar -------------------------------------------------------------------

@pytest.mark.parametrize("make, bar, stop", [
    (_bull, (99.8, 100.3, 98.4, 99.0), 98.5),
    (_bear, (100.2, 101.6, 99.9, 101.0), 101.5),
])
def test_a_stop_touch_on_the_fill_bar_is_a_full_loss(make, bar, stop):
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.outcome == "loss" and res.r_total == -1.0
    assert res.entry_index == res.exit_index == SIGNAL + 1
    assert res.legs == [{"fraction": 1.0, "exit_price": stop, "r": -1.0, "reason": "stop"}]


@pytest.mark.parametrize("make, bar", [
    (_bull, (99.8, 103.5, 98.4, 100.0)),
    (_bear, (100.2, 101.6, 96.5, 100.0)),
])
def test_stop_first_when_the_fill_bar_touches_both(make, bar):
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.outcome == "loss" and res.r_total == -1.0


@pytest.mark.parametrize("make, bar, rr", [
    (_bull, (99.8, 103.2, 99.6, 103.0), (103.0 - 99.8) / (99.8 - 98.5)),
    (_bear, (100.2, 100.4, 96.8, 97.0), (100.2 - 97.0) / (101.5 - 100.2)),
])
def test_tp1_on_the_fill_bar_single_leg_is_the_tp1_win(make, bar, rr):
    res = _run(_bars({SIGNAL + 1: bar}), make(tp1_fraction=1.0), scale_out=False)
    assert res.outcome == "win" and res.exit_index == SIGNAL + 1
    assert res.r_total == round(rr, 3)
    assert res.legs[0]["reason"] == "tp1" and res.legs[0]["exit_price"] == make().tp1


@pytest.mark.parametrize("make, bar", [
    (_bull, (99.8, 103.2, 99.6, 103.0)),
    (_bear, (100.2, 100.4, 96.8, 97.0)),
])
def test_tp1_on_the_fill_bar_scale_out_hands_the_runner_on_from_the_fill_bar(make, bar):
    df = _bars({SIGNAL + 1: bar})
    plan = make()
    res = _run(df, plan)
    j, fill = SIGNAL + 1, bar[0]
    is_bull = plan.direction == "bullish"
    mhd = HORIZONS[plan.horizon_key]["max_holding_days"]
    ctx = exit_sim._WalkCtx(df["High"].values, df["Low"].values, df["Close"].values, j, fill,
                            plan, is_bull, 1 if is_bull else -1, abs(fill - plan.stop_loss),
                            min(j + mhd, len(df) - 1), df["Open"].values)
    assert res == exit_sim._runner_result(ctx, exit_sim._runner_phase(df, ctx, j))
    assert res.legs[0] == {"fraction": 0.5, "exit_price": plan.tp1,
                           "r": round(abs(plan.tp1 - fill) / abs(fill - plan.stop_loss), 3),
                           "reason": "tp1"}


@pytest.mark.parametrize("make, bar_open", [(_bull, 103.2), (_bear, 96.8)])
def test_an_open_beyond_tp1_is_a_0r_gap_target_scratch(make, bar_open):
    """v180's _bar_exit convention; a wide stored ceiling lets the open fill at all."""
    bar = (bar_open, bar_open + 0.4, bar_open - 0.4, bar_open)
    res = _run(_bars({SIGNAL + 1: bar}), make(stop_ceiling_pct=10.0))
    assert res.outcome == "scratch" and res.r_total == 0.0
    assert res.entry_price == bar_open and res.exit_index == SIGNAL + 1
    assert res.legs == [{"fraction": 1.0, "exit_price": bar_open, "r": 0.0,
                         "reason": noe.GAP_TARGET_REASON}]


# --- after the fill bar ---------------------------------------------------------------

@pytest.mark.parametrize("make, bar, later", [
    (_bull, (99.8, 100.3, 99.6, 100.0), (99.5, 99.6, 98.4, 98.6)),
    (_bear, (100.2, 100.4, 99.7, 100.0), (100.5, 101.6, 100.4, 101.4)),
])
def test_the_walk_starts_after_the_fill_bar(make, bar, later):
    df = _bars({SIGNAL + 1: bar, SIGNAL + 3: later})
    plan = make()
    res = _run(df, plan)
    mhd = HORIZONS[plan.horizon_key]["max_holding_days"]
    assert res == exit_sim._walk_for(plan, True)(df, SIGNAL + 1, bar[0], plan, mhd)
    assert res.outcome == "loss" and res.exit_index == SIGNAL + 3


def test_a_confluence_plan_without_a_cap_walks_max_holding_days_after_the_fill():
    df = _bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)})
    res = _run(df, _bull())
    assert res.outcome == "timeout"
    assert res.exit_index == SIGNAL + 1 + HORIZONS["4w"]["max_holding_days"]


def test_the_fill_session_is_session_one_of_a_hold_cap():
    plan = _bull(source="strategy", strategy="Fibonacci", hold_cap_bars=5)
    assert exit_sim._counts_fill_session(plan)
    assert not exit_sim._counts_fill_session(_bull(waits_next_open=None, hold_cap_bars=5))
    res = _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), plan)
    assert res.outcome == "timeout" and res.exit_index == SIGNAL + 1 + 5 - 1


# --- the observer -----------------------------------------------------------------

def test_observer_sees_every_decision():
    seen = []
    with mno.observing(seen.append):
        _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull())
        _run(_bars({SIGNAL + 1: (98.0, 98.4, 97.5, 98.2)}), _bull())
        _run(_bars(n=SIGNAL + 1), _bull())
    _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull())   # outside: not observed
    assert [d.decision for d in seen] == [gr.FILL_OPEN, gr.OPEN_THROUGH_STOP, "no_bar"]
    first = seen[0]
    assert (first.ticker, first.strategy, first.horizon_key, first.source, first.direction) == (
        "AAPL", "S/R Confluence", "4w", "confluence", "bullish")
    assert first.signal_date == str(_bars().index[SIGNAL].date())
    assert (first.entry, first.stop, first.open_price, first.fill_price) == (100.0, 98.5, 99.8, 99.8)
    assert first.reclaimed is False and first.ambiguous is False
    assert first.atr is None and first.reclaim_level is None and first.gap_atr is None
    assert seen[1].fill_price is None and seen[2].open_price is None


def test_gap_atr_is_the_gap_over_the_stored_atr():
    seen = []
    with mno.observing(seen.append):
        _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull(reclaim_atr=0.8))
    assert seen[0].gap_atr == pytest.approx(0.2 / 0.8)


def test_observers_nest_and_unwind_on_error():
    outer, inner = [], []
    with mno.observing(outer.append):
        with pytest.raises(RuntimeError):
            with mno.observing(inner.append):
                raise RuntimeError("boom")
        _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull())
    assert len(outer) == 1 and inner == []
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_market_next_open.py
```

Expected: FAIL — `ImportError: cannot import name 'market_next_open'`.

- [ ] **Step 3: Write the module** — `swingbot/core/planning/market_next_open.py`

```python
"""v192: the replay's next-open market fill, both measurement arms.

A market plan built under MARKET_ENTRY_NEXT_OPEN (gap_reclaim.waits_for_open)
fills at Open[t+1], or cancels on an open at or through the stop or a stop past
the plan's ceiling from the open (gap_reclaim.decide_at_open, the same function
the live PlanManager calls). The fill bar is checked before the plan's normal
exit walk (``next_open_fill_bar``): an open beyond TP1 first (v180's gap-target
convention), then the stop (stop-first), then TP1 -- banked whole, or as the
scale-out TP1 leg with the runner continuing from the fill bar. With the gap
veto armed (a stored reclaim_level) the plan rests at E for that session instead
(``_reclaim_exit``).

Every next-open decision is reported to the callbacks registered with
``observing`` -- the census (V192-15) reads them; nothing else does. v1 only;
exit_sim_v2 is untouched.
"""
from __future__ import annotations

import contextlib
from dataclasses import dataclass

from . import exit_sim
from . import gap_reclaim
from .exit_sim import ExitResult
from .lifecycle import stop_touched
from .next_open_entry import GAP_TARGET_REASON
from .plan_manager import gap_target_fill

NO_BAR = "no_bar"


@dataclass(frozen=True)
class NextOpenDecision:
    ticker: str
    strategy: str
    horizon_key: str
    source: str
    direction: str
    signal_date: str
    entry: float
    stop: float
    open_price: float | None
    atr: float | None
    reclaim_level: float | None
    gap_atr: float | None
    decision: str            # gap_reclaim.FILL_OPEN | RECLAIM_WAIT | OPEN_THROUGH_STOP | RISK_CAP | "no_bar"
    reclaimed: bool
    ambiguous: bool
    fill_price: float | None


_OBSERVERS: list = []


@contextlib.contextmanager
def observing(callback):
    """Call ``callback(NextOpenDecision)`` for every next-open market plan simulated inside."""
    _OBSERVERS.append(callback)
    try:
        yield
    finally:
        _OBSERVERS.remove(callback)


def _emit(decision: NextOpenDecision) -> None:
    for callback in tuple(_OBSERVERS):
        callback(decision)


def _gap_atr(plan, open_price: float | None) -> float | None:
    atr = getattr(plan, "reclaim_atr", None)
    if open_price is None or not atr:
        return None
    return gap_reclaim.gap_toward_stop(plan, open_price) / atr


def _decision(plan, df, signal_index: int, open_price, decision: str, *, fill_price=None,
              reclaimed: bool = False, ambiguous: bool = False) -> NextOpenDecision:
    return NextOpenDecision(
        ticker=plan.ticker, strategy=plan.strategy, horizon_key=plan.horizon_key,
        source=plan.source, direction=plan.direction,
        signal_date=str(df.index[signal_index].date()), entry=plan.trigger_price,
        stop=plan.stop_loss, open_price=open_price, atr=getattr(plan, "reclaim_atr", None),
        reclaim_level=getattr(plan, "reclaim_level", None),
        gap_atr=_gap_atr(plan, open_price), decision=decision, reclaimed=reclaimed,
        ambiguous=ambiguous, fill_price=fill_price)


def _open_beyond_tp1(plan, bar_open: float) -> bool:
    return bar_open >= plan.tp1 if plan.direction == "bullish" else bar_open <= plan.tp1


def _tp1_touched(plan, high: float, low: float) -> bool:
    return high >= plan.tp1 if plan.direction == "bullish" else low <= plan.tp1


def _one_leg(j: int, fill: float, outcome: str, price: float, r: float, reason: str) -> ExitResult:
    return ExitResult(outcome, None, j, j, fill, r,
                      [{"fraction": 1.0, "exit_price": price, "r": r, "reason": reason}])


def _gap_target_exit(df, j: int, fill: float, plan, sign: int, risk: float) -> ExitResult:
    price = gap_target_fill(float(df["Open"].values[j]), plan.tp1, plan.direction)
    r = round((price - fill) * sign / risk, 3)
    return _one_leg(j, fill, "win" if r > 0 else "scratch", price, r, GAP_TARGET_REASON)


def _tp1_exit(df, j: int, fill: float, plan, scale_out: bool, max_holding_days: int,
              sign: int, risk: float) -> ExitResult:
    if scale_out and plan.tp1_fraction < 1.0:      # _walk_for's scale-out rule
        ctx = exit_sim._WalkCtx(df["High"].values, df["Low"].values, df["Close"].values, j,
                                fill, plan, sign == 1, sign, risk,
                                min(j + max_holding_days, len(df) - 1), df["Open"].values)
        return exit_sim._runner_result(ctx, exit_sim._runner_phase(df, ctx, j))
    rr = abs(plan.tp1 - fill) / risk
    r, leg = exit_sim._single_leg_booking("win", rr, plan.tp1, fill, sign, risk, plan, j, j)
    return ExitResult("win", None, j, j, fill, r, [leg])


def next_open_fill_bar(df, j: int, fill: float, plan, scale_out: bool,
                       max_holding_days: int) -> ExitResult | None:
    """The fill bar's own exit, or None when it is clean (the walk then runs from j).
    Order: open beyond TP1 (v180 gap target), the stop (stop-first, -1R), TP1."""
    risk = abs(fill - plan.stop_loss)
    if risk <= 0:
        return None                                 # the walker books no_trade
    sign = 1 if plan.direction == "bullish" else -1
    high, low = float(df["High"].values[j]), float(df["Low"].values[j])
    if _open_beyond_tp1(plan, float(df["Open"].values[j])):
        return _gap_target_exit(df, j, fill, plan, sign, risk)
    if stop_touched(plan, high, low):
        return _one_leg(j, fill, "loss", plan.stop_loss, -1.0, "stop")
    if _tp1_touched(plan, high, low):
        return _tp1_exit(df, j, fill, plan, scale_out, max_holding_days, sign, risk)
    return None


def _filled(df, j: int, fill: float, plan, scale_out: bool, max_holding_days: int) -> ExitResult:
    early = next_open_fill_bar(df, j, fill, plan, scale_out, max_holding_days)
    if early is not None:
        return early
    return exit_sim._walk_for(plan, scale_out)(df, j, fill, plan, max_holding_days)


def _reclaim_exit(df, signal_index: int, open_price: float, plan, scale_out: bool,
                  max_holding_days: int) -> ExitResult:
    """The armed veto: the open sat at or beyond X. V192-7 adds the same-session
    reclaim fill; until then every armed plan cancels gap_no_reclaim."""
    _emit(_decision(plan, df, signal_index, open_price, gap_reclaim.RECLAIM_WAIT))
    return exit_sim._not_triggered(gap_reclaim.GAP_NO_RECLAIM)


def next_open_market_exit(df, signal_index: int, plan, scale_out: bool,
                          max_holding_days: int) -> ExitResult:
    """A waiting market plan: decide at Open[signal_index + 1], then fill and walk.
    ``max_holding_days`` is the walk length after the fill bar, as simulate_exit
    passes it (_hold_cap_bars already applied)."""
    j = signal_index + 1
    if j >= len(df):
        _emit(_decision(plan, df, signal_index, None, NO_BAR))
        return exit_sim._not_triggered()
    open_price = float(df["Open"].values[j])
    decision = gap_reclaim.decide_at_open(plan, open_price)
    if decision == gap_reclaim.RECLAIM_WAIT:
        return _reclaim_exit(df, signal_index, open_price, plan, scale_out, max_holding_days)
    if decision != gap_reclaim.FILL_OPEN:
        _emit(_decision(plan, df, signal_index, open_price, decision))
        return exit_sim._not_triggered(decision)
    _emit(_decision(plan, df, signal_index, open_price, decision, fill_price=open_price))
    return _filled(df, j, open_price, plan, scale_out, max_holding_days)
```

- [ ] **Step 4: Wire it into `exit_sim.py`**

Add `from . import gap_reclaim` after `from .plan_types import TradePlanV2` (`gap_reclaim` imports `lifecycle`, `plan_types`, `stop_scope`, `risk_limits` and `config` only, and `next_open_entry` lazily, so there is no cycle). Then:

```python
def _counts_fill_session(plan) -> bool:
    """v180: the compression short and Turtle Soup; v192: a market plan waiting for
    its next open (its fill session is session 1 of a hold cap)."""
    return (getattr(plan, "strategy", None) in SESSION_ONE_HOLD_CAP
            or gap_reclaim.waits_for_open(plan))
```

```python
def _market_exit(df, signal_index: int, plan: TradePlanV2, scale_out: bool,
                 max_holding_days: int) -> ExitResult:
    """A market entry: v180 next-open plans fill at Open[t+1] (next_open_entry); a v192
    plan waiting for its next open goes to market_next_open; every other market plan
    fills at the signal bar's close, exactly as before."""
    from . import next_open_entry     # next_open_entry imports this module
    if next_open_entry.uses_next_open_fill(plan):
        return next_open_entry.next_open_exit(df, signal_index, plan, max_holding_days)
    if gap_reclaim.waits_for_open(plan):
        from .market_next_open import next_open_market_exit   # it imports this module
        return next_open_market_exit(df, signal_index, plan, scale_out, max_holding_days)
    entry_price = float(df["Close"].values[signal_index])
    return _walk_for(plan, scale_out)(df, signal_index, entry_price, plan, max_holding_days)
```

In `simulate_exit`'s docstring, extend the market paragraph:

```
    ``market`` entries fill immediately at the signal bar's close, except a
    v180 next-open strategy (``next_open_entry.NEXT_OPEN_STRATEGIES``), which
    fills at the next bar's open, and a v192 plan waiting for its next open
    (``gap_reclaim.waits_for_open``), which ``market_next_open`` fills.
```

Update the `_hold_cap_bars` docstring's "the compression short's and Turtle Soup's fill session is session 1" to "the compression short's, Turtle Soup's and a waiting v192 market plan's fill session is session 1".

- [ ] **Step 5: Run the tests, the goldens and the exit-sim suites**

```bash
python scripts/dev/testrun.py file tests/planning/test_market_next_open.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_next_open_entry.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_single.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_entry.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_hold_cap.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout_witness.py
python scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each. The existing exit-sim tests build PENDING market plans without the marker and keep the close fill; the v1 golden and the scale-out witness are byte-identical. The gate passes (`_market_exit` cc 3, `next_open_fill_bar` cc 5).

- [ ] **Step 6: Commit (in the worktree)**

```bash
git add swingbot/core/planning/market_next_open.py swingbot/core/planning/exit_sim.py tests/planning/test_market_next_open.py
git commit -m "feat(v192): replay next-open market fill -- fill-bar check, hold cap session 1, decision observer"
```

### Task V192-7: Replay veto branch: reclaim fill, ambiguous bar, `gap_no_reclaim`
**Model:** opus — the component arm's only difference from the baseline; the reclaim tick, the same-session limit and the ambiguous-bar convention decide what the measurement scores.

**Files:**
- Modify: `swingbot/core/planning/market_next_open.py` (`_reclaim_exit` body)
- Create: `tests/planning/test_market_next_open_veto.py`

**Interfaces:**
- Consumes: `gap_reclaim.reclaim_touched(plan, high, low)`, `gap_reclaim.reclaim_fill_price(plan)`, `RECLAIM_WAIT`, `GAP_NO_RECLAIM`, `FILL_OPEN`, `OPEN_THROUGH_STOP` (V192-4); `NextOpenDecision`, `observing`, `_decision`, `_emit`, `_filled`, `next_open_fill_bar` (V192-6); `lifecycle.stop_touched`.
- Produces: the veto branch of `next_open_market_exit` (index § Contracts). For an armed plan (`decide_at_open == RECLAIM_WAIT`) on bar `j = t + 1` only:
  - no reclaim (bull `High < E + tick`, bear `Low > E − tick`) → `not_triggered`, `cancel_reason == "gap_no_reclaim"`; the observer row has `decision = RECLAIM_WAIT`, `reclaimed = False`, `fill_price = None`;
  - reclaim → fill at `reclaim_fill_price(plan)` (`E + tick` bull / `E − tick` bear) on bar `j`, then `next_open_fill_bar` and the normal walk exactly as an open fill; the observer row has `reclaimed = True`, `fill_price` = that price, `ambiguous = stop_touched(plan, High[j], Low[j])`;
  - an ambiguous bar (reclaim and stop both touched) is therefore −1R through `next_open_fill_bar`'s stop-first rule — no separate code path, so it biases neither arm.
  The reclaim fill keeps the plan's own stop, targets and hold cap; it is never risk-capped (the decision order puts `RECLAIM_WAIT` before `RISK_CAP`, index § Global Constraints). An open beyond TP1 cannot occur here (the open sits at or beyond `X`, toward the stop).

- [ ] **Step 1: Write the failing tests** — `tests/planning/test_market_next_open_veto.py`

```python
"""V192-7: with a stored reclaim level X, an open at or beyond X toward the stop makes
the plan rest at E for session t+1: one tick through E fills at E +/- one adverse tick
and walks from that bar; no reclaim cancels gap_no_reclaim; a reclaim bar that also
reaches the stop is -1R. Bullish and bearish twins, and a sub-$1 plan."""
import pytest

from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import exit_sim
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning import market_next_open as mno
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_types import PlanStatus
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

SIGNAL = 30
J = SIGNAL + 1
FLAT = (100.0, 100.5, 99.5, 100.0)


def _bars(overrides=None, n=120, flat=FLAT):
    rows = [flat] * n
    for i, row in (overrides or {}).items():
        rows[i] = row
    return make_ohlcv(rows, start="2024-01-02")


def _bull(**kw):
    """E 100, stop 98.5, TP1 103; a_t 2.0 and g 0.25 put X at 99.50."""
    base = dict(source="confluence", strategy="S/R Confluence", direction="bullish",
                entry_type="market", trigger_price=100.0, stop_loss=98.5, tp1=103.0,
                tp2=106.0, tp1_fraction=0.5, status=PlanStatus.PENDING, waits_next_open=True,
                reclaim_atr=2.0, reclaim_level=99.5)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=94.0, reclaim_level=100.5)
    base.update(kw)
    return _bull(**base)


def _observed(df, plan, scale_out=True):
    seen = []
    with mno.observing(seen.append):
        res = simulate_exit(df, SIGNAL, plan, scale_out=scale_out)
    assert len(seen) == 1
    return res, seen[0]


# --- under the threshold the baseline rule applies ----------------------------------

@pytest.mark.parametrize("make, bar", [
    (_bull, (99.51, 100.2, 99.4, 100.0)),       # gap 0.49 < 0.50
    (_bear, (100.49, 100.6, 99.8, 100.0)),
])
def test_a_gap_just_under_the_threshold_fills_at_the_open(make, bar):
    res, seen = _observed(_bars({J: bar}), make())
    assert seen.decision == gr.FILL_OPEN and seen.reclaimed is False
    assert res.entry_index == J and res.entry_price == bar[0]


@pytest.mark.parametrize("make, bar", [
    (_bull, (98.5, 100.2, 98.0, 99.0)),
    (_bear, (101.5, 102.0, 99.9, 101.0)),
])
def test_an_open_at_the_stop_cancels_before_the_veto(make, bar):
    res, seen = _observed(_bars({J: bar}), make())
    assert res.cancel_reason == gr.OPEN_THROUGH_STOP and seen.decision == gr.OPEN_THROUGH_STOP


# --- armed, no reclaim ---------------------------------------------------------------

@pytest.mark.parametrize("make, bar", [
    (_bull, (99.50, 99.90, 99.0, 99.6)),        # exactly at X, never back to E
    (_bull, (99.00, 100.00, 98.9, 99.8)),       # a bare touch of E is not a reclaim
    (_bear, (100.50, 101.0, 100.1, 100.4)),
    (_bear, (101.00, 101.1, 100.00, 100.2)),
])
def test_no_reclaim_cancels_gap_no_reclaim(make, bar):
    res, seen = _observed(_bars({J: bar}), make())
    assert res.outcome == "not_triggered"
    assert res.cancel_reason == gr.GAP_NO_RECLAIM == "gap_no_reclaim"
    assert res.legs == [] and res.entry_index is None
    assert seen.decision == gr.RECLAIM_WAIT
    assert seen.reclaimed is False and seen.ambiguous is False and seen.fill_price is None
    assert seen.open_price == bar[0] and seen.reclaim_level == make().reclaim_level


@pytest.mark.parametrize("make, later", [
    (_bull, (99.8, 101.0, 99.7, 100.8)),
    (_bear, (100.2, 100.3, 99.0, 99.2)),
])
def test_a_reclaim_on_a_later_session_does_not_count(make, later):
    first = (99.0, 99.9, 98.9, 99.5) if make is _bull else (101.0, 101.1, 100.1, 100.5)
    res, _ = _observed(_bars({J: first, J + 1: later}), make())
    assert res.cancel_reason == gr.GAP_NO_RECLAIM


# --- armed, reclaimed ---------------------------------------------------------------

@pytest.mark.parametrize("make, bar, fill", [
    (_bull, (99.2, 100.2, 99.1, 100.1), 100.01),
    (_bear, (100.8, 100.9, 99.8, 99.9), 99.99),
])
def test_a_reclaim_fills_one_tick_through_entry_and_walks_on(make, bar, fill):
    df = _bars({J: bar})
    plan = make()
    res, seen = _observed(df, plan)
    assert res.entry_index == J and res.entry_price == fill
    assert seen.decision == gr.RECLAIM_WAIT
    assert seen.reclaimed is True and seen.ambiguous is False and seen.fill_price == fill
    assert seen.gap_atr == pytest.approx(abs(100.0 - bar[0]) / 2.0)
    mhd = HORIZONS[plan.horizon_key]["max_holding_days"]
    assert res == exit_sim._walk_for(plan, True)(df, J, fill, plan, mhd)


@pytest.mark.parametrize("make, bar, stop", [
    (_bull, (99.0, 100.3, 98.4, 99.0), 98.5),
    (_bear, (101.0, 101.6, 99.9, 100.8), 101.5),
])
def test_an_ambiguous_reclaim_bar_is_a_full_loss(make, bar, stop):
    res, seen = _observed(_bars({J: bar}), make())
    assert seen.reclaimed is True and seen.ambiguous is True
    assert res.outcome == "loss" and res.r_total == -1.0
    assert res.entry_index == res.exit_index == J
    assert res.legs == [{"fraction": 1.0, "exit_price": stop, "r": -1.0, "reason": "stop"}]


@pytest.mark.parametrize("make, bar, fill", [
    (_bull, (99.4, 103.2, 99.3, 103.0), 100.01),
    (_bear, (100.6, 100.7, 96.8, 97.0), 99.99),
])
def test_a_reclaim_bar_that_reaches_tp1_is_the_tp1_win(make, bar, fill):
    plan = make(tp1_fraction=1.0)
    res, _ = _observed(_bars({J: bar}), plan, scale_out=False)
    rr = abs(plan.tp1 - fill) / abs(fill - plan.stop_loss)
    assert res.outcome == "win" and res.exit_index == J and res.r_total == round(rr, 3)


def test_the_reclaim_fill_keeps_the_hold_cap_session_one():
    plan = _bull(source="strategy", strategy="Fibonacci", hold_cap_bars=5)
    res, _ = _observed(_bars({J: (99.2, 100.2, 99.1, 100.1)}), plan)
    assert res.entry_index == J and res.exit_index == J + 5 - 1


def test_the_reclaim_fill_is_never_risk_capped():
    """A stored 1.4% ceiling that the plan's own 1.5% risk at E already breaches: the
    decision order puts RECLAIM_WAIT before RISK_CAP, so the reclaim still fills."""
    plan = _bull(stop_ceiling_pct=1.4)
    res, seen = _observed(_bars({J: (99.2, 100.2, 99.1, 100.1)}), plan)
    assert seen.reclaimed is True and res.entry_price == 100.01


def test_a_sub_dollar_plan_reclaims_on_the_small_tick():
    plan = _bull(trigger_price=0.85, stop_loss=0.835, tp1=0.88, tp2=None, tp1_fraction=1.0,
                 reclaim_atr=0.0123, reclaim_level=0.8469)
    flat = (0.85, 0.8505, 0.8495, 0.85)
    res, seen = _observed(_bars({J: (0.846, 0.8501, 0.8455, 0.8498)}, flat=flat), plan)
    assert seen.reclaimed is True and res.entry_price == 0.8501
    res, seen = _observed(_bars({J: (0.846, 0.85, 0.8455, 0.8498)}, flat=flat), plan)
    assert res.cancel_reason == gr.GAP_NO_RECLAIM
```

- [ ] **Step 2: Run them to see them fail**

```bash
python scripts/dev/testrun.py file tests/planning/test_market_next_open_veto.py
```

Expected: FAIL — every reclaim test sees `not_triggered` / `gap_no_reclaim` (V192-6's interim branch cancels every armed plan); the no-reclaim tests pass already.

- [ ] **Step 3: Implement the branch** — replace `_reclaim_exit` in `swingbot/core/planning/market_next_open.py`

```python
def _reclaim_exit(df, signal_index: int, open_price: float, plan, scale_out: bool,
                  max_holding_days: int) -> ExitResult:
    """The armed veto: the open sat at or beyond X toward the stop, so the plan rests
    as a DAY stop order at E for session t+1 only. One tick through E fills at
    reclaim_fill_price (E +/- one adverse tick, the stop order's slippage) and walks
    exactly as an open fill; no reclaim cancels gap_no_reclaim. A reclaim bar that
    also reaches the stop is ambiguous: filled, then stopped at -1R by
    next_open_fill_bar's stop-first rule."""
    j = signal_index + 1
    high, low = float(df["High"].values[j]), float(df["Low"].values[j])
    if not gap_reclaim.reclaim_touched(plan, high, low):
        _emit(_decision(plan, df, signal_index, open_price, gap_reclaim.RECLAIM_WAIT))
        return exit_sim._not_triggered(gap_reclaim.GAP_NO_RECLAIM)
    fill = gap_reclaim.reclaim_fill_price(plan)
    _emit(_decision(plan, df, signal_index, open_price, gap_reclaim.RECLAIM_WAIT,
                    fill_price=fill, reclaimed=True, ambiguous=stop_touched(plan, high, low)))
    return _filled(df, j, fill, plan, scale_out, max_holding_days)
```

Update the module docstring's last paragraph sentence "(``_reclaim_exit``)" to "(``_reclaim_exit``: one tick through E fills, else ``gap_no_reclaim``)".

- [ ] **Step 4: Run the veto tests, the V192-6 tests and the goldens**

```bash
python scripts/dev/testrun.py file tests/planning/test_market_next_open_veto.py
python scripts/dev/testrun.py file tests/planning/test_market_next_open.py
python scripts/dev/testrun.py file tests/planning/test_gap_reclaim.py
python scripts/dev/testrun.py file tests/backtesting/arms/test_v192_flag_off_golden.py
python scripts/dev/testrun.py file tests/planning/test_v192_plan_golden.py
python scripts/dev/complexity_gate.py
```

Expected: `0 failed` each; the gate passes (`_reclaim_exit` cc 2).

- [ ] **Step 5: Run the part's changed-test selection once**

```bash
python scripts/dev/testrun.py changed
```

Expected: `0 failed`, `0 xfailed`. This is the diff-selected run for V192-1..V192-7, not the plan's full suite (that is V192-26).

- [ ] **Step 6: Commit (in the worktree)**

```bash
git add swingbot/core/planning/market_next_open.py tests/planning/test_market_next_open_veto.py
git commit -m "feat(v192): replay gap veto -- same-session reclaim fill one tick through E, ambiguous bar -1R, gap_no_reclaim"
```
