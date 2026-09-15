# v88 Armed Confluence Entries — Part 1: the replay

> Header, global constraints, parallelisation and outcomes live in `2026-09-15-v88-armed-confluence-entries_0-index.md`. Every task here implicitly includes that file's Global Constraints.

# Phase 1 — Replay code (worktree)

### Task AR1: Test and reaction predicates

**Files:**
- Create: `swingbot/core/market/reaction.py`
- Test: `tests/market/test_reaction.py`
- Modify: `docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md` §3.2 (clarifications, Step 5)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `R1, R2, R3: str` (`"R1"`, `"R2"`, `"R3"`), `RECLAIM_BARS = 2`
  - `Bars` — frozen dataclass of float `np.ndarray`s `open, high, low, close`; `Bars.from_frame(df) -> Bars`
  - `is_test(bars, t, level, direction, k, atr_t) -> bool`
  - `is_rejection(bars, t, level, direction) -> bool`
  - `is_follow_through(bars, t, direction) -> bool`
  - `is_reclaim(bars, t, level, direction, floor_index) -> bool`
  - `reaction_kind(bars, t, level, direction, *, tested_now, tested_prev, floor_index) -> str | None` — precedence R3 > R2 > R1

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_reaction.py`:

```python
import numpy as np
import pytest

from swingbot.core.market import reaction as rx
from tests.helpers import make_ohlcv

L_BULL, L_BEAR, K, ATR = 98.5, 101.5, 0.25, 1.0


def _bars(*rows):
    return rx.Bars.from_frame(make_ohlcv(list(rows)))


def test_is_test_bullish_touch_pierce_and_miss():
    bars = _bars((100, 101, 99.0, 100.5), (100, 101, 98.7, 100.5), (99, 100, 97.0, 99.5))
    assert rx.is_test(bars, 0, L_BULL, "bullish", K, ATR) is False   # 99.0 > 98.75
    assert rx.is_test(bars, 1, L_BULL, "bullish", K, ATR) is True    # touch within k*ATR
    assert rx.is_test(bars, 2, L_BULL, "bullish", K, ATR) is True    # pierce
    assert rx.is_test(bars, 2, L_BULL, "bullish", K, float("nan")) is False


def test_is_test_bearish_mirror():
    bars = _bars((100, 101.0, 99, 100.5), (100, 101.3, 99, 100.5))
    assert rx.is_test(bars, 0, L_BEAR, "bearish", K, ATR) is False   # 101.0 < 101.25
    assert rx.is_test(bars, 1, L_BEAR, "bearish", K, ATR) is True


def test_rejection_bullish_fires_and_near_misses_do_not():
    bars = _bars((99.0, 99.6, 97.6, 99.4),   # wick 1.4 of 2.0, close in top third, above L
                 (99.0, 99.6, 97.6, 98.6),   # close not in the top third
                 (98.0, 98.4, 96.0, 98.3),   # shape right, but closes below L
                 (99.0, 99.0, 99.0, 99.0))   # zero range
    assert rx.is_rejection(bars, 0, L_BULL, "bullish") is True
    assert rx.is_rejection(bars, 1, L_BULL, "bullish") is False
    assert rx.is_rejection(bars, 2, L_BULL, "bullish") is False
    assert rx.is_rejection(bars, 3, L_BULL, "bullish") is False


def test_rejection_bearish_mirror():
    bars = _bars((101.0, 102.4, 100.4, 100.6))  # upper wick 1.4 of 2.0, close in bottom third, below L
    assert rx.is_rejection(bars, 0, L_BEAR, "bearish") is True


def test_follow_through_needs_a_prior_bar():
    bars = _bars((99.0, 99.5, 98.6, 99.2), (99.3, 100.2, 99.1, 99.8))
    assert rx.is_follow_through(bars, 0, "bullish") is False
    assert rx.is_follow_through(bars, 1, "bullish") is True
    bear = _bars((101.0, 101.4, 100.5, 100.8), (100.7, 100.9, 100.0, 100.2))
    assert rx.is_follow_through(bear, 1, "bearish") is True


def test_reclaim_only_counts_closes_inside_the_arm_window():
    bars = _bars((99, 99, 98, 98.2), (99, 99, 98, 98.3), (99, 99.2, 98.4, 98.9))
    assert rx.is_reclaim(bars, 2, L_BULL, "bullish", floor_index=0) is True
    assert rx.is_reclaim(bars, 2, L_BULL, "bullish", floor_index=1) is True   # bar 1 still closed below
    assert rx.is_reclaim(bars, 2, L_BULL, "bullish", floor_index=2) is False  # nothing earlier inside the window
    bear = _bars((101, 102, 101, 101.8), (101.5, 101.9, 101.0, 101.2))
    assert rx.is_reclaim(bear, 1, L_BEAR, "bearish", floor_index=0) is True


def test_reaction_kind_precedence_and_test_requirements():
    # bar 2 is both a reclaim and a follow-through -> R3 wins
    bars = _bars((99, 99, 98, 98.2), (98.2, 98.4, 97.8, 98.3), (98.4, 99.6, 98.3, 99.5))
    assert rx.reaction_kind(bars, 2, L_BULL, "bullish", tested_now=True,
                            tested_prev=True, floor_index=0) == rx.R3
    # a rejection that is also a follow-through, tested now -> R2 over R1
    ft = _bars((99.0, 99.3, 98.8, 99.1), (99.0, 99.6, 97.6, 99.4))
    assert rx.reaction_kind(ft, 1, L_BULL, "bullish", tested_now=True,
                            tested_prev=False, floor_index=0) == rx.R2
    # follow-through with no test on this bar or the one before -> nothing
    assert rx.reaction_kind(ft, 1, L_BULL, "bullish", tested_now=False,
                            tested_prev=False, floor_index=0) is None
    # a rejection must itself be the test bar
    rej = _bars((99.6, 99.9, 99.5, 99.8), (99.0, 99.6, 97.6, 99.4))
    assert rx.reaction_kind(rej, 1, L_BULL, "bullish", tested_now=False,
                            tested_prev=True, floor_index=0) is None
    assert rx.reaction_kind(rej, 1, L_BULL, "bullish", tested_now=True,
                            tested_prev=False, floor_index=0) == rx.R1


def test_predicates_never_read_past_t():
    """NO-LOOKAHEAD: every predicate at bar t is identical on the full frame
    and on the frame truncated right after t."""
    rng = np.random.default_rng(11)
    closes = 100 + np.cumsum(rng.normal(0, 1.2, 80))
    rows = [(c - rng.uniform(-1, 1), c + rng.uniform(0, 2), c - rng.uniform(0, 2), c)
            for c in closes]
    rows = [(o, max(o, h, c), min(o, l, c), c) for o, h, l, c in rows]
    df = make_ohlcv(rows)
    full = rx.Bars.from_frame(df)
    level = float(np.median(closes))
    for t in range(2, len(df)):
        trunc = rx.Bars.from_frame(df.iloc[:t + 1])
        for direction in ("bullish", "bearish"):
            args = dict(level=level, direction=direction)
            assert rx.is_test(full, t, k=K, atr_t=ATR, **args) == rx.is_test(trunc, t, k=K, atr_t=ATR, **args)
            assert rx.is_rejection(full, t, **args) == rx.is_rejection(trunc, t, **args)
            assert rx.is_follow_through(full, t, direction) == rx.is_follow_through(trunc, t, direction)
            assert rx.is_reclaim(full, t, floor_index=0, **args) == rx.is_reclaim(trunc, t, floor_index=0, **args)
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/market/test_reaction.py`
Expected: FAIL — `ImportError: cannot import name 'reaction'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/market/reaction.py`:

```python
"""v88: did price test a level and react there?

Pure bar predicates for the armed-entry measurement
(backtesting/armed_replay.py). They live in market/ rather than
backtesting/ so a live path -- v88 spec §5's A2, written only if the
measurement passes VALIDATION -- would share this one source, the way
entry_filters.py is shared by the backtest and the live scanner.

Bullish: `level` is a SUPPORT below price (the plan's stop level). Bearish
mirrors it: `level` is a RESISTANCE above price, highs for lows, every
inequality flipped.

NO-LOOKAHEAD: every predicate at bar `t` reads bar `t` and earlier only.
Callers pass whole arrays for speed; nothing here indexes past `t`.
No config reads, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

R1, R2, R3 = "R1", "R2", "R3"   # rejection, follow-through, reclaim

REJECTION_WICK_MIN = 0.5          # wick >= half the bar's range
REJECTION_CLOSE_FRACTION = 2.0 / 3.0  # close in the top (bullish) third
RECLAIM_BARS = 2                  # a close through the level may be undone within 2 bars


@dataclass(frozen=True, eq=False)
class Bars:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    @classmethod
    def from_frame(cls, df) -> "Bars":
        return cls(df["Open"].to_numpy(dtype=float), df["High"].to_numpy(dtype=float),
                   df["Low"].to_numpy(dtype=float), df["Close"].to_numpy(dtype=float))


def is_test(bars: Bars, t: int, level: float, direction: str, k: float, atr_t: float) -> bool:
    """Bar t came within k*ATR of the level, or went through it."""
    if not np.isfinite(atr_t):
        return False
    if direction == "bullish":
        return bool(bars.low[t] <= level + k * atr_t)
    return bool(bars.high[t] >= level - k * atr_t)


def is_rejection(bars: Bars, t: int, level: float, direction: str) -> bool:
    """R1 shape: a long wick into the level, a close far from it, on the
    trade's side of the level."""
    o, h, l, c = bars.open[t], bars.high[t], bars.low[t], bars.close[t]
    rng = h - l
    if not rng > 0:
        return False
    if direction == "bullish":
        wick = min(o, c) - l
        return bool(wick >= REJECTION_WICK_MIN * rng
                    and c >= l + REJECTION_CLOSE_FRACTION * rng and c >= level)
    wick = h - max(o, c)
    return bool(wick >= REJECTION_WICK_MIN * rng
                and c <= h - REJECTION_CLOSE_FRACTION * rng and c <= level)


def is_follow_through(bars: Bars, t: int, direction: str) -> bool:
    """R2 shape: bar t closed beyond the previous bar's extreme."""
    if t < 1:
        return False
    if direction == "bullish":
        return bool(bars.close[t] > bars.high[t - 1])
    return bool(bars.close[t] < bars.low[t - 1])


def is_reclaim(bars: Bars, t: int, level: float, direction: str, floor_index: int) -> bool:
    """R3: a close through the level within the last RECLAIM_BARS bars --
    counting only bars at or after `floor_index` (the arm bar) -- undone by
    bar t's close."""
    lo = max(floor_index, t - RECLAIM_BARS)
    if lo > t - 1:
        return False
    prior = bars.close[lo:t]
    if direction == "bullish":
        return bool((prior < level).any() and bars.close[t] >= level)
    return bool((prior > level).any() and bars.close[t] <= level)


def reaction_kind(bars: Bars, t: int, level: float, direction: str, *,
                  tested_now: bool, tested_prev: bool, floor_index: int) -> str | None:
    """The strongest reaction bar t shows, or None. R3 > R2 > R1.

    R2 needs a test on bar t or t-1 (the caller passes tested_prev=False
    when t-1 precedes the arm bar). R1 needs bar t itself to be the test:
    a rejection wick that never reached the level rejected nothing.
    R3 needs no separate test flag -- closing through the level is one.
    """
    if is_reclaim(bars, t, level, direction, floor_index):
        return R3
    if (tested_now or tested_prev) and is_follow_through(bars, t, direction):
        return R2
    if tested_now and is_rejection(bars, t, level, direction):
        return R1
    return None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/market/test_reaction.py`
Expected: 8 PASS.

If `test_reaction_kind_precedence_and_test_requirements`'s first frame does not read as a reclaim + follow-through (check `bars.close[2] >= 98.5` and `> bars.high[1]`), fix the fixture numbers, not the module, and keep the intent the comment states.

- [ ] **Step 5: Clarify the spec where the plan pinned a reading**

In the spec §3.2, replace the R1 bullet's opening `**R1 rejection:** `range_j > 0`,` with `**R1 rejection:** bar `j` is itself a test bar, `range_j > 0`,`. Replace the R3 bullet's `some bar in `[j−2, j−1]` closed below `L`` with `some bar in `[max(i, j−2), j−1]` — inside the arm window — closed below `L``. Append to the **Cancel before confirmation** bullet: ` The target check starts on the bar after the arm bar; when one bar both reaches the target and reacts, the cancel wins.` (AR2 implements that.)

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add swingbot/core/market/reaction.py tests/market/test_reaction.py docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md
git -C <worktree> commit -m "feat(v88): level test and reaction predicates"
```

---

### Task AR2: Arm candidates and the arm walk

**Files:**
- Create: `swingbot/core/backtesting/armed_replay.py`
- Test: `tests/backtesting/test_armed_replay.py`

**Interfaces:**
- Consumes (AR1): `reaction.Bars`, `reaction.is_test`, `reaction.reaction_kind`, `reaction.RECLAIM_BARS`.
- Produces:
  - `Cell(mode: str, n: int, k: float, b: float)` frozen dataclass, property `cell_id -> str` formatted `f"{mode}-N{n}-k{k:.2f}-b{b:.2f}"` (e.g. `"M1-N5-k0.25-b0.10"`)
  - `ArmCandidate(index: int, direction: str, level: float, target: float, scenario: levels.Scenario)` frozen dataclass
  - `ArmOutcome(status: str, resolved_index: int | None, kind: str | None = None, first_test_index: int | None = None)`; `status` ∈ `"confirmed"`, `"expired"`, `"cancelled_target"`, `"cancelled_closed_through"`, `"unresolved"`
  - `arm_candidates(ticker, df, horizon_key, *, params=None, level_cache=None) -> dict[int, list[ArmCandidate]]`
  - `walk_arm(bars, atr_values, cand, cell) -> ArmOutcome`
  - constants `COOLDOWN_BARS = 5`, `STOP_ENTRY_EXPIRY_BARS = 2`, `CONFLUENCE_TOLERANCE_PCT = 5.0`

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_armed_replay.py`:

```python
import dataclasses

import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting import armed_replay as ar
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.market import levels, reaction as rx
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

L, T1 = 98.5, 106.0
CELL = ar.Cell("M1", 5, 0.25, 0.10)


def _params(**kw):
    base = dict(min_reward_pct=3.0, min_stop_distance_pct=2.0, max_stop_loss_pct=7.0,
                min_target_confluence_count=2, min_risk_reward_ratio=1.5,
                max_risk_reward_ratio=2.5)
    base.update(kw)
    return dataclasses.replace(ScanParams.from_config(), **base)


def _scenario(direction="bullish", entry=100.0, stop=L, target=T1):
    return levels.Scenario(
        direction=direction, entry=entry, market_price=entry, stop_loss=stop,
        stop_sources=["Rolling S/R"], stop_distance_pct=abs(entry - stop) / entry * 100,
        tight_stop=False, atr_floor_pct=0.0, take_profit=target,
        target_distance_pct=abs(target - entry) / entry * 100,
        target_sources=["Fibonacci"], target2_price=None, target2_distance_pct=None,
        target2_sources=None)


def _cand(index=25, direction="bullish", level=L, target=T1):
    return ar.ArmCandidate(index, direction, level, target,
                           _scenario(direction, stop=level, target=target))


def _frame(overrides, n=30):
    """Flat 100 closes (high 101 / low 99, well clear of L=98.5 at k=0.25),
    with (open, high, low, close) overrides by bar index."""
    rows = [(100.0, 101.0, 99.0, 100.0)] * n
    for idx, row in overrides.items():
        rows[idx] = row
    return make_ohlcv(rows)


def _walk(df, cand=None, cell=CELL):
    return ar.walk_arm(rx.Bars.from_frame(df), np.full(len(df), 1.0), cand or _cand(), cell)


def test_cell_id_format():
    assert ar.Cell("M2", 10, 0.5, 0.25).cell_id == "M2-N10-k0.50-b0.25"


def test_walk_confirms_a_rejection_and_records_the_first_test():
    out = _walk(_frame({27: (99.0, 99.6, 97.6, 99.4)}))
    assert out == ar.ArmOutcome("confirmed", 27, rx.R1, 27)


def test_walk_expires_when_nothing_tests_the_level():
    # arm at 25 with N=5 expires at bar 30, which must exist: 31 bars
    assert _walk(_frame({}, n=31)) == ar.ArmOutcome("expired", 30)


def test_walk_cancels_when_the_target_trades_first():
    out = _walk(_frame({26: (100.0, 106.5, 99.5, 105.0), 27: (99.0, 99.6, 97.6, 99.4)}))
    assert out == ar.ArmOutcome("cancelled_target", 26)


def test_target_reached_on_the_arm_bar_itself_is_ignored():
    out = _walk(_frame({25: (100.0, 106.5, 99.5, 100.0), 27: (99.0, 99.6, 97.6, 99.4)}))
    assert out.status == "confirmed" and out.resolved_index == 27


def test_walk_cancels_a_close_through_that_is_not_reclaimed():
    out = _walk(_frame({26: (98.6, 98.7, 97.9, 98.0),
                        27: (98.0, 98.1, 97.4, 97.5),
                        28: (97.5, 97.6, 96.9, 97.0)}))
    assert out == ar.ArmOutcome("cancelled_closed_through", 28)


def test_walk_is_unresolved_when_the_window_runs_off_the_frame():
    assert _walk(_frame({}, n=28)) == ar.ArmOutcome("unresolved", None)


def test_walk_bearish_mirror_confirms():
    cand = _cand(direction="bearish", level=101.5, target=94.0)
    out = _walk(_frame({27: (101.0, 102.4, 100.4, 100.6)}), cand=cand)
    assert out == ar.ArmOutcome("confirmed", 27, rx.R1, 27)


def test_arm_candidates_widen_past_the_min_stop_gate(monkeypatch):
    """Spec §3.1's widening: a 1.5% stop is refused by today's replay and
    arms here."""
    supports, resistances = [levels.Level(L, ["Rolling S/R"])], [levels.Level(T1, ["Fibonacci"])]
    monkeypatch.setattr(ar, "levels_asof", lambda *a, **k: (supports, resistances))
    monkeypatch.setattr(bs, "levels_asof", lambda *a, **k: (supports, resistances))
    monkeypatch.setattr(levels, "count_confirming_strategies", lambda *a, **k: (3, ["x", "y", "z"]))
    df = make_ohlcv([100.0] * 60)
    params = _params()
    baseline = bs.replay_scenarios("AAPL", df, "4w", params=params)
    assert [p for _, p in baseline if p.direction == "bullish"] == []
    cands = ar.arm_candidates("AAPL", df, "4w", params=params)
    bullish = [c for bar in cands.values() for c in bar if c.direction == "bullish"]
    assert bullish and all(c.level == L and c.target == T1 for c in bullish)
    assert min(cands) == 45          # MIN_BARS["4w"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: FAIL — `ImportError: cannot import name 'armed_replay'`.

- [ ] **Step 3: Write the module**

Create `swingbot/core/backtesting/armed_replay.py`:

```python
"""v88 A1: the armed confluence replay (spec §3).

A confluence scenario no longer becomes a plan on the bar it appears. It
ARMS, and only a test of its stop level followed by a price reaction there
(market/reaction.py) turns it into a plan -- rebuilt at the confirmation
bar through the same constructor, target selection and gates the live scan
uses, with the stop re-anchored under the reaction.

NO-LOOKAHEAD: every decision at bar j reads df.iloc[:j+1] only.
levels_asof caches its map per 5-bar bucket, built at the FIRST bar that
asks -- so arm_candidates must walk bars in order and fill the cache before
anything reads a bucket out of order (plan construction at a later
confirmation bar, the permutation's random bars).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from swingbot.core.backtesting.backtest_scenarios import levels_asof
from swingbot.core.market import levels, reaction
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS
from swingbot.core.scanning.gating import passes_confluence, scenario_gate_inputs
from swingbot.scan_params import ScanParams

COOLDOWN_BARS = 5                 # replay_scenarios' own per-direction cooldown
STOP_ENTRY_EXPIRY_BARS = 2        # spec §3.4, pre-registered
CONFLUENCE_TOLERANCE_PCT = 5.0    # replay_scenarios' count_confirming_strategies tolerance


@dataclass(frozen=True)
class Cell:
    mode: str      # "M1" | "M2"
    n: int         # arm window, bars
    k: float       # test proximity, ATR
    b: float       # stop buffer, ATR

    @property
    def cell_id(self) -> str:
        return f"{self.mode}-N{self.n}-k{self.k:.2f}-b{self.b:.2f}"


@dataclass(frozen=True)
class ArmCandidate:
    index: int
    direction: str
    level: float       # the scenario's stop price at arm time
    target: float      # the scenario's target 1 at arm time
    scenario: object   # levels.Scenario


@dataclass(frozen=True)
class ArmOutcome:
    status: str                    # confirmed | expired | cancelled_target | cancelled_closed_through | unresolved
    resolved_index: int | None
    kind: str | None = None
    first_test_index: int | None = None


def arm_candidates(ticker: str, df, horizon_key: str, *, params: ScanParams | None = None,
                   level_cache: dict | None = None) -> dict[int, list[ArmCandidate]]:
    """Every bar's arm-eligible scenarios: replay_scenarios' construction
    with ONE gate relaxed -- min_stop_distance_pct is 0 at arm time (spec
    §3.1) and re-applied at confirmation. Walks bars in order, which is
    what makes `level_cache` safe to read out of order afterwards."""
    if params is None:
        params = ScanParams.from_config()
    cache = {} if level_cache is None else level_cache
    h = HORIZONS[horizon_key]
    gates = scenario_gate_inputs(params, h)
    out: dict[int, list[ArmCandidate]] = {}
    for i in range(MIN_BARS[horizon_key], len(df)):
        window = df.iloc[:i + 1]
        price = float(window["Close"].iloc[-1])
        supports, resistances = levels_asof(ticker, df, i, horizon_key, cache)
        all_levels = sorted(supports + resistances, key=lambda lv: lv.price)
        supports = [lv for lv in all_levels if lv.price < price][::-1]
        resistances = [lv for lv in all_levels if lv.price > price]
        scenarios = levels.build_scenarios(
            price, supports, resistances, gates["min_reward_pct"],
            atr_floor=levels.atr_floor_pct(window, price, h),
            min_stop_distance_pct=0.0,
            max_stop_distance_pct=gates["max_stop_distance_pct"],
            min_risk_reward=gates["min_risk_reward"])
        found = []
        for sc in scenarios:
            n_confl, _ = levels.count_confirming_strategies(
                window, h, price, sc.take_profit, tolerance_pct=CONFLUENCE_TOLERANCE_PCT)
            if passes_confluence(n_confl, params):
                found.append(ArmCandidate(i, sc.direction, float(sc.stop_loss),
                                          float(sc.take_profit), sc))
        if found:
            out[i] = found
    return out


def walk_arm(bars: reaction.Bars, atr_values: np.ndarray, cand: ArmCandidate,
             cell: Cell) -> ArmOutcome:
    """Walk one armed scenario across [i, i + N] (spec §3.2).

    Per bar t, in this order: the target check (bars after the arm bar
    only; a bar that both reaches the target and reacts is a cancel), the
    test, the reaction, then the close-through-not-reclaimed cancel. Every
    check at t reads bars <= t.
    """
    n_bars = len(bars.close)
    i, last = cand.index, cand.index + cell.n
    bull = cand.direction == "bullish"
    first_test = None
    breach_start = None
    for t in range(i, min(last, n_bars - 1) + 1):
        if t > i and ((bars.high[t] >= cand.target) if bull else (bars.low[t] <= cand.target)):
            return ArmOutcome("cancelled_target", t)
        tested_now = reaction.is_test(bars, t, cand.level, cand.direction, cell.k, atr_values[t])
        if tested_now and first_test is None:
            first_test = t
        tested_prev = t - 1 >= i and reaction.is_test(
            bars, t - 1, cand.level, cand.direction, cell.k, atr_values[t - 1])
        if first_test is not None:
            kind = reaction.reaction_kind(bars, t, cand.level, cand.direction,
                                          tested_now=tested_now, tested_prev=tested_prev,
                                          floor_index=i)
            if kind is not None:
                return ArmOutcome("confirmed", t, kind, first_test)
        through = bars.close[t] < cand.level if bull else bars.close[t] > cand.level
        if through:
            if breach_start is None:
                breach_start = t
            elif t - breach_start >= reaction.RECLAIM_BARS:
                return ArmOutcome("cancelled_closed_through", t)
        else:
            breach_start = None
    if last <= n_bars - 1:
        return ArmOutcome("expired", last)
    return ArmOutcome("unresolved", None)
```

Note `reaction_kind`'s R3 can fire with `first_test` set on the same bar a close first went through — a close below the level implies a low below it, so `is_test` is already true on that bar.

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: 9 PASS.

If `test_walk_cancels_a_close_through_that_is_not_reclaimed` confirms an R2 instead (a close above the previous high while below the level), lower that fixture's closes further so each bar closes under the previous bar's high; the property under test is the cancel, not the numbers.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add swingbot/core/backtesting/armed_replay.py tests/backtesting/test_armed_replay.py
git -C <worktree> commit -m "feat(v88): arm candidates and the arm walk"
```

---

### Task AR3: The plan at confirmation

**Files:**
- Modify: `swingbot/core/backtesting/armed_replay.py`
- Test: `tests/backtesting/test_armed_replay.py`

**Interfaces:**
- Consumes (AR2): `Cell`, `ArmCandidate`, `ArmOutcome`, `STOP_ENTRY_EXPIRY_BARS`, `CONFLUENCE_TOLERANCE_PCT`.
- Produces:
  - `plan_at(ticker, df, horizon_key, cand, *, j, first_test_index, kind, cell, bars, atr_values, params, level_map_at, confluence_at) -> tuple[TradePlanV2 | None, str]`
  - `build_armed_plan(ticker, df, horizon_key, cand, outcome, cell, *, bars, atr_values, params, level_map_at, confluence_at) -> tuple[TradePlanV2 | None, str]` — thin wrapper for a confirmed `ArmOutcome`
  - reason strings: `"issued"`, `"regate_invalid_atr"`, `"regate_stop_distance"`, `"regate_no_target"`, `"regate_reward"`, `"regate_confluence"`
  - `level_map_at: Callable[[int], tuple[list, list]]`, `confluence_at: Callable[[int, float, float], int]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_armed_replay.py`:

```python
from swingbot.core.planning.plan_engine import PlanStatus


def _build(df, outcome, cell=CELL, *, resistances=(T1,), confluence=3, params=None):
    res = [levels.Level(p, ["Fibonacci"]) for p in resistances]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    return ar.build_armed_plan(
        "AAPL", df, "4w", _cand(), outcome, cell,
        bars=rx.Bars.from_frame(df), atr_values=np.full(len(df), 1.0),
        params=params or _params(),
        level_map_at=lambda j: (sup, res),
        confluence_at=lambda j, entry, target: confluence)


REJECTION = (99.0, 99.6, 97.6, 99.4)


def test_m1_issues_a_stop_entry_above_the_reaction_high():
    df = _frame({26: REJECTION})
    plan, reason = _build(df, ar.ArmOutcome("confirmed", 26, rx.R1, 26))
    assert reason == "issued"
    assert plan.entry_type == "stop_entry" and plan.entry_price is None
    assert plan.trigger_price == pytest.approx(99.6)
    assert plan.expiry_bars == ar.STOP_ENTRY_EXPIRY_BARS
    assert plan.stop_loss == pytest.approx(97.5)              # min(98.5, 97.6) - 0.10 * 1.0
    assert plan.tp1 == pytest.approx(99.6 + 2.1 * 2.5)        # 106 is past the 2.5R cap
    assert plan.status == PlanStatus.PENDING
    assert plan.created_at == df.index[26].date().isoformat()


def test_the_widened_scenario_issues_once_its_stop_is_re_anchored():
    """Today's gates refuse this scenario (1.5% stop); the armed path
    issues it with a stop >= 2% from the entry."""
    assert [s for s in levels.build_scenarios(
        100.0, [levels.Level(L, ["Rolling S/R"])], [levels.Level(T1, ["Fibonacci"])], 3.0,
        min_stop_distance_pct=2.0, max_stop_distance_pct=7.0, min_risk_reward=1.5)
        if s.direction == "bullish"] == []
    plan, reason = _build(_frame({26: REJECTION}), ar.ArmOutcome("confirmed", 26, rx.R1, 26))
    assert reason == "issued"
    assert abs(plan.trigger_price - plan.stop_loss) / plan.trigger_price * 100 >= 2.0


def test_m2_goes_straight_to_market_on_a_follow_through():
    df = _frame({25: (99.2, 99.5, 97.9, 99.2), 26: (99.3, 100.2, 98.6, 100.0)})
    plan, reason = _build(df, ar.ArmOutcome("confirmed", 26, rx.R2, 25),
                          cell=ar.Cell("M2", 5, 0.25, 0.25))
    assert reason == "issued"
    assert plan.entry_type == "market"
    assert plan.entry_price == pytest.approx(100.0) == plan.trigger_price
    assert plan.stop_loss == pytest.approx(97.65)             # min(98.5, 97.9) - 0.25
    assert plan.status == PlanStatus.ACTIVE


def test_m2_keeps_a_rejection_as_a_stop_entry():
    plan, _ = _build(_frame({26: REJECTION}), ar.ArmOutcome("confirmed", 26, rx.R1, 26),
                     cell=ar.Cell("M2", 5, 0.25, 0.10))
    assert plan.entry_type == "stop_entry"


def test_regates_refuse_rather_than_bend():
    shallow = _frame({26: (99.0, 99.6, 98.4, 99.4)})
    assert _build(shallow, ar.ArmOutcome("confirmed", 26, rx.R1, 26)) == (None, "regate_stop_distance")
    df = _frame({26: REJECTION})
    ok = ar.ArmOutcome("confirmed", 26, rx.R1, 26)
    assert _build(df, ok, resistances=()) == (None, "regate_no_target")
    assert _build(df, ok, params=_params(min_reward_pct=6.0)) == (None, "regate_reward")
    assert _build(df, ok, confluence=1) == (None, "regate_confluence")


def test_nan_atr_refuses():
    df = _frame({26: REJECTION})
    plan, reason = ar.build_armed_plan(
        "AAPL", df, "4w", _cand(), ar.ArmOutcome("confirmed", 26, rx.R1, 26), CELL,
        bars=rx.Bars.from_frame(df), atr_values=np.full(len(df), np.nan), params=_params(),
        level_map_at=lambda j: ([], []), confluence_at=lambda *a: 3)
    assert (plan, reason) == (None, "regate_invalid_atr")
```

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: the six new tests FAIL with `AttributeError: module ... has no attribute 'build_armed_plan'`; AR2's tests still PASS.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/armed_replay.py`, add to the imports:

```python
import dataclasses

from swingbot.core.planning.plan_engine import PlanStatus, build_confluence_plan, primary_strategy_for
from swingbot.core.planning.plan_types import record_transition
```

Append:

```python
def plan_at(ticker: str, df, horizon_key: str, cand: ArmCandidate, *, j: int,
            first_test_index: int, kind: str, cell: Cell, bars: reaction.Bars,
            atr_values: np.ndarray, params: ScanParams, level_map_at, confluence_at):
    """The plan an armed scenario becomes if bar j is its confirmation
    (spec §3.3-3.4). Returns (plan, "issued") or (None, the gate that
    refused it). A plan is never adjusted to fit a gate.

    `level_map_at(j)` -> (supports, resistances) as of bar j; `confluence_at
    (j, entry, target)` -> confirming-strategy count. Injected so the
    permutation (AR6) and the tests share this exact path.
    """
    h = HORIZONS[horizon_key]
    gates = scenario_gate_inputs(params, h)
    bull = cand.direction == "bullish"
    atr_j = float(atr_values[j])
    if not np.isfinite(atr_j):
        return None, "regate_invalid_atr"

    if bull:
        stop = min(cand.level, float(bars.low[first_test_index:j + 1].min())) - cell.b * atr_j
    else:
        stop = max(cand.level, float(bars.high[first_test_index:j + 1].max())) + cell.b * atr_j
    market = cell.mode == "M2" and kind in (reaction.R2, reaction.R3)
    if market:
        entry = float(bars.close[j])
    else:
        entry = float(bars.high[j] if bull else bars.low[j])

    if (bull and stop >= entry) or (not bull and stop <= entry):
        return None, "regate_stop_distance"
    risk_pct = abs(entry - stop) / entry * 100.0
    if risk_pct < gates["min_stop_distance_pct"] or risk_pct > gates["max_stop_distance_pct"]:
        return None, "regate_stop_distance"

    supports, resistances = level_map_at(j)
    all_levels = sorted(list(supports) + list(resistances), key=lambda lv: lv.price)
    supports = [lv for lv in all_levels if lv.price < entry][::-1]
    resistances = [lv for lv in all_levels if lv.price > entry]
    scenario = dataclasses.replace(cand.scenario, entry=entry, market_price=entry,
                                   stop_loss=stop, stop_distance_pct=risk_pct)
    plan = build_confluence_plan(
        scenario, df.iloc[:j + 1], ticker=ticker, horizon_key=horizon_key,
        primary_strategy=primary_strategy_for(cand.scenario),
        level_map=(supports, resistances), params=params)
    if plan is None:
        return None, "regate_no_target"
    if abs(plan.tp1 - entry) / entry * 100.0 < gates["min_reward_pct"]:
        return None, "regate_reward"
    if not passes_confluence(confluence_at(j, entry, plan.tp1), params):
        return None, "regate_confluence"

    plan = dataclasses.replace(
        plan, entry_type="market" if market else "stop_entry", trigger_price=entry,
        entry_price=entry if market else None,
        expiry_bars=plan.expiry_bars if market else STOP_ENTRY_EXPIRY_BARS,
        status=PlanStatus.PENDING, status_history=[])
    if market:
        record_transition(plan, PlanStatus.ACTIVE, reason="market_entry", at=plan.created_at)
    return plan, "issued"


def build_armed_plan(ticker: str, df, horizon_key: str, cand: ArmCandidate,
                     outcome: ArmOutcome, cell: Cell, *, bars, atr_values, params,
                     level_map_at, confluence_at):
    """plan_at for a real confirmation."""
    return plan_at(ticker, df, horizon_key, cand, j=outcome.resolved_index,
                   first_test_index=outcome.first_test_index, kind=outcome.kind, cell=cell,
                   bars=bars, atr_values=atr_values, params=params,
                   level_map_at=level_map_at, confluence_at=confluence_at)
```

`plan_types.record_transition` rejects illegal transitions; `PENDING → ACTIVE` is legal. If `plan_engine` does not re-export `PlanStatus`, import it from `swingbot.core.planning.plan_types` instead (`plan_store.py` imports it from `plan_engine`, so it should).

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: 15 PASS.

If `test_m1_issues_a_stop_entry_above_the_reaction_high` fails only on `tp1`, print `plan.tp1` and check the arithmetic against `targets.select_structural_target` (risk 2.1, floor 3.15, cap 5.25, candidate 106 is 6.4 away → synthetic `entry + cap`). Fix the test's expectation only if the function's documented rule gives a different number; never change `select_structural_target`.

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add swingbot/core/backtesting/armed_replay.py tests/backtesting/test_armed_replay.py
git -C <worktree> commit -m "feat(v88): build and re-gate the plan at confirmation"
```

---

### Task AR4: Per-cell replay

**Files:**
- Modify: `swingbot/core/backtesting/armed_replay.py`
- Test: `tests/backtesting/test_armed_replay.py`

**Interfaces:**
- Consumes (AR2–AR3): `arm_candidates`, `walk_arm`, `build_armed_plan`, `COOLDOWN_BARS`, `CONFLUENCE_TOLERANCE_PCT`.
- Produces:
  - `CellResult` dataclass: `issued: list[tuple[int, TradePlanV2, str]]` (confirmation index, plan, reaction kind), `confirmed: list[tuple[ArmCandidate, ArmOutcome]]` (every confirmed arm, issued or regated — the permutation's population), `counts: collections.Counter`
  - `make_confluence_at(df, horizon_key) -> Callable[[int, float, float], int]` (memoised)
  - `replay_armed(ticker, df, horizon_key, cells, *, params=None, candidates=None, level_cache=None, level_map_at=None, confluence_at=None) -> dict[str, CellResult]` keyed by `cell_id`
  - counter keys: `"armed"`, `"unresolved"`, `"expired"`, `"cancelled_target"`, `"cancelled_closed_through"`, plus every `plan_at` reason

- [ ] **Step 1: Write the failing tests**

Append to `tests/backtesting/test_armed_replay.py`:

```python
def _replay(df, candidates, cell=CELL):
    res = [levels.Level(T1, ["Fibonacci"])]
    sup = [levels.Level(90.0, ["Rolling S/R"])]
    out = ar.replay_armed("AAPL", df, "4w", [cell], params=_params(), candidates=candidates,
                          level_map_at=lambda j: (sup, res),
                          confluence_at=lambda j, entry, target: 3)
    return out[cell.cell_id]


def test_one_live_arm_per_direction_and_cooldown_after_issuance(monkeypatch):
    # real ATR on this flat frame is ~2, which would make every 99.0 low a
    # test at k=0.25; pin it at 1.0 so only the rejection bar tests the level
    monkeypatch.setattr(ar, "atr", lambda df, period=14: pd.Series(1.0, index=df.index))
    df = _frame({27: REJECTION}, n=45)
    cands = {i: [_cand(index=i)] for i in (25, 26, 27, 28, 31, 32, 33)}
    result = _replay(df, cands)
    # 25 arms and confirms at 27; 26 and 27 are skipped (busy through 27);
    # 28 and 31 fall inside the 5-bar cooldown from 27; 32 arms and expires at 37;
    # 33 is skipped (busy through 37).
    assert [j for j, _, _ in result.issued] == [27]
    assert result.counts["armed"] == 2
    assert result.counts["issued"] == 1
    assert result.counts["expired"] == 1
    assert len(result.confirmed) == 1


def test_confluence_at_is_memoised(monkeypatch):
    calls = []
    monkeypatch.setattr(levels, "count_confirming_strategies",
                        lambda *a, **k: (calls.append(a) or 2, []))
    f = ar.make_confluence_at(make_ohlcv([100.0] * 30), "4w")
    assert f(20, 100.0, 105.0) == 2 and f(20, 100.0, 105.0) == 2
    assert len(calls) == 1


def _structured_df():
    """Trend up, then a 60-bar consolidation between ~95 and ~105 -- the
    fixture family tests/backtesting/test_backtest_scenarios.py uses, copied
    so the two files stay independent."""
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


@pytest.mark.slow
def test_replay_armed_never_reads_past_the_confirmation_bar():
    """NO-LOOKAHEAD: every plan issued at j <= t is identical on the full
    frame and on the frame truncated at t."""
    df = _structured_df()
    params = _params(min_target_confluence_count=1, min_stop_distance_pct=0.5,
                     max_stop_loss_pct=15.0, min_reward_pct=1.0)
    cells = [ar.Cell("M1", 10, 0.5, 0.10), ar.Cell("M2", 10, 0.5, 0.10)]
    t = len(df) - 15

    def signature(result):
        return sorted((j, kind, p.direction, p.entry_type, round(p.trigger_price, 6),
                       round(p.stop_loss, 6), round(p.tp1, 6))
                      for j, p, kind in result.issued if j <= t)

    full = ar.replay_armed("AAPL", df, "4w", cells, params=params)
    trunc = ar.replay_armed("AAPL", df.iloc[:t + 1], "4w", cells, params=params)
    assert any(r.counts["armed"] for r in full.values()), "fixture must arm at least once"
    for cell in cells:
        assert signature(full[cell.cell_id]) == signature(trunc[cell.cell_id])
```

If the slow test's fixture arms nothing, loosen `params` further (e.g. `min_risk_reward_ratio` stays 1.5 — it feeds target selection — but `min_reward_pct` may drop to 0.5) and freeze the shape with a comment, per `architecture.md`'s note on REPL-tuning synthetic fixtures. Do not change module code to make a fixture fire. If it arms but issues nothing, the test still guards arm lifecycle parity; record that in the task report.

- [ ] **Step 2: Run to verify failure**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: the new tests FAIL — `AttributeError: ... 'replay_armed'` / `'make_confluence_at'`.

- [ ] **Step 3: Implement**

In `swingbot/core/backtesting/armed_replay.py`, add to the imports:

```python
from collections import Counter
from dataclasses import field

from swingbot.core.market.indicators import atr
```

Append:

```python
@dataclass
class CellResult:
    issued: list = field(default_factory=list)      # (confirmation index, plan, reaction kind)
    confirmed: list = field(default_factory=list)   # (ArmCandidate, ArmOutcome), issued or regated
    counts: Counter = field(default_factory=Counter)


def make_confluence_at(df, horizon_key: str):
    """count_confirming_strategies at bar j for (entry, target), memoised --
    the permutation revisits the same (j, entry, target) many times."""
    h = HORIZONS[horizon_key]
    memo: dict = {}

    def confluence_at(j: int, entry: float, target: float) -> int:
        key = (j, round(entry, 6), round(target, 6))
        if key not in memo:
            memo[key] = levels.count_confirming_strategies(
                df.iloc[:j + 1], h, entry, target, tolerance_pct=CONFLUENCE_TOLERANCE_PCT)[0]
        return memo[key]

    return confluence_at


def replay_armed(ticker: str, df, horizon_key: str, cells, *, params: ScanParams | None = None,
                 candidates: dict | None = None, level_cache: dict | None = None,
                 level_map_at=None, confluence_at=None) -> dict:
    """Every cell's issued plans over one (ticker, horizon) frame.

    One armed scenario per direction at a time: a new arm for a direction
    is ignored until the live one resolves. After a plan is issued at bar
    j, arms for that direction wait COOLDOWN_BARS (replay_scenarios' own
    rule, measured from issuance). Candidates, the level cache and the
    confluence memo are shared across cells -- they do not depend on the
    cell -- which is what keeps 24 cells affordable.
    """
    if params is None:
        params = ScanParams.from_config()
    cache = {} if level_cache is None else level_cache
    if candidates is None:
        candidates = arm_candidates(ticker, df, horizon_key, params=params, level_cache=cache)
    if level_map_at is None:
        level_map_at = lambda j: levels_asof(ticker, df, j, horizon_key, cache)  # noqa: E731
    if confluence_at is None:
        confluence_at = make_confluence_at(df, horizon_key)
    bars = reaction.Bars.from_frame(df)
    atr_values = atr(df, 14).to_numpy(dtype=float)

    results = {}
    for cell in cells:
        result = CellResult()
        busy_until: dict[str, int] = {}
        last_issued: dict[str, int] = {}
        for i in sorted(candidates):
            for cand in candidates[i]:
                d = cand.direction
                if i <= busy_until.get(d, -1):
                    continue
                if d in last_issued and i - last_issued[d] < COOLDOWN_BARS:
                    continue
                result.counts["armed"] += 1
                outcome = walk_arm(bars, atr_values, cand, cell)
                if outcome.status == "unresolved":
                    result.counts["unresolved"] += 1
                    busy_until[d] = len(df)
                    continue
                busy_until[d] = outcome.resolved_index
                if outcome.status != "confirmed":
                    result.counts[outcome.status] += 1
                    continue
                result.confirmed.append((cand, outcome))
                plan, reason = build_armed_plan(
                    ticker, df, horizon_key, cand, outcome, cell, bars=bars,
                    atr_values=atr_values, params=params,
                    level_map_at=level_map_at, confluence_at=confluence_at)
                result.counts[reason] += 1
                if plan is not None:
                    last_issued[d] = outcome.resolved_index
                    result.issued.append((outcome.resolved_index, plan, outcome.kind))
        results[cell.cell_id] = result
    return results
```

`indicators.atr` is a trailing computation, so reading it on the full frame is lookahead-free; the slow truncation test is what proves it for this frame.

- [ ] **Step 4: Run to verify it passes**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_armed_replay.py`
Expected: 18 PASS (the slow test included — `testrun.py file` runs slow-marked tests in the named file).

- [ ] **Step 5: Commit**

```bash
git -C <worktree> add swingbot/core/backtesting/armed_replay.py tests/backtesting/test_armed_replay.py
git -C <worktree> commit -m "feat(v88): per-cell armed replay with arm exclusivity and cooldown"
```
