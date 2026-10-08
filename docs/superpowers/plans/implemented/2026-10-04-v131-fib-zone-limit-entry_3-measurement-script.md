# v131 Fibonacci Limit — Part 3: measurement script

Index, Global Constraints, Review Focus and `## Parallelisation`: `2026-10-04-v131-fib-zone-limit-entry_0-index.md`. Spec: `docs/superpowers/specs/implemented/2026-10-04-v131-fib-zone-limit-entry-design.md`.

Same worktree and branch as Parts 1–2 (`<worktree>` = the absolute path of `.claude/worktrees/2026-10-04-v131-fib-zone-limit-entry`); `python scripts/dev/testrun.py ...` means `python <worktree>/scripts/dev/testrun.py ...`. **Never run a command containing the substring `eval` in the worktree** — the script's `evaluate` subcommand is exercised only through the unit tests here and runs for real on `main` in V131-10.

# Phase 3 — Measurement script (sequential)

### Task V131-06: `measure_fib_limit.py` — cells, rows, collect, Stage 0, reference reproduction, disclosures

**Files:**
- Create: `scripts/backtest/measure_fib_limit.py`
- Create: `tests/scripts/test_measure_fib_limit.py`
- Modify: `.gitignore` (after line 71, `data/v113_*.json`)

**Interfaces:**
- Consumes: `funnel` (`pooled`, `assert_rows_before`, `MIN_N_TRAIN`, `MIN_N_VALIDATION`, `BOOTSTRAP_SEED`); `measure_fib_confluence` (`Progress`, `_load_frames`, `_write`, `require_ext_cache`); `measure_fib_v103.require_committed`; `run_backtest_range` (`_build_asof_map`, `merge_registry`); `acceptance.BOOTSTRAP_RESAMPLES`; `backtest.run_backtest` and V131-04's `BacktestSummary.limit_orders`; V131-05's `FIB_LIMIT`, `PLAN_SHAPES[FIB_LIMIT]`, `DEFAULT_PARAMS[FIB_LIMIT]`; `stop_scope.in_scope`, `stop_ceiling`; `strategy_types.LEGACY_HORIZONS`.
- Produces (V131-07 and V131-10 rely on these): constants `TRAIN`, `REPRO_WINDOW`, `V103_REFERENCE`, `HOLDOUT_START`, `THIN_REOPEN`, `FOLD_YEARS`, `ALL_HZ`, `L_GRID`, `N_GRID`, `CELLS`, `LOOSEST_KEY`, `STAGE0_MIN_FILLS`, `FILLS_SHARE`, `WR_SLACK_PP`, `MIN_HOLDOUT_FILLS`, `EARLY_STOP_BARS`, `CAP_TOLERANCE_PCT`, `TOP2_LINE`, `RR_BAND`, `RESULTS`; `cell_key(ratio, life)`, `parse_cell(key)`, `require_preregistration(path)`, `require_frozen_config()`, `cell(key)` (context manager), `limit_row`, `reference_row`, `cell_rows(key, frames, asof_map, horizon, window, *, run_fn, progress) -> {"rows", "orders"}`, `reference_rows(...) -> list`, `collect_horizon(...)`, `load_collects(paths) -> {"universe_n", "reference", "cells": {key: {"rows", "orders"}}}`, `stage0_verdict(merged)`, `reproduction(merged)`, `disclosures(rows, orders=None)`, `_frames(args)`; commands `collect`, `stage0`, `reproduce`.
- The script's horizon tuple is named `ALL_HZ`, never `HORIZONS`: `tests/scripts/test_v113_script_horizons.py` fails on any script that iterates a name `HORIZONS`.

- [ ] **Step 1: Write the failing tests.** Create `tests/scripts/test_measure_fib_limit.py`:

```python
"""v131 funnel logic -- no market data: synthetic rows and a fake backtest."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "backtest"))
import measure_fib_limit as mf  # noqa: E402

from swingbot import config  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS  # noqa: E402
from swingbot.core.market.strategy_types import FIB_LIMIT, LEGACY_HORIZONS, STRATEGY_GATES, admits  # noqa: E402
from swingbot.core.planning.params import PLAN_SHAPES  # noqa: E402
from tests.helpers import make_ohlcv  # noqa: E402

FAST = dict(n_resamples=200, seed=42)
PREREG = "docs/superpowers/results/2026-10-05-v131-preregistration.md"


# --- fixtures -------------------------------------------------------------------

def _frame():
    """Daily bars 2025-12-01 .. 2026-02-20: straddles the TRAIN / holdout line."""
    return make_ohlcv([100.0] * 60, start="2025-12-01")


def _trade(frame, signal, exit_, *, outcome="win", r=1.5, entry=98.0, stop=97.0, target=100.0):
    return SimpleNamespace(direction="bullish", entry_date=str(frame.index[signal].date()),
                           exit_date=str(frame.index[exit_].date()), outcome=outcome, r_multiple=r,
                           entry=entry, stop_loss=stop, take_profit=target,
                           context={"stop_pct": 2.0, "planned_rr": 1.0, "stop_atr": 9.9, "rsi_14": 40.0})


def _order(frame, signal, fill, status="filled", new_high=False):
    filled = status == "filled"
    return {"signal_date": str(frame.index[signal].date()), "limit_price": 98.0, "cancel_level": 105.0,
            "status": status, "fill_date": str(frame.index[fill].date()) if filled else None,
            "fill_price": 98.0 if filled else None, "same_bar_new_high": new_high if filled else None}


def _fake_run(frame):
    """Two fills (one stopped out on bar fill+2, one in 2026), one expiry, one cancel."""
    trades = [_trade(frame, 5, 9, outcome="loss", r=-1.0), _trade(frame, 30, 40), _trade(frame, 45, 50)]
    orders = [_order(frame, 5, 7), _order(frame, 12, None, "expired"),
              _order(frame, 20, None, "cancelled"), _order(frame, 30, 31, new_high=True),
              _order(frame, 45, 46)]

    def run(ticker, df, strategy, horizon, **kwargs):
        assert kwargs == dict(one_at_a_time=True, exit_model="v2", scale_out=True,
                              tp2_mode="levels", frictions=True, asof=None)
        if strategy == FIB_LIMIT:
            return SimpleNamespace(trades=list(trades), limit_orders=list(orders))
        return SimpleNamespace(trades=[_trade(frame, 5, 6, outcome="loss", r=-1.0, entry=100.0, stop=98.0)],
                               limit_orders=[])
    return run


def _rows(years, per_year, win_share, *, tickers=8, horizon="2w"):
    rows = []
    for year in years:
        wins = round(per_year * win_share)
        for i in range(per_year):
            win = i < wins
            rows.append({"ticker": f"T{i % tickers}", "horizon_key": horizon, "direction": "bullish",
                         "entry_date": f"{year}-06-01", "outcome": "win" if win else "loss",
                         "r_multiple": 1.0 if win else -1.0, "early_stop": False, "cap_bound": True})
    return rows


def _merged(cell_rows, reference, universe_n=74):
    return {"universe_n": universe_n, "reference": reference,
            "cells": {key: {"rows": cell_rows.get(key, []), "orders": {"placed": 0}} for key in mf.CELLS}}


# --- Task V131-06: constants, cells, rows, Stage 0, reproduction --------------------

def test_preregistered_constants():
    assert mf.TRAIN == ("2010-01-01", "2025-12-31") and mf.HOLDOUT_START == "2026-01-01"
    assert mf.REPRO_WINDOW == ("2010-01-01", "2023-12-31")
    assert mf.V103_REFERENCE == {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219, "universe_n": 73}
    assert mf.FOLD_YEARS == tuple(range(2013, 2026)) and mf.THIN_REOPEN == "2026-12-31"
    assert mf.ALL_HZ == tuple(LEGACY_HORIZONS) and len(mf.ALL_HZ) == 10
    assert mf.CELLS == ("L0.5|N3", "L0.5|N5", "L0.5|N10", "L0.618|N3", "L0.618|N5", "L0.618|N10")
    assert mf.LOOSEST_KEY == "L0.5|N10" and mf.STAGE0_MIN_FILLS == 30
    assert (mf.FILLS_SHARE, mf.WR_SLACK_PP, mf.MIN_HOLDOUT_FILLS) == (0.5, 2.0, 15)
    assert mf.RR_BAND == (1.5, 2.5) and mf.EARLY_STOP_BARS == 3 and mf.TOP2_LINE == 0.8


def test_cell_sets_l_n_expiry_and_unmasks_then_restores():
    before = (dict(DEFAULT_PARAMS[FIB_LIMIT]), PLAN_SHAPES[FIB_LIMIT]["expiry_bars"])
    with mf.cell("L0.5|N10"):
        assert DEFAULT_PARAMS[FIB_LIMIT] == {"L": 0.5, "N": 10}
        assert PLAN_SHAPES[FIB_LIMIT]["expiry_bars"] == 10
        assert admits(FIB_LIMIT, "bullish", "2w") and not admits(FIB_LIMIT, "bearish", "2w")
    assert (DEFAULT_PARAMS[FIB_LIMIT], PLAN_SHAPES[FIB_LIMIT]["expiry_bars"]) == before
    assert STRATEGY_GATES[FIB_LIMIT] == {"directions": ()}


def test_preregistration_must_be_named_and_committed(monkeypatch):
    seen = []
    monkeypatch.setattr(mf, "require_committed", seen.append)
    with pytest.raises(SystemExit):
        mf.require_preregistration("docs/superpowers/results/2026-10-05-v130-preregistration.md")
    mf.require_preregistration(PREREG)
    assert seen == [PREREG]


def test_frozen_config_is_enforced(monkeypatch):
    mf.require_frozen_config()
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 3.0)
    with pytest.raises(SystemExit):
        mf.require_frozen_config()


def test_cell_rows_score_fills_and_count_orders_inside_the_window():
    frame = _frame()
    out = mf.cell_rows("L0.5|N10", {"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    [row] = out["rows"]                         # the two 2026 fills are outside TRAIN
    assert (row["entry_date"], row["fill_date"]) == (str(frame.index[5].date()), str(frame.index[7].date()))
    assert (row["signal_index"], row["fill_index"], row["limit_price"], row["fill_price"]) == (5, 7, 98.0, 98.0)
    assert row["early_stop"] is True             # a loss 2 bars after the fill
    assert row["risk_pct"] == pytest.approx(1 / 98 * 100, abs=1e-4)
    assert row["cap_bound"] is False             # 1.02% risk, 2% ceiling
    assert row["context"]["stop_pct"] == pytest.approx(1 / 98 * 100, abs=1e-6)
    assert row["context"]["planned_rr"] == pytest.approx(2.0)
    assert row["context"]["rsi_14"] == 40.0      # every other feature kept as recorded
    assert out["orders"] == {"placed": 3, "filled": 1, "expired": 1, "cancelled": 1, "same_bar_new_high": 0}


def test_holdout_dated_rows_never_reach_a_train_collect():
    frame = _frame()
    collected = mf.collect_horizon({"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    dates = [row["entry_date"] for arm in collected["cells"].values() for row in arm["rows"]]
    dates += [row["entry_date"] for row in collected["reference"]["rows"]]
    assert dates and max(dates) <= mf.TRAIN[1]


def test_the_collect_command_has_no_window_argument():
    with pytest.raises(SystemExit):
        mf._parser().parse_args(["collect", "--out", "x", "--preregistration", PREREG,
                                 "--horizon", "2w", "--window", "2026-01-01"])


def test_reference_rows_use_the_close_and_the_entry_bar():
    frame = _frame()
    [row] = mf.reference_rows({"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    assert row["early_stop"] is True and row["cap_bound"] is True       # 2.0% risk on 2% ceiling
    assert row["risk_pct"] == pytest.approx(2.0)


def _payload(horizon, cell_rows=(), ref_rows=(), universe_n=74):
    return {"horizon": horizon, "universe_n": universe_n, "reference": {"rows": list(ref_rows)},
            "cells": {key: {"rows": list(cell_rows) if key == mf.LOOSEST_KEY else [],
                            "orders": {"placed": len(cell_rows), "filled": len(cell_rows)}}
                      for key in mf.CELLS}}


def _write_collects(tmp_path, per_horizon_rows=0, skip=None):
    paths = []
    for horizon in mf.ALL_HZ:
        if horizon == skip:
            continue
        path = tmp_path / f"{horizon}.json"
        rows = _rows((2015,), per_horizon_rows, 0.5, horizon=horizon)
        path.write_text(json.dumps(_payload(horizon, rows, rows)), encoding="utf-8")
        paths.append(path)
    return paths


def test_load_collects_needs_every_horizon_exactly_once(tmp_path):
    with pytest.raises(SystemExit):
        mf.load_collects(_write_collects(tmp_path, skip="9m"))
    merged = mf.load_collects(_write_collects(tmp_path, per_horizon_rows=3))
    assert len(merged["cells"][mf.LOOSEST_KEY]["rows"]) == 30
    assert merged["cells"][mf.LOOSEST_KEY]["orders"] == {"placed": 30, "filled": 30}


@pytest.mark.parametrize("fills, passes", [(29, False), (30, True)])
def test_stage0_reads_only_the_loosest_cell(fills, passes):
    merged = _merged({mf.LOOSEST_KEY: _rows((2015,), fills, 0.5), "L0.618|N3": _rows((2015,), 500, 1.0)}, [])
    verdict = mf.stage0_verdict(merged)
    assert verdict == {"cell": "L0.5|N10", "fills": fills, "min_fills": 30, "passes": passes}


def test_reproduction_compares_the_2010_2023_slice_with_v103():
    reference = _rows((2015,), 10, 0.5) + _rows((2024, 2025), 50, 1.0)
    out = mf.reproduction(_merged({}, reference, universe_n=73))
    assert out["got"] == {"n": 10, "universe_n": 73, "win_rate": 50.0, "expectancy_r": 0.0}
    assert out["matches"] is False and sum(out["by_ticker"].values()) == 10


def test_disclosures():
    rows = _rows((2015,), 4, 0.5, horizon="2w") + _rows((2015,), 3, 0.5, horizon="4w") \
        + _rows((2015,), 3, 0.5, horizon="2m")
    rows[0]["early_stop"] = True
    out = mf.disclosures(rows, {"placed": 20, "filled": 10})
    assert out["fills"] == 10 and out["fill_rate"] == 0.5
    assert out["early_stop_share"] == 0.1 and out["cap_bind_share"] == 1.0
    assert out["horizon_concentration"]["top2_share"] == 0.7
    assert out["horizon_concentration"]["over_line"] is False
    assert out["total_r"] == sum(row["r_multiple"] for row in rows)
```

- [ ] **Step 2: Run to verify it fails.** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_limit.py`. Expected: FAIL — `ModuleNotFoundError: No module named 'measure_fib_limit'`.

- [ ] **Step 3: Implement.** Create `scripts/backtest/measure_fib_limit.py`:

```python
#!/usr/bin/env python3
"""v131 measurement: Fibonacci Limit -- a resting buy limit inside the retracement zone.

Stages (spec "The measurement"): collect (TRAIN rows, one horizon per call) ->
stage0 (the loosest cell's fill count) -> reproduce (the reference arm's
2010-2023 slice against v103) -> evaluate (Stages 1-2) -> holdout (Stage 3, one
shot) -> emit-registry. Every command refuses to run until the pre-registration
is committed. Reads the EXTENDED cache only:
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_limit.py <command> ...
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import funnel  # noqa: E402
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION  # noqa: E402
from measure_fib_confluence import Progress, _load_frames, _write, require_ext_cache  # noqa: E402
from measure_fib_v103 import require_committed  # noqa: E402
from run_backtest_range import _build_asof_map, merge_registry  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, gate_override  # noqa: E402
from swingbot.core.market.indicators import atr  # noqa: E402
from swingbot.core.market.strategy_types import FIB_LIMIT, LEGACY_HORIZONS  # noqa: E402
from swingbot.core.planning.params import PLAN_SHAPES  # noqa: E402
from swingbot.core.planning.stop_scope import in_scope, stop_ceiling  # noqa: E402

# --- pre-registered constants (spec "The measurement") ---
TRAIN = ("2010-01-01", "2025-12-31")
REPRO_WINDOW = ("2010-01-01", "2023-12-31")
V103_REFERENCE = {"n": 815, "win_rate": 36.81, "expectancy_r": 0.2219, "universe_n": 73}
HOLDOUT_START = "2026-01-01"
THIN_REOPEN = "2026-12-31"
FOLD_YEARS = tuple(range(2013, 2026))
ALL_HZ = tuple(LEGACY_HORIZONS)          # the ten legacy horizons, 2w..9m
L_GRID = (0.5, 0.618)
N_GRID = (3, 5, 10)
LOOSEST = (0.5, 10)
STAGE0_MIN_FILLS = 30
FILLS_SHARE = 0.5                           # profit clause (b)
WR_SLACK_PP = 2.0                           # profit clause (c)
MIN_HOLDOUT_FILLS = 15
EARLY_STOP_BARS = 3
CAP_TOLERANCE_PCT = 0.001
TOP2_LINE = 0.8
RR_BAND = (1.5, 2.5)
REFERENCE_STRATEGY = "Fibonacci"
UNMASKED = {"directions": ("bullish",)}
RESULTS = ROOT / "docs" / "superpowers" / "results"


def cell_key(ratio, life) -> str:
    return f"L{float(ratio):g}|N{int(life)}"


CELLS = tuple(cell_key(ratio, life) for ratio in L_GRID for life in N_GRID)
LOOSEST_KEY = cell_key(*LOOSEST)


def parse_cell(key: str) -> tuple[float, int]:
    ratio, life = key.split("|")
    return float(ratio[1:]), int(life[1:])


# --- guards -------------------------------------------------------------------

def require_preregistration(path) -> None:
    """Every command refuses to run before the pre-registration is committed."""
    if not Path(path).name.endswith("-v131-preregistration.md"):
        raise SystemExit(f"--preregistration must be the v131 pre-registration, got {path}")
    require_committed(path)


def require_frozen_config() -> None:
    """The plan arithmetic the pre-registration froze: the 1.5-2.5R band, and
    Fibonacci Limit outside STRUCTURAL_STOP_SCOPE (2% cap, not drop)."""
    band = (float(config.MIN_RISK_REWARD_RATIO), float(config.MAX_RISK_REWARD_RATIO))
    if band != RR_BAND:
        raise SystemExit(f"R:R band is {band}, the pre-registration froze {RR_BAND}")
    if in_scope(FIB_LIMIT, "bullish"):
        raise SystemExit("Fibonacci Limit is in STRUCTURAL_STOP_SCOPE; the pre-registration froze the 2% cap")


@contextlib.contextmanager
def cell(key: str):
    """Set one grid cell: L and N on the setup, N as the order's expiry_bars."""
    ratio, life = parse_cell(key)
    params, shape = DEFAULT_PARAMS[FIB_LIMIT], PLAN_SHAPES[FIB_LIMIT]
    saved = (dict(params), shape["expiry_bars"])
    params.update(L=ratio, N=life)
    shape["expiry_bars"] = life
    try:
        with gate_override(FIB_LIMIT, UNMASKED):
            yield
    finally:
        params.clear()
        params.update(saved[0])
        shape["expiry_bars"] = saved[1]


# --- rows -------------------------------------------------------------------------

def _positions(frame, *dates):
    import pandas as pd
    return [int(frame.index.get_indexer([pd.Timestamp(date)])[0]) for date in dates]


def _geometry(entry, stop, target, atr_value, ceiling) -> dict:
    """Plan geometry measured from `entry` (the limit for a cell, the close for
    the reference): risk %, cap binding, and the three context keys v131
    recomputes from the limit (spec "Features recorded for B")."""
    risk = abs(entry - stop)
    risk_pct = risk / entry * 100
    return {"risk_pct": round(risk_pct, 4),
            "cap_bound": risk_pct >= ceiling - CAP_TOLERANCE_PCT,
            "stop_pct": round(risk_pct, 6),
            "planned_rr": round(abs(target - entry) / risk, 6) if risk else None,
            "stop_atr": round(risk / atr_value, 6) if atr_value else None}


def _base_row(ticker, horizon, trade) -> dict:
    return {"ticker": ticker, "horizon_key": horizon, "direction": trade.direction,
            "entry_date": trade.entry_date, "exit_date": trade.exit_date,
            "outcome": trade.outcome, "r_multiple": trade.r_multiple,
            "stop_loss": trade.stop_loss, "take_profit": trade.take_profit}


def _early_stop(trade, fill_pos, exit_pos) -> bool:
    return trade.outcome == "loss" and exit_pos - fill_pos <= EARLY_STOP_BARS


def limit_row(ticker, horizon, trade, order, frame, atr_series) -> dict:
    """One filled Fibonacci Limit order: outcome, fill, disclosures, and the
    arming-bar entry_context with its geometry re-priced from the limit."""
    signal_pos, fill_pos, exit_pos = _positions(frame, trade.entry_date, order["fill_date"],
                                                trade.exit_date)
    ceiling = stop_ceiling(FIB_LIMIT, "bullish", horizon)[0]
    geometry = _geometry(trade.entry, trade.stop_loss, trade.take_profit,
                         float(atr_series.iloc[signal_pos]), ceiling)
    context = dict(trade.context or {})
    context.update({key: geometry[key] for key in ("stop_pct", "planned_rr", "stop_atr")})
    return {**_base_row(ticker, horizon, trade), "limit_price": trade.entry,
            "fill_date": order["fill_date"], "fill_price": order["fill_price"],
            "fill_index": fill_pos, "signal_index": signal_pos,
            "risk_pct": geometry["risk_pct"], "cap_bound": geometry["cap_bound"],
            "early_stop": _early_stop(trade, fill_pos, exit_pos),
            "same_bar_new_high": order["same_bar_new_high"], "context": context}


def reference_row(ticker, horizon, trade, frame) -> dict:
    """One reference-arm trade (market entry on the bounce bar's close)."""
    entry_pos, exit_pos = _positions(frame, trade.entry_date, trade.exit_date)
    ceiling = stop_ceiling(REFERENCE_STRATEGY, "bullish", horizon)[0]
    risk_pct = abs(trade.entry - trade.stop_loss) / trade.entry * 100
    return {**_base_row(ticker, horizon, trade), "risk_pct": round(risk_pct, 4),
            "cap_bound": risk_pct >= ceiling - CAP_TOLERANCE_PCT,
            "early_stop": _early_stop(trade, entry_pos, exit_pos)}


def _in_window(date, window) -> bool:
    return window[0] <= date <= window[1]


def _run(run_fn, ticker, frame, strategy, horizon, asof):
    return run_fn(ticker, frame, strategy, horizon, one_at_a_time=True, exit_model="v2",
                  scale_out=True, tp2_mode="levels", frictions=True, asof=asof)


def _count_orders(counts, orders, window) -> None:
    for order in orders:
        if not _in_window(order["signal_date"], window):
            continue
        counts["placed"] += 1
        counts[order["status"]] += 1
        counts["same_bar_new_high"] += int(bool(order["same_bar_new_high"]))


def cell_rows(key, frames, asof_map, horizon, window, *, run_fn=None, progress=None) -> dict:
    """Every bullish fill of one cell on one horizon inside `window`, plus the
    order counts behind the fill rate."""
    run_fn = run_fn or run_backtest
    rows, counts = [], collections.Counter()
    with cell(key):
        for ticker, frame in sorted(frames.items()):
            if progress is not None:
                progress.tick(f"{horizon} {key} {ticker}")
            summary = _run(run_fn, ticker, frame, FIB_LIMIT, horizon, asof_map.get(ticker))
            filled = {order["signal_date"]: order for order in summary.limit_orders
                      if order["status"] == "filled"}
            atr_series = atr(frame, 14)
            rows.extend(limit_row(ticker, horizon, trade, filled[trade.entry_date], frame, atr_series)
                        for trade in summary.trades
                        if trade.direction == "bullish" and _in_window(trade.entry_date, window))
            _count_orders(counts, summary.limit_orders, window)
    return {"rows": rows, "orders": {name: counts[name] for name in
                                     ("placed", "filled", "expired", "cancelled", "same_bar_new_high")}}


def reference_rows(frames, asof_map, horizon, window, *, run_fn=None, progress=None) -> list:
    """Today's Fibonacci, as it ships (bullish, live gates), on the same window."""
    run_fn = run_fn or run_backtest
    rows = []
    for ticker, frame in sorted(frames.items()):
        if progress is not None:
            progress.tick(f"{horizon} reference {ticker}")
        summary = _run(run_fn, ticker, frame, REFERENCE_STRATEGY, horizon, asof_map.get(ticker))
        rows.extend(reference_row(ticker, horizon, trade, frame) for trade in summary.trades
                    if trade.direction == "bullish" and _in_window(trade.entry_date, window))
    return rows


def collect_horizon(frames, asof_map, horizon, window, *, cells=CELLS, run_fn=None,
                    progress=None) -> dict:
    out = {"cells": {key: cell_rows(key, frames, asof_map, horizon, window,
                                    run_fn=run_fn, progress=progress) for key in cells},
           "reference": {"rows": reference_rows(frames, asof_map, horizon, window,
                                                run_fn=run_fn, progress=progress)}}
    return out


# --- loading the per-horizon collects ----------------------------------------------

def load_collects(paths) -> dict:
    """Merge the ten per-horizon TRAIN collects into one {cells, reference, universe_n}."""
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    horizons = sorted(payload["horizon"] for payload in payloads)
    if horizons != sorted(ALL_HZ):
        raise SystemExit(f"need exactly one collect per horizon {list(ALL_HZ)}, got {horizons}")
    if len({payload["universe_n"] for payload in payloads}) != 1:
        raise SystemExit("collects disagree on universe_n")
    merged = {"universe_n": payloads[0]["universe_n"], "reference": [],
              "cells": {key: {"rows": [], "orders": collections.Counter()} for key in CELLS}}
    for payload in payloads:
        merged["reference"].extend(payload["reference"]["rows"])
        for key in CELLS:
            merged["cells"][key]["rows"].extend(payload["cells"][key]["rows"])
            merged["cells"][key]["orders"].update(payload["cells"][key]["orders"])
    for key in CELLS:
        merged["cells"][key]["orders"] = dict(merged["cells"][key]["orders"])
    return merged


# --- Stage 0 and the reference reproduction -----------------------------------------

def stage0_verdict(merged) -> dict:
    """Free volume check: the loosest cell needs STAGE0_MIN_FILLS fills. Reads
    that one cell's fill count and nothing else."""
    fills = len(merged["cells"][LOOSEST_KEY]["rows"])
    return {"cell": LOOSEST_KEY, "fills": fills, "min_fills": STAGE0_MIN_FILLS,
            "passes": fills >= STAGE0_MIN_FILLS}


def reproduction(merged) -> dict:
    """The reference arm's 2010-2023 slice against v103's reference."""
    rows = [row for row in merged["reference"] if _in_window(row["entry_date"], REPRO_WINDOW)]
    stats = funnel.pooled(rows)
    got = {"n": stats["n"], "universe_n": merged["universe_n"],
           "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 2),
           "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 4)}
    by_ticker = collections.Counter(row["ticker"] for row in rows)
    return {"window": list(REPRO_WINDOW), "expected": V103_REFERENCE, "got": got,
            "matches": got == V103_REFERENCE, "by_ticker": dict(sorted(by_ticker.items()))}


# --- disclosures (reported, never selecting) ------------------------------------------

def _share(rows, flag):
    return sum(1 for row in rows if row[flag]) / len(rows) if rows else None


def horizon_concentration(rows) -> dict:
    counts = collections.Counter(row["horizon_key"] for row in rows)
    top2 = sum(n for _, n in counts.most_common(2))
    share = top2 / len(rows) if rows else None
    return {"by_horizon": dict(sorted(counts.items())), "top2_share": share,
            "over_line": share is not None and share >= TOP2_LINE}


def total_r(rows) -> float:
    return round(sum(row["r_multiple"] for row in rows if row["r_multiple"] is not None), 4)


def disclosures(rows, orders=None) -> dict:
    out = {"fills": len(rows), "early_stop_share": _share(rows, "early_stop"),
           "cap_bind_share": _share(rows, "cap_bound"),
           "horizon_concentration": horizon_concentration(rows), "total_r": total_r(rows)}
    if orders is not None:
        placed = orders.get("placed", 0)
        out.update(orders=orders, fill_rate=orders.get("filled", 0) / placed if placed else None)
    return out


# --- commands (collect, stage0, reproduce) -------------------------------------------

def _frames(args):
    require_ext_cache()
    require_frozen_config()
    frames = _load_frames(args.universe, args.tickers)
    return frames, _build_asof_map(list(frames), frames, args.universe)


def _cmd_collect(args):
    require_preregistration(args.preregistration)
    if args.horizon not in ALL_HZ:
        raise SystemExit(f"--horizon must be one of {list(ALL_HZ)}")
    started = time.monotonic()
    frames, asof_map = _frames(args)
    progress = Progress((len(CELLS) + 1) * len(frames))
    collected = collect_horizon(frames, asof_map, args.horizon, TRAIN, progress=progress)
    for arm in [*collected["cells"].values(), collected["reference"]]:
        funnel.assert_rows_before(arm["rows"], TRAIN[1])
    _write(args.out, {"horizon": args.horizon, "window": list(TRAIN), "universe_n": len(frames),
                      **collected, "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_stage0(args):
    require_preregistration(args.preregistration)
    _write(args.out, stage0_verdict(load_collects(args.rows)))


def _cmd_reproduce(args):
    require_preregistration(args.preregistration)
    _write(args.out, reproduction(load_collects(args.rows)))


def _parser():
    parser = argparse.ArgumentParser(description="v131 Fibonacci Limit funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "stage0", "reproduce"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--preregistration", required=True)
    sub.choices["collect"].add_argument("--universe")
    sub.choices["collect"].add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["collect"].add_argument("--horizon", required=True)
    for name in ("stage0", "reproduce"):
        sub.choices[name].add_argument("--rows", nargs="+", required=True)
    return parser


COMMANDS = {"collect": _cmd_collect, "stage0": _cmd_stage0, "reproduce": _cmd_reproduce}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v131 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Git-ignore the local dumps.** In `.gitignore`, directly after line 71 (`data/v113_*.json`), add `data/v131_*.json`. `git -C <worktree> check-ignore -v data/v131_collect_2w.json` must print the new rule.

- [ ] **Step 5: Run to verify it passes.**

```bash
python scripts/dev/testrun.py file tests/scripts/test_measure_fib_limit.py
python scripts/dev/testrun.py file tests/scripts/test_v113_script_horizons.py
```

Expected: 13 passed; the horizon-iteration guard green.

- [ ] **Step 6: Smoke the real path (optional but recommended; read-only, ~2.5 min).** This touches the extended cache but writes nothing tracked and reads only TRAIN-window rows:

```bash
BACKTEST_CACHE_DIR=data/backtest_cache_ext python - <<'EOF'
import sys
sys.path[:0] = [r"<worktree>", r"<worktree>/scripts/backtest"]
import measure_fib_limit as mf
from measure_fib_confluence import _load_frames
frames = _load_frames(None, "AAPL,MSFT,NVDA")
out = mf.collect_horizon(frames, {}, "3m", mf.TRAIN)
print({k: (len(v["rows"]), v["orders"]) for k, v in out["cells"].items()}, len(out["reference"]["rows"]))
EOF
```

Run it with the main tree as the working directory (so `data/backtest_cache_ext` resolves). Expected: six cells with non-zero `placed`, `filled + expired + cancelled == placed` per cell, and no exception. Measured while writing this plan: 77 orders placed per cell on `3m` for the three tickers, ~22 s; `2w` took ~125 s for the same three — so a full 74-ticker collect is roughly 50 min on `2w` and under 10 min on long horizons. Do **not** print or record any ExpR/WR here.

- [ ] **Step 7: Complexity.** `python -m radon cc -s -n C scripts/backtest/measure_fib_limit.py` prints nothing (measured max: `cell_rows` 10, `load_collects` 10).

- [ ] **Step 8: Commit**

```bash
git -C <worktree> add scripts/backtest/measure_fib_limit.py tests/scripts/test_measure_fib_limit.py .gitignore
git -C <worktree> commit -m "feat(v131): measure_fib_limit -- cells, fill rows with re-priced context, TRAIN collect, Stage 0 and the v103 reproduction gate

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V131-07: `measure_fib_limit.py` — Stages 1–3, the features record, emit-registry

**Files:**
- Modify: `scripts/backtest/measure_fib_limit.py` (imports; new section before `def _parser():`; replace `_parser` … end of file)
- Modify: `tests/scripts/test_measure_fib_limit.py` (append)

**Interfaces:**
- Consumes: V131-06's script (everything listed there); `funnel.score_cell`, `funnel._pick_winner(cells, plateau1, plateau2)` (keys may be any hashable — it reads `cells[key]["stats"]["expectancy_r"]`), `funnel.year_rows`, `funnel.TRAIN_START_YEAR`, `funnel.fold_verdict`.
- Produces: `neighbours(key)`, `plateau(passes)`, `profit_clauses(cell_stats, cell_fills, ref_stats, ref_trades) -> {"a_expr_beats_reference", "b_fills_half_of_reference", "c_wr_within_2pp"}`, `stage1(merged, *, n_resamples, seed)`, `fold_pick(merged, year)`, `stage2(merged)`, `evaluate(merged, *, n_resamples, seed)` (keys `stage1`, `stage2`, `proceed_to_holdout`, `closed_at` ∈ {None, "stage1", "stage2"}, `winner`, `tier`, `reference`, `disclosures`), `holdout_window(frames)`, `check_shot_allowed(out_path, cache_end=None)`, `holdout_verdict(rows, reference, tier, *, n_resamples, seed)` (`status` "sealed-thin" | "scored", `badge`), `holdout_rows(...)`, `registry_row(payload, run_date)`, `FEATURE_ROW_KEYS`, `feature_rows(merged)`; commands `evaluate`, `features`, `holdout`, `emit-registry`.

- [ ] **Step 1: Write the failing tests.** Append to `tests/scripts/test_measure_fib_limit.py`:

```python
# --- Task V131-07: Stages 1-3 ---------------------------------------------------------

def test_neighbours_are_one_axis_apart():
    assert sorted(mf.neighbours("L0.5|N5")) == ["L0.5|N10", "L0.5|N3", "L0.618|N5"]
    assert sorted(mf.neighbours("L0.618|N10")) == ["L0.5|N10", "L0.618|N5"]


def test_plateau_needs_every_neighbour():
    passes = {key: True for key in mf.CELLS}
    passes["L0.618|N3"] = False
    assert mf.plateau(passes) == ["L0.5|N5", "L0.5|N10", "L0.618|N10"]


# Hand-labelled: reference N(trades)=100, WR 40.0%, ExpR +0.20.
REF = {"win_rate": 40.0, "expectancy_r": 0.20}


@pytest.mark.parametrize("stats, fills, expected", [
    ({"win_rate": 38.0, "expectancy_r": 0.21}, 50, (True, True, True)),     # every edge exactly met
    ({"win_rate": 37.99, "expectancy_r": 0.21}, 50, (True, True, False)),   # WR 2.01pp below
    ({"win_rate": 45.0, "expectancy_r": 0.20}, 80, (False, True, True)),    # ExpR equal is not above
    ({"win_rate": 45.0, "expectancy_r": 0.30}, 49, (True, False, True)),    # 49 < 50% of 100
    ({"win_rate": None, "expectancy_r": None}, 0, (False, False, False)),
])
def test_profit_clause_arithmetic(stats, fills, expected):
    clauses = mf.profit_clauses(stats, fills, REF, 100)
    assert (clauses["a_expr_beats_reference"], clauses["b_fills_half_of_reference"],
            clauses["c_wr_within_2pp"]) == expected


def test_stage1_winner_is_the_highest_expr_tier1_plateau_cell_and_must_beat_the_reference():
    years = (2015, 2016, 2017)
    strong = {key: _rows(years, 20, 0.6) for key in mf.CELLS}            # WR 60, ExpR +0.2
    strong["L0.618|N10"] = _rows(years, 20, 0.7)                         # WR 70, ExpR +0.4
    reference = _rows(years, 20, 0.55)                                   # WR 55, ExpR +0.1
    first = mf.stage1(_merged(strong, reference), **FAST)
    assert (first["winner"], first["winner_tier"]) == ("L0.618|N10", 1)
    assert first["passes"] is True
    better_reference = _rows(years, 20, 0.75)                            # ExpR +0.5 beats every cell
    assert mf.stage1(_merged(strong, better_reference), **FAST)["passes"] is False


def test_stage1_without_a_plateau_has_no_winner():
    cells = {"L0.5|N10": _rows((2015, 2016), 20, 0.7)}                   # one strong cell, no neighbours
    first = mf.stage1(_merged(cells, _rows((2015,), 20, 0.5)), **FAST)
    assert first["winner"] is None and first["passes"] is False and first["profit_clauses"] is None


def test_stage2_reselects_on_prior_years_per_fold():
    years = tuple(range(2010, 2026))
    cells = {key: _rows(years, 40, 0.6) for key in mf.CELLS}
    second = mf.stage2(_merged(cells, []))
    assert [fold["test_year"] for fold in second["folds"]] == list(range(2013, 2026))
    assert all(fold["tol"] in mf.CELLS for fold in second["folds"])
    assert second["verdict"]["clears"] is True and second["verdict"]["qualifying"] == 13


def test_evaluate_closes_at_stage1_and_never_runs_stage2_then():
    out = mf.evaluate(_merged({}, _rows((2015,), 20, 0.5)), **FAST)
    assert (out["closed_at"], out["stage2"], out["proceed_to_holdout"], out["winner"]) == (
        "stage1", None, False, None)
    assert set(out["disclosures"]) == set(mf.CELLS)


def test_evaluate_proceeds_with_the_winner_and_its_tier():
    years = tuple(range(2010, 2026))
    cells = {key: _rows(years, 40, 0.6) for key in mf.CELLS}
    out = mf.evaluate(_merged(cells, _rows(years, 40, 0.55)), **FAST)
    assert out["proceed_to_holdout"] is True and out["closed_at"] is None
    assert out["winner"] in mf.CELLS and out["tier"] == 1


@pytest.fixture
def results(tmp_path, monkeypatch):
    monkeypatch.setattr(mf, "RESULTS", tmp_path)
    return tmp_path


def test_holdout_out_path_must_be_the_ledger(results, tmp_path):
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(tmp_path / "elsewhere.json")
    mf.check_shot_allowed(results / "2026-10-20-v131-holdout.json")


def test_a_scored_shot_is_spent_forever(results):
    (results / "2026-10-20-v131-holdout.json").write_text(json.dumps({"status": "scored"}))
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(results / "2027-06-01-v131-holdout.json", cache_end="2027-05-30")


def test_a_sealed_thin_shot_retries_once_after_the_reopen_date(results):
    (results / "2026-10-20-v131-holdout.json").write_text(json.dumps({"status": "sealed-thin"}))
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(results / "2026-11-20-v131-holdout.json", cache_end="2026-11-19")
    mf.check_shot_allowed(results / "2027-01-05-v131-holdout.json", cache_end="2026-12-31")
    (results / "2027-01-05-v131-holdout.json").write_text(json.dumps({"status": "sealed-thin"}))
    with pytest.raises(SystemExit):
        mf.check_shot_allowed(results / "2027-06-01-v131-holdout.json", cache_end="2027-05-30")


def test_holdout_verdict_sealed_thin_below_15_fills():
    assert mf.holdout_verdict(_rows((2026,), 14, 1.0), [], 1, **FAST) == {"status": "sealed-thin", "fills": 14}


def test_holdout_verdict_tier1_pass_is_validated_tier2_pass_is_weak():
    rows, reference = _rows((2026,), 20, 0.7), _rows((2026,), 20, 0.5)
    tier1 = mf.holdout_verdict(rows, reference, 1, **FAST)
    assert (tier1["status"], tier1["passes"], tier1["badge"]) == ("scored", True, "VALIDATED")
    tier2 = mf.holdout_verdict(rows, reference, 2, **FAST)
    assert (tier2["passes"], tier2["badge"]) == (True, "WEAK")


def test_holdout_verdict_fails_when_the_reference_does_better():
    rows, reference = _rows((2026,), 20, 0.7), _rows((2026,), 20, 0.9)
    out = mf.holdout_verdict(rows, reference, 1, **FAST)
    assert out["clauses"]["a_expr_beats_reference"] is False
    assert (out["passes"], out["badge"]) == (False, None)


def _args(**kw):
    return SimpleNamespace(**kw)


def _json(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


@pytest.fixture
def committed(monkeypatch):
    seen = []
    monkeypatch.setattr(mf, "require_committed", seen.append)
    return seen


def test_evaluate_refuses_a_volume_dead_stage0(tmp_path, committed):
    args = _args(preregistration=PREREG, stage0=_json(tmp_path, "s0.json", {"passes": False}),
                 reproduction=_json(tmp_path, "r.json", {"matches": True}), reproduction_note=None,
                 rows=[], out=str(tmp_path / "e.json"))
    with pytest.raises(SystemExit):
        mf._cmd_evaluate(args)


def test_evaluate_refuses_an_unexplained_reproduction_gap(tmp_path, committed):
    args = _args(preregistration=PREREG, stage0=_json(tmp_path, "s0.json", {"passes": True}),
                 reproduction=_json(tmp_path, "r.json", {"matches": False}), reproduction_note=None,
                 rows=[], out=str(tmp_path / "e.json"))
    with pytest.raises(SystemExit, match="reproduction-note"):
        mf._cmd_evaluate(args)


def test_holdout_refuses_a_mechanism_that_did_not_proceed(tmp_path, committed):
    args = _args(preregistration=PREREG, evaluate=_json(tmp_path, "e.json", {"proceed_to_holdout": False}))
    with pytest.raises(SystemExit):
        mf._holdout_target(args)


def test_emit_writes_one_row_only_for_a_passing_shot(tmp_path, committed):
    registry = tmp_path / "registry.json"
    passing = {"status": "scored", "passes": True, "badge": "WEAK", "preregistration": PREREG,
               "window": ["2026-01-01", "2026-09-28"],
               "stats": {"n": 40, "win_rate": 45.0, "expectancy_r": 0.31}}
    mf._cmd_emit(_args(holdout_json=_json(tmp_path, "h.json", passing), registry=str(registry),
                       run_date="2026-10-20"))
    [row] = json.loads(registry.read_text(encoding="utf-8"))
    assert row == {"source": "strategy", "strategy": FIB_LIMIT, "horizon": None, "status": "WEAK",
                   "n": 40, "win_rate": 45.0, "expectancy_r": 0.31,
                   "window": "2026-01-01..2026-09-28", "run_date": "2026-10-20"}
    for bad in ({"status": "sealed-thin"}, {**passing, "passes": False}):
        with pytest.raises(SystemExit):
            mf._cmd_emit(_args(holdout_json=_json(tmp_path, "bad.json", bad), registry=str(registry),
                               run_date="2026-10-20"))


def test_features_records_every_fill_with_its_context_and_nothing_else(tmp_path, committed):
    import gzip
    paths = _write_collects(tmp_path, per_horizon_rows=0)
    frame = _frame()
    one = mf.cell_rows("L0.5|N10", {"T": frame}, {}, "2w", mf.TRAIN, run_fn=_fake_run(frame))
    payload = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    payload["cells"]["L0.5|N10"]["rows"] = one["rows"]
    Path(paths[0]).write_text(json.dumps(payload), encoding="utf-8")
    out = tmp_path / "fills.json.gz"
    mf._cmd_features(_args(preregistration=PREREG, rows=paths, out=str(out)))
    with gzip.open(out, "rt", encoding="utf-8") as handle:
        written = json.load(handle)
    [row] = written["cells"]["L0.5|N10"]
    assert set(row) == set(mf.FEATURE_ROW_KEYS)
    assert (row["fill_index"], row["fill_price"], row["outcome"]) == (7, 98.0, "loss")
    assert row["context"]["stop_pct"] == pytest.approx(1 / 98 * 100, abs=1e-6)
    assert set(written) == {"window", "universe_n", "cells"}
```

- [ ] **Step 2: Run to verify it fails.** `python scripts/dev/testrun.py file tests/scripts/test_measure_fib_limit.py`. Expected: the 13 V131-06 tests pass; the new ones FAIL with `AttributeError: module 'measure_fib_limit' has no attribute 'neighbours'` (and `profit_clauses`, `stage1`, …).

- [ ] **Step 3: Implement.**

(a) In the import block, replace `import contextlib\nimport json` with:

```python
import contextlib
import gzip
import json
```

(b) Directly above `def _parser():`, insert:

```python
# --- Stage 1: selection on TRAIN ------------------------------------------------------

def neighbours(key: str) -> list[str]:
    """Adjacent values on one axis of the L x N grid."""
    ratio, life = parse_cell(key)
    i, j = L_GRID.index(ratio), N_GRID.index(life)
    out = [cell_key(L_GRID[a], life) for a in (i - 1, i + 1) if 0 <= a < len(L_GRID)]
    return out + [cell_key(ratio, N_GRID[b]) for b in (j - 1, j + 1) if 0 <= b < len(N_GRID)]


def plateau(passes: dict) -> list[str]:
    """Cells that clear a tier together with every grid neighbour."""
    return [key for key in CELLS if passes[key] and all(passes[n] for n in neighbours(key))]


def profit_clauses(cell_stats, cell_fills, ref_stats, ref_trades) -> dict:
    """Stage 1's profit clauses, all required of the winner: (a) ExpR above the
    reference arm's, (b) fills at least half the reference's trade count,
    (c) WR no more than 2.0pp below the reference's."""
    exp, ref_exp = cell_stats.get("expectancy_r"), ref_stats.get("expectancy_r")
    wr, ref_wr = cell_stats.get("win_rate"), ref_stats.get("win_rate")
    return {"a_expr_beats_reference": exp is not None and ref_exp is not None and exp > ref_exp,
            "b_fills_half_of_reference": cell_fills >= FILLS_SHARE * ref_trades,
            "c_wr_within_2pp": wr is not None and ref_wr is not None and wr >= ref_wr - WR_SLACK_PP}


def stage1(merged, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    cells = {key: funnel.score_cell(merged["cells"][key]["rows"], MIN_N_TRAIN,
                                    n_resamples=n_resamples, seed=seed) for key in CELLS}
    plateau1 = plateau({key: cells[key]["tier1"]["clears"] for key in CELLS})
    plateau2 = plateau({key: cells[key]["tier2"]["clears"] for key in CELLS})
    winner, tier = funnel._pick_winner(cells, plateau1, plateau2)
    reference = merged["reference"]
    clauses = None if winner is None else profit_clauses(
        cells[winner]["stats"], len(merged["cells"][winner]["rows"]),
        funnel.pooled(reference), len(reference))
    return {"cells": cells, "plateau_tier1": plateau1, "plateau_tier2": plateau2,
            "winner": winner, "winner_tier": tier, "profit_clauses": clauses,
            "passes": clauses is not None and all(clauses.values())}


# --- Stage 2: anchored folds ------------------------------------------------------------

def fold_pick(merged, year):
    """Re-select on 2010..year-1: the highest-ExpR cell with N >= 30 there."""
    best = None
    for key in CELLS:
        stats = funnel.pooled(funnel.year_rows(merged["cells"][key]["rows"],
                                               funnel.TRAIN_START_YEAR, year - 1))
        if stats["n"] < MIN_N_TRAIN or stats["expectancy_r"] is None:
            continue
        if best is None or stats["expectancy_r"] > best[1]:
            best = (key, stats["expectancy_r"])
    return None if best is None else best[0]


def stage2(merged) -> dict:
    folds = []
    for year in FOLD_YEARS:
        key = fold_pick(merged, year)
        stats = None if key is None else funnel.pooled(
            funnel.year_rows(merged["cells"][key]["rows"], year, year))
        folds.append({"test_year": year, "tol": key, "stats": stats})
    return {"folds": folds, "verdict": funnel.fold_verdict(folds)}


def evaluate(merged, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """Stages 1-2. Stage 2 runs only behind a Stage 1 winner that met every
    profit clause; disclosures are reported for every cell either way."""
    first = stage1(merged, n_resamples=n_resamples, seed=seed)
    second = stage2(merged) if first["passes"] else None
    proceed = second is not None and second["verdict"]["clears"]
    closed_at = None if proceed else ("stage1" if second is None else "stage2")
    reference = merged["reference"]
    return {"universe_n": merged["universe_n"], "stage1": first, "stage2": second,
            "proceed_to_holdout": proceed, "closed_at": closed_at,
            "winner": first["winner"] if proceed else None,
            "tier": first["winner_tier"] if proceed else None,
            "reference": {"stats": funnel.pooled(reference), "trades": len(reference),
                          **disclosures(reference)},
            "disclosures": {key: disclosures(merged["cells"][key]["rows"], merged["cells"][key]["orders"])
                            for key in CELLS}}


# --- Stage 3: the holdout (one shot) ----------------------------------------------------

def holdout_window(frames) -> tuple:
    """2026-01-01 to the cache end at the time of the shot."""
    return HOLDOUT_START, max(str(frame.index[-1].date()) for frame in frames.values())


def check_shot_allowed(out_path, cache_end=None) -> None:
    """One shot, ever: the results directory is the ledger. A single
    sealed-thin shot may be retried once, when the cache reaches THIN_REOPEN."""
    out = Path(out_path)
    if out.parent.resolve() != Path(RESULTS).resolve() or not out.name.endswith("-v131-holdout.json"):
        raise SystemExit(f"--out must be {RESULTS}/<date>-v131-holdout.json so the one-shot rule sees it")
    if out.exists():
        raise SystemExit(f"holdout output already exists: {out}")
    prior = sorted(Path(RESULTS).glob("*-v131-holdout.json"))
    if not prior:
        return
    statuses = [json.loads(path.read_text(encoding="utf-8")).get("status") for path in prior]
    if statuses != ["sealed-thin"]:
        raise SystemExit(f"the v131 holdout shot is spent ({prior[-1].name})")
    if cache_end is not None and cache_end < THIN_REOPEN:
        raise SystemExit(f"sealed-thin; the one retry waits for the cache to reach {THIN_REOPEN}")


def holdout_verdict(rows, reference, tier, *, n_resamples=BOOTSTRAP_RESAMPLES,
                    seed=BOOTSTRAP_SEED) -> dict:
    """Fewer than 15 fills is sealed-thin (shot unspent). Otherwise the winner
    is scored at the tier it held on TRAIN, plus profit clause (a) against the
    reference arm on the same holdout. The badge is computed, never gating:
    VALIDATED only for a Tier 1 winner that passes, WEAK for a Tier 2 pass."""
    fills = len(rows)
    if fills < MIN_HOLDOUT_FILLS:
        return {"status": "sealed-thin", "fills": fills}
    scored = funnel.score_cell(rows, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    reference_stats = funnel.pooled(reference)
    clauses = dict(scored["tier1" if tier == 1 else "tier2"]["clauses"])
    clauses["a_expr_beats_reference"] = profit_clauses(
        scored["stats"], fills, reference_stats, len(reference))["a_expr_beats_reference"]
    passes = all(clauses.values())
    return {"status": "scored", "tier": tier, "fills": fills, "stats": scored["stats"],
            "lower_bound": scored["lower_bound"], "reference": reference_stats,
            "clauses": clauses, "passes": passes,
            "badge": ("VALIDATED" if tier == 1 else "WEAK") if passes else None}


def holdout_rows(winner, frames, asof_map, window, progress=None) -> tuple:
    rows, orders, reference = [], collections.Counter(), []
    for horizon in ALL_HZ:
        one = cell_rows(winner, frames, asof_map, horizon, window, progress=progress)
        rows.extend(one["rows"])
        orders.update(one["orders"])
        reference.extend(reference_rows(frames, asof_map, horizon, window, progress=progress))
    return rows, dict(orders), reference


def registry_row(payload, run_date) -> dict:
    stats = payload["stats"]
    return {"source": "strategy", "strategy": FIB_LIMIT, "horizon": None, "status": payload["badge"],
            "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{payload['window'][0]}..{payload['window'][1]}", "run_date": run_date}


# --- commands (evaluate, holdout, emit-registry) -----------------------------------------

def _require_reproduction(path, note) -> None:
    """No cell is read until the reference reproduces v103, or a committed
    note explains the difference."""
    require_committed(path)
    if json.loads(Path(path).read_text(encoding="utf-8")).get("matches"):
        return
    if note is None:
        raise SystemExit("the reference does not reproduce v103: commit a --reproduction-note first")
    require_committed(note)


def _cmd_evaluate(args):
    require_preregistration(args.preregistration)
    require_committed(args.stage0)
    if not json.loads(Path(args.stage0).read_text(encoding="utf-8")).get("passes"):
        raise SystemExit("Stage 0 closed the mechanism (volume-dead); nothing to evaluate")
    _require_reproduction(args.reproduction, args.reproduction_note)
    _write(args.out, evaluate(load_collects(args.rows)))


def _holdout_target(args) -> dict:
    require_preregistration(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    if not evaluated.get("proceed_to_holdout"):
        raise SystemExit("the mechanism did not proceed to the holdout")
    return evaluated


def _cmd_holdout(args):
    evaluated = _holdout_target(args)
    check_shot_allowed(args.out)
    frames, asof_map = _frames(args)
    window = holdout_window(frames)
    check_shot_allowed(args.out, cache_end=window[1])
    progress = Progress(2 * len(ALL_HZ) * len(frames))
    rows, orders, reference = holdout_rows(evaluated["winner"], frames, asof_map, window, progress)
    result = holdout_verdict(rows, reference, evaluated["tier"])
    payload = {"candidate": evaluated["winner"], "window": list(window), "universe_n": len(frames),
               "evaluate": str(args.evaluate), "preregistration": str(args.preregistration), **result}
    if result["status"] == "scored":
        payload.update(rows=rows, reference_rows=reference, disclosures=disclosures(rows, orders),
                       reference_disclosures=disclosures(reference))
    _write(args.out, payload)


FEATURE_ROW_KEYS = ("ticker", "horizon_key", "entry_date", "signal_index", "fill_index", "fill_date",
                    "fill_price", "limit_price", "stop_loss", "take_profit", "outcome", "r_multiple",
                    "context")


def feature_rows(merged) -> dict:
    """Every TRAIN fill per cell with its arming-bar entry_context, for the
    queued meta-label spec (B). Recorded only: nothing here is split, scored
    or read by any stage."""
    return {key: [{name: row[name] for name in FEATURE_ROW_KEYS} for row in merged["cells"][key]["rows"]]
            for key in CELLS}


def _cmd_features(args):
    require_preregistration(args.preregistration)
    merged = load_collects(args.rows)
    payload = {"window": list(TRAIN), "universe_n": merged["universe_n"], "cells": feature_rows(merged)}
    with gzip.open(args.out, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, default=str)


def _cmd_emit(args):
    require_committed(args.holdout_json)
    payload = json.loads(Path(args.holdout_json).read_text(encoding="utf-8"))
    if payload.get("status") != "scored" or not payload.get("passes"):
        raise SystemExit("refusing to emit a failing or sealed-thin holdout")
    require_preregistration(payload["preregistration"])
    merge_registry(args.registry, [registry_row(payload, args.run_date)])
```

(c) Replace everything from `def _parser():` to the end of the file with:

```python
def _parser():
    parser = argparse.ArgumentParser(description="v131 Fibonacci Limit funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "stage0", "reproduce", "evaluate", "features", "holdout"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--preregistration", required=True)
    for name in ("collect", "holdout"):
        sub.choices[name].add_argument("--universe")
        sub.choices[name].add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["collect"].add_argument("--horizon", required=True)
    for name in ("stage0", "reproduce", "evaluate", "features"):
        sub.choices[name].add_argument("--rows", nargs="+", required=True)
    evaluate_parser = sub.choices["evaluate"]
    evaluate_parser.add_argument("--stage0", required=True)
    evaluate_parser.add_argument("--reproduction", required=True)
    evaluate_parser.add_argument("--reproduction-note")
    sub.choices["holdout"].add_argument("--evaluate", required=True)
    emit = sub.add_parser("emit-registry")
    emit.add_argument("--holdout-json", required=True)
    emit.add_argument("--registry", required=True)
    emit.add_argument("--run-date", required=True)
    return parser


COMMANDS = {"collect": _cmd_collect, "stage0": _cmd_stage0, "reproduce": _cmd_reproduce,
            "evaluate": _cmd_evaluate, "features": _cmd_features, "holdout": _cmd_holdout,
            "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v131 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify it passes.**

```bash
python scripts/dev/testrun.py file tests/scripts/test_measure_fib_limit.py
python scripts/dev/testrun.py file tests/scripts/test_v113_script_horizons.py
```

Expected: 36 passed; the guard green.

- [ ] **Step 5: Complexity.** `python -m radon cc -s -n C scripts/backtest/measure_fib_limit.py` prints nothing (measured: `check_shot_allowed` 9, `evaluate` 8, `fold_pick` 7, `stage1` 6).

- [ ] **Step 6: Commit**

```bash
git -C <worktree> add scripts/backtest/measure_fib_limit.py tests/scripts/test_measure_fib_limit.py
git -C <worktree> commit -m "feat(v131): measure_fib_limit -- 2-D plateau, profit clauses, anchored folds, features record, one-shot holdout ledger, emit-registry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task V131-08: No-lookahead review, fast tier, merge to `main`

**Files:**
- Review only: `swingbot/core/market/entry_filters.py` (V131-02/05 additions), `swingbot/core/planning/builders.py` (`_fib_limit_branch`, `_fib_zone_price`, `_fib_zone_cancel`, `plan_entry_reference`), `scripts/backtest/measure_fib_limit.py` (`limit_row`, `_geometry`, `reference_row`, `cell_rows`)
- Possibly modify: any of the above, only to fix a finding

**Interfaces:**
- Consumes: the finished branch.
- Produces: the branch merged to `main`; the merge commit hash V131-09 records.

- [ ] **Step 1: Load the `no-lookahead` skill** and run its review over exactly these units, recording each answer in the merge commit body:
  - `fibonacci_limit_setups` / `fib_limit_anchors` / `_fib_limit_candidates` / `_arm_orders`: every input at row `t` is from bars ≤ `t` (trailing `rolling`, `_rolling_arg*_pos` over `sliding_window_view` windows ending at `t`, the order book updated with bar `t` before arming at `t`). Proof: V131-02's every-cut truncation test.
  - `fib_limit_price_at`, `fib_limit_cancel_at`, `_fib_limit_row`, `_fib_limit_branch`: slice to `index` before computing. Proof: V131-02 `test_price_and_cancel_functions_match_the_setup_frame` (truncated call), V131-05 `test_truncation_invariance_of_the_built_plan`.
  - The script's feature code: `limit_row` re-prices `stop_pct`, `planned_rr`, `stop_atr` from the limit, the stop, the target (all frozen at `t`) and `atr(frame, 14)` **at the signal bar** (`signal_pos`), never at the fill bar; every other context key is `run_backtest`'s `entry_context(df.iloc[:i + 1], ...)` at the arming bar. `early_stop`, `same_bar_new_high` and `fill_*` are outcome/disclosure columns read after the fact and never enter a feature.
  - The simulator: `_limit_entry_exit` reads bar `j` only; truncation test in V131-03.
  A finding is fixed in the owning file with a test that fails first; record "no findings" otherwise.

- [ ] **Step 2: Fast tier.** `python <worktree>/scripts/dev/testrun.py fast`. Expected: `0 failed`, `0 xfailed`. Then `python <worktree>/scripts/dev/testrun.py file tests/backtesting/test_v131_witness.py` (slow tier, not in `fast`): 2 passed.

- [ ] **Step 3: Complexity over every touched file.**

```bash
python -m radon cc -s -n C <worktree>/swingbot/core/market/entry_filters.py <worktree>/swingbot/core/planning/builders.py <worktree>/swingbot/core/planning/exit_sim.py <worktree>/swingbot/core/planning/lifecycle.py <worktree>/swingbot/core/backtesting/backtest.py <worktree>/scripts/backtest/measure_fib_limit.py
```

Expected: only pre-existing entries, at their pre-v131 grades (`run_backtest` F 58, `run_backtest_daterange` D 25, `_trade_plan_at` C 14, `build_strategy_plan` C 14, and whatever `main` already lists for these files). Compare against the same command on `main`'s copies: no new name, no higher number except the two pre-announced 13 → 14.

- [ ] **Step 4: Merge to `main`** (load `worktree-lifecycle`; check for concurrent sessions first — `git -C E:/Documents/Private/Projects/Discord-Bot status --short` and `git log --oneline -5 main`; if another session committed to `main` since the branch point, pause and confirm with the partner before merging, per the collaboration note).

```bash
git -C E:/Documents/Private/Projects/Discord-Bot merge --no-ff 2026-10-04-v131-fib-zone-limit-entry -m "merge(v131): Fibonacci Limit -- masked strategy, limit_price plan shape, cancellable limit simulator, measurement script

no-lookahead review: <one line per unit from Step 1>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

Do not re-run any suite after a conflict-free merge. If the merge resolved conflicts, run `python scripts/dev/testrun.py changed` once on `main`.

- [ ] **Step 5: Remove the worktree** (`worktree-lifecycle`): `git -C E:/Documents/Private/Projects/Discord-Bot worktree remove .claude/worktrees/2026-10-04-v131-fib-zone-limit-entry`, then `git -C E:/Documents/Private/Projects/Discord-Bot branch -d 2026-10-04-v131-fib-zone-limit-entry` (its name contains no `backup`; `git rev-list --count main..2026-10-04-v131-fib-zone-limit-entry` must print `0` first).
