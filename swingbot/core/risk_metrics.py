"""
Risk-adjusted performance metrics for the closed-trade track record, via
the QuantStats library (https://github.com/ranaroussi/quantstats, same
author as yfinance which this project already depends on).

`!performance` previously reported only win rate. This adds the metrics
that actually matter for judging whether a track record is good, not
just how often it wins: Sharpe and Sortino ratios (return per unit of
risk taken, Sortino counting only downside volatility), max drawdown
(the worst peak-to-trough dip you'd have sat through, in cumulative
trade-return terms), and Calmar (total return relative to that worst
dip) -- plus profit factor and average win/loss size, which QuantStats
also provides directly.

Important framing: this bot logs DISCRETE trades at irregular dates, not
a continuous daily equity curve, but QuantStats itself is built around
daily return series. Rather than fake an annualization that assumes a
trade happens every single day (which would wildly overstate Sharpe/
Sortino), every ratio here is computed UNANNUALIZED, directly from the
chronological sequence of trade returns -- qs.stats.sharpe(returns,
annualize=False), i.e. "return per trade, divided by volatility per
trade". That's honest for irregularly-spaced discrete trades, at the
cost of not being directly comparable to a textbook annualized Sharpe
quoted elsewhere for a daily-rebalanced portfolio. Every place these
numbers are displayed says "per trade, not annualized" for this reason.

Optional in practice: if quantstats isn't installed, or there aren't
enough closed trades yet for the numbers to mean anything, this simply
returns None and `!performance` falls back to win-rate-only stats,
exactly as before.
"""
import logging

import pandas as pd

log = logging.getLogger("swing-bot.risk_metrics")

try:
    import quantstats as qs
    _QUANTSTATS_AVAILABLE = True
except ImportError:
    _QUANTSTATS_AVAILABLE = False
    log.info("quantstats not installed -- risk-adjusted performance metrics are disabled; win-rate stats are unaffected.")

# Below this many closed trades, Sharpe/Sortino/drawdown numbers are
# mostly sampling noise -- not worth presenting as if they mean anything yet.
MIN_CLOSED_TRADES = 5


def _trade_return_pct(trade: dict) -> float:
    """Signed % return for one closed trade -- mirrors the same calculation
    scan_engine.py's closed-trade embed already uses."""
    pct = (trade["exit_price"] - trade["entry"]) / trade["entry"] * 100
    return -pct if trade["direction"] == "bearish" else pct


def compute_risk_metrics(closed_trades: list) -> dict | None:
    """
    `closed_trades`: trade records with status in ("win", "loss"), in any
    order. Returns None if quantstats isn't available or there aren't
    enough trades yet for the numbers to be meaningful (see
    MIN_CLOSED_TRADES); otherwise a dict:

      n_trades, sharpe, sortino, max_drawdown_pct, calmar, profit_factor,
      total_return_pct, avg_win_pct, avg_loss_pct, best_trade_pct,
      worst_trade_pct

    sharpe/sortino/calmar are UNANNUALIZED (see module docstring).
    profit_factor/calmar are None if undefined (e.g. no losing trades yet
    makes profit factor infinite -- reported as None/"n/a" rather than a
    misleading infinity).
    """
    if not _QUANTSTATS_AVAILABLE or len(closed_trades) < MIN_CLOSED_TRADES:
        return None

    ordered = sorted(closed_trades, key=lambda t: t["closed_at"])
    dates = pd.to_datetime([t["closed_at"] for t in ordered])
    pct_returns = [_trade_return_pct(t) for t in ordered]
    returns = pd.Series([r / 100 for r in pct_returns], index=dates)

    try:
        sharpe = float(qs.stats.sharpe(returns, annualize=False))
        sortino = float(qs.stats.sortino(returns, annualize=False))
        equity_curve = (1 + returns).cumprod()
        max_dd = float(qs.stats.max_drawdown(equity_curve)) * 100  # negative %
        total_return_pct = float(equity_curve.iloc[-1] - 1) * 100
        calmar = (total_return_pct / abs(max_dd)) if max_dd else None
        profit_factor = float(qs.stats.profit_factor(returns, prepare_returns=False))
    except Exception as e:
        log.warning("Risk metrics computation failed: %s", e)
        return None

    def _clean(x):
        return round(x, 2) if x is not None and x == x and x not in (float("inf"), float("-inf")) else None

    wins = [r for r in pct_returns if r > 0]
    losses = [r for r in pct_returns if r <= 0]

    return {
        "n_trades": len(ordered),
        "sharpe": _clean(sharpe),
        "sortino": _clean(sortino),
        "max_drawdown_pct": _clean(max_dd),
        "calmar": _clean(calmar),
        "profit_factor": _clean(profit_factor),
        "total_return_pct": _clean(total_return_pct),
        "avg_win_pct": _clean(sum(wins) / len(wins)) if wins else None,
        "avg_loss_pct": _clean(sum(losses) / len(losses)) if losses else None,
        "best_trade_pct": _clean(max(pct_returns)),
        "worst_trade_pct": _clean(min(pct_returns)),
    }
