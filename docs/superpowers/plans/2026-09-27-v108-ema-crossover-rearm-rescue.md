# v108 EMA Crossover re-arm rescue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`
**Bump:** none until wiring; bot minor if a K > 1 ships (alert stream gains entries, badge flips)
**Edge:** volume

**Goal:** Let EMA Crossover take up to K pullback-touch *events* per held cross (per direction, default K=1 = today, bit-for-bit), then measure K ∈ {2, 3} through v103's pre-registered funnel and ship a direction's K only when that direction passes.

**Architecture:** `ema_cross_entries`'s nested `_first_touch_after` becomes two module-level helpers, `_pullback_touches` and `_mark_touch_events`, driven by the new `DEFAULT_PARAMS["EMA Crossover"]` keys `max_touches_bull` / `max_touches_bear`. `scripts/backtest/measure_fib_v103.py` gains mechanism `E`. Its cell context sets only the scored direction's knob, and its Stage 0 gains the "mechanism inert" clause. `fib_funnel.py`'s Stage 1/2 logic is reused unchanged. It iterates only `spec.grid = (2, 3)`, so the K=1 reference can never be selected. Measurement is pre-registered and committed before any count or collect.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, the v103 funnel (`fib_funnel.py`, `measure_fib_v103.py`), the extended 2010-2025 OHLCV cache.

## Global Constraints

- **Parity:** `max_touches_bull = max_touches_bear = 1` must reproduce today's entries bit-for-bit. The code ships inert.
- **Touch event:** a bar in the existing touch mask whose previous bar is not in the mask. A run of consecutive touching bars is one event. **Parity decision (written down here, see V108-1):** inside a cross's window, the first touching bar always starts an event, even when the bar before it (the cross bar itself) also touched. Without this, K=1 would drop the case where the cross bar and the bar after it both touch, and parity would break.
- **Unchanged:** `pullback_max_bars=15`, all ten ANDed filters, the stop/target arithmetic, and the absence of any `STRATEGY_GATES["EMA Crossover"]` entry. No cooldown knob.
- **No-lookahead:** a touch event at bar `j` reads bars `<= j` only (the cross at `ci < j`, the touch mask at `j` and `j-1`).
- **Harness:** mechanism `E` = `SimpleNamespace(strategy="EMA Crossover", grid=(2, 3), loosest=3, baseline=1, inert_ratio=1.15)`. The cell sets only `max_touches_<dir>` for the direction being scored. The `K=1` reference is reported and never eligible to win.
- **Windows:** `TRAIN_EXT = 2010-01-01..2023-12-31`. `FOLD_YEARS = 2013..2023` (11 anchored folds from 2010). `VALIDATION = 2024-01-01..2025-12-31`.
- **Stage 0 (per direction):** closes when `K=3` TRAIN_EXT signals < 30 (`MIN_N_TRAIN`), **or** when `K=3` signals < **1.15×** the `K=1` signals (mechanism inert).
- **Tier 1:** WR ≥ 50, ExpR > 0, N ≥ 30 (≥ 15 on VALIDATION), scratch+timeout share ≤ 0.5. **Tier 2:** ExpR > 0, ticker-cluster bootstrap lower bound > 0, and the same floors. Plateau: the cell and every grid neighbour pass the same tier. **Only a Tier 1 winner can earn `VALIDATED`.**
- **Arithmetic:** `exit_model="v2"`, `scale_out=True`, `tp2_mode="levels"`, `frictions=True`, `one_at_a_time=True`, level lifecycle as today. All ten horizons pooled. Directions scored separately. Bearish rows go through the v93 laggard rule, exactly as v103.
- **Cache:** the extended cache is git-ignored, so the worktree has none. Every measurement command sets `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext`, the main tree's copy, as an absolute path. A relative override resolves against the worktree root, where the cache does not exist. `require_ext_cache` checks only the directory name, so the absolute path passes it.
- **Universe:** the 77-name production watchlist is passed with `--tickers`, because a worktree's `data/watchlist.json` is a 3-ticker fixture. It has sha256 `4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de` of the comma-joined sorted list, re-checked 2026-09-27, the same as v103. 73 names survive the liquidity filter. **A run reporting any `universe_n` other than 73 is discarded.** The literal list is:
  `AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CRWV,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SI=F,SNDK,SNOW,SNPS,SOFI,SPCX,STX,TSLA,UBER,UNH,V,WDC,WMT`
- **Honesty:** `K=1` cannot win. If `K=1` would clear and no `K>1` cell does, the verdict is NO-LIFT. The 2026-07 VALIDATION read (N=36, WR 75.0%) is consulted for nothing. No threshold, grid value or window changes after the pre-registration commit. The pre-registration is committed **before the first `count` run** (the spec's "before any measurement"), and so before any `collect`.
- **One VALIDATION shot per direction**, ever. It runs only at the committed evaluate JSON's `validation_cell`. Closed rows in `docs/claude/backtest-methodology.md` are never re-run.
- **Complexity:** every function written or changed stays at cyclomatic complexity < 15 (`python -m radon cc -s -n C <files>` prints nothing).
- **Tests:** per task, use `python scripts/dev/testrun.py file <one test file>`. The full suite runs once, in V108-10.
- **Commits:** every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Stage by explicit path, never `git add -A` or `git add data/`.

## Execution setup (controller, before V108-1)

Create the worktree per the `worktree-lifecycle` skill, named after this plan: `.claude/worktrees/2026-09-27-v108-ema-crossover-rearm-rescue/`, branch `2026-09-27-v108-ema-crossover-rearm-rescue`, off current `main` (which carries the spec at `cc68687c` and this plan). Every task runs inside that worktree, from its root, with no `cd` in Bash. The spec and plan stay committed on `main`, and the branch merges back in V108-10.

## Parallelisation

- **Group 1 (parallel): V108-1 and V108-2.** The files are disjoint (`entry_filters.py` + `tests/market/test_ema_rearm.py` versus `measure_fib_v103.py` + `tests/scripts/test_measure_fib_v103.py`). There is no contract dependency: V108-2 needs only the param *names* `max_touches_bull` / `max_touches_bear`, which the spec fixes. Its tests `monkeypatch.setitem` both keys, so they pass with or without V108-1. The two agents share one worktree index, so each commits with a pathspec (`git commit -m ... -- <its paths>`). That commits only its own files, even if the other agent has staged something.
- **Sequential:**
  - V108-3 runs after Group 1, because it drives the real `ema_cross_entries` (V108-1) through mechanism `E` (V108-2).
  - V108-4 (pre-registration) runs after V108-3, because it records the commit the scripts under test sit at, and the spec requires it before any measurement.
  - V108-5 → V108-6 → V108-7 → V108-8 → V108-9 → V108-10 form a strict chain. Each consumes the previous task's committed output: Stage 0 gates collect, the committed evaluate JSON gates VALIDATION, and the verdicts gate wiring and close-out. The full suite runs once, last.
  - Inside V108-7, the two directions' shots are separate processes with separate outputs, so they may run concurrently.

---

# Phase A — Code (worktree branch)

### Task V108-1: `max_touches_bull` / `max_touches_bear` — first K touch events per held cross

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (`DEFAULT_PARAMS["EMA Crossover"]` ~line 440, `ema_cross_entries` ~line 454)
- Create: `tests/market/test_ema_rearm.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `entry_filters._pullback_touches(cross_mask: pd.Series, touch_mask: pd.Series, window: int, max_touches: int) -> pd.Series` (bool, same index as `cross_mask`).
  - `entry_filters._mark_touch_events(out: np.ndarray, touches: np.ndarray, start: int, stop: int, max_touches: int) -> None`.
  - `DEFAULT_PARAMS["EMA Crossover"]["max_touches_bull"] == 1` and `["max_touches_bear"] == 1`.
  - `ema_cross_entries` reads `p["max_touches_bull"]` for the bullish side and `p["max_touches_bear"]` for the bearish side.

- [ ] **Step 1: Load the `no-lookahead` skill** (this task edits entry-signal computation under `swingbot/core/market/`).

- [ ] **Step 2: Write the failing tests**

Create `tests/market/test_ema_rearm.py`:

```python
"""v108: EMA Crossover re-arm -- the first K pullback touch *events* per held cross.

A touch event is a touching bar whose previous bar did not touch, so a run of
consecutive touching bars is one event. Inside a cross's window the first
touching bar always starts an event, even when the cross bar itself touched:
that is what keeps K=1 bit-for-bit equal to the pre-v108 first-touch rule
(`_legacy_first_touch` below is a verbatim copy of it).
"""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, _pullback_touches, ema_cross_entries
from swingbot.core.market.indicators import ema
from swingbot.core.market.strategy_types import HORIZONS
from tests.conftest import make_ohlcv

WINDOW = 15


def _legacy_first_touch(cross_mask, touch_mask, window):
    """Verbatim copy of the pre-v108 nested `_first_touch_after`."""
    out = pd.Series(False, index=cross_mask.index)
    for ci in np.where(cross_mask.values)[0]:
        for j in range(ci + 1, min(ci + 1 + window, len(cross_mask))):
            if touch_mask.values[j]:
                out.iloc[j] = True
                break                     # first touch only
    return out


def _series(bits):
    return pd.Series([bit == "1" for bit in bits], index=pd.RangeIndex(len(bits)))


def _bits(series):
    return "".join("1" if value else "0" for value in series)


def _wave_frame(seed=4, n=900):
    """Seeded trend + oscillation: many held crosses, several multi-touch legs.

    Seed 4 on 4w gives one K=1 bullish entry and two at K=3 (checked when the
    plan was written); the tests assert inequalities, not those counts.
    """
    rng = np.random.default_rng(seed)
    i = np.arange(n)
    closes = 100 * np.exp(0.0008 * i + 0.06 * np.sin(i / 14) + np.cumsum(rng.normal(0, 0.012, n)))
    return make_ohlcv(closes, spread_pct=2.0, start="2012-01-02")


def _masks(df, horizon_key):
    h = HORIZONS[horizon_key]
    fast = ema(df["Close"], h["ema_fast"])
    diff = fast - ema(df["Close"], h["ema_slow"])
    bull_cross = (diff.shift(2) <= 0) & (diff.shift(1) > 0) & (diff > 0)
    bear_cross = (diff.shift(2) >= 0) & (diff.shift(1) < 0) & (diff < 0)
    bull_touch = (df["Low"] <= fast) & (df["Close"] > fast)
    bear_touch = (df["High"] >= fast) & (df["Close"] < fast)
    return [(bull_cross, bull_touch), (bear_cross, bear_touch)]


# -- touch-event counting (hand-built masks) ---------------------------------

def test_consecutive_touching_bars_are_one_event():
    got = _pullback_touches(_series("1000000000"), _series("0111001100"), WINDOW, 3)
    assert _bits(got) == "0100001000"


def test_k_caps_the_events_taken_per_cross():
    cross, touch = _series("100000000000"), _series("010101010100")
    assert _bits(_pullback_touches(cross, touch, WINDOW, 1)) == "010000000000"
    assert _bits(_pullback_touches(cross, touch, WINDOW, 2)) == "010100000000"


def test_touches_past_the_window_are_ignored():
    got = _pullback_touches(_series("10000000"), _series("00001010"), 4, 3)
    assert _bits(got) == "00001000"


def test_a_run_that_starts_on_the_cross_bar_still_counts_once():
    got = _pullback_touches(_series("1000"), _series("1110"), WINDOW, 2)
    assert _bits(got) == "0100"


def test_a_new_cross_resets_the_count():
    cross, touch = _series("1000010000"), _series("0101001010")
    assert _bits(_pullback_touches(cross, touch, WINDOW, 1)) == "0100001000"
    assert _bits(_pullback_touches(cross, touch, WINDOW, 2)) == "0101001010"


# -- K=1 parity with the pre-v108 rule -----------------------------------------

@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_k1_equals_the_legacy_first_touch_on_real_masks(seed):
    df = _wave_frame(seed)
    for horizon_key in HORIZONS:
        for cross, touch in _masks(df, horizon_key):
            legacy = _legacy_first_touch(cross, touch, WINDOW)
            assert _pullback_touches(cross, touch, WINDOW, 1).equals(legacy), horizon_key


@pytest.mark.parametrize("seed", [2, 4])
def test_default_entries_are_bit_for_bit_the_legacy_entries(monkeypatch, seed):
    df = _wave_frame(seed)
    today = {hz: ema_cross_entries(df, hz) for hz in HORIZONS}
    monkeypatch.setattr(entry_filters, "_pullback_touches",
                        lambda cross, touch, window, max_touches: _legacy_first_touch(cross, touch, window))
    for horizon_key in HORIZONS:
        legacy_bull, legacy_bear = ema_cross_entries(df, horizon_key)
        assert today[horizon_key][0].equals(legacy_bull), horizon_key
        assert today[horizon_key][1].equals(legacy_bear), horizon_key


def test_defaults_ship_inert():
    params = DEFAULT_PARAMS["EMA Crossover"]
    assert (params["max_touches_bull"], params["max_touches_bear"]) == (1, 1)
    assert (params["entry_mode"], params["pullback_max_bars"]) == ("pullback", 15)


# -- the knobs reach ema_cross_entries, per direction ------------------------

def test_bullish_knob_adds_entries_and_leaves_bearish_alone():
    df = _wave_frame(4)
    bull1, bear1 = ema_cross_entries(df, "4w")
    bull3, bear3 = ema_cross_entries(df, "4w", params={"max_touches_bull": 3})
    assert int(bull3.sum()) > int(bull1.sum())
    assert bool((bull3 | ~bull1).all())          # K=3 keeps every K=1 entry
    assert bear3.equals(bear1)


def test_bearish_knob_leaves_bullish_alone():
    df = _wave_frame(4)
    bull1, _ = ema_cross_entries(df, "4w")
    bull, _ = ema_cross_entries(df, "4w", params={"max_touches_bear": 3})
    assert bull.equals(bull1)


# -- no lookahead --------------------------------------------------------------

def test_touch_events_never_read_future_bars():
    rng = np.random.default_rng(7)
    cross = pd.Series(rng.random(300) < 0.05)
    touch = pd.Series(rng.random(300) < 0.4)
    full = _pullback_touches(cross, touch, WINDOW, 3)
    for cut in range(1, 300):
        assert _pullback_touches(cross.iloc[:cut], touch.iloc[:cut], WINDOW, 3).equals(full.iloc[:cut]), cut


def test_truncating_the_frame_keeps_every_earlier_k3_entry():
    df = _wave_frame(4)
    params = {"max_touches_bull": 3, "max_touches_bear": 3}
    full_bull, full_bear = ema_cross_entries(df, "4w", params=params)
    entry_bars = np.flatnonzero((full_bull | full_bear).to_numpy())
    cuts = sorted(set(range(260, len(df), 40)) | {int(i) + 1 for i in entry_bars})
    for cut in cuts:
        bull, bear = ema_cross_entries(df.iloc[:cut], "4w", params=params)
        assert bull.equals(full_bull.iloc[:cut]) and bear.equals(full_bear.iloc[:cut]), cut
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`
Expected: FAIL. Collection errors with `ImportError: cannot import name '_pullback_touches'`.

- [ ] **Step 4: Implement**

In `swingbot/core/market/entry_filters.py`, extend `DEFAULT_PARAMS["EMA Crossover"]`. Keep the existing comment block and keys, and add after `"entry_mode": "pullback", "pullback_max_bars": 15,`:

```python
    # v108 re-arm: enter on the first K pullback touch *events* after each held
    # cross (a run of consecutive touching bars is one event). 1 = first touch
    # only -- the v84-measured mechanism, bit-for-bit. Each direction has its own
    # knob so a per-direction verdict maps onto it
    # (docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md).
    "max_touches_bull": 1, "max_touches_bear": 1,
```

Directly above `def ema_cross_entries`, add the two helpers:

```python
def _mark_touch_events(out, touches, start, stop, max_touches):
    """Mark up to `max_touches` touch events in bars [start, stop).

    A touch event is a touching bar whose previous bar did not touch; the
    first touching bar at `start` always counts, so max_touches=1 is exactly
    "the first touch after the cross". Reads touches[j] and touches[j-1] only.
    """
    taken = 0
    for j in range(start, stop):
        if not touches[j] or (j > start and touches[j - 1]):
            continue
        out[j] = True
        taken += 1
        if taken >= max_touches:
            return


def _pullback_touches(cross_mask, touch_mask, window, max_touches):
    """First `max_touches` touch events inside `window` bars after each held cross.

    Every cross counts its own events from zero. No lookahead: an event at bar
    j depends on the cross at ci < j and the touch mask at j and j-1.
    """
    touches = np.asarray(touch_mask, dtype=bool)
    out = np.zeros(len(touches), dtype=bool)
    for ci in np.flatnonzero(np.asarray(cross_mask, dtype=bool)):
        _mark_touch_events(out, touches, ci + 1, min(ci + 1 + window, len(touches)), max_touches)
    return pd.Series(out, index=cross_mask.index)
```

In `ema_cross_entries`, replace the whole pullback block from `if p.get("entry_mode") == "pullback":` through `held_bear = _first_touch_after(held_bear, touched_bear).fillna(False)`, including the nested `def _first_touch_after`, with:

```python
    if p.get("entry_mode") == "pullback":
        window = int(p.get("pullback_max_bars", 10))
        touched_bull = (df["Low"] <= fast) & (df["Close"] > fast)
        touched_bear = (df["High"] >= fast) & (df["Close"] < fast)
        held_bull = _pullback_touches(held_bull, touched_bull, window, int(p.get("max_touches_bull", 1)))
        held_bear = _pullback_touches(held_bear, touched_bear, window, int(p.get("max_touches_bear", 1)))
```

Keep the `# --- rescue mode (Task 107): enter on the pullback, not the cross ---` comment above it. Change nothing else in the function.

- [ ] **Step 5: Run the new tests and the existing EMA tests**

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`
Expected: PASS (all).
Run: `python scripts/dev/testrun.py file tests/market/test_rescue_ema.py`
Expected: PASS. It pins cross mode, the adopted pullback default and the existing no-lookahead check.
Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters.py`
Expected: PASS.

If `test_bullish_knob_adds_entries_and_leaves_bearish_alone` fails only on `int(bull3.sum()) > int(bull1.sum())`, the fixture no longer produces a second leg on 4w. Scan seeds 1..40 on `"4w"` and `"2m"` for one where K=3 > K=1, pin that seed and horizon, and say so in the commit message. Never weaken the assertion to `>=`.

- [ ] **Step 6: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py`
Expected: no line naming `ema_cross_entries`, `_pullback_touches` or `_mark_touch_events`. Any other function it lists was already there before this task (`git stash` + re-run to confirm) and is untouched.

- [ ] **Step 7: Commit**

```bash
git add swingbot/core/market/entry_filters.py tests/market/test_ema_rearm.py
git commit -m "feat(v108): EMA Crossover max_touches_bull/bear -- first K pullback touch events per cross (default 1, inert)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/market/entry_filters.py tests/market/test_ema_rearm.py
```

---

### Task V108-2: Mechanism `E` in the v103 funnel — per-direction cell, inert Stage 0 clause

**Files:**
- Modify: `scripts/backtest/measure_fib_v103.py` (module docstring, `MECHANISMS`, `mechanism_cell`, `collect_trades`, `count_signals`, `stage0_closures`)
- Modify: `tests/scripts/test_measure_fib_v103.py` (append tests)

**Interfaces:**
- Consumes: the param names `max_touches_bull` / `max_touches_bear` in `DEFAULT_PARAMS["EMA Crossover"]` (the names are fixed by the spec, and the values come from V108-1 at runtime).
- Produces:
  - `MECHANISMS["E"]` with `.strategy == "EMA Crossover"`, `.grid == (2, 3)`, `.loosest == 3`, `.baseline == 1` and `.inert_ratio == 1.15`. A and C gain `inert_ratio=None`.
  - `TOUCH_PARAMS = {"bullish": "max_touches_bull", "bearish": "max_touches_bear"}`.
  - `mechanism_cell(mech, value, direction=None)` is a context manager. Mechanism E requires `direction` and raises `ValueError` without one.
  - `stage0_closures(counts, mech) -> list[str]` closes on the N floor or, when `inert_ratio` is set, on `total(loosest) < inert_ratio * total(baseline)`.
  - CLI: `--mechanism E` is accepted by `count` / `collect` / `validation`, since `choices=tuple(MECHANISMS)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_measure_fib_v103.py`:

```python
# -- v108 mechanism E (EMA Crossover re-arm) ---------------------------------

def _touch_params(monkeypatch, module):
    params = module.DEFAULT_PARAMS["EMA Crossover"]
    monkeypatch.setitem(params, "max_touches_bull", 1)
    monkeypatch.setitem(params, "max_touches_bear", 1)
    return params


def _knobs(params):
    return params["max_touches_bull"], params["max_touches_bear"]


def test_mechanism_e_is_registered_with_k1_as_reference_only():
    spec = _module().MECHANISMS["E"]
    assert (spec.strategy, spec.grid, spec.loosest, spec.baseline, spec.inert_ratio) == ("EMA Crossover", (2, 3), 3, 1, 1.15)
    assert spec.baseline not in spec.grid


def test_mechanism_e_cell_sets_only_the_scored_direction_and_restores(monkeypatch):
    module = _module()
    params = _touch_params(monkeypatch, module)
    with module.mechanism_cell("E", 3, "bullish"):
        assert _knobs(params) == (3, 1)
    with module.mechanism_cell("E", 2, "bearish"):
        assert _knobs(params) == (1, 2)
    assert _knobs(params) == (1, 1)
    with pytest.raises(ValueError):
        module.mechanism_cell("E", 2)


def test_collect_trades_sets_each_directions_knob_during_its_own_pass(monkeypatch):
    module, frame, seen = _module(), make_ohlcv([100.0] * 300, start="2012-01-02"), []
    params = _touch_params(monkeypatch, module)
    def run_fn(ticker, df, strategy, horizon, **kwargs):
        seen.append((strategy, *_knobs(params)))
        return NS(trades=[])
    module.collect_trades("E", {"AAA": frame}, {}, 3, module.TRAIN_EXT, horizons=("4w",), run_fn=run_fn, progress=NS(tick=lambda label: None))
    assert seen == [("EMA Crossover", 3, 1), ("EMA Crossover", 1, 3)]
    assert _knobs(params) == (1, 1)


def test_count_signals_scores_each_direction_under_its_own_knob(monkeypatch):
    module = _module()
    import pandas as pd
    params = _touch_params(monkeypatch, module)
    def fake(strategy, df, horizon):
        bull, bear = pd.Series(False, index=df.index), pd.Series(False, index=df.index)
        bull.iloc[:params["max_touches_bull"]] = True
        bear.iloc[:10 * params["max_touches_bear"]] = True
        return bull, bear
    monkeypatch.setattr(module, "entries_for", fake)
    counts = module.count_signals("E", {"AAA": make_ohlcv([100.0] * 50, start="2012-01-02")}, (1, 3), horizons=("4w",))
    assert {key: cell["total"] for key, cell in counts.items()} == {"1|bullish": 1, "1|bearish": 10, "3|bullish": 3, "3|bearish": 30}
    assert _knobs(params) == (1, 1)


def test_stage0_closes_e_when_the_mechanism_is_inert_or_thin():
    stage0 = _module().stage0_closures
    assert stage0({"3|bullish": {"total": 114}, "1|bullish": {"total": 100},
                   "3|bearish": {"total": 115}, "1|bearish": {"total": 100}}, "E") == ["bullish"]
    assert stage0({"3|bullish": {"total": 29}, "1|bullish": {"total": 5},
                   "3|bearish": {"total": 60}, "1|bearish": {"total": 40}}, "E") == ["bullish"]


def _tier1(direction="bullish", win=2.0):
    return [row for index in range(10) for row in (
        [_row(f"T{index}", "win", win, direction) for _ in range(4)]
        + [_row(f"T{index}", "loss", -1.0, direction) for _ in range(2)]
    )]


def _losing(direction="bullish"):
    return [row for index in range(10) for row in (
        [_row(f"T{index}", "win", 1.0, direction)]
        + [_row(f"T{index}", "loss", -1.0, direction) for _ in range(5)]
    )]


def test_evaluate_e_never_selects_the_k1_reference():
    module = _module()
    result = module.evaluate("E", {"1": _tier1(), "2": _losing(), "3": _losing()}, closed=("bearish",), **FAST)
    bullish = result["bullish"]
    assert bullish["baseline"]["n"] == 60 and bullish["baseline"]["win_rate"] > 50
    assert bullish["stage1"]["winner"] is None and bullish["proceed_to_validation"] is False
    assert set(bullish["stage1"]["cells"]) == {"2", "3"}
    assert all(fold["tol"] in (None, 2, 3) for fold in bullish["stage2"]["folds"])


def test_evaluate_e_picks_the_higher_expectancy_tier1_plateau_cell():
    module = _module()
    result = module.evaluate("E", {"1": _losing(), "2": _tier1(win=2.0), "3": _tier1(win=3.0)}, closed=("bearish",), **FAST)
    assert (result["bullish"]["stage1"]["winner"], result["bullish"]["stage1"]["winner_tier"]) == (3, 1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py`
Expected: FAIL, with `KeyError: 'E'` in the new tests. The existing A/C tests still pass.

- [ ] **Step 3: Implement**

In `scripts/backtest/measure_fib_v103.py`:

1. Module docstring:

```python
"""v103 Fibonacci level-stop (A) and continuation (C) funnel; v108 EMA Crossover re-arm (E)."""
```

2. Replace the `MECHANISMS` block with:

```python
MECHANISMS = {
    "A": SimpleNamespace(strategy="Fibonacci", grid=(0.1, 0.25, 0.5), loosest=0.1, baseline=0.0, inert_ratio=None),
    "C": SimpleNamespace(strategy="Fibonacci Continuation", grid=(0.5, 0.618, 0.786), loosest=0.786, baseline=None, inert_ratio=None),
    # v108: K pullback touch events per held cross. K=1 (today) is the reference
    # arm -- reported, never in the grid, so Stage 1/2 can never select it.
    # Stage 0 also closes a direction whose K=3 count is < 1.15x its K=1 count.
    "E": SimpleNamespace(strategy="EMA Crossover", grid=(2, 3), loosest=3, baseline=1, inert_ratio=1.15),
}
TOUCH_PARAMS = {"bullish": "max_touches_bull", "bearish": "max_touches_bear"}
```

3. Replace `mechanism_cell` with:

```python
def mechanism_cell(mech, value, direction=None):
    if mech == "A":
        enabled = float(value) > 0
        return _config_values(FIB_LEVEL_STOP_ATR=float(value), FIB_LEVEL_STOP_DIRECTIONS="bullish,bearish" if enabled else "")
    if mech == "E":
        if direction not in TOUCH_PARAMS:
            raise ValueError("mechanism E sets one direction's max_touches; pass direction='bullish' or 'bearish'")
        return _param_value(MECHANISMS["E"].strategy, TOUCH_PARAMS[direction], int(value))
    return _param_value(MECHANISMS["C"].strategy, "d_max", float(value))
```

4. In `collect_trades`, move the cell inside the direction loop. The function body after `rows = []` becomes:

```python
    for direction in directions:
        with mechanism_cell(mech, value, direction):
            rows.extend(_direction_pass(spec.strategy, frames, asof_map, direction, window, horizons, run_fn, progress, f"{mech} {cell_key(value)}"))
    return rows
```

5. `count_signals` becomes:

```python
def count_signals(mech, frames, values, *, horizons=ALL_HZ):
    strategy, results = MECHANISMS[mech].strategy, {}
    for value in values:
        for direction in DIRECTIONS:
            with mechanism_cell(mech, value, direction):
                results[f"{cell_key(value)}|{direction}"] = _count_direction(strategy, frames, direction, horizons)
    return results
```

For A and C, entering the cell once per direction applies the same setting as before, so their behaviour is unchanged.

6. Replace `stage0_closures` with:

```python
def _inert(counts, spec, direction):
    if spec.inert_ratio is None:
        return False
    loosest = counts[f"{cell_key(spec.loosest)}|{direction}"]["total"]
    return loosest < spec.inert_ratio * counts[f"{cell_key(spec.baseline)}|{direction}"]["total"]


def stage0_closures(counts, mech):
    spec = MECHANISMS[mech]
    key = cell_key(spec.loosest)
    return [direction for direction in DIRECTIONS
            if counts[f"{key}|{direction}"]["total"] < MIN_N_TRAIN or _inert(counts, spec, direction)]
```

`_cmd_count` and `_cmd_collect` already build `values = (baseline,) + grid`, i.e. `(1, 2, 3)` for E. `evaluate` already reports the baseline and scores only `spec.grid`, and `validation` already collects one direction at the committed cell. Leave those unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_v103.py`
Expected: PASS (all, old and new).
Run: `python scripts/dev/testrun.py file tests/scripts/test_fib_funnel.py`
Expected: PASS (untouched, sanity).

- [ ] **Step 5: Complexity check**

Run: `python -m radon cc -s -n C scripts/backtest/measure_fib_v103.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add scripts/backtest/measure_fib_v103.py tests/scripts/test_measure_fib_v103.py
git commit -m "feat(v108): mechanism E in the v103 funnel -- per-direction max_touches cell, K=1 reference only, Stage 0 inert clause

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- scripts/backtest/measure_fib_v103.py tests/scripts/test_measure_fib_v103.py
```

---

### Task V108-3: Contract test — mechanism E drives the real `ema_cross_entries`

**Files:**
- Create: `tests/scripts/test_measure_ema_rearm.py`

**Interfaces:**
- Consumes: `entry_filters.DEFAULT_PARAMS["EMA Crossover"]["max_touches_*"]` and `ema_cross_entries` (V108-1), plus `measure_fib_v103.count_signals("E", ...)` and `mechanism_cell("E", ...)` (V108-2).
- Produces: nothing new. This task proves that the knob the harness sets is the knob the entry function reads.

- [ ] **Step 1: Write the test**

```python
"""v108: mechanism E moves the real EMA Crossover entries through the v103 harness.

V108-1 and V108-2 are each tested alone; this pins the seam between them --
the key the harness sets is the key ema_cross_entries reads, K=1 through the
harness equals today's default, and every cell restores the defaults.
"""
import sys
from pathlib import Path

import numpy as np

from tests.conftest import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))
HORIZONS = ("4w", "2m")


def _wave_frame(seed=4, n=900):
    rng = np.random.default_rng(seed)
    i = np.arange(n)
    closes = 100 * np.exp(0.0008 * i + 0.06 * np.sin(i / 14) + np.cumsum(rng.normal(0, 0.012, n)))
    return make_ohlcv(closes, spread_pct=2.0, start="2012-01-02")


def _default_total(frame, side):
    from swingbot.core.market.entry_filters import entries_for
    return sum(int(entries_for("EMA Crossover", frame, horizon)[side].sum()) for horizon in HORIZONS)


def test_mechanism_e_counts_real_entries_per_direction():
    import measure_fib_v103 as module
    from swingbot.core.market.entry_filters import DEFAULT_PARAMS
    frames = {"AAA": _wave_frame()}
    before = dict(DEFAULT_PARAMS["EMA Crossover"])
    counts = module.count_signals("E", frames, (1, 2, 3), horizons=HORIZONS)
    assert DEFAULT_PARAMS["EMA Crossover"] == before
    assert counts["1|bullish"]["total"] == _default_total(frames["AAA"], 0)
    assert counts["1|bearish"]["total"] == _default_total(frames["AAA"], 1)
    for direction in ("bullish", "bearish"):
        totals = [counts[f"{k}|{direction}"]["total"] for k in (1, 2, 3)]
        assert totals == sorted(totals), direction
    assert counts["3|bullish"]["total"] > counts["1|bullish"]["total"]


def test_mechanism_e_cell_changes_the_live_entry_function():
    import measure_fib_v103 as module
    frame = _wave_frame()
    base = _default_total(frame, 0)
    with module.mechanism_cell("E", 3, "bullish"):
        assert _default_total(frame, 0) > base
    with module.mechanism_cell("E", 3, "bearish"):
        assert _default_total(frame, 0) == base
    assert _default_total(frame, 0) == base
```

- [ ] **Step 2: Run it**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_ema_rearm.py`
Expected: PASS. It is written after both halves exist, so a failure here is a real seam bug. Check first that `TOUCH_PARAMS` in `measure_fib_v103.py` spells the keys exactly as `DEFAULT_PARAMS["EMA Crossover"]` does.

- [ ] **Step 3: Commit**

```bash
git add tests/scripts/test_measure_ema_rearm.py
git commit -m "test(v108): mechanism E drives the real EMA Crossover entries through the harness

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- tests/scripts/test_measure_ema_rearm.py
```

---

# Phase B — Pre-registration and measurement (same worktree branch)

**Conventions for every task in this phase:**
- `<date>` is the run date (`YYYY-MM-DD`). Pick it once in V108-4 and reuse it in every file name. Result files live under `docs/superpowers/results/`.
- **Load `backtest-gate` before every measurement command** (V108-5, 6 and 7). **Load `pooled-numbers` before writing any N / WR / ExpR figure.** Every figure carries its N and window, and comes from the JSON the script wrote in that task.
- `data/v108_collect_E.json` stays local, is git-ignored by V108-4 and is never staged.
- Long runs go to the `backtest-runner` agent with progress in a scratchpad log. `collect` and `validation` print `[k/N] P% ...` lines, which satisfies the percent rule past 15 minutes. The log is deleted on success. CLAUDE.md chunks long runs per strategy; this is one strategy, so it is one chunk.

### Task V108-4: Pre-registration (committed before any count or collect)

**Files:**
- Modify: `.gitignore`
- Create: `docs/superpowers/results/<date>-v108-preregistration.md`

**Interfaces:**
- Consumes: V108-1..3's commits. Record the scripts-under-test hash with `git log -1 --format=%h -- scripts/backtest/measure_fib_v103.py scripts/backtest/fib_funnel.py swingbot/core/market/entry_filters.py`.
- Produces: the committed pre-registration path. V108-7's `validation --preregistration` refuses it unless it is committed and unchanged.

- [ ] **Step 1: Git-ignore the collect dump.** In `.gitignore`, directly under the `data/v103_*.json` line, add:

```gitignore
data/v108_*.json
```

- [ ] **Step 2: Re-check the universe hash** (from the main tree's watchlist, not the worktree fixture):

```bash
python -c "import json,hashlib; n=sorted(json.load(open('E:/Documents/Private/Projects/Discord-Bot/data/watchlist.json',encoding='utf-8'))); print(len(n), hashlib.sha256(','.join(n).encode()).hexdigest())"
```

Required: `77 4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de`. If it differs, **stop and ask the controller**. The production watchlist changed, and the universe has to be decided before registration, not after.

- [ ] **Step 3: Read the constants from the files, not from this plan**

```bash
grep -n "^[A-Z_]* = " scripts/backtest/fib_funnel.py
grep -n "\"E\":\|TOUCH_PARAMS" scripts/backtest/measure_fib_v103.py
grep -n "^TRAIN_EXT\|^VALIDATION" scripts/backtest/measure_fib_confluence.py
grep -n "BOOTSTRAP_RESAMPLES =" swingbot/core/backtesting/acceptance.py
```

If any printed value disagrees with the text below, the file wins. Stop and report the mismatch before writing.

- [ ] **Step 4: Write `docs/superpowers/results/<date>-v108-preregistration.md`** with this content. Fill `<date>`, `<branch head>` and `<scripts hash>`, and change nothing else:

```markdown
# v108 pre-registration -- EMA Crossover re-arm (mechanism E)

Registered <date>, before any count, collect or VALIDATION run. Committed on branch
`2026-09-27-v108-ema-crossover-rearm-rescue` on top of `<branch head>`. Scripts under test:
`scripts/backtest/measure_fib_v103.py` (mechanism `E`), `scripts/backtest/fib_funnel.py` and
`swingbot/core/market/entry_filters.py`, last changed at `<scripts hash>`.
Spec: `docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`.
Every constant below was read from those files.

## Why this is a new mechanism, not a re-run

v84 closed EMA Crossover's pullback re-measurement at fold stability (N=55 on TRAIN 2020-2023, every year
N < 15 but one; `results/2026-09-10-v84-ema-crossover-preregistration.md`) with "reopening needs a genuinely new
mechanism". `ema_cross_entries` kept only the **first** fast-EMA touch after each held cross. This registration
changes **which bars can be entries**: the first K touch *events* per held cross. That is a change to the
signal, not to the instrument. The extended 2010-2023 history is the instrument only.

## Mechanism

- `DEFAULT_PARAMS["EMA Crossover"]` gains `max_touches_bull` and `max_touches_bear`, both default `1`. At `1` the
  entries are bit-for-bit today's (pinned by `tests/market/test_ema_rearm.py`).
- A touch event is a bar in the existing touch mask whose previous bar is not. A run of touching bars is one
  event. Inside a cross's `pullback_max_bars = 15` window the first touching bar always starts an event (parity
  with K=1). Every held cross counts its own events from zero.
- Unchanged: `pullback_max_bars = 15`, all ten ANDed filters, stop/target arithmetic, no `STRATEGY_GATES` entry,
  no cooldown knob (`one_at_a_time` forbids overlapping trades).
- **Grid** `K in {2, 3}`, loosest `K = 3`. **Reference** `K = 1`: reported, never eligible to win. The harness
  sets only the scored direction's `max_touches_<dir>`; the other direction stays at 1.

## Windows

- `TRAIN_EXT = 2010-01-01..2023-12-31`.
- `FOLD_YEARS = 2013..2023` (11 folds), anchored: fold Y trains on 2010-01-01..Y-1 and tests on year Y.
- `VALIDATION = 2024-01-01..2025-12-31`, read only by the `validation` command.

## Stage 0 (free; signal counts on TRAIN_EXT, no backtest)

Per direction, the direction closes with its budget intact if **either**:
1. `K = 3` has fewer than `MIN_N_TRAIN = 30` TRAIN_EXT signals; or
2. **mechanism inert:** `K = 3` produces fewer than **1.15x** the `K = 1` signal count (`count_signals`).
Counts are recorded in `<date>-v108-stage0.md`, after this commit.

## Clauses and constants (`fib_funnel.py`)

`WR_FLOOR = 50.0`, `MIN_N_TRAIN = 30`, `MIN_N_VALIDATION = 15`, `MAX_SCRATCH_SHARE = 0.5`
(scratch+timeout share), `FOLD_MIN_N = 15`, `FOLD_POSITIVE_SHARE = 2/3`, `MIN_QUALIFYING_FOLDS = 3`,
`TRAIN_START_YEAR = 2010`, `BOOTSTRAP_SEED = 42`, `BOOTSTRAP_RESAMPLES = 10_000`.

- **Tier 1 (badge tier):** win rate >= 50, ExpR > 0, decided N >= 30 on TRAIN_EXT (>= 15 on VALIDATION),
  scratch+timeout share <= 0.5.
- **Tier 2:** ExpR > 0 **and** the ExpR bootstrap lower bound > 0, plus the same N and scratch floors. No
  win-rate floor. Bootstrap: `acceptance.cluster_bootstrap` over **ticker clusters**, empty baseline arm, 10,000
  resamples, seed 42, lower bound = 2.5th percentile.
- **Only a Tier 1 winner can earn `VALIDATED`.** A Tier 2-only winner still runs Stages 2-3; if it passes, its K
  ships live but the badge stays `WEAK`.

## Stage 1 (TRAIN_EXT, per direction)

A cell counts only if it and every grid neighbour pass the same tier. Winner: the highest-ExpR Tier 1 plateau
cell, else the highest-ExpR Tier 2 plateau cell, else none. VALIDATION scores on the tier Stage 1 assigned and
never changes it.

## Stage 2 (11 anchored folds)

Per fold Y, re-select from `K in {2, 3}` the cell with the highest ExpR on 2010..Y-1 among cells with N >= 30
(none qualifying = an **unselected** fold, counted in the report). Score it on year Y. Clears when **>= 3 folds
have test N >= 15 and >= 2/3 of those have ExpR > 0**. A direction proceeds to VALIDATION only when Stage 1 has
a winner **and** Stage 2 clears.

## Populations and arithmetic

- Both directions as live today: EMA Crossover has no `STRATEGY_GATES` entry, so no direction mask. Bearish rows
  pass through the v93 laggard rule (`apply_laggard_rule`), exactly as v103.
- `exit_model="v2"`, `scale_out=True`, `tp2_mode="levels"`, `frictions=True`, `one_at_a_time=True`,
  `apply_level_lifecycle` as today. All ten horizons (`2w`..`9m`) pooled.

## Data

- Extended cache `data/backtest_cache_ext` (2010-2025, checked in v103's V103-9). The worktree has no copy, so
  every run sets `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext` (the
  main tree's cache, absolute). The shared cache is never written.
- **Universe:** the production watchlist, 77 names, sorted, sha256 of the comma-joined list
  `4452b50f6391e7b3f14a224874b7a0dcc8f4245f7f5cca006c0f0ed7c2dca4de` (identical to v103), passed with
  `--tickers` because the worktree's watchlist is a 3-ticker fixture. 73 survive the liquidity/data-quality
  filter; **a run reporting any other `universe_n` is discarded.**
- **Survivorship bias is stated, not corrected.** Today's watchlist favours survivors, biasing WR and ExpR
  upward in the early years.

## Honesty clause

- **`K = 1` cannot win.** It is the unchanged v84 mechanism on a longer window, reference only. If `K = 1` would
  clear and no `K > 1` cell does, the verdict is NO-LIFT.
- The 2026-07 VALIDATION read of the pullback entry (N=36, WR 75.0%, scored under the deleted fixed
  reward:risk table) is not consulted for any choice.
- No threshold, grid value or window changes after this commit.

## The one-shot rule

At most **one `validation` run per direction (at most two in all)**, only at the committed evaluate output's
`validation_cell`, never at another K, never again after a FAIL. The script enforces it (this file and the
evaluate JSON must be committed and unchanged; it refuses an existing `--out`), and so does this document.

## Outcomes and the registry row (decided before any score)

- **Tier 1 PASS in a direction:** that direction's `max_touches_<dir>` = its winning K. **Tier 2 PASS:** same,
  badge stays `WEAK`. The other direction keeps whatever its own verdict earned (K = 1 unless it also passed).
- `emit-registry` writes one `EMA Crossover` row pooling the VALIDATION rows of every direction that
  **passed**. Status is decided by the script (`registry_status`): `VALIDATED` only when every pooled direction
  passed on Tier 1 and the pooled rows clear the badge clauses, else `WEAK`. It replaces today's row
  (`WEAK`, N=36, 2024-2025, run 2026-07-18; quoted to identify it, used for no decision).
- **No direction passes:** both params stay 1, no row is emitted, today's row stays, a closed-pre-registration
  row goes into `docs/claude/backtest-methodology.md`.

## Not re-run

v84's EMA Crossover row (K = 1 on TRAIN 2020-2023) and the round-2 `pullback_max_bars` grid (closed; stays 15).
```

- [ ] **Step 5: Commit before any measurement**

```bash
git add .gitignore docs/superpowers/results/<date>-v108-preregistration.md
git commit -m "docs(v108): pre-register EMA Crossover re-arm (mechanism E) -- K in {2,3} per direction, TRAIN_EXT, 11 folds, two tiers, one shot per direction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- .gitignore docs/superpowers/results/<date>-v108-preregistration.md
```

Run: `git status --short docs/superpowers/results/ .gitignore`
Expected: nothing listed for these two files.

---

### Task V108-5: Stage 0 — signal counts (K = 1, 2, 3)

**Files:**
- Create: `docs/superpowers/results/<date>-v108-stage0.json`, `docs/superpowers/results/<date>-v108-stage0.md`

**Interfaces:**
- Consumes: V108-4's committed pre-registration.
- Produces: `<date>-v108-stage0.json`, carrying `closed_at_stage0`, which is `collect --stage0`'s input in V108-6.

- [ ] **Step 1: Load `backtest-gate`, then confirm the pre-registration is committed**

Run: `git log --oneline -1 -- docs/superpowers/results/<date>-v108-preregistration.md`
Expected: V108-4's commit. With no output, **stop**: nothing is counted before registration.

- [ ] **Step 2: Count** (free: entry signals on TRAIN_EXT only, no backtest, no VALIDATION data)

```bash
BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py count --mechanism E --out docs/superpowers/results/<date>-v108-stage0.json --tickers "AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CRWV,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SI=F,SNDK,SNOW,SNPS,SOFI,SPCX,STX,TSLA,UBER,UNH,V,WDC,WMT"
```

Expected final line: `v103 count done`. If it runs past 2 minutes, stop it and dispatch the same command to `backtest-runner`, logging to the scratchpad, and delete the log on success.

- [ ] **Step 3: Read the decision and the horizon spread**

```bash
python - <<'EOF'
import json, glob
d = json.load(open(glob.glob("docs/superpowers/results/*-v108-stage0.json")[0], encoding="utf-8"))
print("universe_n", d["universe_n"], "closed_at_stage0", d["closed_at_stage0"])
for direction in ("bullish", "bearish"):
    k1, k3 = d["counts"][f"1|{direction}"]["total"], d["counts"][f"3|{direction}"]["total"]
    print(direction, "K3/K1 =", round(k3 / k1, 3) if k1 else "n/a (K1=0)")
for key, c in d["counts"].items():
    hz = c["by_horizon"]; top2 = sum(sorted(hz.values(), reverse=True)[:2])
    print(f"  {key:10} total={c['total']:5} top2_share={top2 / c['total'] if c['total'] else 0:.0%} by_year={c['by_year']}")
EOF
```

`universe_n` must be 73, or the run is discarded. **Stop and report**, and do not re-run with a different list. `closed_at_stage0` is the decision. Never recompute or override it.

- [ ] **Step 4: Write `docs/superpowers/results/<date>-v108-stage0.md`** with these sections:
  - `## Counts`: one table, rows `K|direction` for K = 1, 2, 3. Columns: total, top-2-horizon share, per-year counts. Mark K = 3 as the loosest cell and K = 1 as the reference.
  - `## Inert check`: per direction, `K3 / K1` against the 1.15 threshold, and the N-floor check (`K3 >= 30`).
  - `## Per-horizon`: `by_horizon` at K = 3 per direction. If the top-2 share is ≥ 80%, say plainly that a PASS would not be a cross-horizon result. This is disclosed, not gated.
  - `## Thin years`: years with 0–5 signals at K = 3, per direction. Stage 2 folds will be thin there.
  - `## Decision`: per direction, either `ENTERS Stage 1` or `NO-LIFT at Stage 0 (<floor: K3=<n> < 30 | inert: K3/K1=<r> < 1.15>)`.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/<date>-v108-stage0.json docs/superpowers/results/<date>-v108-stage0.md
git commit -m "docs(v108): Stage 0 signal counts -- <bullish: enters | NO-LIFT (reason)>, <bearish: ...>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/results/<date>-v108-stage0.json docs/superpowers/results/<date>-v108-stage0.md
```

If both directions close here, skip V108-6 and V108-7, skip V108-8, and go to V108-9.

---

### Task V108-6: Stages 1–2 — collect once, evaluate

**Files:**
- Create (local, never staged): `data/v108_collect_E.json`
- Create: `docs/superpowers/results/<date>-v108-stage12.json`, `docs/superpowers/results/<date>-v108-stage12.md`

**Interfaces:**
- Consumes: `<date>-v108-stage0.json` (V108-5).
- Produces: the committed `<date>-v108-stage12.json`, with per-direction `proceed_to_validation`, `validation_cell` and `tier`. V108-7 consumes it.

- [ ] **Step 1: Load `backtest-gate`.** Confirm that V108-4 and V108-5 are both committed: `git log --oneline -3`.

- [ ] **Step 2: Collect.** Dispatch one background `backtest-runner` with this brief. It is one chunk: one strategy, 3 cells × ≤ 2 directions × 73 tickers × 10 horizons over 14 years, so expect tens of minutes.

> Worktree root, no `cd`: `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py collect --mechanism E --stage0 docs/superpowers/results/<date>-v108-stage0.json --out data/v108_collect_E.json --tickers "AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CRWV,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SI=F,SNDK,SNOW,SNPS,SOFI,SPCX,STX,TSLA,UBER,UNH,V,WDC,WMT" > <scratchpad>/v108_collect_E.log 2>&1`. Progress lines read `[k/N] P% E <cell> <direction> <TICKER>`. Answer "how far along" from the last line's percent. On success, return the final line plus the JSON's `universe_n`, `elapsed_s` and `closed_at_stage0`, and delete the log. On failure, return the last 40 log lines and keep the log.

`universe_n` must be 73, and it must equal Stage 0's. A mismatch means the universe changed between stages: **stop** and record the cause before evaluating.

- [ ] **Step 3: Evaluate** (fast, no backtest)

```bash
python scripts/backtest/measure_fib_v103.py evaluate --rows data/v108_collect_E.json --out docs/superpowers/results/<date>-v108-stage12.json
```

- [ ] **Step 4: Print the verdict fields**

```bash
python - <<'EOF'
import json, glob
ev = json.load(open(glob.glob("docs/superpowers/results/*-v108-stage12.json")[0], encoding="utf-8"))
for d in ("bullish", "bearish"):
    x = ev[d]
    if x.get("closed_at") == "stage0":
        print(d, "closed at Stage 0"); continue
    s1, s2 = x["stage1"], x["stage2"]
    print(d, "reference K=1", x["baseline"])
    for k, c in s1["cells"].items():
        print(f"   K={k}: {c['stats']}  lb={c['lower_bound']}  tier={c['tier']}")
    print("   plateau t1", s1["plateau_tier1"], "t2", s1["plateau_tier2"], "winner", s1["winner"], "tier", s1["winner_tier"])
    for f in s2["folds"]:
        print("   fold", f["test_year"], "K=", f["tol"], f["stats"])
    print("   stage2", s2["verdict"], "=> proceed", x["proceed_to_validation"], "K", x["validation_cell"], "tier", x["tier"])
EOF
```

`proceed_to_validation`, `validation_cell` and `tier` are the decision. **Never override them by hand.** A cell that looks close but did not clear is NO-LIFT.

- [ ] **Step 5: Write `docs/superpowers/results/<date>-v108-stage12.md`.** Load `pooled-numbers` first. Per direction:
  - **Reference K = 1:** N / WR / ExpR / scratch+timeout share. It is reported, never a candidate. Say whether K = 1 alone would have cleared Tier 1. If it would, and no K > 1 does, the verdict is NO-LIFT (honesty clause).
  - **K = 2 and K = 3:** N / WR / ExpR / scratch share / bootstrap lower bound / the Tier 1 and Tier 2 clauses / the tier. Also the **added-trade share** `1 − N_ref / N_cell`, so readers see how much volume re-arm actually added once `one_at_a_time` suppression applies.
  - Plateaus, the winner and its tier, or "no winner".
  - Stage 2: the fold table (test year, selected K, test N, test ExpR) and the verdict (qualifying, positive, unselected). Put v84's fold years next to it for context (2021 N=13, 2022 N=16, 2023 N=13), because the spec's diagnosis was starvation.
  - `## Verdict`: `PROCEED-VALIDATION at K=<k> (Tier <t>)`, or `NO-LIFT at Stage 1|2`.

- [ ] **Step 6: Commit** (`validation` refuses an uncommitted evaluate JSON)

```bash
git add docs/superpowers/results/<date>-v108-stage12.json docs/superpowers/results/<date>-v108-stage12.md
git commit -m "docs(v108): Stages 1-2 on TRAIN_EXT -- <bullish verdict>, <bearish verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/results/<date>-v108-stage12.json docs/superpowers/results/<date>-v108-stage12.md
```

If no direction proceeds, skip V108-7 and V108-8 and go to V108-9.

---

### Task V108-7: Stage 3 — VALIDATION (one shot per proceeding direction)

**Files:**
- Create: `docs/superpowers/results/<date>-v108-validation-<direction>.json` (one per shot), `docs/superpowers/results/<date>-v108-validation.md`

**Interfaces:**
- Consumes: the committed `<date>-v108-preregistration.md` and `<date>-v108-stage12.json`.
- Produces: per-shot JSON with `verdict.passes` and `verdict.tier` and `rows`. V108-8's `emit-registry` consumes it.

- [ ] **Step 1: Load `backtest-gate`, then check that no shot is spent**

Run: `git log --all --oneline -- "docs/superpowers/results/*-v108-validation-*.json"; ls docs/superpowers/results/ | grep -- "-v108-validation-"`
Expected: no output from either. Any existing `-v108-validation-<direction>.json`, of **any date and on any branch**, means that shot is spent. **Stop, and do not re-run it.** The script refuses only an existing file at the same path.

- [ ] **Step 2: Run each proceeding direction exactly once.** Dispatch each shot to `backtest-runner`; the two may run concurrently:

> Worktree root, no `cd`: `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache_ext python scripts/backtest/measure_fib_v103.py validation --mechanism E --direction <direction> --evaluate docs/superpowers/results/<date>-v108-stage12.json --preregistration docs/superpowers/results/<date>-v108-preregistration.md --out docs/superpowers/results/<date>-v108-validation-<direction>.json --tickers "AAPL,ABNB,ADBE,AMAT,AMD,AMZN,ARM,ASML,ASTS,AVGO,AXON,BA,BKNG,CEG,CRM,CRWD,CRWV,CVX,DDOG,DELL,DOCU,EBAY,FTNT,GC=F,GD,GEV,GLW,GM,GOOGL,GS,HD,HIMS,HOOD,HPQ,IBM,ILMN,INTC,INTU,IREN,ISRG,JNJ,JPM,META,MRNA,MRVL,MSFT,MSTR,MU,NBIS,NFLX,NKE,NOW,NVDA,ORCL,PANW,PEP,PFE,PLTR,PYPL,QBTS,QCOM,RKLB,SBUX,SHOP,SI=F,SNDK,SNOW,SNPS,SOFI,SPCX,STX,TSLA,UBER,UNH,V,WDC,WMT" > <scratchpad>/v108_val_<direction>.log 2>&1`. Return the final line and the JSON's `cell` and `verdict`, then delete the log. On a refusal (`SystemExit`), return the message verbatim and **do not retry with changed arguments**.

A refusal means a precondition failed: an uncommitted file, a direction that did not proceed, or a spent shot. Fix the precondition, usually by making a missing commit. Never work around it.

- [ ] **Step 3: Write `docs/superpowers/results/<date>-v108-validation.md`.** Load `pooled-numbers` first. For each shot, give:
  - the K and tier;
  - N / WR / ExpR / scratch share / lower bound;
  - each clause with its value;
  - `PASS` or `FAIL`;
  - one line comparing TRAIN_EXT and VALIDATION at the same K (N, WR, ExpR).

  **A FAIL is final:** no re-run, no other K, no other tier.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/results/<date>-v108-validation-*.json docs/superpowers/results/<date>-v108-validation.md
git commit -m "docs(v108): VALIDATION -- <bullish PASS/FAIL (Tier t, K=k)>, <bearish ...>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/superpowers/results/
```

---

# Phase C — Verdict, wiring and close-out

### Task V108-8: Wiring — ship each passing direction's K (PASS path only)

Skip this task entirely when no direction has `verdict.passes == true` in V108-7. Otherwise, do every step for the passing direction(s) only. A non-passing direction keeps K = 1.

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (`DEFAULT_PARAMS["EMA Crossover"]`)
- Modify: `swingbot/core/market/strategy_types.py:200-210` (the EMA Crossover sentence in the `STRATEGY_GATES` comment block)
- Modify: `swingbot/core/backtesting/validation_registry.json` (via the script only)
- Modify: `tests/market/test_ema_rearm.py` (update the inert pin)
- Create: `tests/scanning/test_strategy_pass_open_trade.py`
- Create: `docs/superpowers/results/<date>-v108-live-path.md`

**Interfaces:**
- Consumes: `<date>-v108-validation-<direction>.json` (`cell`, `verdict.tier`, `verdict.passes`, `rows`).
- Produces: shipped defaults `max_touches_<dir> = <K>`, an `EMA Crossover` registry row with `run_date = <date>`, and a live-path finding.

- [ ] **Step 1: Load the `edge-module` skill** (this task edits `strategy_types.py` and a strategy's shipped entry params).

- [ ] **Step 2: Live-path check first (spec § Live-path risk).** With K > 1 live, a second pullback in the same leg posts a second alert, and the partner places real resting orders off alerts. The live population must be suppressed the way `one_at_a_time` suppressed the measured one. Both live paths use one gate. Read it:
  - `swingbot/core/scanning/strategy_pass.py::run_strategy_pass`, around line 128. A signal only opens a trade and posts an alert when `trade_log.open_trade_for_ticker(ticker) is None`; otherwise it counts as `stored_only`. `already_emitted` also blocks the same bar twice.
  - `swingbot/core/scanning/scan_run.py`, around lines 614–672 (confluence path, which reads `signals.ema_cross_signal` → `entries_for("EMA Crossover")`). With an open trade on the ticker, an automatic scan `continue`s, and the `skipped_already_open` count rises.
  - `swingbot/core/tracking/performance.py::open_trade_for_ticker` checks the ticker only, across **any** strategy, horizon or direction, with `status == "open"`.

  `run_strategy_pass` has no test today, so write one. Create `tests/scanning/test_strategy_pass_open_trade.py`:

```python
"""v108 live-path check: a second EMA Crossover leg never alerts while the first is open.

The backtest measured K > 1 under one_at_a_time=True. Live, one open trade per
ticker (any strategy/horizon/direction) is the equivalent guard -- stricter,
never looser. These pin that the strategy pass honours it.
"""
from types import SimpleNamespace as NS

from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv


class _Store:
    def __init__(self):
        self.plans = []

    def all(self):
        return list(self.plans)

    def add(self, plan):
        self.plans.append(plan)


class _Log:
    def __init__(self, open_trade=None):
        self.open_trade, self.logged = open_trade, []

    def open_trade_for_ticker(self, ticker):
        return self.open_trade

    def log_trade(self, **kwargs):
        self.logged.append(kwargs)
        self.open_trade = kwargs


def _plan(frame):
    return NS(source="strategy", ticker="AAA", strategy="EMA Crossover", horizon_key="4w",
              created_at=frame.index[-1].date().isoformat(), direction="bullish",
              trigger_price=100.0, stop_loss=98.0, tp1=104.0, tp2=None, plan_id="p1", badge="WEAK",
              quality_score=None, cohort_label=None, cohort_stats=None, risk_features=None,
              ledger="weak", entry_context=None)


def _run(monkeypatch, frame, trade_log, store):
    monkeypatch.setattr(sp, "completed_frame", lambda df, now: df)
    monkeypatch.setattr(sp, "strategy_signals", lambda df, horizon, spy_df: [("EMA Crossover", "bullish")])
    monkeypatch.setattr(sp, "build_strategy_plan_at", lambda df, **kwargs: _plan(df))
    monkeypatch.setattr(sp, "build_strategy_alert_embed", lambda plan: "embed")
    return sp.run_strategy_pass(["AAA"], {"AAA": frame}, now=None, horizons=("4w",), spy_df=frame,
                                regimes=None, rs_combined_of=lambda ticker: None, mode="live",
                                live_allow=set(), trade_log=trade_log, plan_store=store)


def test_second_leg_is_stored_only_while_the_first_trade_is_open(monkeypatch):
    frame = make_ohlcv([100.0] * 30)
    trade_log = _Log(open_trade={"ticker": "AAA", "strategy": "EMA Crossover", "status": "open"})
    result = _run(monkeypatch, frame, trade_log, _Store())
    assert (result.opened, result.stored_only, result.alerts, trade_log.logged) == (0, 1, [], [])


def test_first_leg_opens_and_blocks_the_next_bars_leg(monkeypatch):
    frame, trade_log, store = make_ohlcv([100.0] * 30), _Log(), _Store()
    first = _run(monkeypatch, frame.iloc[:-1], trade_log, store)
    second = _run(monkeypatch, frame, trade_log, store)
    assert (first.opened, len(first.alerts)) == (1, 1)
    assert (second.opened, second.stored_only, second.alerts) == (0, 1, [])


def test_a_closed_first_leg_frees_the_ticker_for_the_second(monkeypatch):
    frame, trade_log = make_ohlcv([100.0] * 30), _Log()
    result = _run(monkeypatch, frame, trade_log, _Store())
    assert (result.opened, len(result.alerts)) == (1, 1)
```

Run: `python scripts/dev/testrun.py file tests/scanning/test_strategy_pass_open_trade.py`
Expected: PASS. It pins behaviour that already exists, so a FAIL is a real live-path gap. **Stop and report it to the controller before shipping any K.** The measured population would then differ from the live one.

Write `docs/superpowers/results/<date>-v108-live-path.md`: three short paragraphs, one per path above (file:line, what suppresses a second same-leg alert), then the residual difference. Live is **stricter** than the backtest. `one_at_a_time` was per (ticker, strategy, horizon), while live blocks on any open trade on the ticker. So the live EMA Crossover population is a subset of the measured one, never a superset.

- [ ] **Step 3: Set the shipped K.** In `DEFAULT_PARAMS["EMA Crossover"]` (`entry_filters.py`), set each passing direction's key to its `cell` from the validation JSON, and leave the other at `1`. Under the v108 comment added in V108-1, add one line per shipped direction:

```python
    # v108 (<date>): <direction> ships K=<K> -- TRAIN_EXT 2010-2023 N=<n> WR=<wr>% ExpR=<e>;
    # VALIDATION 2024-25 N=<n> WR=<wr>% ExpR=<e> (Tier <t>) -- results/<date>-v108-validation.md.
```

- [ ] **Step 4: Update the inert pin.** In `tests/market/test_ema_rearm.py`, rename `test_defaults_ship_inert` to `test_defaults_ship_the_v108_verdict` and assert the shipped tuple:

```python
def test_defaults_ship_the_v108_verdict():
    params = DEFAULT_PARAMS["EMA Crossover"]
    assert (params["max_touches_bull"], params["max_touches_bear"]) == (<bull K or 1>, <bear K or 1>)
    assert (params["entry_mode"], params["pullback_max_bars"]) == ("pullback", 15)
```

The parity tests stay as they are, because they pass `max_touches_*=1` through the monkeypatched legacy helper and through the `_pullback_touches(..., 1)` call. Change `test_default_entries_are_bit_for_bit_the_legacy_entries` to pass explicit `params={"max_touches_bull": 1, "max_touches_bear": 1}` to both `ema_cross_entries` calls. The default is no longer K = 1 for a shipped direction, and the test pins K = 1 parity, not the default.

- [ ] **Step 5: Comment block.** In `swingbot/core/market/strategy_types.py`, after the sentence ending `(results/2026-09-10-v84-ema-crossover-preregistration.md).` (~line 208), insert:

```python
# v108 (<date>) re-armed it: DEFAULT_PARAMS max_touches_<dir>=<K> (first K
# pullback touch events per held cross; the other direction stays 1).
# TRAIN_EXT 2010-2023 N=<n> WR=<wr>% ExpR=<e>; VALIDATION 2024-25 N=<n>
# WR=<wr>% ExpR=<e> (Tier <t>) -> badge <VALIDATED|WEAK>
# (results/<date>-v108-validation.md). Still ungated.
```

- [ ] **Step 6: Registry row, through the script only** (the pre-registration's registry-row rule):

```bash
python scripts/backtest/measure_fib_v103.py emit-registry --validation-json <every passing docs/superpowers/results/<date>-v108-validation-<direction>.json> --registry swingbot/core/backtesting/validation_registry.json --run-date <date>
python -c "import json; print([r for r in json.load(open('swingbot/core/backtesting/validation_registry.json')) if r['strategy']=='EMA Crossover'])"
```

Expected: exactly one `EMA Crossover` row, `window` `2024-01-01..2025-12-31`, `run_date` `<date>`, and `status` as `registry_status` decided. Never edit the row by hand.

- [ ] **Step 7: Narrow runs, then `fast` once**

Run: `python scripts/dev/testrun.py file tests/market/test_ema_rearm.py`, `python scripts/dev/testrun.py file tests/market/test_rescue_ema.py`, `python scripts/dev/testrun.py file tests/backtesting/test_registry.py`
Expected: PASS each.
Run: `python scripts/dev/testrun.py fast`
Expected: `0 failed`. Treat any failure that names EMA Crossover entries, counts or the registry like this:
  - If the test is a frozen no-behaviour-change witness (its docstring says it pins a pre-change result), pin `max_touches_*` to `1` via `monkeypatch.setitem(DEFAULT_PARAMS["EMA Crossover"], ...)` and add a one-line reason.
  - Otherwise it asserts production behaviour. Update the expectation to what the shipped K produces.
  - Never loosen an assertion or add an `xfail`. If the category is unclear, stop and ask.

- [ ] **Step 8: Complexity check**

Run: `python -m radon cc -s -n C swingbot/core/market/entry_filters.py tests/scanning/test_strategy_pass_open_trade.py`
Expected: nothing new, compared with V108-1's check.

- [ ] **Step 9: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py swingbot/core/backtesting/validation_registry.json tests/market/test_ema_rearm.py tests/scanning/test_strategy_pass_open_trade.py docs/superpowers/results/<date>-v108-live-path.md
git commit -m "feat(v108): ship EMA Crossover re-arm -- <direction(s)> K=<K> (Tier <t>), registry row <status>, live one-trade-per-ticker suppression pinned

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py swingbot/core/backtesting/validation_registry.json tests/market/test_ema_rearm.py tests/scanning/test_strategy_pass_open_trade.py docs/superpowers/results/<date>-v108-live-path.md
```

---

### Task V108-9: Methodology row (every outcome)

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (the `### Closed pre-registrations — do not re-run these` table, appended after the v103 C row)

**Interfaces:**
- Consumes: the committed stage0, stage12 and validation results from V108-5..7.
- Produces: the closed row, which V108-10's close-out links.

The spec asks for this row on every non-PASS outcome. It is also written on a PASS: a spent VALIDATION shot has to be recorded, or a later session could run it again.

- [ ] **Step 1: Load `pooled-numbers`**, then append one row, matching the v103 rows' style:

```markdown
| EMA Crossover re-arm, first K pullback touch events per held cross, `K ∈ {2, 3}` per direction (v108) | **<SHIPPED <dir> K=<k> (Tier <t>, badge <status>) | NO-LIFT> — bullish <ended at Stage 0 (floor|inert, K3/K1=<r>) | Stage 1 | Stage 2 | VALIDATION PASS/FAIL>; bearish <same>. VALIDATION spent: <directions or none>.** Extended-cache TRAIN_EXT 2010-2023, universe 73, reference `K=1` (the v84 mechanism): bullish N=<n> WR <wr>% ExpR <e>, bearish N=<n> WR <wr>% ExpR <e>. <Per direction: K=2/K=3 N, WR, ExpR, lower bound, tier, added-trade share; Stage 2 qualifying/positive/unselected folds.> <VALIDATION line per shot, with the TRAIN_EXT→VALIDATION comparison.> Horizon concentration: <none | top-2 share X%>. <Params: `max_touches_bull=<k|1>`, `max_touches_bear=<k|1>`.> Reopening needs a mechanism other than "first K touch events per held cross for K ∈ {2, 3}" | `results/<date>-v108-preregistration.md`, `results/<date>-v108-stage0.md`, `results/<date>-v108-stage12.md`<, `results/<date>-v108-validation.md`, `results/<date>-v108-live-path.md`> |
```

Every bracket is filled from the committed result files; a direction that closed earlier has no later-stage figures, so write only the stage it reached. Leave the v84 EMA Crossover row untouched: it stays closed as written.

- [ ] **Step 2: Commit**

```bash
git add docs/claude/backtest-methodology.md
git commit -m "docs(v108): methodology row -- EMA Crossover re-arm <shipped <dir> K=<k> | no-lift at Stage <n>>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/claude/backtest-methodology.md
```

---

### Task V108-10: Full-suite verification, release, merge and close-out

**Files:**
- Modify (PASS path only): `VERSION.json`, `swingbot/admin/version_history.json`
- Move (on `main`, after merge): `docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md` → `docs/superpowers/specs/implemented/`, `docs/superpowers/plans/2026-09-27-v108-ema-crossover-rearm-rescue.md` → `docs/superpowers/plans/implemented/`

**Interfaces:**
- Consumes: everything above.
- Produces: the merged branch, the release (PASS only) and the closed documents.

- [ ] **Step 1: Full suite, once.** Dispatch `test-runner` for `python scripts/dev/testrun.py full` in the worktree. Require `0 failed` and `0 xfailed`. **If it is not green, fix forward from the failures it names**: they are this plan's regressions. If a failure passes in isolation and sits in code v108 never touched, report it with both outputs and don't call the suite green.

- [ ] **Step 2 (PASS path only): Release, bump `bot` minor.** The bump goes after green:
  1. Read `VERSION.json` as it is now, not a number from this plan or memory. Increment `bot`'s minor, reset patch to 0, leave `ui` untouched, and set `bot_updated` to now (UTC, `YYYY-MM-DD HH-MM-SS`).
  2. Commit: `git commit -m "release(bot): <X.Y.0> -- EMA Crossover re-arm (<dir> K=<k>)" -- VERSION.json`, with the trailer.
  3. Run: `python scripts/dev/build_version_matrix.py`. Then commit `swingbot/admin/version_history.json` with message `chore(bot): <X.Y.0> -- EMA Crossover re-arm (<dir> K=<k>)` and the trailer.
  4. Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
     Expected: PASS.

  If nothing passed, skip this step. The spec's `Bump:` then resolves to **none**: inert code bumps nothing.

- [ ] **Step 3: Merge to `main`** per the `worktree-lifecycle` skill. First `git fetch` and check `git log main` for other sessions' commits (memory: concurrent session commits). Do not re-run the suite after a conflict-free merge. A merge that resolved conflicts gets one `full` run.

- [ ] **Step 4: Close the documents on `main`.** The spec says the outcome is `implemented/` either way, since the inert code lands.

```bash
git mv docs/superpowers/specs/2026-09-27-v108-ema-crossover-rearm-rescue-design.md docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-09-27-v108-ema-crossover-rearm-rescue.md docs/superpowers/plans/implemented/
```

In the moved spec, replace the `**Status:**` line with `**Status:** <Shipped <dir> K=<k> (Tier <t>, badge <status>) | Closed no-lift at Stage <n>, params stay 1> <date>; VALIDATION spent: <directions or none>.`. On NO-LIFT, also amend `**Bump:**` to `none (no K shipped)`. If Stage 1 showed re-arm added little volume, amend `**Edge:**` with one clause saying why, per `document-conventions.md`. Fix the moved plan's `**Spec:**` link to `docs/superpowers/specs/implemented/2026-09-27-v108-ema-crossover-rearm-rescue-design.md`.

```bash
git commit -m "docs(v108): close out -- <shipped <dir> K=<k> | no-lift, inert>; move spec and plan to implemented/

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 5: Remove the worktree and its merged branch** per `docs/claude/git-safety.md`. First, `git rev-list --count main..2026-09-27-v108-ema-crossover-rearm-rescue` must print `0`. Never touch a `backup`/`stable-*` branch. The local `data/v108_collect_E.json` goes with the worktree.

- [ ] **Step 6: Report.** Give the controller the verdict per direction, the shipped params, the registry row (if any) and the release version (if any). Say that deploying to the Hetzner VM is a separate release step: this plan changes no production `.env`.
