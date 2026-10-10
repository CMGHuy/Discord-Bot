# v157 Instrument v2, phase 2: fills and costs. Part 2: threading and the full suite (FC6–FC9)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (section 2 "Fills and costs", "Scope", rule 1, "Testing")
**Bump:** bot minor
**Edge:** none (integrity)

> Index, Global Constraints, Where to work, Parallelisation and the task ledger: `2026-10-10-v157-instrument-v2-fills-costs_0-index.md`. Every task here implicitly includes the index's Global Constraints. Pull one task with `grep -n "^### Task FC6" -A 400 docs/superpowers/plans/2026-10-10-v157-instrument-v2-fills-costs_2-threading-suite.md`.

`$R` is the main tree's root, `$WT` = `$R/.claude/worktrees/2026-10-10-v157-instrument-v2-fills-costs`. Never `cd`; every command uses absolute paths or `git -C $WT`.

What this part consumes from part 1 (all verified on disk in parts 1/1b, created there):
- FC5: `exit_sim.simulate_exit(df, signal_index, plan, *, scale_out=False, max_holding_days=None, instrument=None)`; a spec whose `version != "v1"` goes to `exit_sim_v2.simulate_exit_v2`, which returns an `ExitResult` whose `entry_index`/`entry_price` are the **raw fill** and whose `r_total`/`legs[].r` are **net of costs**.
- FC1: `resolve("v2")` = `InstrumentSpec("v2", V2_FILLS, V2_COSTS)`; `ZERO_COSTS`; `V1_FILLS`.
- `backtest.py` imports `simulate_exit` at module level (`backtest.py:66`), so `monkeypatch.setattr(bt, "simulate_exit", ...)` reaches `_replay_live_constructor`.

# Phase C: the instrument threaded into every library consumer

### Task FC6: Backtest threading, fill dates and `signal_date`

**Model:** sonnet — threads one keyword through a replay and rewrites one row builder, with a cross-plan date contract (v158) and three serialisations that must keep their bytes; every edit is written out below.

**Cross-plan (audit 2026-10-10):** v133 task V133-5 also drops its own new context keys inside `tests/backtesting/instrument/golden.py:golden_records`. If that drop is already in the trade loop (v133 merged), add the `signal_date` assert-and-pop of Step 4(a) beside it and keep both drops; if v133 lands later, it must keep this one. Either way the golden bytes stay unchanged.

**Files:**
- Modify: `swingbot/core/backtesting/backtest.py` (`BacktestTrade`: one field and `__post_init__`; `_live_trade` body and docstring; `_replay_live_constructor`: one keyword; `run_backtest`: the existing `_replay_live_constructor(...)` call gains `instrument=instrument`, and one docstring sentence)
- Modify: `tests/backtesting/instrument/golden.py` (`golden_records`: drop `signal_date` after asserting it equals `entry_date`)
- Modify: `tests/backtesting/instrument/test_live_constructor_replay.py` (`test_v2_trade_rows_carry_the_live_plans_levels`: look the plan up by `signal_date`; the entry is now the fill, pinned by FC6's new file)
- Modify: `tests/backtesting/test_v131_witness.py` (`_trade_rows`: drop `signal_date` after asserting it equals `entry_date`)
- Modify: `tests/scripts/test_range_trades_jsonl.py` (the expected row gains `"signal_date"`)
- Create: `tests/backtesting/instrument/test_fills_costs_replay.py`

**Interfaces:**
- Consumes: FC5 `simulate_exit(..., instrument=None)` (part 1b); FC1 `resolve`, `ZERO_COSTS` (part 1). Existing, verified with `git grep -n`: `BacktestTrade` `backtest.py:95`, `_live_trade` :418, `_replay_live_constructor` :438, its call in `run_backtest` :581, `_signal_masks` :356, `_live_plan_at` :404, `entry_context` imported at :71, `asof_row` :70, `MIN_BARS` :74; `tests/helpers.py:10 make_ohlcv`; `tests/fixtures/ohlcv_parity.py` `load_ohlcv`; `tests/backtesting/test_pullback_dryup_witness.py:18 pin_code_defaults`.
- Produces (ledger):
  - `BacktestTrade.signal_date: str | None = None`, the last field; `__post_init__` sets it to `entry_date` when `None`. Every v1 row therefore carries `signal_date == entry_date` without touching the v1 loop's two `BacktestTrade(...)` calls (`backtest.py:667`, `:746`).
  - `_replay_live_constructor(ticker, df, strategy, horizon_key, *, one_at_a_time, scale_out, asof, instrument)`: forwards `instrument=instrument` into `simulate_exit`.
  - `_live_trade(df, i, plan, res, horizon_key, asof)` (signature unchanged; reached only under a live-constructor instrument, i.e. never under v1): `entry_date` = `df.index[res.entry_index]`, `signal_date` = `df.index[i]`, `entry` = `res.entry_price` (raw fill), `holding_days = res.exit_index - res.entry_index`, `return_pct` on the fill's risk. The entry context stays the signal bar's (`df.iloc[:i + 1]`, `asof_row(asof, df.index[i])`): the plan, and every feature recorded with it, is known at the signal close.
- Cross-plan contract (index, "Dates"): v158's folds assign trades by `entry_date`; its PIT membership check reads `signal_date`. `ArmTrade` is not changed.
- Byte stability: `dataclasses.asdict(BacktestTrade)` gains a key. The v1 golden renderer and the v131 witness pop it after asserting `signal_date == entry_date` (the v131 `limit_orders` precedent in `golden.py`), so neither committed fixture changes. `scripts/backtest/run_backtest_range.py:write_trades_jsonl` writes the new key into its JSONL rows (an added column, no value changes); its test pins the new row.
- Complexity: `run_backtest` stays E (35) (one keyword argument, no branch); `_replay_live_constructor` stays B (9); `_live_trade` A (1); `BacktestTrade.__post_init__` A (2).

- [ ] **Step 1: Write the failing test**, `$WT/tests/backtesting/instrument/test_fills_costs_replay.py`:

```python
"""v157 FC6: the v2 replay walks every plan through the instrument's fills and
costs. A v2 trade row's entry_date is its fill bar and its signal_date the
signal bar (the cross-plan contract with v158); a v1 row carries
signal_date == entry_date."""
import dataclasses

import pandas as pd
import pytest

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.helpers import make_ohlcv

TICKER, STRATEGY, HORIZON = "DOCU", "RSI", "4w"
V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
V2_EXIT = {"exit_model": "v2", "scale_out": True}
SIGNAL = (100.0, 100.5, 99.5, 100.0)
HOLD = (101.0, 101.5, 100.5, 101.0)
UP = (101.0, 102.5, 100.5, 102.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


@pytest.fixture
def frame():
    return load_ohlcv(TICKER)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _day(df, k):
    return str(df.index[k].date())


def _row(**kw):
    base = dict(entry_date="2021-03-01", exit_date="2021-03-05", direction="bullish",
                entry=100.0, stop_loss=95.0, take_profit=110.0, outcome="win",
                exit_price=110.0, return_pct=10.0, r_multiple=2.0, holding_days=4)
    base.update(kw)
    return bt.BacktestTrade(**base)


# --- the field ----------------------------------------------------------------

def test_signal_date_defaults_to_the_entry_date():
    assert _row().signal_date == "2021-03-01"


def test_an_explicit_signal_date_is_kept():
    assert _row(signal_date="2021-02-26").signal_date == "2021-02-26"


def test_signal_date_is_the_last_field_so_positional_rows_are_unchanged():
    names = [f.name for f in dataclasses.fields(bt.BacktestTrade)]
    assert names[-1] == "signal_date"
    assert names[:-1] == ["entry_date", "exit_date", "direction", "entry", "stop_loss",
                          "take_profit", "outcome", "exit_price", "return_pct",
                          "r_multiple", "holding_days", "runner_outcome", "context"]


# --- _live_trade: one row from one walked plan ---------------------------------

@pytest.mark.parametrize("instrument", [FREE, V2], ids=["free", "costed"])
def test_live_trade_dates_and_entry_come_from_the_fill(monkeypatch, instrument):
    seen = {}

    def context(window, **kwargs):
        seen.update(rows=len(window), **kwargs)
        return {"probe": True}

    monkeypatch.setattr(bt, "entry_context", context)
    df = make_ohlcv([SIGNAL, HOLD, HOLD, UP, HOLD])
    plan = _plan()
    res = simulate_exit(df, 0, plan, scale_out=True, max_holding_days=2, instrument=instrument)
    assert (res.entry_index, res.entry_price) == (1, 101.0)   # next open, raw
    trade = bt._live_trade(df, 0, plan, res, "4w", None)
    assert (trade.signal_date, trade.entry_date) == (_day(df, 0), _day(df, 1))
    assert trade.exit_date == _day(df, res.exit_index)
    assert trade.entry == 101.0                               # costs never move the price
    assert trade.holding_days == res.exit_index - 1           # counted from the fill bar
    assert trade.r_multiple == round(res.r_total, 3)
    assert trade.return_pct == round(res.r_total * (6.0 / 101.0) * 100, 3)
    assert trade.exit_price == round(res.legs[-1]["exit_price"], 4)
    assert (trade.stop_loss, trade.take_profit) == (95.0, 110.0)
    # The context is the signal bar's: the plan is known at the signal close.
    assert seen["rows"] == 1 and seen["entry"] == 101.0
    assert trade.context == {"probe": True}


# --- run_backtest under v2, end to end on a synthetic tape ----------------------

def test_v2_replay_row_carries_the_fill_bar_and_the_signal_bar(monkeypatch):
    signal = bt.MIN_BARS["2w"]
    df = make_ohlcv([100.0] * signal + [SIGNAL, HOLD, HOLD, UP] + [100.0] * 6)

    def one_signal(frame, strategy, horizon_key):
        bull = pd.Series(False, index=frame.index)
        bull.iloc[signal] = True
        return bull, pd.Series(False, index=frame.index)

    monkeypatch.setattr(bt, "_signal_masks", one_signal)
    monkeypatch.setattr(bt, "_live_plan_at", lambda frame, i, **kw: _plan(horizon_key="2w"))
    monkeypatch.setattr(bt, "entry_context", lambda window, **kw: {})
    summary = bt.run_backtest("T", df, STRATEGY, "2w", **V2_EXIT, instrument=FREE)
    [trade] = summary.trades
    assert (trade.signal_date, trade.entry_date) == (_day(df, signal), _day(df, signal + 1))
    assert trade.entry == 101.0
    exit_index = df.index.get_loc(pd.Timestamp(trade.exit_date))
    assert trade.holding_days == exit_index - (signal + 1)


# --- run_backtest under v2 on the frozen DOCU tape -------------------------------

def test_v2_replay_hands_the_instrument_to_simulate_exit(monkeypatch, frame):
    seen = []
    real = bt.simulate_exit

    def spy(df, index, plan, **kwargs):
        seen.append(kwargs.get("instrument"))
        return real(df, index, plan, **kwargs)

    monkeypatch.setattr(bt, "simulate_exit", spy)
    bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=V2)
    assert seen and all(spec is V2 for spec in seen)


def test_v2_rows_are_the_simulators_fills_net_of_costs(frame):
    summary = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=V2)
    index_of = {_day(frame, k): k for k in range(len(frame))}
    assert summary.trades, "fixture case must trade under v2 or this proves nothing"
    for trade in summary.trades:
        i = index_of[trade.signal_date]
        plan = bt._live_plan_at(frame, i, ticker=TICKER, strategy=STRATEGY,
                                horizon_key=HORIZON, direction=trade.direction)
        res = simulate_exit(frame, i, plan, scale_out=True, instrument=V2)
        assert trade.entry_date == _day(frame, res.entry_index)
        assert trade.signal_date < trade.entry_date    # v2 never fills on the signal bar
        assert trade.entry == round(res.entry_price, 4)
        assert trade.r_multiple == round(res.r_total, 3)
        assert trade.holding_days == res.exit_index - res.entry_index


def test_costs_move_r_and_nothing_else(frame):
    costed = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=V2).trades
    free = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, **V2_EXIT, instrument=FREE).trades
    assert costed

    def events(trades):
        return [(t.signal_date, t.entry_date, t.exit_date, t.outcome, t.entry, t.exit_price)
                for t in trades]

    assert events(costed) == events(free)              # labels follow the event
    assert [t.r_multiple for t in costed] != [t.r_multiple for t in free]
    for c, f in zip(costed, free):
        if c.outcome == "win":
            assert c.r_multiple < f.r_multiple         # slippage never helps a winner


# --- v1 rows ---------------------------------------------------------------------

@pytest.mark.parametrize("instrument", [None, resolve("v1")], ids=["default", "explicit_v1"])
def test_v1_rows_carry_signal_date_equal_to_entry_date(frame, instrument):
    summary = bt.run_backtest(TICKER, frame, STRATEGY, HORIZON, exit_model="v2",
                              scale_out=True, tp2_mode="levels", instrument=instrument)
    assert summary.trades
    assert all(t.signal_date == t.entry_date for t in summary.trades)
```

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_fills_costs_replay.py`
Expected: failures, first `AttributeError: 'BacktestTrade' object has no attribute 'signal_date'`.

- [ ] **Step 3: Implement** in `$WT/swingbot/core/backtesting/backtest.py`.

(a) `BacktestTrade` (`backtest.py:95`): append the field after `context` and add `__post_init__`:

```python
    runner_outcome: str | None = None
    context: dict | None = None
    # v157: the signal bar's date. Under the v2 instrument entry_date is the
    # fill bar (next open, stop or limit fill) and this is the bar the plan
    # was built on; v1 fills on its signal bar, so v1 rows carry entry_date.
    signal_date: str | None = None

    def __post_init__(self):
        if self.signal_date is None:
            self.signal_date = self.entry_date
```

(b) Replace `_live_trade` (`backtest.py:418-435`) whole:

```python
def _live_trade(df, i, plan, res, horizon_key, asof) -> BacktestTrade:
    """One v2-instrument trade row (v157): entry_date and entry are the fill
    (res.entry_index / res.entry_price, raw: costs show only in r_multiple),
    signal_date is the signal bar i, holding_days counts from the fill. The
    entry context is the signal bar's, where the plan was built."""
    entry, stop_loss, take_profit = res.entry_price, plan.stop_loss, plan.tp1
    risk_per_share = abs(entry - stop_loss)
    entry_i, exit_i = res.entry_index, res.exit_index
    return BacktestTrade(
        entry_date=str(df.index[entry_i].date()), exit_date=str(df.index[exit_i].date()),
        direction=plan.direction, entry=round(entry, 4), stop_loss=round(stop_loss, 4),
        take_profit=round(take_profit, 4), outcome=res.outcome,
        exit_price=round(res.legs[-1]["exit_price"], 4),
        return_pct=round(res.r_total * (risk_per_share / entry) * 100, 3),
        r_multiple=round(res.r_total, 3), holding_days=exit_i - entry_i,
        runner_outcome=res.runner_outcome,
        context=entry_context(df.iloc[:i + 1], direction=plan.direction, horizon_key=horizon_key,
                              stop=stop_loss, target=take_profit,
                              asof=asof_row(asof, df.index[i]), entry=entry),
        signal_date=str(df.index[i].date()),
    )
```

(c) `_replay_live_constructor` (`backtest.py:438`): the signature gains `instrument` after `asof`, the docstring one sentence, and the `simulate_exit` call one keyword. Nothing else in the body changes (`open_until = res.exit_index` stays: one-at-a-time still runs from the exit bar).

```python
def _replay_live_constructor(ticker, df, strategy, horizon_key, *, one_at_a_time, scale_out, asof,
                             instrument):
    """The v2 instrument's replay: same signals, warm-up and one-at-a-time rule
    as the v1 loop, but every plan comes from _live_plan_at and every trade is
    walked by simulate_exit under ``instrument`` (its fills and costs, v157).
    Returns (total_signals, trades, runner_counts)."""
```

and, in its loop:

```python
        res = simulate_exit(df, i, plan, scale_out=scale_out, instrument=instrument)
```

(d) In `run_backtest` (`backtest.py:581`) the existing call gains one argument and no branch:

```python
        total_signals, trades, runner_counts = _replay_live_constructor(
            ticker, df, strategy, horizon_key, one_at_a_time=one_at_a_time,
            scale_out=scale_out, asof=asof, instrument=instrument)
```

(e) In `run_backtest`'s docstring, replace the sentence `It ignores ``frictions``; costs arrive in v136 phase 2.` with:

```
    It ignores ``frictions``: fills and costs come from ``instrument``
    (exit_sim_v2, v157), and each row's entry_date is its fill bar while
    signal_date is the signal bar.
```

- [ ] **Step 4: Keep the two pinned serialisations byte-stable and update the JSONL row.**

(a) `$WT/tests/backtesting/instrument/golden.py`, in `golden_records`, replace the trade loop:

```python
            for k, trade in enumerate(trades):
                yield {"case": case, "trade": k, "row": trade}
```

with:

```python
            for k, trade in enumerate(trades):
                # v157 field: a v1 row's signal_date is its entry_date; kept out of the golden bytes.
                assert trade.pop("signal_date") == trade["entry_date"]
                yield {"case": case, "trade": k, "row": trade}
```

(b) `$WT/tests/backtesting/test_v131_witness.py`, replace `_trade_rows` whole:

```python
def _trade_rows(symbol, frame, strategy, horizon):
    summary = run_backtest(symbol, frame, strategy, horizon, exit_model="v2",
                           scale_out=True, tp2_mode="levels")
    # context is entry_context's feature snapshot -- v131 does not touch it, and
    # it is most of the bytes; every priced and scored field is kept. signal_date
    # (v157) equals entry_date on every v1 row and is kept out of the pre-v157 golden.
    rows = []
    for trade in summary.trades:
        record = {k: v for k, v in dataclasses.asdict(trade).items() if k != "context"}
        assert record.pop("signal_date") == record["entry_date"]
        rows.append([symbol, strategy, horizon, record])
    return rows
```

(c) `$WT/tests/scripts/test_range_trades_jsonl.py`: the expected row's last line

```python
                     "context": {"rsi_14": 40.0}}]
```

becomes

```python
                     "context": {"rsi_14": 40.0}, "signal_date": "2021-03-01"}]
```

(d) `$WT/tests/backtesting/instrument/test_live_constructor_replay.py`, replace `test_v2_trade_rows_carry_the_live_plans_levels` whole (the row's entry is now the fill, pinned by `test_fills_costs_replay.py::test_v2_rows_are_the_simulators_fills_net_of_costs`):

```python
def test_v2_trade_rows_carry_the_live_plans_levels(monkeypatch, frame):
    pin_code_defaults(monkeypatch)
    summary = _run(frame, **V2_EXIT, instrument=resolve("v2"))
    index_of = {str(day.date()): k for k, day in enumerate(frame.index)}
    assert summary.trades
    for trade in summary.trades:
        plan = bt._live_plan_at(frame, index_of[trade.signal_date], ticker=TICKER,
                                strategy=STRATEGY, horizon_key=HORIZON,
                                direction=trade.direction)
        assert (trade.stop_loss, trade.take_profit) == (
            round(plan.stop_loss, 4), round(plan.tp1, 4))
```

- [ ] **Step 5: Run the tests, the goldens and complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_fills_costs_replay.py`
Expected: `11 passed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_live_constructor_replay.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_constructor_parity.py`
Expected: `0 failed` (its spy forwards `**kwargs`, so the new `instrument=` keyword reaches the real simulator).
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `1 passed` (slow-marked: run it by file; never regenerate the golden).
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_range_trades_jsonl.py`
Expected: `1 passed`.
Run: `python $WT/scripts/dev/testrun.py changed`
Expected: `0 failed` (picks up every other test reaching `backtest.py`: `test_wf_portfolio.py`, `test_measure_strategy_arm.py`, `test_alert_density.py` build `BacktestTrade` by keyword and are unaffected).
Run: `python -m radon cc -s $WT/swingbot/core/backtesting/backtest.py | grep -E "run_backtest|_replay_live_constructor|_live_trade|BacktestTrade"`
Expected: `run_backtest - E (35)`, `run_backtest_daterange - D (25)` (both unchanged), `_replay_live_constructor - B (9)`, `_live_trade - A (1)`, `BacktestTrade.__post_init__ - A (2)`.

If `test_fills_costs_replay.py::test_costs_move_r_and_nothing_else` fails on `events(costed) == events(free)`, do not loosen it: costs must not change any fill, exit bar or label, so a difference is a bug in FC4's `_booked` (stop and report), not in this test.

- [ ] **Step 6: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/backtesting/backtest.py tests/backtesting/instrument/golden.py tests/backtesting/instrument/test_live_constructor_replay.py tests/backtesting/instrument/test_fills_costs_replay.py tests/backtesting/test_v131_witness.py tests/scripts/test_range_trades_jsonl.py
git -C $WT commit -m "feat(v157): v2 replay walks plans under the instrument; rows carry the fill bar as entry_date and a new signal_date (FC6)"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows nothing new.

### Task FC7: Arms engines and `run_arm` take the instrument

**Model:** sonnet — an optional keyword threaded through three small modules, each forwarding into FC5's seam; the code is written out below and the guard against v1 drift is the existing arms tests.

**Cross-plan (audit 2026-10-10):** If `blocked_sink` is already a keyword of `StrategyEngine.__init__` (v147 merged), the Step 3(b) signature is `(self, strategies=None, compression_context=None, instrument=None, *, blocked_sink=None, compression_allowlist=None)` instead (type annotations as on `main`), keeping both groups of `self.` assignments (v147's and `self.instrument = instrument`); `test_strategy_engine_keeps_its_positional_arguments` still holds, since `instrument` stays the third positional argument. Otherwise write the signature as below.

**Files:**
- Modify: `swingbot/core/backtesting/arms/engine.py` (`get_engine`, `run_arm`: one keyword-only `instrument=None` each)
- Modify: `swingbot/core/backtesting/arms/strategy_engine.py` (`StrategyEngine.__init__` stores `instrument`; `iter_trades`' one `simulate_exit` call forwards it; module docstring sentence)
- Modify: `swingbot/core/backtesting/arms/confluence_engine.py` (`ConfluenceEngine.__init__(instrument=None)`; `run_ticker`'s `simulate_exit` call forwards it)
- Create: `tests/backtesting/arms/test_engine_instrument.py`

**Interfaces:**
- Consumes: FC5 `simulate_exit(..., instrument=None)` (part 1b); FC1 `resolve` (part 1). Existing, verified with `git grep -n`: `engine.get_engine` `arms/engine.py:18`, `run_arm` :29, `ArmEngine` Protocol :11 (its `run_ticker` signature is not changed: the instrument is constructor state, so callers of `run_ticker` are untouched); `StrategyEngine.__init__` `strategy_engine.py:85`, `iter_trades` :182 (cc 14: the edit adds a keyword argument, no branch), `_entries` :144, `_candidate_plan` :218, the module-level names `simulate_exit` and `exit_params_for` (imported at :35); `ConfluenceEngine.run_ticker` `confluence_engine.py:14`, module-level `replay_scenarios` (:5) and `simulate_exit` (:6, imported from `plan_engine`, the same function object as `exit_sim.simulate_exit`); `MIN_BARS` `strategy_types.py:327`.
- Produces (ledger):
  - `get_engine(engine_id: str, *, instrument=None)`
  - `run_arm(ticker, df, engine_ids, horizons, signal_window, delta, *, instrument=None)`
  - `StrategyEngine(strategies=None, compression_context=None, instrument=None)` (appended last: `compression_research.py:83` passes the first two positionally/by keyword and is unaffected)
  - `ConfluenceEngine(instrument=None)`
- Under v2 an engine's `ArmTrade.entry_date` stays the **signal** date (index, "Dates": `ArmTrade` is not changed) and `r_multiple` is the v2 walk's net `r_total`. Compression shorts are stop entries, so they never see `GAP_CANCEL`; `_CANCEL_REASONS` is not changed (an unknown reason already counts as `"not_triggered"`).
- No script passes an instrument (index, "Reach"): `scripts/backtest/measure_arms.py:64`, `scripts/backtest/fvg_attribution.py:175`, `scripts/reports/{runner_headroom,volume_context_report}.py` keep the v1 default.

- [ ] **Step 1: Write the failing test**, `$WT/tests/backtesting/arms/test_engine_instrument.py`:

```python
"""v157 FC7: run_arm, get_engine and both arms engines carry an optional
instrument down to simulate_exit; None keeps v1. ArmTrade rows keep the
signal date; their r_multiple is the walk's (net, under v2) r_total."""
import pandas as pd
import pytest

from swingbot.core.backtesting.arms import confluence_engine, engine, strategy_engine
from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.market.strategy_types import MIN_BARS
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
SIGNAL = (100.0, 100.5, 99.5, 100.0)
DRIFT = (101.0, 102.0, 100.5, 101.5)
TARGET = (102.0, 111.0, 101.5, 110.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="RSI", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _window(df, first):
    return str(df.index[first].date()), str(df.index[-1].date())


def _spy(monkeypatch, module):
    seen = []
    real = module.simulate_exit

    def spy(df, index, plan, **kwargs):
        seen.append(kwargs.get("instrument"))
        return real(df, index, plan, **kwargs)

    monkeypatch.setattr(module, "simulate_exit", spy)
    return seen


# --- construction ------------------------------------------------------------------

@pytest.mark.parametrize("engine_id", ["strategy", "confluence"])
def test_get_engine_hands_the_instrument_to_the_engine(engine_id):
    assert engine.get_engine(engine_id, instrument=V2).instrument is V2
    assert engine.get_engine(engine_id).instrument is None


def test_strategy_engine_keeps_its_positional_arguments():
    built = StrategyEngine(("RSI",), None, V2)
    assert (built.strategies, built.compression_context, built.instrument) == (("RSI",), None, V2)


@pytest.mark.parametrize("instrument", [None, V2], ids=["v1", "v2"])
def test_run_arm_forwards_the_instrument_to_every_engine(monkeypatch, instrument):
    seen = []

    class Fake:
        def __init__(self, engine_id):
            self.engine_id = engine_id

        def run_ticker(self, ticker, df, horizons, signal_window, params):
            return [self.engine_id]

    def fake_get_engine(engine_id, *, instrument=None):
        seen.append((engine_id, instrument))
        return Fake(engine_id)

    monkeypatch.setattr(engine, "get_engine", fake_get_engine)
    kwargs = {} if instrument is None else {"instrument": instrument}
    out = engine.run_arm("T", None, ("strategy", "confluence"), ("4w",),
                         ("2024-01-01", "2024-12-31"), {}, **kwargs)
    assert out == ["strategy", "confluence"]
    assert seen == [("strategy", instrument), ("confluence", instrument)]


# --- the confluence engine -------------------------------------------------------

def _confluence(monkeypatch, instrument):
    df = make_ohlcv([SIGNAL, DRIFT, TARGET, DRIFT])

    def one_scenario(ticker, signal_df, horizon_key, params=None):
        yield 0, _plan()

    monkeypatch.setattr(confluence_engine, "replay_scenarios", one_scenario)
    seen = _spy(monkeypatch, confluence_engine)
    trades = ConfluenceEngine(instrument=instrument).run_ticker(
        "T", df, ("4w",), _window(df, 0), None)
    return df, seen, trades


def test_confluence_engine_walks_under_the_instrument(monkeypatch):
    df, seen, [trade] = _confluence(monkeypatch, V2)
    assert seen == [V2]
    assert trade.entry_date == str(df.index[0].date())        # ArmTrade keeps the signal date
    assert trade.r_multiple == simulate_exit(df, 0, _plan(), scale_out=True,
                                             instrument=V2).r_total


def test_confluence_engine_default_is_v1(monkeypatch):
    df, seen, [trade] = _confluence(monkeypatch, None)
    assert seen == [None]
    assert trade.r_multiple == simulate_exit(df, 0, _plan(), scale_out=True).r_total


def test_confluence_v2_r_differs_from_v1_on_the_same_plan(monkeypatch):
    _, _, [v1] = _confluence(monkeypatch, None)
    _, _, [v2] = _confluence(monkeypatch, V2)
    assert v2.r_multiple != v1.r_multiple      # next-open fill and costs, not the signal close


# --- the strategy engine ---------------------------------------------------------

def _strategy(monkeypatch, instrument):
    signal = MIN_BARS["4w"]
    df = make_ohlcv([100.0] * signal + [SIGNAL, DRIFT, TARGET] + [100.0] * 8)

    def one_signal(self, frame, strategy, horizon_key):
        bull = pd.Series(False, index=frame.index)
        bull.iloc[signal] = True
        return bull, pd.Series(False, index=frame.index)

    monkeypatch.setattr(StrategyEngine, "_entries", one_signal)
    monkeypatch.setattr(StrategyEngine, "_candidate_plan", lambda self, *a, **k: (_plan(), {}))
    monkeypatch.setattr(strategy_engine, "exit_params_for", lambda strategy: {"tp2": None})
    seen = _spy(monkeypatch, strategy_engine)
    trades = StrategyEngine(strategies=("RSI",), instrument=instrument).run_ticker(
        "T", df, ("4w",), _window(df, signal), None)
    return df, signal, seen, trades


def test_strategy_engine_walks_under_the_instrument(monkeypatch):
    df, signal, seen, [trade] = _strategy(monkeypatch, V2)
    assert seen == [V2]
    assert trade.entry_date == str(df.index[signal].date())
    assert trade.r_multiple == simulate_exit(df, signal, _plan(), scale_out=True,
                                             instrument=V2).r_total


def test_strategy_engine_default_is_v1(monkeypatch):
    df, signal, seen, [trade] = _strategy(monkeypatch, None)
    assert seen == [None]
    assert trade.r_multiple == simulate_exit(df, signal, _plan(), scale_out=True).r_total
```

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/arms/test_engine_instrument.py`
Expected: failures, first `TypeError: get_engine() got an unexpected keyword argument 'instrument'`.

- [ ] **Step 3: Implement.**

(a) `$WT/swingbot/core/backtesting/arms/engine.py`, replace `get_engine` and `run_arm` (`:18-39`) whole:

```python
def get_engine(engine_id: str, *, instrument=None) -> ArmEngine:
    """Construct a registered engine without importing inactive engines.
    ``instrument`` (v157): None is v1; any other spec walks every trade under
    its fills and costs (exit_sim.simulate_exit's seam)."""
    if engine_id == "confluence":
        from swingbot.core.backtesting.arms.confluence_engine import ConfluenceEngine
        return ConfluenceEngine(instrument=instrument)
    if engine_id == "strategy":
        from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
        return StrategyEngine(instrument=instrument)
    raise ValueError(f"unknown engine {engine_id!r}; expected one of {DEFAULT_ENGINES}")


def run_arm(ticker: str, df, engine_ids, horizons, signal_window, delta: dict, *,
            instrument=None) -> list:
    """Run one ticker arm, applying its config globals inside this worker.
    ``instrument`` goes to every engine (get_engine); None is v1."""
    from swingbot.scan_params import ScanParams

    with apply_knobs(delta):
        params = ScanParams.from_config()
        out: list = []
        for engine_id in engine_ids:
            out.extend(get_engine(engine_id, instrument=instrument).run_ticker(
                ticker, df, horizons, signal_window, params))
    return out
```

(b) `$WT/swingbot/core/backtesting/arms/strategy_engine.py`:

The `__init__` signature (`:85`) and its first lines become:

```python
    def __init__(self, strategies=None, compression_context: CompressionResearchContext | None = None,
                 instrument=None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)
        self.compression_context = compression_context
        # v157: the backtest instrument every simulate_exit call runs under; None is v1.
        self.instrument = instrument
```

(the remaining `__init__` lines, `self.compression_reasons` onward, are unchanged). In `iter_trades` (`:211`) the one call becomes:

```python
            result = simulate_exit(df, index, plan, scale_out=True, instrument=self.instrument)
```

and in the module docstring, after the sentence ending ``simulate_exit`` alone walks later bars to determine the outcome.`` add:

```
Under a v2 instrument (``StrategyEngine(instrument=...)``, v157) that walk uses
the instrument's fills and costs; each ArmTrade still carries its signal date.
```

(c) `$WT/swingbot/core/backtesting/arms/confluence_engine.py`, the class becomes:

```python
class ConfluenceEngine:
    engine_id = "confluence"

    def __init__(self, instrument=None):
        # v157: the backtest instrument every simulate_exit call runs under; None is v1.
        self.instrument = instrument

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        """Produce closed confluence trades with signal dates in the window."""
        start, end = signal_window
        signal_df = df.loc[:end]
        out = []
        for horizon_key in horizons:
            for index, plan in replay_scenarios(ticker, signal_df, horizon_key, params=params):
                entry_date = str(df.index[index].date())
                if entry_date < start:
                    continue
                result = simulate_exit(df, index, plan, scale_out=True,
                                       instrument=self.instrument)
                if result.outcome in SKIPPED:
                    continue
                out.append(arm_trade_from_plan(
                    plan, entry_date=entry_date, outcome=result.outcome,
                    r_multiple=result.r_total,
                ))
        return out
```

- [ ] **Step 4: Run the tests, the older arms and exit tests, the golden and complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/arms/test_engine_instrument.py`
Expected: `10 passed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/arms/`
Expected: `0 failed` (`test_confluence_engine.py`, `test_strategy_engine.py`, `test_pullback_dryup_replay.py`, `test_reachability.py` call `run_arm`/the engines without an instrument: v1, unchanged).
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`
Expected: `0 failed`. If it fails, run the same command against main (`python $R/scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py`): a failure there too, with the same assertion, is the pre-existing sandbox environment failure part 1 noted, not this task's; record it for FC9. A failure only in `$WT` is this task's bug.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `1 passed`.
Run: `python -m radon cc -s $WT/swingbot/core/backtesting/arms/engine.py $WT/swingbot/core/backtesting/arms/strategy_engine.py $WT/swingbot/core/backtesting/arms/confluence_engine.py | grep -E "get_engine|run_arm|iter_trades |__init__|run_ticker"`
Expected: `get_engine - A (3)`, `run_arm - A (2)`, `StrategyEngine.iter_trades - C (14)` (unchanged), `StrategyEngine.__init__ - A (2)`, `ConfluenceEngine.__init__ - A (1)`, `ConfluenceEngine.run_ticker - A (5)`.

- [ ] **Step 5: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/backtesting/arms/engine.py swingbot/core/backtesting/arms/strategy_engine.py swingbot/core/backtesting/arms/confluence_engine.py tests/backtesting/arms/test_engine_instrument.py
git -C $WT commit -m "feat(v157): run_arm, get_engine and both arms engines take an optional instrument (FC7)"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows nothing new.

### Task FC8: `backtest_wf` takes the instrument; "friction-adjusted" label removed

**Model:** sonnet — one pure helper, three keyword threadings and text edits in two files; every edit is written out, and the v1 call must stay byte-for-byte the E22 harness call.

**Files:**
- Modify: `swingbot/core/backtesting/backtest_wf.py` (new `_exit_kwargs`; `_default_run`, `run_folds`, `collect_portfolio_signals` gain `instrument=None`; the "friction-adjusted" wording at `:92`, `:141-153`, `:466-471` rewritten)
- Modify: `scripts/backtest/wf_components.py` (module docstring `:3` and the report's setup line `:180-181`: wording only)
- Create: `tests/backtesting/test_backtest_wf_instrument.py`

**Interfaces:**
- Consumes: FC1 `resolve("v2")` (part 1). Existing, verified with `git grep -n`: `backtest_wf._frame_for` :84, `_default_run` :115 (cc 13), `run_folds` :162 (cc 8), `collect_portfolio_signals` :465 (cc 18, legacy: must not get worse), `_symbols_for_folds` :74; `backtest.run_backtest_daterange` :777 (locally imported inside both run functions, so patching the module attribute reaches them, the pattern `tests/backtesting/test_wf_portfolio.py:132` uses); `marketdata.universe.liquidity_ok`, `sector_map` (also locally imported). It does not need FC5–FC7: its tests replace `run_backtest_daterange`.
- Produces (ledger):
  - `_exit_kwargs(instrument) -> dict`: `None` or a `"v1"` spec → exactly `{"frictions": True, "exit_model": "v2", "scale_out": True, "tp2_mode": "levels"}` (today's call, no `instrument` key); any other spec → `{"exit_model": "v2", "scale_out": True, "tp2_mode": "none", "instrument": instrument}` (v2 refuses `tp2_mode="levels"`, v137; costs come from the spec, so no `frictions` key).
  - `_default_run(start, end, overrides, strategies=None, horizons=None, tickers=None, instrument=None)`
  - `run_folds(overrides, folds=ANCHORED_FOLDS, tickers=None, run_fn=None, instrument=None)` (an injected `run_fn` is used as is: the instrument reaches only the default run)
  - `collect_portfolio_signals(start, end, strategies=None, horizons=None, instrument=None)`
- Complexity: `_exit_kwargs` A (3); `_default_run`, `run_folds`, `collect_portfolio_signals` unchanged at 13 / 8 / 18 (the literal keyword block becomes `**_exit_kwargs(instrument)`, no branch).
- Under v2, `collect_portfolio_signals` keys signals on `t.entry_date`, which FC6 makes the fill date: the portfolio replay opens positions on the day they fill. No script passes an instrument yet (v158 owns `--instrument`): `scripts/backtest/wf_run.py:90,121` and `reversal_ab.py:91` keep v1.

- [ ] **Step 1: Write the failing test**, `$WT/tests/backtesting/test_backtest_wf_instrument.py`:

```python
"""v157 FC8: backtest_wf takes an optional instrument. v1 (None or
resolve("v1")) keeps the exact E22 harness call; any other instrument runs
with its own fills and costs and the tp2_mode the live constructor requires.
The "friction-adjusted" label is gone: under exit_model="v2" the frictions
flag never booked a cost."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from swingbot.core.backtesting import backtest_wf as wf
from swingbot.core.backtesting.instrument.contract import resolve

ROOT = Path(__file__).resolve().parents[2]
V2 = resolve("v2")
V1_CALL = {"frictions": True, "exit_model": "v2", "scale_out": True, "tp2_mode": "levels"}
V2_CALL = {"exit_model": "v2", "scale_out": True, "tp2_mode": "none", "instrument": V2}
WINDOW = ("2021-01-01", "2021-12-31")
FOLD = ("2018-06-01", "2020-12-31", *WINDOW)


def _trade():
    return SimpleNamespace(r_multiple=0.5, exit_date="2021-03-05", entry_date="2021-03-01",
                           signal_date="2021-02-26", outcome="win", direction="bullish",
                           entry=100.0, stop_loss=95.0, take_profit=110.0)


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(sym, df, strat, hk, start, end, **kwargs):
        seen.append(kwargs)
        return SimpleNamespace(trades=[_trade()])

    monkeypatch.setattr("swingbot.core.backtesting.backtest.run_backtest_daterange", fake)
    monkeypatch.setattr(wf, "_symbols_for_folds", lambda: ["FAKE"])
    monkeypatch.setattr(wf, "_frame_for", lambda sym: object())
    monkeypatch.setattr("swingbot.core.marketdata.universe.liquidity_ok", lambda df: True)
    monkeypatch.setattr("swingbot.core.marketdata.universe.sector_map",
                        lambda universe: {"FAKE": "Tech"})
    return seen


@pytest.mark.parametrize("instrument", [None, resolve("v1")], ids=["default", "explicit_v1"])
def test_v1_exit_kwargs_are_the_e22_harness_call(instrument):
    assert wf._exit_kwargs(instrument) == V1_CALL


def test_v2_exit_kwargs_carry_the_instrument_and_no_frictions():
    assert wf._exit_kwargs(V2) == V2_CALL


def test_default_run_v1_call_is_unchanged(calls):
    out = wf._default_run(*WINDOW, {}, strategies=["RSI"], horizons=["4w"], tickers=["FAKE"])
    assert calls == [V1_CALL]
    assert out == {"expectancy_r": 0.5, "n": 1}


def test_default_run_threads_the_instrument(calls):
    wf._default_run(*WINDOW, {}, strategies=["RSI"], horizons=["4w"], tickers=["FAKE"],
                    instrument=V2)
    assert calls == [V2_CALL]


@pytest.mark.parametrize(("instrument", "expected"), [(None, V1_CALL), (V2, V2_CALL)],
                         ids=["v1", "v2"])
def test_run_folds_threads_the_instrument_into_both_legs(calls, instrument, expected):
    result = wf.run_folds({}, folds=(FOLD,), tickers=["FAKE"], instrument=instrument)
    assert len(result["folds"]) == 1
    assert calls and all(kwargs == expected for kwargs in calls)


@pytest.mark.parametrize(("instrument", "expected"), [(None, V1_CALL), (V2, V2_CALL)],
                         ids=["v1", "v2"])
def test_collect_portfolio_signals_threads_the_instrument(calls, instrument, expected):
    signals = wf.collect_portfolio_signals(*WINDOW, strategies=["RSI"], horizons=["4w"],
                                           instrument=instrument)
    assert calls == [expected]
    assert [s["date"] for s in signals] == ["2021-03-01"]    # the trade's entry (fill) date


@pytest.mark.parametrize("path", ["swingbot/core/backtesting/backtest_wf.py",
                                  "scripts/backtest/wf_components.py"])
def test_the_friction_adjusted_label_is_gone(path):
    assert "friction-adjusted" not in (ROOT / path).read_text(encoding="utf-8")
```

- [ ] **Step 2: Run it and watch it fail.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_backtest_wf_instrument.py`
Expected: failures, first `AttributeError: module 'swingbot.core.backtesting.backtest_wf' has no attribute '_exit_kwargs'`.

- [ ] **Step 3: Implement** in `$WT/swingbot/core/backtesting/backtest_wf.py`.

(a) In `_frame_for`'s docstring (`:91-93`), the first bullet's opening becomes (the rest of the bullet is unchanged):

```
      * COMPARABILITY. Every number these folds are judged against (the
        E22 baseline) came from scripts/run_backtest_
        range.py, which reads this cache. Folds measured on the other one
        would be comparing against a different dataset.
```

(b) Insert `_exit_kwargs` directly above `def _default_run`:

```python
#: The E22 harness call, unchanged since E39. ``frictions=True`` is a no-op
#: there: run_backtest's exit_model="v2" walk never books slippage or
#: commission (frictions reach only the frozen v1 exit loop), so these numbers
#: carry no costs.
_V1_EXIT_KWARGS = {"frictions": True, "exit_model": "v2", "scale_out": True, "tp2_mode": "levels"}


def _exit_kwargs(instrument) -> dict:
    """run_backtest_daterange's exit keywords for one fold run (v157). None or
    the v1 spec: exactly the E22 harness call. Any other instrument: its own
    fills and costs (exit_sim_v2), with tp2_mode="none" because the live
    constructor refuses the v1 "levels" knob (v137)."""
    if instrument is None or instrument.version == "v1":
        return dict(_V1_EXIT_KWARGS)
    return {"exit_model": "v2", "scale_out": True, "tp2_mode": "none",
            "instrument": instrument}
```

(c) `_default_run`: the signature gains `instrument=None`, one docstring paragraph, and the inner call plus its comment become:

```python
def _default_run(start: str, end: str, overrides: dict,
                 strategies=None, horizons=None, tickers=None, instrument=None) -> dict:
```

docstring, appended after the `tickers` paragraph:

```
    `instrument` (v157): None is the v1 harness call; any other spec runs
    under its fills and costs (`_exit_kwargs`).
```

and the inner loop body (replacing the comment block `:141-153` and the call `:154-156`):

```python
            for hk in horizons:
                # The plan's own snippet omitted horizon_key entirely and
                # was never callable: run_backtest_daterange is
                # (ticker, df, strategy, horizon_key, date_from, date_to).
                # Under v1, exit_model/scale_out/tp2_mode match what the E22
                # baseline was measured with (run_backtest_range.py defaults
                # --tp2 levels), or fold deltas would be comparing against a
                # different exit model; that walk books no costs, whatever
                # the frictions flag says (`_exit_kwargs`).
                #
                # tp2_mode="levels" is also what makes level-sourced
                # components VISIBLE here at all: with "none" the backtest
                # never calls build_level_map, so AVWAP and HVN/LVN change
                # nothing and their folds would score a meaningless 0.0000.
                # The v2 instrument has no "levels" knob (v137): a
                # level-sourced component cannot be judged under v2 here.
                s = run_backtest_daterange(sym, df, strat, hk, start, end,
                                           **_exit_kwargs(instrument))
```

(d) `run_folds`:

```python
def run_folds(overrides: dict, folds=ANCHORED_FOLDS, tickers=None,
              run_fn=None, instrument=None) -> dict:
    """Baseline vs component expectancy per fold. `instrument` (v157) reaches
    the default run only; an injected `run_fn` is used as is."""
    if run_fn is None:
        def _scoped_default_run(start, end, ov):
            return _default_run(start, end, ov, tickers=tickers, instrument=instrument)
        run = _guarded(_scoped_default_run)
    else:
        run = run_fn
```

(the rest of the body is unchanged).

(e) `collect_portfolio_signals`: the signature becomes

```python
def collect_portfolio_signals(start: str, end: str, strategies=None, horizons=None,
                              instrument=None) -> list:
```

the first paragraph of its docstring becomes

```
    """Build a chronological signal list for `portfolio_replay` from real
    fold-run trades. Mirrors `_default_run`'s iteration structure (same
    symbol universe, same liquidity screen, same exit keywords via
    `_exit_kwargs`, including `instrument`) so the portfolio numbers stay
    comparable to the E22 baseline -- see `_frame_for` and `_default_run`
    docstrings for why those specific arguments are frozen. Signals are
    dated by each trade's entry_date: under v2 that is the fill bar.
```

(the remaining paragraphs are unchanged), and its inner call becomes

```python
                s = run_backtest_daterange(sym, df, strat, hk, start, end,
                                           **_exit_kwargs(instrument))
```

(f) `$WT/scripts/backtest/wf_components.py`, wording only, no logic or number change:

line 3: `One component at a time, against the friction-adjusted baseline. The gate` becomes `One component at a time, against the E22 baseline. The gate`.

lines 180-181:

```python
        "- Exit model: v2 + scale-out, `tp2_mode=levels`, frictions ON "
        "(matches the E22 friction-adjusted baseline tooling's own defaults)",
```

become

```python
        "- Exit model: v2 + scale-out, `tp2_mode=levels`, frictions flag on "
        "(the E22 baseline tooling's own defaults; the v2 exit walk books no "
        "slippage or commission, so these numbers carry no costs)",
```

Committed results docs that already quote the old line are history and are not edited.

- [ ] **Step 4: Run the tests, the older walk-forward tests, the golden and complexity.**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_backtest_wf_instrument.py`
Expected: `11 passed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_wf_portfolio.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/test_wf_engine.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_wf_run.py`
Expected: `0 failed`.
Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py`
Expected: `1 passed`.
Run: `python -m radon cc -s $WT/swingbot/core/backtesting/backtest_wf.py | grep -E "_exit_kwargs|_default_run|run_folds|collect_portfolio_signals"`
Expected: `collect_portfolio_signals - C (18)`, `_default_run - C (13)`, `run_folds - B (8)` (all unchanged), `_exit_kwargs - A (3)`.
Run: `git -C $WT grep -n "friction-adjusted" -- swingbot/core/backtesting/backtest_wf.py scripts/backtest/wf_components.py`
Expected: no output.

- [ ] **Step 5: Commit** and confirm the main tree is untouched.

```bash
git -C $WT add swingbot/core/backtesting/backtest_wf.py scripts/backtest/wf_components.py tests/backtesting/test_backtest_wf_instrument.py
git -C $WT commit -m "feat(v157): backtest_wf takes an optional instrument; drop the false friction-adjusted label (FC8)"
git -C $R status --short
```

Expected: the commit lands on the branch; the main tree shows nothing new.

# Phase D: the gate

### Task FC9: Full suite, golden and complexity gate

**Model:** haiku — runs fixed commands and compares their output to written expectations; any red result is escalated, never fixed here.

**Files:** none modified. This task only runs checks; it commits nothing unless Step 5 applies.

**Interfaces:**
- Consumes: everything FC1–FC8 created (index, task ledger).
- Produces: the plan's green verdict, which `/close-out` needs (bot minor bump, applied there).

- [ ] **Step 1: Confirm every task landed.**

```bash
git -C $WT log --oneline main..HEAD
git -C $WT status --short
git -C $R status --short
```

Expected: eight commits, one per task, whose subjects end `(FC1)` … `(FC8)`; a clean worktree; a main tree with nothing from this plan.

- [ ] **Step 2: Prove rule 1 by diff.** The v1-only code is untouched, and `exit_sim.py` changed only inside `simulate_exit`:

```bash
git -C $WT diff --quiet main -- swingbot/core/planning/lifecycle.py swingbot/core/edge/frictions.py swingbot/core/planning/plan_manager.py tests/fixtures/instrument/v1_golden.jsonl tests/fixtures/v131/witness.json && echo UNTOUCHED
git -C $WT diff --stat main -- swingbot/core/planning/exit_sim.py
git -C $WT diff main -- swingbot/core/backtesting/instrument/contract.py | grep -E "^[-+](V1_FILLS|ZERO_COSTS)"
```

Expected: `UNTOUCHED`; `exit_sim.py` shows about 10 insertions and 0 deletions; the last command prints nothing (`V1_FILLS` and `ZERO_COSTS` lines unchanged).

- [ ] **Step 3: Run the v1 golden and the pinned exit goldens by file** (slow-marked ones are skipped by the `fast` tier, so they run here explicitly):

```bash
python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_golden.py
python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_live_constructor_replay.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_exit_parity.py
```

Expected: `0 failed` and `0 xfailed` on each. Never run `golden.py --write`: a red golden is a bug in the task that caused it.

- [ ] **Step 4: Run the full suite** through the `test-runner` subagent (so its output stays out of this context), naming the worktree:

Run: `python $WT/scripts/dev/testrun.py full`
Expected: `0 failed`, `0 xfailed`. A changed pass count is not a failure (`docs/claude/testing-cost.md`); about 90 new tests come from this plan.

**How to tell a pre-existing environment failure from a regression.** Part 1's writer saw `tests/backtesting/test_v129_flag_off_golden.py` fail in a sandbox on unmodified `main` (likely library versions; unproven). For every test that fails in Step 3 or Step 4, run the same test on `main`'s tree with the same interpreter:

```bash
python $R/scripts/dev/testrun.py file <failing test file>
```

- Fails on `$WT`, passes on `$R`: a regression from this plan. Find the task whose files it reaches, fix it there under that task's rules (never by editing a golden), and re-run Steps 3–4.
- Fails on both, with the same assertion and values: pre-existing, not this plan's. It still does not count as green. Record the test id, the error line and "also fails on main <short sha>" in the report, and stop for the partner: the plan closes only on `0 failed` in the real dev environment (the partner's machine, or CI), so either the run is repeated there or the partner decides the environment issue explicitly.
- Fails on both but differently: treat as a regression.

- [ ] **Step 5: Complexity gate** over every file the plan created or changed:

```bash
python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/contract.py $WT/swingbot/core/backtesting/instrument/fills.py $WT/swingbot/core/backtesting/instrument/costs.py $WT/swingbot/core/planning/exit_sim_v2.py $WT/swingbot/core/planning/exit_sim.py $WT/swingbot/core/backtesting/backtest.py $WT/swingbot/core/backtesting/arms/engine.py $WT/swingbot/core/backtesting/arms/strategy_engine.py $WT/swingbot/core/backtesting/arms/confluence_engine.py $WT/swingbot/core/backtesting/backtest_wf.py
```

Expected: only these C-or-worse entries, each at its pre-plan value except `simulate_exit`: `exit_sim._single_leg_exit_walk - C (14)`, `exit_sim._pre_tp1_phase - C (12)`, `exit_sim.simulate_exit - C (13)` (was 11; FC5), and the legacy ones `backtest.run_backtest - E (35)`, `backtest.run_backtest_daterange - D (25)`, `backtest._v1_plan_levels - C (14)`, `strategy_engine.StrategyEngine.iter_trades - C (14)`, `backtest_wf.portfolio_replay - F (45)`, `backtest_wf.collect_portfolio_signals - C (18)`, `backtest_wf._default_run - C (13)`, `backtest_wf.gate_expectancy_harvest - C (11)`, plus any other entry that `python -m radon cc -s -n C <same files on $R>` already lists at the same value. Nothing from `fills.py`, `costs.py` or `exit_sim_v2.py`. Any new entry at 15 or above, or a legacy entry that grew, is a defect: return it to the task that wrote the function.

Only if Step 4's fix loop edited code: commit that fix on the branch with a message naming the task it belongs to, then repeat Steps 3–5.

- [ ] **Step 6: Report** to the controller: the full-suite verdict line, the four Step 3 verdicts, Step 2's output, the radon list, and any pre-existing failure with its `main` comparison. The controller updates the index's `## Progress` on `main` and runs `/close-out` (the `bot` minor bump is applied there; no task edits `VERSION.json`). The plan is not done until the full suite shows `0 failed` and `0 xfailed`.

