"""v232 layer 1: the same plan, backtest outcome against live outcome (spec ### Layer 1).

Every value is gross and in the live trade's risk unit, |live fill - issued stop|.
Nothing here stores or returns an outcome of a plan live did not fill.
"""
from __future__ import annotations

import dataclasses
import datetime as dt

import numpy as np
import pandas as pd

from swingbot.core.analytics.metrics import r_multiple
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.edge.frictions import apply_frictions, borrow_r, commission_r
from swingbot.core.planning import exit_sim, exit_sim_v2

from . import records, sessions

FILL_MODELS = ("v1", "v2")
SCRATCH_R = 0.05
OUTCOME_CLASSES = ("win", "loss", "scratch", "timeout")
NO_FILL_OUTCOMES = ("not_triggered", "no_trade")
GAP_REASON = "gap_through_stop"
#: v2 fills, zero costs (the confluence_limit_replay.py precedent): every value is gross.
GROSS_V2 = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)


def live_risk(rec) -> float:
    risk = abs(float(rec.trade["entry"]) - float(rec.plan["stop_loss"]))
    if risk <= 0:
        raise ValueError(f"plan {rec.plan_id}: the live fill sits on the issued stop")
    return risk


R_SOURCES = ("journal", "trade")


def live_r_source(rec) -> tuple[str | None, float | None]:
    """The live R in the trade's own unit and where it came from: the journal's r_realized,
    else the app's own definition metrics.r_multiple(trade); (None, None) when neither."""
    journal_r = (rec.journal or {}).get("r_realized")
    if journal_r is not None:
        return "journal", float(journal_r)
    trade_r = r_multiple(rec.trade)
    return ("trade", float(trade_r)) if trade_r is not None else (None, None)


def r_live(rec) -> float:
    """Live R (gross, the trade's own unit, see live_r_source) in the live unit."""
    _, own_r = live_r_source(rec)
    if own_r is None:
        raise ValueError(f"plan {rec.plan_id}: no R in the journal or the trade doc")
    own = abs(float(rec.trade["entry"]) - float(rec.trade["stop_loss"]))
    return own_r * own / live_risk(rec)


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


@dataclasses.dataclass(frozen=True)
class Values:
    fill_model: str
    r_exit_only: float
    exit_only_outcome: str
    exit_only_class: str
    r_as_backtest: float | None
    r_rebased: float | None
    stop_shift_pct: float | None
    backtest_no_fill: bool


def _v1_engine(df, index, plan, scale_out):
    return exit_sim.simulate_exit(df, index, plan, scale_out=scale_out)


def _v2_engine(df, index, plan, scale_out):
    return exit_sim_v2.simulate_exit_v2(df, index, plan, GROSS_V2, scale_out=scale_out)


def _v1_from_fill(df, index, price, plan, scale_out):
    return exit_sim.simulate_exit_from_fill(df, index, price, plan, scale_out=scale_out,
                                            fill_bar_check=False)


def _v2_from_fill(df, index, price, plan, scale_out):
    return exit_sim_v2.simulate_exit_v2_from_fill(df, index, price, plan, GROSS_V2,
                                                  scale_out=scale_out, fill_bar_check=False)


_ENGINES = {"v1": (_v1_engine, _v1_from_fill), "v2": (_v2_engine, _v2_from_fill)}


def _engines(fill_model: str):
    if fill_model not in _ENGINES:
        raise ValueError(f"unknown fill model {fill_model!r}; known: {FILL_MODELS}")
    return _ENGINES[fill_model]


def _no_fill(result) -> bool:
    if result.entry_index is None or result.outcome in NO_FILL_OUTCOMES:
        return True
    return any(leg.get("reason") == GAP_REASON for leg in result.legs or [])


def _signal_day(rec) -> dt.date:
    return sessions.issue_session(sessions.stamp_source(rec.plan)[0])


def _position(df, day: dt.date, what: str, rec) -> int:
    pos = bar_position(df, day)
    if pos is None:
        raise ValueError(f"plan {rec.plan_id}: no {what} bar on {day}")
    return pos


def score(rec, df, fill_model: str) -> Values:
    """R_exit_only and R_as_backtest of one scored trade under one fill model."""
    engine, from_fill = _engines(fill_model)
    risk, stop = live_risk(rec), float(rec.plan["stop_loss"])
    fill_pos = _position(df, sessions.issue_session(rec.trade["opened_at"]), "fill", rec)
    signal_pos = _position(df, _signal_day(rec), "signal", rec)
    plan, scale_out = records.rehydrate(rec.plan)
    exit_only = from_fill(df, fill_pos, float(rec.trade["entry"]), plan, scale_out)
    r_exit = float(exit_only.r_total)          # its risk is |live fill - issued stop|
    common = dict(fill_model=fill_model, r_exit_only=r_exit,
                  exit_only_outcome=exit_only.outcome,
                  exit_only_class=outcome_class(exit_only.outcome, r_exit))
    plan, scale_out = records.rehydrate(rec.plan)
    backtest = engine(df, signal_pos, plan, scale_out)
    if _no_fill(backtest):
        return Values(**common, r_as_backtest=None, r_rebased=None, stop_shift_pct=None,
                      backtest_no_fill=True)
    distance = abs(float(backtest.entry_price) - stop)
    return Values(**common, r_as_backtest=float(backtest.r_total) * distance / risk,
                  r_rebased=float(backtest.r_total),
                  stop_shift_pct=(distance / risk - 1.0) * 100.0, backtest_no_fill=False)


def effects(r_live: float, v: Values) -> dict:
    """Exit and entry effects in live R; they telescope to r_live - r_as_backtest."""
    entry = None if v.r_as_backtest is None else v.r_exit_only - v.r_as_backtest
    return {"exit": r_live - v.r_exit_only, "entry": entry}


def would_fill(rec, df, fill_model: str) -> bool | None:
    """Whether the backtest entry rule fills an unfilled plan: yes / no only."""
    engine, _ = _engines(fill_model)
    pos = bar_position(df, _signal_day(rec))
    if pos is None:
        return None
    plan, scale_out = records.rehydrate(rec.plan)
    return not _no_fill(engine(df, pos, plan, scale_out))
