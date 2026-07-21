"""Fractional-Kelly and volatility-targeted position sizing.

Kelly derivation (two-outcome approximation over R multiples):
    b  = avg_win_r / avg_loss_r        (payoff odds per unit risked)
    f* = p - q/b                       (p = win rate, q = 1-p)
f* is the growth-optimal fraction of equity to risk -- and also the
fraction at which drawdowns become psychologically unsurvivable, which
is why nobody sane trades full Kelly. We take a QUARTER of it
(KELLY_FRACTION_CAP) and then clamp to [0.25%, 2.0%] of equity. These
constants are frozen by the Edge plan's Global Constraints: nothing in
code may raise effective risk beyond them.
"""
from __future__ import annotations

import math

KELLY_FRACTION_CAP = 0.25   # quarter-Kelly ceiling -- FROZEN
RISK_FLOOR_PCT = 0.25       # never size below this (min position still tradeable)
RISK_CEILING_PCT = 2.0      # never size above this -- FROZEN
KELLY_MIN_SAMPLE = 30       # below this N a Kelly estimate is noise


def kelly_fraction(win_rate: float, avg_win_r: float, avg_loss_r: float) -> float:
    """Full-Kelly fraction f* = p - q/b, floored at 0 (no edge -> no bet)."""
    if avg_win_r <= 0 or avg_loss_r <= 0:
        return 0.0
    b = avg_win_r / avg_loss_r
    f = win_rate - (1.0 - win_rate) / b
    return max(0.0, f)


def kelly_risk_pct(stats: dict, cap: float = KELLY_FRACTION_CAP) -> float:
    """Quarter-Kelly of the strategy's own stats as a percent of equity,
    clamped to [RISK_FLOOR_PCT, RISK_CEILING_PCT]."""
    if stats.get("n", 0) < KELLY_MIN_SAMPLE:
        return RISK_FLOOR_PCT
    f = kelly_fraction(stats.get("win_rate", 0.0),
                       stats.get("avg_win_r", 0.0),
                       stats.get("avg_loss_r", 1.0))
    pct = f * cap * 100.0
    return max(RISK_FLOOR_PCT, min(pct, RISK_CEILING_PCT))


def vol_target_risk_pct(ticker_atr_pct: float,
                        portfolio_target_daily_vol_pct: float = 0.7,
                        open_positions: int = 0,
                        stop_cap_pct: float = 3.0) -> float:
    """Risk% such that this position's expected daily equity impact stays
    inside its share of the portfolio vol budget.

    Model (transparent, documented so the walk-forward harness can audit):
      - per-position vol budget = target / sqrt(open_positions + 1)
        (sqrt because independent positions add in quadrature)
      - position notional (as % of equity) = budget / ticker_atr_pct * 100
      - stop distance = 2*ATR, capped at stop_cap_pct (the horizon caps
        already bound stops; beyond the cap high-ATR names lose notional
        AND risk -- which is the point)
      - risk% = notional% * stop% / 100
    """
    if ticker_atr_pct <= 0:
        return RISK_FLOOR_PCT
    budget = portfolio_target_daily_vol_pct / math.sqrt(open_positions + 1)
    notional_pct = budget / ticker_atr_pct * 100.0
    stop_pct = min(2.0 * ticker_atr_pct, stop_cap_pct)
    risk = notional_pct * stop_pct / 100.0
    return max(RISK_FLOOR_PCT, min(risk, RISK_CEILING_PCT))


def effective_risk_pct(config_risk: float, kelly_risk: float | None = None,
                       vol_risk: float | None = None,
                       throttle_mult: float = 1.0) -> float:
    """THE sizing chain: min of every estimate that exists, then the
    drawdown/streak throttle multiplies the survivor. throttle_mult == 0
    means the kill switch / pause rung -- risk is exactly 0, not floored."""
    candidates = [config_risk]
    if kelly_risk is not None:
        candidates.append(kelly_risk)
    if vol_risk is not None:
        candidates.append(vol_risk)
    base = min(candidates)
    if throttle_mult <= 0:
        return 0.0
    return max(RISK_FLOOR_PCT, base * throttle_mult) if base > 0 else 0.0
