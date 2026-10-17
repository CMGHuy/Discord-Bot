"""v2 costs (v136 spec section 2): slippage and commission, converted to R
once, at booking, with the trade's own risk per share.

The v2 walk records raw legs -- the fill prices fills.py produced -- and hands
them to ``book`` exactly once per trade. Rules (v157 controller decisions 5, 6):

* the entry slips against the trader at ``slippage_bps`` (a bull buys higher);
* an exit of kind ``"stop"`` slips at ``stop_slippage_bps``; kinds
  ``"target"`` and ``"close"`` (timeout, acceptance, stall, a runner stall at
  the open) at ``slippage_bps``;
* risk = |slipped entry - stop_loss|; leg r = ((slipped exit - slipped entry)
  * sign - 2 * commission_per_share) / risk;
* each leg's r is rounded to 3 dp for display; r_total is the rounded sum of
  fraction * UNROUNDED r, so nothing is rounded twice.

Prices in the returned legs stay raw: costs show only in r. The v1 friction
code (``edge/frictions.py``, config SLIPPAGE_BPS/COMMISSION_*) is v1-only and
never read here.
"""
from __future__ import annotations

from .contract import CostModel

EXIT_KINDS = ("stop", "target", "close")
_BPS = 10_000.0


def slip(price: float, *, buy: bool, bps: float) -> float:
    """`price` moved `bps` basis points against the trader: up for a buy."""
    factor = bps / _BPS
    return price * (1.0 + factor) if buy else price * (1.0 - factor)


def exit_bps(cost_model: CostModel, kind: str) -> float:
    """The slippage an exit of `kind` pays."""
    if kind not in EXIT_KINDS:
        raise ValueError(f"exit kind must be one of {EXIT_KINDS}, got {kind!r}")
    return cost_model.stop_slippage_bps if kind == "stop" else cost_model.slippage_bps


def book(cost_model: CostModel, *, direction: str, entry_price: float, stop_loss: float,
         legs: list[dict]) -> tuple[float, list[dict]]:
    """(r_total, booked legs) for one trade's raw legs.

    In: legs ``{"fraction", "exit_price", "reason", "kind"}`` at raw fill
    prices. Out: ``{"fraction", "exit_price", "r", "reason"}`` per leg, the
    exit price still raw, r net of slippage and commission."""
    bull = direction == "bullish"
    sign = 1 if bull else -1
    entry = slip(entry_price, buy=bull, bps=cost_model.slippage_bps)
    risk = (entry - stop_loss) * sign
    if risk <= 0:
        raise ValueError(f"entry {entry_price} is at or beyond the stop {stop_loss}")
    commission = 2.0 * cost_model.commission_per_share
    total, booked = 0.0, []
    for leg in legs:
        exit_px = slip(leg["exit_price"], buy=not bull, bps=exit_bps(cost_model, leg["kind"]))
        r = ((exit_px - entry) * sign - commission) / risk
        total += leg["fraction"] * r
        booked.append({"fraction": leg["fraction"], "exit_price": leg["exit_price"],
                       "r": round(r, 3), "reason": leg["reason"]})
    return round(total, 3), booked
