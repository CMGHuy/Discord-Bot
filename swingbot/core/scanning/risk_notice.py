"""v183 Part B: the squeeze / earnings / ex-div snapshot on a short.

Built once, at LIVE plan creation, for a bearish plan while
``config.SHORT_RISK_NOTICE`` is on, and stored on ``TradePlanV2.risk_notice``
for the alert and the plan page to word. It reads caches only --
``short_interest.cached_short_interest`` and ``earnings_calendar.CachedSource``
-- never the network. A cache miss is "not checked", never comfort. Nothing
here is read by a filter, score, confidence or backtest; the snapshot is
display only and never an ``entry_context`` key.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from swingbot import config
from swingbot.core.market import short_interest as si_mod
from swingbot.core.market.earnings_calendar import CachedSource, next_report
from swingbot.core.market.session import now_et, nyse_calendar
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.marketdata import universe
from swingbot.core.marketdata.spot_metals import is_spot_metal

log = logging.getLogger(__name__)

VERSION = 1
_NOT_CHECKED_EARNINGS = {"status": "not_checked", "date": None, "sessions": None}


def _never_reports(ticker) -> bool:
    """Funds and spot metals never report earnings (same rule as events)."""
    return universe.is_etf(ticker) or is_spot_metal(ticker)


def _earnings_source():
    return CachedSource()


def hold_window(plan, signal_date: date) -> tuple[date, date]:
    """Signal bar to the last session a fill could still be held, in NYSE
    sessions; capped at the calendar's last session."""
    cal = nyse_calendar()
    n = int(plan.expiry_bars or 0) + int(HORIZONS[plan.horizon_key]["max_holding_days"])
    end = cal.session_after(signal_date, n) or cal.last
    return signal_date, end


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _is_stale(si_date, today: date) -> bool:
    parsed = _parse_date(si_date) if si_date else None
    if parsed is None:
        return True
    return (today - parsed).days > si_mod.STALE_DAYS


def _at_least(value, threshold) -> bool:
    return value is not None and float(value) >= float(threshold)


def _squeeze(entry: dict) -> bool:
    return (_at_least(entry.get("short_pct_float"), config.SHORT_SQUEEZE_SI_PCT)
            or _at_least(entry.get("days_to_cover"), config.SHORT_SQUEEZE_DTC))


def _short_interest_part(ticker, today: date) -> tuple[str, dict | None]:
    try:
        entry = si_mod.cached_short_interest(ticker)
    except Exception:  # ShortInterestCacheError or any read failure
        return "not_checked", None
    if entry is None:
        si_mod.request_refresh(ticker)
        return "not_checked", None
    return "ok", {**entry, "stale": _is_stale(entry.get("si_date"), today),
                  "squeeze": _squeeze(entry)}


def _earnings_part(ticker, start: date, end: date, source) -> dict:
    if _never_reports(ticker):
        return {"status": "etf", "date": None, "sessions": None}
    if source.reports(ticker) == []:
        return dict(_NOT_CHECKED_EARNINGS)
    report = next_report(ticker, start, source=source)
    if report is None or not start <= report.date <= end:
        return {"status": "none_in_hold", "date": None, "sessions": None}
    return {"status": "in_hold", "date": report.date.isoformat(),
            "sessions": nyse_calendar().sessions_between(start, report.date)}


def _ex_div_part(entry: dict | None, start: date, end: date) -> dict | None:
    ex_div = _parse_date(entry.get("ex_div_date")) if entry and entry.get("ex_div_date") else None
    if ex_div is None or not start <= ex_div <= end:
        return None
    return {"date": ex_div.isoformat(), "per_share": entry.get("div_per_share"),
            "estimated": bool(entry.get("div_estimated"))}


def _safe_earnings(ticker, start: date, end: date, source) -> dict:
    try:
        return _earnings_part(ticker, start, end, source)
    except Exception as exc:
        log.debug("%s: earnings part not checked (%s)", ticker, exc)
        return dict(_NOT_CHECKED_EARNINGS)


def build_risk_notice(plan, signal_date: date, *, now=None, source=None) -> dict:
    now = now or datetime.now(timezone.utc)
    today = now_et(now).date()
    start, end = hold_window(plan, signal_date)
    si_status, si_part = _short_interest_part(plan.ticker, today)
    earnings = _safe_earnings(plan.ticker, start, end, source or _earnings_source())
    return {"version": VERSION, "built_at": now.isoformat(),
            "window": [start.isoformat(), end.isoformat()],
            "si_status": si_status, "short_interest": si_part, "earnings": earnings,
            "ex_div": _ex_div_part(si_part, start, end)}


def degraded_notice(plan, signal_date: date) -> dict:
    """The version-1 shape with every part "not checked"; cannot raise."""
    return {"version": VERSION, "built_at": datetime.now(timezone.utc).isoformat(),
            "window": [signal_date.isoformat(), None],
            "si_status": "not_checked", "short_interest": None,
            "earnings": dict(_NOT_CHECKED_EARNINGS), "ex_div": None}


def _signal_date(plan, df) -> date:
    try:
        if df is not None and len(df):
            return df.index[-1].date()
    except Exception:
        pass  # an odd index falls back to the plan's creation date
    created = _parse_date(plan.created_at) if plan.created_at else None
    return created or now_et().date()


def stamp_risk_notice(plan, df) -> None:
    """Stamp the snapshot on a bearish plan while the switch is on. Never raises."""
    if plan.direction != "bearish" or not config.SHORT_RISK_NOTICE:
        return
    signal = _signal_date(plan, df)
    try:
        plan.risk_notice = build_risk_notice(plan, signal)
    except Exception as exc:
        log.info("%s: risk notice degraded (%s)", plan.ticker, exc)
        plan.risk_notice = degraded_notice(plan, signal)
