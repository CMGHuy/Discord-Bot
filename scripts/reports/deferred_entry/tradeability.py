"""v229 tradeability record (spec § Tradeability record). A deferred fill is
a different trade from the plan's, so each pair records what a follow-on
would need to judge it. Disclosure only: nothing here gates a verdict."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from swingbot.core.market import opex
from swingbot.core.market.market_events import FOMC_DECISION_DATES
from swingbot.core.market.session import RTH_CLOSE, nyse_calendar

from .bars import BAR_MINUTES, ET, et_date, session_close_utc, session_open, to_utc
from .simulate import SIGN

FLAG_KEYS = ("earnings_after_close", "monthly_opex", "fomc", "event_day")
_STOP_PREFIXES = ("loss", "stop")


def _default_earnings(ticker: str) -> list:
    from swingbot.core.market.events import get_earnings_datetimes
    return get_earnings_datetimes(ticker)


def _after_close_on(stamps, entry_date: dt.date) -> bool:
    for stamp in stamps:
        ts = pd.Timestamp(stamp)
        local = ts.tz_localize(ET) if ts.tzinfo is None else ts.tz_convert(ET)
        if local.date() == entry_date and local.time() >= RTH_CLOSE:
            return True
    return False


def event_flags(ticker: str, entry_date: dt.date, *, earnings_lookup=None) -> dict:
    lookup = earnings_lookup or _default_earnings
    try:
        earnings = _after_close_on(lookup(ticker) or [], entry_date)
    except Exception:  # noqa: BLE001 -- an unknown earnings date never fails a pair
        earnings = None
    monthly = opex.opex_tier(entry_date) == opex.MONTHLY
    fomc = entry_date in FOMC_DECISION_DATES
    return {"earnings_after_close": earnings, "monthly_opex": monthly, "fomc": fomc,
            "event_day": bool(earnings) or monthly or fomc}


def _entry_bar_start(bars, opened_at) -> pd.Timestamp:
    if bars is not None and not bars.empty:
        before = bars.index[bars.index <= opened_at]
        if len(before):
            return before[-1]
    return opened_at.floor(f"{BAR_MINUTES}min")


def entry_bar_stopout(bars, *, opened_at, closed_at, live_reason) -> bool:
    """The live trade was stopped inside the bar containing its entry."""
    reason = (live_reason or "").strip().lower()
    if closed_at is None or not reason.startswith(_STOP_PREFIXES):
        return False
    start = _entry_bar_start(bars, opened_at)
    return closed_at < start + pd.Timedelta(minutes=BAR_MINUTES)


def plan_expired(plan_created_at, expiry_bars, entry_date: dt.date) -> tuple[bool | None, int | None]:
    try:
        created = et_date(to_utc(plan_created_at))
    except ValueError:
        return None, None
    sessions = nyse_calendar().sessions_between(created, entry_date)
    if sessions is None:
        return None, None
    try:
        limit = int(float(expiry_bars))
    except (TypeError, ValueError):
        return None, sessions
    return sessions >= limit, sessions


def day_extreme(bars, *, direction: str, session_start, deferral) -> float | None:
    """The day's adverse extreme before 15:30: the low (long) or high (short)."""
    window = bars[(bars.index >= session_start) & (bars.index < deferral)]
    if window.empty:
        return None
    return float(window["Low"].min()) if SIGN[direction] > 0 else float(window["High"].max())


def first_gap_r(bars, *, direction: str, risk: float, start, exit_ts) -> float | None:
    """The first overnight gap inside [start, exit_ts], in R; None without one."""
    if start is None or exit_ts is None:
        return None
    window = bars[(bars.index >= start) & (bars.index <= to_utc(exit_ts))]
    days = window.index.tz_convert(ET).date
    for i in range(1, len(window)):
        if days[i] != days[i - 1]:
            gap = float(window["Open"].iloc[i]) - float(window["Close"].iloc[i - 1])
            return SIGN[direction] * gap / risk
    return None


def _last_close_before(bars, d: dt.date, deferral) -> float | None:
    window = bars[(bars.index >= session_open(d)) & (bars.index < deferral)]
    return None if window.empty else float(window["Close"].iloc[-1])


def _bar_1530(bars, d: dt.date, deferral, sign: int, risk: float) -> dict:
    bar = bars.loc[deferral]
    session = bars[(bars.index >= session_open(d)) & (bars.index < session_close_utc(d))]
    last_close = float(session["Close"].iloc[-1])
    return {"volume": float(bar["Volume"]),
            "range_r": (float(bar["High"]) - float(bar["Low"])) / risk,
            "open_vs_last_close_r": sign * (float(bar["Open"]) - last_close) / risk}


def _levels(sign: int, risk: float, entry: float, stop: float, arm_a, low) -> dict:
    return {
        "fill_vs_entry_r": sign * (arm_a.fill - entry) / risk,
        "fill_above_entry": bool(arm_a.fill > entry),
        "day_low": low,
        "shifted_stop_above_day_low": None if low is None else bool(sign * (arm_a.stop - low) > 0),
        "day_low_vs_stop_r": None if low is None else sign * (low - stop) / risk,
    }


def _gaps(bars, direction: str, risk: float, opened_at, deferral, arms: dict) -> dict:
    starts = {"C": opened_at, "A": deferral, "B": deferral if arms["B"].taken else None}
    return {name: first_gap_r(bars, direction=direction, risk=risk, start=starts[name],
                              exit_ts=arms[name].exit_ts) for name in ("C", "A", "B")}


def record(bars, *, direction: str, entry: float, stop: float, tp1: float, opened_at,
           deferral, arms: dict, plan_created_at, expiry_bars, closed_at, live_reason,
           flags: dict) -> dict:
    """The tradeability record of one pair; ``deferral`` is the 15:30 bar's start."""
    sign, risk, d = SIGN[direction], abs(entry - stop), et_date(opened_at)
    low = day_extreme(bars, direction=direction, session_start=session_open(d), deferral=deferral)
    last = _last_close_before(bars, d, deferral)
    expired, sessions = plan_expired(plan_created_at, expiry_bars, d)
    return {
        **_levels(sign, risk, entry, stop, arms["A"], low),
        "price_1530_vs_entry_r": None if last is None else sign * (last - entry) / risk,
        "first_gap_r": _gaps(bars, direction, risk, opened_at, deferral, arms),
        "bar_1530": _bar_1530(bars, d, deferral, sign, risk),
        "plan_expired": expired,
        "sessions_since_plan": sessions,
        "entry_bar_stopout": entry_bar_stopout(bars, opened_at=opened_at, closed_at=closed_at,
                                               live_reason=live_reason),
        **{key: flags[key] for key in FLAG_KEYS},
    }
