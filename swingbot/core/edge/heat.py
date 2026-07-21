"""Portfolio heat: the sum of risk-to-stop across every open position,
as a percent of equity. Heat is what actually hits the account when a
correlated gap takes every stop out on the same morning -- capping it is
survival, not style. Blocking is FLAGGED, never hidden: the alert still
posts, labeled, with size 0, so the operator always sees what the cap
cost them and can free heat deliberately."""
from __future__ import annotations

from swingbot import config


def trade_risk_pct(trade: dict, balance: float) -> float:
    if trade.get("risk_pct") is not None:
        return float(trade["risk_pct"])
    entry = float(trade.get("entry", 0.0))
    stop = float(trade.get("stop_loss", 0.0))
    shares = float(trade.get("shares", 0.0))
    if balance <= 0:
        return 0.0
    return abs(entry - stop) * shares / balance * 100.0


def open_heat(open_trades: list, balance: float) -> float:
    return sum(trade_risk_pct(t, balance) for t in open_trades)


def heat_check(open_trades: list, balance: float, candidate_risk_pct: float,
               cap_pct: float | None = None) -> dict:
    cap = cap_pct if cap_pct is not None else getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)
    heat = open_heat(open_trades, balance)
    remaining = max(0.0, cap - heat)
    return {
        "allowed": candidate_risk_pct <= remaining + 1e-9,
        "open_heat": round(heat, 3),
        "remaining": round(remaining, 3),
        "cap": cap,
    }
