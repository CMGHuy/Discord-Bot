"""Anchored walk-forward fold runner.

Delegates to edge-engine E39 (swingbot/core/backtest_wf.py) when it exposes
a `run_walk_forward(strategy, gate_min_tier=...)` entry point; else the
minimal fallback below runs the G92 gate-filtered replay per fold directly.

`swingbot/core/backtest_wf.py` already exists in this repo (confirmed via
`ls`) -- it ships edge-engine's OWN `run_folds(overrides, ...)`, shaped
around parameter-grid overrides, not a per-strategy `run_walk_forward`. So
today this always takes the fallback path; the delegation is a forward seam
for whenever E39 grows that entry point. The `hasattr` guard below (not a
bare `try/except ImportError`) is deliberate: `import swingbot.core.backtest_
wf` already succeeds since the module is real, so wrapping the delegation
call in `except ImportError` alone would let an AttributeError (missing
`run_walk_forward`) propagate unhandled instead of falling through to the
fallback -- confirmed against the real module, not just the plan's
stub-module test (see test_no_delegation_against_the_real_backtest_wf_module
in tests/test_gate_folds.py)."""
from __future__ import annotations

import importlib

FOLDS = (
    {"year": 2021, "train_end": "2020-12-31",
     "test_start": "2021-01-01", "test_end": "2021-12-31"},
    {"year": 2022, "train_end": "2021-12-31",
     "test_start": "2022-01-01", "test_end": "2022-12-31"},
    {"year": 2023, "train_end": "2022-12-31",
     "test_start": "2023-01-01", "test_end": "2023-12-31"},
)


def fold_windows() -> tuple:
    return FOLDS


def apply_fold_gate(fold_rows: list[dict], baseline_rows: list[dict]) -> dict:
    """The Global-Constraints fold gate verbatim: improve in >= 2 of 3
    folds, no fold degrades expectancy_r by > 0.05R, N >= 30 per fold."""
    improved = degraded = 0
    for fold, base in zip(fold_rows, baseline_rows):
        if (fold.get("n") or 0) < 30:
            return {"passes_gate": False,
                    "reason": f"{fold['year']}: N={fold.get('n')} < 30"}
        if fold["wr"] > base["wr"]:
            improved += 1
        if fold["expectancy_r"] < base["expectancy_r"] - 0.05:
            degraded += 1
    passes = improved >= 2 and degraded == 0
    return {"passes_gate": passes, "improved_folds": improved,
            "degraded_folds": degraded,
            "reason": None if passes else f"improved {improved}/3, degraded {degraded}"}


def _fold_stats(trades: list[dict]) -> dict:
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    wins = sum(t["outcome"] == "win" for t in closed)
    n = len(closed)
    return {"n": n, "wr": round(100.0 * wins / n, 1) if n else None,
            "expectancy_r": (round(sum(t.get("r_multiple", 0.0) for t in closed) / n, 3)
                             if n else None)}


def _default_replay(strategy, ticker, test_start, test_end, gate_min_tier):
    """Wraps the G92 replay: load cached daily bars ending at test_end, run
    with gate_eval=True (+ gate_min_tier), keep trades entered inside the
    test window.

    Reads `swingbot.core.backtest_cache.CACHE_DIR` -- NOT `market_data/`.
    This repo keeps two parallel OHLCV caches (see docs/claude/known-traps.md
    and backtest_wf.py's own `_frame_for` docstring) and only the backtest
    cache is comparable to every other backtest number in this repo.

    horizon_key="2w": run_folds has no horizon_key parameter in its own
    interface, so this picks the shortest/cheapest HORIZONS entry as the
    fallback's fixed horizon. A caller needing a different horizon should
    pass its own `replay` callable instead."""
    import pandas as pd

    from swingbot.core.backtest import run_backtest
    from swingbot.core.backtest_cache import CACHE_DIR

    path = CACHE_DIR / f"{ticker}.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df = df.loc[:test_end]
    if not len(df):
        return []
    result = run_backtest(ticker, df, strategy, "2w",
                          gate_eval=True, gate_min_tier=gate_min_tier)
    return [t.to_dict() for t in result.trades
            if test_start <= str(t.entry_date)[:10] <= test_end]


def run_folds(strategy: str, *, gate_min_tier: str | None = None,
              tickers=None, replay=None, verbose: bool = False) -> dict:
    try:
        backtest_wf = importlib.import_module("swingbot.core.backtest_wf")
    except ImportError:
        backtest_wf = None
    if backtest_wf is not None and hasattr(backtest_wf, "run_walk_forward"):
        return backtest_wf.run_walk_forward(strategy, gate_min_tier=gate_min_tier)

    replay = replay or _default_replay
    if tickers is None:
        from swingbot.core.watchlist import load_watchlist
        tickers = load_watchlist()
    folds, all_trades = [], []
    for window in FOLDS:
        trades = []
        for idx, ticker in enumerate(tickers, 1):
            if verbose:
                print(f"    [{strategy}] fold {window['year']} "
                      f"ticker {idx}/{len(tickers)} {ticker}", flush=True)
            trades += replay(strategy, ticker, window["test_start"],
                             window["test_end"], gate_min_tier)
        stats = _fold_stats(trades)
        folds.append({"year": window["year"], **stats})
        if verbose:
            print(f"  [{strategy}] fold {window['year']} done: {stats}", flush=True)
        all_trades += [t for t in trades if t.get("outcome") in ("win", "loss")]
    return {"strategy": strategy, "min_tier": gate_min_tier,
            "folds": folds, "pooled": _fold_stats(all_trades),
            "trades": all_trades}


def ablate_flags(trades: list[dict], flags: list[str] | None = None) -> list[dict]:
    """Each flag alone as a filter: what does removing ITS trades do to
    WR/expectancy? Flags that HURT expectancy get demoted to weight 0 by
    the follow-up commit this task documents."""
    closed = [t for t in trades if t.get("outcome") in ("win", "loss")]
    if not closed:
        return []
    if flags is None:
        flags = sorted({f for t in closed for f in t.get("fired_flags", [])})
    base = _fold_stats(closed)
    out = []
    for flag in flags:
        kept = [t for t in closed if flag not in t.get("fired_flags", [])]
        stats = _fold_stats(kept)
        out.append({
            "flag": flag,
            "signals_removed_pct": round(100.0 * (len(closed) - len(kept))
                                         / len(closed), 1),
            "wr_delta": (round(stats["wr"] - base["wr"], 1)
                         if None not in (stats["wr"], base["wr"]) else None),
            "expectancy_delta": (round(stats["expectancy_r"] - base["expectancy_r"], 3)
                                 if None not in (stats["expectancy_r"],
                                                 base["expectancy_r"]) else None),
            "n_kept": stats["n"],
        })
    return out
