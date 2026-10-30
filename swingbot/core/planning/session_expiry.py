"""v144: why an outlook (next_session) plan was cancelled, in one line.

Four cancellations happen DURING session D through the existing live transitions
(cancelled_invalidated, cancelled_risk_cap, and v187's cancelled_limit and
cancelled_gap_through_stop for a limit entry); `in_session_message` only words
them. v189 adds cancelled_trade_deleted: the placeholder trade was deleted (a
human act, at any time), worded here so the tables stay complete. Two are decided AT D's close by `classify_expiry`, from D's own bars:
`never_triggered` (the common case, with the distance in percent and ATR) and
`no_session_data`.

Data source at close. The hourly cache cannot be trusted to be fresh:
market_data_refresh wakes every MARKET_DATA_REFRESH_MINUTES and
data_refresh.is_stale uses the file mtime against a 4h hourly window, so the
CSV can miss D's last bars. `hourly_session_bar` is used only when it reaches
D's last RTH hour; otherwise D's daily bar (RTH-only, so its high/low is the
RTH extreme). NO-LOOKAHEAD: this runs after D closed, and the ATR is read from
bars strictly before D.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass

import pandas as pd

from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, session_close

NEVER_TRIGGERED = "never_triggered"
NO_SESSION_DATA = "no_session_data"
INVALIDATED = "invalidated"
RISK_CAP = "risk_cap"
LIMIT_CANCELLED = "limit_cancelled"
GAP_THROUGH_STOP = "gap_through_stop"
TRADE_DELETED = "trade_deleted"            # v189 A7

REASON_CODE = "reason_code"
REASON_MESSAGE = "reason_message"

_IN_SESSION_CODES = {
    "cancelled_invalidated": INVALIDATED,
    "cancelled_risk_cap": RISK_CAP,
    "cancelled_limit": LIMIT_CANCELLED,
    "cancelled_gap_through_stop": GAP_THROUGH_STOP,
    "cancelled_trade_deleted": TRADE_DELETED,
}
_ATR_PERIOD = 14


@dataclass(frozen=True)
class SessionBar:
    high: float
    low: float
    source: str          # "hourly" | "daily"


@dataclass(frozen=True)
class Verdict:
    code: str
    message: str


def _et_index(frame) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(frame.index)
    if index.tz is None:
        index = index.tz_localize("UTC")      # the hourly cache is written in UTC
    return index.tz_convert(US_MARKET_TZ)


def hourly_session_bar(hourly, day: dt.date) -> SessionBar | None:
    """D's RTH high/low from hourly bars, or None unless the bars reach D's
    last RTH hour (a bar starting within an hour of D's official close)."""
    if hourly is None or len(hourly) == 0:
        return None
    index = _et_index(hourly)
    open_at = dt.datetime.combine(day, RTH_OPEN, tzinfo=US_MARKET_TZ)
    close_at = dt.datetime.combine(day, session_close(day), tzinfo=US_MARKET_TZ)
    mask = (index >= open_at) & (index < close_at)
    if not mask.any() or index[mask].max() < close_at - dt.timedelta(hours=1):
        return None
    rows = hourly.loc[mask]
    return SessionBar(float(rows["High"].max()), float(rows["Low"].min()), "hourly")


def daily_session_bar(daily, day: dt.date) -> SessionBar | None:
    """D's daily bar (RTH-only), or None when the frame has no row dated D."""
    if daily is None or len(daily) == 0:
        return None
    rows = daily.loc[pd.DatetimeIndex(daily.index).date == day]
    if len(rows) == 0:
        return None
    return SessionBar(float(rows["High"].iloc[-1]), float(rows["Low"].iloc[-1]), "daily")


def session_bar(day: dt.date, *, hourly, daily) -> SessionBar | None:
    return hourly_session_bar(hourly, day) or daily_session_bar(daily, day)


def atr_before(daily, day: dt.date) -> float | None:
    """ATR(14) on the bars strictly before D; None when there are too few."""
    from swingbot.core.market.indicators import atr
    if daily is None or len(daily) == 0:
        return None
    prior = daily.loc[pd.DatetimeIndex(daily.index).date < day]
    if len(prior) <= _ATR_PERIOD:
        return None
    value = float(atr(prior, _ATR_PERIOD).iloc[-1])
    return value if math.isfinite(value) and value > 0 else None


def _never_triggered_message(plan, bar: SessionBar, atr_value: float | None) -> str:
    bull = plan.direction == "bullish"
    word, extreme = ("High", bar.high) if bull else ("Low", bar.low)
    trigger = float(plan.trigger_price)
    gap = (trigger - extreme) if bull else (extreme - trigger)
    if gap <= 0:
        return (f"{word} {extreme:.2f} reached the {trigger:.2f} trigger between polls; "
                "no live print filled it")
    atr_part = f" ({gap / atr_value:.1f} ATR)" if atr_value else ""
    return f"{word} {extreme:.2f} stopped {gap / trigger * 100:.1f}%{atr_part} short of the {trigger:.2f} trigger"


def classify_expiry(plan, day: dt.date, *, hourly, daily) -> Verdict:
    """The close-time reason for an outlook plan still PENDING at D's close."""
    bar = session_bar(day, hourly=hourly, daily=daily)
    if bar is None:
        return Verdict(NO_SESSION_DATA, f"No price data for {day.isoformat()}; plan expired unevaluated")
    return Verdict(NEVER_TRIGGERED, _never_triggered_message(plan, bar, atr_before(daily, day)))


def _risk_cap_message(plan, detail: dict) -> str:
    fill, trigger = float(detail["entry_price"]), float(plan.trigger_price)
    lead = (f"Gapped to {fill:.2f} past the {trigger:.2f} trigger" if abs(fill - trigger) > 1e-9
            else f"Triggered at {fill:.2f}")
    return (f"{lead}; the stop distance ({float(detail['planned_loss_pct']):.1f}%) "
            f"is over the {float(detail['max_planned_loss_pct']):g}% cap")


def _limit_cancelled_message(plan, detail: dict) -> str:
    return (f"Ran to {float(detail['live_price']):.2f}, past the "
            f"{float(detail['limit_cancel_level']):.2f} cancel level, before the "
            f"{float(plan.trigger_price):.2f} limit filled")


def _gap_through_stop_message(plan, detail: dict) -> str:
    return (f"Touched the {float(plan.trigger_price):.2f} limit at "
            f"{float(detail['live_price']):.2f}, already at or through the "
            f"{float(plan.stop_loss):.2f} stop; nothing opened")


def _trade_deleted_message(plan, detail: dict) -> str:
    return "The trade record was deleted before the order filled; nothing opened"


#: v187 D3: the limit-entry cancellations, worded from their own detail keys.
_LIMIT_MESSAGES = {
    "cancelled_limit": _limit_cancelled_message,
    "cancelled_gap_through_stop": _gap_through_stop_message,
    "cancelled_trade_deleted": _trade_deleted_message,
}


def in_session_message(plan, transition: str, detail: dict) -> str | None:
    """Words for the in-session cancellations; None for anything else."""
    if transition == "cancelled_invalidated":
        return (f"Traded {float(detail['live_price']):.2f} through the {float(plan.stop_loss):.2f} "
                "stop before triggering; the setup broke")
    if transition == "cancelled_risk_cap":
        return _risk_cap_message(plan, detail)
    builder = _LIMIT_MESSAGES.get(transition)
    return builder(plan, detail) if builder is not None else None


def code_for(transition: str) -> str | None:
    return _IN_SESSION_CODES.get(transition)


def cancel_reason(plan) -> str | None:
    """The reason recorded on the plan's CANCELLED transition, or None."""
    return next((entry.get("reason") for entry in reversed(plan.status_history or [])
                 if entry.get("status") == "CANCELLED"), None)
