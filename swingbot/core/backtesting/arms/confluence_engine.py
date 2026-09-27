"""Confluence population: scenario replay followed by the shared exit model."""
from __future__ import annotations

from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.planning.plan_engine import simulate_exit

SKIPPED = ("not_triggered", "no_trade")


class ConfluenceEngine:
    engine_id = "confluence"

    def run_ticker(self, ticker, df, horizons, signal_window, params) -> list:
        """Produce closed confluence trades with signal dates in the window."""
        start, end = signal_window
        signal_df = df.loc[:end]
        out = []
        for horizon_key in horizons:
            for index, plan in replay_scenarios(ticker, signal_df, horizon_key, params=params):
                entry_date = str(df.index[index].date())
                if entry_date < start:
                    continue
                result = simulate_exit(df, index, plan, scale_out=True)
                if result.outcome in SKIPPED:
                    continue
                out.append(arm_trade_from_plan(
                    plan, entry_date=entry_date, outcome=result.outcome,
                    r_multiple=result.r_total,
                ))
        return out
