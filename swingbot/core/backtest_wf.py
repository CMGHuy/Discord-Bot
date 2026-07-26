"""Anchored walk-forward harness -- the gatekeeper for every Edge component.

Folds are FROZEN (pre-registered before any data contact, per the plan's
Global Constraints). Train windows exist for parameter *fitting* inside
components that need it; the judgment numbers come only from the test
years. The 2024-2025 window does not appear here at all -- it is spent
exactly once, at the end of the plan.
"""
from __future__ import annotations

import logging

from swingbot import config

log = logging.getLogger("swing-bot.backtest_wf")

ANCHORED_FOLDS = (
    ("2018-01-01", "2020-12-31", "2021-01-01", "2021-12-31"),
    ("2018-01-01", "2021-12-31", "2022-01-01", "2022-12-31"),
    ("2018-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
)

# Pre-registered gate constants -- do not touch without a new pre-registration.
GATE_MIN_IMPROVING_FOLDS = 2
GATE_MAX_DEGRADATION_R = 0.05
GATE_MIN_N_PER_FOLD = 30

PLATEAU_TOLERANCE_R = 0.03


def plateau_report(param_name: str, grid: list, expectancies: list,
                   adopted_value) -> dict:
    """Adopted values must sit on plateaus, never spikes: if moving one
    grid step changes expectancy by more than PLATEAU_TOLERANCE_R, the
    'optimum' is noise you happened to sample."""
    i = grid.index(adopted_value)
    neighbors = [j for j in (i - 1, i + 1) if 0 <= j < len(grid)]
    is_plateau = all(abs(expectancies[j] - expectancies[i]) <= PLATEAU_TOLERANCE_R
                     for j in neighbors)
    return {"param": param_name, "grid": grid, "expectancies": expectancies,
            "adopted": adopted_value,
            "neighbors": {grid[j]: expectancies[j] for j in neighbors},
            "is_plateau": is_plateau}


def _apply_overrides(overrides: dict) -> dict:
    old = {}
    for key, value in overrides.items():
        old[key] = getattr(config, key, None)
        setattr(config, key, value)
    return old


def _guarded(run_fn):
    """Wrap a run function so config overrides are applied and restored
    around it, whatever happens inside. Split out of `_default_run` so an
    injected `run_fn` gets the same protection: a component run that
    raises must never leave config mutated, or the next component's folds
    silently inherit it."""
    def wrapped(start: str, end: str, overrides: dict) -> dict:
        old = _apply_overrides(overrides or {})
        try:
            return run_fn(start, end, overrides)
        finally:
            _apply_overrides(old)
    return wrapped


def _symbols_for_folds() -> list:
    """The symbol set folds run over. Separate seam so tests never touch
    the universe files or the OHLCV cache."""
    from swingbot.core.universe import universe_symbols
    from swingbot.core.watchlist import load_watchlist

    symbols = universe_symbols(getattr(config, "SCAN_UNIVERSE", "watchlist")) or []
    return symbols or load_watchlist()


def _frame_for(symbol: str):
    """Daily bars for one symbol, or None.

    Reads `data/backtest_cache/` -- NOT `market_data/`. This repo has two
    parallel OHLCV caches and they are not interchangeable. The choice
    matters twice over here:

      * COMPARABILITY. Every number these folds are judged against (the
        E22 friction-adjusted baseline) came from scripts/run_backtest_
        range.py, which reads this cache. Folds measured on the other one
        would be comparing against a different dataset.
      * WARM-UP DEPTH. market_data/ starts 2018-06 (measured), i.e. right
        at the folds' own anchor, leaving indicators no warm-up before
        the first train window. backtest_cache goes back to 2000. On AAPL
        the same strategies produce 13 trades from backtest_cache vs 1
        from market_data over identical windows -- the fold N would have
        been starved by the data source alone.
    """
    from swingbot.core.backtest_cache import CACHE_DIR
    import pandas as pd

    path = CACHE_DIR / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, index_col=0, parse_dates=True)
    except Exception as exc:
        log.warning("fold frame unreadable for %s: %s", symbol, exc)
        return None


def _default_run(start: str, end: str, overrides: dict,
                 strategies=None, horizons=None) -> dict:
    """Pooled expectancy over the cached universe for one window.

    Overrides are NOT applied here -- `run_folds` wraps every run function
    in `_guarded`, so applying them twice would double-restore.
    """
    import numpy as np
    from swingbot.core.backtest import ALL_STRATEGIES, run_backtest_daterange
    from swingbot.core.strategy_types import HORIZONS
    from swingbot.core.universe import liquidity_ok

    strategies = ALL_STRATEGIES if strategies is None else strategies
    horizons = list(HORIZONS) if horizons is None else horizons

    rs = []
    for sym in _symbols_for_folds():
        df = _frame_for(sym)
        if df is None or not liquidity_ok(df):
            continue
        for strat in strategies:
            for hk in horizons:
                # The plan's own snippet omitted horizon_key entirely and
                # was never callable: run_backtest_daterange is
                # (ticker, df, strategy, horizon_key, date_from, date_to).
                # exit_model/scale_out/tp2_mode match what the E22
                # friction-adjusted baseline was measured with
                # (run_backtest_range.py defaults --tp2 levels), or fold
                # deltas would be comparing against a different exit model.
                #
                # tp2_mode="levels" is also what makes level-sourced
                # components VISIBLE here at all: with "none" the backtest
                # never calls build_level_map, so AVWAP and HVN/LVN change
                # nothing and their folds would score a meaningless 0.0000.
                s = run_backtest_daterange(sym, df, strat, hk, start, end,
                                           frictions=True, exit_model="v2",
                                           scale_out=True, tp2_mode="levels")
                rs.extend(t.r_multiple for t in (s.trades or [])
                          if t.r_multiple is not None)
    return {"expectancy_r": float(np.mean(rs)) if rs else None, "n": len(rs)}


def run_folds(overrides: dict, folds=ANCHORED_FOLDS, tickers=None,
              run_fn=None) -> dict:
    run = _guarded(_default_run) if run_fn is None else run_fn
    fold_rows = []
    for train_start, train_end, test_start, test_end in folds:
        base = run(test_start, test_end, {})
        comp = run(test_start, test_end, dict(overrides))
        delta = None
        if base["expectancy_r"] is not None and comp["expectancy_r"] is not None:
            delta = comp["expectancy_r"] - base["expectancy_r"]
        fold_rows.append({"test_years": test_start[:4],
                          "baseline": base, "component": comp,
                          "delta_expectancy_r": delta,
                          "n": min(base["n"], comp["n"])})
    deltas = [f["delta_expectancy_r"] for f in fold_rows if f["delta_expectancy_r"] is not None]
    pooled = sum(deltas) / len(deltas) if deltas else None
    return {"folds": fold_rows, "pooled_delta_expectancy_r": pooled}


def gate(result: dict) -> str:
    """The PRE-REGISTERED pass rule. A component that fails is dropped and
    documented -- no second grid on the same hypothesis."""
    folds = result["folds"]
    deltas = [f["delta_expectancy_r"] for f in folds]
    if any(d is None for d in deltas):
        return "FAIL"
    if any(f["n"] < GATE_MIN_N_PER_FOLD for f in folds):
        return "FAIL"
    if sum(d > 0 for d in deltas) < GATE_MIN_IMPROVING_FOLDS:
        return "FAIL"
    if any(d < -GATE_MAX_DEGRADATION_R for d in deltas):
        return "FAIL"
    return "PASS"
