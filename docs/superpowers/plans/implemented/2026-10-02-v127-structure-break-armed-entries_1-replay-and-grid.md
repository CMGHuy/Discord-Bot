# v127 Structure-Break Armed Entries — Part 1: the walk, the replay and the grid

> Part of `2026-10-02-v127-structure-break-armed-entries`. Header, global constraints, spec readings, review focus, parallelisation and outcomes live in `_0-index.md` — read its **Global Constraints** and **Spec readings fixed by this plan** before any task here.

# Phase 1 — The walk, the replay and the grid (worktree branch)

### Task V127-1: The structure-break walk

**Files:**
- Create: `swingbot/core/backtesting/structure_arm.py`
- Create: `tests/backtesting/structure_arm_fixtures.py`
- Test: `tests/backtesting/test_structure_arm_walk.py`

**Interfaces:**
- Consumes: v121's `swingbot.core.market.structure.confirmed_pivots(df, k=3) -> pd.DataFrame` (columns `last_sh`, `last_sh_pos`, `last_sl`, `last_sl_pos` used); `armed_replay.ArmCandidate(index, direction, level, target, scenario)`, `armed_replay.ArmOutcome(status, resolved_index, kind=None, first_test_index=None)`, `armed_replay.Cell(n, k, b)`; `reaction.Bars.from_frame(df)` — all existing, unchanged.
- Produces: `MSB = "MSB"`, `HL = "HL"`, `TRIGGERS = (MSB, HL)`, `STOP_BUFFER_ATR = 0.10`, `ZONE_FAIL_ATR = 0.10`, `TRIGGERED = "triggered"`, `ZONE_FAILED = "cancelled_zone_failed"`; `StructCell(trigger: str, n: int, k: float)` frozen dataclass with `.cell_id -> str` and `.plan_cell() -> armed_replay.Cell`; `Pivots(sh, sh_pos, sl, sl_pos)` (numpy arrays) with `Pivots.from_frame(df)`; `walk_structure_arm(bars, atr_values, pivots, cand, cell) -> ArmOutcome` returning `ArmOutcome("triggered", j, cell.trigger, i)`, `ArmOutcome("cancelled_zone_failed", j)`, `ArmOutcome("expired", i + N)` or `ArmOutcome("unresolved", None)`. Fixture module: `L`, `T1`, `BASE`, `TEST`, `HOVER`, `RETEST`, `RELEASE`, `MSB_FRAME`, `HL_FRAME`, `CANCEL_FRAME`, `PIVOT_LAG_FRAME`, `mirror`, `frame`, `scenario`, `cand`, `bear_cand`, `walk`, `params`, `structured_df`.

- [ ] **Step 1: Verify v121 is merged — stop if it is not**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot grep -n "def confirmed_pivots\|^PIVOT_COLUMNS\|^PIVOT_K" main -- swingbot/core/market/structure.py
```

Expected: three lines — `PIVOT_K = 3`, `PIVOT_COLUMNS = ("last_sh_pos", "last_sh", "prior_sh_pos", "prior_sh", "last_sl_pos", "last_sl", "prior_sl_pos", "prior_sl")` and `def confirmed_pivots(df: pd.DataFrame, k: int = PIVOT_K) -> pd.DataFrame:`. **If there is no output, or the columns differ, stop and report `BLOCKED: v121 confirmed_pivots is not on main` — do not create a worktree, do not write a local pivot detector.**

- [ ] **Step 2: Create the worktree**

Via the `superpowers:using-git-worktrees` skill: `.claude/worktrees/2026-10-02-v127-structure-break-armed-entries/`, branch `2026-10-02-v127-structure-break-armed-entries`, from `main`. Every later path in Phases 1–2 is inside it.

- [ ] **Step 3: Write the shared fixtures**

Create `tests/backtesting/structure_arm_fixtures.py`:

```python
"""Hand-built frames with known swing structure for the v127 walk (spec §7).

Every frame is flat (100, 101, 99, 100) bars with overrides. Flat highs and
lows are never pivots (a swing high must be STRICTLY above the 3 highs
before it), so the only pivots are the ones an override creates. The arm
candidate sits at bar 25 on a support at L=98.5; with ATR pinned at 1.0
and k=0.25 a bar tests the level when its low is <= 98.75.
"""
import dataclasses

import numpy as np

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import levels, reaction as rx
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

L, T1 = 98.5, 108.0
BASE = (100.0, 101.0, 99.0, 100.0)
TEST = (99.5, 100.0, 98.6, 99.5)              # bar 25: low 98.6 tests L
HOVER = (99.3, 99.6, 99.0, 99.3)              # near the level, never a test, never a release
RETEST = (99.3, 99.6, 98.6, 99.3)             # tests L again
RELEASE = (99.3, 100.4, 99.2, 100.2)          # close 100.2 > L + (0.25 + 1) * 1.0 = 99.75

# MSB: swing high 101.6 at bar 20 (confirmed at 23). Bar 27 closes 101.4
# (below it), bar 28 closes 101.7 (above it) -> the first break is bar 28.
MSB_FRAME = {20: (100.0, 101.6, 99.0, 100.0), 25: TEST,
             27: (100.0, 101.5, 99.0, 101.4), 28: (100.0, 101.9, 99.8, 101.7)}
# HL: MSB_FRAME, then a higher low 98.8 at bar 30 (confirmed at 33) and a
# close 102.1 at bar 34 above the newer swing high 101.9 (bar 28, confirmed 31).
HL_FRAME = {**MSB_FRAME, 30: (100.0, 101.0, 98.8, 100.0), 34: (101.0, 102.3, 100.5, 102.1)}
# Zone failed: bar 27 closes 98.4 < touch low 98.6 - 0.10 * 1.0.
CANCEL_FRAME = {25: TEST, 27: (99.0, 99.2, 98.0, 98.4)}
# Never-confirmed swing high: bar 27's 101.8 is beaten by bar 29's 102.2, so
# only bar 29 is a pivot (confirmed at 32). Bar 29's own close 102.0 > 101.8
# must NOT trigger; bar 33's close 102.4 > 102.2 does.
PIVOT_LAG_FRAME = {25: TEST, 27: (100.0, 101.8, 99.5, 101.0), 28: (101.0, 101.5, 100.5, 101.2),
                   29: (101.2, 102.2, 101.0, 102.0), 33: (101.0, 102.6, 100.8, 102.4)}


def mirror(row):
    """Reflect a bar through 100: the bearish twin of a bullish bar."""
    o, h, l, c = row
    return (200.0 - o, 200.0 - l, 200.0 - h, 200.0 - c)


def frame(overrides, n=40, bearish=False):
    rows = [BASE] * n
    for index, row in overrides.items():
        rows[index] = row
    if bearish:
        rows = [mirror(row) for row in rows]
    return make_ohlcv(rows)


def scenario(direction, stop, target, entry=100.0):
    return levels.Scenario(
        direction=direction, entry=entry, market_price=entry, stop_loss=stop,
        stop_sources=["Rolling S/R"], stop_distance_pct=abs(entry - stop) / entry * 100,
        tight_stop=False, atr_floor_pct=0.0, take_profit=target,
        target_distance_pct=abs(target - entry) / entry * 100,
        target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
        target2_sources=None)


def cand(index=25, direction="bullish", level=L, target=T1):
    return ar.ArmCandidate(index, direction, level, target, scenario(direction, level, target))


def bear_cand(index=25):
    return cand(index, direction="bearish", level=200.0 - L, target=92.0)


def walk(df, c=None, cell=sa.StructCell(sa.MSB, 5, 0.25), atr_values=None):
    atr_values = np.full(len(df), 1.0) if atr_values is None else atr_values
    return sa.walk_structure_arm(rx.Bars.from_frame(df), atr_values, sa.Pivots.from_frame(df),
                                 c or cand(), cell)


def params(**kw):
    base = dict(min_reward_pct=3.0, min_stop_distance_pct=2.0, max_stop_loss_pct=7.0,
                min_target_confluence_count=2, min_risk_reward_ratio=1.5,
                max_risk_reward_ratio=2.5)
    base.update(kw)
    return dataclasses.replace(ScanParams.from_config(), **base)


def structured_df():
    """Trend up, then a 60-bar consolidation -- tests/backtesting/
    test_armed_replay.py's fixture, copied so the files stay independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)
```

- [ ] **Step 4: Write the failing walk tests**

Create `tests/backtesting/test_structure_arm_walk.py`:

```python
import numpy as np
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import reaction as rx
from tests.backtesting.structure_arm_fixtures import (
    CANCEL_FRAME, HL_FRAME, MSB_FRAME, PIVOT_LAG_FRAME, TEST, bear_cand, cand, frame, walk,
)

MSB5, MSB10 = sa.StructCell(sa.MSB, 5, 0.25), sa.StructCell(sa.MSB, 10, 0.25)
HL5, HL10 = sa.StructCell(sa.HL, 5, 0.25), sa.StructCell(sa.HL, 10, 0.25)


def test_cell_id_and_frozen_constants():
    assert sa.StructCell(sa.MSB, 10, 0.25).cell_id == "MSB-N10-k0.25"
    assert sa.StructCell(sa.HL, 5, 0.5).cell_id == "HL-N5-k0.50"
    assert sa.TRIGGERS == ("MSB", "HL")
    assert sa.STOP_BUFFER_ATR == 0.10 and sa.ZONE_FAIL_ATR == 0.10


def test_plan_cell_carries_the_frozen_stop_buffer():
    assert sa.StructCell(sa.HL, 15, 0.5).plan_cell() == ar.Cell(15, 0.5, 0.10)


def test_pivots_come_from_confirmed_pivots():
    pivots = sa.Pivots.from_frame(frame(HL_FRAME))
    assert np.isnan(pivots.sh[22]) and pivots.sh[23] == 101.6 and pivots.sh_pos[23] == 20
    assert pivots.sh[31] == 101.9 and pivots.sh_pos[31] == 28
    assert pivots.sl[28] == 98.6 and pivots.sl_pos[28] == 25
    assert pivots.sl[33] == 98.8 and pivots.sl_pos[33] == 30


def test_msb_triggers_at_the_first_close_above_the_confirmed_swing_high():
    assert walk(frame(MSB_FRAME)) == ar.ArmOutcome("triggered", 28, "MSB", 25)


def test_hl_ignores_the_break_without_a_higher_low_then_triggers_once_confirmed():
    """Bar 28 breaks 101.6, but the only swing low after the test is the
    touch low itself (bar 25, not > i). The higher low at 30 is confirmed
    at 33; bar 34 then closes above the newer swing high 101.9."""
    assert walk(frame(HL_FRAME), cell=MSB5) == ar.ArmOutcome("triggered", 28, "MSB", 25)
    assert walk(frame(HL_FRAME), cell=HL5) == ar.ArmOutcome("expired", 30)
    assert walk(frame(HL_FRAME), cell=HL10) == ar.ArmOutcome("triggered", 34, "HL", 25)


def test_a_close_below_the_touch_low_minus_the_buffer_cancels():
    assert walk(frame(CANCEL_FRAME)) == ar.ArmOutcome("cancelled_zone_failed", 27)


def test_the_cancel_reads_the_touch_low_before_the_bar():
    """Close 98.55 is above 98.6 - 0.10 = 98.5: no cancel, though the bar's
    own low 98.0 is the new touch low."""
    df = frame({25: TEST, 27: (99.0, 99.2, 98.0, 98.55)})
    assert walk(df) == ar.ArmOutcome("expired", 30)


def test_no_trigger_by_i_plus_n_expires_and_a_short_frame_is_unresolved():
    assert walk(frame({25: TEST})) == ar.ArmOutcome("expired", 30)
    assert walk(frame({25: TEST}, n=28)) == ar.ArmOutcome("unresolved", None)


@pytest.mark.parametrize("overrides, cell, expected", [
    (MSB_FRAME, MSB5, ar.ArmOutcome("triggered", 28, "MSB", 25)),
    (HL_FRAME, HL5, ar.ArmOutcome("expired", 30)),
    (HL_FRAME, HL10, ar.ArmOutcome("triggered", 34, "HL", 25)),
    (CANCEL_FRAME, MSB5, ar.ArmOutcome("cancelled_zone_failed", 27)),
    ({25: TEST}, MSB5, ar.ArmOutcome("expired", 30)),
])
def test_bearish_mirrors(overrides, cell, expected):
    assert walk(frame(overrides, bearish=True), c=bear_cand(), cell=cell) == expected


def test_a_swing_high_cannot_trigger_before_it_is_confirmed():
    """Bar 29 closes 102.0 above bar 27's 101.8, but bar 27 is never a
    pivot (bar 29's high beats it). Bar 29 itself is confirmed at 32; the
    first close above 102.2 is bar 33."""
    df = frame(PIVOT_LAG_FRAME)
    out = walk(df, cell=MSB10)
    assert out == ar.ArmOutcome("triggered", 33, "MSB", 25)
    pivots = sa.Pivots.from_frame(df)
    assert np.isnan(pivots.sh[31]) and pivots.sh_pos[32] == 29
    assert out.resolved_index >= pivots.sh_pos[out.resolved_index] + 3


@pytest.mark.parametrize("overrides, cell", [(MSB_FRAME, MSB5), (HL_FRAME, HL10),
                                             (CANCEL_FRAME, MSB5), (PIVOT_LAG_FRAME, MSB10)])
def test_every_outcome_is_identical_on_every_truncation_past_it(overrides, cell):
    """NO-LOOKAHEAD: full.iloc[:t + 1] decides the same as the full frame
    for every t at or after the deciding bar."""
    df = frame(overrides)
    full = walk(df, cell=cell)
    for t in range(full.resolved_index, len(df)):
        assert walk(df.iloc[:t + 1], cell=cell) == full, t


def test_a_cancel_on_the_same_bar_as_a_break_wins():
    """Review focus: the cancel is checked before the trigger. Hand-built
    pivots put a swing high (97.0) under the zone so bar 27 both breaks it
    and fails the zone."""
    df = frame(CANCEL_FRAME)
    n = len(df)
    sh = np.full(n, np.nan)
    sh[27:] = 97.0
    pivots = sa.Pivots(sh, np.where(np.isnan(sh), np.nan, 10.0), np.full(n, np.nan), np.full(n, np.nan))
    out = sa.walk_structure_arm(rx.Bars.from_frame(df), np.full(n, 1.0), pivots, cand(), MSB5)
    assert out == ar.ArmOutcome("cancelled_zone_failed", 27)


def test_a_nan_atr_bar_neither_cancels_nor_crashes():
    """Review focus: ATR14 is NaN early in a frame. NaN comparisons are
    False, so the zone cannot fail on that bar."""
    atr_values = np.full(40, 1.0)
    atr_values[27] = np.nan
    assert walk(frame(CANCEL_FRAME), atr_values=atr_values) == ar.ArmOutcome("expired", 30)
```

- [ ] **Step 5: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_walk.py`
Expected: FAIL — `ImportError: cannot import name 'structure_arm' from 'swingbot.core.backtesting'` (collection error in the fixture import).

- [ ] **Step 6: Implement the walk**

Create `swingbot/core/backtesting/structure_arm.py`:

```python
"""v127: the structure-break armed replay (spec §3).

A confluence scenario's level ARMS at its first test (v88's is_test rule)
and becomes a plan only when price breaks minor swing structure after the
test: a close beyond the last confirmed swing high (MSB), optionally only
after a confirmed higher low (HL). market/reaction.py's R1/R2/R3 shapes are
not used. The population is bounded by a touch-episode rule per level, not
by armed_replay.COOLDOWN_BARS.

Reuses armed_replay's arm_candidates, plan_at (plan construction + every
regate), make_confluence_at and delay_permutations unchanged; v88/v90's
walks in armed_replay.py are not touched.

NO-LOOKAHEAD: every decision at bar j reads bars <= j. Swing pivots come
from market/structure.confirmed_pivots, whose row j knows only pivots
confirmed by bar j (pivot bar p is known from p + PIVOT_K).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swingbot.core.backtesting import armed_replay
from swingbot.core.backtesting.armed_replay import ArmCandidate, ArmOutcome
from swingbot.core.market import reaction
from swingbot.core.market.structure import confirmed_pivots

MSB, HL = "MSB", "HL"
TRIGGERS = (MSB, HL)
STOP_BUFFER_ATR = 0.10       # spec §2.3: b frozen at v88's pre-registered value
ZONE_FAIL_ATR = 0.10         # spec §3.1: cancel when a close breaks the touch low by this
TRIGGERED, ZONE_FAILED = "triggered", "cancelled_zone_failed"


@dataclass(frozen=True)
class StructCell:
    trigger: str   # MSB | HL
    n: int         # arm window, bars after the test bar
    k: float       # test proximity, ATR

    @property
    def cell_id(self) -> str:
        return f"{self.trigger}-N{self.n}-k{self.k:.2f}"

    def plan_cell(self) -> armed_replay.Cell:
        """The v88 Cell plan_at reads: only `.b` is consulted there."""
        return armed_replay.Cell(self.n, self.k, STOP_BUFFER_ATR)


@dataclass(frozen=True, eq=False)
class Pivots:
    """Per-bar confirmed swing structure, as known at that bar."""
    sh: np.ndarray       # last confirmed swing-high price (NaN if none)
    sh_pos: np.ndarray   # its positional index
    sl: np.ndarray       # last confirmed swing-low price
    sl_pos: np.ndarray

    @classmethod
    def from_frame(cls, df) -> "Pivots":
        p = confirmed_pivots(df)
        return cls(*(p[c].to_numpy(dtype=float)
                     for c in ("last_sh", "last_sh_pos", "last_sl", "last_sl_pos")))


def _touch_extreme(bars: reaction.Bars, i: int, j: int, bull: bool) -> float:
    """L_j (bullish: min Low[i..j]) or H_j (bearish: max High[i..j])."""
    return float(bars.low[i:j + 1].min() if bull else bars.high[i:j + 1].max())


def _zone_failed(bars, atr_values, i: int, j: int, bull: bool) -> bool:
    """Close[j] beyond the touch extreme known BEFORE bar j by ZONE_FAIL_ATR.
    The extreme is taken over [i, j-1]: bar j's own low can never sit
    above its own close, so an inclusive extreme could never cancel."""
    prior = _touch_extreme(bars, i, j - 1, bull)
    buffer = ZONE_FAIL_ATR * atr_values[j]
    return bool(bars.close[j] < prior - buffer if bull else bars.close[j] > prior + buffer)


def _broke_structure(bars, pivots: Pivots, j: int, bull: bool) -> bool:
    """MSB: Close[j] beyond the last swing extreme confirmed at j."""
    level = pivots.sh[j] if bull else pivots.sl[j]
    if not np.isfinite(level):
        return False
    return bool(bars.close[j] > level if bull else bars.close[j] < level)


def _higher_low(bars, pivots: Pivots, i: int, j: int, bull: bool) -> bool:
    """HL: the last swing low confirmed at j sits after the test bar and
    above the touch low (bearish: a lower high below the touch high)."""
    pos, price = (pivots.sl_pos[j], pivots.sl[j]) if bull else (pivots.sh_pos[j], pivots.sh[j])
    if not (np.isfinite(pos) and pos > i):
        return False
    extreme = _touch_extreme(bars, i, j, bull)
    return bool(price > extreme if bull else price < extreme)


def _triggered(bars, pivots, cand: ArmCandidate, cell: StructCell, j: int) -> bool:
    bull = cand.direction == "bullish"
    if not _broke_structure(bars, pivots, j, bull):
        return False
    return cell.trigger == MSB or _higher_low(bars, pivots, cand.index, j, bull)


def walk_structure_arm(bars: reaction.Bars, atr_values: np.ndarray, pivots: Pivots,
                       cand: ArmCandidate, cell: StructCell) -> ArmOutcome:
    """Walk one arm opened at its test bar i = cand.index across (i, i + N].

    Per bar j, in this order: the zone-failed cancel, then the trigger.
    No trigger by i + N -> expired at i + N; a window running off the
    frame -> unresolved. A trigger returns ArmOutcome("triggered", j,
    cell.trigger, i) -- first_test_index is the arm bar, which is what
    plan_at anchors the stop's touch low from.
    """
    i, last = cand.index, cand.index + cell.n
    bull = cand.direction == "bullish"
    for j in range(i + 1, min(last, len(bars.close) - 1) + 1):
        if _zone_failed(bars, atr_values, i, j, bull):
            return ArmOutcome(ZONE_FAILED, j)
        if _triggered(bars, pivots, cand, cell, j):
            return ArmOutcome(TRIGGERED, j, cell.trigger, i)
    if last <= len(bars.close) - 1:
        return ArmOutcome("expired", last)
    return ArmOutcome("unresolved", None)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_walk.py`
Expected: `VERDICT: PASS  20 passed`.

The pivot positions the tests pin (`sh_pos[23] == 20`, `sl_pos[33] == 30`, …) follow from v121's pivot contract (strictly above the 3 highs before, `>=` the 3 after, known at `p + 3`). If v121 merged with a different contract and `test_pivots_come_from_confirmed_pivots` fails, **stop and report** — do not edit the expected values to match.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/structure_arm.py`
Expected: no output (every function A or B).

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/backtesting/structure_arm.py tests/backtesting/structure_arm_fixtures.py tests/backtesting/test_structure_arm_walk.py
git commit -m "feat(v127): structure-break armed walk (MSB / HL, zone-failed cancel)"
```

---

### Task V127-2: Touch episodes and the per-cell replay

**Files:**
- Modify: `swingbot/core/backtesting/structure_arm.py` (import block; append after `walk_structure_arm`)
- Test: `tests/backtesting/test_structure_arm_replay.py`

**Interfaces:**
- Consumes: V127-1's `StructCell`, `Pivots`, `walk_structure_arm`, `TRIGGERED`; `armed_replay.arm_candidates(ticker, df, horizon_key, *, params, level_cache) -> dict[int, list[ArmCandidate]]`, `armed_replay.plan_at(ticker, df, horizon_key, cand, *, j, first_test_index, cell, bars, atr_values, params, level_map_at, confluence_at) -> (plan | None, reason)`, `armed_replay.make_confluence_at(df, horizon_key)`, `backtest_scenarios.levels_asof`, `reaction.is_test` — existing, unchanged. **No change to `armed_replay.py`:** `plan_at` reads only `cell.b` from the `Cell` it is handed, so `StructCell.plan_cell()` supplies `Cell(n, k, 0.10)`.
- Produces: `released(bars, atr_values, level, direction, k, start, stop) -> bool`; `level_key(cand) -> tuple`; `StructCellResult` with `issued: list[(trigger index, plan, trigger)]`, `confirmed: list[(ArmCandidate, ArmOutcome)]` (issued or regated), `counts: Counter`, `arms: list[(arm index, end index | None, status-or-plan-reason)]`; `replay_structure(ticker, df, horizon_key, cells, *, params=None, candidates=None, level_cache=None, level_map_at=None, confluence_at=None) -> dict[cell_id, StructCellResult]`. Counts keys: `armed`, `issued`, `regate_*`, `cancelled_zone_failed`, `expired`, `unresolved`.

- [ ] **Step 1: Write the failing replay tests**

Create `tests/backtesting/test_structure_arm_replay.py`:

```python
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import levels, reaction as rx
from swingbot.core.planning.plan_engine import PlanStatus
from tests.backtesting.structure_arm_fixtures import (
    HOVER, L, MSB_FRAME, RELEASE, RETEST, T1, TEST, cand, frame, params, structured_df,
)

MSB5 = sa.StructCell(sa.MSB, 5, 0.25)


@pytest.fixture
def flat_atr(monkeypatch):
    """Pin ATR14 at 1.0 so the fixture geometry is exact."""
    monkeypatch.setattr(sa, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))


def _replay(df, candidates, cell=MSB5, resistances=(T1,), confluence=3):
    res = [levels.Level(p, ["Fibonacci"]) for p in resistances]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    out = sa.replay_structure("AAPL", df, "4w", [cell], params=params(), candidates=candidates,
                              level_map_at=lambda j: (sup, res),
                              confluence_at=lambda j, entry, target: confluence)
    return out[cell.cell_id]


def _episode_frame(release=True):
    """Arm at 25 expires at 30; 31 re-tests L (no release yet); 33 closes
    100.2, releasing L; 38 re-tests L. HOVER bars never test, never release."""
    overrides = {i: HOVER for i in range(25, 50)}
    overrides.update({25: TEST, 31: RETEST, 33: RELEASE if release else HOVER, 38: RETEST})
    return frame(overrides, n=50)


def test_released_needs_a_close_beyond_k_plus_one_atr_in_the_trades_favour():
    df = _episode_frame()
    bars, atr_values = rx.Bars.from_frame(df), np.full(len(df), 1.0)
    assert not sa.released(bars, atr_values, L, "bullish", 0.25, 31, 33)   # [31, 33) misses 33
    assert sa.released(bars, atr_values, L, "bullish", 0.25, 31, 34)
    assert not sa.released(bars, atr_values, L, "bullish", 0.25, 34, 34)   # empty range
    bear = frame({i: HOVER for i in range(25, 50)} | {33: RELEASE}, n=50, bearish=True)
    bear_bars = rx.Bars.from_frame(bear)
    assert not sa.released(bear_bars, atr_values, 200.0 - L, "bearish", 0.25, 31, 33)
    assert sa.released(bear_bars, atr_values, 200.0 - L, "bearish", 0.25, 31, 34)


def test_touch_episode_blocks_an_immediate_retest_and_releases_after_a_departure(flat_atr):
    other = cand(31, level=98.8)
    cands = {25: [cand(25)], 31: [cand(31), other], 38: [cand(38)]}
    result = _replay(_episode_frame(), cands)
    # 31 (same level, no release yet) is blocked; the different level at 31
    # arms on its own; 38 re-arms L after bar 33's release close.
    assert result.arms == [(25, 30, "expired"), (31, 36, "expired"), (38, 43, "expired")]
    assert result.counts["armed"] == 3 and result.counts["expired"] == 3


def test_without_a_release_close_the_level_never_re_arms(flat_atr):
    cands = {25: [cand(25)], 31: [cand(31), cand(31, level=98.8)], 38: [cand(38)]}
    result = _replay(_episode_frame(release=False), cands)
    assert result.arms == [(25, 30, "expired"), (31, 36, "expired")]


def test_cooldown_bars_is_not_consulted(flat_atr):
    """v88 would skip an arm 2 bars after an issuance (COOLDOWN_BARS = 5).
    Here a different level arms at 30, two bars after the plan at 28."""
    result = _replay(frame(MSB_FRAME), {25: [cand(25)], 30: [cand(30, level=98.8)]})
    assert result.arms == [(25, 28, "issued"), (30, 35, "expired")]


def test_one_live_arm_per_direction_and_directions_are_independent(flat_atr):
    df = _episode_frame()
    busy = _replay(df, {25: [cand(25)], 27: [cand(27, level=98.8)]})
    assert busy.arms == [(25, 30, "expired")]
    both = _replay(df, {25: [cand(25)],
                        27: [cand(27, direction="bearish", level=99.7, target=90.0)]})
    assert both.arms == [(25, 30, "expired"), (27, 32, "expired")]


def test_a_candidate_whose_bar_does_not_test_never_arms(flat_atr):
    assert _replay(_episode_frame(), {26: [cand(26)]}).arms == []


def test_an_arm_running_off_the_frame_is_unresolved_and_holds_the_direction(flat_atr):
    """Review focus: the last arm of a frame never resolves."""
    result = _replay(frame({25: TEST}, n=28), {25: [cand(25)], 27: [cand(27, level=98.8)]})
    assert result.arms == [(25, None, "unresolved")]
    assert result.counts["unresolved"] == 1


def test_a_nan_atr_frame_arms_nothing(monkeypatch):
    """Review focus: reaction.is_test refuses a NaN ATR, so no arm opens."""
    monkeypatch.setattr(sa, "atr", lambda df, period=14: pd.Series(np.nan, index=df.index))
    assert _replay(_episode_frame(), {25: [cand(25)]}).arms == []


def test_a_trigger_issues_a_stop_entry_at_the_trigger_bar_high(flat_atr, monkeypatch):
    # Pins the pre-clamp geometry; the clamp's own effect is the next test.
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    df = frame(MSB_FRAME)
    result = _replay(df, {25: [cand(25)]})
    assert result.counts["issued"] == 1 and len(result.confirmed) == 1
    j, plan, trigger = result.issued[0]
    assert (j, trigger) == (28, "MSB")
    assert plan.entry_type == "stop_entry" and plan.entry_price is None
    assert plan.trigger_price == pytest.approx(101.9)              # High[28]
    assert plan.expiry_bars == ar.STOP_ENTRY_EXPIRY_BARS == 2
    assert plan.stop_loss == pytest.approx(98.4)                   # min(98.5, 98.6) - 0.10 * 1.0
    assert plan.tp1 == pytest.approx(108.0)                        # 1.74R, inside [1.5, 2.5]
    assert plan.status == PlanStatus.PENDING and plan.status_history == []
    assert plan.created_at == df.index[28].date().isoformat()


def test_the_live_hard_cap_clamp_applies_unchanged(flat_atr, monkeypatch):
    """Spec §3.1: the clamp applies exactly as live -- a 3.4% stop is
    clamped to 1.75% under the 101.9 trigger."""
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    _, plan, _ = _replay(frame(MSB_FRAME), {25: [cand(25)]}).issued[0]
    assert plan.stop_loss == pytest.approx(101.9 * (1 - 0.0175))


def test_regates_are_counted_and_still_count_as_triggered(flat_atr, monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    result = _replay(frame(MSB_FRAME), {25: [cand(25)]}, confluence=1)
    assert result.arms == [(25, 28, "regate_confluence")]
    assert result.issued == [] and len(result.confirmed) == 1      # the permutation population
    assert _replay(frame(MSB_FRAME), {25: [cand(25)]}, resistances=()).arms == [
        (25, 28, "regate_no_target")]


def test_replay_never_reads_past_the_deciding_bar():
    """NO-LOOKAHEAD on the real pipeline (arm_candidates, levels_asof,
    confirmed_pivots, plan_at): every arm resolved and every plan issued at
    j <= t is identical on the full frame and on full.iloc[:t + 1]."""
    df = structured_df()
    p = params(min_target_confluence_count=1, min_stop_distance_pct=0.5,
               max_stop_loss_pct=15.0, min_reward_pct=1.0)
    cells = [sa.StructCell(sa.MSB, 10, 0.5), sa.StructCell(sa.HL, 15, 0.5)]
    full = sa.replay_structure("AAPL", df, "4w", cells, params=p)
    assert full["MSB-N10-k0.50"].counts["issued"] >= 1, "fixture must issue at least once"

    def signature(result, t):
        plans = sorted((j, k, pl.direction, round(pl.trigger_price, 6), round(pl.stop_loss, 6),
                        round(pl.tp1, 6)) for j, pl, k in result.issued if j <= t)
        return plans, [a for a in result.arms if a[1] is not None and a[1] <= t]

    for t in (len(df) - 2, len(df) - 15, len(df) - 30):
        trunc = sa.replay_structure("AAPL", df.iloc[:t + 1], "4w", cells, params=p)
        for cell in cells:
            assert signature(full[cell.cell_id], t) == signature(trunc[cell.cell_id], t), (t, cell)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_replay.py`
Expected: FAIL — `AttributeError: module 'swingbot.core.backtesting.structure_arm' has no attribute 'replay_structure'` (and `'released'`, `'atr'`).

- [ ] **Step 3: Widen the import block**

In `swingbot/core/backtesting/structure_arm.py`, replace the import block (from `from __future__ import annotations` through `from swingbot.core.market.structure import confirmed_pivots`) with:

```python
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from swingbot.core.backtesting import armed_replay
from swingbot.core.backtesting.armed_replay import ArmCandidate, ArmOutcome
from swingbot.core.backtesting.backtest_scenarios import levels_asof
from swingbot.core.market import reaction
from swingbot.core.market.indicators import atr
from swingbot.core.market.structure import confirmed_pivots
from swingbot.scan_params import ScanParams
```

- [ ] **Step 4: Append the replay**

Append to `swingbot/core/backtesting/structure_arm.py`, after `walk_structure_arm`:

```python
def released(bars: reaction.Bars, atr_values: np.ndarray, level: float, direction: str,
             k: float, start: int, stop: int) -> bool:
    """Did any bar in [start, stop) close more than (k + 1) * ATR14 from
    `level` in the trade's favour (above a support, below a resistance)?"""
    if stop <= start:
        return False
    close = bars.close[start:stop]
    reach = (k + 1.0) * atr_values[start:stop]
    with np.errstate(invalid="ignore"):
        away = close > level + reach if direction == "bullish" else close < level - reach
    return bool(np.any(away))


def level_key(cand: ArmCandidate) -> tuple:
    return (cand.direction, round(cand.level, 6))


@dataclass
class StructCellResult:
    issued: list = field(default_factory=list)      # (trigger index, plan, trigger)
    confirmed: list = field(default_factory=list)   # (ArmCandidate, ArmOutcome), issued or regated
    counts: Counter = field(default_factory=Counter)
    arms: list = field(default_factory=list)        # (arm index, end index | None, status or plan reason)


@dataclass
class _Frame:
    """Everything one (ticker, horizon) frame shares across cells."""
    ticker: str
    df: object
    horizon_key: str
    bars: reaction.Bars
    atr_values: np.ndarray
    pivots: Pivots
    params: ScanParams
    level_map_at: object
    confluence_at: object


class _Episodes:
    """Touch-episode bookkeeping (spec §3.1): a level whose arm terminated
    re-arms only after a release close. `pending[key]` is the first bar
    not yet scanned for that release."""

    def __init__(self, fr: _Frame, k: float):
        self.fr, self.k, self.pending = fr, k, {}

    def blocked(self, cand: ArmCandidate) -> bool:
        key = level_key(cand)
        if key not in self.pending:
            return False
        start = self.pending[key]
        if released(self.fr.bars, self.fr.atr_values, cand.level, cand.direction,
                    self.k, start, cand.index):
            del self.pending[key]
            return False
        self.pending[key] = max(start, cand.index)
        return True

    def close(self, cand: ArmCandidate, end: int) -> None:
        self.pending[level_key(cand)] = end + 1


def _issue(fr: _Frame, cand, outcome, cell: StructCell, result: StructCellResult) -> str:
    result.confirmed.append((cand, outcome))
    plan, reason = armed_replay.plan_at(
        fr.ticker, fr.df, fr.horizon_key, cand, j=outcome.resolved_index,
        first_test_index=outcome.first_test_index, cell=cell.plan_cell(),
        bars=fr.bars, atr_values=fr.atr_values, params=fr.params,
        level_map_at=fr.level_map_at, confluence_at=fr.confluence_at)
    if plan is not None:
        result.issued.append((outcome.resolved_index, plan, cell.trigger))
    return reason


def _arm(fr: _Frame, cand, cell: StructCell, result: StructCellResult) -> ArmOutcome:
    outcome = walk_structure_arm(fr.bars, fr.atr_values, fr.pivots, cand, cell)
    status = outcome.status
    if status == TRIGGERED:
        status = _issue(fr, cand, outcome, cell, result)
    result.counts["armed"] += 1
    result.counts[status] += 1
    result.arms.append((cand.index, outcome.resolved_index, status))
    return outcome


def _replay_cell(fr: _Frame, candidates: dict, cell: StructCell) -> StructCellResult:
    result = StructCellResult()
    busy_until: dict[str, int] = {}
    episodes = _Episodes(fr, cell.k)
    for i in sorted(candidates):
        for cand in candidates[i]:
            if i <= busy_until.get(cand.direction, -1) or episodes.blocked(cand):
                continue
            if not reaction.is_test(fr.bars, i, cand.level, cand.direction, cell.k,
                                    fr.atr_values[i]):
                continue
            outcome = _arm(fr, cand, cell, result)
            end = len(fr.df) if outcome.resolved_index is None else outcome.resolved_index
            busy_until[cand.direction] = end
            episodes.close(cand, end)
    return result


def replay_structure(ticker: str, df, horizon_key: str, cells, *, params: ScanParams | None = None,
                     candidates: dict | None = None, level_cache: dict | None = None,
                     level_map_at=None, confluence_at=None) -> dict:
    """Every cell's arms and issued plans over one (ticker, horizon) frame.

    An arm opens at a bar where an arm candidate's own bar tests its level
    (reaction.is_test at k). One live arm per direction (v88's
    exclusivity); a level whose arm terminated waits for a release close
    (_Episodes). COOLDOWN_BARS is not consulted. Candidates, the level
    cache, the confluence memo and the pivots are shared across cells.
    """
    if params is None:
        params = ScanParams.from_config()
    cache = {} if level_cache is None else level_cache
    if candidates is None:
        candidates = armed_replay.arm_candidates(ticker, df, horizon_key, params=params,
                                                 level_cache=cache)
    if level_map_at is None:
        level_map_at = lambda j: levels_asof(ticker, df, j, horizon_key, cache)  # noqa: E731
    if confluence_at is None:
        confluence_at = armed_replay.make_confluence_at(df, horizon_key)
    fr = _Frame(ticker, df, horizon_key, reaction.Bars.from_frame(df),
                atr(df, 14).to_numpy(dtype=float), Pivots.from_frame(df), params,
                level_map_at, confluence_at)
    return {cell.cell_id: _replay_cell(fr, candidates, cell) for cell in cells}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_replay.py`
Expected: `VERDICT: PASS  12 passed`. Also re-run `tests/backtesting/test_structure_arm_walk.py` (20 passed) and `tests/backtesting/test_armed_replay.py` (26 passed, unchanged file).

`test_replay_never_reads_past_the_deciding_bar` runs the real pipeline (`arm_candidates`, `levels_asof`, `confirmed_pivots`, `plan_at`) on the 180-bar fixture; prototyped at ~1s per replay, it is not marked slow. Prototype funnel on that fixture for `MSB-N10-k0.50`: 19 armed — 2 issued (bars 69, 137), 1 `regate_no_target`, 7 `cancelled_zone_failed`, 7 `expired`, 2 `unresolved`. The test asserts only `issued >= 1`; quote the funnel if it differs, do not tune the fixture.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/structure_arm.py`
Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/backtesting/structure_arm.py tests/backtesting/test_structure_arm_replay.py
git commit -m "feat(v127): touch-episode bookkeeping and the per-cell structure replay"
```

---

### Task V127-3: The random-delay permutation population

**Files:**
- Modify: `swingbot/core/backtesting/structure_arm.py` (append)
- Test: `tests/backtesting/test_structure_arm_permutation.py`

**Interfaces:**
- Consumes: V127-2's `StructCellResult.confirmed`; `armed_replay.delay_permutations(ticker, df, horizon_key, cell, confirmed, *, n, seed, level_cache, params=None, level_map_at=None, confluence_at=None) -> list[list[(entry_date, strategy, horizon_key, outcome)]]` — existing, unchanged. Its seed is `[seed, crc32("ticker|horizon")]`, its draw `[cand.index, min(cand.index + cell.n, last bar)]`, its first-test scan starts at `cand.index` — which is v127's test bar, so the stop always anchors from `i`.
- Produces: `structure_permutations(ticker, df, horizon_key, cell: StructCell, confirmed, *, n, seed, level_cache, params=None, level_map_at=None, confluence_at=None) -> list` (same shape as `delay_permutations`).

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_structure_arm_permutation.py`:

```python
import pandas as pd
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import structure_arm as sa
from swingbot.core.market import levels
from tests.backtesting.structure_arm_fixtures import MSB_FRAME, T1, cand, frame, params

CELL = sa.StructCell(sa.MSB, 5, 0.25)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(ar, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))
    df = frame(MSB_FRAME, n=45)
    confirmed = [(cand(25), ar.ArmOutcome("triggered", 28, "MSB", 25))]
    res, sup = [levels.Level(T1, ["Fibonacci"])], [levels.Level(90.0, ["Rolling S/R"])]
    kwargs = dict(level_cache={}, params=params(),
                  level_map_at=lambda j: (sup, res), confluence_at=lambda *a: 3)
    return df, confirmed, kwargs


def test_seed_42_is_deterministic_and_draws_stay_in_the_arm_window(setup):
    df, confirmed, kwargs = setup
    first = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    again = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    assert first == again and len(first) == 50
    window = {df.index[j].date().isoformat() for j in range(25, 31)}     # [i, i + N]
    assert all(len(perm) <= 1 for perm in first)
    assert all(row[0] in window and row[1].startswith("confluence:") and row[2] == "4w"
               for perm in first for row in perm)


def test_a_different_seed_draws_differently(setup):
    df, confirmed, kwargs = setup
    a = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=42, **kwargs)
    b = sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=50, seed=43, **kwargs)
    assert a != b


def test_every_draw_anchors_the_stop_at_the_arm_bar_with_the_frozen_buffer(setup, monkeypatch):
    """The arm bar IS the test bar, so delay_permutations' first-test scan
    returns i for every drawn bar, and plan_at sees b = 0.10."""
    df, confirmed, kwargs = setup
    seen = {}
    real = ar.plan_at

    def spy(*a, **k):
        seen[k["j"]] = (k["first_test_index"], k["cell"].b)
        return real(*a, **k)

    monkeypatch.setattr(ar, "plan_at", spy)
    sa.structure_permutations("AAPL", df, "4w", CELL, confirmed, n=200, seed=1, **kwargs)
    assert set(seen) <= set(range(25, 31)) and len(seen) >= 2
    assert set(seen.values()) == {(25, 0.10)}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_permutation.py`
Expected: FAIL — `AttributeError: ... has no attribute 'structure_permutations'`.

- [ ] **Step 3: Append the permutation**

Append to `swingbot/core/backtesting/structure_arm.py`:

```python
def structure_permutations(ticker: str, df, horizon_key: str, cell: StructCell, confirmed, *,
                           n: int, seed: int, level_cache: dict, params: ScanParams | None = None,
                           level_map_at=None, confluence_at=None) -> list:
    """Spec §4.2's random-delay null: armed_replay.delay_permutations over
    the arms that triggered, with v127's frozen stop buffer. Each arm's
    candidate index IS its test bar, so delay_permutations' first-test scan
    anchors the stop at the arm bar and draws from [i, min(i + N, last)]."""
    return armed_replay.delay_permutations(
        ticker, df, horizon_key, cell.plan_cell(), confirmed, n=n, seed=seed,
        level_cache=level_cache, params=params, level_map_at=level_map_at,
        confluence_at=confluence_at)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_arm_permutation.py`
Expected: `VERDICT: PASS  3 passed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/structure_arm.py tests/backtesting/test_structure_arm_permutation.py
git commit -m "feat(v127): random-delay permutation over triggered structure arms"
```

---

### Task V127-4: The 12-cell grid, selection and population disclosure

**Files:**
- Create: `swingbot/core/backtesting/structure_measurement.py`
- Test: `tests/backtesting/test_structure_measurement.py`

**Interfaces:**
- Consumes: V127-1's `StructCell`, `TRIGGERS`; `armed_measurement.score_cell(rows, cell) -> CellScore` (reads only `cell.cell_id`), `Selection`, `Row`, `in_window`, `arm_trades`, `arms_blob`, `folds_blob`, `permutation_p`, the window/permutation constants and `LIMITATIONS`; `backtest_wf.plateau_report(param_name, grid, expectancies, adopted_value) -> dict` — existing, unchanged. `armed_measurement.CELLS` (v90's 30 cells) is not touched.
- Produces: `N_GRID = (5, 10, 15)`, `K_GRID = (0.25, 0.5)`, `CELLS` (12 `StructCell`s, trigger-major), `FUNNEL_COLUMNS = ("armed", "issued", "regated", "cancelled_zone_failed", "expired", "unresolved")`, `SELECTION_RULE`; `cell_by_id(cell_id) -> StructCell`; `select_cell(rows, cells=CELLS) -> Selection` (plateau params `STRUCT_N`, `STRUCT_K`); `trigger_rows(selection) -> list[CellScore]`; `funnel(arm_records, window) -> dict[cell_id, dict[column, int]]` where a record is `{"cell", "horizon", "arm_date", "status"}`; `render_selection_md(selection, funnel_counts) -> str`. Re-exports `BASELINE`, `FOLD_TEST_YEARS`, `LIMITATIONS`, `MDE_TARGET_DAYS`, `NO_ELIGIBLE_CELL`, `PERMUTATION_N`, `PERMUTATION_SEED`, `RUN1_WINDOW`, `SELECTED`, `SELECTION_OBSERVED_DAYS`, `SELECTION_WINDOW`, `SPIKE`, `VALIDATION_WINDOW`, `Row`, `Selection`, `arm_trades`, `arms_blob`, `folds_blob`, `in_window`, `permutation_p` for the script.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_structure_measurement.py`:

```python
import pytest

from swingbot.core.backtesting import armed_measurement as am
from swingbot.core.backtesting import structure_measurement as sm
from swingbot.core.backtesting.acceptance import ArmTrade


def _trades(arm, wins, losses, kind=None, date="2019-03-01"):
    return [sm.Row(arm, ArmTrade("AAA", "confluence:Fib", "4w", date, o, r, 2.0), kind)
            for o, r in [("win", 1.5)] * wins + [("loss", -1.0)] * losses]


def _rows(component=(6, 3), override=None):
    """Baseline 5W/5L; every cell `component` (W, L) unless overridden."""
    rows = _trades(sm.BASELINE, 5, 5)
    for cell in sm.CELLS:
        wins, losses = (override or {}).get(cell.cell_id, component)
        rows += _trades(cell.cell_id, wins, losses, kind=cell.trigger)
    return rows


def test_the_grid_is_the_pre_registered_twelve_cells():
    assert sm.N_GRID == (5, 10, 15) and sm.K_GRID == (0.25, 0.5)
    assert [c.cell_id for c in sm.CELLS] == [
        "MSB-N5-k0.25", "MSB-N5-k0.50", "MSB-N10-k0.25", "MSB-N10-k0.50",
        "MSB-N15-k0.25", "MSB-N15-k0.50", "HL-N5-k0.25", "HL-N5-k0.50",
        "HL-N10-k0.25", "HL-N10-k0.50", "HL-N15-k0.25", "HL-N15-k0.50"]


def test_windows_and_permutation_constants_are_v90s():
    assert sm.SELECTION_WINDOW == ("2018-06-01", "2020-12-31")
    assert sm.FOLD_TEST_YEARS == ("2021", "2022", "2023")
    assert sm.VALIDATION_WINDOW == ("2024-01-01", "2025-12-31")
    assert (sm.PERMUTATION_N, sm.PERMUTATION_SEED) == (200, 42)
    assert (sm.SELECTION_OBSERVED_DAYS, sm.MDE_TARGET_DAYS) == (945, 730)


def test_v90s_grid_is_untouched():
    assert len(am.CELLS) == 30 and am.CELLS[0].cell_id == "N3-k0.25-b0.00"


def test_cell_by_id_round_trips_and_rejects_unknown_ids():
    assert sm.cell_by_id("HL-N10-k0.50") == sm.CELLS[9]
    with pytest.raises(KeyError):
        sm.cell_by_id("N10-k0.50-b0.10")


def test_flat_eligible_grid_selects_the_first_cell_on_a_plateau():
    selection = sm.select_cell(_rows())
    assert selection.verdict == sm.SELECTED and selection.selected == "MSB-N5-k0.25"
    assert [p["param"] for p in selection.plateaus] == ["STRUCT_N", "STRUCT_K"]
    assert all(p["is_plateau"] for p in selection.plateaus)
    score = {s.cell_id: s for s in selection.scores}["MSB-N5-k0.25"]
    assert score.volume_cut_pct == pytest.approx(10.0)
    assert score.delta_win_rate_pp == pytest.approx(16.6667, abs=1e-4)
    assert score.delta_expectancy_r == pytest.approx(0.416667, abs=1e-6)


def test_a_lone_peak_is_a_spike():
    """MSB-N10-k0.25 at 7W/2L (ExpR 0.944) beside 6W/3L (0.667) neighbours."""
    selection = sm.select_cell(_rows(override={"MSB-N10-k0.25": (7, 2)}))
    assert selection.verdict == sm.SPIKE and selection.selected is None
    assert selection.best == "MSB-N10-k0.25"
    assert [p["is_plateau"] for p in selection.plateaus] == [False, False]


def test_trigger_is_categorical_and_both_rows_are_reported():
    """HL beats MSB everywhere by the same margin: a plateau across N and k,
    selected, with both trigger rows at the pick's N and k."""
    override = {c.cell_id: (7, 2) for c in sm.CELLS if c.trigger == "HL"}
    selection = sm.select_cell(_rows(override=override))
    assert selection.verdict == sm.SELECTED and selection.selected == "HL-N5-k0.25"
    assert [s.cell_id for s in sm.trigger_rows(selection)] == ["MSB-N5-k0.25", "HL-N5-k0.25"]


def test_a_negative_dwr_is_never_eligible_at_any_expectancy():
    selection = sm.select_cell(_rows(component=(4, 5)))
    assert selection.verdict == sm.NO_ELIGIBLE_CELL and selection.best is None
    assert sm.trigger_rows(selection) == []


def test_a_volume_cut_over_25_percent_is_ineligible():
    selection = sm.select_cell(_rows(component=(5, 2)))
    assert selection.verdict == sm.NO_ELIGIBLE_CELL
    assert selection.scores[0].reasons == ("volume: cut 30.00% > 25.0%",)


def test_funnel_buckets_regates_and_windows_by_arm_date():
    recs = [{"cell": "MSB-N5-k0.25", "horizon": "4w", "arm_date": d, "status": s} for d, s in [
        ("2019-03-01", "issued"), ("2019-03-02", "regate_reward"),
        ("2019-03-03", "regate_no_target"), ("2019-03-04", "cancelled_zone_failed"),
        ("2019-03-05", "expired"), ("2021-03-05", "expired")]]
    recs.append({"cell": "HL-N15-k0.50", "horizon": "4w", "arm_date": "2020-12-31",
                 "status": "unresolved"})
    funnel = sm.funnel(recs, sm.SELECTION_WINDOW)
    assert funnel["MSB-N5-k0.25"] == {"armed": 5, "issued": 1, "regated": 2,
                                      "cancelled_zone_failed": 1, "expired": 1, "unresolved": 0}
    assert funnel["HL-N15-k0.50"]["unresolved"] == 1
    assert funnel["HL-N5-k0.25"]["armed"] == 0 and len(funnel) == 12


def test_selection_markdown_carries_rule_limitations_plateaus_and_disclosure():
    selection = sm.select_cell(_rows())
    md = sm.render_selection_md(selection, sm.funnel([], sm.SELECTION_WINDOW))
    assert "**Verdict: SELECTED**" in md and "## All 12 cells" in md
    assert sm.SELECTION_RULE in md and sm.LIMITATIONS in md
    assert "STRUCT_N" in md and "STRUCT_K" in md
    assert "## Population disclosure" in md and "alert-volume ratio" in md
    assert "| MSB-N5-k0.25 | 0 | 0 | 0 | 0 | 0 | 0 | 0.900 |" in md
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_measurement.py`
Expected: FAIL — `ImportError: cannot import name 'structure_measurement'`.

- [ ] **Step 3: Implement the module**

Create `swingbot/core/backtesting/structure_measurement.py`:

```python
"""Pre-registered v127 structure-break armed-entry measurement (spec §3.3, §4).

The constants below ARE the pre-registration. None is a config.Field, so
no search can sweep them, and none may change after a number is seen.
Scoring, the selection-rule arithmetic, the fold/arms blobs and the
permutation p are armed_measurement's, reused unchanged; this module adds
only the 12-cell grid, the categorical `trigger` axis and the population
disclosure. v90's grid (armed_measurement.CELLS) is not touched.
"""
from __future__ import annotations

import dataclasses
from collections import Counter

from swingbot.core.backtesting import armed_measurement as am
from swingbot.core.backtesting.armed_measurement import (  # noqa: F401  (re-exported for the script)
    BASELINE, FOLD_TEST_YEARS, LIMITATIONS, MDE_TARGET_DAYS, NO_ELIGIBLE_CELL,
    PERMUTATION_N, PERMUTATION_SEED, RUN1_WINDOW, SELECTED, SELECTION_OBSERVED_DAYS,
    SELECTION_WINDOW, SPIKE, VALIDATION_WINDOW, Row, Selection, arm_trades, arms_blob,
    folds_blob, in_window, permutation_p,
)
from swingbot.core.backtesting.backtest_wf import plateau_report
from swingbot.core.backtesting.structure_arm import TRIGGERS, StructCell

N_GRID = (5, 10, 15)
K_GRID = (0.25, 0.5)
CELLS = tuple(StructCell(t, n, k) for t in TRIGGERS for n in N_GRID for k in K_GRID)
FUNNEL_COLUMNS = ("armed", "issued", "regated", "cancelled_zone_failed", "expired", "unresolved")

SELECTION_RULE = (
    "A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), "
    "ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible "
    "cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. "
    "The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along N and "
    "along k with the other knobs held; any spike disqualifies. `trigger` is categorical: "
    "both trigger rows at the selected N and k are reported, not plateau-checked."
)


def cell_by_id(cell_id: str) -> StructCell:
    for cell in CELLS:
        if cell.cell_id == cell_id:
            return cell
    raise KeyError(cell_id)


def _plateau(best: StructCell, scores: dict, knob: str, grid) -> dict:
    expectancies = []
    for value in grid:
        score = scores.get(dataclasses.replace(best, **{knob: value}).cell_id)
        value_r = None if score is None else score.component_expectancy_r
        expectancies.append(float("nan") if value_r is None else value_r)
    return plateau_report(f"STRUCT_{knob.upper()}", list(grid), expectancies, getattr(best, knob))


def select_cell(rows, cells=CELLS) -> Selection:
    scores = {cell.cell_id: am.score_cell(rows, cell) for cell in cells}
    eligible = [cell for cell in cells if scores[cell.cell_id].eligible]
    if not eligible:
        return Selection(tuple(scores.values()), None, None, (), NO_ELIGIBLE_CELL)
    best = max(eligible, key=lambda c: (scores[c.cell_id].delta_expectancy_r,
                                        scores[c.cell_id].delta_win_rate_pp, -c.n))
    plateaus = (_plateau(best, scores, "n", N_GRID), _plateau(best, scores, "k", K_GRID))
    on_plateau = all(p["is_plateau"] for p in plateaus)
    return Selection(tuple(scores.values()), best.cell_id if on_plateau else None,
                     best.cell_id, plateaus, SELECTED if on_plateau else SPIKE)


def trigger_rows(selection: Selection) -> list:
    """Both triggers' scores at the rule's pick's N and k (spec §4.1)."""
    if selection.best is None:
        return []
    best = cell_by_id(selection.best)
    wanted = {dataclasses.replace(best, trigger=t).cell_id for t in TRIGGERS}
    return [s for s in selection.scores if s.cell_id in wanted]


def _bucket(status: str) -> str:
    return "regated" if status.startswith("regate_") else status


def funnel(arm_records, window) -> dict:
    """Per cell: arms opened in `window` by how they ended (spec §4.3)."""
    out = {cell.cell_id: Counter() for cell in CELLS}
    for rec in arm_records:
        if window[0] <= rec["arm_date"] <= window[1] and rec["cell"] in out:
            out[rec["cell"]]["armed"] += 1
            out[rec["cell"]][_bucket(rec["status"])] += 1
    return {cell_id: {col: counts.get(col, 0) for col in FUNNEL_COLUMNS}
            for cell_id, counts in out.items()}


def _fmt(value, spec):
    return "n/a" if value is None else format(value, spec)


def _score_line(s) -> str:
    return (f"| {s.cell_id} | {s.baseline_n} | {s.component_n} | {s.volume_cut_pct:+.2f} | "
            f"{_fmt(s.delta_win_rate_pp, '+.2f')} | {_fmt(s.delta_expectancy_r, '+.4f')} | "
            f"{_fmt(s.component_expectancy_r, '+.4f')} | {'yes' if s.eligible else 'no'} | "
            f"{'; '.join(s.reasons)} |")


_SCORE_HEAD = ["| cell | baseline N | component N | cut % | ΔWR pp | ΔExpR R | ExpR R | eligible | reasons |",
               "|---|---|---|---|---|---|---|---|---|"]


def _funnel_lines(selection: Selection, funnel_counts: dict) -> list:
    ratios = {s.cell_id: (s.component_n / s.baseline_n if s.baseline_n else None)
              for s in selection.scores}
    lines = ["## Population disclosure (arms opened in the selection window)", "",
             "| cell | " + " | ".join(FUNNEL_COLUMNS) + " | alert-volume ratio |",
             "|---|" + "---|" * (len(FUNNEL_COLUMNS) + 1)]
    for cell_id, counts in funnel_counts.items():
        lines.append(f"| {cell_id} | " + " | ".join(str(counts[c]) for c in FUNNEL_COLUMNS)
                     + f" | {_fmt(ratios.get(cell_id), '.3f')} |")
    return lines


def _plateau_lines(selection: Selection) -> list:
    if not selection.plateaus:
        return []
    lines = ["## Plateau reports (N and k; trigger is categorical)", ""]
    for p in selection.plateaus:
        lines.append(f"- {p['param']}: grid {p['grid']}, expectancies "
                     f"{[round(e, 4) for e in p['expectancies']]}, adopted {p['adopted']}, "
                     f"plateau {p['is_plateau']}")
    lines += ["", "## Both triggers at the pick's N and k (not plateau-checked)", "", *_SCORE_HEAD]
    lines += [_score_line(s) for s in trigger_rows(selection)]
    return lines + [""]


def render_selection_md(selection: Selection, funnel_counts: dict) -> str:
    lines = ["# v127 structure-break armed entries — Stage 1 selection", "",
             f"**Verdict: {selection.verdict}**", "",
             f"Window: {SELECTION_WINDOW[0]}..{SELECTION_WINDOW[1]} (fold-train only).", "",
             "## Pre-registered rule", "", SELECTION_RULE, "", LIMITATIONS, "",
             f"## All {len(selection.scores)} cells", "", *_SCORE_HEAD]
    lines += [_score_line(s) for s in selection.scores]
    lines += ["", f"Rule's pick before the plateau check: {selection.best or 'none'}",
              f"Selected for Stage 0: {selection.selected or 'none'}", ""]
    lines += _plateau_lines(selection)
    lines += _funnel_lines(selection, funnel_counts)
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_structure_measurement.py`
Expected: `VERDICT: PASS  11 passed`. Also `python scripts/dev/testrun.py file tests/backtesting/test_armed_measurement.py` — unchanged file, still green.

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/backtesting/structure_measurement.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/backtesting/structure_measurement.py tests/backtesting/test_structure_measurement.py
git commit -m "feat(v127): 12-cell structure grid, N/k plateau selection, population disclosure"
```
