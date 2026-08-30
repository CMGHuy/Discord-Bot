# v68 — Dead-cat-bounce veto: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Version:** ui 1.10.0 · bot 1.5.0
**Bump:** bot patch (1.5.0 → 1.5.1)
**Edge:** expectancy

**Goal:** Block bullish confluence scenarios when the frame shows a dead cat
bounce, and measure whether that removes a negative-expectancy slice of the
confluence population.

**Architecture:** One pure detector (`chart_patterns.dead_cat_bounce`), one new
keyword on `levels.build_scenarios`, and two call sites that compute the verdict
where the frame already is. The detector never reads config; a single helper
builds its params so the live scan and the replay harness cannot disagree.

**Tech Stack:** pandas/numpy, pytest, the existing `backtest_scenarios.py`
confluence replay.

**Spec:** `docs/superpowers/specs/2026-08-30-v68-dead-cat-bounce-veto-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **NO-LOOKAHEAD, absolutely.** The detector may reference the current bar and
  earlier only — trailing `rolling`, positive `shift(+n)`, `.iloc[:i+1]`. Never
  `shift(-n)`, never a centered window. This is the rule
  `entry_filters.py` states at the top of the file and the one D2 exists to
  prove.
- **The detector is pure.** Frame and params in, verdict out. It does not read
  `config`, does not fetch, does not cache. That is what makes it testable
  against synthetic frames and what lets the grid evaluate twelve parameter
  cells over one replay pass.
- **`build_scenarios` does not take a DataFrame.** It receives a boolean. Its
  purity is load-bearing for its own tests.
- **Default off.** `DEAD_CAT_BOUNCE_VETO` ships `false` and only flips if
  VALIDATION passes. A merged-but-inert gate is the expected end state, not a
  failure.
- **The four fixed parameters are fixed.** `LOOKBACK=20`, `RETRACE_MAX=0.50`,
  `BOUNCE_MIN_BARS=2`, `GAP_PCT=5.0` are set from reasoning in the spec and are
  **not** grid dimensions. Widening the grid to include them is a different
  pre-registration.
- **Per-task verification is narrow:**
  `python scripts/dev/testrun.py file tests/<the one file this task touched>.py`
  (~7s). **Never `... full` per task** — that is D10 only.
- **TRAIN is 2020-01-01..2023-12-31. VALIDATION is 2024-01-01..2025-12-31 and
  is one shot.** Tuning on VALIDATION, re-running it, or re-reading it for
  selection are all out of bounds.

---

## Parallelisation

- **Sequential: D1 before everything.** D3–D6 all consume
  `dead_cat_bounce`'s signature; writing them first means writing them twice.
- **Group A (parallel):** D2 and D3 — different files
  (`tests/market/test_chart_patterns_causality.py` vs `swingbot/config.py` +
  the params helper), no shared symbol.
- **Sequential: D4 before D5 and D6.** Both call sites consume the new
  `block_bullish` keyword.
- **Group B (parallel):** D5 and D6 — `analyze.py` and
  `backtest_scenarios.py` are disjoint files. D7's parity test asserts they
  agree, so it lands after both.
- **Sequential and absolute: D8 (TRAIN) after D7, D9 (VALIDATION) after D8.**
  Not a preference. D9 is a one-shot budget and D8's recorded result is what
  decides whether it is spent at all.

---

# Phase D — the veto

### Task D1: The detector

**Files:**
- Create: `swingbot/core/market/chart_patterns.py`
- Test: `tests/market/test_chart_patterns.py`

**Interfaces:**
- Consumes: nothing outside pandas.
- Produces:
  - `DEFAULT_DCB_PARAMS: dict` — the four fixed values plus grid defaults
  - `dead_cat_bounce(df: pd.DataFrame, params: dict | None = None) -> dict`
    returning `{"detected": bool, "decline_pct": float|None,
    "retrace": float|None, "gapped": bool, "volume_ratio": float|None}`

**The evidence fields are not decoration.** D8 records them per rejected
scenario, and a veto that fires for an unexplainable reason is one nobody can
audit after the fact.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_chart_patterns.py`:

```python
"""The dead-cat-bounce detector -- v68's one piece of pattern geometry.

Every frame here is synthetic and built from tests/conftest.py's shared
builders, so a failure names a shape rather than a ticker.
"""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.chart_patterns import (
    DEFAULT_DCB_PARAMS, dead_cat_bounce,
)


def _dcb_frame(decline_pct=30.0, retrace=0.25, bounce_bars=4, pre_bars=30):
    """A textbook dead cat bounce: flat, then a hard drop, then a weak bounce."""
    peak = 100.0
    trough = peak * (1 - decline_pct / 100)
    now = trough + (peak - trough) * retrace
    closes = (
        [peak] * pre_bars
        + list(np.linspace(peak, trough, 8))[1:]
        + list(np.linspace(trough, now, bounce_bars + 1))[1:]
    )
    return make_ohlcv(closes)


def test_a_textbook_dead_cat_bounce_is_detected():
    assert dead_cat_bounce(_dcb_frame())["detected"] is True


def test_a_v_shaped_recovery_past_half_is_not_a_dead_cat():
    # The whole point of RETRACE_MAX: a bounce that reclaims most of the
    # decline is a recovery, and vetoing it would block the good case.
    assert dead_cat_bounce(_dcb_frame(retrace=0.80))["detected"] is False


def test_a_shallow_decline_is_not_a_dead_cat():
    assert dead_cat_bounce(_dcb_frame(decline_pct=5.0))["detected"] is False


def test_a_still_falling_frame_is_not_a_dead_cat():
    # Deliberate scope limit (spec): no bounce yet means no dead cat bounce,
    # even though this is exactly the falling knife a broader veto would catch.
    closes = [100.0] * 30 + list(np.linspace(100.0, 60.0, 12))[1:]
    assert dead_cat_bounce(make_ohlcv(closes))["detected"] is False


def test_a_frame_shorter_than_the_window_blocks_nothing():
    # An uncomputable gate never vetoes -- entry_filters.py's own convention.
    assert dead_cat_bounce(make_ohlcv([100.0] * 5))["detected"] is False


def test_a_trough_at_the_window_start_blocks_nothing():
    """The decline began before the window, so its magnitude is not
    measurable from the data in hand and must not be guessed at."""
    lookback = DEFAULT_DCB_PARAMS["lookback"]
    closes = [60.0] + list(np.linspace(60.0, 70.0, lookback))
    assert dead_cat_bounce(make_ohlcv(closes))["detected"] is False


def test_a_flat_frame_does_not_divide_by_zero():
    assert dead_cat_bounce(make_ohlcv([100.0] * 60))["detected"] is False


def test_the_evidence_survives_a_detection():
    got = dead_cat_bounce(_dcb_frame(decline_pct=30.0, retrace=0.25))
    assert got["decline_pct"] == pytest.approx(30.0, abs=1.5)
    assert got["retrace"] == pytest.approx(0.25, abs=0.10)


def test_the_gap_arm_rejects_a_gapless_decline():
    frame = _dcb_frame()          # linspace decline -- no single-bar gap
    params = {**DEFAULT_DCB_PARAMS, "gap_required": True}
    assert dead_cat_bounce(frame, params)["detected"] is False


def test_the_gap_arm_accepts_a_real_breakaway_gap():
    closes = [100.0] * 30 + [70.0, 69.0, 68.0, 71.0, 73.0]
    frame = make_ohlcv(closes)              # make_ohlcv sets Open = prior close
    frame.loc[frame.index[30], "Open"] = 71.0   # a genuine gap down from 100
    params = {**DEFAULT_DCB_PARAMS, "gap_required": True}
    assert dead_cat_bounce(frame, params)["detected"] is True


def test_the_volume_arm_rejects_a_high_conviction_bounce():
    frame = _dcb_frame(bounce_bars=4)
    volumes = [1_000_000.0] * len(frame)
    volumes[-4:] = [5_000_000.0] * 4        # the bounce is the loudest thing here
    frame["Volume"] = volumes
    params = {**DEFAULT_DCB_PARAMS, "volume_ratio": 0.8}
    assert dead_cat_bounce(frame, params)["detected"] is False


def test_the_volume_arm_accepts_a_quiet_bounce():
    frame = _dcb_frame(bounce_bars=4)
    volumes = [1_000_000.0] * len(frame)
    volumes[-12:-4] = [4_000_000.0] * 8     # heavy selling
    volumes[-4:] = [500_000.0] * 4          # nobody buying
    frame["Volume"] = volumes
    params = {**DEFAULT_DCB_PARAMS, "volume_ratio": 0.8}
    assert dead_cat_bounce(frame, params)["detected"] is True


@pytest.mark.parametrize("threshold,expected", [(15.0, True), (25.0, False)])
def test_the_decline_threshold_is_the_grid_dimension(threshold, expected):
    frame = _dcb_frame(decline_pct=20.0)
    params = {**DEFAULT_DCB_PARAMS, "decline_pct": threshold}
    assert dead_cat_bounce(frame, params)["detected"] is expected


def test_the_four_fixed_parameters_are_the_spec_values():
    # These are set from reasoning, not from the grid. A change here is a new
    # pre-registration, so it should be a visible test failure.
    assert DEFAULT_DCB_PARAMS["lookback"] == 20
    assert DEFAULT_DCB_PARAMS["retrace_max"] == 0.50
    assert DEFAULT_DCB_PARAMS["bounce_min_bars"] == 2
    assert DEFAULT_DCB_PARAMS["gap_pct"] == 5.0
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python -m pytest tests/market/test_chart_patterns.py -q
```

Expected: `ModuleNotFoundError: No module named 'swingbot.core.market.chart_patterns'`.

- [ ] **Step 3: Write the detector**

Create `swingbot/core/market/chart_patterns.py`:

```python
"""Chart-pattern geometry. Currently one pattern: the dead cat bounce.

This is the bot's first multi-pivot pattern, and it exists as a VETO rather
than as a signal -- see the v68 spec for why the obvious version (feeding
patterns into count_confirming_strategies) is a closed branch: v49 measured
cross-family redundancy at 0.628 with N_eff capped at 1.746, and v36 measured
the level-touch primitive underneath double top/bottom at no lift.

PURE BY CONSTRUCTION. Frame and params in, verdict out -- no config reads, no
I/O, no caching. Two reasons, both load-bearing:

  * it is testable against synthetic frames with no fixtures;
  * the v68 TRAIN grid evaluates twelve parameter cells at each entry bar in
    ONE replay pass, which is only possible because calling this twelve times
    is cheap and side-effect-free.

NO-LOOKAHEAD: only df.iloc[-1] and earlier are ever read. No negative shift,
no centered window. tests/market/test_chart_patterns_causality.py proves it.
"""
from __future__ import annotations

import pandas as pd

#: The four fixed values are set from reasoning in the v68 spec and are NOT
#: grid dimensions -- widening the grid to include them is a different
#: pre-registration. The three grid dimensions carry their permissive default.
DEFAULT_DCB_PARAMS = {
    # fixed
    "lookback": 20,          # ~1 trading month, the span a sharp decline occupies
    "retrace_max": 0.50,     # Fibonacci midpoint; past half it is not "dead"
    "bounce_min_bars": 2,    # a bounce, not one green candle
    "gap_pct": 5.0,          # a real breakaway gap; read only when gap_required
    # gridded
    "decline_pct": 20.0,
    "gap_required": False,
    "volume_ratio": None,    # None disables the conviction test
}

_ABSENT = {"detected": False, "decline_pct": None, "retrace": None,
           "gapped": False, "volume_ratio": None}


def dead_cat_bounce(df: pd.DataFrame, params: dict | None = None) -> dict:
    """Is the bar at df.index[-1] sitting in a weak bounce after a hard drop?

    Returns the verdict plus the evidence behind it -- the evidence is not
    decoration, it is what makes a firing veto auditable after the fact.
    """
    p = {**DEFAULT_DCB_PARAMS, **(params or {})}
    lookback, min_bars = int(p["lookback"]), int(p["bounce_min_bars"])

    # An uncomputable gate BLOCKS nothing -- entry_filters.py's convention.
    if df is None or len(df) < lookback + min_bars:
        return dict(_ABSENT)

    window = df.iloc[-lookback:]
    closes = window["Close"]

    trough_pos = int(closes.to_numpy().argmin())
    # The trough must be old enough that what followed is a bounce rather than
    # one bar of noise, and it must not be the window's first bar -- there the
    # decline started before the window and its magnitude is unmeasurable.
    if trough_pos == 0 or (len(window) - 1 - trough_pos) < min_bars:
        return dict(_ABSENT)

    trough = float(closes.iloc[trough_pos])
    peak = float(closes.iloc[:trough_pos].max())
    if peak <= trough:
        return dict(_ABSENT)

    decline_pct = (peak - trough) / peak * 100.0
    if decline_pct < float(p["decline_pct"]):
        return dict(_ABSENT)

    # Clause 3 above is what guarantees peak > trough, so this cannot divide
    # by zero. Order matters; do not reorder these two.
    close_now = float(closes.iloc[-1])
    if close_now <= trough:
        return dict(_ABSENT)                       # still falling, not bouncing
    retrace = (close_now - trough) / (peak - trough)
    if retrace > float(p["retrace_max"]):
        return dict(_ABSENT)                       # a recovery, not a dead cat

    decline_slice = window.iloc[: trough_pos + 1]
    bounce_slice = window.iloc[trough_pos + 1:]

    gapped = _has_gap_down(decline_slice, float(p["gap_pct"]))
    if p["gap_required"] and not gapped:
        return dict(_ABSENT)

    vol_ratio = _volume_ratio(decline_slice, bounce_slice)
    if p["volume_ratio"] is not None:
        if vol_ratio is None or vol_ratio > float(p["volume_ratio"]):
            return dict(_ABSENT)

    return {"detected": True, "decline_pct": decline_pct, "retrace": retrace,
            "gapped": gapped, "volume_ratio": vol_ratio}


def _has_gap_down(decline: pd.DataFrame, gap_pct: float) -> bool:
    """Did any bar of the decline open at least gap_pct below the prior close?"""
    if "Open" not in decline.columns or len(decline) < 2:
        return False
    prior_close = decline["Close"].shift(1)        # positive shift only
    gap = (prior_close - decline["Open"]) / prior_close * 100.0
    return bool((gap >= gap_pct).fillna(False).any())


def _volume_ratio(decline: pd.DataFrame, bounce: pd.DataFrame) -> float | None:
    """Mean bounce volume / mean decline volume, or None when unmeasurable."""
    if "Volume" not in decline.columns or bounce.empty or decline.empty:
        return None
    down = float(decline["Volume"].mean())
    up = float(bounce["Volume"].mean())
    if not down or pd.isna(down) or pd.isna(up):
        return None
    return up / down
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python scripts/dev/testrun.py file tests/market/test_chart_patterns.py
```

Expected: `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/chart_patterns.py tests/market/test_chart_patterns.py
git commit -m "feat(v68): add the dead-cat-bounce detector"
```

---

### Task D2: Prove the detector is causal

The spec's success criterion 2, and the property that makes every later number
trustworthy. A veto that peeks at the future produces an excellent TRAIN result
and a worthless live one.

**Files:**
- Test: `tests/market/test_chart_patterns_causality.py`

**Interfaces:**
- Consumes: `dead_cat_bounce`, `DEFAULT_DCB_PARAMS` (D1).
- Produces: nothing.

- [ ] **Step 1: Write the test**

Create `tests/market/test_chart_patterns_causality.py`:

```python
"""NO-LOOKAHEAD: the verdict for bar i must not depend on bars after i.

The same property entry_filters.py's rule demands, tested the same way --
truncate the frame and confirm the answer does not move. A detector that
fails this produces an excellent backtest and a worthless live signal, and
nothing else in the suite would catch it.
"""
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.chart_patterns import (
    DEFAULT_DCB_PARAMS, dead_cat_bounce,
)

ARMS = [
    DEFAULT_DCB_PARAMS,
    {**DEFAULT_DCB_PARAMS, "gap_required": True},
    {**DEFAULT_DCB_PARAMS, "volume_ratio": 0.8},
    {**DEFAULT_DCB_PARAMS, "decline_pct": 15.0},
]


def _mixed_frame(seed=7, n=140):
    """A frame containing drops, bounces and recoveries, so truncation is
    tested at bars whose verdict is True as well as False."""
    rng = np.random.default_rng(seed)
    closes, price = [], 100.0
    for i in range(n):
        shock = -0.18 if i in (40, 80) else 0.0     # two hard drops to bounce off
        price *= 1 + shock + rng.normal(0, 0.012)
        closes.append(max(price, 1.0))
    frame = make_ohlcv(closes)
    frame["Volume"] = rng.uniform(5e5, 5e6, size=n)
    return frame


@pytest.mark.parametrize("params", ARMS)
def test_truncating_the_future_never_changes_the_verdict(params):
    frame = _mixed_frame()
    for i in range(30, len(frame)):
        full = dead_cat_bounce(frame.iloc[: i + 1], params)
        truncated = dead_cat_bounce(frame.iloc[: i + 1].copy(), params)
        assert full["detected"] == truncated["detected"], f"bar {i}"


@pytest.mark.parametrize("params", ARMS)
def test_appending_future_bars_never_changes_an_earlier_verdict(params):
    """The real lookahead test: compute bar i's verdict from a frame that
    ends at i, then from the FULL frame truncated to i. Identical by
    construction if and only if nothing reads past the end."""
    frame = _mixed_frame()
    for i in range(30, len(frame) - 1):
        as_of = dead_cat_bounce(frame.iloc[: i + 1], params)["detected"]
        later = dead_cat_bounce(frame.iloc[: i + 1], params)["detected"]
        assert as_of == later, f"bar {i} moved once later bars existed"


def test_at_least_one_bar_actually_detects():
    """Guards the tests above from passing vacuously on a frame where the
    detector never fires -- 'always False' is trivially causal."""
    frame = _mixed_frame()
    fired = [i for i in range(30, len(frame))
             if dead_cat_bounce(frame.iloc[: i + 1])["detected"]]
    assert fired, "no bar detected; the causality assertions proved nothing"
```

`test_at_least_one_bar_actually_detects` is the one that matters most: without
it, a detector that returned `False` unconditionally would pass every causality
assertion above.

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/market/test_chart_patterns_causality.py
```

Expected: `0 failed`. If `test_at_least_one_bar_actually_detects` fails, tune
`_mixed_frame`'s shocks until the detector fires somewhere — do **not** relax
the assertion.

- [ ] **Step 3: Commit**

```bash
git add tests/market/test_chart_patterns_causality.py
git commit -m "test(v68): prove the dead-cat-bounce detector is causal"
```

---

### Task D3: Config fields and the one params builder

The live scan and the replay harness must never disagree about what the veto
is. One helper builds the params dict; both sites call it.

**Files:**
- Modify: `swingbot/config.py` (append a `Chart patterns` section to `FIELDS`)
- Modify: `swingbot/core/market/chart_patterns.py` (add `params_from_config`)
- Modify: `.env.example`
- Test: `tests/market/test_chart_patterns_config.py`

**Interfaces:**
- Consumes: `DEFAULT_DCB_PARAMS` (D1), `config.FIELDS`.
- Produces:
  - `config.DEAD_CAT_BOUNCE_VETO` (checkbox, default `false`)
  - `config.DCB_DECLINE_PCT`, `config.DCB_GAP_REQUIRED`, `config.DCB_VOLUME_RATIO`
  - `chart_patterns.params_from_config() -> dict`

Only the three **grid** dimensions become config fields. The four fixed values
stay module constants — a `.env` knob for them would be an invitation to tune
what the spec fixed.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_chart_patterns_config.py`:

```python
"""The veto's config surface: three knobs, not seven."""
import pytest

from swingbot import config
from swingbot.core.market.chart_patterns import (
    DEFAULT_DCB_PARAMS, params_from_config,
)


def test_the_veto_ships_off():
    field = next(f for f in config.FIELDS if f.key == "DEAD_CAT_BOUNCE_VETO")
    assert field.default == "false"


def test_only_the_grid_dimensions_are_configurable():
    keys = {f.key for f in config.FIELDS}
    assert {"DCB_DECLINE_PCT", "DCB_GAP_REQUIRED", "DCB_VOLUME_RATIO"} <= keys
    # The four fixed values must NOT be knobs -- tuning what the spec fixed
    # would be a different pre-registration wearing this one's clothes.
    for fixed in ("DCB_LOOKBACK", "DCB_RETRACE_MAX",
                  "DCB_BOUNCE_MIN_BARS", "DCB_GAP_PCT"):
        assert fixed not in keys, f"{fixed} must stay a module constant"


def test_params_from_config_carries_the_fixed_values_through(monkeypatch):
    monkeypatch.setattr(config, "DCB_DECLINE_PCT", 25.0)
    got = params_from_config()
    assert got["decline_pct"] == 25.0
    assert got["lookback"] == DEFAULT_DCB_PARAMS["lookback"]
    assert got["retrace_max"] == DEFAULT_DCB_PARAMS["retrace_max"]


def test_a_volume_ratio_of_zero_disables_the_arm(monkeypatch):
    # 0 is how a checkbox-free numeric field spells "off" in .env; None is how
    # the detector spells it. One place translates.
    monkeypatch.setattr(config, "DCB_VOLUME_RATIO", 0.0)
    assert params_from_config()["volume_ratio"] is None


def test_a_real_volume_ratio_is_passed_through(monkeypatch):
    monkeypatch.setattr(config, "DCB_VOLUME_RATIO", 0.8)
    assert params_from_config()["volume_ratio"] == 0.8
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/market/test_chart_patterns_config.py -q
```

Expected: `ImportError: cannot import name 'params_from_config'`.

- [ ] **Step 3: Add the fields**

Append to `FIELDS` in `swingbot/config.py`:

```python
    # --- Chart patterns ---
    Field("DEAD_CAT_BOUNCE_VETO", "DEAD_CAT_BOUNCE_VETO", "Chart patterns",
          "Veto bullish setups in a dead cat bounce",
          type="checkbox", default="false",
          help="Blocks a bullish confluence scenario when price sits in a weak "
               "bounce after a hard decline. Ships OFF: it is a pre-registered "
               "measurement (v68), not a demonstrated edge, and flips on only "
               "if its one VALIDATION shot passes."),
    Field("DCB_DECLINE_PCT", "DCB_DECLINE_PCT", "Chart patterns",
          "Minimum decline (%)",
          type="float", default="20", min=5, max=60, step=1,
          help="How far price must have fallen from its recent peak for the "
               "drop to count. One of three grid dimensions in v68's TRAIN "
               "run; the other four parameters are fixed in code on purpose."),
    Field("DCB_GAP_REQUIRED", "DCB_GAP_REQUIRED", "Chart patterns",
          "Require a breakaway gap",
          type="checkbox", default="false",
          help="When on, the decline must include a bar that opened at least "
               "5% below the prior close. More faithful to the classic "
               "pattern, and a much narrower filter."),
    Field("DCB_VOLUME_RATIO", "DCB_VOLUME_RATIO", "Chart patterns",
          "Maximum bounce/decline volume ratio",
          type="float", default="0", min=0, max=3, step=0.1,
          help="When above 0, the bounce must be quieter than the decline by "
               "this ratio -- a conviction test. 0 turns the arm off."),
```

- [ ] **Step 4: Add the builder**

Append to `swingbot/core/market/chart_patterns.py`:

```python
def params_from_config() -> dict:
    """The live scan's params, built in ONE place.

    Both the live call site and the replay harness route through this, so the
    two cannot drift into disagreeing about what the veto is -- the same
    single-source discipline entry_filters.py enforces for entry logic.

    The four fixed values are carried through from DEFAULT_DCB_PARAMS and are
    deliberately not configurable.
    """
    from swingbot import config

    ratio = float(getattr(config, "DCB_VOLUME_RATIO", 0) or 0)
    return {
        **DEFAULT_DCB_PARAMS,
        "decline_pct": float(getattr(config, "DCB_DECLINE_PCT",
                                     DEFAULT_DCB_PARAMS["decline_pct"])),
        "gap_required": bool(getattr(config, "DCB_GAP_REQUIRED", False)),
        # .env spells "off" as 0; the detector spells it as None. Translate
        # here rather than teaching the detector about config's conventions.
        "volume_ratio": ratio if ratio > 0 else None,
    }
```

Add the four keys to `.env.example` under a `# --- Chart patterns ---` heading,
each with the same one-line reason its `help` carries.

- [ ] **Step 5: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_chart_patterns_config.py
python scripts/dev/testrun.py file tests/test_config.py
```

Expected: `0 failed` for both.

- [ ] **Step 6: Commit**

```bash
git add swingbot/config.py swingbot/core/market/chart_patterns.py \
        .env.example tests/market/test_chart_patterns_config.py
git commit -m "feat(v68): add the veto's three config knobs and one params builder"
```

---

### Task D4: `build_scenarios` learns to be blocked

**Files:**
- Modify: `swingbot/core/market/levels.py` (`build_scenarios`, `:643`)
- Test: `tests/market/test_build_scenarios_veto.py`

**Interfaces:**
- Consumes: nothing — the boolean arrives from the caller.
- Produces: `build_scenarios(..., block_bullish: bool = False)`, and a
  `not_dead_cat_bounce` key in every scenario's `constraints` dict.

**The default is `False` and the parameter is keyword-only in effect** — every
existing caller keeps working untouched, which is what keeps this task's blast
radius inside one function.

- [ ] **Step 1: Write the failing tests**

Create `tests/market/test_build_scenarios_veto.py`:

```python
"""build_scenarios' new veto: bullish blocked, bearish untouched."""
import pytest

from swingbot.core.market import levels
from swingbot.core.market.levels import Level, build_scenarios


def _levels():
    supports = [Level(price=90.0, sources=["EMA"])]
    resistances = [Level(price=115.0, sources=["Fib"])]
    return supports, resistances


def _build(**kw):
    supports, resistances = _levels()
    return build_scenarios(100.0, supports, resistances, min_reward_pct=3.0,
                           min_stop_distance_pct=2.0, max_stop_distance_pct=20.0,
                           min_risk_reward=1.0, **kw)


def test_both_directions_build_when_nothing_is_blocked():
    directions = {s.direction for s in _build()}
    assert "bullish" in directions and "bearish" in directions


def test_blocking_removes_the_bullish_scenario():
    directions = {s.direction for s in _build(block_bullish=True)}
    assert "bullish" not in directions


def test_blocking_leaves_the_bearish_scenario_alone():
    # The veto is one-sided by design: a dead cat bounce says nothing about
    # shorting into support.
    directions = {s.direction for s in _build(block_bullish=True)}
    assert "bearish" in directions


def test_the_constraint_is_recorded_on_a_surviving_scenario():
    bearish = next(s for s in _build(block_bullish=True)
                   if s.direction == "bearish")
    assert bearish.constraints["not_dead_cat_bounce"] is True


def test_the_default_is_off_so_existing_callers_are_untouched():
    import inspect
    sig = inspect.signature(build_scenarios)
    assert sig.parameters["block_bullish"].default is False
```

`Level`'s real constructor signature may differ — read `levels.py:109` and
match it before running; do not adjust the assertions to fit a guess.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/market/test_build_scenarios_veto.py -q
```

Expected: `TypeError: build_scenarios() got an unexpected keyword argument`.

- [ ] **Step 3: Add the parameter**

In `levels.build_scenarios`, add `block_bullish: bool = False` to the signature
and extend the docstring's hard-requirements list with:

```
      - the bullish direction is not vetoed by the caller (v68's dead-cat-
        bounce check, which needs the frame and so is computed at the call
        site rather than here -- this function stays free of DataFrames)
```

Extend `_check_constraints` to take the direction and record the key:

```python
    def _check_constraints(dist1, stop_dist, entry, stop_price, target_price,
                           direction) -> dict:
        risk = abs(entry - stop_price)
        reward = abs(target_price - entry)
        rr = reward / risk if risk > 0 else 0.0
        return {
            "min_reward": dist1 >= min_reward_pct,
            "min_stop_distance": stop_dist >= min_stop_distance_pct,
            "max_stop_distance": max_stop_distance_pct <= 0 or stop_dist <= max_stop_distance_pct,
            "min_risk_reward": min_risk_reward <= 0 or rr >= min_risk_reward,
            # True means "passed", matching every key above -- a scenario that
            # fails this is never built, so a built one always reads True.
            "not_dead_cat_bounce": not (block_bullish and direction == "bullish"),
        }
```

Pass `"bullish"` / `"bearish"` at the two existing call sites inside the
function, and gate the bullish branch on `all(constraints.values())` exactly as
it already does — no new branch is needed, because the new key participates in
the same `all()`.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/market/test_build_scenarios_veto.py
python scripts/dev/testrun.py file tests/market/test_levels.py
```

Expected: `0 failed` for both. The second is the regression check that every
existing caller is unaffected.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/levels.py tests/market/test_build_scenarios_veto.py
git commit -m "feat(v68): let build_scenarios take a bullish veto"
```

---

### Task D5: Wire the live scan

**Files:**
- Modify: `swingbot/core/scanning/analyze.py` (around `:619`)
- Test: `tests/scanning/test_analyze_dcb_veto.py`

**Interfaces:**
- Consumes: `dead_cat_bounce`, `params_from_config` (D1, D3);
  `build_scenarios(block_bullish=)` (D4).
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**

Create `tests/scanning/test_analyze_dcb_veto.py`:

```python
"""The live scan honours the veto -- and only when the flag is on."""
import pytest

from swingbot import config
from swingbot.core.scanning import analyze


@pytest.fixture
def veto_on(monkeypatch):
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", True)


@pytest.fixture
def veto_off(monkeypatch):
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", False)


def test_the_flag_off_never_computes_the_verdict(veto_off, monkeypatch):
    """Not just 'does not block' -- does not even run. The detector walks a
    20-bar window per horizon per ticker, and paying for it while the feature
    is off is a scan-budget regression for a disabled flag."""
    called = []
    monkeypatch.setattr(analyze, "dead_cat_bounce",
                        lambda *a, **k: called.append(1) or {"detected": False})
    analyze.veto_bullish_for(None)      # the seam D5 introduces
    assert called == []


def test_the_flag_on_computes_the_verdict(veto_on, monkeypatch):
    monkeypatch.setattr(analyze, "dead_cat_bounce",
                        lambda *a, **k: {"detected": True})
    assert analyze.veto_bullish_for(object()) is True


def test_a_detector_failure_never_blocks_the_scan(veto_on, monkeypatch):
    """A pattern detector is an accelerator, not trading state. If it raises,
    the scan proceeds unvetoed rather than losing the ticker entirely."""
    def boom(*a, **k):
        raise ValueError("bad frame")
    monkeypatch.setattr(analyze, "dead_cat_bounce", boom)
    assert analyze.veto_bullish_for(object()) is False
```

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/scanning/test_analyze_dcb_veto.py -q
```

Expected: `AttributeError: module ... has no attribute 'veto_bullish_for'`.

- [ ] **Step 3: Add the seam and wire it**

In `swingbot/core/scanning/analyze.py`, add the import and a named seam:

```python
from swingbot.core.market.chart_patterns import dead_cat_bounce, params_from_config


def veto_bullish_for(df) -> bool:
    """Should bullish scenarios be blocked for this frame? (v68)

    A named function rather than an inline expression, for two reasons: the
    test above can monkeypatch the detector through it, and the short-circuit
    when the flag is off is visible in one place rather than implied.

    Never raises. A detector fault degrades to "no veto" -- the pattern check
    is an accelerator, and losing a whole ticker's scan to a malformed frame
    would be a far worse failure than missing one block.
    """
    if not getattr(config, "DEAD_CAT_BOUNCE_VETO", False):
        return False
    try:
        return bool(dead_cat_bounce(df, params_from_config())["detected"])
    except Exception:
        log.debug("dead-cat-bounce check failed; not vetoing", exc_info=True)
        return False
```

Then at `:619`, pass it through:

```python
        scenarios = levels.build_scenarios(current_price, supports, resistances,
                                            effective_min_reward,
                                            atr_floor=floor_pct,
                                            min_stop_distance_pct=hard_filters["min_stop_distance_pct"],
                                            max_stop_distance_pct=effective_max_stop,
                                            min_risk_reward=hard_filters["min_risk_reward_ratio"],
                                            block_bullish=veto_bullish_for(df))
```

Confirm `log` exists in this module before using it (`grep -n "^log = " swingbot/core/scanning/analyze.py`).

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/scanning/test_analyze_dcb_veto.py
python scripts/dev/testrun.py file tests/scanning/test_analyze.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/analyze.py tests/scanning/test_analyze_dcb_veto.py
git commit -m "feat(v68): wire the dead-cat-bounce veto into the live scan"
```

---

### Task D6: Wire the replay harness

**Files:**
- Modify: `swingbot/core/backtesting/backtest_scenarios.py` (`replay_scenarios`)
- Test: `tests/backtesting/test_replay_dcb_veto.py`

**Interfaces:**
- Consumes: `dead_cat_bounce` (D1), `build_scenarios(block_bullish=)` (D4).
- Produces: `replay_scenarios(..., dcb_params: dict | None = None)` — `None`
  means no veto, which is the baseline arm.

**The harness takes params directly, not from config.** The grid needs twelve
different parameter sets in one process; reading config would make them a
global the workers fight over.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtesting/test_replay_dcb_veto.py`:

```python
"""The replay harness honours the same veto the live scan does."""
import inspect

import pytest

from swingbot.core.backtesting import backtest_scenarios


def test_the_harness_accepts_params_not_config():
    # Twelve cells in one process: a config read would make them a global the
    # workers fight over.
    sig = inspect.signature(backtest_scenarios.replay_scenarios)
    assert "dcb_params" in sig.parameters
    assert sig.parameters["dcb_params"].default is None


def test_none_means_no_veto(monkeypatch):
    called = []
    monkeypatch.setattr(backtest_scenarios, "dead_cat_bounce",
                        lambda *a, **k: called.append(1) or {"detected": True})
    # The baseline arm must not pay for a detector it does not use.
    assert called == []


def test_the_window_passed_to_the_detector_never_extends_past_the_bar(monkeypatch):
    """The harness's own no-lookahead guarantee, asserted at the seam where
    v68 could break it."""
    seen = []
    monkeypatch.setattr(backtest_scenarios, "dead_cat_bounce",
                        lambda window, params: seen.append(len(window))
                        or {"detected": False})
    # Driven by the harness's existing per-bar loop; lengths must be strictly
    # non-decreasing and never exceed the bar index + 1.
    assert seen == sorted(seen)
```

The third test needs a real (small) frame driven through `replay_scenarios`.
Build one with `make_trend_df` and assert against the recorded window lengths;
if the harness's loop shape makes that awkward, assert instead that every
window's last index equals the bar being evaluated. Either proves the property
— do not drop it.

- [ ] **Step 2: Run to verify failure**

```bash
python -m pytest tests/backtesting/test_replay_dcb_veto.py -q
```

Expected: `KeyError: 'dcb_params'` from the signature assertion.

- [ ] **Step 3: Wire it**

In `replay_scenarios`, add the parameter and the call:

```python
def replay_scenarios(ticker, df, horizon_key, *, gates,
                     dcb_params: dict | None = None) -> list:
```

and immediately before the `build_scenarios` call at `:100`:

```python
        # v68. `window` is the harness's no-lookahead slice -- the same frame
        # the live scan hands to veto_bullish_for. dcb_params=None is the
        # baseline arm and must not pay for the detector at all.
        block_bullish = False
        if dcb_params is not None:
            block_bullish = bool(dead_cat_bounce(window, dcb_params)["detected"])
```

Pass `block_bullish=block_bullish` into `build_scenarios`. Thread `dcb_params`
through `_replay_ticker` and `run_scenario_backtest` so a caller can set it once.

- [ ] **Step 4: Run the tests**

```bash
python scripts/dev/testrun.py file tests/backtesting/test_replay_dcb_veto.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_scenarios.py
```

Expected: `0 failed` for both.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/backtest_scenarios.py \
        tests/backtesting/test_replay_dcb_veto.py
git commit -m "feat(v68): let the confluence replay apply the veto"
```

---

### Task D7: Live and replay cannot disagree

**Files:**
- Test: `tests/market/test_dcb_parity.py`

**Interfaces:**
- Consumes: everything from D1–D6.
- Produces: nothing.

The whole design rests on one claim: the veto that TRAIN measures is the veto
that ships. That claim gets a test rather than a comment.

- [ ] **Step 1: Write the test**

Create `tests/market/test_dcb_parity.py`:

```python
"""The veto TRAIN measures is the veto that ships.

entry_filters.py enforces this for entry logic by construction -- one
function, both worlds. v68's veto has two call sites, so it needs a test.
"""
import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot import config
from swingbot.core.market.chart_patterns import dead_cat_bounce, params_from_config
from swingbot.core.scanning import analyze


def _frames():
    peak, trough = 100.0, 70.0
    dcb = make_ohlcv([peak] * 30 + list(np.linspace(peak, trough, 8))[1:]
                     + [72.0, 74.0, 75.0])
    recovery = make_ohlcv([peak] * 30 + list(np.linspace(peak, trough, 8))[1:]
                          + [85.0, 92.0, 96.0])
    calm = make_ohlcv([100.0] * 45)
    return {"dcb": dcb, "recovery": recovery, "calm": calm}


@pytest.mark.parametrize("name", ["dcb", "recovery", "calm"])
def test_both_call_sites_reach_the_same_verdict(name, monkeypatch):
    monkeypatch.setattr(config, "DEAD_CAT_BOUNCE_VETO", True)
    frame = _frames()[name]

    live = analyze.veto_bullish_for(frame)
    replay = dead_cat_bounce(frame, params_from_config())["detected"]

    assert live == replay, f"{name}: live={live} replay={replay}"


def test_the_live_seam_uses_the_shared_params_builder():
    """A second params dict anywhere is how the two worlds drift apart."""
    import inspect
    source = inspect.getsource(analyze.veto_bullish_for)
    assert "params_from_config()" in source
```

- [ ] **Step 2: Run it**

```bash
python scripts/dev/testrun.py file tests/market/test_dcb_parity.py
python scripts/dev/testrun.py fast
```

Expected: `0 failed`. The fast tier here, not `full` — D5 and D6 touched the
scan and backtest paths, so the blast radius genuinely crosses files.

- [ ] **Step 3: Commit**

```bash
git add tests/market/test_dcb_parity.py
git commit -m "test(v68): pin live/replay parity for the veto"
```

---

### Task D8: The TRAIN grid — twelve cells, one replay pass

**Files:**
- Create: `scripts/backtest/measure_dcb_veto.py`
- Create: `docs/superpowers/results/2026-08-30-v68-dcb-veto-train.md`

**Interfaces:**
- Consumes: `replay_scenarios` (D6), `dead_cat_bounce` (D1),
  `backtest_scenarios._aggregate`.
- Produces: the TRAIN table and the selection-rule verdict.

**The runtime problem, and the design that solves it.**
`tune_confluence_gates.py`'s docstring records that *"a single grid point alone
ran for hours"* on the full universe even parallelised across 12 cores. Twelve
cells run naively is days of compute, which is how a measurement never gets
made.

It is also unnecessary. **The veto is a pure function of the frame at the entry
bar** — it does not change which levels are found or which scenarios are
geometrically valid, only which of them survive. So:

> Run the replay **once** with `dcb_params=None`. At each accepted entry bar,
> evaluate all twelve parameter cells against the frame already in hand and
> record the twelve booleans alongside the trade's outcome. Aggregating per
> cell afterwards is then arithmetic over a table, not twelve backtests.

One expensive pass, twelve cheap filters. It is also **more** rigorous than
twelve separate runs: every cell scores the identical trade population, so a
delta is attributable to the veto alone and not to any run-to-run variation.

- [ ] **Step 1: Write the harness**

Create `scripts/backtest/measure_dcb_veto.py`. It must:

1. Load TRAIN frames from `data/backtest_cache/` (see
   `tune_confluence_gates.py` for the loader and the `SAMPLE_EVERY`
   deterministic alphabetical stride — reuse both, and print the actual ticker
   list so the sample is auditable rather than silently smaller).
2. Run `run_scenario_backtest` once over TRAIN with `dcb_params=None`,
   instrumented to emit, per accepted trade: `ticker, horizon, entry_index,
   direction, outcome, r_multiple` **plus** `dcb[cell_id] -> bool` for all
   twelve cells, computed at the entry bar from the same no-lookahead window.
3. Write that table to `data/v68_train_dcb.json` (gitignored, matching the
   `data/v3*_*.json` precedent).
4. Aggregate per cell: baseline vs. veto-on win rate, ExpR, N surviving, and
   alert-volume cut.
5. Print the pre-registered rule verbatim beside the table.

The twelve cells:

```python
GRID = [
    {"decline_pct": d, "gap_required": g, "volume_ratio": v}
    for d in (15.0, 20.0, 25.0)
    for g in (False, True)
    for v in (None, 0.8)
]   # 3 x 2 x 2 = 12
```

The pre-registered rule, to be printed and quoted in the results doc:

```
RULE = ("select the cell with the greatest pooled ExpR improvement over the "
        "veto-off baseline, among cells with N>=30 surviving trades AND an "
        "alert-volume cut <=30%. If no cell satisfies both, no cell is "
        "selected and VALIDATION is NOT spent.")
```

Progress output is per-ticker and flushed —
`docs/claude/working-conventions.md` requires it for anything that can run for
more than a couple of minutes, and this will.

- [ ] **Step 2: Smoke it on a small sample first**

```bash
python scripts/backtest/measure_dcb_veto.py --tickers AAPL,MSFT --horizons 4w --dry-run
```

Expected: a complete table over a tiny population in under a minute. **Do not
start the full run until this shape is right** — discovering a column is
missing after six hours is how a session's compute budget disappears.

- [ ] **Step 3: Run the full TRAIN grid**

```bash
python scripts/backtest/measure_dcb_veto.py --train 2>&1 | tee /tmp/v68-train.log
```

Dispatch this to the `backtest-runner` subagent — it runs for hours and its
per-ticker progress must not land in the main context.

- [ ] **Step 4: Record the result**

Write `docs/superpowers/results/2026-08-30-v68-dcb-veto-train.md` with: the
ticker sample actually used, the full twelve-row table (win rate, ExpR, N,
alert cut, per cell), the rule quoted verbatim, the selected cell **or the
explicit statement that none qualified**, and an honest observations section.

**Every cell that returned fewer than 30 surviving trades is named as such.** A
cell with no data is a different fact from a cell that measured badly, and
collapsing the two is how a negative result gets misread later.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_dcb_veto.py \
        docs/superpowers/results/2026-08-30-v68-dcb-veto-train.md
git commit -m "measure(v68): TRAIN grid for the dead-cat-bounce veto"
```

---

### Task D9: VALIDATION — one shot, and only if earned

**Files:**
- Create: `docs/superpowers/results/2026-08-30-v68-dcb-veto-validation.md`
- Modify: `swingbot/config.py` (flip the default — **only** on a pass)

**Interfaces:**
- Consumes: D8's selected cell.
- Produces: the validation record, and possibly a default flip.

- [ ] **Step 1: Check whether this task runs at all**

Read D8's results document. **If no cell cleared the rule, this task does not
run.** Instead:

- write `docs/superpowers/results/`'s closing paragraph recording that
  VALIDATION was deliberately not spent and the budget remains available,
- move the spec and plan to `no-lift/` per `document-lifecycle.md`,
- skip to D10.

That is the v36 and v49 outcome and it is a finished result, not an
unfinished task. A negative TRAIN closes the component; re-running it with a
looser rule is the exact failure the one-shot budget exists to prevent.

- [ ] **Step 2: Run VALIDATION once**

```bash
python scripts/backtest/measure_dcb_veto.py \
    --validation --cell "<the exact cell id D8 selected>" \
    2>&1 | tee /tmp/v68-validation.log
```

One cell. One run. The result is recorded as-is whatever it says.

- [ ] **Step 3: Apply the gates**

`expectancy_r > 0`, `win_rate >= 50`, `N >= 15`, scratches+timeouts ≤ 50% of
closed trades. All four, on the surviving population.

- [ ] **Step 4: Record and decide the default**

Write the validation results doc. **If all four gates hold**, flip
`DEAD_CAT_BOUNCE_VETO`'s default `"false"` → `"true"` and set the three grid
fields to the selected cell's values. **If any gate fails**, the default stays
`false`, the code stays merged and inert, and the doc says so plainly.

Both outcomes are legitimate. v35's AVWAP row is the precedent for "on because
it degrades nothing, NOT because an edge was measured" — if that is what the
numbers say, say exactly that.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/results/2026-08-30-v68-dcb-veto-validation.md swingbot/config.py
git commit -m "measure(v68): VALIDATION shot for the dead-cat-bounce veto"
```

---

### Task D10: Full-suite verification and close-out

**Files:**
- Modify: `VERSION.json`, `frontend/src/assets/version_history.json`
- Modify: `docs/claude/known-traps.md`
- Move: the spec and plan into `implemented/` or `no-lift/`

- [ ] **Step 1: Run the full suite, once**

```bash
python scripts/dev/testrun.py full
```

Expected: `0 failed`, `0 xfailed`. Dispatch `test-runner` to keep the output
out of context. This plan touches no `frontend/` source, so `npm test` is not
part of its gate.

- [ ] **Step 2: Record the trap**

Add to `docs/claude/known-traps.md`:

- **The dead-cat-bounce veto is invisible to `run_backtest_range.py`.** It
  lives on the confluence path (`build_scenarios`), which the strategy backtest
  never reaches. Measuring it needs `backtest_scenarios.py` — the same split
  that made v34's RS_GATE need its own instrument and that made
  `DATA_DRIVEN_STOPS` unmeasurable by construction.

- [ ] **Step 3: Bump and regenerate**

`bot` patch `1.5.0` → `1.5.1` (inert code behind a default-off flag), or
`1.6.0` minor if D9 flipped the default on — a gate that changes which alerts
get posted is an observable difference, and `document-conventions.md` says to
argue the bump from that, not from diff size.

Then, and this is the step that gets missed because the local gate runs
*before* the bump and structurally cannot catch it:

```bash
python scripts/dev/build_version_matrix.py
git diff --stat frontend/src/assets/version_history.json
```

An empty diff means the bump was not picked up — investigate before committing.

- [ ] **Step 4: Close the documents out**

```bash
git mv docs/superpowers/specs/2026-08-30-v68-dead-cat-bounce-veto-design.md \
       docs/superpowers/specs/implemented/     # or no-lift/
git mv docs/superpowers/plans/2026-08-30-v68-dead-cat-bounce-veto.md \
       docs/superpowers/plans/implemented/     # or no-lift/
```

`implemented/` if the veto shipped or landed inert after a spent VALIDATION;
`no-lift/` if TRAIN found nothing and the budget was preserved.

Amend the spec's `Bump:` and `Edge:` lines in this commit if either prediction
came out wrong, with one clause saying why. A spec that predicted `expectancy`
and measured nothing is the most useful record this repo keeps — it is the
exact shape of the mistake the one-shot budget exists to make expensive.

- [ ] **Step 5: Commit**

```bash
git add VERSION.json frontend/src/assets/version_history.json \
        docs/claude/known-traps.md docs/superpowers
git commit -m "release(v68): bot 1.5.1 -- dead-cat-bounce veto"
```

---

## Success criteria

1. `dead_cat_bounce` detects the textbook structure and rejects V-recoveries,
   shallow declines and still-falling frames.
2. The verdict is provably causal — D2, including the guard against passing
   vacuously.
3. Live and replay reach identical verdicts for the same frame — D7.
4. A twelve-cell TRAIN table exists with the rule quoted and every
   under-populated cell named.
5. Either one cell earned a VALIDATION shot and it was spent once, **or** none
   did and the budget is explicitly preserved.
6. `python scripts/dev/testrun.py full` is green.
