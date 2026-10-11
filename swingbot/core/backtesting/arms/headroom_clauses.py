"""Frozen v135 clause-6 baseline reading and the no-level-map disclosure.

A rejected entry frees the one-position slot (strategy) or the 5-bar cooldown (confluence),
so the component arm is not a subset of baseline and acceptance.py reports mechanism
SKIPPED. As for v122, the mechanism clause is scored on the BASELINE arm: in-scope trades
the predicate flags at h ("removed") against in-scope trades it does not flag ("retained").

A stamped arm row carries no entry or stop, so the reading replays the baseline with both
knobs forced off. Strategy: each in-scope cell goes through StrategyEngine.iter_trades (the
baseline's own plans), with the level map built at each trade's signal bar by level_map_at
-- the very map the replay gate and the live gate read. Confluence: each trade's scenario and lists are rebuilt with scenarios_at after
priming the level bucket, which reproduces the replay bar for bar.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from swingbot.core.backtesting import backtest_scenarios as scenarios_mod
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.arms import dryup_clauses
from swingbot.core.backtesting.arms.knobs import apply_knobs
from swingbot.core.backtesting.arms.strategy_engine import StrategyEngine, level_map_at
from swingbot.core.edge import gates
from swingbot.scan_params import ScanParams

#: The reading always replays the baseline, whatever the operator's .env says.
BASELINE_KNOBS = {"HEADROOM_SCOPE": "off", "HEADROOM_MIN_R": 0.0}


class NotAHeadroomArm(ValueError):
    """The arm stamp does not identify an active headroom component."""


@dataclass(frozen=True)
class Reading:
    blocker: tuple | None    # gates.nearest_blocker's (distance, risk), or None
    n_levels: int            # size of the level map the predicate was handed


def in_scope(trade, scope) -> bool:
    """Keep the two registered components and the frozen strategy list separate."""
    if trade.source != scope:
        return False
    return scope == "confluence" or (scope == "strategy"
                                     and gates.strategy_in_headroom_scope(trade.strategy))


def _reading(entry, stop, direction, level_map) -> Reading:
    levels = gates.level_map_levels(level_map)
    return Reading(gates.nearest_blocker(entry, stop, direction, levels), len(levels))


def _bar_index(frame, date) -> int:
    """Position of the signal bar: the last bar at or before `date`."""
    return len(frame.loc[:date]) - 1


def strategy_cell_readings(ticker, frame, strategy, horizon_key, signal_window, params) -> dict:
    """Reading per baseline trade of one (ticker, strategy, horizon) cell. The cell is
    replayed through the baseline engine, so each plan is the baseline's own plan."""
    out = {}
    engine = StrategyEngine(strategies=(strategy,))
    for date, plan, result in engine.iter_trades(ticker, frame, strategy, horizon_key,
                                                 signal_window, params):
        trade = arm_trade_from_plan(plan, entry_date=date, outcome=result.outcome,
                                    r_multiple=result.r_total)
        level_map = level_map_at(frame, _bar_index(frame, date), horizon_key)
        out[trade.key] = _reading(gates.planned_entry(plan), plan.stop_loss, plan.direction,
                                  level_map)
    return out


def confluence_reading(trade, frame, params, level_cache) -> Reading | None:
    """The reading for one baseline confluence trade, from the scenario and the lists the
    replay had at its signal bar. None when that bar holds no scenario in its direction."""
    index, horizon_key = _bar_index(frame, trade.entry_date), trade.horizon_key
    scenarios_mod.levels_asof(trade.ticker, frame, scenarios_mod.bucket_bar(index, horizon_key),
                              horizon_key, level_cache)
    _window, _price, supports, resistances, scenarios = scenarios_mod.scenarios_at(
        trade.ticker, frame, index, horizon_key, params, level_cache)
    scenario = next((item for item in scenarios if item.direction == trade.direction), None)
    if scenario is None:
        return None
    return _reading(scenario.entry, scenario.stop_loss, trade.direction, (supports, resistances))


def _strategy_readings(trades, frame, signal_window, params, cache) -> dict:
    out = {}
    for ticker, strategy, horizon_key in sorted({(t.ticker, t.strategy, t.horizon_key)
                                                 for t in trades}):
        key = ("strategy", ticker, strategy, horizon_key, tuple(signal_window))
        if key not in cache:
            cache[key] = strategy_cell_readings(ticker, frame, strategy, horizon_key,
                                                signal_window, params)
        out.update(cache[key])
    return out


def _confluence_readings(trades, frame, params, cache) -> dict:
    out, level_cache = {}, {}
    for trade in trades:
        key = ("confluence", trade.key)
        if key not in cache:
            cache[key] = confluence_reading(trade, frame, params, level_cache)
        out[trade.key] = cache[key]
    return out


def _ticker_readings(trades, frame, scope, signal_window, params, cache) -> dict:
    if frame is None:
        return {}
    if scope == "strategy":
        return _strategy_readings(trades, frame, signal_window, params, cache)
    return _confluence_readings(trades, frame, params, cache)


def scoped_readings(trades, frame_for, scope, signal_window, cache=None, progress=None) -> dict:
    """Reading per in-scope baseline trade key. None means the baseline replay did not
    reproduce the trade (or its ticker has no frame). `cache` may be shared across arm files
    of one process: a reading depends on the frame and the trade, never on h.
    `progress(done, total)` is called once per ticker."""
    cache = {} if cache is None else cache
    by_ticker = defaultdict(list)
    for trade in trades:
        if in_scope(trade, scope):
            by_ticker[trade.ticker].append(trade)
    found = {}
    with apply_knobs(BASELINE_KNOBS):
        params = ScanParams.from_config()
        for done, ticker in enumerate(sorted(by_ticker), 1):
            found.update(_ticker_readings(by_ticker[ticker], frame_for(ticker), scope,
                                          signal_window, params, cache))
            if progress is not None:
                progress(done, len(by_ticker))
    return {trade.key: found.get(trade.key)
            for ticker in sorted(by_ticker) for trade in by_ticker[ticker]}


def no_map_share(readings, scope) -> dict:
    """Disclose how many scoped baseline plans were judged with no level map at all, and how
    many the replay did not reproduce. Neither can be flagged."""
    n = len(readings)
    unreadable = sum(reading is None for reading in readings.values())
    no_map = sum(reading is not None and reading.n_levels == 0 for reading in readings.values())
    return {"scope": scope, "n": n, "no_map": no_map, "unreadable": unreadable,
            "share": no_map / n if n else None,
            "unreadable_share": unreadable / n if n else None}


def flagged_keys(readings, min_r) -> set:
    """The gate's own strict comparison, including its None and off rules."""
    return {key for key, reading in readings.items()
            if reading is not None and gates.blocker_inside(reading.blocker, min_r)}


def baseline_mechanism(baseline, flagged, scope):
    """Compare flagged vs unflagged in-scope baseline outcomes only."""
    scoped = [trade for trade in baseline if in_scope(trade, scope)]
    removed = [trade for trade in scoped if trade.key in flagged]
    retained = [trade for trade in scoped if trade.key not in flagged]
    return dryup_clauses.mechanism_result(removed, retained, scope)


def knob_context(blob):
    """Return an active component only when both headroom knobs are stamped."""
    delta = (blob.get("provenance") or {}).get("knob_delta") or {}
    scope, min_r = delta.get("HEADROOM_SCOPE"), delta.get("HEADROOM_MIN_R")
    if scope not in gates.HEADROOM_SCOPES or isinstance(min_r, bool):
        return None
    if not isinstance(min_r, (int, float)) or not math.isfinite(min_r) or min_r <= 0:
        return None
    return scope, float(min_r)


def signal_window(blob) -> tuple:
    """The stamped signal window, which the strategy replay must reuse to reproduce the arm."""
    start, end = blob["provenance"]["signal_window"]
    return start, end
