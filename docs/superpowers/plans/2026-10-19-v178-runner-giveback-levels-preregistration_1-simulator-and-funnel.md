# v178 — Runner give-back levels: Implementation Plan, part 1 (simulator and funnel)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time: `grep -n "^### Task V178-2:" -A 400 <this file>`.

**Spec:** [2026-10-19-v178-runner-giveback-levels-preregistration-design.md](../specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md)
**Index:** [2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md](2026-10-19-v178-runner-giveback-levels-preregistration_0-index.md) — Goal, Architecture, `## Global Constraints`, the row / funnel / blocks / simulator contracts, `## Parallelisation` and the task ledger live there and bind every task below.

**Tasks in this part:** V178-1 (adaptive modes in the v1 walk), V178-2 (v2 walk parity and the pinned witnesses), V178-3 (funnel logic). V178-4 (descriptive blocks) is in part 1b.

**Where to work:** every task here runs in the worktree
`.claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration`
(branch `2026-10-19-v178-runner-giveback-levels-preregistration`, created in
V178-1 Step 1). All paths below are relative to that worktree's root; run every
command from it (absolute path, never `cd` in a Bash call that also runs a
hook-checked command). Commits go on the worktree branch, one scoped commit per
task.

# Phase 1 — Simulator

### Task V178-1: Adaptive give-back modes in the v1 walk

**Model:** opus — changes the shared exit simulator that live behaviour and every backtest read (lookahead and byte-identity at stake)

**Files:**
- Modify: `swingbot/core/planning/exit_sim.py` (imports `:7-9`; new block after `giveback_level` `:265-269`; `_runner_bar_exit` `:466-480`; new helpers after `_stop_source` `:523-528`; `_runner_phase` `:537-580`)
- Create: `tests/planning/test_giveback_levels.py` (suite `planning`; existing directory, no `tests/suites.toml` edit)

**Interfaces:**
- Consumes: `giveback_level(extreme, direction)` `exit_sim.py:265`, `runner_giveback_pct()` `:258`, `tighter_stop(stop, other, is_bull)` `:272`, `runner_stop_source(stop, floor, giveback)` `:279`, `_giveback_extreme(ctx, j, extreme)` `:502`, `_scale_out_exit_walk(df, entry_index, entry_price, plan, max_holding_days, *, trace=None)` `:~606`, `atr` (`swingbot/core/market/indicators.py:62`, Wilder, `min_periods=14`). All exist today.
- Produces (simulator contract in the index; V178-2 and V178-5 import these exact names):
  - `GIVEBACK_MODES: tuple[str, ...] = ("pct", "range", "profit_share")`, `GIVEBACK_MODE: str = "pct"`, `GIVEBACK_K: float = 1.0`, `GIVEBACK_F: float = 0.33`, `GIVEBACK_FLOOR_ATR: float = 1.0`, `GIVEBACK_K_BOUNDS = (0.25, 3.0)`, `GIVEBACK_F_BOUNDS = (0.05, 0.95)`
  - `giveback_allowance(mode: str, extreme: float, entry: float, atr: float | None, *, k: float, f: float) -> float | None`
  - `giveback_term(extreme: float | None, entry: float, atr: float | None, direction: str) -> float | None`
  - `_giveback_term(ctx, j: int, extreme: float | None, atr_series) -> float | None`
  - `_carried_level(runner_stop: float, level: float | None, carried: float | None) -> float | None`
  - `_runner_bar_exit(ctx, j, runner_stop, floor, gb_level=None)`: the 5th argument is now the carried level, passed straight to `runner_stop_source`.
- Leaves in place for V178-2: `_giveback_ratchet` and `_stop_source` (still imported by `exit_sim_v2.py:25`; V178-2 deletes them). `giveback_level` and `runner_giveback_pct` keep their signatures and results (live calls them).

**Why the carried level.** Today `_runner_bar_exit` re-derives the give-back level from the extreme through bar `j − 1` and labels the stop "giveback" when the two are equal. With ATR in the level, a level set on an earlier bar survives (never widens) while a recomputation from a later, larger ATR is looser, so the stop would be mislabelled "trail" (spec § The rules, last bullet; risk-manager 6). The loop therefore carries the level that last set the stop. In `pct` mode the level only tightens with its extreme, so the carried level equals the old recomputation exactly and every existing attribution is unchanged.

- [ ] **Step 1: Create the worktree** (from the main tree; this is the plan's first code task)

```bash
git -C "E:/Documents/Private/Projects/Discord-Bot" worktree add .claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration -b 2026-10-19-v178-runner-giveback-levels-preregistration main
git -C "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-19-v178-runner-giveback-levels-preregistration" log --oneline -1
```

Expected: the worktree exists and its HEAD is `main`'s HEAD. Every later step runs from the worktree root.

- [ ] **Step 2: Write the failing tests** — create `tests/planning/test_giveback_levels.py`:

```python
"""v178 V178-1: adaptive give-back levels (range multiple, profit share) in the v1 walk.

Frames: 15 flat warm-up bars (open 100, high 101.5, low 98.5, close 100; true
range 3.0) so ATR(14) exists from bar 13; the market entry fills at bar 14's
close (100). Stop 95, TP1 110 (tp1_fraction 0.5), runner floor 106.6667;
trail_atr_mult=50 parks the chandelier, so only the floor and the give-back
can bind. ATR(14) (Wilder) after bar 16 is 4.1352, after bar 17 4.3755.

REVERSE
  bar 15 (100, 111, 99.5, 110.5)   TP1 touched
  bar 16 (110.5, 121, 110, 120)    best close 120; sets the level for bar 17
                                   from ATR after bar 16
  bar 17 (120, 120.5, 113, 113.5)  low 113: R k 0.75/1.0/1.25 (116.90 / 115.86 /
                                   114.83), S 0.25 (115.0), S 0.33 (113.4) exit here
  bar 18 (113.5, 114, 106, 106.5)  S 0.50 (110.0) exits here; the floor too
JUMP: bars 15-16 as REVERSE, then
  bar 17 (120, 124, 116.5, 119)    no new best close; true range 7.5 lifts ATR,
                                   so the k = 1.0 level recomputed after bar 17
                                   (115.62) is looser and the stop stays 115.865
  bar 18 (119, 119.5, 112, 112.5)  low 112: out at the bar-16 level, "giveback"
  bar 19 (112.5, 113, 106, 106.5)
Bar 16's own low (110) is below every level its close sets: exit_index 17, not
16, is the no-lookahead check. The bearish frames mirror every bar around 100.
"""
import math
import pathlib

import pytest

from swingbot import config
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim import (GIVEBACK_F_BOUNDS, GIVEBACK_K_BOUNDS,
                                             GIVEBACK_MODES, _carried_level,
                                             _scale_out_exit_walk, giveback_allowance,
                                             giveback_level, giveback_term)
from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
ENTRY = 14
WARM = [(100.0, 101.5, 98.5, 100.0)] * 15
RUN = [(100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0)]
REVERSE = WARM + RUN + [(120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
JUMP = WARM + RUN + [(120.0, 124.0, 116.5, 119.0), (119.0, 119.5, 112.0, 112.5),
                     (112.5, 113.0, 106.0, 106.5)]
# test_exit_sim_giveback.BULL_BARS: five bars, so ATR(14) is NaN on every bar.
NAN_ATR_BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
                (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
ARMS = [("pct", 1.0, 0.33), ("range", 0.75, 0.33), ("range", 1.0, 0.33),
        ("range", 1.25, 0.33), ("profit_share", 1.0, 0.25),
        ("profit_share", 1.0, 0.33), ("profit_share", 1.0, 0.50)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Give-back on, pct mode at 5%; every other runner rule that could bind off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", "pct")
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", 1.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", 0.33)


def _arm(monkeypatch, mode, k=1.0, f=0.33):
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", mode)
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", k)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", f)


def _mirror(bars):
    return [(200.0 - o, 200.0 - lo, 200.0 - hi, 200.0 - c) for o, hi, lo, c in bars]


def _bull(**kw):
    base = dict(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _run(bars, plan, entry=ENTRY):
    return simulate_exit(make_ohlcv(bars), entry, plan, scale_out=True, max_holding_days=10)


def _trace(bars, plan):
    trace = []
    _scale_out_exit_walk(make_ohlcv(bars), ENTRY, 100.0, plan, 10, trace=trace)
    return trace


def _atr_after(bars, j):
    return float(atr_indicator(make_ohlcv(bars), 14).iloc[j])


# --- the pure level ------------------------------------------------------------

def test_module_defaults_keep_the_live_rule():
    src = pathlib.Path(exit_sim.__file__).read_text(encoding="utf-8")
    assert 'GIVEBACK_MODE: str = "pct"' in src
    assert "GIVEBACK_K: float = 1.0" in src
    assert "GIVEBACK_F: float = 0.33" in src
    assert GIVEBACK_MODES == ("pct", "range", "profit_share")
    assert exit_sim.GIVEBACK_FLOOR_ATR == 1.0
    assert GIVEBACK_K_BOUNDS == (0.25, 3.0) and GIVEBACK_F_BOUNDS == (0.05, 0.95)


@pytest.mark.parametrize("mode, k, f, expected", [
    ("range", 0.75, 0.33, 53.063),           # 49.94 + 0.75 x 4.164
    ("range", 1.0, 0.33, 54.104),
    ("range", 1.25, 0.33, 55.145),
    ("profit_share", 1.0, 0.25, 54.104),     # 0.25 x 10.73 = 2.68 < ATR: the floor binds
    ("profit_share", 1.0, 0.33, 54.104),     # 3.54 < 4.164: the floor binds
    ("profit_share", 1.0, 0.50, 55.305),     # 5.365 > ATR
])
def test_rklb_short_worked_example(monkeypatch, mode, k, f, expected):
    _arm(monkeypatch, mode, k, f)
    assert giveback_term(49.94, 60.67, 4.164, "bearish") == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("mode, k, f, expected", [
    ("pct", 1.0, 0.33, 106.40),
    ("range", 0.75, 0.33, 110.875),
    ("range", 1.0, 0.33, 110.50),
    ("range", 1.25, 0.33, 110.125),
    ("profit_share", 1.0, 0.25, 109.00),
    ("profit_share", 1.0, 0.33, 108.04),
    ("profit_share", 1.0, 0.50, 106.00),
])
def test_calm_long_worked_example(monkeypatch, mode, k, f, expected):
    _arm(monkeypatch, mode, k, f)
    assert giveback_term(112.0, 100.0, 1.5, "bullish") == pytest.approx(expected, abs=1e-9)


def test_pct_mode_is_the_live_level_exactly():
    for extreme, direction in ((120.0, "bullish"), (80.0, "bearish"), (49.94, "bearish")):
        assert giveback_term(extreme, 100.0, 4.0, direction) == giveback_level(extreme, direction)


def test_allowance_per_mode():
    assert giveback_allowance("pct", 112.0, 100.0, None, k=1.0, f=0.33) == pytest.approx(5.6)
    assert giveback_allowance("range", 112.0, 100.0, 1.5, k=1.0, f=0.33) == 1.5
    assert giveback_allowance("profit_share", 112.0, 100.0, 1.5, k=1.0, f=0.5) == 6.0
    # best price at entry: zero profit, so the 1.0 x ATR floor is the allowance
    assert giveback_allowance("profit_share", 100.0, 100.0, 2.0, k=1.0, f=0.5) == 2.0


@pytest.mark.parametrize("mode", ["range", "profit_share"])
@pytest.mark.parametrize("atr", [None, math.nan, 0.0, -1.0, math.inf])
def test_unusable_atr_yields_no_term_never_a_substitute(monkeypatch, mode, atr):
    _arm(monkeypatch, mode, 1.0, 0.33)
    assert giveback_allowance(mode, 120.0, 100.0, atr, k=1.0, f=0.33) is None
    assert giveback_term(120.0, 100.0, atr, "bullish") is None


@pytest.mark.parametrize("mode", list(GIVEBACK_MODES))
def test_flag_off_or_no_extreme_is_no_term(monkeypatch, mode):
    _arm(monkeypatch, mode)
    assert giveback_term(None, 100.0, 4.0, "bullish") is None
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)    # control B
    assert giveback_term(120.0, 100.0, 4.0, "bullish") is None


def test_parameter_bounds_are_inclusive_and_enforced():
    assert giveback_allowance("range", 120.0, 100.0, 4.0, k=0.25, f=0.33) == 1.0
    assert giveback_allowance("range", 120.0, 100.0, 4.0, k=3.0, f=0.33) == 12.0
    assert giveback_allowance("profit_share", 120.0, 100.0, 1.0, k=1.0, f=0.95) == 19.0
    for k in (0.2, 3.5):
        with pytest.raises(ValueError, match="GIVEBACK_K"):
            giveback_allowance("range", 120.0, 100.0, 4.0, k=k, f=0.33)
    for f in (0.01, 0.99):
        with pytest.raises(ValueError, match="GIVEBACK_F"):
            giveback_allowance("profit_share", 120.0, 100.0, 4.0, k=1.0, f=f)
    with pytest.raises(ValueError, match="GIVEBACK_K"):          # bounds before ATR
        giveback_allowance("range", 120.0, 100.0, math.nan, k=9.0, f=0.33)


def test_an_unknown_mode_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="GIVEBACK_MODE"):
        giveback_allowance("atr", 120.0, 100.0, 4.0, k=1.0, f=0.33)
    _arm(monkeypatch, "atr")
    with pytest.raises(ValueError, match="GIVEBACK_MODE"):
        giveback_term(120.0, 100.0, 4.0, "bullish")


def test_carried_level_tracks_the_level_that_set_the_stop():
    assert _carried_level(115.0, 115.0, None) == 115.0        # this bar's level set it
    assert _carried_level(116.0, 115.0, 114.0) == 114.0       # it did not: keep the old one
    assert _carried_level(116.0, None, 114.0) == 114.0        # no term this bar
    assert _carried_level(106.0, None, None) is None


# --- the v1 walk ---------------------------------------------------------------

def test_pct_mode_walk_is_the_v176_exit():
    res = _run(REVERSE, _bull())
    assert (res.exit_index, res.runner_stop_source) == (17, "giveback")
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(120.0, 5.0, "bullish")


@pytest.mark.parametrize("k, hand", [(0.75, 116.899), (1.0, 115.865), (1.25, 114.831)])
def test_range_arm_exits_at_best_minus_k_atr_the_next_bar(monkeypatch, k, hand):
    _arm(monkeypatch, "range", k=k)
    res = _run(REVERSE, _bull())
    assert res.outcome == "win"
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 17                      # bar 16 sets it, bar 17 tests it
    level = 120.0 - k * _atr_after(REVERSE, 16)
    assert res.legs[1]["exit_price"] == pytest.approx(level)
    assert res.legs[1]["exit_price"] == pytest.approx(hand, abs=1e-3)
    assert set(res.legs[1]) == {"fraction", "exit_price", "r", "reason"}


@pytest.mark.parametrize("f, exit_index, price", [(0.25, 17, 115.0), (0.33, 17, 113.4),
                                                  (0.50, 18, 110.0)])
def test_profit_share_arm_exits_at_its_share_of_the_profit(monkeypatch, f, exit_index, price):
    _arm(monkeypatch, "profit_share", f=f)
    res = _run(REVERSE, _bull())
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == exit_index
    assert res.legs[1]["exit_price"] == pytest.approx(price)


@pytest.mark.parametrize("mode, k, f, exit_index, price", [
    ("range", 1.0, 0.33, 17, None),                  # 80 + ATR after bar 16
    ("profit_share", 1.0, 0.50, 18, 90.0),
])
def test_bearish_mirror(monkeypatch, mode, k, f, exit_index, price):
    _arm(monkeypatch, mode, k, f)
    bars = _mirror(REVERSE)
    res = _run(bars, _bear())
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == exit_index
    expected = price if price is not None else 80.0 + _atr_after(bars, 16)
    assert res.legs[1]["exit_price"] == pytest.approx(expected)


@pytest.mark.parametrize("k", [1.0, 1.25])
def test_atr_jump_leaves_the_stop_and_its_source_unchanged(monkeypatch, k):
    """Spec test (a) and stop attribution: no new extreme on bar 17 and a larger
    ATR -- the stop set on bar 16 stays, and still fires as "giveback"."""
    _arm(monkeypatch, "range", k=k)
    level = 120.0 - k * _atr_after(JUMP, 16)
    trace = _trace(JUMP, _bull())
    assert [j for j, _ in trace] == [16, 17]
    assert trace[0][1] == pytest.approx(level) and trace[1][1] == trace[0][1]
    res = _run(JUMP, _bull())
    assert res.exit_index == 18
    assert res.runner_stop_source == "giveback"      # recomputing from bar 17 would say "trail"
    assert res.legs[1]["exit_price"] == pytest.approx(level)


@pytest.mark.parametrize("mode, k, f", ARMS)
@pytest.mark.parametrize("bull", [True, False])
def test_the_runner_stop_only_moves_toward_price(monkeypatch, mode, k, f, bull):
    """Spec test (b): every arm's stop series is monotone toward price."""
    _arm(monkeypatch, mode, k, f)
    bars, plan = (JUMP, _bull()) if bull else (_mirror(JUMP), _bear())
    stops = [stop for _, stop in _trace(bars, plan)]
    assert stops, "the runner must survive at least one bar"
    pairs = list(zip(stops, stops[1:]))
    assert all((b >= a) if bull else (b <= a) for a, b in pairs)


@pytest.mark.parametrize("mode", ["range", "profit_share"])
def test_no_atr_means_no_term_so_the_runner_rides_to_the_floor(monkeypatch, mode):
    """Spec test (c) in the walk: a NaN ATR gives no term (pct still fires)."""
    _arm(monkeypatch, mode)
    res = _run(NAN_ATR_BARS, _bull(), entry=0)
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 4)
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)
    _arm(monkeypatch, "pct")
    assert _run(NAN_ATR_BARS, _bull(), entry=0).exit_index == 3


def test_an_allowance_beyond_the_profit_exits_at_the_floor(monkeypatch):
    """Floor clamp: f = 0.95 puts the level at 120 - 19 = 101, below the floor."""
    _arm(monkeypatch, "profit_share", f=0.95)
    res = _run(REVERSE, _bull())
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 18)
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)
    assert res.legs[1]["r"] > 0                      # never on the loss side of entry


@pytest.mark.parametrize("mode", list(GIVEBACK_MODES))
def test_control_b_is_flag_off_in_every_mode(monkeypatch, mode):
    _arm(monkeypatch, mode)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    res = _run(REVERSE, _bull())
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 18)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_giveback_levels.py`
Expected: FAIL — collection error, `ImportError: cannot import name 'GIVEBACK_F_BOUNDS' from 'swingbot.core.planning.exit_sim'`.

- [ ] **Step 4: Add the modes and the pure level** — in `swingbot/core/planning/exit_sim.py`.

At the imports (`:7-9`), add `import math`:

```python
from __future__ import annotations

import math
from dataclasses import dataclass
```

Directly after `giveback_level` (ends `:269`, before `def tighter_stop`), insert:

```python
#: v178: simulator-only give-back modes. "pct" is the live v176 rule and the
#: default; "range" (k x ATR) and "profit_share" (max(f x profit, 1.0 x ATR))
#: are the pre-registered arms. Module constants, never config: plan_manager
#: calls giveback_level(), so a mode read from config there would change live
#: behaviour on a SIGHUP. The v178 measurement script assigns them per arm
#: (and in its pool workers' initializer).
GIVEBACK_MODES: tuple[str, ...] = ("pct", "range", "profit_share")
GIVEBACK_MODE: str = "pct"
GIVEBACK_K: float = 1.0
GIVEBACK_F: float = 0.33
GIVEBACK_FLOOR_ATR: float = 1.0
GIVEBACK_K_BOUNDS = (0.25, 3.0)
GIVEBACK_F_BOUNDS = (0.05, 0.95)


def _check_giveback_mode(mode: str) -> None:
    if mode not in GIVEBACK_MODES:
        raise ValueError(f"GIVEBACK_MODE must be one of {GIVEBACK_MODES}, got {mode!r}")


def _check_giveback_bound(name: str, value: float, bounds: tuple[float, float]) -> None:
    low, high = bounds
    if not low <= value <= high:
        raise ValueError(f"{name} must lie in [{low}, {high}], got {value!r}")


def _usable_atr(atr: float | None) -> bool:
    """A real, finite, positive ATR. Anything else means no adaptive term --
    never _safe_atr_value's 2%-of-entry stand-in, which would be a term."""
    return atr is not None and math.isfinite(atr) and atr > 0


def giveback_allowance(mode: str, extreme: float, entry: float, atr: float | None,
                       *, k: float, f: float) -> float | None:
    """v178: the distance from the best price to the give-back level.

    pct: RUNNER_GIVEBACK_PCT of the best price (descriptive only -- the pct
    walk itself goes through giveback_level). range: ``k x ATR``.
    profit_share: ``max(f x |best - entry|, GIVEBACK_FLOOR_ATR x ATR)``.
    The parameter bounds are checked first; then an adaptive mode with no
    usable ATR (missing, NaN, infinite, zero, negative) returns None."""
    _check_giveback_mode(mode)
    if mode == "pct":
        return abs(float(extreme)) * runner_giveback_pct() / 100.0
    if mode == "range":
        _check_giveback_bound("GIVEBACK_K", k, GIVEBACK_K_BOUNDS)
    else:
        _check_giveback_bound("GIVEBACK_F", f, GIVEBACK_F_BOUNDS)
    if not _usable_atr(atr):
        return None
    if mode == "range":
        return k * float(atr)
    return max(f * abs(float(extreme) - float(entry)), GIVEBACK_FLOOR_ATR * float(atr))


def giveback_term(extreme: float | None, entry: float, atr: float | None,
                  direction: str) -> float | None:
    """v178: the give-back term under GIVEBACK_MODE, read at call time.

    pct returns giveback_level() itself -- the live v176 rule, byte-identical.
    range / profit_share return ``best - allowance`` (long) or ``best +
    allowance`` (short). None with the flag off (control B), before the first
    extreme, or with no usable ATR: a missing term never loosens a stop."""
    _check_giveback_mode(GIVEBACK_MODE)
    if GIVEBACK_MODE == "pct":
        return giveback_level(extreme, direction)
    if extreme is None or not config.RUNNER_GIVEBACK_ENABLED:
        return None
    best = float(extreme)
    allowance = giveback_allowance(GIVEBACK_MODE, best, entry, atr,
                                   k=GIVEBACK_K, f=GIVEBACK_F)
    if allowance is None:
        return None
    return best - allowance if direction == "bullish" else best + allowance
```

- [ ] **Step 5: Carry the level through the v1 walk** — still in `exit_sim.py`.

Replace `_runner_bar_exit` (`:466-480`) with:

```python
def _runner_bar_exit(ctx, j, runner_stop, floor, gb_level=None):
    """Runner stop first, then TP2; the stop checked is the one set BEFORE bar j.
    (price, index, reason, stop_source); stop_source is None for TP2.
    v178: ``gb_level`` is the give-back level that set ``runner_stop``,
    carried by the loop (_carried_level), not recomputed here."""
    hi, lo = float(ctx.high[j]), float(ctx.low[j])
    if (lo <= runner_stop) if ctx.is_bull else (hi >= runner_stop):
        # v39: "runner_be" means "closed at its initial post-TP1 floor"; the
        # string is deliberately unchanged (~30 files pattern-match it).
        # v176: a give-back close is still "runner_trail"; the term that
        # fired rides on ExitResult.runner_stop_source instead.
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return runner_stop, j, reason, runner_stop_source(runner_stop, floor, gb_level)
    tp2 = ctx.plan.tp2
    if tp2 is not None and ((hi >= tp2) if ctx.is_bull else (lo <= tp2)):
        return tp2, j, "runner_tp2", None
    return None
```

Directly after `_stop_source` (ends `:528`, before `def _runner_timeout`), insert:

```python
def _giveback_term(ctx, j: int, extreme: float | None, atr_series) -> float | None:
    """v178: the give-back level for bar j + 1, from the extreme through bar j
    and ATR(14) through bar j -- the index _chandelier_ratchet reads, so the
    tested bar's own range never enters its level (no lookahead)."""
    return giveback_term(extreme, ctx.entry_price, float(atr_series.iloc[j]),
                         ctx.plan.direction)


def _carried_level(runner_stop: float, level: float | None,
                   carried: float | None) -> float | None:
    """v178: the give-back level that set the runner stop, recorded at the
    ratchet. An ATR-dependent level set on an earlier bar is not reproduced by
    recomputing it from a later ATR, so the source is carried with the stop.
    In pct mode the level only tightens with its extreme, so this equals the
    old recomputation exactly."""
    if level is not None and runner_stop == level:
        return level
    return carried
```

In `_runner_phase` (`:537-580`), append to the docstring (after "...effective next bar."):

```
    v178: the give-back term follows GIVEBACK_MODE (_giveback_term, ATR through
    bar j) and the level that set the stop is carried for runner_stop_source.
```

and replace the body from `from swingbot.core.market.indicators import atr as atr_indicator` to the end of the function with:

```python
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    gb_extreme = _giveback_extreme(ctx, tp1_index, None)
    gb_level = None
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", None
        checked_stop = runner_stop
        hit = _runner_bar_exit(ctx, j, runner_stop, floor, gb_level)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        gb_extreme = _giveback_extreme(ctx, j, gb_extreme)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        level = _giveback_term(ctx, j, gb_extreme, atr_series)
        runner_stop = tighter_stop(runner_stop, level, ctx.is_bull)
        gb_level = _carried_level(runner_stop, level, gb_level)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop, atr_series)
        if trace is not None:
            trace.append((j, runner_stop))
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", None
```

The loop gains no branch, so `_runner_phase` stays at complexity 9. Leave `_giveback_ratchet` and `_stop_source` in place: `exit_sim_v2.py` still imports them until V178-2.

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_giveback_levels.py`
Expected: PASS, `0 failed`.

- [ ] **Step 7: Run the existing give-back and witness tests unmodified**

```bash
python scripts/dev/testrun.py suite planning
python scripts/dev/testrun.py file tests/backtesting/test_runner_structure_parity.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_runner_giveback.py
python scripts/dev/complexity_gate.py
```

Expected: every run `0 failed`, `0 xfailed`; the gate prints no finding. The `planning` suite includes `test_exit_sim_giveback.py` (v176 pct-mode exits, attribution, the frozen scale-out witness), `test_giveback_stop.py`, `test_exit_sim_scaleout.py`, `test_exit_sim_runner_structure.py` and `test_plan_manager_giveback.py` (live, untouched). A failure here means `pct` mode is no longer byte-identical: fix the code, never the test.

- [ ] **Step 8: Commit** (on the worktree branch)

```bash
git add swingbot/core/planning/exit_sim.py tests/planning/test_giveback_levels.py
git commit -m "feat(v178): adaptive give-back modes in the v1 exit walk

Range-multiple and profit-share levels as simulator-only module constants
(default pct = the live v176 rule, byte-identical); no term on a missing or
non-positive ATR; the level that set the stop is carried for attribution.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V178-2: v2 walk parity and the pinned witnesses

**Model:** opus — second copy of the shared runner loop; a drift between the two walks silently changes every v2 backtest

**Files:**
- Modify: `swingbot/core/planning/exit_sim_v2.py` (import block `:25-28`; `_runner_bar_v2` `:164-178`; `_runner_v2` `:180-217`)
- Modify: `swingbot/core/planning/exit_sim.py` (delete `_giveback_ratchet` and `_stop_source`, which no walk calls after this task)
- Create: `tests/planning/test_exit_sim_v2_giveback_levels.py` (suite `planning`; no manifest edit)

**Interfaces:**
- Consumes (V178-1): `_giveback_term(ctx, j, extreme, atr_series)`, `_carried_level(runner_stop, level, carried)`, `GIVEBACK_MODE/K/F`; and from the V178-1 test module the frames and helpers `REVERSE`, `JUMP`, `NAN_ATR_BARS`, `ARMS`, `ENTRY`, `FLOOR`, `_arm`, `_mirror`, `_bull`, `_bear` (`tests/planning/test_giveback_levels.py`). Existing: `walk_v2(df, entry_index, entry_price, plan, max_holding_days, instrument, *, scale_out)` (`exit_sim_v2.py:~225`), `ZERO_COSTS`, `resolve` (`swingbot/core/backtesting/instrument/contract.py`), `runner_stop_source`, `tighter_stop` (`exit_sim.py:279`, `:272`).
- Produces: `_runner_bar_v2(ctx, j, runner_stop, floor, gb_level=None)`; the guarantee "v1 = v2 on every arm" that V178-5 relies on (it runs the v1 walk; `backtest_wf` uses v2).

- [ ] **Step 1: Write the failing tests** — create `tests/planning/test_exit_sim_v2_giveback_levels.py`:

```python
"""v178 V178-2: the v2 walk follows every give-back arm exactly as the v1 walk.

Frames and helpers come from test_giveback_levels.py (V178-1); its module
docstring derives every level. The v2 walk runs with zero costs, so a stop
filled at its level (every open here sits on the profit side of the level)
matches the v1 exit price.
"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_giveback_levels import (ARMS, ENTRY, FLOOR, JUMP, NAN_ATR_BARS,
                                                 REVERSE, _arm, _bear, _bull, _mirror)

FREE = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
FRAMES = [("reverse-long", REVERSE, _bull), ("jump-long", JUMP, _bull),
          ("reverse-short", _mirror(REVERSE), _bear), ("jump-short", _mirror(JUMP), _bear)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", "pct")
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", 1.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", 0.33)


def _v1(bars, plan, entry=ENTRY):
    return simulate_exit(make_ohlcv(bars), entry, plan, scale_out=True, max_holding_days=10)


def _v2(bars, plan, entry=ENTRY):
    return walk_v2(make_ohlcv(bars), entry, 100.0, plan, 10, FREE, scale_out=True)


@pytest.mark.parametrize("mode, k, f", ARMS)
@pytest.mark.parametrize("name, bars, plan", FRAMES, ids=[f[0] for f in FRAMES])
def test_v1_and_v2_agree_on_every_arm(monkeypatch, mode, k, f, name, bars, plan):
    _arm(monkeypatch, mode, k, f)
    v1, v2 = _v1(bars, plan()), _v2(bars, plan())
    assert (v1.outcome, v1.exit_index, v1.runner_outcome, v1.runner_stop_source) == \
           (v2.outcome, v2.exit_index, v2.runner_outcome, v2.runner_stop_source)
    assert v1.legs[1]["exit_price"] == pytest.approx(v2.legs[1]["exit_price"])


@pytest.mark.parametrize("bars, plan", [(JUMP, _bull), (_mirror(JUMP), _bear)])
def test_v2_carries_an_earlier_atr_level_as_giveback(monkeypatch, bars, plan):
    _arm(monkeypatch, "range", k=1.0)
    res = _v2(bars, plan())
    assert (res.exit_index, res.runner_stop_source) == (18, "giveback")


@pytest.mark.parametrize("mode", ["range", "profit_share"])
def test_v2_no_atr_means_no_term(monkeypatch, mode):
    _arm(monkeypatch, mode)
    res = _v2(NAN_ATR_BARS, _bull(), entry=0)
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 4)


def test_v2_an_allowance_beyond_the_profit_exits_at_the_floor(monkeypatch):
    _arm(monkeypatch, "profit_share", f=0.95)
    res = _v2(REVERSE, _bull())
    assert (res.runner_stop_source, res.exit_index) == ("floor", 18)
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)


def test_the_recomputing_helpers_are_gone():
    assert not hasattr(exit_sim, "_giveback_ratchet")
    assert not hasattr(exit_sim, "_stop_source")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_giveback_levels.py`
Expected: FAIL — `test_v2_carries_an_earlier_atr_level_as_giveback` reports `"trail"` for the long frame (v2 still recomputes the level), several `test_v1_and_v2_agree_on_every_arm` cases differ (v2 still ratchets the pct level in every mode), and `test_the_recomputing_helpers_are_gone` fails.

- [ ] **Step 3: Switch the v2 walk to the shared term and the carried level** — in `swingbot/core/planning/exit_sim_v2.py`.

Replace the import block `:25-28` with:

```python
from .exit_sim import (ExitResult, _carried_level, _chandelier_ratchet, _giveback_extreme,
                       _giveback_term, _hold_cap_bars, _is_compression, _limit_unfilled,
                       _no_trade, _not_triggered, _runner_timeout, _structure_update,
                       _tenth_session_reached, acceptance_exit, runner_floor,
                       runner_stop_source, runner_structure_frame, tighter_stop)
```

Replace `_runner_bar_v2` (`:164-178`) with:

```python
def _runner_bar_v2(ctx, j: int, runner_stop: float, floor: float, gb_level=None):
    """Runner stop first, then TP2, each filled through fills.exit_fill:
    (price, index, reason, kind, stop_source) or None; stop_source is None for TP2.
    v178: ``gb_level`` is the carried give-back level that set ``runner_stop``."""
    hi, lo, op = float(ctx.high[j]), float(ctx.low[j]), float(ctx.open_[j])
    direction = ctx.plan.direction
    if fills.stop_touched(hi, lo, runner_stop, direction):
        reason = "runner_be" if runner_stop == floor else "runner_trail"
        return (fills.exit_fill(ctx.fills, "stop", runner_stop, op, direction), j, reason,
                "stop", runner_stop_source(runner_stop, floor, gb_level))
    tp2 = ctx.plan.tp2
    if tp2 is not None and fills.target_touched(hi, lo, tp2, direction):
        return (fills.exit_fill(ctx.fills, "target", tp2, op, direction), j, "runner_tp2",
                "target", None)
    return None
```

In `_runner_v2` (`:180-217`), append to the docstring "v178: the give-back term follows GIVEBACK_MODE and the level that set the stop is carried, as in exit_sim." and replace the body from `floor = runner_floor(...)` to the end with:

```python
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    gb_extreme = _giveback_extreme(ctx, tp1_index, None)
    gb_level = None
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall", "close", None
        checked_stop = runner_stop
        hit = _runner_bar_v2(ctx, j, runner_stop, floor, gb_level)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        gb_extreme = _giveback_extreme(ctx, j, gb_extreme)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        level = _giveback_term(ctx, j, gb_extreme, atr_series)
        runner_stop = tighter_stop(runner_stop, level, ctx.is_bull)
        gb_level = _carried_level(runner_stop, level, gb_level)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop,
                                                           atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout", "close", None
```

(The `acceptance_exit` early return and the local `atr_indicator` import above `floor = ...` stay as they are.)

- [ ] **Step 4: Delete the two recomputing helpers** — in `swingbot/core/planning/exit_sim.py`, delete `def _giveback_ratchet(ctx, extreme, runner_stop)` and `def _stop_source(ctx, runner_stop, floor, gb_extreme)` with their docstrings. Then confirm nothing references them:

```bash
git grep -n "_giveback_ratchet\|[^_a-z]_stop_source(" -- swingbot scripts tests
```

Expected: no output. (`runner_stop_source` does not match: the pattern needs a non-letter before `_stop_source(`.)

- [ ] **Step 5: Run the new tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_giveback_levels.py`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Run the pinned witnesses and goldens, unmodified**

These pin the flag-off and pct-mode trade lists of both walks (brief § 7). None may be edited.

```bash
python scripts/dev/testrun.py suite planning
python scripts/dev/testrun.py file tests/backtesting/test_runner_structure_parity.py
python scripts/dev/testrun.py file tests/backtesting/test_pullback_dryup_witness.py
python scripts/dev/testrun.py file tests/backtesting/test_v129_flag_off_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py
python scripts/dev/testrun.py file tests/backtesting/test_v139_flag_off_golden.py
python scripts/dev/testrun.py file tests/backtesting/test_headroom_witness.py
python scripts/dev/testrun.py suite backtesting-arms
python scripts/dev/testrun.py file tests/market/test_v113_horizon_witness.py
python scripts/dev/testrun.py file tests/scripts/test_runner_headroom.py
python scripts/dev/testrun.py file tests/scanning/test_giveback_embed.py
python scripts/dev/testrun.py file tests/backtest_scripts/test_measure_runner_giveback.py
python scripts/dev/complexity_gate.py
```

Expected: every run `0 failed`, `0 xfailed`; the gate prints no finding. `backtesting-arms` holds the instrument goldens (`instrument/test_v1_golden.py`, `test_constructor_parity.py`, `test_fills_costs_replay.py`, `test_live_constructor_replay.py`) and `arms/test_engine_instrument.py`. A red witness means default `pct` is no longer byte-identical in one walk: fix the code, never the fixture.

- [ ] **Step 7: Commit** (on the worktree branch)

```bash
git add swingbot/core/planning/exit_sim_v2.py swingbot/core/planning/exit_sim.py tests/planning/test_exit_sim_v2_giveback_levels.py
git commit -m "feat(v178): v2 exit walk follows the give-back arms; v1 = v2 on every arm

The v2 runner loop uses the shared give-back term and the carried level;
the recomputing helpers _giveback_ratchet and _stop_source are removed.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2 — Funnel logic and descriptive blocks

### Task V178-3: Funnel logic: stages 0–2, stage-3 pick, Holm, cells

**Model:** opus — encodes the frozen pre-registration rules; a wrong comparison here decides a one-shot VALIDATION

**Files:**
- Create: `swingbot/core/backtesting/giveback_levels_funnel.py`
- Create: `tests/backtesting/test_giveback_levels_funnel.py` (suite `backtesting-a-k` by its `test_g*` name; no manifest edit)

**Interfaces:**
- Consumes (existing): `ArmTrade`, `CLOSED`, `BOOTSTRAP_RESAMPLES`, `bootstrap_delta(baseline, component, statistic, *, n_resamples, seed, cluster)`, `delta_expectancy_r(baseline, component)`, `mde_paired(baseline, component, statistic, *, observed_n, target_n, ..., n_resamples, seed, cluster)` (`swingbot/core/backtesting/acceptance.py:28,100,182,280,225,372`); `STAGES` (`swingbot/core/backtesting/arms/windows.py`); `gate(result)`, `plateau_report(param_name, grid, expectancies, adopted_value)`, `GATE_MIN_IMPROVING_FOLDS` (`swingbot/core/backtesting/backtest_wf.py:205,36,29`); `week_cluster_bootstrap`, `WEEK_BOOTSTRAP_RESAMPLES` (`swingbot/core/backtesting/instrument/stats.py:57,24`). Rows follow the index's row contract (only `ticker, source, strategy, horizon_key, direction, signal_date, planned_rr` and per arm `outcome, r_net, exit_index, exit_price` are read here).
- Produces (funnel contract in the index; V178-4 does not import it, V178-6 does): `PCT`, `ARMS`, `CONTROLS`, `CANDIDATES`, `FAMILIES`, `FAMILY_PARAM`, `MIN_CHANGED_PER_FOLD`, `SAME_SIGN_MIN_WINDOWS`, `pooled_window()`, `fold_train_windows()`, `fold_test_windows()`, `rows_in`, `arm_trades`, `changed_count`, `paired_delta`, `week_interval`, `stage0`, `fold_train_deltas`, `stage1`, `stage2`, `pick_stage3`, `holm`, `cells_looked_at`, `run_funnel` with the exact signatures and return keys the index lists.

**Readings fixed here (spec § The test; brief M4, M6, M7, M10):**
- Stage 0's pooled fold-train window is `STAGES["selection"].signal_window` (2018-06-01..2022-12-31): the three fold-train windows are nested from 2018-06-01, so their union is the widest one. `RESOLVABLE` needs the measured ΔExpR at or above `mde_paired` on the same pairs; an effect at or below zero is refused too, which only differs from the bare rule when the MDE itself is zero (pairs with no spread).
- Stage 1 adopts, per family, the arm with the highest pooled ΔExpR among the family's arms still open after stage 0 (a refused arm is closed, so it cannot be adopted, but it stays a neighbour and stays in the family-wide same-sign rule). No open arm → `NO-CANDIDATE`.
- Stage 2 is `backtest_wf.gate` on the three fold-test years, **and** at least `GATE_MIN_IMPROVING_FOLDS` folds that improve with at least `MIN_CHANGED_PER_FOLD` changed exits. "Changed" is `(exit_index, exit_price)` differing from control A (a post-TP1 rule cannot flip `outcome`).
- `stage3_arm`: best stage-2 `mean_delta_r` among stage-2 passes; a tie goes to family R.
- Holm is applied to the six stage-0 (pooled fold-train) one-sided p values.

- [ ] **Step 1: Write the failing tests** — create `tests/backtesting/test_giveback_levels_funnel.py`:

```python
"""v178 V178-3: the funnel's frozen rules on synthetic paired rows."""
import pytest

from swingbot.core.backtesting import giveback_levels_funnel as fn
from swingbot.core.backtesting.arms.windows import STAGES

TICKERS = [f"T{i}" for i in range(8)]
BUCKETS = ("2019-03-04", "2021-03-01", "2022-03-01")   # folds 2020-22 / 2021-22 / 2022
N = 200                                                 # resamples: speed, never a real run


def _row(ticker, date, deltas, *, i=0, changed=None):
    """One entry. ``deltas`` maps arm -> r_net minus control A's (1.0); arms not
    named equal A. ``changed`` names the arms whose exit differs from A
    (default: every arm with a non-zero delta)."""
    moved = {a for a, d in deltas.items() if d} if changed is None else set(changed)
    arms = {arm: {"outcome": "win", "r_net": 1.0 + deltas.get(arm, 0.0),
                  "exit_index": 20 + (arm in moved), "exit_price": 110.0 + (arm in moved)}
            for arm in fn.ARMS}
    return {"ticker": ticker, "source": "strategy", "strategy": f"S{i}", "horizon_key": "1m",
            "direction": "bullish", "signal_date": date, "planned_rr": 2.0, "arms": arms}


def _date(year, k):
    return f"{year}-{k % 12 + 1:02d}-{k // 12 % 28 + 1:02d}"


def _year_rows(year, deltas_for, n=40):
    """n rows in ``year``, spread over TICKERS; deltas_for(k, ticker_index) -> deltas."""
    return [_row(TICKERS[k % 8], _date(year, k), deltas_for(k, k % 8), i=k) for k in range(n)]


def _bucket_rows(per_arm):
    """One row per ticker per bucket; per_arm: arm -> (d_2019, d_2021, d_2022)."""
    return [_row(t, date, {a: v[b] for a, v in per_arm.items()}, i=b)
            for b, date in enumerate(BUCKETS) for t in TICKERS]


def _s0(**arms):
    """stage0 stand-ins: arm id with '.' written '_' -> (pooled delta, verdict)."""
    return {k.replace("_", "."): {"delta_r": d, "verdict": v} for k, (d, v) in arms.items()}


OPEN = "RESOLVABLE"


def test_the_arm_table_is_frozen():
    assert fn.PCT == 5.0
    assert fn.ARMS == {
        "A": {"enabled": True, "mode": "pct"}, "B": {"enabled": False, "mode": "pct"},
        "R0.75": {"enabled": True, "mode": "range", "k": 0.75},
        "R1.00": {"enabled": True, "mode": "range", "k": 1.0},
        "R1.25": {"enabled": True, "mode": "range", "k": 1.25},
        "S0.25": {"enabled": True, "mode": "profit_share", "f": 0.25},
        "S0.33": {"enabled": True, "mode": "profit_share", "f": 0.33},
        "S0.50": {"enabled": True, "mode": "profit_share", "f": 0.50}}
    assert fn.CONTROLS == ("A", "B")
    assert fn.CANDIDATES == ("R0.75", "R1.00", "R1.25", "S0.25", "S0.33", "S0.50")
    assert fn.FAMILIES == {"R": ("R0.75", "R1.00", "R1.25"), "S": ("S0.25", "S0.33", "S0.50")}
    assert fn.FAMILY_PARAM == {"R": ("k", (0.75, 1.0, 1.25)), "S": ("f", (0.25, 0.33, 0.50))}
    assert (fn.MIN_CHANGED_PER_FOLD, fn.SAME_SIGN_MIN_WINDOWS) == (30, 2)


def test_windows_come_from_the_stage_table():
    assert fn.pooled_window() == STAGES["selection"].signal_window == ("2018-06-01", "2022-12-31")
    assert fn.fold_train_windows() == [("2020", ("2018-06-01", "2020-12-31")),
                                       ("2021", ("2018-06-01", "2021-12-31")),
                                       ("2022", ("2018-06-01", "2022-12-31"))]
    assert [label for label, _ in fn.fold_test_windows()] == ["2021", "2022", "2023"]


def test_rows_in_is_inclusive_and_changed_counts_exits():
    rows = [_row("T0", "2018-06-01", {"R1.00": 0.1}), _row("T1", "2022-12-31", {}),
            _row("T2", "2023-01-02", {"R1.00": 0.1})]
    assert len(fn.rows_in(rows, fn.pooled_window())) == 2
    assert fn.changed_count(rows, "R1.00") == 2
    assert fn.changed_count(rows, "R1.00", against="B") == 2
    assert fn.changed_count(rows, "S0.25") == 0


def test_arm_trades_carry_net_r_and_the_pairing_key():
    [trade] = fn.arm_trades([_row("T0", "2019-03-04", {"R1.00": 0.25}, i=7)], "R1.00")
    assert trade.r_multiple == 1.25 and trade.outcome == "win"
    assert trade.key == ("T0", "S7", "1m", "2019-03-04", "strategy", "bullish")


def test_paired_delta_on_a_constant_shift():
    rows = _year_rows(2019, lambda k, t: {"R1.00": 0.1})
    out = fn.paired_delta(rows, "R1.00", n_resamples=N)
    assert out["delta_r"] == pytest.approx(0.1)
    assert out["ci_lo"] == pytest.approx(0.1) and out["ci_hi"] == pytest.approx(0.1)
    assert out["p"] == 0.0 and (out["n"], out["changed"]) == (40, 40)
    assert set(out) == {"arm", "against", "n", "changed", "delta_r", "ci_lo", "ci_hi", "p"}
    week = fn.week_interval(rows, "R1.00", n_resamples=N)
    assert week["lo"] == pytest.approx(0.1) and week["hi"] == pytest.approx(0.1)


def test_stage0_compares_the_measured_effect_with_the_paired_mde():
    rows = _year_rows(2019, lambda k, t: {"R1.00": 0.2 + 0.01 * (t % 3),
                                          "R0.75": 0.3 if t % 2 else -0.3})
    rows += _year_rows(2023, lambda k, t: {"R1.00": -5.0})       # outside the pooled window
    good = fn.stage0(rows, "R1.00", n_resamples=N)
    assert good["n"] == 40 and good["verdict"] == "RESOLVABLE"
    assert 0 < good["mde_paired"] < good["delta_r"]
    assert fn.stage0(rows, "R0.75", n_resamples=N)["verdict"] == "REFUSED"   # mean 0
    flat = fn.stage0(rows, "S0.25", n_resamples=N)                            # identical to A
    assert flat["delta_r"] == 0.0 and flat["verdict"] == "REFUSED"


def test_fold_train_deltas_follow_the_nested_windows():
    rows = _bucket_rows({"R1.00": (0.3, 0.0, -0.3)})
    assert fn.fold_train_deltas(rows, "R1.00") == pytest.approx([0.3, 0.15, 0.0])


GOOD = {"R0.75": (0.10, 0.10, 0.10), "R1.00": (0.12, 0.12, 0.12), "R1.25": (0.11, 0.11, 0.11)}


def test_stage1_passes_a_plateau_with_family_wide_same_sign():
    out = fn.stage1(_bucket_rows(GOOD), "R",
                    _s0(R0_75=(0.10, OPEN), R1_00=(0.12, OPEN), R1_25=(0.11, OPEN)))
    assert out["adopted"] == "R1.00" and out["verdict"] == "PASS"
    assert out["plateau"]["is_plateau"] is True
    assert out["same_sign"]["windows_by_arm"] == {"R0.75": 3, "R1.00": 3, "R1.25": 3}


@pytest.mark.parametrize("r125_verdict", [OPEN, "REFUSED"])
def test_stage1_family_wide_rule_counts_a_refused_neighbour(r125_verdict):
    rows = _bucket_rows({**GOOD, "R1.25": (-0.10, -0.10, 0.50)})   # folds -0.1, -0.1, +0.1
    out = fn.stage1(rows, "R", _s0(R0_75=(0.10, OPEN), R1_00=(0.12, OPEN),
                                   R1_25=(0.11, r125_verdict)))
    assert out["plateau"]["is_plateau"] is True
    assert out["same_sign"]["windows_by_arm"]["R1.25"] == 1
    assert out["verdict"] == "FAIL"


def test_stage1_rejects_a_spike():
    out = fn.stage1(_bucket_rows(GOOD), "R",
                    _s0(R0_75=(0.02, OPEN), R1_00=(0.12, OPEN), R1_25=(0.11, OPEN)))
    assert out["plateau"]["is_plateau"] is False and out["verdict"] == "FAIL"


def test_stage1_edge_arm_has_one_neighbour_but_faces_the_whole_family():
    rows = _bucket_rows({**GOOD, "R1.25": (-0.10, -0.10, -0.10)})
    out = fn.stage1(rows, "R", _s0(R0_75=(0.13, OPEN), R1_00=(0.12, OPEN), R1_25=(0.05, OPEN)))
    assert out["adopted"] == "R0.75"
    assert out["plateau"]["neighbors"] == {1.0: 0.12} and out["plateau"]["is_plateau"]
    assert out["verdict"] == "FAIL"                           # R1.25 never shares the sign


def test_stage1_adopts_only_an_arm_still_open_after_stage0():
    out = fn.stage1(_bucket_rows(GOOD), "R",
                    _s0(R0_75=(0.10, OPEN), R1_00=(0.12, OPEN), R1_25=(0.13, "REFUSED")))
    assert out["adopted"] == "R1.00"
    none_open = fn.stage1(_bucket_rows(GOOD), "R", _s0(
        R0_75=(0.10, "REFUSED"), R1_00=(0.12, "REFUSED"), R1_25=(0.11, "REFUSED")))
    assert (none_open["adopted"], none_open["verdict"]) == (None, "NO-CANDIDATE")


def _fold_rows(spec):
    """spec: year -> (delta on a changed row, number of changed rows of 40)."""
    rows = []
    for year, (delta, changed) in spec.items():
        rows += _year_rows(year, lambda k, t, d=delta, c=changed: {"R1.00": d if k < c else 0.0})
    return rows


def test_stage2_passes_three_improving_folds():
    out = fn.stage2(_fold_rows({2021: (0.1, 40), 2022: (0.1, 40), 2023: (0.1, 40)}), "R1.00")
    assert (out["gate"], out["improving_folds"], out["verdict"]) == ("PASS", 3, "PASS")
    assert out["mean_delta_r"] == pytest.approx(0.1)
    assert [f["test_year"] for f in out["folds"]] == ["2021", "2022", "2023"]


def test_stage2_a_fold_needs_30_changed_exits_to_count_as_improving():
    # deltas +0.1, +0.0725, -0.01: backtest_wf.gate alone passes (2 of 3 > 0)
    out = fn.stage2(_fold_rows({2021: (0.1, 40), 2022: (0.1, 29), 2023: (-0.01, 40)}), "R1.00")
    assert out["gate"] == "PASS"
    assert [f["improving"] for f in out["folds"]] == [True, False, False]
    assert out["verdict"] == "FAIL"


def test_stage2_a_fold_below_the_degradation_floor_fails():
    out = fn.stage2(_fold_rows({2021: (0.1, 40), 2022: (0.1, 40), 2023: (-0.1, 40)}), "R1.00")
    assert (out["gate"], out["verdict"]) == ("FAIL", "FAIL")


def test_pick_stage3_takes_the_best_mean_and_breaks_ties_to_family_r():
    s2 = lambda m, v="PASS": {"mean_delta_r": m, "verdict": v}    # noqa: E731
    assert fn.pick_stage3({"S0.33": s2(0.05), "R1.00": s2(0.05)}) == "R1.00"
    assert fn.pick_stage3({"R1.00": s2(0.03), "S0.33": s2(0.05)}) == "S0.33"
    assert fn.pick_stage3({"R1.00": s2(0.09, "FAIL"), "S0.33": s2(0.02)}) == "S0.33"
    assert fn.pick_stage3({}) is None


def test_holm_step_down():
    out = fn.holm({"a": 0.01, "b": 0.04, "c": 0.03, "d": None, "e": 0.9})
    assert out["a"] == pytest.approx(0.04)          # 4 x 0.01
    assert out["c"] == pytest.approx(0.09)          # 3 x 0.03
    assert out["b"] == pytest.approx(0.09)          # max(2 x 0.04, 0.09)
    assert out["e"] == pytest.approx(0.9) and out["d"] is None
    assert fn.holm({"a": 0.6, "b": 0.7})["a"] == 1.0   # capped


def test_cells_looked_at_is_the_frozen_150():
    assert fn.cells_looked_at() == 150
    assert fn.cells_looked_at(sensitivity=12) == 162


def test_run_funnel_stops_at_stage0_when_every_arm_is_refused():
    rows = _year_rows(2019, lambda k, t: {}) + _year_rows(2021, lambda k, t: {})
    out = fn.run_funnel(rows, n_resamples=N)
    assert out["stopped_at"] == "stage0" and out["stage3_arm"] is None
    assert out["stage1"] == {} and out["stage2"] == {}
    assert set(out["stage0"]) == set(out["holm"]) == set(out["week_interval"]) == set(fn.CANDIDATES)


def test_run_funnel_carries_one_arm_to_stage3():
    def deltas(k, t):
        noise = 0.01 * (t % 3)
        return {"R0.75": 0.20 + noise, "R1.00": 0.21 + noise, "R1.25": 0.20 + noise}
    rows = [r for year in (2019, 2021, 2022, 2023) for r in _year_rows(year, deltas)]
    out = fn.run_funnel(rows, n_resamples=N)
    assert {a: out["stage0"][a]["verdict"] for a in fn.CANDIDATES} == {
        "R0.75": OPEN, "R1.00": OPEN, "R1.25": OPEN,
        "S0.25": "REFUSED", "S0.33": "REFUSED", "S0.50": "REFUSED"}
    assert out["stage1"]["R"]["verdict"] == "PASS"
    assert out["stage1"]["S"]["verdict"] == "NO-CANDIDATE"
    assert set(out["stage2"]) == {"R1.00"} and out["stage2"]["R1.00"]["verdict"] == "PASS"
    assert (out["stopped_at"], out["stage3_arm"]) == (None, "R1.00")
    assert out["week_interval"]["R1.00"]["lo"] > 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_giveback_levels_funnel.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.backtesting.giveback_levels_funnel'`.

- [ ] **Step 3: Write the module** — create `swingbot/core/backtesting/giveback_levels_funnel.py`:

```python
"""v178 funnel logic: stages 0-2, the stage-3 pick, Holm, cells looked at.

Pure functions over the v178 row contract (one row per entry, the result of
every arm under ``row["arms"][arm_id]``; plan v178 index, "Row contract").
Every comparison is paired on the same entries against control A, the live
fixed 5%. The rules are the spec's, frozen 2026-10-19
(docs/superpowers/specs/2026-10-19-v178-runner-giveback-levels-preregistration-design.md
§ The test). Nothing here simulates and nothing reads past the walk-forward
windows: VALIDATION is the script's one shot through validate_component.py.
"""
from __future__ import annotations

import numpy as np

from swingbot.core.backtesting.acceptance import (BOOTSTRAP_RESAMPLES, CLOSED, ArmTrade,
                                                  bootstrap_delta, delta_expectancy_r,
                                                  mde_paired)
from swingbot.core.backtesting.arms.windows import STAGES
from swingbot.core.backtesting.backtest_wf import (GATE_MIN_IMPROVING_FOLDS, gate,
                                                   plateau_report)
from swingbot.core.backtesting.instrument.stats import (WEEK_BOOTSTRAP_RESAMPLES,
                                                        week_cluster_bootstrap)

#: Control A's fixed give-back, percent of the best close (the live v176 rule).
PCT = 5.0
#: The frozen arms. No other value is ever run (spec § The rules).
ARMS: dict[str, dict] = {
    "A": {"enabled": True, "mode": "pct"},
    "B": {"enabled": False, "mode": "pct"},
    "R0.75": {"enabled": True, "mode": "range", "k": 0.75},
    "R1.00": {"enabled": True, "mode": "range", "k": 1.0},
    "R1.25": {"enabled": True, "mode": "range", "k": 1.25},
    "S0.25": {"enabled": True, "mode": "profit_share", "f": 0.25},
    "S0.33": {"enabled": True, "mode": "profit_share", "f": 0.33},
    "S0.50": {"enabled": True, "mode": "profit_share", "f": 0.50},
}
CONTROLS = ("A", "B")
CANDIDATES = ("R0.75", "R1.00", "R1.25", "S0.25", "S0.33", "S0.50")
FAMILIES = {"R": ("R0.75", "R1.00", "R1.25"), "S": ("S0.25", "S0.33", "S0.50")}
FAMILY_PARAM = {"R": ("k", (0.75, 1.0, 1.25)), "S": ("f", (0.25, 0.33, 0.50))}
#: Stage 2: a fold counts as improving only with this many changed exits.
MIN_CHANGED_PER_FOLD = 30
#: Stage 1: fold-train windows each family arm must share the adopted sign on.
SAME_SIGN_MIN_WINDOWS = 2


def pooled_window() -> tuple[str, str]:
    """The union of the three nested fold-train windows (all from 2018-06-01)."""
    return STAGES["selection"].signal_window


def _labelled(stage: str) -> list[tuple[str, tuple[str, str]]]:
    return [(label, (lo, hi)) for label, lo, hi in STAGES[stage].folds]


def fold_train_windows() -> list[tuple[str, tuple[str, str]]]:
    return _labelled("selection")


def fold_test_windows() -> list[tuple[str, tuple[str, str]]]:
    return _labelled("walkforward")


def rows_in(rows: list[dict], window: tuple[str, str]) -> list[dict]:
    """Rows whose signal date lies in the window, both ends included."""
    lo, hi = window
    return [r for r in rows if lo <= r["signal_date"] <= hi]


def arm_trades(rows: list[dict], arm: str) -> list[ArmTrade]:
    """One ArmTrade per row for ``arm``, R net of frictions."""
    return [ArmTrade(ticker=r["ticker"], strategy=r["strategy"], horizon_key=r["horizon_key"],
                     entry_date=r["signal_date"], outcome=r["arms"][arm]["outcome"],
                     r_multiple=r["arms"][arm]["r_net"], planned_rr=r["planned_rr"],
                     source=r["source"], direction=r["direction"])
            for r in rows]


def _exit(row: dict, arm: str) -> tuple:
    res = row["arms"][arm]
    return res["exit_index"], res["exit_price"]


def changed_count(rows: list[dict], arm: str, *, against: str = "A") -> int:
    """Rows whose exit (bar, price) differs between ``arm`` and ``against``."""
    return sum(_exit(r, arm) != _exit(r, against) for r in rows)


def paired_delta(rows, arm, *, against="A", n_resamples=BOOTSTRAP_RESAMPLES, seed=42) -> dict:
    """ΔExpR (arm - against) with the ticker-cluster bootstrap; ``p`` is the
    one-sided share of draws at or below zero."""
    boot = bootstrap_delta(arm_trades(rows, against), arm_trades(rows, arm),
                           delta_expectancy_r, n_resamples=n_resamples, seed=seed)
    return {"arm": arm, "against": against, "n": len(rows),
            "changed": changed_count(rows, arm, against=against), "delta_r": boot.point,
            "ci_lo": boot.lo, "ci_hi": boot.hi, "p": boot.p_greater_than_zero}


def week_interval(rows, arm, *, against="A", n_resamples=WEEK_BOOTSTRAP_RESAMPLES) -> dict:
    """The week-clustered 95% interval of ΔExpR. Descriptive, never gating."""
    draws = week_cluster_bootstrap(arm_trades(rows, against), arm_trades(rows, arm),
                                   delta_expectancy_r, n_resamples=n_resamples)
    if draws.size == 0:
        return {"lo": None, "hi": None}
    return {"lo": float(np.percentile(draws, 2.5)), "hi": float(np.percentile(draws, 97.5))}


def _resolvable(effect: float | None, mde: float | None) -> bool:
    """Refused when the measured effect is below the paired MDE. An effect at
    or below zero is refused as well; that only matters when the MDE is zero."""
    return effect is not None and mde is not None and effect > 0 and effect >= mde


def stage0(rows, arm, *, n_resamples=BOOTSTRAP_RESAMPLES) -> dict:
    """Stage 0 on the pooled fold-train window: the measured paired ΔExpR
    (arm - A) against acceptance.mde_paired on the same pairs."""
    pooled = rows_in(rows, pooled_window())
    out = paired_delta(pooled, arm, n_resamples=n_resamples)
    mde = mde_paired(arm_trades(pooled, "A"), arm_trades(pooled, arm), delta_expectancy_r,
                     observed_n=len(pooled), target_n=len(pooled), n_resamples=n_resamples)
    return {**out, "mde_paired": mde,
            "verdict": "RESOLVABLE" if _resolvable(out["delta_r"], mde) else "REFUSED"}


def fold_train_deltas(rows, arm) -> list[float | None]:
    """ΔExpR (arm - A) on each fold-train window, in fold order."""
    return [delta_expectancy_r(arm_trades(sub, "A"), arm_trades(sub, arm))
            for sub in (rows_in(rows, window) for _, window in fold_train_windows())]


def _sign(value: float | None) -> int:
    if value is None:
        return 0
    return (value > 0) - (value < 0)


def _same_sign(sign: int, deltas_by_arm: dict[str, list]) -> dict:
    counts = {arm: sum(1 for d in deltas if d is not None and _sign(d) == sign)
              for arm, deltas in deltas_by_arm.items()}
    passed = sign != 0 and all(c >= SAME_SIGN_MIN_WINDOWS for c in counts.values())
    return {"sign": sign, "windows_by_arm": counts, "pass": passed}


def _adopt(family: str, stage0_by_arm: dict[str, dict]) -> str | None:
    """Highest pooled ΔExpR among the family's arms still open after stage 0."""
    open_arms = [a for a in FAMILIES[family] if stage0_by_arm[a]["verdict"] == "RESOLVABLE"]
    if not open_arms:
        return None
    return max(open_arms, key=lambda a: stage0_by_arm[a]["delta_r"])


def _plateau(family: str, pooled: dict, adopted: str) -> dict:
    param, grid = FAMILY_PARAM[family]
    arms = FAMILIES[family]
    if any(pooled[a] is None for a in arms):
        return {"param": param, "grid": list(grid), "adopted": grid[arms.index(adopted)],
                "is_plateau": False, "reason": "an arm has no pooled ΔExpR"}
    return plateau_report(param, list(grid), [pooled[a] for a in arms],
                          grid[arms.index(adopted)])


def stage1(rows, family: str, stage0_by_arm: dict[str, dict]) -> dict:
    """Stage 1 per family: plateau_report on the pooled ΔExpR, plus every
    family arm sharing the adopted arm's sign on >= 2 of 3 fold-train windows."""
    arms = FAMILIES[family]
    pooled = {a: stage0_by_arm[a]["delta_r"] for a in arms}
    fold_train = {a: fold_train_deltas(rows, a) for a in arms}
    adopted = _adopt(family, stage0_by_arm)
    out = {"family": family, "adopted": adopted, "pooled": pooled, "fold_train": fold_train,
           "plateau": None, "same_sign": None}
    if adopted is None:
        return {**out, "verdict": "NO-CANDIDATE"}
    plateau = _plateau(family, pooled, adopted)
    same = _same_sign(_sign(pooled[adopted]), fold_train)
    verdict = "PASS" if plateau["is_plateau"] and same["pass"] else "FAIL"
    return {**out, "plateau": plateau, "same_sign": same, "verdict": verdict}


def _closed(trades) -> int:
    return sum(t.outcome in CLOSED for t in trades)


def _fold(rows, arm, label, window) -> dict:
    sub = rows_in(rows, window)
    base, comp = arm_trades(sub, "A"), arm_trades(sub, arm)
    delta = delta_expectancy_r(base, comp)
    changed = changed_count(sub, arm)
    return {"test_year": label, "delta_expectancy_r": delta,
            "n": min(_closed(base), _closed(comp)), "changed": changed,
            "improving": delta is not None and delta > 0 and changed >= MIN_CHANGED_PER_FOLD}


def stage2(rows, arm) -> dict:
    """Stage 2: backtest_wf.gate on the fold-test years (>= 2 of 3 improving,
    none below -0.05R, n >= 30), with improving counted only on folds that
    have >= MIN_CHANGED_PER_FOLD changed exits."""
    folds = [_fold(rows, arm, label, window) for label, window in fold_test_windows()]
    gate_verdict = gate({"folds": folds})
    improving = sum(f["improving"] for f in folds)
    deltas = [f["delta_expectancy_r"] for f in folds]
    mean = None if any(d is None for d in deltas) else float(np.mean(deltas))
    passed = gate_verdict == "PASS" and improving >= GATE_MIN_IMPROVING_FOLDS
    return {"arm": arm, "folds": folds, "gate": gate_verdict, "improving_folds": improving,
            "mean_delta_r": mean, "verdict": "PASS" if passed else "FAIL"}


def pick_stage3(stage2_by_arm: dict[str, dict]) -> str | None:
    """The one arm for VALIDATION: best stage-2 mean ΔExpR among passes; a
    tie goes to the simpler rule, family R."""
    passed = [(r["mean_delta_r"], arm) for arm, r in stage2_by_arm.items()
              if r["verdict"] == "PASS" and r["mean_delta_r"] is not None]
    if not passed:
        return None
    best = max(mean for mean, _ in passed)
    tied = sorted(arm for mean, arm in passed if mean == best)
    family_r = [arm for arm in tied if arm in FAMILIES["R"]]
    return (family_r or tied)[0]


def holm(pvalues: dict[str, float | None]) -> dict[str, float | None]:
    """Holm step-down adjusted p values; None passes through and is not counted."""
    present = sorted((p, arm) for arm, p in pvalues.items() if p is not None)
    m = len(present)
    out: dict[str, float | None] = {arm: None for arm in pvalues}
    running = 0.0
    for i, (p, arm) in enumerate(present):
        running = max(running, min(1.0, (m - i) * p))
        out[arm] = running
    return out


def cells_looked_at(*, arms=6, fold_train=3, fold_test_arms=6, fold_test=3, horizons=10,
                    control_b=6, blocks=7, regime_arms=3, sensitivity=0) -> int:
    """The spec's frozen count: 36 gating + 60 per-horizon + 6 control-B + 42
    block + 6 regime cells = 150, plus the sensitivity cells if they run."""
    return (arms * fold_train + fold_test_arms * fold_test + arms * horizons + control_b
            + arms * blocks + regime_arms * 2 + sensitivity)


def run_funnel(rows, *, n_resamples=BOOTSTRAP_RESAMPLES) -> dict:
    """Stages 0-2 on TRAIN-side rows, stopping at the first stage that closes
    every arm; ``stage3_arm`` is the single VALIDATION candidate or None."""
    s0 = {arm: stage0(rows, arm, n_resamples=n_resamples) for arm in CANDIDATES}
    pooled = rows_in(rows, pooled_window())
    out = {"stage0": s0, "stage1": {}, "stage2": {}, "stopped_at": None, "stage3_arm": None,
           "holm": holm({arm: s0[arm]["p"] for arm in CANDIDATES}),
           "week_interval": {arm: week_interval(pooled, arm, n_resamples=n_resamples)
                             for arm in CANDIDATES}}
    if not any(r["verdict"] == "RESOLVABLE" for r in s0.values()):
        return {**out, "stopped_at": "stage0"}
    out["stage1"] = {family: stage1(rows, family, s0) for family in FAMILIES}
    adopted = [r["adopted"] for r in out["stage1"].values() if r["verdict"] == "PASS"]
    if not adopted:
        return {**out, "stopped_at": "stage1"}
    out["stage2"] = {arm: stage2(rows, arm) for arm in adopted}
    pick = pick_stage3(out["stage2"])
    return {**out, "stopped_at": None if pick else "stage2", "stage3_arm": pick}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_giveback_levels_funnel.py`
Expected: PASS, `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: no finding (every function above is well under 15).

- [ ] **Step 6: Commit** (on the worktree branch)

```bash
git add swingbot/core/backtesting/giveback_levels_funnel.py tests/backtesting/test_giveback_levels_funnel.py
git commit -m "feat(v178): give-back levels funnel -- stages 0-2, stage-3 pick, Holm, cells

Pure functions over the v178 paired rows: measured pooled fold-train ΔExpR
against the paired MDE, plateau plus the family-wide same-sign rule, the
harvest fold gate with a 30-changed-exit floor per improving fold.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
