"""Historical replay of the confluence scan (spec §4): rebuild the level
map as of each bar, run levels.build_scenarios with that bar's close, and
feed the qualifying scenarios through the SAME plan constructor and exit
simulator the live scan uses. No lookahead: every computation sees
df.iloc[:i+1] only."""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from swingbot import config

from swingbot.core.market import levels
from swingbot.core.market.chart_patterns import dead_cat_bounce
from swingbot.core.planning.plan_engine import build_confluence_plan, primary_strategy_for, simulate_exit
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS

# Levels move slowly; recomputing the full multi-source level map every bar
# is ~5x the cost for near-identical output. One recompute per 5 bars is the
# fidelity/cost tradeoff -- the same granularity the Task 28 backtest tp2
# lookup uses.
LEVEL_REFRESH_BARS = 5

# TRAIN grid found no qualifying config (Task 39); these are unvalidated
# defaults, not a tuned winner. The pre-registered selection rule (per
# horizon: win_rate>=80, expectancy_r>0, N>=30, excl<=50%; pair with the
# best pooled ExpR among pairs with >=2 qualifying horizons) failed at every
# one of the 6 (min_confluence, min_risk_reward) grid points tested -- best
# observed win_rate was 66.4% (need >=80%) and every expectancy_r was
# negative (need >0). Zero qualifying horizons anywhere, so there was no
# pair to even rank. Full grid + the rule applied by hand:
# docs/superpowers/results/2026-07-confluence-train-grid.txt; narrative +
# table: docs/superpowers/results/2026-07-confluence-train.md.
#
# Per the plan's pre-registered fallback ("if no pair qualifies, confluence
# source stays WEAK everywhere and Tasks 41-42 record that honestly"), this
# is NOT the grid winner -- there wasn't one. min_reward_pct/min_stop_
# distance_pct/max_stop_distance_pct/min_risk_reward mirror the pre-existing
# SCENARIO_GATES in scripts/backtest/run_backtest_range.py (the closest existing
# precedent, itself never grid-validated). min_confluence uses the least
# restrictive value the Task 39 grid tested (2), not a tuned choice. horizons
# lists every horizon the grid covered -- NOT a "qualifying" subset, since
# none qualified.
CONFLUENCE_GATES = {
    "min_reward_pct": 3.0,
    "min_stop_distance_pct": 2.0,
    "max_stop_distance_pct": 7.0,
    "min_risk_reward": 1.5,
    "min_confluence": 2,
    "cooldown_bars": 5,
    "horizons": ["4w", "2m", "3m", "4m", "6m"],  # grid coverage, not a pass
}


def levels_asof(ticker: str, df, bar_index: int, horizon_key: str, cache: dict):
    """(supports, resistances) as they looked at bar_index -- computed on
    df.iloc[:bar_index+1] so the map can never see future bars."""
    key = (ticker, horizon_key, bar_index // LEVEL_REFRESH_BARS)
    if key in cache:
        return cache[key]
    window = df.iloc[:bar_index + 1]
    price = float(window["Close"].iloc[-1])
    result = levels.build_level_map(window, HORIZONS[horizon_key], price)
    cache[key] = result
    return result


def replay_scenarios(ticker: str, df, horizon_key: str, *, gates: dict,
                     dcb_params: dict | None = None) -> list:
    """(signal_index, TradePlanV2) for every bar where the confluence scan
    WOULD have emitted a plan, under `gates`, with a per-direction cooldown.

    No lookahead: every computation below is scoped to `window = df.iloc[:i+1]`
    (or `levels_asof`, which enforces the same slice internally) -- never
    `df.iloc[-1]` or any index beyond `i`.

    `dcb_params`: v68's dead-cat-bounce veto params. Taken directly rather
    than read from config -- the TRAIN grid runs twelve different parameter
    sets in one process, and a config read would make them a global the
    workers fight over. `None` is the baseline arm and must not pay for the
    detector at all.
    """
    h = HORIZONS[horizon_key]
    warmup = MIN_BARS[horizon_key]
    cooldown = gates.get("cooldown_bars", 5)
    cache: dict = {}
    out: list = []
    last_accepted: dict = {}   # direction -> bar index

    for i in range(warmup, len(df)):
        window = df.iloc[:i + 1]
        price = float(window["Close"].iloc[-1])
        supports, resistances = levels_asof(ticker, df, i, horizon_key, cache)
        # drop levels the later bars created is already impossible (as-of map);
        # but the map's supports/resistances were split against ITS OWN price --
        # re-split against this bar's price when the cache bucket lags:
        all_levels = sorted(supports + resistances, key=lambda lv: lv.price)
        supports = [lv for lv in all_levels if lv.price < price][::-1]
        resistances = [lv for lv in all_levels if lv.price > price]

        floor_pct = levels.atr_floor_pct(window, price, h)
        effective_min_reward = max(gates["min_reward_pct"],
                                   h.get("sr_target_min_pct", 0) * 0.15)
        effective_max_stop = max(gates["max_stop_distance_pct"],
                                 h.get("max_risk_pct", 0))
        # v68. `window` is the harness's no-lookahead slice -- the same frame
        # the live scan hands to veto_bullish_for. dcb_params=None is the
        # baseline arm and must not pay for the detector at all.
        block_bullish = False
        if dcb_params is not None:
            block_bullish = bool(dead_cat_bounce(window, dcb_params)["detected"])
        scenarios = levels.build_scenarios(
            price, supports, resistances, effective_min_reward,
            atr_floor=floor_pct,
            min_stop_distance_pct=gates["min_stop_distance_pct"],
            max_stop_distance_pct=effective_max_stop,
            min_risk_reward=gates["min_risk_reward"],
            block_bullish=block_bullish)

        for sc in scenarios:
            n_confl, families = levels.count_confirming_strategies(
                window, h, price, sc.take_profit, tolerance_pct=5.0)
            if n_confl < gates.get("min_confluence", 1):
                continue
            last = last_accepted.get(sc.direction)
            if last is not None and i - last < cooldown:
                continue
            plan = build_confluence_plan(
                sc, window, ticker=ticker, horizon_key=horizon_key,
                primary_strategy=primary_strategy_for(sc),
                level_map=(supports, resistances))
            if plan is None:
                continue          # no qualifying target -> no trade, same as live
            last_accepted[sc.direction] = i
            out.append((i, plan))
    return out


def _aggregate(results: list) -> dict:
    """Win/loss/scratch/timeout/runner stats -- same shape family as
    run_backtest_range.py's `pool()`, but keyed to ExitResult's outcome
    vocabulary (Task 37)."""
    closed = [r for r in results if r.outcome != "not_triggered"]
    ev = [r for r in closed if r.outcome in ("win", "loss")]
    wins = [r for r in ev if r.outcome == "win"]
    runner = {}
    for r in closed:
        if r.runner_outcome:
            runner[r.runner_outcome] = runner.get(r.runner_outcome, 0) + 1
    return {
        "n": len(ev),
        "wins": len(wins),
        "losses": len(ev) - len(wins),
        "scratches": sum(1 for r in closed if r.outcome == "scratch"),
        "timeouts": sum(1 for r in closed if r.outcome == "timeout"),
        "not_triggered": sum(1 for r in results if r.outcome == "not_triggered"),
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([r.r_total for r in closed])) if closed else None,
        "runner": runner,
    }


def _replay_ticker(args) -> dict:
    """All horizons for ONE ticker -- the process-pool entry point, so it must
    be module-level and take a single picklable argument.

    Grouped per ticker rather than per (ticker, horizon) pair on purpose: the
    OHLCV frame is the expensive thing to move across a process boundary (~2MB
    for a ten-year daily history), and a per-pair split would ship the same
    frame once per horizon -- ten times the IPC for parallelism a 2-4 core box
    cannot use anyway. At 300-500 tickers there are already far more tasks
    than cores.

    Returns {horizon_key: [exit_result, ...]}. The horizon travels in the
    RESULT rather than being inferred from completion order, which is what
    makes the pooled path order-independent.
    """
    ticker, df, horizons, start, end, gates, scale_out, dcb_params = args
    out = {hk: [] for hk in horizons}
    for hk in horizons:
        for i, plan in replay_scenarios(ticker, df, hk, gates=gates,
                                        dcb_params=dcb_params):
            signal_date = str(df.index[i].date())
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            out[hk].append(simulate_exit(df, i, plan, scale_out=scale_out))
    return out


def _resolve_replay_workers(workers: int | None) -> int:
    if workers is not None:
        return max(1, int(workers))
    configured = int(getattr(config, "FETCH_WORKERS", 0) or 0)
    if configured > 0:
        return configured
    return max(1, (os.cpu_count() or 2) - 1)


def run_scenario_backtest(frames: dict, start, end, *, gates,
                          scale_out=True, horizons=None, workers=None,
                          dcb_params: dict | None = None) -> dict:
    """frames: {ticker: OHLCV df}. start/end (ISO or None) restrict SIGNAL
    dates -- the exit walk may run past `end`, same convention as
    run_backtest_daterange.

    v47: each ticker is replayed across a process pool, all horizons inside
    one task. Every task is fully independent -- it reads one frame and
    contributes only to its own result lists -- and aggregation happens
    strictly after every task returns, so the output is identical to the
    sequential walk. `workers=1` forces the sequential path; None resolves
    FETCH_WORKERS (0 = auto).

    This is CPU-bound work on in-memory frames with no network and no yfinance
    involvement, so it carries none of the crawl's thread-safety constraints --
    processes are used here purely because the work is GIL-bound Python.
    """
    horizons = horizons or list(HORIZONS)
    results_by_hz: dict = {hk: [] for hk in horizons}

    tasks = [
        (ticker, df, horizons, start, end, gates, scale_out, dcb_params)
        for ticker, df in frames.items()
    ]

    n = _resolve_replay_workers(workers)
    if n <= 1 or len(tasks) <= 1:
        per_ticker_results = [_replay_ticker(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=n) as pool:
            per_ticker_results = list(pool.map(_replay_ticker, tasks))

    for per_ticker in per_ticker_results:
        for hk, results in per_ticker.items():
            results_by_hz[hk].extend(results)

    all_results = [r for rs in results_by_hz.values() for r in rs]
    return {"pooled": _aggregate(all_results),
            "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}
