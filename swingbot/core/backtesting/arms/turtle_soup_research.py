"""v180's Turtle Soup research cell for ``StrategyEngine``.

It covers four things:

- the knob (``TURTLE_SOUP_RESEARCH_MODE``: ``off`` | ``structural``);
- the one open cell, ("bullish", "2w"), which is fixed and never the horizon being replayed;
- the cost model for the cell's rows, which is the screen's: 5 bps a side plus ``commission_r()``
  (``expectancy_attribution.net_r``);
- the per-signal events the diagnostics read.

Nothing here is read by the live bot.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.planning.next_open_entry import OPEN_THROUGH_STOP, RISK_CAP

RESEARCH_KNOB = "TURTLE_SOUP_RESEARCH_MODE"
RESEARCH_MODES = ("off", "structural")
HORIZON = "2w"
#: The live mask ({"directions": ()}) plus ("bullish", "2w") only.
RESEARCH_CELL = {"directions": (), "cells": {("bullish", HORIZON)}}
CANCEL_STATUS = {OPEN_THROUGH_STOP: "cancelled_open_through_stop", RISK_CAP: "cancelled_risk_cap_fill"}


def research_mode() -> str:
    """The research knob's current value ("off" | "structural")."""
    return getattr(config, RESEARCH_KNOB, "off")


def net_r(plan, result) -> float:
    """The row's R net of the screen's costs, recomputed from the fill and the exit legs."""
    from swingbot.core.analytics import expectancy_attribution
    return expectancy_attribution.net_r(result.entry_price, plan.stop_loss, plan.direction, result.legs)


def _base(ticker, signal_date, status) -> dict:
    return {"ticker": ticker, "signal_date": signal_date, "status": status}


def trade_event(ticker, df, signal_date, plan, result, r_net) -> dict:
    """One scored Turtle Soup signal: fill and exit dates, why it closed, gross and net R."""
    leg = result.legs[-1] if result.legs else {}
    return {
        **_base(ticker, signal_date, "trade"),
        "entry_date": str(df.index[result.entry_index].date()),
        "exit_date": str(df.index[result.exit_index].date()),
        "entry_index": result.entry_index,
        "exit_index": result.exit_index,
        "hold_sessions": int(result.exit_index - result.entry_index + 1),
        "outcome": result.outcome,
        "exit_reason": leg.get("reason") or result.outcome,
        "r_gross": result.r_total,
        "r_net": r_net,
        "entry_price": result.entry_price,
        "stop_loss": plan.stop_loss,
        "tp1": plan.tp1,
    }


def cancel_event(ticker, signal_date, cancel_reason) -> dict:
    """A counted candidate whose walk produced no trade (open through the stop, fill risk cap...)."""
    return _base(ticker, signal_date, CANCEL_STATUS.get(cancel_reason, "not_triggered"))


def plan_none_event(ticker, signal_date) -> dict:
    """A counted candidate the constructor returned no plan for (no level in the R:R band)."""
    return _base(ticker, signal_date, "plan_none")
