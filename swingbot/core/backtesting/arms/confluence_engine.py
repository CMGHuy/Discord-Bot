"""Confluence population: scenario replay followed by the shared exit model."""
from __future__ import annotations

from swingbot.core.backtesting.acceptance import arm_trade_from_plan
from swingbot.core.backtesting.arms import net_basis
from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.core.planning.plan_engine import simulate_exit

SKIPPED = ("not_triggered", "no_trade")


class ConfluenceEngine:
    engine_id = "confluence"

    def __init__(self, instrument=None, r_basis=None):
        # v157: the backtest instrument every simulate_exit call runs under; None is v1.
        self.instrument = instrument
        # v238: None books today's gross r_total; "net" / "gross" book through arms.net_basis.
        net_basis.check_basis(r_basis, instrument=instrument)
        self.r_basis = r_basis

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
                result = simulate_exit(df, index, plan, scale_out=True,
                                       instrument=self.instrument)
                if result.outcome in SKIPPED:
                    continue
                out.append(arm_trade_from_plan(
                    plan, entry_date=entry_date, outcome=result.outcome,
                    r_multiple=self._booked_r(plan, result, df),
                ))
        return out

    def _booked_r(self, plan, result, df) -> float:
        """Today's gross r_total under r_basis=None; otherwise the requested basis (v238)."""
        if self.r_basis is None:
            return result.r_total
        return net_basis.booked_r(plan, result, df, r_basis=self.r_basis)
