# Strategy path goes live — Part 4: Phase 3 (bearish-arm re-derivation) and final verification

Index, header block, global constraints and the parallelisation map: `2026-09-17-v93-strategy-path-live_0-index.md`. Spec: `docs/superpowers/specs/2026-09-17-v93-strategy-path-live-design.md` (§4).

**Sequential throughout; depends on Phase 2** (Task 24 reads `rs_combined` from Task 18's as-of builder). **No VALIDATION shot is spent in this phase.**

# Phase 3 — Bearish-arm re-derivation

### Task 22: `horizons_by_direction` in the gate schema; `gate_override` context manager

**Files:**
- Modify: `swingbot/core/market/entry_filters.py` (`entries_for` ~L126–166; new `gate_override`)
- Modify: `swingbot/core/market/strategy_types.py` (comment block above `STRATEGY_GATES`: document the new optional key)
- Test: `tests/market/test_entry_filters_gates_v93.py`

**Interfaces:**
- Produces: `STRATEGY_GATES[name]` may carry `"horizons_by_direction": {"bearish": (...), "bullish": (...)}` — a per-direction horizon list that overrides `"horizons"` for that direction only; `entry_filters.gate_override(strategy: str, gates: dict | None)` context manager that temporarily replaces (or removes, with `None`) one strategy's gate entry in place and restores it on exit.

- [ ] **Step 1: Write the failing tests**

`tests/market/test_entry_filters_gates_v93.py`:

```python
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import STRATEGY_GATES
from tests.helpers import make_ohlcv


@pytest.fixture
def frame(monkeypatch):
    df = make_ohlcv([100.0] * 300, start="2025-01-02")
    on = pd.Series(True, index=df.index)
    monkeypatch.setitem(ef.ENTRY_FUNCS, "Fake", lambda d, hk, params=None: (on.copy(), on.copy()))
    monkeypatch.setattr(ef, "apply_regime_gate", lambda bull, bear, strategy, regimes: (bull, bear))
    return df


def test_horizons_by_direction_overrides_only_that_direction(frame, monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish", "bearish"), "horizons": ("2m",),
                                                  "horizons_by_direction": {"bearish": ("4w", "2m")}})
    bull, bear = ef.entries_for("Fake", frame, "4w", regimes=pd.Series("x", index=frame.index))
    assert not bull.any() and bear.all()          # bullish keeps "horizons"=(2m,), bearish uses its own list
    bull, bear = ef.entries_for("Fake", frame, "2m", regimes=pd.Series("x", index=frame.index))
    assert bull.all() and bear.all()
    bull, bear = ef.entries_for("Fake", frame, "9m", regimes=pd.Series("x", index=frame.index))
    assert not bull.any() and not bear.any()


def test_directions_mask_still_applies(frame, monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish",)})
    bull, bear = ef.entries_for("Fake", frame, "4w", regimes=pd.Series("x", index=frame.index))
    assert bull.all() and not bear.any()


def test_gate_override_restores_on_exit(monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish",)})
    with ef.gate_override("Fake", {"directions": ("bullish", "bearish")}):
        assert STRATEGY_GATES["Fake"] == {"directions": ("bullish", "bearish")}
    assert STRATEGY_GATES["Fake"] == {"directions": ("bullish",)}
    with ef.gate_override("Fake", None):
        assert "Fake" not in STRATEGY_GATES
    assert STRATEGY_GATES["Fake"] == {"directions": ("bullish",)}


def test_gate_override_restores_after_exception(monkeypatch):
    monkeypatch.setitem(STRATEGY_GATES, "Fake", {"directions": ("bullish",)})
    with pytest.raises(RuntimeError):
        with ef.gate_override("Fake", {}):
            raise RuntimeError("boom")
    assert STRATEGY_GATES["Fake"] == {"directions": ("bullish",)}


def test_existing_call_sites_unchanged():
    """The 11 detectors in signals.py call entries_for(strategy, df, hk) positionally."""
    import inspect
    sig = inspect.signature(ef.entries_for)
    assert list(sig.parameters)[:3] == ["strategy", "df", "horizon_key"]
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/market/test_entry_filters_gates_v93.py -v`
Expected: FAIL (`AttributeError: gate_override`; the by-direction test fails on the 4w bearish assertion)

- [ ] **Step 3: Implement**

In `entry_filters.py`, replace the gate block inside `entries_for`:

```python
    gates = STRATEGY_GATES.get(strategy)
    if gates:
        by_dir = gates.get("horizons_by_direction") or {}
        horizons = gates.get("horizons")
        directions = gates.get("directions")

        def _allowed(direction: str) -> bool:
            if directions is not None and direction not in directions:
                return False
            hz = by_dir.get(direction, horizons)
            return hz is None or horizon_key in hz

        if not _allowed("bullish"):
            bullish = _off(df)
        if not _allowed("bearish"):
            bearish = _off(df)
```

and add at module level:

```python
import contextlib


@contextlib.contextmanager
def gate_override(strategy: str, gates: dict | None):
    """Temporarily replace one strategy's STRATEGY_GATES entry in place
    (`None` removes it) and restore it afterwards, whatever happens. The
    dict object is shared with strategy_types, so in-place mutation is what
    every reader sees -- the same reason backtest_wf._apply_overrides
    mutates `config` rather than copying it."""
    missing = object()
    old = STRATEGY_GATES.get(strategy, missing)
    try:
        if gates is None:
            STRATEGY_GATES.pop(strategy, None)
        else:
            STRATEGY_GATES[strategy] = gates
        yield
    finally:
        if old is missing:
            STRATEGY_GATES.pop(strategy, None)
        else:
            STRATEGY_GATES[strategy] = old
```

In `strategy_types.py`, extend the comment above `STRATEGY_GATES`:
```python
# Optional key (v93): "horizons_by_direction": {"bearish": (...)} -- a
# per-direction horizon list that overrides "horizons" for that direction
# only. Used when a bearish arm clears the badge floor on a different horizon
# subset than the bullish arm (docs/superpowers/results/<date>-v93-bearish-arms-train.md).
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters_gates_v93.py` and `... tests/market/test_entry_filters.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/market/entry_filters.py swingbot/core/market/strategy_types.py tests/market/test_entry_filters_gates_v93.py
git commit -m "feat(v93): horizons_by_direction gate key + gate_override context manager"
```

---

### Task 23: `backtesting/arm_rule.py` — the pre-registered decision clauses

**Files:**
- Create: `swingbot/core/backtesting/arm_rule.py`
- Test: `tests/backtesting/test_arm_rule.py`

**Interfaces:**
- Produces:
  - `pooled_stats(trades) -> dict` (`n, wins, losses, win_rate, expectancy_r, scratch_timeout_share`) over `BacktestTrade`-like objects (attributes `outcome`, `r_multiple`).
  - `stage1_verdict(pooled: dict, folds: list[dict]) -> dict` — `folds` items are `{"test_year": str, "stats": pooled_stats(...)}`; returns `{"clears": bool, "clauses": {...}}` with clauses `wr, exp_r, n, scratch_share, folds`.
  - `stage2_allowed(pooled: dict) -> bool` — `ExpR > 0` and `WR < 50`.
  - `neighbour_subsets(subset: tuple, all_horizons: tuple) -> list[tuple]` and `plateau_ok(subset_stats: dict, neighbour_stats: list[dict]) -> bool`.
  - Constants `WR_FLOOR=50.0, MIN_N=30, MAX_SCRATCH_SHARE=0.5, FOLD_MIN_N=15, FOLDS_REQUIRED=2, PLATEAU_MIN_NEIGHBOURS=4`.

- [ ] **Step 1: Write the failing tests**

`tests/backtesting/test_arm_rule.py`:

```python
from types import SimpleNamespace as T

from swingbot.core.backtesting import arm_rule as ar
from swingbot.core.market.strategy_types import HORIZONS


def _trades(wins, losses, scratches=0, timeouts=0, win_r=1.0, loss_r=-1.0):
    return ([T(outcome="win", r_multiple=win_r)] * wins + [T(outcome="loss", r_multiple=loss_r)] * losses
            + [T(outcome="scratch", r_multiple=0.0)] * scratches + [T(outcome="timeout", r_multiple=0.05)] * timeouts)


def test_pooled_stats():
    s = ar.pooled_stats(_trades(6, 4, scratches=2))
    assert s["n"] == 10 and s["wins"] == 6 and s["losses"] == 4
    assert s["win_rate"] == 60.0
    assert s["expectancy_r"] == (6 * 1.0 + 4 * -1.0 + 0.0 * 2) / 12
    assert s["scratch_timeout_share"] == 2 / 12


def test_pooled_stats_empty():
    s = ar.pooled_stats([])
    assert s == {"n": 0, "wins": 0, "losses": 0, "win_rate": None, "expectancy_r": None, "scratch_timeout_share": None}


def _folds(*ns, exp=0.2):
    return [{"test_year": str(2021 + i), "stats": {"n": n, "expectancy_r": exp}} for i, n in enumerate(ns)]


def test_stage1_clears_when_every_clause_holds():
    pooled = ar.pooled_stats(_trades(18, 14))
    v = ar.stage1_verdict(pooled, _folds(16, 15, 9))
    assert v["clauses"] == {"wr": True, "exp_r": True, "n": True, "scratch_share": True, "folds": True}
    assert v["clears"] is True


def test_stage1_each_clause_can_fail_alone():
    ok = ar.pooled_stats(_trades(18, 14))
    assert ar.stage1_verdict({**ok, "win_rate": 49.9}, _folds(16, 15, 15))["clauses"]["wr"] is False
    assert ar.stage1_verdict({**ok, "expectancy_r": 0.0}, _folds(16, 15, 15))["clauses"]["exp_r"] is False
    assert ar.stage1_verdict({**ok, "n": 29}, _folds(16, 15, 15))["clauses"]["n"] is False
    assert ar.stage1_verdict({**ok, "scratch_timeout_share": 0.51}, _folds(16, 15, 15))["clauses"]["scratch_share"] is False
    assert ar.stage1_verdict(ok, _folds(16, 14, 14))["clauses"]["folds"] is False           # only 1 fold with N>=15
    assert ar.stage1_verdict(ok, _folds(16, 15, 15, exp=-0.01))["clauses"]["folds"] is False


def test_stage2_allowed_only_on_wr_alone_failure():
    assert ar.stage2_allowed({"win_rate": 46.0, "expectancy_r": 0.3, "n": 40}) is True
    assert ar.stage2_allowed({"win_rate": 46.0, "expectancy_r": -0.1, "n": 40}) is False
    assert ar.stage2_allowed({"win_rate": 52.0, "expectancy_r": 0.3, "n": 40}) is False
    assert ar.stage2_allowed({"win_rate": None, "expectancy_r": None, "n": 0}) is False


def test_neighbour_subsets_drop_one_and_extend_adjacent():
    hz = tuple(HORIZONS)                      # 2w,4w,2m,3m,4m,5m,6m,7m,8m,9m
    nb = ar.neighbour_subsets(("2m", "3m", "4m"), hz)
    assert ("3m", "4m") in nb and ("2m", "4m") in nb and ("2m", "3m") in nb
    assert ("4w", "2m", "3m", "4m") in nb and ("2m", "3m", "4m", "5m") in nb
    assert len(nb) == 5


def test_plateau_requires_min_neighbours_all_clearing():
    good = {"win_rate": 53.0, "n": 40}
    assert ar.plateau_ok(good, [good] * 4) is True
    assert ar.plateau_ok(good, [good] * 3) is False
    assert ar.plateau_ok(good, [good] * 3 + [{"win_rate": 49.0, "n": 40}]) is False
    assert ar.plateau_ok(good, [good] * 3 + [{"win_rate": 55.0, "n": 29}]) is False
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/backtesting/test_arm_rule.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

`swingbot/core/backtesting/arm_rule.py`:

```python
"""v93 Phase 3: the pre-registered bearish-arm decision rule (spec §4).

Fixed BEFORE the measurement ran. Badge floor per backtest-methodology.md
(`win_rate >= 50`, `expectancy_r > 0`, `N >= 30` on TRAIN) plus the range
script's scratch/timeout share rule and v84's fold-stability clause. Pure
functions; the measurement script only feeds them numbers.
"""
from __future__ import annotations

WR_FLOOR = 50.0
MIN_N = 30
MAX_SCRATCH_SHARE = 0.5
FOLD_MIN_N = 15
FOLDS_REQUIRED = 2
PLATEAU_MIN_NEIGHBOURS = 4

DECIDED = ("win", "loss")
CLOSED = ("win", "loss", "scratch", "timeout")


def pooled_stats(trades) -> dict:
    closed = [t for t in trades if t.outcome in CLOSED]
    decided = [t for t in closed if t.outcome in DECIDED]
    wins = sum(1 for t in decided if t.outcome == "win")
    losses = len(decided) - wins
    rs = [t.r_multiple for t in closed if t.r_multiple is not None]
    return {
        "n": len(decided), "wins": wins, "losses": losses,
        "win_rate": (wins / len(decided) * 100.0) if decided else None,
        "expectancy_r": (sum(rs) / len(rs)) if rs else None,
        "scratch_timeout_share": ((len(closed) - len(decided)) / len(closed)) if closed else None,
    }


def stage1_verdict(pooled: dict, folds: list) -> dict:
    good_folds = sum(1 for f in folds
                     if (f["stats"].get("n") or 0) >= FOLD_MIN_N
                     and (f["stats"].get("expectancy_r") is not None and f["stats"]["expectancy_r"] > 0))
    clauses = {
        "wr": pooled["win_rate"] is not None and pooled["win_rate"] >= WR_FLOOR,
        "exp_r": pooled["expectancy_r"] is not None and pooled["expectancy_r"] > 0,
        "n": pooled["n"] >= MIN_N,
        "scratch_share": pooled["scratch_timeout_share"] is not None and pooled["scratch_timeout_share"] <= MAX_SCRATCH_SHARE,
        "folds": good_folds >= FOLDS_REQUIRED,
    }
    return {"clears": all(clauses.values()), "clauses": clauses, "good_folds": good_folds}


def stage2_allowed(pooled: dict) -> bool:
    """Only when Stage 1 failed on win rate ALONE with positive expectancy."""
    return (pooled.get("expectancy_r") is not None and pooled["expectancy_r"] > 0
            and pooled.get("win_rate") is not None and pooled["win_rate"] < WR_FLOOR)


def neighbour_subsets(subset: tuple, all_horizons: tuple) -> list:
    """Drop-one subsets plus extend-by-one on either side (contiguous in
    the horizon order). The plateau check runs over these."""
    order = list(all_horizons)
    idx = sorted(order.index(h) for h in subset)
    out = []
    if len(idx) > 1:
        for i in idx:
            out.append(tuple(order[j] for j in idx if j != i))
    if idx[0] > 0:
        out.append(tuple(order[j] for j in [idx[0] - 1] + idx))
    if idx[-1] < len(order) - 1:
        out.append(tuple(order[j] for j in idx + [idx[-1] + 1]))
    return out


def plateau_ok(subset_stats: dict, neighbour_stats: list) -> bool:
    if len(neighbour_stats) < PLATEAU_MIN_NEIGHBOURS:
        return False
    return all(s.get("win_rate") is not None and s["win_rate"] >= WR_FLOOR and (s.get("n") or 0) >= MIN_N
               for s in neighbour_stats)
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/backtesting/test_arm_rule.py`
Expected: green.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/backtesting/arm_rule.py tests/backtesting/test_arm_rule.py
git commit -m "feat(v93): arm_rule -- pre-registered bearish-arm decision clauses"
```

---

### Task 24: `scripts/backtest/measure_bearish_arms.py`

**Files:**
- Create: `scripts/backtest/measure_bearish_arms.py`
- Test: `tests/scripts/test_measure_bearish_arms.py`

**Interfaces:**
- Consumes: `run_backtest_range.load_cached`, `_with_context`, `_tickers_for_run`, `_build_asof_map` (Task 21), `liquidity_reason`, `data_quality_issues`; `entry_filters.gate_override` (Task 22); `backtest.run_backtest(..., asof=)`; `backtest_wf.ANCHORED_FOLDS`; `rs_gate.rs_verdict`; `arm_rule.*` (Task 23); `STRATEGY_GATES`.
- Produces: CLI `python scripts/backtest/measure_bearish_arms.py --strategy "MACD" --out data/v93_arms_macd.json [--universe NAME] [--tickers A,B,C]`; module functions `bearish_arm_trades(strategy, frames, asof_map, *, date_from, date_to, horizons) -> list[dict]` (rows `ticker, horizon_key, trade`), `apply_laggard_rule(rows) -> list[dict]`, `evaluate(strategy, rows_train, rows_by_fold, horizons_mask) -> dict`.

- [ ] **Step 1: Write the failing test (dry-run on a three-ticker fixture)**

`tests/scripts/test_measure_bearish_arms.py`:

```python
import sys
from pathlib import Path
from types import SimpleNamespace as T

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

from tests.helpers import make_ohlcv


def _frames():
    rng = np.random.RandomState(11)
    out = {}
    for sym in ("AAA", "BBB", "CCC"):
        closes = 100 * np.cumprod(1 + rng.normal(0.0, 0.012, 1200))
        out[sym] = make_ohlcv(list(closes), start="2019-01-02")
    return out


def test_apply_laggard_rule_keeps_blocks_out():
    import measure_bearish_arms as mba
    rows = [
        {"ticker": "AAA", "horizon_key": "3m", "trade": T(outcome="win", r_multiple=1.0, direction="bearish",
                                                          context={"rs_combined": 10.0})},
        {"ticker": "BBB", "horizon_key": "3m", "trade": T(outcome="loss", r_multiple=-1.0, direction="bearish",
                                                          context={"rs_combined": 80.0})},
        {"ticker": "CCC", "horizon_key": "3m", "trade": T(outcome="win", r_multiple=1.0, direction="bearish",
                                                          context={"rs_combined": None})},
    ]
    kept = mba.apply_laggard_rule(rows)
    assert [r["ticker"] for r in kept] == ["AAA", "CCC"]      # 80th pct leader blocked; None -> exempt (never counted as pass)


def test_bearish_arm_trades_only_bearish_and_unmasked(monkeypatch):
    import measure_bearish_arms as mba
    import swingbot.core.backtesting.backtest as bt
    from swingbot.core.market.strategy_types import STRATEGY_GATES
    frames = _frames()

    def fake_run(ticker, df, strategy, hk, **kw):
        assert kw["asof"] is None or isinstance(kw["asof"], pd.DataFrame)
        # the mask must have been lifted for bearish while this runs
        assert "bearish" in STRATEGY_GATES[strategy]["directions"]
        return T(trades=[T(outcome="win", r_multiple=0.5, direction="bearish", entry_date="2021-06-01", context={}),
                         T(outcome="loss", r_multiple=-1.0, direction="bullish", entry_date="2021-06-02", context={})])
    monkeypatch.setattr(mba, "run_backtest", fake_run)
    monkeypatch.setitem(STRATEGY_GATES, "MACD", {"directions": ("bullish",), "horizons": ("3m",)})
    rows = mba.bearish_arm_trades("MACD", frames, {}, date_from="2020-01-01", date_to="2023-12-31", horizons=("3m", "4m"))
    assert rows and all(r["trade"].direction == "bearish" for r in rows)
    assert STRATEGY_GATES["MACD"] == {"directions": ("bullish",), "horizons": ("3m",)}   # restored


def test_evaluate_shape_and_stage_logic():
    import measure_bearish_arms as mba
    win = lambda: T(outcome="win", r_multiple=1.0)
    loss = lambda: T(outcome="loss", r_multiple=-1.0)
    rows = [{"ticker": "A", "horizon_key": "3m", "trade": t} for t in [win()] * 20 + [loss()] * 15]
    folds = {"2021": rows[:16], "2022": rows[16:32], "2023": rows[32:]}
    out = mba.evaluate("MACD", rows, folds, horizons_mask=("3m", "4m"))
    assert set(out) >= {"strategy", "stage1", "stage2", "decision"}
    assert out["stage1"]["masked"]["pooled"]["n"] == 35
    assert out["decision"] in ("clear_masked", "clear_all", "clear_subset", "fail")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/scripts/test_measure_bearish_arms.py -v`
Expected: FAIL with `ModuleNotFoundError: measure_bearish_arms`

- [ ] **Step 3: Implement**

`scripts/backtest/measure_bearish_arms.py`:

```python
#!/usr/bin/env python3
"""v93 Phase 3: measure ONE strategy's bearish arm on TRAIN under current
arithmetic, with the live RS laggard rule applied, and evaluate it against
the pre-registered decision rule in backtesting/arm_rule.py.

Free, repeatable TRAIN + anchored-fold check. NEVER runs VALIDATION.

Run (dispatch to backtest-runner; prints per-symbol progress):
  python scripts/backtest/measure_bearish_arms.py --strategy "MACD" --out data/v93_arms_macd.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_backtest_range import (  # noqa: E402
    TRAIN, _build_asof_map, _tickers_for_run, _with_context, load_cached, window_trades,
)
from swingbot.core.backtesting import arm_rule  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS  # noqa: E402
from swingbot.core.edge.rs_gate import rs_verdict  # noqa: E402
from swingbot.core.market.entry_filters import gate_override  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_GATES  # noqa: E402
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason  # noqa: E402

ALL_HZ = tuple(HORIZONS)


def _unmasked_gates(strategy: str) -> dict:
    g = dict(STRATEGY_GATES.get(strategy) or {})
    g["directions"] = ("bullish", "bearish")
    g.pop("horizons", None)                 # measure every horizon; the mask is re-applied in evaluate()
    g.pop("horizons_by_direction", None)
    return g


def bearish_arm_trades(strategy, frames, asof_map, *, date_from, date_to, horizons=ALL_HZ) -> list:
    rows = []
    with gate_override(strategy, _unmasked_gates(strategy)):
        for ti, (ticker, df) in enumerate(sorted(frames.items()), 1):
            print(f"[{ti}/{len(frames)}] {ticker}", flush=True)
            for hk in horizons:
                try:
                    s = run_backtest(ticker, df, strategy, hk, one_at_a_time=True, exit_model="v2",
                                     scale_out=True, tp2_mode="levels", frictions=True,
                                     asof=asof_map.get(ticker))
                except Exception as e:
                    print(f"    ! {strategy}/{hk}: {e}", flush=True)
                    continue
                for t in window_trades(s, date_from, date_to):
                    if t.direction == "bearish":
                        rows.append({"ticker": ticker, "horizon_key": hk, "trade": t})
    return rows


def apply_laggard_rule(rows: list) -> list:
    """Same verdict function the live scan applies to bearish plans. A
    missing RS reading is `exempt`, kept, and NEVER counted as a pass."""
    kept = []
    for r in rows:
        ctx = getattr(r["trade"], "context", None) or {}
        rs = ctx.get("rs_combined")
        v = rs_verdict(r["ticker"], "bearish", rs if rs is not None else 50.0, rs_available=rs is not None)
        if v["status"] != "block":
            kept.append(r)
    return kept


def _stats(rows):
    return arm_rule.pooled_stats([r["trade"] for r in rows])


def _fold_stats(rows_by_fold: dict, horizons: tuple | None):
    out = []
    for year, rows in sorted(rows_by_fold.items()):
        sel = rows if horizons is None else [r for r in rows if r["horizon_key"] in horizons]
        out.append({"test_year": year, "stats": _stats(sel)})
    return out


def evaluate(strategy: str, rows_train: list, rows_by_fold: dict, *, horizons_mask: tuple | None) -> dict:
    masked_rows = rows_train if horizons_mask is None else [r for r in rows_train if r["horizon_key"] in horizons_mask]
    s1 = {
        "masked": {"horizons": horizons_mask, "pooled": _stats(masked_rows),
                   "folds": _fold_stats(rows_by_fold, horizons_mask)},
        "all": {"horizons": ALL_HZ, "pooled": _stats(rows_train), "folds": _fold_stats(rows_by_fold, None)},
    }
    for arm in s1.values():
        arm["verdict"] = arm_rule.stage1_verdict(arm["pooled"], arm["folds"])
    decision, chosen = "fail", None
    if horizons_mask is not None and s1["masked"]["verdict"]["clears"]:
        decision, chosen = "clear_masked", horizons_mask
    elif s1["all"]["verdict"]["clears"]:
        decision, chosen = "clear_all", None
    s2 = {"allowed": False, "candidates": []}
    if decision == "fail" and arm_rule.stage2_allowed(s1["all"]["pooled"]):
        s2["allowed"] = True
        per_hz = {hk: _stats([r for r in rows_train if r["horizon_key"] == hk]) for hk in ALL_HZ}
        # contiguous subsets of length 2..5 whose members each have positive expectancy
        for L in range(2, 6):
            for start in range(0, len(ALL_HZ) - L + 1):
                sub = ALL_HZ[start:start + L]
                if not all((per_hz[h]["expectancy_r"] or 0) > 0 for h in sub):
                    continue
                sub_rows = [r for r in rows_train if r["horizon_key"] in sub]
                pooled = _stats(sub_rows)
                v = arm_rule.stage1_verdict(pooled, _fold_stats(rows_by_fold, sub))
                nb = arm_rule.neighbour_subsets(sub, ALL_HZ)
                nb_stats = [_stats([r for r in rows_train if r["horizon_key"] in n]) for n in nb]
                plateau = arm_rule.plateau_ok(pooled, nb_stats)
                s2["candidates"].append({"horizons": sub, "pooled": pooled, "verdict": v, "plateau": plateau})
        ok = [c for c in s2["candidates"] if c["verdict"]["clears"] and c["plateau"]]
        if ok:
            best = max(ok, key=lambda c: c["pooled"]["expectancy_r"])   # pre-registered tiebreak
            decision, chosen = "clear_subset", best["horizons"]
    return {"strategy": strategy, "stage1": s1, "stage2": s2, "decision": decision, "chosen_horizons": chosen,
            "n_bearish_before_rs": None, "n_bearish_after_rs": len(rows_train)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--universe", default=None)
    ap.add_argument("--tickers", default=None, help="comma list; overrides --universe (fixtures/dry runs)")
    args = ap.parse_args()
    t0 = time.monotonic()

    tickers = args.tickers.split(",") if args.tickers else _tickers_for_run(args.universe)
    frames = {}
    for tk in tickers:
        df = _with_context(load_cached(tk))
        if df is None or liquidity_reason(df) is not None or data_quality_issues(df, tk):
            continue
        frames[tk] = df
    asof_map = _build_asof_map(list(frames), frames, args.universe)

    rows_all = bearish_arm_trades(args.strategy, frames, asof_map, date_from=TRAIN[0], date_to=TRAIN[1])
    rows = apply_laggard_rule(rows_all)
    rows_by_fold = {}
    for _a, _b, test_start, test_end in ANCHORED_FOLDS:
        rows_by_fold[test_start[:4]] = [r for r in rows if test_start <= r["trade"].entry_date <= test_end]

    gates = STRATEGY_GATES.get(args.strategy) or {}
    result = evaluate(args.strategy, rows, rows_by_fold, horizons_mask=gates.get("horizons"))
    result["n_bearish_before_rs"] = len(rows_all)
    result["universe_n"] = len(frames)
    result["elapsed_s"] = round(time.monotonic() - t0, 1)
    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    print(f"\n{args.strategy}: decision={result['decision']} chosen={result['chosen_horizons']} "
          f"pooled(all)={result['stage1']['all']['pooled']} -> {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests, then a real dry run**

Run: `python scripts/dev/testrun.py file tests/scripts/test_measure_bearish_arms.py` — green.
Then a cheap end-to-end smoke on three cached tickers (well under 2 minutes; run inline):
```bash
python scripts/backtest/measure_bearish_arms.py --strategy "MACD" --tickers AAPL,MSFT,SPY --out data/v93_arms_smoke.json
```
Expected: exits 0, prints a decision line, writes JSON with `stage1.all.pooled.n` an integer. Delete `data/v93_arms_smoke.json` afterwards.

- [ ] **Step 5: Commit**

```bash
git add scripts/backtest/measure_bearish_arms.py tests/scripts/test_measure_bearish_arms.py
git commit -m "feat(v93): measure_bearish_arms -- TRAIN + folds + laggard rule + pre-registered decision"
```

---

### Task 25: Run the seven measurements; apply the decision rule

**Files:**
- Create: `docs/superpowers/results/<YYYY-MM-DD>-v93-bearish-arms-train.md`
- Modify: `swingbot/core/market/strategy_types.py` (`STRATEGY_GATES` entries + comments) — **only for arms that clear**
- Modify: `swingbot/core/backtesting/validation_registry.json` — **only for WEAK strategies whose arm clears**, via the range script's `--emit-registry`
- Test: `tests/market/test_entry_filters.py` (existing gate tests must still pass), `tests/backtesting/test_registry.py`

**Interfaces:**
- Consumes: Task 24's script and JSON outputs.
- Produces: the results doc; updated masks; TRAIN-window registry rows.

- [ ] **Step 1: Run the seven measurements (dispatch to `backtest-runner`, one strategy per dispatch)**

For each of `Fibonacci`, `RSI`, `MA Ribbon`, `VWAP`, `Support/Resistance`, `MACD`, `Volume Profile`:
```bash
python scripts/backtest/measure_bearish_arms.py --strategy "<name>" --out data/v93_arms_<slug>.json
```
Each run must print flushed per-symbol progress; if any single run exceeds 15 minutes, the runner reports a percent figure from the `[i/N]` lines. Collect the seven JSON files.

- [ ] **Step 2: Write the results doc**

`docs/superpowers/results/<date>-v93-bearish-arms-train.md`, following `2026-09-10-legacy-badge-refresh-train.md`'s shape:

- Header: `Edge: volume (conditional on v93 Phase 1)`, what ran (window, arithmetic flags, universe N, laggard rule applied via `rs_combined`), the exact command.
- **Decision rule** copied verbatim from spec §4 (so the doc is self-contained).
- One table row per strategy: `Strategy | existing mask | bearish N (before RS) | N (after RS) | WR | ExpR | scratch+TO share | folds N>=15 & ExpR>0 (x/3) | Stage 1 masked | Stage 1 all | Stage 2 | Decision | chosen horizons`.
- Per-strategy detail blocks: the `stage1.masked.pooled`, `stage1.all.pooled`, fold stats, and every Stage 2 candidate with its plateau result.
- **Outcome section**: which masks change (WEAK strategies only), which are recorded-not-enabled (MACD, Volume Profile) and why, which failed.

- [ ] **Step 3: Apply the decision rule — masks**

For each **WEAK** strategy with `decision != "fail"`:
- `clear_masked`: `"directions": ("bullish", "bearish")`, `horizons` unchanged.
- `clear_all`: `"directions": ("bullish", "bearish")` and add `"horizons_by_direction": {"bearish": None}` only if a bullish `horizons` mask exists (so bearish runs every horizon while bullish keeps its mask). Note `entries_for` treats a `None` per-direction list as "all horizons".
- `clear_subset`: `"directions": ("bullish", "bearish")`, `"horizons_by_direction": {"bearish": <chosen>}`.
- Update the inline comment with the current-arithmetic numbers and the results doc path.

For **MACD** and **Volume Profile**: no code change regardless of decision; add a comment line under their entries: `# v93: bearish arm measured <numbers> -- NOT enabled; VALIDATED badge must not be diluted with an unvalidated population. Awaits its own shot (spec 3).`

For any strategy with `decision == "fail"`: no change; the results doc and Task 26's closed-table row are the record.

- [ ] **Step 4: Apply the decision rule — registry rows (WEAK clears only)**

For each WEAK strategy whose mask changed, re-emit its registry row as a TRAIN-window, both-directions row with today's run date (the same command shape the legacy badge refresh used, `--pass-wr 50` explicit):
```bash
python scripts/backtest/run_backtest_range.py --train --strategy "<name>" --exit-model v2 --scale-out --pass-wr 50 \
  --emit-registry swingbot/core/backtesting/validation_registry.json --run-date <YYYY-MM-DD>
```
(dispatch to `backtest-runner`). The badge stays `WEAK` — a TRAIN-window row never earns `VALIDATED`; that is spec 3's shot.

- [ ] **Step 5: Verify and commit**

Run: `python scripts/dev/testrun.py file tests/market/test_entry_filters.py`, `... tests/market/test_entry_filters_gates_v93.py`, `... tests/backtesting/test_registry.py`, `... tests/test_emit_registry.py` — green. Any test that pinned a now-changed mask literal is updated to the new mask **only if the results doc shows the clear**; otherwise the mask edit is wrong, not the test.

```bash
git add docs/superpowers/results/*-v93-bearish-arms-train.md swingbot/core/market/strategy_types.py swingbot/core/backtesting/validation_registry.json tests/market/test_entry_filters.py
git commit -m "feat(v93): bearish arms re-derived on TRAIN under current arithmetic -- masks per pre-registered rule"
```
(Commit the results doc even when every arm fails; a negative result is a finished measurement.)

---

### Task 26: Methodology and strategy docs for Phase 3

**Files:**
- Modify: `docs/claude/backtest-methodology.md` (closed pre-registrations table)
- Modify: `docs/strategy/strategy-gates.md` (new "Direction masks (v93 re-derivation)" section)
- Modify: `docs/strategy/strategy.md` (strategy table: direction column, if one exists; otherwise one paragraph pointing at the results doc)
- Modify: `.codex/AGENTS.md` **only if** `CLAUDE.md` or `docs/claude/*.md` gained a rule (it did: the methodology table row) — condensed, one line

- [ ] **Step 1: Closed table row** — append to the table in `backtest-methodology.md`:

```
| Bearish-arm re-derivation, seven bullish-only masks (v93) | **TRAIN + folds only, no VALIDATION spent.** Pre-registered rule `backtesting/arm_rule.py`. Cleared: <list with N/WR/ExpR>. Failed: <list with N/WR/ExpR>. MACD / Volume Profile arms <numbers> recorded, NOT enabled (VALIDATED badge not diluted; awaits spec 3's shot). Masks changed in `strategy_types.STRATEGY_GATES`; registry rows for cleared WEAK strategies re-emitted TRAIN-window. | `results/<date>-v93-bearish-arms-train.md` |
```

- [ ] **Step 2: `strategy-gates.md`** — new section:

```markdown
## Direction masks (v93 re-derivation)

The seven bullish-only masks in `strategy_types.STRATEGY_GATES` dated from the
2026-07 TRAIN tuning under the fixed reward:risk table v31 deleted. v93
measured each bearish arm on TRAIN under current arithmetic (v2 exits,
scale-out, level TP2, frictions), with the live RS laggard rule applied, against
a rule fixed before the run (`backtesting/arm_rule.py`: WR ≥ 50, ExpR > 0,
N ≥ 30, scratch+timeout ≤ 50 %, ≥ 2 of 3 anchored fold years with N ≥ 15 and
ExpR > 0; a bearish-only horizon subset allowed only on a win-rate-alone failure
with a plateau check). Outcome per strategy: `results/<date>-v93-bearish-arms-train.md`.
A cleared WEAK arm trades live into the weak ledger; MACD and Volume Profile
arms are recorded but not enabled until their own VALIDATION shot.
```

- [ ] **Step 3: Verify docs did not break any doc-pinned test**

Run: `python scripts/dev/testrun.py file tests/hooks/test_guardrails.py` (guardrails read `CLAUDE.md`/docs paths) — green.

- [ ] **Step 4: Commit**

```bash
git add docs/claude/backtest-methodology.md docs/strategy/strategy-gates.md docs/strategy/strategy.md .codex/AGENTS.md
git commit -m "docs(v93): closed-table row and strategy-gates section for the bearish-arm re-derivation"
```

---

# Phase 4 — Final verification and release

### Task 27: Full-suite verification, version bump, close-out

**Files:**
- Modify: `VERSION.json`, the generated version history (via `scripts/dev/build_version_matrix.py`)
- Move: `docs/superpowers/plans/2026-09-17-v93-strategy-path-live_*.md` → `docs/superpowers/plans/implemented/` and the spec → `docs/superpowers/specs/implemented/` per `docs/claude/document-lifecycle.md`

- [ ] **Step 1: Full Python suite, once**

Dispatch the `test-runner` subagent: `python scripts/dev/testrun.py full`. Expect `0 failed`, `0 xfailed`. **If not green, fix forward from the named failures** — they are this plan's regressions; the task is not done until the run is.

- [ ] **Step 2: Full frontend suite, once**

`cd frontend && npm test`. Expect green. Same rule.

- [ ] **Step 3: Version bump (read `VERSION.json` on disk; never a number from this document)**

Per `docs/claude/working-conventions.md`: increment the `bot` line at **minor** (new alert class and a new stored field are observable) and the `ui` line at **minor** (the headline P&L gains a sibling card and the Breakdowns picker a dimension). Set both `*_updated` stamps to now in the existing `YYYY-MM-DD HH-MM-SS` format. Run `python scripts/dev/build_version_matrix.py` and commit the regenerated history **with** the bump.

- [ ] **Step 4: Close-out**

Move the five plan files and the spec into their `implemented/` folders; if any prediction in the header block came out different (e.g. an `Edge: volume` arm that measured nothing), amend the line in this commit with one clause saying why. Confirm `git rev-list --count main..<branch>` is zero before any branch deletion, and never delete a branch whose name contains `backup`.

```bash
git add VERSION.json swingbot/admin/version_history.json docs/superpowers/plans docs/superpowers/specs
git commit -m "release(v93): strategy path live -- bot minor, ui minor; plan and spec closed out"
```
