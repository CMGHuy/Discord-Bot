"""Historical replay of the confluence scan (spec §4): rebuild the level
map as of each bar, run levels.build_scenarios with that bar's close, and
feed the qualifying scenarios through the SAME plan constructor and exit
simulator the live scan uses. No lookahead: every computation sees
df.iloc[:i+1] only."""
from __future__ import annotations

import numpy as np

from swingbot.core import levels
from swingbot.core.plan_engine import build_confluence_plan, simulate_exit
from swingbot.core.strategy_types import HORIZONS, MIN_BARS

# Levels move slowly; recomputing the full multi-source level map every bar
# is ~5x the cost for near-identical output. One recompute per 5 bars is the
# fidelity/cost tradeoff -- the same granularity the Task 28 backtest tp2
# lookup uses.
LEVEL_REFRESH_BARS = 5


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


def replay_scenarios(ticker: str, df, horizon_key: str, *, gates: dict) -> list:
    """(signal_index, TradePlanV2) for every bar where the confluence scan
    WOULD have emitted a plan, under `gates`, with a per-direction cooldown.

    No lookahead: every computation below is scoped to `window = df.iloc[:i+1]`
    (or `levels_asof`, which enforces the same slice internally) -- never
    `df.iloc[-1]` or any index beyond `i`.
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
        scenarios = levels.build_scenarios(
            price, supports, resistances, effective_min_reward,
            atr_floor=floor_pct,
            min_stop_distance_pct=gates["min_stop_distance_pct"],
            max_stop_distance_pct=effective_max_stop,
            min_risk_reward=gates["min_risk_reward"])

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
                # Task 38 will wire real strategy attribution via
                # primary_strategy_for(sc); until then, the plan's own
                # documented fallback literal.
                primary_strategy="S/R Confluence")
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


def run_scenario_backtest(frames: dict, start, end, *, gates,
                          scale_out=True, horizons=None) -> dict:
    """frames: {ticker: OHLCV df}. start/end (ISO or None) restrict SIGNAL
    dates -- the exit walk may run past `end`, same convention as
    run_backtest_daterange."""
    horizons = horizons or list(HORIZONS)
    results_by_hz: dict = {hk: [] for hk in horizons}
    for ticker, df in frames.items():
        for hk in horizons:
            for i, plan in replay_scenarios(ticker, df, hk, gates=gates):
                signal_date = str(df.index[i].date())
                if start and signal_date < start:
                    continue
                if end and signal_date > end:
                    continue
                results_by_hz[hk].append(simulate_exit(df, i, plan,
                                                       scale_out=scale_out))
    all_results = [r for rs in results_by_hz.values() for r in rs]
    return {"pooled": _aggregate(all_results),
            "by_horizon": {hk: _aggregate(rs) for hk, rs in results_by_hz.items()}}
