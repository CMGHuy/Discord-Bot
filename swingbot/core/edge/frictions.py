"""Execution frictions: slippage + commission.

The clean backtest fills at exact trigger/stop/target prices. Real fills
don't. 5 bps of slippage per side and a commission per trade is a
conservative-for-liquid-names model (the E12 liquidity screen is what
makes this assumption defensible). Commission is expressed in R against
a fixed risk basis (default $100 risked/trade = 1% of a $10k account)
so the unit-less backtest can subtract it from r_multiple.
"""
from __future__ import annotations

from swingbot import config


def apply_frictions(fill_price: float, side: str, slippage_bps: float | None = None) -> float:
    """Worsen a fill by `slippage_bps`. Buys fill higher, sells fill lower."""
    bps = slippage_bps if slippage_bps is not None else getattr(config, "SLIPPAGE_BPS", 5.0)
    adj = fill_price * bps / 10_000.0
    return fill_price + adj if side == "buy" else fill_price - adj


def commission_r(risk_dollars: float | None = None, commission: float | None = None) -> float:
    """Round-trip commission as an R deduction."""
    basis = risk_dollars if risk_dollars else getattr(config, "COMMISSION_RISK_BASIS", 100.0)
    per_side = commission if commission is not None else getattr(config, "COMMISSION_PER_TRADE", 1.0)
    if basis <= 0:
        return 0.0
    return 2.0 * per_side / basis
