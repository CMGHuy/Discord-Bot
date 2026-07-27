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


def sector_heat(open_trades: list, balance: float, sectors: dict) -> dict:
    out: dict = {}
    for t in open_trades:
        sec = sectors.get(t.get("ticker"))
        if sec:
            out[sec] = out.get(sec, 0.0) + trade_risk_pct(t, balance)
    return {k: round(v, 3) for k, v in out.items()}


def sector_check(open_trades: list, balance: float, candidate_ticker: str,
                 candidate_risk_pct: float, sectors: dict,
                 cap_pct: float | None = None) -> dict:
    cap = cap_pct if cap_pct is not None else getattr(config, "SECTOR_HEAT_CAP_PCT", 3.0)
    sec = sectors.get(candidate_ticker)
    if sec is None:
        return {"allowed": True, "sector": None, "sector_heat": 0.0,
                "remaining": cap, "cap": cap}
    heat = sector_heat(open_trades, balance, sectors).get(sec, 0.0)
    remaining = max(0.0, cap - heat)
    return {"allowed": candidate_risk_pct <= remaining + 1e-9, "sector": sec,
            "sector_heat": heat, "remaining": round(remaining, 3), "cap": cap}


def horizon_check(open_trades: list, candidate_horizon: str,
                  max_per_horizon: int | None = None) -> dict:
    cap = max_per_horizon if max_per_horizon is not None else \
        getattr(config, "MAX_OPEN_PER_HORIZON", 4)
    n = sum(1 for t in open_trades if t.get("horizon_key") == candidate_horizon)
    return {"allowed": n < cap, "open_in_horizon": n, "cap": cap}
