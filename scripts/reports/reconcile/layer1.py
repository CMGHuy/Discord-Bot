"""v232 layer 1: the same plan, backtest outcome against live outcome (spec ### Layer 1).

Every value is gross and in the live trade's risk unit, |live fill - issued stop|.
Nothing here stores or returns an outcome of a plan live did not fill.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r

from . import sessions

FILL_MODELS = ("v1", "v2")
SCRATCH_R = 0.05
OUTCOME_CLASSES = ("win", "loss", "scratch", "timeout")


def live_risk(rec) -> float:
    risk = abs(float(rec.trade["entry"]) - float(rec.plan["stop_loss"]))
    if risk <= 0:
        raise ValueError(f"plan {rec.plan_id}: the live fill sits on the issued stop")
    return risk


def r_live(rec) -> float:
    """Journal R (gross, the trade's own unit) re-expressed in the live unit."""
    own = abs(float(rec.trade["entry"]) - float(rec.trade["stop_loss"]))
    return float(rec.journal["r_realized"]) * own / live_risk(rec)


def _slip(price: float, side: str, bps: float) -> float:
    return abs(apply_frictions(price, side, slippage_bps=bps) - price)


def _exit_fills(trade: dict) -> list[tuple[float, float]]:
    legs = [leg for leg in trade.get("legs") or [] if leg.get("exit_price") is not None]
    if legs:
        return [(float(leg.get("fraction", 1.0)), float(leg["exit_price"])) for leg in legs]
    price = trade.get("exit_price")
    return [(1.0, float(price if price is not None else trade["entry"]))]


def _days_held(trade: dict) -> int:
    opened = sessions.ny_time(trade["opened_at"]).date()
    closed = sessions.ny_time(trade["closed_at"]).date()
    return max(0, (closed - opened).days)


def live_cost_r(rec, frictions: dict) -> float:
    """Modelled costs of the live trade, positive, in live R (borrow on shorts only)."""
    trade, risk = rec.trade, live_risk(rec)
    short = rec.side == "short"
    side_in, side_out = ("sell", "buy") if short else ("buy", "sell")
    bps = frictions["slippage_bps"]
    slip = _slip(float(trade["entry"]), side_in, bps)
    slip += sum(frac * _slip(price, side_out, bps) for frac, price in _exit_fills(trade))
    cost = slip / risk + commission_r(risk_dollars=frictions["commission_risk_basis"],
                                      commission=frictions["commission_per_trade"])
    if short:
        cost += borrow_r(float(trade["entry"]), risk, _days_held(trade))
    return cost


def bar_position(df, day: dt.date) -> int | None:
    if df is None or len(df) == 0:
        return None
    hits = np.flatnonzero(pd.DatetimeIndex(df.index).normalize() == pd.Timestamp(day))
    return int(hits[0]) if len(hits) else None


def outcome_class(outcome: str | None, r: float) -> str:
    """Engine and journal labels kept; a generic close is scratch within SCRATCH_R."""
    if outcome in OUTCOME_CLASSES:
        return outcome
    if abs(r) <= SCRATCH_R:
        return "scratch"
    return "win" if r > 0 else "loss"
