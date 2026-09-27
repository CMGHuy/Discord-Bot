"""Strategy-source population through the live plan constructor (v100).

At signal bar ``i`` the constructor receives only ``df.iloc[:i + 1]``;
``simulate_exit`` alone walks later bars to determine the outcome.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting import backtest as bt
from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.arms.confluence_engine import SKIPPED
from swingbot.core.market.levels import build_level_map
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS
from swingbot.core.planning.builders import build_strategy_plan
from swingbot.core.planning.plan_engine import exit_params_for, simulate_exit


class StrategyEngine:
    engine_id = "strategy"

    def __init__(self, strategies=None):
        self.strategies = tuple(strategies or bt.ALL_STRATEGIES)

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        out = []
        for horizon_key in horizons:
            for strategy in self.strategies:
                for date, plan, result in self.iter_trades(
                        ticker, df, strategy, horizon_key, signal_window, params):
                    out.append(arm_trade_from_plan(
                        plan, entry_date=date, outcome=result.outcome,
                        r_multiple=result.r_total,
                    ))
        return out

    def iter_trades(self, ticker, df, strategy, horizon_key, signal_window, params):
        start, end = signal_window
        min_bars = MIN_BARS[horizon_key]
        if len(df) < min_bars + 10:
            return
        bull, bear = bt._vectorized_entries(df, strategy, horizon_key)
        if bt.ENTRY_SHIFT:
            bull = pd.Series(np.roll(bull.values, bt.ENTRY_SHIFT), index=df.index)
            bear = pd.Series(np.roll(bear.values, bt.ENTRY_SHIFT), index=df.index)
        wants_tp2 = bool(exit_params_for(strategy)["tp2"])
        open_until, level_map_key, level_map = -1, None, None
        for index in np.where(bull.values | bear.values)[0]:
            if index < min_bars or index <= open_until:
                continue
            date = str(df.index[index].date())
            if date > end:
                break
            direction = "bullish" if bull.values[index] else "bearish"
            window = df.iloc[:index + 1]
            if wants_tp2 and index // 5 != level_map_key:
                level_map = build_level_map(
                    window, HORIZONS[horizon_key], float(df["Close"].iloc[index]))
                level_map_key = index // 5
            plan = build_strategy_plan(
                window, index, ticker=ticker, strategy=strategy,
                horizon_key=horizon_key, direction=direction,
                level_map=level_map if wants_tp2 else None, scan_params=params,
            )
            if plan is None:
                continue
            result = simulate_exit(df, index, plan, scale_out=True)
            if result.outcome in SKIPPED:
                continue
            open_until = result.exit_index
            if date >= start:
                yield date, plan, result
