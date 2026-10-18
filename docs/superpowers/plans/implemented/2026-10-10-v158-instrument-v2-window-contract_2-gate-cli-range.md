# v158 Instrument v2, phase 3: window contract and folds. Implementation Plan, part 2 (universe gate, CLI, v1 windows, run_backtest_range)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this file whole**: pull one task with `/task-brief WC8` or `grep -n "^### Task WC8" -A 400 docs/superpowers/plans/2026-10-10-v158-instrument-v2-window-contract_2-gate-cli-range.md`.

**Spec:** [`docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md`](../specs/2026-10-06-v136-backtest-instrument-v2-design.md) (cross-cutting rules 1 and 2; section 1 "Universe" and v2 spans)
**Index:** [`2026-10-10-v158-instrument-v2-window-contract_0-index.md`](2026-10-10-v158-instrument-v2-window-contract_0-index.md): header block, `## Where to work`, `## Global Constraints`, `## Parallelisation` and the task ledger. Every task below implicitly includes that index's Global Constraints; the ledger's names, signatures and paths are the contract with parts 1 and 3.

**Tasks in this part:** WC5, WC6, WC7, WC8. WC5 and WC6 need only WC1 (part 1) and may run in parallel with each other and with WC2–WC4 (disjoint files), at most 2 implementers at once. WC7 needs WC1 and must land before WC8, WC9 and WC10 (it edits their files). WC8 needs WC5, WC6 and WC7.

Conventions used in every task (from the index's `## Where to work`):

- `$R` = `/home/user/Discord-Bot` (main tree, never edited by a task). `$WT` = `/home/user/Discord-Bot/.claude/worktrees/2026-10-10-v158-instrument-v2-window-contract` (branch `2026-10-10-v158-instrument-v2-window-contract`).
- Never `cd`. Use `git -C $WT ...` and `python $WT/scripts/dev/testrun.py file tests/...` (test paths resolve against `$WT`).
- After every commit: `git -C $R status --short` must print nothing new (the main tree is unchanged).
- Every new or changed function stays < complexity 15: `python -m radon cc -s -n C <files>` prints nothing (for `run_backtest_range.py`, only the three legacy functions named in the index may print, each at or below its measured score).
- Contract fields used here come from WC1 (part 1): `InstrumentSpec.universe`, `.research_span`, `.holdout_start`, `.train_window`, `.validation_window`, `.liquidity_floor`; `LiquidityFloor(min_avg_dollar_vol, min_price, lookback_bars)`; `V2_LIQUIDITY_FLOOR`.

# Phase B (continued): Universe gate

### Task WC5: Causal PIT universe gate and watchlist slice

**Model:** opus — no-lookahead date logic (a floor that must read no bar past the signal date) plus the signal-date vs entry-date contract with v157; a slip here silently biases every v2 verdict.

**Files:**
- Create: `swingbot/core/backtesting/instrument/universe_gate.py`
- Create: `tests/backtesting/instrument/test_universe_gate.py`

**Why:** spec section 1, "Universe": v2's verdict is on the point-in-time S&P 500, membership checked on the **signal** date, combined with a point-in-time liquidity floor; the watchlist is a reported slice of the same run that fails the verdict when its ExpR < 0 with N >= 30 and reports `thin` below 30. Two facts in today's code shape this unit:

- `run_backtest_range.member_trades` filters on `t.entry_date`, not the signal date. That is exact under v1 (entry is the signal bar's close) but not under v2, where v157 makes `entry_date` the next-open fill date and adds `signal_date`. v1 keeps `member_trades` untouched (byte-identical); v2 uses `eligible_trades` here, which reads `signal_day(trade)`.
- The "point-in-time liquidity floor already there" does not exist: `_exclusion_reason` **skips** `universe.liquidity_reason` for `_pit` runs because it reads the last 20 bars of the whole cached history (lookahead). Partner decision 1 defines the causal floor: average `Close*Volume` over the `lookback_bars` bars ending **at** the signal bar, plus that bar's close, thresholds frozen in `contract.V2_LIQUIDITY_FLOOR` ($20M, $5, 20 bars). No exemption for non-equities: v2's universe is the S&P 500.

**Cross-plan contract with v157 (index Global Constraints):** `signal_day(trade)` returns `trade.signal_date` when the attribute exists and is truthy, else `trade.entry_date` (the fallback until v157 lands; exact under v1). Tests use `SimpleNamespace` trades so they hold whichever plan merges first.

Contract (index ledger): `signal_day(trade) -> str`; `causal_liquidity_reason(df, day: str, floor: LiquidityFloor) -> str | None`; `eligible_trades(trades, spans, df, floor) -> list`; `WATCHLIST_SLICE_MIN_N = 30`; `SliceVerdict(status: str, n: int, expectancy_r: float | None)` with status in `{"pass", "fail", "thin"}`; `watchlist_slice_verdict(n: int, expectancy_r: float | None, min_n: int = WATCHLIST_SLICE_MIN_N) -> SliceVerdict`. WC8 consumes all of them; `n` is the caller's evaluated count (`pool()["n_eval"]`, the N every gate in `run_backtest_range.py` uses).

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/backtesting/instrument/test_universe_gate.py`:

```python
"""v158 WC5: causal point-in-time universe gate and the watchlist-slice verdict
(v136 spec section 1 "Universe"; partner decision 1)."""
import math
from types import SimpleNamespace

import pandas as pd
import pytest

from swingbot.core.backtesting.instrument import universe_gate as ug
from swingbot.core.backtesting.instrument.contract import (V2_LIQUIDITY_FLOOR, LiquidityFloor,
                                                           resolve)
from swingbot.core.marketdata.universe import liquidity_reason

FLOOR = LiquidityFloor(min_avg_dollar_vol=20_000_000.0, min_price=5.0, lookback_bars=20)


def _frame(closes, volumes, start="2021-01-04"):
    index = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes,
                         "Close": closes, "Volume": volumes}, index=index)


def _day(df, i):
    return str(df.index[i].date())


def _trade(entry, signal=None):
    fields = {"entry_date": entry, "exit_date": None, "r_multiple": 1.0}
    if signal is not None:
        fields["signal_date"] = signal
    return SimpleNamespace(**fields)


# --- the floor is the contract's -------------------------------------------

def test_v2_floor_is_the_frozen_contract_floor_and_v1_has_none():
    assert resolve("v2").liquidity_floor == V2_LIQUIDITY_FLOOR == FLOOR
    assert resolve("v1").liquidity_floor is None


# --- signal_day: the v157 field, with the entry_date fallback ---------------

def test_signal_day_falls_back_to_entry_date_before_v157_lands():
    assert ug.signal_day(_trade("2021-03-02")) == "2021-03-02"


def test_signal_day_reads_signal_date_when_present():
    assert ug.signal_day(_trade("2021-03-02", signal="2021-03-01")) == "2021-03-01"


def test_signal_day_treats_a_none_signal_date_as_absent():
    assert ug.signal_day(_trade("2021-03-02", signal=None)) == "2021-03-02"
    trade = SimpleNamespace(entry_date="2021-03-02", signal_date=None)
    assert ug.signal_day(trade) == "2021-03-02"


def test_signal_day_normalises_timestamps_to_iso_days():
    assert ug.signal_day(_trade(pd.Timestamp("2021-03-02"))) == "2021-03-02"


# --- causal_liquidity_reason ------------------------------------------------

def test_liquid_ticker_passes():
    df = _frame([50.0] * 40, [1_000_000] * 40)            # $50M a day
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR) is None


def test_fewer_than_lookback_bars_through_the_signal_day_is_refused():
    df = _frame([50.0] * 40, [1_000_000] * 40)
    assert ug.causal_liquidity_reason(df, _day(df, 18), FLOOR).startswith(
        "insufficient history (<20 bars)")
    assert ug.causal_liquidity_reason(df, _day(df, 19), FLOOR) is None   # exactly 20 bars


def test_price_floor_reads_the_signal_bars_close():
    df = _frame([50.0] * 30 + [4.0] * 10, [1_000_000] * 40)
    assert ug.causal_liquidity_reason(df, _day(df, 29), FLOOR) is None
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR).startswith(
        "price 4.00 < 5.00 floor")


def test_dollar_volume_averages_exactly_the_lookback_bars_ending_at_the_signal():
    df = _frame([50.0] * 40, [100_000] * 20 + [1_000_000] * 20)   # $5M then $50M
    # bars 6..25: 14 x $5M + 6 x $50M = $370M / 20 = $18.5M
    assert ug.causal_liquidity_reason(df, _day(df, 25), FLOOR).startswith(
        "avg dollar vol $18.5M < $20M floor")
    # bars 19..38: 1 x $5M + 19 x $50M = $47.75M
    assert ug.causal_liquidity_reason(df, _day(df, 38), FLOOR) is None


def test_a_non_trading_signal_day_uses_the_last_bar_on_or_before_it():
    df = _frame([50.0] * 5, [1_000_000] * 5)              # Mon 2021-01-04 .. Fri 2021-01-08
    small = LiquidityFloor(min_avg_dollar_vol=1.0, min_price=1.0, lookback_bars=5)
    assert ug.causal_liquidity_reason(df, "2021-01-09", small) is None    # Saturday
    assert ug.causal_liquidity_reason(df, "2021-01-07", small).startswith(
        "insufficient history (<5 bars)")


# --- no lookahead (partner decision 1) ---------------------------------------

def _mixed_frame():
    closes = [50.0] * 20 + [3.0] * 10 + [50.0] * 20 + [1.0] * 10
    volumes = [1_000_000] * 10 + [10_000] * 20 + [2_000_000] * 20 + [0] * 10
    return _frame(closes, volumes)


def test_reason_on_every_day_equals_the_reason_on_the_frame_cut_at_that_day():
    """The floor reads no bar after the signal date: cutting the future off
    never changes the answer, on any day of a frame whose regime flips."""
    df = _mixed_frame()
    for i in range(len(df)):
        day = _day(df, i)
        assert ug.causal_liquidity_reason(df, day, FLOOR) == \
            ug.causal_liquidity_reason(df.iloc[: i + 1], day, FLOOR), day


def test_rewriting_the_future_never_changes_the_verdict():
    df = _frame([50.0] * 60, [1_000_000] * 60)
    day = _day(df, 30)
    before = ug.causal_liquidity_reason(df, day, FLOOR)
    poisoned = df.copy()
    poisoned.iloc[31:, poisoned.columns.get_loc("Close")] = 0.01
    poisoned.iloc[31:, poisoned.columns.get_loc("Volume")] = 0
    assert before is None
    assert ug.causal_liquidity_reason(poisoned, day, FLOOR) is None


def test_causal_floor_keeps_a_name_that_later_collapsed_unlike_the_legacy_floor():
    """The survivorship trap the legacy last-20-bars floor carries for `_pit` runs."""
    df = _frame([50.0] * 31 + [1.0] * 29, [1_000_000] * 31 + [0] * 29)
    assert liquidity_reason(df, min_avg_dollar_vol=20_000_000.0, min_price=5.0) is not None
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR) is None


def test_causal_floor_drops_a_name_illiquid_at_the_signal_that_later_grew():
    df = _frame([50.0] * 60, [1_000] * 31 + [1_000_000] * 29)
    assert liquidity_reason(df, min_avg_dollar_vol=20_000_000.0, min_price=5.0) is None
    assert ug.causal_liquidity_reason(df, _day(df, 30), FLOOR).startswith("avg dollar vol")


# --- eligible_trades ----------------------------------------------------------

SPANS = [("2021-02-01", "2021-03-01")]   # [start, end) like pit_membership


def test_membership_is_checked_on_the_signal_day_not_the_entry_day():
    signal_in = _trade("2021-03-01", signal="2021-02-26")   # fills the day the span ends
    signal_out = _trade("2021-02-01", signal="2021-01-29")  # fills the day the span starts
    df = _frame([50.0] * 60, [1_000_000] * 60)
    assert ug.eligible_trades([signal_in, signal_out], SPANS, df, None) == [signal_in]


def test_spans_none_is_unmasked_and_an_empty_span_list_keeps_nothing():
    df = _frame([50.0] * 60, [1_000_000] * 60)
    trades = [_trade(_day(df, 30)), _trade(_day(df, 40))]
    assert ug.eligible_trades(trades, None, df, None) == trades
    assert ug.eligible_trades(trades, [], df, None) == []


def test_the_floor_is_applied_on_the_signal_day():
    df = _frame([50.0] * 60, [10_000] * 25 + [1_000_000] * 35)
    early = _trade(_day(df, 23), signal=_day(df, 22))    # illiquid window at the signal
    late = _trade(_day(df, 46), signal=_day(df, 45))     # bars 26..45 all liquid
    assert ug.eligible_trades([early, late], None, df, FLOOR) == [late]


def test_eligible_trades_keeps_order_and_every_trade_of_a_shared_day():
    df = _frame([50.0] * 60, [1_000_000] * 60)
    day = _day(df, 30)
    a, b, c = _trade(day), _trade(_day(df, 40)), _trade(day)
    assert ug.eligible_trades([a, b, c], None, df, FLOOR) == [a, b, c]


# --- watchlist_slice_verdict --------------------------------------------------

def test_slice_minimum_is_thirty():
    assert ug.WATCHLIST_SLICE_MIN_N == 30


@pytest.mark.parametrize("n, exp_r, status", [
    (0, None, "thin"),
    (29, -0.5, "thin"),          # below 30: reported, never blocks
    (30, -0.01, "fail"),
    (30, 0.0, "pass"),           # the guard is ExpR < 0, not <= 0
    (120, 0.21, "pass"),
])
def test_slice_verdict(n, exp_r, status):
    verdict = ug.watchlist_slice_verdict(n, exp_r)
    assert verdict == ug.SliceVerdict(status=status, n=n, expectancy_r=exp_r)


def test_slice_min_n_is_overridable():
    assert ug.watchlist_slice_verdict(10, -0.1, min_n=10).status == "fail"


@pytest.mark.parametrize("exp_r", [None, math.nan, math.inf])
def test_a_full_slice_without_a_finite_expectancy_is_an_error(exp_r):
    with pytest.raises(ValueError, match="no finite ExpR"):
        ug.watchlist_slice_verdict(30, exp_r)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_universe_gate.py`
Expected: FAIL, collection error `ImportError: cannot import name 'universe_gate'`.

- [ ] **Step 3: Implement `universe_gate.py`**

Create `$WT/swingbot/core/backtesting/instrument/universe_gate.py`:

```python
"""Causal point-in-time universe gate for instrument v2 (v136 spec section 1,
"Universe"; v158 partner decision 1).

A v2 trade counts only when, on its SIGNAL day:

- the ticker was an index member (``pit_membership`` spans, [start, end)), and
- the ticker cleared the causal liquidity floor: the average Close*Volume of
  the ``lookback_bars`` bars ending AT the signal bar, and that bar's close.

``universe.liquidity_reason`` reads the last bars of the whole cached history,
which is lookahead inside a replay (that is why ``run_backtest_range`` skips it
for ``_pit`` runs). Nothing here reads a bar dated after the signal day;
tests/backtesting/instrument/test_universe_gate.py proves it.

The watchlist is a reported slice of the same run: its verdict fails when the
slice's ExpR < 0 with N >= ``WATCHLIST_SLICE_MIN_N``, and is ``thin`` (never
blocking) below that.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from swingbot.core.backtesting.instrument.contract import LiquidityFloor
from swingbot.core.marketdata.pit_membership import is_member

WATCHLIST_SLICE_MIN_N = 30


def signal_day(trade) -> str:
    """ISO day of the trade's signal bar.

    v157 adds ``BacktestTrade.signal_date``: under v2 ``entry_date`` is the
    next-open fill, one bar after the signal. Until v157 lands the attribute
    is absent and this falls back to ``entry_date``; under v1 both are the
    same bar, so the fallback is exact there."""
    value = getattr(trade, "signal_date", None) or trade.entry_date
    return str(value)[:10]


def _bars_through(df: pd.DataFrame, day: str, count: int) -> pd.DataFrame:
    """The last `count` bars dated on or before `day` (index sorted ascending)."""
    end = int(df.index.searchsorted(pd.Timestamp(day), side="right"))
    return df.iloc[max(0, end - count):end]


def causal_liquidity_reason(df: pd.DataFrame, day: str, floor: LiquidityFloor) -> str | None:
    """None when the ticker cleared `floor` on `day`, else a loggable reason.
    Reads only the `floor.lookback_bars` bars dated on or before `day`."""
    window = _bars_through(df, day, floor.lookback_bars)
    if len(window) < floor.lookback_bars:
        return f"insufficient history (<{floor.lookback_bars} bars) at {day}"
    close = float(window["Close"].iloc[-1])
    if not close >= floor.min_price:
        return f"price {close:.2f} < {floor.min_price:.2f} floor at {day}"
    dollar_vol = float((window["Close"] * window["Volume"]).mean())
    if not dollar_vol >= floor.min_avg_dollar_vol:
        return (f"avg dollar vol ${dollar_vol / 1e6:.1f}M < "
                f"${floor.min_avg_dollar_vol / 1e6:.0f}M floor at {day}")
    return None


def _eligible_on(day: str, spans, df: pd.DataFrame, floor: LiquidityFloor | None) -> bool:
    if not is_member(day, spans):
        return False
    return floor is None or causal_liquidity_reason(df, day, floor) is None


def eligible_trades(trades, spans, df: pd.DataFrame, floor: LiquidityFloor | None) -> list:
    """Trades whose signal day passes PIT membership (`spans`; None = unmasked,
    [] = never a member) and, when `floor` is set, the causal liquidity floor.
    Input order is kept; each signal day is evaluated once."""
    verdicts: dict[str, bool] = {}
    kept = []
    for trade in trades:
        day = signal_day(trade)
        if day not in verdicts:
            verdicts[day] = _eligible_on(day, spans, df, floor)
        if verdicts[day]:
            kept.append(trade)
    return kept


@dataclass(frozen=True)
class SliceVerdict:
    """The watchlist slice's verdict: "pass", "fail" or "thin" (N below the minimum)."""

    status: str
    n: int
    expectancy_r: float | None


def watchlist_slice_verdict(n: int, expectancy_r: float | None,
                            min_n: int = WATCHLIST_SLICE_MIN_N) -> SliceVerdict:
    """Spec section 1: the slice fails the verdict when ExpR < 0 with N >= min_n;
    below min_n it is reported as thin and never blocks."""
    if n < min_n:
        return SliceVerdict("thin", n, expectancy_r)
    if expectancy_r is None or not math.isfinite(expectancy_r):
        raise ValueError(f"watchlist slice has N={n} but no finite ExpR ({expectancy_r!r})")
    return SliceVerdict("fail" if expectancy_r < 0 else "pass", n, expectancy_r)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_universe_gate.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/universe_gate.py`
Expected: no output.

- [ ] **Step 5: Re-run the instrument package (contract and golden untouched)**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/`
Expected: PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/backtesting/instrument/universe_gate.py tests/backtesting/instrument/test_universe_gate.py
git -C $WT commit -m "feat(instrument): v158 WC5 causal PIT universe gate on the signal date and watchlist-slice verdict"
git -C /home/user/Discord-Bot status --short
```

# Phase C: CLI helper, v1 windows from the contract, `run_backtest_range`

### Task WC6: `--instrument` CLI helper

**Model:** sonnet — a small argparse/window helper with pinned behaviour per instrument; the holdout seal is spelled out below.

**Files:**
- Create: `swingbot/core/backtesting/instrument/cli.py`
- Create: `tests/backtesting/instrument/test_instrument_cli.py`

**Why:** spec cross-cutting rule 2: "Every backtest script takes `--instrument v1|v2` and reads spans from the contract." One helper module keeps the flag, the window resolution and the refusals identical across WC8–WC10, so no script decides a date or a refusal message itself.

Behaviour, per instrument:

| Call | v1 (default) | v2 |
|---|---|---|
| `add_instrument_arg(parser)` | `--instrument`, `choices=contract.VERSIONS`, `default="v1"` | same flag |
| `run_instrument(spec)` | `None`: every `run_backtest(..., instrument=...)` call gets exactly today's argument (the path the golden test pins) | the spec |
| `window_for(spec, "train")` | `spec.train_window` (the same tuple object WC7 aliases) | `spec.research_span` |
| `window_for(spec, "validation")` | `spec.validation_window` | `SystemExit` carrying `HOLDOUT_SEALED` (the holdout is sealed; reading it is a one-shot pre-registration path no phase-3 script builds) |
| `check_inside_research(spec, from, to)` | no-op (today's `--from/--to` accepts any window) | `SystemExit` unless `research_start <= from <= to <= research_end` |
| `require_v1(spec, script, owner)` | no-op | `SystemExit` naming the script and the phase that wires v2 (controller-accepted call: non-range/tuner live scripts refuse v2 this way) |

A spec is treated as v1-shaped when it carries a `train_window` (the v1-only field, WC1). Keying on the field rather than on `version == "v1"` keeps the rule in the contract: the instrument with a train/validation split gets split windows.

Contract (index ledger): `add_instrument_arg(parser) -> None`; `spec_from_args(args) -> InstrumentSpec`; `run_instrument(spec) -> InstrumentSpec | None`; `HOLDOUT_SEALED: str`; `window_for(spec, stage: str) -> tuple[str, str]`; `check_inside_research(spec, date_from: str, date_to: str) -> None`; `require_v1(spec, script: str, owner: str) -> None`.

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/backtesting/instrument/test_instrument_cli.py`:

```python
"""v158 WC6: the shared --instrument flag, window resolution and v2 refusals
(v136 spec cross-cutting rule 2; section 1 "v2 spans")."""
import argparse

import pytest

from swingbot.core.backtesting.instrument import cli
from swingbot.core.backtesting.instrument.contract import VERSIONS, resolve


def _parser():
    ap = argparse.ArgumentParser(prog="demo")
    cli.add_instrument_arg(ap)
    return ap


# --- the flag -----------------------------------------------------------------

def test_flag_defaults_to_v1():
    args = _parser().parse_args([])
    assert args.instrument == "v1"
    assert cli.spec_from_args(args) is resolve("v1")


def test_flag_accepts_every_contract_version():
    for version in VERSIONS:
        args = _parser().parse_args(["--instrument", version])
        assert cli.spec_from_args(args) is resolve(version)


def test_flag_refuses_an_unknown_version(capsys):
    with pytest.raises(SystemExit) as exc:
        _parser().parse_args(["--instrument", "v3"])
    assert exc.value.code == 2
    assert "invalid choice: 'v3'" in capsys.readouterr().err


# --- run_instrument: v1 passes None, exactly as today ------------------------

def test_run_instrument_is_none_under_v1():
    assert cli.run_instrument(resolve("v1")) is None


def test_run_instrument_is_the_spec_under_v2():
    assert cli.run_instrument(resolve("v2")) is resolve("v2")


# --- window_for -----------------------------------------------------------------

def test_v1_windows_are_the_contract_objects():
    v1 = resolve("v1")
    assert cli.window_for(v1, "train") is v1.train_window
    assert cli.window_for(v1, "validation") is v1.validation_window
    assert cli.window_for(v1, "train") == ("2020-01-01", "2023-12-31")
    assert cli.window_for(v1, "validation") == ("2024-01-01", "2025-12-31")


def test_v2_train_is_the_research_span():
    assert cli.window_for(resolve("v2"), "train") == ("2010-01-01", "2025-12-31")


def test_v2_validation_is_the_sealed_holdout():
    with pytest.raises(SystemExit) as exc:
        cli.window_for(resolve("v2"), "validation")
    assert cli.HOLDOUT_SEALED in str(exc.value)
    assert "2026-01-01" in str(exc.value)


def test_unknown_stage_is_a_programming_error():
    with pytest.raises(ValueError, match="unknown stage 'holdout'"):
        cli.window_for(resolve("v1"), "holdout")


# --- check_inside_research --------------------------------------------------------

def test_v1_custom_windows_are_unchecked_as_today():
    cli.check_inside_research(resolve("v1"), "2018-06-01", "2025-12-31")   # no raise


@pytest.mark.parametrize("date_from, date_to", [
    ("2010-01-01", "2025-12-31"),     # the whole span, both ends inclusive
    ("2014-01-01", "2014-12-31"),
])
def test_v2_window_inside_the_research_span_is_accepted(date_from, date_to):
    cli.check_inside_research(resolve("v2"), date_from, date_to)


@pytest.mark.parametrize("date_from, date_to", [
    ("2009-12-31", "2012-12-31"),     # starts before the research span
    ("2024-01-01", "2026-01-01"),     # reaches the sealed holdout
    ("2015-06-01", "2015-01-01"),     # reversed
])
def test_v2_window_outside_the_research_span_is_refused(date_from, date_to):
    with pytest.raises(SystemExit) as exc:
        cli.check_inside_research(resolve("v2"), date_from, date_to)
    assert "research span 2010-01-01..2025-12-31" in str(exc.value)


# --- require_v1 ---------------------------------------------------------------------

def test_require_v1_is_silent_under_v1():
    cli.require_v1(resolve("v1"), "measure_arms.py", "phase 5")


def test_require_v1_names_the_script_and_the_owning_phase_under_v2():
    with pytest.raises(SystemExit) as exc:
        cli.require_v1(resolve("v2"), "measure_arms.py", "phase 5 (v2 stage table)")
    message = str(exc.value)
    assert "measure_arms.py" in message
    assert "--instrument v2" in message
    assert "phase 5 (v2 stage table)" in message
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_instrument_cli.py`
Expected: FAIL, collection error `ImportError: cannot import name 'cli'`.

- [ ] **Step 3: Implement `cli.py`**

Create `$WT/swingbot/core/backtesting/instrument/cli.py`:

```python
"""``--instrument v1|v2`` for backtest scripts (v136 spec, cross-cutting rule 2:
"Scripts never define dates").

Every live script under ``scripts/backtest/`` calls ``add_instrument_arg`` and
takes its windows from here, so no script picks a date or words a refusal
itself. v1 (the default) returns exactly today's windows and passes
``instrument=None`` to ``run_backtest``; v2 returns the research span, seals the
holdout, and lets a script refuse a path a later phase owns (``require_v1``).
"""
from __future__ import annotations

import argparse

from swingbot.core.backtesting.instrument import contract
from swingbot.core.backtesting.instrument.contract import InstrumentSpec

HOLDOUT_SEALED = ("the holdout is sealed: one shot per pre-registration, read only after "
                  "the research verdict is committed; no phase-3 script reads it")
_STAGES = ("train", "validation")


def add_instrument_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--instrument`` (default v1) to a script's parser."""
    parser.add_argument(
        "--instrument", choices=contract.VERSIONS, default="v1",
        help="backtest instrument (v136 spec): v1 = today's windows and fills (default); "
             "v2 = research span, point-in-time S&P 500, purged folds")


def spec_from_args(args: argparse.Namespace) -> InstrumentSpec:
    """The InstrumentSpec named by the parsed ``--instrument``."""
    return contract.resolve(args.instrument)


def run_instrument(spec: InstrumentSpec) -> InstrumentSpec | None:
    """What a script passes as ``run_backtest(..., instrument=...)``: None under
    v1, exactly today's argument (rule 1, v1 byte-identical)."""
    return None if spec.version == "v1" else spec


def _has_v1_split(spec: InstrumentSpec) -> bool:
    """True for an instrument carrying the v1 TRAIN/VALIDATION split."""
    return spec.train_window is not None


def window_for(spec: InstrumentSpec, stage: str) -> tuple[str, str]:
    """The (from, to) entry-date window for ``--train`` / ``--validation``.
    v1: its split windows. v2: ``train`` is the research span; ``validation``
    is the sealed holdout and exits."""
    if stage not in _STAGES:
        raise ValueError(f"unknown stage {stage!r}; expected one of {_STAGES}")
    if _has_v1_split(spec):
        return spec.train_window if stage == "train" else spec.validation_window
    if stage == "validation":
        raise SystemExit(f"--instrument {spec.version}: {HOLDOUT_SEALED} "
                         f"(holdout starts {spec.holdout_start})")
    return spec.research_span


def check_inside_research(spec: InstrumentSpec, date_from: str, date_to: str) -> None:
    """Under v2, a ``--from/--to`` window must lie inside the research span (and
    be ordered); under v1 any window is accepted, as today."""
    if _has_v1_split(spec):
        return
    start, end = spec.research_span
    if not start <= str(date_from)[:10] <= str(date_to)[:10] <= end:
        raise SystemExit(f"--instrument {spec.version}: --from/--to {date_from}..{date_to} "
                         f"must lie inside the research span {start}..{end}; {HOLDOUT_SEALED}")


def require_v1(spec: InstrumentSpec, script: str, owner: str) -> None:
    """Exit under any instrument but v1, naming the phase that wires v2 for
    `script`. v1 (the default) runs exactly as before."""
    if spec.version != "v1":
        raise SystemExit(f"{script}: --instrument {spec.version} is not wired yet; "
                         f"{owner} wires it. Run with --instrument v1 (the default).")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_instrument_cli.py`
Expected: PASS, `0 failed`.

Run: `python -m radon cc -s -n C $WT/swingbot/core/backtesting/instrument/cli.py`
Expected: no output.

- [ ] **Step 5: Re-run the instrument package (contract and golden untouched)**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/`
Expected: PASS, `0 failed`, `0 xfailed`.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/backtesting/instrument/cli.py tests/backtesting/instrument/test_instrument_cli.py
git -C $WT commit -m "feat(instrument): v158 WC6 shared --instrument flag, contract windows and v2 refusals"
git -C /home/user/Discord-Bot status --short
```

### Task WC7: v1 windows sourced from the contract

**Model:** sonnet — mechanical alias swaps across six modules with a pinned-literal and identity test; the one sensitive site (the admin TRAIN-only gate) keeps its exact expression.

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py`
- Modify: `scripts/backtest/tune_strategy.py`
- Modify: `scripts/backtest/tune_exit_v2.py`
- Modify: `scripts/backtest/tune_confluence_gates.py`
- Modify: `swingbot/admin/jobs.py`
- Modify: `swingbot/core/backtesting/arms/windows.py`
- Create: `tests/backtesting/instrument/test_v1_windows_pinned.py`

**Why:** partner decision 4: v1's TRAIN/VALIDATION live in the contract (`InstrumentSpec.train_window` / `validation_window`, WC1), and every script-level name becomes an alias of them. The names stay because other modules import them (`measure_adaptive_trail`, `measure_stall_exit`, `measure_bearish_arms`, `measure_alert_density` import `run_backtest_range.TRAIN`; `arms/provenance.py` imports `windows.VALIDATION_START`; the Tuning page shows `jobs.TRAIN_WINDOW`). Values do not change, so every stamp, report and gate is byte-identical (rule 1). The new test pins today's literals **and** asserts each alias **is** the contract's tuple object, so a future re-typed literal fails it.

Scope notes:
- `windows.py` keeps every other `STAGES` literal (pilot/selection/walkforward, the 2018-06 v100 machinery): those are v1-only producer windows outside the guard's scope (index "Out of scope"). Only `VALIDATION_START` and the validation stage's window, which are v1's VALIDATION window, are re-sourced.
- `jobs.assert_train_only` is a security gate. Its body and `_VALIDATION_START_TUPLE`'s expression are untouched; only the tuple it parses now comes from the contract. `tests/admin/test_jobs.py` proves the gate is unchanged.
- `contract.py` imports only `dataclasses`, so importing it from `windows.py` and `jobs.py` adds no import cycle.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/backtesting/instrument/test_v1_windows_pinned.py`:

```python
"""v158 WC7 (rule 1, partner decision 4): every v1 script window equals today's
literal AND is the contract's own tuple, so it can never drift from the contract.

The literals below are the only copies allowed outside contract.py: they are
the pin."""
import importlib
import sys
from pathlib import Path

import pytest

from swingbot.core.backtesting.instrument.contract import resolve

ROOT = Path(__file__).resolve().parents[3]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

V1_TRAIN = ("2020-01-01", "2023-12-31")
V1_VALIDATION = ("2024-01-01", "2025-12-31")


def test_the_contract_holds_todays_v1_windows():
    v1 = resolve("v1")
    assert v1.train_window == V1_TRAIN
    assert v1.validation_window == V1_VALIDATION


@pytest.mark.parametrize("module", [
    "run_backtest_range", "tune_strategy", "tune_exit_v2", "tune_confluence_gates"])
def test_script_train_window_is_the_contract_alias(module):
    mod = importlib.import_module(module)
    assert mod.TRAIN == V1_TRAIN
    assert mod.TRAIN is resolve("v1").train_window


def test_run_backtest_range_validation_is_the_contract_alias():
    import run_backtest_range as rbr
    assert rbr.VALIDATION == V1_VALIDATION
    assert rbr.VALIDATION is resolve("v1").validation_window


def test_admin_job_windows_and_the_train_only_gate_are_unchanged():
    from swingbot.admin import jobs
    assert jobs.TRAIN_WINDOW == V1_TRAIN
    assert jobs.VALIDATION_WINDOW == V1_VALIDATION
    assert jobs.TRAIN_WINDOW is resolve("v1").train_window
    assert jobs.VALIDATION_WINDOW is resolve("v1").validation_window
    assert jobs._VALIDATION_START_TUPLE == (2024, 1, 1)


def test_arms_validation_start_and_stage_are_v1_validation():
    from swingbot.core.backtesting.arms import windows
    assert windows.VALIDATION_START == V1_VALIDATION[0]
    assert windows.STAGES["validation"].signal_window == V1_VALIDATION
    assert windows.STAGES["validation"].signal_window is resolve("v1").validation_window
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_windows_pinned.py`
Expected: FAIL. Every `is resolve("v1")...` assertion fails (each module holds its own literal tuple); the value assertions and `test_the_contract_holds_todays_v1_windows` pass.

- [ ] **Step 3: Alias the windows**

In each file below, add the import line directly after the file's last `from swingbot...` import:

```python
from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument
```

1. `$WT/scripts/backtest/run_backtest_range.py`. Replace

```python
TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
```

with

```python
# v1's windows live in the instrument contract (v158 WC7). The names stay as
# aliases: measure_* scripts import them.
TRAIN = resolve_instrument("v1").train_window
VALIDATION = resolve_instrument("v1").validation_window
```

2. `$WT/scripts/backtest/tune_strategy.py`, 3. `$WT/scripts/backtest/tune_exit_v2.py`, 4. `$WT/scripts/backtest/tune_confluence_gates.py`: in each, replace the line `TRAIN = ("2020-01-01", "2023-12-31")` with:

```python
TRAIN = resolve_instrument("v1").train_window   # v1 contract alias (v158 WC7)
```

5. `$WT/swingbot/admin/jobs.py`. Replace the line `VALIDATION_WINDOW = ("2024-01-01", "2025-12-31")` with:

```python
VALIDATION_WINDOW = resolve_instrument("v1").validation_window   # v1 contract (v158 WC7)
```

Replace the line `TRAIN_WINDOW = ("2020-01-01", "2023-12-31")` with:

```python
TRAIN_WINDOW = resolve_instrument("v1").train_window   # v1 contract (v158 WC7)
```

Keep both comment blocks above them and leave `_VALIDATION_START_TUPLE = tuple(int(p) for p in VALIDATION_WINDOW[0].split("-"))` and `assert_train_only` exactly as they are.

6. `$WT/swingbot/core/backtesting/arms/windows.py`. Replace `VALIDATION_START = "2024-01-01"` with:

```python
_V1_VALIDATION = resolve_instrument("v1").validation_window   # v1 contract (v158 WC7)
VALIDATION_START = _V1_VALIDATION[0]
```

and in `STAGES`, replace

```python
    "validation": StageSpec("validation", (VALIDATION_START, "2025-12-31"), full_width=True),
```

with

```python
    "validation": StageSpec("validation", _V1_VALIDATION, full_width=True),
```

(`_V1_VALIDATION == (VALIDATION_START, "2025-12-31")`, so the stage's `signal_window` keeps its value.)

- [ ] **Step 4: Run the new test and every consumer of the aliased names**

Run: `python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/test_v1_windows_pinned.py`
Expected: PASS, `0 failed`.

Run each (one verdict line each):

```bash
python $WT/scripts/dev/testrun.py file tests/admin/test_jobs.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_jobs.py
python $WT/scripts/dev/testrun.py file tests/admin/test_api_v1_dashboard.py
python $WT/scripts/dev/testrun.py file tests/backtesting/arms/test_windows.py
python $WT/scripts/dev/testrun.py file tests/backtesting/arms/test_provenance.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_measure_arms.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_tune_strategy.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_tuner_gate_loudness.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_range_trades_jsonl.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_alert_density.py
python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/
```

Expected: every run PASS, `0 failed`, `0 xfailed`.

Run: `python -m radon cc -s -n C $WT/swingbot/admin/jobs.py $WT/swingbot/core/backtesting/arms/windows.py`
Expected: no output (no function changed; module-level assignments only).

- [ ] **Step 5: Commit**

```bash
git -C $WT add scripts/backtest/run_backtest_range.py scripts/backtest/tune_strategy.py scripts/backtest/tune_exit_v2.py scripts/backtest/tune_confluence_gates.py swingbot/admin/jobs.py swingbot/core/backtesting/arms/windows.py tests/backtesting/instrument/test_v1_windows_pinned.py
git -C $WT commit -m "refactor(instrument): v158 WC7 v1 TRAIN/VALIDATION windows become aliases of the contract"
git -C /home/user/Discord-Bot status --short
```

### Task WC8: `run_backtest_range.py --instrument v1|v2`

**Model:** opus — edits the acceptance harness's cc-65 `main` (must go down, not up) and wires the v2 universe gate, holdout seal and watchlist slice while v1 stays byte-identical.

**Cross-plan (audit 2026-10-10):** **Complexity gate (v149):** If `scripts/dev/complexity_gate.py` exists (v149 merged), this task lowers a legacy function at or above 15 (`run_backtest_range.main`, cc 65 → about 62), so after its radon step it runs `python scripts/dev/complexity_gate.py`, then `python scripts/dev/complexity_gate.py --update`, and adds `scripts/dev/complexity_baseline.json` to this task's commit (`improved`/`gone` expected; `new`/`risen` never). Full rule: index `## Cross-plan coordination (audit 2026-10-10)`.

**Files:**
- Modify: `scripts/backtest/run_backtest_range.py`
- Create: `tests/scripts/test_run_backtest_range_instrument.py`

**Why:** spec rule 2 (every backtest script takes `--instrument` and reads spans from the contract) and section 1 ("Universe"): this is the first script with a real v2 path. Under v2:

- `--train` is the research span 2010-01-01..2025-12-31 (`cli.window_for`); `--validation` exits with `HOLDOUT_SEALED`; `--from/--to` must lie inside the research span (`cli.check_inside_research`).
- The universe is the contract's (`sp500_pit`). An explicit different `--universe` is refused, never silently replaced.
- Trades are windowed by **entry** date (as today), then kept only when PIT membership and the causal liquidity floor pass on the **signal** day (`universe_gate.eligible_trades`, WC5). The non-causal last-20-bars floor stays skipped for `_pit` runs (`_exclusion_reason`, unchanged).
- `run_backtest` receives `instrument=spec`. Its v2 refusals (`exit_model` must be `"v2"`, `tp2_mode` must be `"none"`, no live-state flag on) are checked **once, before the ticker loop**: inside the loop `main` catches every exception per `(strategy, horizon)` and prints it, so a refusal there would silently empty the table.
- `--scenarios` (scan replay, phase 5) and `--emit-registry` / `--from-json` (the registry has no `instrument_version` column until phase 6) refuse v2 through `cli.require_v1`.
- The report gains the watchlist slice of the same run, one row per strategy (`pass` / `fail` / `thin`, WC5's `watchlist_slice_verdict` over `pool()["n_eval"]` and `pool()["expectancy_r"]`), and the `--json` output gains a top-level `"_watchlist_slice"` key: `{strategy: {"status", "n", "expectancy_r"}}`. A verdict is per strategy, so the slice is too; `_watchlist_slice` itself scores whatever rows it is given (ledger signature).

Under v1 (the default) every path is today's: same windows (the WC7 aliases, via `cli.window_for`), `instrument=None` passed to `run_backtest` (`cli.run_instrument`), `member_trades` on the entry date, no report line or JSON key added.

**Complexity (index Global Constraints):** `main` measures F 65 on `main` at `b180c882`. Window selection moves into `_resolve_window` (removes the `if/elif/if-not ... and` chain, 4 decision points; adds one `try/except`), and every v2 behaviour lives in helpers that `main` calls unconditionally (`_instrument_guards`, `_windowed_trades`, `_instrument_report`), so `main` drops to about 62. `run_scenario_mode` (19) and `pool` (15) are not touched.

Contract (index ledger): `_resolve_window(args, spec) -> tuple[str, str, int, str]`; `_v2_window_trades(summary, date_from, date_to, spans, df, spec) -> list`; `_watchlist_slice(trade_rows, watchlist) -> tuple[str, dict]` (`trade_rows` = main's `[(ticker, strat, hk, trade)]`; returns the report text and `{status, n, expectancy_r}`). Private helpers added here and used only in this file: `_windowed_trades`, `_instrument_guards`, `_instrument_report`, `_V2_UNWIRED`. WC9 imports none of them (it imports only pre-existing helpers whose signatures are unchanged).

- [ ] **Step 1: Write the failing tests**

Create `$WT/tests/scripts/test_run_backtest_range_instrument.py`:

```python
"""v158 WC8: run_backtest_range.py --instrument v1|v2 (v136 rule 1: v1
byte-identical; rule 2: windows from the contract; section 1: PIT universe on
the signal date and the watchlist slice)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
for _sub in ("scripts/backtest", "scripts/data"):
    if str(ROOT / _sub) not in sys.path:
        sys.path.insert(0, str(ROOT / _sub))

import run_backtest_range as rbr  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting import backtest  # noqa: E402
from swingbot.core.backtesting.backtest import BacktestTrade  # noqa: E402
from swingbot.core.backtesting.instrument.cli import HOLDOUT_SEALED  # noqa: E402
from swingbot.core.backtesting.instrument.contract import resolve  # noqa: E402

V1, V2 = resolve("v1"), resolve("v2")
ALWAYS = [("2010-01-01", "9999-12-31")]


def _args(**over):
    base = dict(train=False, validation=False, date_from=None, date_to=None, universe=None,
                scenarios=False, emit_registry=None, from_json=None,
                exit_model="v2", tp2="none")
    base.update(over)
    return SimpleNamespace(**base)


def _trade(entry, r=1.0, outcome="win"):
    return BacktestTrade(entry_date=entry, exit_date=entry, direction="bullish", entry=50.0,
                         stop_loss=48.0, take_profit=54.0, outcome=outcome, exit_price=54.0,
                         return_pct=8.0, r_multiple=r, holding_days=3)


def _frame(volume=1_000_000, periods=400, start="2020-06-01"):
    index = pd.bdate_range(start, periods=periods)
    return pd.DataFrame({"Open": 50.0, "High": 50.0, "Low": 50.0, "Close": 50.0,
                         "Volume": volume}, index=index)


@pytest.fixture
def live_flags_off(monkeypatch):
    for name in backtest._LIVE_STATE_FLAGS:
        monkeypatch.setattr(config, name, False, raising=False)


# --- _resolve_window ------------------------------------------------------------

def test_v1_windows_are_todays():
    assert rbr._resolve_window(_args(train=True), V1) == (*rbr.TRAIN, 30, "TRAIN")
    assert rbr._resolve_window(_args(validation=True), V1) == (*rbr.VALIDATION, 15, "VALIDATION")
    assert rbr._resolve_window(_args(train=True), V1)[:2] == ("2020-01-01", "2023-12-31")


def test_v1_custom_window_is_unchecked_as_today():
    args = _args(date_from="2018-06-01", date_to="2019-01-01")
    assert rbr._resolve_window(args, V1) == ("2018-06-01", "2019-01-01", 15, "CUSTOM")


@pytest.mark.parametrize("over", [{}, {"date_from": "2021-01-01"}, {"date_to": "2021-12-31"}])
def test_a_missing_window_is_a_value_error_main_turns_into_ap_error(over):
    with pytest.raises(ValueError, match="need --train, --validation, or --from/--to"):
        rbr._resolve_window(_args(**over), V1)


def test_v2_train_is_the_research_span():
    assert rbr._resolve_window(_args(train=True), V2) == ("2010-01-01", "2025-12-31", 30, "TRAIN")


def test_v2_validation_is_sealed():
    with pytest.raises(SystemExit) as exc:
        rbr._resolve_window(_args(validation=True), V2)
    assert HOLDOUT_SEALED in str(exc.value)


def test_v2_custom_window_must_lie_inside_the_research_span():
    inside = _args(date_from="2014-01-01", date_to="2014-12-31")
    assert rbr._resolve_window(inside, V2) == ("2014-01-01", "2014-12-31", 15, "CUSTOM")
    with pytest.raises(SystemExit, match="research span"):
        rbr._resolve_window(_args(date_from="2025-01-01", date_to="2026-03-31"), V2)


# --- _instrument_guards ---------------------------------------------------------

def test_v1_guards_are_a_no_op():
    args = _args(scenarios=True, emit_registry="reg.json", from_json="x.json",
                 exit_model="v1", tp2="levels", universe="etfs")
    before = dict(vars(args))
    rbr._instrument_guards(args, V1)
    assert vars(args) == before


def test_v2_pins_the_contract_universe(live_flags_off):
    args = _args()
    rbr._instrument_guards(args, V2)
    assert args.universe == "sp500_pit"
    explicit = _args(universe="sp500_pit")
    rbr._instrument_guards(explicit, V2)
    assert explicit.universe == "sp500_pit"


def test_v2_refuses_a_different_universe(live_flags_off):
    with pytest.raises(SystemExit, match="sp500_pit"):
        rbr._instrument_guards(_args(universe="etfs"), V2)


@pytest.mark.parametrize("over, owner", [
    ({"scenarios": True}, "phase 5"),
    ({"emit_registry": "reg.json"}, "phase 6"),
    ({"from_json": "x.json"}, "phase 6"),
])
def test_v2_refuses_paths_a_later_phase_owns(live_flags_off, over, owner):
    with pytest.raises(SystemExit) as exc:
        rbr._instrument_guards(_args(**over), V2)
    assert owner in str(exc.value)
    assert "--instrument v2" in str(exc.value)


@pytest.mark.parametrize("over, message", [
    ({"exit_model": "v1"}, "needs exit_model='v2'"),
    ({"tp2": "levels"}, "tp2_mode='levels'"),
])
def test_v2_refuses_v1_exit_knobs_before_any_backtest(live_flags_off, over, message):
    with pytest.raises(SystemExit, match=message):
        rbr._instrument_guards(_args(**over), V2)


def test_v2_refuses_a_live_state_flag(monkeypatch, live_flags_off):
    monkeypatch.setattr(config, backtest._LIVE_STATE_FLAGS[0], True, raising=False)
    with pytest.raises(SystemExit, match="refuses lookahead"):
        rbr._instrument_guards(_args(), V2)


# --- _windowed_trades / _v2_window_trades ------------------------------------------

def _signal_trade(signal, entry):
    return SimpleNamespace(entry_date=entry, signal_date=signal, exit_date=entry,
                           outcome="win", r_multiple=1.0)


def test_v1_windowing_is_exactly_todays_expression():
    trades = [_trade("2019-12-31"), _trade("2020-01-02"), _trade("2022-06-01"),
              _trade("2024-01-02")]
    summary = SimpleNamespace(trades=trades)
    spans = [("2020-01-01", "2022-01-01")]
    for s in (None, spans, []):
        assert rbr._windowed_trades(summary, *rbr.TRAIN, s, _frame(), V1) == \
            rbr.member_trades(rbr.window_trades(summary, *rbr.TRAIN), s)


def test_v2_checks_membership_on_the_signal_day_v1_on_the_entry_day():
    spans = [("2021-01-01", "2021-03-01")]
    crosses_out = _signal_trade(signal="2021-02-26", entry="2021-03-01")
    summary = SimpleNamespace(trades=[crosses_out])
    df = _frame()
    assert rbr._v2_window_trades(summary, "2010-01-01", "2025-12-31", spans, df, V2) == [crosses_out]
    assert rbr._windowed_trades(summary, "2010-01-01", "2025-12-31", spans, df, V2) == [crosses_out]
    assert rbr._windowed_trades(summary, "2010-01-01", "2025-12-31", spans, df, V1) == []


def test_v2_applies_the_causal_floor_v1_does_not():
    summary = SimpleNamespace(trades=[_trade("2021-02-01")])
    thin = _frame(volume=1_000)                      # $50k a day
    assert rbr._windowed_trades(summary, *rbr.TRAIN, None, thin, V1) == summary.trades
    assert rbr._v2_window_trades(summary, "2010-01-01", "2025-12-31", ALWAYS, thin, V2) == []


def test_v2_windows_by_entry_date():
    summary = SimpleNamespace(trades=[_signal_trade(signal="2025-12-31", entry="2026-01-02")])
    df = _frame(periods=1600, start="2020-01-01")
    assert rbr._v2_window_trades(summary, "2010-01-01", "2025-12-31", ALWAYS, df, V2) == []


# --- _watchlist_slice ---------------------------------------------------------------

def _rows(ticker, n, r, outcome):
    return [(ticker, "RSI", "3m", _trade("2021-02-01", r=r, outcome=outcome)) for _ in range(n)]


def test_slice_scores_only_watchlist_rows_and_fails_on_negative_expectancy():
    rows = _rows("AAA", 30, -1.0, "loss") + _rows("BBB", 50, 2.0, "win")
    line, verdict = rbr._watchlist_slice(rows, ["AAA"])
    assert verdict == {"status": "fail", "n": 30, "expectancy_r": -1.0}
    assert "N=30" in line and "FAIL" in line


def test_slice_passes_at_or_above_zero():
    line, verdict = rbr._watchlist_slice(_rows("AAA", 30, 1.0, "win"), {"AAA"})
    assert verdict == {"status": "pass", "n": 30, "expectancy_r": 1.0}
    assert "PASS" in line


def test_slice_below_thirty_is_thin_and_an_empty_slice_too():
    _, few = rbr._watchlist_slice(_rows("AAA", 29, -1.0, "loss"), ["AAA"])
    assert few == {"status": "thin", "n": 29, "expectancy_r": -1.0}
    line, none = rbr._watchlist_slice(_rows("BBB", 40, -1.0, "loss"), ["AAA"])
    assert none == {"status": "thin", "n": 0, "expectancy_r": None}
    assert "ExpR=n/a" in line


# --- main, end to end on a stubbed engine -----------------------------------------------

@pytest.fixture
def harness(monkeypatch, tmp_path, live_flags_off):
    calls, seen, frame = [], {}, _frame()

    def fake_run_backtest(ticker, df, strat, hk, **kwargs):
        calls.append(dict(kwargs, ticker=ticker))
        return SimpleNamespace(trades=[_trade("2021-02-01"),
                                       _trade("2021-03-01", r=-1.0, outcome="loss")])

    def tickers(universe):
        seen["universe"] = universe
        return ["AAA", "BBB"]

    def membership(universe, symbols):
        return None if universe is None else {sym: ALWAYS for sym in symbols}

    monkeypatch.chdir(tmp_path)          # main writes backtest_range_summary.txt to cwd
    monkeypatch.setattr(rbr, "run_backtest", fake_run_backtest)
    monkeypatch.setattr(rbr, "_tickers_for_run", tickers)
    monkeypatch.setattr(rbr, "_membership_for_run", membership)
    monkeypatch.setattr(rbr, "load_cached", lambda ticker: frame)
    monkeypatch.setattr(rbr, "_with_context", lambda df, **kwargs: df)
    monkeypatch.setattr(rbr, "_exclusion_reason", lambda df, ticker, pit: None)
    monkeypatch.setattr(rbr, "load_watchlist", lambda: ["AAA"])
    monkeypatch.setattr(rbr, "LEGACY_HORIZONS", ("3m",))

    def run(*argv):
        out = tmp_path / "out.json"
        monkeypatch.setattr(sys, "argv", ["run_backtest_range.py", "--strategy", "RSI",
                                          "--context", "off", "--json", str(out), *argv])
        rbr.main()
        report = (tmp_path / "backtest_range_summary.txt").read_text(encoding="utf-8")
        return json.loads(out.read_text(encoding="utf-8")), report

    return SimpleNamespace(run=run, calls=calls, seen=seen)


V2_FLAGS = ("--instrument", "v2", "--exit-model", "v2", "--tp2", "none")


def test_v1_main_passes_instrument_none_and_adds_nothing(harness):
    payload, report = harness.run("--train")
    assert harness.seen["universe"] is None
    assert len(harness.calls) == 2
    assert all(call["instrument"] is None for call in harness.calls)
    assert list(payload) == ["RSI"]
    assert payload["RSI"]["n_eval"] == 4
    assert "== TRAIN 2020-01-01 .. 2023-12-31" in report
    assert "watchlist slice" not in report and "instrument" not in report


def test_explicit_v1_is_identical_to_the_default(harness):
    default = harness.run("--train")
    default_calls = list(harness.calls)
    harness.calls.clear()
    assert harness.run("--train", "--instrument", "v1") == default
    assert harness.calls == default_calls


def test_v2_main_runs_the_research_span_on_the_pit_universe_with_a_slice(harness):
    payload, report = harness.run("--train", *V2_FLAGS)
    assert harness.seen["universe"] == "sp500_pit"
    assert len(harness.calls) == 2
    assert all(call["instrument"] is resolve("v2") for call in harness.calls)
    assert all(call["exit_model"] == "v2" and call["tp2_mode"] == "none"
               for call in harness.calls)
    assert payload["RSI"]["n_eval"] == 4
    assert payload["_watchlist_slice"] == {"RSI": {"status": "thin", "n": 2, "expectancy_r": 0.0}}
    assert "== TRAIN 2010-01-01 .. 2025-12-31" in report
    assert "instrument v2: universe sp500_pit" in report
    assert "THIN" in report


def test_v2_validation_exits_before_any_backtest(harness):
    with pytest.raises(SystemExit) as exc:
        harness.run("--validation", *V2_FLAGS)
    assert HOLDOUT_SEALED in str(exc.value)
    assert harness.calls == []


def test_v2_with_the_default_tp2_exits_before_any_backtest(harness):
    with pytest.raises(SystemExit, match="tp2_mode='levels'"):
        harness.run("--train", "--instrument", "v2", "--exit-model", "v2")
    assert harness.calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_run_backtest_range_instrument.py`
Expected: FAIL, `AttributeError: module 'run_backtest_range' has no attribute '_resolve_window'` (and the other new helpers); the `main` tests fail with `unrecognized arguments: --instrument` or on the missing JSON key.

- [ ] **Step 3: Implement**

In `$WT/scripts/backtest/run_backtest_range.py`:

1. Module docstring: after the line `    python scripts/backtest/run_backtest_range.py --from 2022-01-01 --to 2022-12-31 --strategy "RSI"`, insert:

```text
    python scripts/backtest/run_backtest_range.py --train --instrument v2 --exit-model v2 --tp2 none
        # instrument v2 (v158): the contract's research span on its point-in-time
        # universe, membership and a causal liquidity floor checked on the signal
        # day, plus the watchlist slice; --validation is the sealed holdout and exits
```

2. Imports. Replace `from swingbot.core.backtesting.backtest import ALL_STRATEGIES, run_backtest` with:

```python
from swingbot.core.backtesting.backtest import ALL_STRATEGIES, _uses_live_constructor, run_backtest
```

and add directly after the `from swingbot.core.backtesting.instrument.contract import resolve as resolve_instrument` line (WC7):

```python
from swingbot.core.backtesting.instrument import cli as instrument_cli
from swingbot.core.backtesting.instrument import universe_gate
```

3. Insert after `member_trades` (before the `# Hard gates on the registry emit path.` comment block):

```python
def _v2_window_trades(summary, date_from, date_to, spans, df, spec) -> list:
    """v2: the entry-date window, then PIT membership and the causal liquidity
    floor checked on each trade's SIGNAL day (universe_gate, v136 section 1)."""
    return universe_gate.eligible_trades(window_trades(summary, date_from, date_to),
                                         spans, df, spec.liquidity_floor)


def _windowed_trades(summary, date_from, date_to, spans, df, spec) -> list:
    """The trades a run keeps for one (ticker, strategy, horizon). v1 is exactly
    today's entry-date mask (rule 1); v2 goes through the signal-day gate."""
    if spec.version == "v1":
        return member_trades(window_trades(summary, date_from, date_to), spans)
    return _v2_window_trades(summary, date_from, date_to, spans, df, spec)


def _resolve_window(args, spec) -> tuple[str, str, int, str]:
    """(date_from, date_to, min_n, label), windows from the instrument contract.
    v1: today's --train/--validation/--from-to exactly. v2: --train is the
    research span, --validation is the sealed holdout (exits), and --from/--to
    must lie inside the research span. ValueError when no window is given."""
    if args.train:
        return (*instrument_cli.window_for(spec, "train"), 30, "TRAIN")
    if args.validation:
        return (*instrument_cli.window_for(spec, "validation"), 15, "VALIDATION")
    if not (args.date_from and args.date_to):
        raise ValueError("need --train, --validation, or --from/--to")
    instrument_cli.check_inside_research(spec, args.date_from, args.date_to)
    return args.date_from, args.date_to, 15, "CUSTOM"


# (args attribute, what to name, the phase that wires it under v2)
_V2_UNWIRED = (
    ("scenarios", "run_backtest_range.py --scenarios", "phase 5 (scan replay under v2)"),
    ("emit_registry", "run_backtest_range.py --emit-registry",
     "phase 6 (registry instrument_version column)"),
    ("from_json", "run_backtest_range.py --from-json",
     "phase 6 (registry instrument_version column)"),
)


def _instrument_guards(args, spec) -> None:
    """Under v2: refuse the paths a later phase owns, pin the contract's
    universe, and check run_backtest's v2 refusals ONCE, before the ticker
    loop (inside it main catches every exception per run, so a refusal there
    would silently empty the table). Under v1: no-op."""
    if spec.version == "v1":
        return
    for attr, script, owner in _V2_UNWIRED:
        if getattr(args, attr):
            instrument_cli.require_v1(spec, script, owner)
    if args.universe not in (None, spec.universe):
        raise SystemExit(f"--instrument {spec.version} runs on the contract's universe "
                         f"{spec.universe!r}; got --universe {args.universe!r}")
    args.universe = spec.universe
    tp2_mode = args.tp2 if args.exit_model == "v2" else "none"
    try:
        _uses_live_constructor(spec, args.exit_model, tp2_mode)
    except ValueError as exc:
        raise SystemExit(f"--instrument {spec.version}: {exc}") from None


def _watchlist_slice(trade_rows, watchlist) -> tuple[str, dict]:
    """The watchlist slice of a run's rows (v136 section 1): the report text and
    {status, n, expectancy_r}. `trade_rows` are main's (ticker, strategy, hk,
    trade) tuples; N is pool()'s n_eval, the N every gate here uses."""
    members = set(watchlist)
    stats = pool([trade for ticker, _strat, _hk, trade in trade_rows if ticker in members])
    verdict = universe_gate.watchlist_slice_verdict(stats["n_eval"], stats["expectancy_r"])
    exp_r = "n/a" if verdict.expectancy_r is None else f"{verdict.expectancy_r:+.3f}"
    line = f"N={verdict.n} ExpR={exp_r} -> {verdict.status.upper()}"
    return line, {"status": verdict.status, "n": verdict.n, "expectancy_r": verdict.expectancy_r}


def _instrument_report(spec, trade_rows, strategies) -> tuple[list[str], dict]:
    """Report lines and JSON keys a v2 run adds: the instrument line and the
    per-strategy watchlist slice. v1 adds nothing (byte-identical output)."""
    if spec.version == "v1":
        return [], {}
    watchlist = sorted(load_watchlist())
    lines = ["",
             f"-- instrument {spec.version}: universe {spec.universe}; PIT membership and the "
             f"causal liquidity floor checked on the signal day --",
             f"-- watchlist slice (same run, {len(watchlist)} watchlist tickers): FAIL here "
             f"fails the strategy's verdict whatever PASS says; ExpR < 0 with "
             f"N >= {universe_gate.WATCHLIST_SLICE_MIN_N} fails, fewer is THIN --"]
    slices = {}
    for strat in strategies:
        rows = [row for row in trade_rows if row[1] == strat]
        line, slices[strat] = _watchlist_slice(rows, watchlist)
        lines.append(f"{strat:22s} {line}")
    return lines, {"_watchlist_slice": slices}
```

4. In `main`:

a. After the `--from-json` `ap.add_argument(...)` call and before `args = ap.parse_args()`, add:

```python
    instrument_cli.add_instrument_arg(ap)
```

b. Replace the whole window block

```python
    if args.train:
        date_from, date_to, min_n, label = *TRAIN, 30, "TRAIN"
    elif args.validation:
        date_from, date_to, min_n, label = *VALIDATION, 15, "VALIDATION"
    else:
        if not (args.date_from and args.date_to):
            ap.error("need --train, --validation, or --from/--to")
        date_from, date_to, min_n, label = args.date_from, args.date_to, 15, "CUSTOM"
```

with

```python
    spec = instrument_cli.spec_from_args(args)
    _instrument_guards(args, spec)
    try:
        date_from, date_to, min_n, label = _resolve_window(args, spec)
    except ValueError as exc:
        ap.error(str(exc))
```

(The `if args.emit_registry and not args.run_date:` check stays above it, unchanged.)

c. In the ticker loop, change the `run_backtest(...)` call to pass the instrument as its last keyword:

```python
                    s = run_backtest(ticker, df, strat, hk, one_at_a_time=True,
                                      exit_model=args.exit_model, scale_out=args.scale_out,
                                      tp2_mode=tp2_mode, frictions=(args.frictions == "on"),
                                      asof=asof_map.get(ticker),
                                      instrument=instrument_cli.run_instrument(spec))
```

and replace

```python
                tr = member_trades(window_trades(s, date_from, date_to), spans)
```

with

```python
                tr = _windowed_trades(s, date_from, date_to, spans, df, spec)
```

d. Directly before `report = "\n".join(lines)`, insert:

```python
    instrument_lines, instrument_json = _instrument_report(spec, trade_rows, strategies)
    lines.extend(instrument_lines)
```

e. Replace the `--json` write

```python
        Path(args.json_out).write_text(json.dumps(
            {k: {kk: vv for kk, vv in v.items()} for k, v in results.items()}, indent=2))
```

with

```python
        Path(args.json_out).write_text(json.dumps(
            {**{k: {kk: vv for kk, vv in v.items()} for k, v in results.items()},
             **instrument_json}, indent=2))
```

(Under v1 `instrument_json` is `{}`, so the dumped text is byte-identical.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_run_backtest_range_instrument.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity: `main` went down, the new helpers are small**

Run: `python -m radon cc -s -n C $WT/scripts/backtest/run_backtest_range.py`
Expected: exactly three lines, `main` (F, a score **below 65**; about 62), `run_scenario_mode` (C 19) and `pool` (C 15). None of `_resolve_window`, `_instrument_guards`, `_windowed_trades`, `_v2_window_trades`, `_watchlist_slice`, `_instrument_report` appears. If `main` is at or above 65, stop: a branch was inlined into `main` instead of a helper.

- [ ] **Step 6: Every existing consumer of the script still passes**

Run each:

```bash
python $WT/scripts/dev/testrun.py file tests/scripts/test_range_trades_jsonl.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_alert_density.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_emit_registry.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_quarterly_revalidation.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_measure_bearish_arms.py
python $WT/scripts/dev/testrun.py file tests/scripts/test_measure_arms.py
python $WT/scripts/dev/testrun.py file tests/backtesting/test_backtest_engine.py
python $WT/scripts/dev/testrun.py file tests/backtesting/instrument/
```

Expected: every run PASS, `0 failed`, `0 xfailed` (the golden test in `tests/backtesting/instrument/` is untouched by this task and stays green).

Smoke the flag without a cache (none exists on the dev machine):

```bash
python $WT/scripts/backtest/run_backtest_range.py --help | grep -A1 -- "--instrument"
python $WT/scripts/backtest/run_backtest_range.py --validation --instrument v2 --exit-model v2 --tp2 none; echo "exit=$?"
```

Expected: the help shows `--instrument {v1,v2}`; the second command prints the `HOLDOUT_SEALED` message (holdout starts 2026-01-01) and `exit=1`, before any ticker is loaded. (If this machine's `.env` turns on one of `backtest._LIVE_STATE_FLAGS`, the pre-flight refusal naming that flag prints instead, still with `exit=1` and no ticker loaded; both are correct v2 refusals.)

- [ ] **Step 7: Commit**

```bash
git -C $WT add scripts/backtest/run_backtest_range.py tests/scripts/test_run_backtest_range_instrument.py
git -C $WT commit -m "feat(backtest): v158 WC8 run_backtest_range --instrument v1|v2 with the signal-day PIT gate and watchlist slice"
git -C /home/user/Discord-Bot status --short
```

