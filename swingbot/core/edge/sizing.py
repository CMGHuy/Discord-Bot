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
