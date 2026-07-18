"""Analytics core -- pure computation over trade-record dicts (see the Global
Constraints in docs/superpowers/plans/2026-07-11-cockpit-v3.md Part 1: no I/O
in metrics/aggregate/calibration/rank/insights, and every stat has exactly
one definition here that every UI/embed/route consumes instead of
re-deriving). Re-exports the public surface so callers can do either
`from swingbot.core.analytics import metrics` or
`from swingbot.core.analytics import equity_curve` interchangeably."""
from swingbot.core.analytics.metrics import (  # noqa: F401
    equity_curve,
    drawdown_series,
    max_drawdown_pct,
    r_multiple,
    win_rate,
    expectancy_r,
    profit_factor,
    streaks,
    r_multiples,
    rolling_win_rate,
    trade_return_pct,
    sharpe,
    sortino,
)
from swingbot.core.analytics.mfe_mae import compute_mfe_mae  # noqa: F401
from swingbot.core.analytics.aggregate import StatRow, stats_by  # noqa: F401

__all__ = [
    "equity_curve",
    "drawdown_series",
    "max_drawdown_pct",
    "r_multiple",
    "win_rate",
    "expectancy_r",
    "profit_factor",
    "streaks",
    "r_multiples",
    "rolling_win_rate",
    "trade_return_pct",
    "sharpe",
    "sortino",
    "compute_mfe_mae",
    "StatRow",
    "stats_by",
]
