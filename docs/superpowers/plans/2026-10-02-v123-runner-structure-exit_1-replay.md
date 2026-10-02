# Structure-aware runner exit — implementation plan, part 1 (Phases 0–2)

> Part of v123. Header, global constraints, file map, spec reconciliations, review focus and `## Parallelisation` live in `2026-10-02-v123-runner-structure-exit_0-index.md`; read it and the spec (`docs/superpowers/specs/2026-10-02-v123-runner-structure-exit-design.md`) with any task here.

# Phase 0 — Headroom

### Task V123-0: Baseline runner capture on TRAIN replay

**Files:** Create `scripts/reports/runner_headroom.py`, `tests/scripts/test_runner_headroom.py`, `docs/superpowers/results/2026-10-02-v123-runner-headroom.md`.

**Interfaces:**
- Produces: `runner_metrics(df, result, plan) -> dict | None`, with keys `horizon_key`, `source`, `runner_r`, `mfe_r`, `capture`, `reason`, or None when the trade never touched TP1 or has no runner leg. Also `summarise(rows) -> dict` (pooled plus `per_horizon`) and `stop_rule(summary) -> str` (`"NO_HEADROOM"` when mean capture ≥ 0.75, else `"HEADROOM"`).
- Consumes: `StrategyEngine().iter_trades`, `replay_scenarios`, `simulate_exit(..., scale_out=True)`, `measure_arms.cached_universe/load_frame/_write_progress`.

This task is read-only against the engine and touches no `swingbot/` file. The result is baseline description, not selection.

- [ ] **Write the failing test.** It pins the MFE definition on a hand-built runner. Runner MFE is the best close from the TP1 bar through the bar before the runner exit, capped below by the runner's own realised R.

```python
# tests/scripts/test_runner_headroom.py
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
from runner_headroom import runner_metrics, stop_rule, summarise  # noqa: E402

from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan


def test_mfe_is_best_close_after_tp1_before_exit():
    df = make_ohlcv([100.0, (100, 111, 99.5, 110.5), (110, 114, 108, 113.0),
                     (113, 113.5, 107, 108.5)])
    plan = _plan(stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, 0, plan, scale_out=True)
    row = runner_metrics(df, result, plan)
    assert row["reason"] == "runner_trail"
    assert row["runner_r"] == pytest.approx(1.6)
    assert row["mfe_r"] == pytest.approx((113.0 - 100.0) / 5.0)   # bar 2's close
    assert row["capture"] == pytest.approx(1.6 / 2.6)


def test_non_runner_trade_is_excluded():
    df = make_ohlcv([100.0, (100, 101, 94, 95)])
    plan = _plan(stop_loss=95.0, tp1=110.0)
    assert runner_metrics(df, simulate_exit(df, 0, plan, scale_out=True), plan) is None


def test_frozen_stop_rule():
    rows = [{"horizon_key": "2w", "source": "strategy", "runner_r": 1.0, "mfe_r": 1.25,
             "capture": 0.8, "reason": "runner_trail"}]
    assert stop_rule(summarise(rows)) == "NO_HEADROOM"
    rows[0]["capture"] = 0.74
    assert stop_rule(summarise(rows)) == "HEADROOM"
```

- [ ] Run `python scripts/dev/testrun.py file tests/scripts/test_runner_headroom.py`. Expect an import failure.
- [ ] **Implement.**

```python
#!/usr/bin/env python3
"""v123 Task 0: baseline runner capture (runner R vs runner MFE) on TRAIN replay."""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

TRAIN = ("2020-01-01", "2023-12-31")
STOP_CAPTURE = 0.75          # spec v123 frozen stop rule


def _tp1_index(df, result, plan) -> int:
    high, low = df["High"].values, df["Low"].values
    for j in range(result.entry_index + 1, result.exit_index + 1):
        if (high[j] >= plan.tp1) if plan.direction == "bullish" else (low[j] <= plan.tp1):
            return j
    return result.exit_index


def runner_metrics(df, result, plan) -> dict | None:
    if result.outcome != "win" or len(result.legs) != 2:
        return None
    sign = 1 if plan.direction == "bullish" else -1
    risk = abs(result.entry_price - plan.stop_loss)
    closes = df["Close"].values[_tp1_index(df, result, plan):result.exit_index]
    runner_r = float(result.legs[1]["r"])
    best = max(((float(c) - result.entry_price) * sign / risk for c in closes), default=runner_r)
    mfe_r = max(best, runner_r)
    return {"horizon_key": plan.horizon_key, "source": plan.source, "runner_r": runner_r,
            "mfe_r": mfe_r, "capture": runner_r / mfe_r if mfe_r > 0 else None,
            "reason": result.legs[1]["reason"]}


def _block(rows) -> dict:
    captured = [r["capture"] for r in rows if r["capture"] is not None]
    reasons = Counter(r["reason"] for r in rows)
    n = len(rows)
    return {"n": n,
            "mean_runner_r": sum(r["runner_r"] for r in rows) / n if n else None,
            "mean_mfe_r": sum(r["mfe_r"] for r in rows) / n if n else None,
            "mean_capture": sum(captured) / len(captured) if captured else None,
            "sum_capture": (sum(r["runner_r"] for r in rows) / sum(r["mfe_r"] for r in rows)
                            if n and sum(r["mfe_r"] for r in rows) > 0 else None),
            "reasons_pct": {k: v / n * 100 for k, v in sorted(reasons.items())}}


def summarise(rows) -> dict:
    by_h = defaultdict(list)
    for row in rows:
        by_h[row["horizon_key"]].append(row)
    return {"pooled": _block(rows), "per_horizon": {h: _block(v) for h, v in sorted(by_h.items())}}


def stop_rule(summary) -> str:
    mean = summary["pooled"]["mean_capture"]
    return "NO_HEADROOM" if mean is not None and mean >= STOP_CAPTURE else "HEADROOM"


def _ticker_rows(task) -> list:
    from measure_arms import load_frame
    from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.planning.plan_engine import simulate_exit
    from swingbot.scan_params import ScanParams
    ticker, horizons = task
    df, params, out = load_frame(ticker), ScanParams.from_config(), []
    if df is None:
        return []
    engine = StrategyEngine()
    for hk in horizons:
        for strategy in engine.strategies:
            for _date, plan, result in engine.iter_trades(ticker, df, strategy, hk, TRAIN, params):
                out.append(runner_metrics(df, result, plan))
        for index, plan in replay_scenarios(ticker, df.loc[:TRAIN[1]], hk, params=params):
            if str(df.index[index].date()) >= TRAIN[0]:
                out.append(runner_metrics(df, simulate_exit(df, index, plan, scale_out=True), plan))
    return [row for row in out if row is not None]
```

Then add `main()`:

```python
def main(argv=None) -> int:
    from measure_arms import _write_progress, cached_universe
    from swingbot.core.backtesting.arms.windows import ALL_HORIZONS
    from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args(argv)
    universe = cached_universe()
    progress = ROOT / "logs" / f"runner_headroom.{uuid.uuid4().hex[:8]}.progress"
    rows, done = [], 0
    with ProcessPoolExecutor(max_workers=_resolve_replay_workers(args.workers)) as pool:
        for future in as_completed([pool.submit(_ticker_rows, (t, ALL_HORIZONS)) for t in universe]):
            rows.extend(future.result())
            done += 1
            print(f"  {done}/{len(universe)} tickers", flush=True)
            _write_progress(progress, done, len(universe))
    progress.unlink(missing_ok=True)
    summary = summarise(rows)
    summary["verdict"] = stop_rule(summary)
    args.out_json.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary["pooled"], indent=1), "\nverdict:", summary["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] Run the narrow test file again and expect PASS. Run `python -m radon cc -s -n C scripts/reports/runner_headroom.py`: nothing at 15 or above.
- [ ] Write `docs/superpowers/results/2026-10-02-v123-runner-headroom.md` **before** running. It quotes the frozen stop rule verbatim from the spec, with the definitions above: MFE window `[TP1 bar, exit bar)`, capped below by realised runner R; capture = runner R / MFE R over trades with MFE > 0. It names window TRAIN 2020-01-01..2023-12-31, the full cached universe and all ten horizons, both engines, at code defaults. Commit the record and the script: `git add scripts/reports/runner_headroom.py tests/scripts/test_runner_headroom.py docs/superpowers/results/2026-10-02-v123-runner-headroom.md && git commit -m "feat(v123): runner headroom instrument + frozen Task 0 record"`.
- [ ] Invoke `backtest-gate`. This run is baseline description, not a funnel stage. Dispatch `backtest-runner` with `python scripts/reports/runner_headroom.py --out-json docs/superpowers/results/2026-10-02-v123-runner-headroom.json`.
- [ ] Append the pooled and per-horizon table, the exit-reason mix, both capture forms and the verdict to the record, as-is. The 2026-09-10 "43%" memory figure is superseded by this re-derivation. Commit the JSON and the record. **If the verdict is `NO_HEADROOM`,** follow the Parallelisation rule: both arms close without a shot.

# Phase 1 — Contract and knobs

### Task V123-1: v121 gate and the structure-frame adapter

**Files:** Modify `swingbot/core/planning/exit_sim.py`. Create `tests/planning/structure_fixtures.py` and `tests/planning/test_runner_structure_frame.py`.

**Interfaces:**
- Consumes: v121 `swingbot.core.market.structure`: `confirmed_pivots(df, k=PIVOT_K)` (columns `PIVOT_COLUMNS` = `last_sh_pos, last_sh, prior_sh_pos, prior_sh, last_sl_pos, last_sl, prior_sl_pos, prior_sl`, positions as floats), `true_range(df)`, `SHORT_WINDOW, LONG_WINDOW = 10, 50`, `MIN_BARS = 60` and `structure_features(df, direction)`. These names are taken from the v121 plan `docs/superpowers/plans/2026-10-02-v121-structure-volume-context.md` (Tasks producing `structure.py`). v121 exposes the two ratios only as scalars at the final bar (`_ratio_of_means`), not as per-bar series, so v123 rebuilds the per-bar series from v121's own `true_range` and window constants. A test pins it equal to v121's scalar at every bar from `MIN_BARS` on.
- Produces: `exit_sim.PIVOT_K = 3`, `exit_sim.runner_structure_frame(df) -> pd.DataFrame` with float columns `sh_i, sh_px, sh_prev_i, sh_prev_px, sl_i, sl_px, sl_prev_i, sl_prev_px, range_trend_10_50, vol_trend_10_50`. `*_i` are bar **positions** (NaN where none). Row `j` holds the last and prior confirmed swing high and low known at `j`. Also `tests/planning/structure_fixtures.py`: `WARMUP = 60`, `sawtooth_closes(cycles, start=100.0)`, `sawtooth(cycles, tail=())`, `stall_frame()`.

- [ ] **Gate.** Run `git log --oneline main -- swingbot/core/market/structure.py`. If it prints nothing, **stop and report `BLOCKED: v121 not merged`**; no later code task may start. Otherwise run `git grep -n "^def \|^PIVOT_COLUMNS\|^SHORT_WINDOW\|^MIN_BARS" swingbot/core/market/structure.py` and confirm the names in **Consumes** above. If the merged module renamed any, edit **only** `_V121_PIVOT_COLUMNS` (and the two window/true-range references in `_trend_ratio`) to match. Never re-derive a pivot.
- [ ] **Fixtures.** One 4-up/3-down cycle (+2 ×4, −1 ×3) prints one higher swing high and one higher swing low after 60 flat bars. Flat bars give no strict pivots. `stall_frame()` ends with a lower high, then 11 quiet bars (range ±0.05, volume 0.4M).

```python
# tests/planning/structure_fixtures.py
"""Deterministic frames with known swing structure (v123 runner tests)."""
from tests.helpers import make_ohlcv

WARMUP = 60
CYCLE = (2.0, 2.0, 2.0, 2.0, -1.0, -1.0, -1.0)


def sawtooth_closes(cycles, start=100.0):
    closes = [start] * WARMUP
    for _ in range(cycles):
        for step in CYCLE:
            closes.append(closes[-1] + step)
    return closes


def sawtooth(cycles, tail=()):
    return make_ohlcv(sawtooth_closes(cycles) + [float(c) for c in tail], spread=0.001)


def stall_frame():
    closes = sawtooth_closes(4)
    sl = closes[-1]                                  # last swing-low close; prior top = sl + 3
    closes += [sl + 1.0, sl + 2.0, sl + 1.5, sl + 1.0, sl + 0.5] + [sl + 0.5] * 6
    df = make_ohlcv(closes, spread=0.001)
    quiet = df.index[-11:]
    df.loc[quiet, "High"] = df.loc[quiet, "Close"] + 0.05
    df.loc[quiet, "Low"] = df.loc[quiet, "Close"] - 0.05
    df.loc[quiet, "Volume"] = 400_000.0
    return df
```

- [ ] **Write the failing tests.**

```python
# tests/planning/test_runner_structure_frame.py
import math

import pandas as pd
import pytest

from swingbot.core.planning.exit_sim import PIVOT_K, runner_structure_frame
from tests.planning.structure_fixtures import WARMUP, sawtooth, stall_frame

POSITIONS = ("sh_i", "sh_prev_i", "sl_i", "sl_prev_i")


def test_v121_contract_is_merged():
    from swingbot.core.market import structure
    assert callable(structure.confirmed_pivots)


def test_frame_is_truncation_stable():
    df = stall_frame()
    full = runner_structure_frame(df)
    for cut in range(5, len(df) + 1):
        pd.testing.assert_series_equal(runner_structure_frame(df.iloc[:cut]).iloc[-1],
                                       full.iloc[cut - 1], check_names=False)


def test_no_pivot_is_known_before_k_bars():
    frame = runner_structure_frame(stall_frame())
    for j in range(len(frame)):
        for col in POSITIONS:
            value = frame[col].iloc[j]
            assert math.isnan(value) or value <= j - PIVOT_K


def test_trend_ratios_equal_v121_scalars_at_every_bar():
    from swingbot.core.market import structure
    df = stall_frame()
    frame = runner_structure_frame(df)
    for t in range(structure.MIN_BARS - 1, len(df)):
        scalar = structure.structure_features(df.iloc[:t + 1], "bullish")
        for key in ("range_trend_10_50", "vol_trend_10_50"):
            assert frame[key].iloc[t] == pytest.approx(scalar[key], abs=1e-6), (key, t)


def test_sawtooth_prints_a_higher_low_each_cycle():
    df = sawtooth(3)
    frame = runner_structure_frame(df)
    first_sl = WARMUP + 6                     # bottom of cycle 1
    assert frame["sl_i"].iloc[first_sl + PIVOT_K] == first_sl
    assert frame["sl_px"].iloc[first_sl + PIVOT_K] == df["Low"].iloc[first_sl]
    assert math.isnan(frame["sl_i"].iloc[first_sl + PIVOT_K - 1]) or \
        frame["sl_i"].iloc[first_sl + PIVOT_K - 1] < first_sl
```

- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_runner_structure_frame.py`. Expect `runner_structure_frame` missing.
- [ ] **Implement** at the top of `exit_sim.py`. Add `import pandas as pd`. The `structure` import stays local, the same as the existing `atr_indicator` import.

```python
#: v121's pivot column names mapped to v123's. The ONLY place v121 column
#: names appear in v123; V123-1's gate step checks them against the merged module.
_V121_PIVOT_COLUMNS = {
    "sh_i": "last_sh_pos", "sh_px": "last_sh",
    "sh_prev_i": "prior_sh_pos", "sh_prev_px": "prior_sh",
    "sl_i": "last_sl_pos", "sl_px": "last_sl",
    "sl_prev_i": "prior_sl_pos", "sl_prev_px": "prior_sl",
}
PIVOT_K = 3                                      # v121 frozen fractal width


def _trend_ratio(series: pd.Series) -> pd.Series:
    """Per-bar mean(last SHORT_WINDOW) / mean(last LONG_WINDOW) -- the series
    form of v121's scalar _ratio_of_means. NaN before LONG_WINDOW bars; a zero
    long mean gives inf/NaN, which no <= comparison passes."""
    from swingbot.core.market import structure
    short = series.rolling(structure.SHORT_WINDOW).mean()
    long = series.rolling(structure.LONG_WINDOW).mean()
    return (short / long).astype(float)


def runner_structure_frame(df) -> pd.DataFrame:
    """Per-bar confirmed pivots and range/volume trends for the v123 runner
    rules. Row j uses df.iloc[:j+1] only (v121 truncation contract; rolling
    windows are causal)."""
    from swingbot.core.market import structure
    pivots = structure.confirmed_pivots(df, k=PIVOT_K)
    out = pd.DataFrame(index=df.index)
    for ours, theirs in _V121_PIVOT_COLUMNS.items():
        out[ours] = pivots[theirs].astype(float).values
    out["range_trend_10_50"] = _trend_ratio(structure.true_range(df)).values
    out["vol_trend_10_50"] = _trend_ratio(df["Volume"].astype(float)).values
    return out
```

- [ ] Rerun the narrow file and expect PASS. Invoke `no-lookahead` on `runner_structure_frame`. Run radon on `exit_sim.py`: the new functions are under 15, and `_scale_out_exit_walk` is still 30 and untouched. Commit: `git add swingbot/core/planning/exit_sim.py tests/planning/structure_fixtures.py tests/planning/test_runner_structure_frame.py && git commit -m "feat(v123): v121 structure-frame adapter for the runner"`.

### Task V123-2: Three searchable knobs, registered unreachable

**Files:** Modify `swingbot/config.py`, `swingbot/scan_params.py`, `.env.example`, `swingbot/core/backtesting/arms/reachability.py`, `tests/test_v115_strategy_work_off.py`. Create `tests/test_runner_structure_knobs.py`.

**Interfaces:**
- Produces: `config.RUNNER_STRUCTURE_EXIT: str` (`off|hl_trail|progress_stall`), `config.RUNNER_HL_TRAIL_ATR_BUFFER: float`, `config.RUNNER_STALL_RANGE_MAX: float`. ScanParams fields `runner_structure_exit`, `runner_hl_trail_atr_buffer`, `runner_stall_range_max`. Registry rows classified `outside_replay` until V123-10.

- [ ] **Write the failing tests.**

```python
# tests/test_runner_structure_knobs.py
from swingbot import config
from swingbot.core.backtesting.arms import reachability as reach

KNOBS = ("RUNNER_STRUCTURE_EXIT", "RUNNER_HL_TRAIL_ATR_BUFFER", "RUNNER_STALL_RANGE_MAX")


def _field(attr):
    return next(f for f in config.FIELDS if f.attr == attr)


def test_defaults_and_search_class():
    assert config._cast(_field("RUNNER_STRUCTURE_EXIT"), "off") == "off"
    assert config._cast(_field("RUNNER_HL_TRAIL_ATR_BUFFER"), _field("RUNNER_HL_TRAIL_ATR_BUFFER").default) == 0.0
    assert config._cast(_field("RUNNER_STALL_RANGE_MAX"), _field("RUNNER_STALL_RANGE_MAX").default) == 1.0
    assert set(KNOBS) <= set(config.searchable_attrs())


def test_invalid_mode_falls_back_to_off():
    assert config._cast(_field("RUNNER_STRUCTURE_EXIT"), "HL_TRAIL") == "hl_trail"
    assert config._cast(_field("RUNNER_STRUCTURE_EXIT"), "bogus") == "off"


def test_unwired_knobs_are_refused_by_the_producer():
    for attr in KNOBS:
        assert reach.classify(attr) == reach.OUTSIDE_REPLAY
```

- [ ] Run `python scripts/dev/testrun.py file tests/test_runner_structure_knobs.py`. Expect failure.
- [ ] **Implement.** In `config.py`, add after the `STALL_EXIT_ENABLED` Field (section `"Exit quality"`):

```python
    Field("RUNNER_STRUCTURE_EXIT", "RUNNER_STRUCTURE_EXIT", "Exit quality",
          "Structure-aware runner exit (v123)",
          type="select", default="off",
          options=[("off", "Off -- chandelier trail, runner floor, TP2, timeout only"),
                   ("hl_trail", "Higher-low trail -- stop follows the last confirmed post-entry swing low"),
                   ("progress_stall", "Progress stall -- exit next open on a failed higher high, contracting range and cooling volume")],
          help="v123. Post-TP1 runner only; cannot move win rate. Evaluated on completed "
               "daily bars (exit_sim.runner_structure_step, shared with plan_manager). "
               "Off until its own pre-registered harvest funnel judges it."),
    Field("RUNNER_HL_TRAIL_ATR_BUFFER", "RUNNER_HL_TRAIL_ATR_BUFFER", "Exit quality",
          "Higher-low trail ATR buffer (b)",
          type="float", default="0.0", min=0.0, max=1.0, step=0.25,
          help="v123 hl_trail: stop = last confirmed post-entry swing low - b x ATR(14). Grid {0, 0.25, 0.5}."),
    Field("RUNNER_STALL_RANGE_MAX", "RUNNER_STALL_RANGE_MAX", "Exit quality",
          "Progress-stall range ratio ceiling (c)",
          type="float", default="1.0", min=0.5, max=1.5, step=0.05,
          help="v123 progress_stall: fires only when mean TR(10)/mean TR(50) <= c. Grid {0.70, 0.85, 1.00}."),
```

Add the three attrs to `_SEARCH_CLASSES["searchable"]` after `"STALL_EXIT_ENABLED",`. In `_cast`, before `caster = _CASTERS.get(f.type)`:

```python
    if f.attr == "RUNNER_STRUCTURE_EXIT":
        v = str(raw).lower()
        if v not in ("off", "hl_trail", "progress_stall"):
            log.warning("invalid RUNNER_STRUCTURE_EXIT=%r, falling back to 'off'", raw)
            return "off"
        return v
```

In `scan_params.py`, add after `fib_target_1_0_extension: bool`: `runner_structure_exit: str`, `runner_hl_trail_atr_buffer: float`, `runner_stall_range_max: float`. Add the matching `from_config` lines, for example `runner_structure_exit=config.RUNNER_STRUCTURE_EXIT,`. In `.env.example`, add after `STALL_EXIT_ENABLED=false` a commented block with `RUNNER_STRUCTURE_EXIT=off`, `RUNNER_HL_TRAIL_ATR_BUFFER=0.0` and `RUNNER_STALL_RANGE_MAX=1.0`. In `tests/test_v115_strategy_work_off.py`, append `("v123", "RUNNER_STRUCTURE_EXIT", "off"),` to `FLAGS_OFF`. In `reachability.py`, add `_V123 = "v123: the runner walk does not read this yet (wired in V123-5, reclassified in V123-10)."` and three registry rows `"RUNNER_STRUCTURE_EXIT": _outside(_V123)`, and so on.

- [ ] Run the narrow file plus `tests/test_scan_params_coverage.py`, `tests/backtesting/arms/test_reachability.py`, `tests/test_v115_strategy_work_off.py` and `tests/backtesting/test_knob_observability.py::test_every_searchable_knob_is_classified`. Expect PASS. Run radon on `config.py:_cast` (8 now, 10 after): under 15. Commit the six files: `feat(v123): runner structure knobs (searchable, unwired)`.

# Phase 2 — Replay

### Task V123-3: Behaviour-preserving split of `_scale_out_exit_walk`

**Files:** Modify `swingbot/core/planning/exit_sim.py`. Create `tests/planning/test_exit_sim_scaleout_witness.py` and `tests/planning/fixtures/scale_out_witness.sha256`.

**Interfaces:**
- Produces: `_WalkCtx` (frozen dataclass: `high, low, close, entry_index, entry_price, plan, is_bull, sign, risk, end`). Phase helpers `_pre_tp1_phase(ctx) -> ExitResult | int`, `_runner_phase(df, ctx, tp1_index) -> tuple[float, int, str]`, `_runner_bar_exit`, `_chandelier_ratchet`, `_runner_timeout`, `_runner_result(ctx, runner) -> ExitResult`, `_stall_exit`, `_full_leg`, `_no_trade`. `_scale_out_exit_walk`'s signature is unchanged.

`_scale_out_exit_walk` is CC 30 today. This commit changes no output: the witness hash must match before and after.

- [ ] **Write the witness on unchanged code.** Frames use exact binary fractions (multiples of 1/8), so results are platform-stable. Floats are rounded to 9 places before hashing.

```python
# tests/planning/test_exit_sim_scaleout_witness.py
"""Byte-identity witness for the scale-out walk (v123 V123-3 refactor, V123-5 off mode)."""
import dataclasses
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from swingbot.core.planning.plan_engine import simulate_exit
from tests.planning.test_exit_sim_single import _plan

FIXTURE = Path(__file__).parent / "fixtures" / "scale_out_witness.sha256"


def _frames():
    rng = np.random.default_rng(123)
    for _ in range(4):
        close = 100.0 + np.cumsum(rng.integers(-3, 4, 260) * 0.25)
        high = close + rng.integers(1, 8, 260) * 0.125
        low = close - rng.integers(1, 8, 260) * 0.125
        open_ = np.r_[close[0], close[:-1]]
        idx = pd.bdate_range("2020-01-02", periods=260)
        yield pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                            "Volume": rng.integers(5, 30, 260) * 1e5}, index=idx)


def _rounded(value):
    if isinstance(value, float):
        return round(value, 9)
    if isinstance(value, dict):
        return {k: _rounded(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_rounded(v) for v in value]
    return value


def witness_rows():
    rows = []
    for f, df in enumerate(_frames()):
        for i in range(20, 240, 11):
            c = float(df["Close"].iloc[i])
            for direction, sign in (("bullish", 1), ("bearish", -1)):
                for tp2 in (None, c + sign * 6.0):
                    plan = _plan(direction=direction, stop_loss=c - sign * 3.0,
                                 tp1=c + sign * 2.0, tp2=tp2, horizon_key="4w")
                    res = simulate_exit(df, i, plan, scale_out=True)
                    rows.append([f, i, direction, tp2 is not None, _rounded(dataclasses.asdict(res))])
    return rows


def witness_hash():
    return hashlib.sha256(json.dumps(witness_rows(), sort_keys=True).encode()).hexdigest()


def write_witness():
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(witness_hash() + "\n", encoding="utf-8")


def test_scale_out_walk_is_byte_identical_to_the_frozen_witness():
    assert witness_hash() == FIXTURE.read_text(encoding="utf-8").strip()


def test_witness_exercises_every_runner_reason():
    reasons = {row[4]["runner_outcome"] for row in witness_rows()}
    assert {"runner_be", "runner_trail", "runner_tp2", "runner_timeout"} <= reasons
```

- [ ] On the **unchanged** code, run `python -c "from tests.planning.test_exit_sim_scaleout_witness import write_witness; write_witness()"`. Then run `python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout_witness.py` and expect PASS. If `test_witness_exercises_every_runner_reason` fails, widen the `range(20, 240, 11)` step or the tp2 distance until all four reasons occur, then regenerate. Commit the witness and its hash alone: `test(v123): frozen scale-out walk witness`.
- [ ] **Refactor.** Replace the body of `_scale_out_exit_walk` (lines 173–320 today) with the following, keeping its docstring. Note: `_stall_exit` uses `not current_r < 0.5` so a NaN close behaves exactly as today.

```python
@dataclass(frozen=True)
class _WalkCtx:
    high: object
    low: object
    close: object
    entry_index: int
    entry_price: float
    plan: TradePlanV2
    is_bull: bool
    sign: int
    risk: float
    end: int


def _no_trade(entry_index, entry_price) -> ExitResult:
    return ExitResult(outcome="no_trade", runner_outcome=None, entry_index=entry_index,
                      exit_index=None, entry_price=entry_price, r_total=0.0, legs=[])


def _full_leg(ctx, outcome, j, price, r, reason) -> ExitResult:
    return ExitResult(outcome=outcome, runner_outcome=None, entry_index=ctx.entry_index,
                      exit_index=j, entry_price=ctx.entry_price, r_total=r,
                      legs=[{"fraction": 1.0, "exit_price": price, "r": r, "reason": reason}])


def _pre_tp1_touches(ctx, j, cur_stop, be_trigger):
    hi, lo = float(ctx.high[j]), float(ctx.low[j])
    if ctx.is_bull:
        return lo <= cur_stop, hi >= ctx.plan.tp1, hi >= be_trigger
    return hi >= cur_stop, lo <= ctx.plan.tp1, lo <= be_trigger


def _stall_exit(ctx, j) -> ExitResult | None:
    """Task 12 stall exit (pre-TP1); stop/target already won any same-bar tie."""
    plan = ctx.plan
    if not (config.STALL_EXIT_ENABLED and plan.stall_exit_day is not None
            and (j - ctx.entry_index) > plan.stall_exit_day):
        return None
    current_r = (float(ctx.close[j]) - ctx.entry_price) * ctx.sign / ctx.risk
    if not current_r < 0.5:
        return None
    r = round(current_r, 3)
    return _full_leg(ctx, "loss" if r < 0 else "scratch", j, float(ctx.close[j]), r, "stall_exit")


def _pre_tp1_phase(ctx) -> ExitResult | int:
    """Phase 1, identical to the single-leg walk: a terminal ExitResult, or the TP1 bar."""
    plan, stop_moved = ctx.plan, False
    target_dist = abs(plan.tp1 - ctx.entry_price)
    be_trigger = ctx.entry_price + ctx.sign * plan.breakeven_trigger_fraction * target_dist
    for j in range(ctx.entry_index + 1, ctx.end + 1):
        cur_stop = ctx.entry_price if stop_moved else plan.stop_loss
        hit_stop, hit_target, reached_trigger = _pre_tp1_touches(ctx, j, cur_stop, be_trigger)
        if hit_stop:  # conservative: stop first, exactly as single-leg
            return _full_leg(ctx, "scratch" if stop_moved else "loss", j, cur_stop,
                             round(0.0 if stop_moved else -1.0, 3),
                             "breakeven_stop" if stop_moved else "stop")
        if hit_target:
            return j
        stalled = _stall_exit(ctx, j)
        if stalled is not None:
            return stalled
        if reached_trigger and not stop_moved:
            stop_moved = True
    exit_price = float(ctx.close[ctx.end])   # timeout before TP1
    return _full_leg(ctx, "timeout", ctx.end, exit_price,
                     round((exit_price - ctx.entry_price) * ctx.sign / ctx.risk, 3), "timeout")


def _runner_bar_exit(ctx, j, runner_stop, floor):
    """Runner stop first, then TP2; the stop checked is the one set BEFORE bar j."""
    hi, lo = float(ctx.high[j]), float(ctx.low[j])
    if (lo <= runner_stop) if ctx.is_bull else (hi >= runner_stop):
        # v39: "runner_be" means "closed at its initial post-TP1 floor"; the
        # string is deliberately unchanged (~30 files pattern-match it).
        return runner_stop, j, ("runner_be" if runner_stop == floor else "runner_trail")
    tp2 = ctx.plan.tp2
    if tp2 is not None and ((hi >= tp2) if ctx.is_bull else (lo <= tp2)):
        return tp2, j, "runner_tp2"
    return None


def _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series) -> float:
    """Ratchet for the NEXT bar from THIS bar's close only -- no intrabar lookahead."""
    atr_val = _safe_atr_value(ctx.entry_price, float(atr_series.iloc[j]))
    runner_r = (extreme_close - ctx.entry_price) * ctx.sign / ctx.risk
    mult = _effective_trail_mult(ctx.plan.trail_atr_mult, runner_r)
    trail = chandelier_stop(extreme_close, atr_val, mult, ctx.plan.direction)
    return max(runner_stop, trail) if ctx.is_bull else min(runner_stop, trail)


def _runner_timeout(ctx, checked_stop) -> float:
    """Clamp to the level actually checked against the last bar walked."""
    exit_px = float(ctx.close[ctx.end])
    return max(exit_px, checked_stop) if ctx.is_bull else min(exit_px, checked_stop)


def _runner_phase(df, ctx, tp1_index):
    """Phase 2: (exit price, exit index, runner reason) for the post-TP1 leg."""
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    atr_series = atr_indicator(df, 14)
    for j in range(tp1_index + 1, ctx.end + 1):
        checked_stop = runner_stop
        hit = _runner_bar_exit(ctx, j, runner_stop, floor)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout"


def _runner_result(ctx, runner) -> ExitResult:
    runner_exit, exit_index, reason = runner
    plan = ctx.plan
    rr = abs(plan.tp1 - ctx.entry_price) / ctx.risk
    frac1 = plan.tp1_fraction
    frac2 = 1.0 - frac1
    leg1 = {"fraction": frac1, "exit_price": plan.tp1, "r": round(rr, 3), "reason": "tp1"}
    r2 = round((runner_exit - ctx.entry_price) * ctx.sign / ctx.risk, 3)
    leg2 = {"fraction": frac2, "exit_price": runner_exit, "r": r2, "reason": reason}
    return ExitResult(outcome="win", runner_outcome=reason, entry_index=ctx.entry_index,
                      exit_index=exit_index, entry_price=ctx.entry_price,
                      r_total=round(frac1 * rr + frac2 * r2, 3), legs=[leg1, leg2])


def _scale_out_exit_walk(df, entry_index: int, entry_price: float, plan: TradePlanV2,
                         max_holding_days: int) -> ExitResult:
    """<existing docstring, unchanged>"""
    risk = abs(entry_price - plan.stop_loss)
    if risk <= 0:
        return _no_trade(entry_index, entry_price)
    is_bull = plan.direction == "bullish"
    ctx = _WalkCtx(df["High"].values, df["Low"].values, df["Close"].values, entry_index,
                   entry_price, plan, is_bull, 1 if is_bull else -1, risk,
                   min(entry_index + max_holding_days, len(df) - 1))
    pre = _pre_tp1_phase(ctx)
    if isinstance(pre, ExitResult):
        return pre
    return _runner_result(ctx, _runner_phase(df, ctx, pre))
```

- [ ] Rerun the witness file, then `tests/planning/test_exit_sim_scaleout.py`, `tests/planning/test_exit_sim_hold_cap.py`, `tests/planning/test_tp2.py` and `tests/backtesting/test_exit_parity.py`. All must pass with the hash unchanged. Run `python -m radon cc -s -n C swingbot/core/planning/exit_sim.py`: no block from `_scale_out_exit_walk` or its helpers at 15 or above. `_single_leg_exit_walk` stays at 16, untouched. Commit `exit_sim.py` only: `refactor(v123): split _scale_out_exit_walk into phase helpers (byte-identical witness)`.

### Task V123-4: The pure structure rules

**Files:** Modify `swingbot/core/planning/exit_sim.py`. Create `tests/planning/test_runner_structure_rules.py`.

**Interfaces:**
- Consumes: V123-1's frame columns and `PIVOT_K`.
- Produces:
  - `STALL_VOLUME_MAX = 1.0`.
  - `structural_runner_stop(pivots_row, atr_value, b, direction, entry_index) -> float | None`.
  - `prev_post_entry_pivot(pivots_row, direction, entry_index) -> float | None`.
  - `progress_stall_fires(pivots_row, prev_post_entry_sh, features_row, c, direction, entry_index, j) -> bool`.
  - `runner_structure_step(frame, j, *, entry_index, direction, runner_stop, atr_value) -> tuple[float, bool]`, which reads `config.RUNNER_STRUCTURE_EXIT`/`RUNNER_HL_TRAIL_ATR_BUFFER`/`RUNNER_STALL_RANGE_MAX` and returns `(runner stop for bar j+1, stall fired at j)`.

- [ ] **Write the failing tests.** Rows are plain `pd.Series`, so the rules are tested without v121's math.

```python
# tests/planning/test_runner_structure_rules.py
import math

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import (prev_post_entry_pivot, progress_stall_fires,
                                             runner_structure_step, structural_runner_stop)

NAN = math.nan


def _row(**kw):
    base = dict(sh_i=NAN, sh_px=NAN, sh_prev_i=NAN, sh_prev_px=NAN, sl_i=NAN, sl_px=NAN,
                sl_prev_i=NAN, sl_prev_px=NAN, range_trend_10_50=0.5, vol_trend_10_50=0.8)
    base.update(kw)
    return pd.Series(base, dtype=float)


def test_hl_candidate_is_post_entry_swing_low_minus_buffer():
    row = _row(sl_i=12, sl_px=104.0)
    assert structural_runner_stop(row, 2.0, 0.25, "bullish", entry_index=10) == pytest.approx(103.5)


def test_pre_entry_or_missing_pivot_gives_no_stop():
    assert structural_runner_stop(_row(sl_i=10, sl_px=104.0), 2.0, 0.0, "bullish", 10) is None
    assert structural_runner_stop(_row(), 2.0, 0.0, "bullish", 10) is None


def test_bearish_mirror_uses_swing_high_plus_buffer():
    row = _row(sh_i=15, sh_px=96.0)
    assert structural_runner_stop(row, 2.0, 0.5, "bearish", 10) == pytest.approx(97.0)


def _stall(**kw):
    return _row(sh_i=17, sh_px=110.0, sh_prev_i=12, sh_prev_px=111.0, **kw)


def test_stall_fires_only_with_all_four():
    j = 20
    assert progress_stall_fires(_stall(), 111.0, _stall(), 0.7, "bullish", 10, j)
    assert not progress_stall_fires(_stall(), 111.0, _stall(), 0.7, "bullish", 10, j + 1)  # not new
    assert not progress_stall_fires(_stall(), 109.0, _stall(), 0.7, "bullish", 10, j)      # HH held
    hot = _stall(range_trend_10_50=0.9)
    assert not progress_stall_fires(hot, 111.0, hot, 0.7, "bullish", 10, j)                # range
    loud = _stall(vol_trend_10_50=1.2)
    assert not progress_stall_fires(loud, 111.0, loud, 1.0, "bullish", 10, j)              # volume


def test_stall_ignores_nan_ratios_and_missing_prior():
    short = _stall(range_trend_10_50=NAN)
    assert not progress_stall_fires(short, 111.0, short, 1.0, "bullish", 10, 20)
    assert not progress_stall_fires(_stall(), None, _stall(), 1.0, "bullish", 10, 20)


def test_prior_pivot_must_be_post_entry():
    assert prev_post_entry_pivot(_stall(), "bullish", 10) == 111.0
    assert prev_post_entry_pivot(_stall(), "bullish", 12) is None
    bear = _row(sl_i=17, sl_px=90.0, sl_prev_i=13, sl_prev_px=89.0)
    assert prev_post_entry_pivot(bear, "bearish", 10) == 89.0
    assert progress_stall_fires(bear, 89.0, bear, 0.7, "bearish", 10, 20)   # LL failed: 90 >= 89


def test_step_never_loosens_and_off_is_inert(monkeypatch):
    frame = pd.DataFrame([_row(sl_i=12, sl_px=104.0)])
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", 0.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "hl_trail")
    kw = dict(entry_index=10, direction="bullish", atr_value=2.0)
    assert runner_structure_step(frame, 0, runner_stop=103.0, **kw) == (104.0, False)
    assert runner_structure_step(frame, 0, runner_stop=105.0, **kw) == (105.0, False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    assert runner_structure_step(frame, 0, runner_stop=103.0, **kw) == (103.0, False)
```

- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_runner_structure_rules.py`. Expect an import failure.
- [ ] **Implement** in `exit_sim.py` after `runner_floor`.

```python
STALL_VOLUME_MAX = 1.0   # v123 frozen: volume ratio ceiling, not gridded


def _post_entry(index, entry_index) -> bool:
    return index == index and index > entry_index        # NaN-safe


def _at_most(value, ceiling) -> bool:
    return value == value and value <= ceiling           # NaN never passes


def _pivot_cols(direction: str, swing: str) -> tuple[str, str, str, str]:
    """(last idx, last px, prior idx, prior px) for 'trail' (the protective
    swing) or 'progress' (the swing that should extend)."""
    bull_low = (direction == "bullish") == (swing == "trail")
    p = "sl" if bull_low else "sh"
    return f"{p}_i", f"{p}_px", f"{p}_prev_i", f"{p}_prev_px"


def structural_runner_stop(pivots_row, atr_value, b, direction, entry_index):
    """v123 hl_trail candidate: the latest confirmed post-entry swing low
    minus b x ATR (bearish: swing high plus). None without such a pivot.
    Row j holds only pivots confirmed by j (index <= j - PIVOT_K)."""
    idx, px, _, _ = _pivot_cols(direction, "trail")
    if not _post_entry(pivots_row[idx], entry_index):
        return None
    sign = -1 if direction == "bullish" else 1
    return float(pivots_row[px]) + sign * b * atr_value


def prev_post_entry_pivot(pivots_row, direction, entry_index):
    """The prior confirmed post-entry swing high (bearish: low), or None."""
    _, _, prev_idx, prev_px = _pivot_cols(direction, "progress")
    if not _post_entry(pivots_row[prev_idx], entry_index):
        return None
    return float(pivots_row[prev_px])


def progress_stall_fires(pivots_row, prev_post_entry_sh, features_row, c, direction,
                         entry_index, j) -> bool:
    """v123 progress_stall at bar j: a post-entry swing high confirmed AT j
    that fails to exceed the prior one, with range and volume both cooling."""
    idx, px, _, _ = _pivot_cols(direction, "progress")
    new_pivot = pivots_row[idx]
    if not (_post_entry(new_pivot, entry_index) and int(new_pivot) == j - PIVOT_K):
        return False
    if prev_post_entry_sh is None:
        return False
    high = float(pivots_row[px])
    failed = high <= prev_post_entry_sh if direction == "bullish" else high >= prev_post_entry_sh
    return bool(failed and _at_most(features_row["range_trend_10_50"], c)
                and _at_most(features_row["vol_trend_10_50"], STALL_VOLUME_MAX))


def runner_structure_step(frame, j, *, entry_index, direction, runner_stop, atr_value):
    """One completed runner bar under RUNNER_STRUCTURE_EXIT, shared by the
    replay walk and plan_manager: (stop for bar j+1, stall fired at j)."""
    mode, row = config.RUNNER_STRUCTURE_EXIT, frame.iloc[j]
    if mode == "hl_trail":
        cand = structural_runner_stop(row, atr_value, config.RUNNER_HL_TRAIL_ATR_BUFFER,
                                      direction, entry_index)
        if cand is None:
            return runner_stop, False
        return (max(runner_stop, cand) if direction == "bullish" else min(runner_stop, cand)), False
    if mode == "progress_stall":
        prev = prev_post_entry_pivot(row, direction, entry_index)
        return runner_stop, progress_stall_fires(row, prev, row, config.RUNNER_STALL_RANGE_MAX,
                                                 direction, entry_index, j)
    return runner_stop, False
```

- [ ] Rerun the narrow file and expect PASS. Invoke `no-lookahead` on the five new functions: each reads row `j` only, and row `j` holds pivots `≤ j − 3`. Run radon: all under 15. Commit `exit_sim.py` and the test: `feat(v123): pure hl_trail / progress_stall rules`.

### Task V123-5: Wire the rules into the runner phase

**Files:** Modify `swingbot/core/planning/exit_sim.py`. Create `tests/planning/test_exit_sim_runner_structure.py`.

**Interfaces:**
- Consumes: `runner_structure_frame`, `runner_structure_step` and V123-2's knobs.
- Produces: `_scale_out_exit_walk(df, entry_index, entry_price, plan, max_holding_days, *, trace=None)`. `trace` is an optional list that receives `(j, stop for bar j+1)` after each walked runner bar. `_WalkCtx.open_`. Runner reason `runner_progress_stall`, exiting at `Open[j+1]` with exit index `j+1`.

- [ ] **Write the failing tests.** Fixture plan: market entry at bar `WARMUP − 1` (close 100), stop 95, tp1 101 (TP1 on bar 60), `trail_atr_mult=50` so the chandelier never binds, and horizon `2m`.

```python
# tests/planning/test_exit_sim_runner_structure.py
import pytest

from swingbot import config
from swingbot.core.market.indicators import atr
from swingbot.core.planning.exit_sim import _scale_out_exit_walk, runner_structure_frame
from swingbot.core.planning.plan_engine import simulate_exit
from tests.planning.structure_fixtures import WARMUP, sawtooth, sawtooth_closes, stall_frame
from tests.planning.test_exit_sim_scaleout_witness import FIXTURE, witness_hash, witness_rows
from tests.planning.test_exit_sim_single import _plan

E = WARMUP - 1


def _runner_plan(**kw):
    return _plan(stop_loss=95.0, tp1=101.0, tp2=None, trail_atr_mult=50.0, horizon_key="2m", **kw)


def _mode(monkeypatch, mode, b=0.0, c=1.0):
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", mode)
    monkeypatch.setattr(config, "RUNNER_HL_TRAIL_ATR_BUFFER", b)
    monkeypatch.setattr(config, "RUNNER_STALL_RANGE_MAX", c)


def test_off_is_byte_identical(monkeypatch):
    _mode(monkeypatch, "off")
    assert witness_hash() == FIXTURE.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize("mode", ["hl_trail", "progress_stall"])
def test_no_outcome_flips(monkeypatch, mode):
    _mode(monkeypatch, "off")
    base = [row[4]["outcome"] for row in witness_rows()]
    _mode(monkeypatch, mode)
    assert [row[4]["outcome"] for row in witness_rows()] == base


def test_hl_stop_moves_only_from_the_bar_after_confirmation(monkeypatch):
    _mode(monkeypatch, "hl_trail", b=0.25)
    df = sawtooth(4)
    frame, atr14, trace = runner_structure_frame(df), atr(df, 14), []
    _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60, trace=trace)
    stops = dict(trace)
    confirm = WARMUP + 6 + 3                         # first post-entry swing low confirms here
    assert stops[confirm - 1] == pytest.approx(100.0 + 2 / 3 * 1.0)   # still the runner floor
    expected = frame["sl_px"].iloc[confirm] - 0.25 * float(atr14.iloc[confirm])
    assert stops[confirm] == pytest.approx(max(stops[confirm - 1], expected))
    assert all(b >= a for a, b in zip([s for _, s in trace], [s for _, s in trace][1:]))


def test_hl_stop_is_hit_on_a_drop_through_the_swing_low(monkeypatch):
    closes = sawtooth_closes(4)
    df = sawtooth(4, tail=(closes[-1] - 2.0,))
    _mode(monkeypatch, "off")
    base = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    _mode(monkeypatch, "hl_trail")
    arm = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert base.runner_outcome == "runner_timeout"
    assert arm.runner_outcome == "runner_trail" and arm.exit_index == len(df) - 1
    assert arm.outcome == base.outcome == "win"


def _stall_j(df):
    frame = runner_structure_frame(df)
    hits = [j for j in range(E + 1, len(df)) if frame["sh_i"].iloc[j] == j - 3
            and frame["sh_px"].iloc[j] <= frame["sh_prev_px"].iloc[j]]
    assert hits, "fixture must print a failed higher high"
    j = hits[0]
    assert frame["range_trend_10_50"].iloc[j] <= 0.70 and frame["vol_trend_10_50"].iloc[j] <= 1.0
    return j


def test_stall_exits_at_next_open(monkeypatch):
    df = stall_frame()
    j = _stall_j(df)
    _mode(monkeypatch, "progress_stall", c=0.70)
    res = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert res.runner_outcome == "runner_progress_stall"
    assert res.exit_index == j + 1
    assert res.legs[1]["exit_price"] == pytest.approx(float(df["Open"].iloc[j + 1]))


def test_stall_exit_takes_a_gapped_open_below_the_stop(monkeypatch):
    df = stall_frame()
    j = _stall_j(df)
    df.iloc[j + 1, df.columns.get_loc("Open")] = 99.0          # below the 100.667 floor
    _mode(monkeypatch, "progress_stall")
    res = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), 60)
    assert res.exit_index == j + 1 and res.legs[1]["exit_price"] == pytest.approx(99.0)


def test_stall_on_the_last_walked_bar_defers_to_timeout(monkeypatch):
    df = stall_frame()
    j = _stall_j(df)
    _mode(monkeypatch, "progress_stall")
    capped = _scale_out_exit_walk(df, E, 100.0, _runner_plan(), j - E)      # end == j
    assert capped.runner_outcome == "runner_timeout" and capped.exit_index == j
    final = _scale_out_exit_walk(df.iloc[:j + 1], E, 100.0, _runner_plan(), 60)   # j == n-1
    assert final.runner_outcome == "runner_timeout"


def test_never_acts_before_tp1(monkeypatch):
    df = stall_frame()
    far = _plan(stop_loss=95.0, tp1=500.0, tp2=None, horizon_key="2m")
    _mode(monkeypatch, "off")
    base = simulate_exit(df, E, far, scale_out=True)
    _mode(monkeypatch, "progress_stall")
    assert simulate_exit(df, E, far, scale_out=True) == base
```

- [ ] Run `python scripts/dev/testrun.py file tests/planning/test_exit_sim_runner_structure.py`. Expect failures (no `trace` kwarg, no stall).
- [ ] **Implement.** Add `open_: object` as the last `_WalkCtx` field. In `_scale_out_exit_walk`, pass `df["Open"].values` and accept `*, trace=None`, then call `_runner_phase(df, ctx, pre, trace)`. Replace `_runner_phase`:

```python
def _runner_phase(df, ctx, tp1_index, trace=None):
    """Phase 2: (exit price, exit index, runner reason) for the post-TP1 leg.
    v123: a structure rule (RUNNER_STRUCTURE_EXIT) updates after the chandelier,
    from this bar's close, effective next bar; a stall exits at the next open."""
    from swingbot.core.market.indicators import atr as atr_indicator
    floor = runner_floor(ctx.entry_price, ctx.plan.tp1)
    runner_stop = checked_stop = floor
    extreme_close = float(ctx.close[tp1_index])
    atr_series = atr_indicator(df, 14)
    frame = runner_structure_frame(df) if config.RUNNER_STRUCTURE_EXIT != "off" else None
    stall_pending = False
    for j in range(tp1_index + 1, ctx.end + 1):
        if stall_pending:                            # the open comes first
            return float(ctx.open_[j]), j, "runner_progress_stall"
        checked_stop = runner_stop
        hit = _runner_bar_exit(ctx, j, runner_stop, floor)
        if hit is not None:
            return hit
        c = float(ctx.close[j])
        extreme_close = max(extreme_close, c) if ctx.is_bull else min(extreme_close, c)
        runner_stop = _chandelier_ratchet(ctx, j, extreme_close, runner_stop, atr_series)
        if frame is not None:
            runner_stop, stall_pending = _structure_update(ctx, frame, j, runner_stop, atr_series)
        if trace is not None:
            trace.append((j, runner_stop))
    return _runner_timeout(ctx, checked_stop), ctx.end, "runner_timeout"


def _structure_update(ctx, frame, j, runner_stop, atr_series):
    """runner_structure_step for bar j; a stall on the last walked bar is dropped
    so the timeout handles it (no bar j+1 inside the holding window)."""
    atr_val = _safe_atr_value(ctx.entry_price, float(atr_series.iloc[j]))
    stop, fires = runner_structure_step(frame, j, entry_index=ctx.entry_index,
                                        direction=ctx.plan.direction,
                                        runner_stop=runner_stop, atr_value=atr_val)
    return stop, fires and j < ctx.end
```

Note that `simulate_exit`'s `_walk_for(...)(df, ...)` call is unchanged: `trace` defaults to None. Update the `ExitResult.runner_outcome` comment to list `"runner_progress_stall"`.

- [ ] Rerun the narrow file plus the witness file, `tests/planning/test_exit_sim_scaleout.py` and `tests/backtesting/test_exit_parity.py`. Expect PASS. Invoke `no-lookahead` on `_runner_phase` and `_structure_update`: the frame row `j` is read after bar `j`'s checks, and nothing at `j+1` is read except the stall's open. Run radon on `exit_sim.py`: all new or changed blocks under 15. Commit: `feat(v123): runner phase honours RUNNER_STRUCTURE_EXIT`.
