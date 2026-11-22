"""Execution frictions: slippage, commission and (v182) the short borrow fee.

The clean backtest fills at exact trigger/stop/target prices. Real fills
don't. 5 bps of slippage per side and a commission per trade is a
conservative-for-liquid-names model (the E12 liquidity screen is what
makes this assumption defensible). Commission is expressed in R against
a fixed risk basis (default $100 risked/trade = 1% of a $10k account)
so the unit-less backtest can subtract it from r_multiple.

v238: ``net_r_legs`` is the one net-R function for arm rows (replay arms
now, live journal rows in v231): the screen's net formula over weighted
exit legs, borrow charged on shorts only.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

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


#: v182: the stock-borrow fee a short pays, a year. S&P 500 names are
#: general-collateral borrows (about 0.25-0.5%); 0.5% is the conservative end.
BORROW_RATE_ANNUAL = 0.005


def borrow_r(entry, risk, days):
    """The borrow fee of a short held ``days`` calendar days, in R:
    entry x BORROW_RATE_ANNUAL / 365 x days / risk. Elementwise on arrays.
    Never charged on a long trade (v182)."""
    return entry * BORROW_RATE_ANNUAL / 365.0 * days / risk


#: v238: the direction spellings net_r_legs accepts -> the side they trade.
#: Arm rows say bullish/bearish; the screen says long/short.
NET_R_SIDES = {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}

_FRACTION_TOLERANCE = 1e-9


def _checked_side(direction: str, risk: float, legs: Sequence[Mapping]) -> str:
    """The side ``direction`` trades, or ValueError for input net_r_legs cannot price."""
    side = NET_R_SIDES.get(direction)
    if side is None:
        raise ValueError(f"unknown direction {direction!r}; expected one of {sorted(NET_R_SIDES)}")
    if not legs:
        raise ValueError("net_r_legs needs at least one exit leg")
    if risk == 0:
        raise ValueError("net_r_legs needs a non-zero stop distance")
    total = sum(float(leg["fraction"]) for leg in legs)
    if abs(total - 1.0) > _FRACTION_TOLERANCE:
        raise ValueError(f"leg fractions sum to {total!r}, not 1")
    return side


def net_r_legs(entry: float, stop_loss: float, direction: str, legs: Sequence[Mapping], *,
               days: float) -> float:
    """R net of costs for one trade from its entry and its exit legs (v238).

    Risk is the PLANNED stop distance ``abs(entry - stop_loss)``, never re-based on
    the slipped fill (the screen's ``sides.net_r`` convention). The entry is slipped
    against the trade, every leg's ``exit_price`` is slipped on the exit side and
    weighted by its ``fraction``; one round-trip ``commission_r()`` comes off; a short
    also pays ``borrow_r(entry, risk, days)`` over ``days`` calendar days held, a long
    never reads ``days``. A leg's recorded ``r`` is ignored. ValueError on no legs, a
    zero stop distance, an unknown direction, or fractions not summing to 1 (+-1e-9)."""
    entry, stop_loss = float(entry), float(stop_loss)
    risk = abs(entry - stop_loss)
    side = _checked_side(direction, risk, legs)
    is_long = side == "long"
    entry_fill = apply_frictions(entry, "buy" if is_long else "sell")
    sign = 1.0 if is_long else -1.0
    gross = 0.0
    for leg in legs:
        exit_fill = apply_frictions(float(leg["exit_price"]), "sell" if is_long else "buy")
        gross += float(leg["fraction"]) * (exit_fill - entry_fill) * sign / risk
    net = gross - commission_r()
    if not is_long:
        net -= borrow_r(entry, risk, days)
    return float(net)
