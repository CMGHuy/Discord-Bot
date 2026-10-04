"""v119 market-mode selector for the masked short compression-release strategy.

Broad (SPY bearish) and isolated (SPY not bearish, stock lagging its sector ETF)
are separate arms; a ticker is in at most one. Pure: the live caller passes only
data, the research caller reconstructs the same as-of frames and dated sector
mapping, never today's static sector map.

NO-LOOKAHEAD: each frame is cut to completed bars, then to dates <= the stock's
last completed date. A later sector/SPY bar can never change today's mode.
"""
from __future__ import annotations

import datetime as dt

from swingbot.core.market import earnings_calendar as ec
from swingbot.core.market.session import now_et
from swingbot.core.scanning.strategy_pass import completed_frame

RETURN_WINDOW = 63
EARNINGS_WINDOW_SESSIONS = 10
MAX_SNAPSHOT_AGE_SESSIONS = 5


def _upto(frame, last):
    return frame[frame.index <= last]


def _return_63(frame) -> float:
    close = frame["Close"]
    return float(close.iloc[-1] / close.iloc[-1 - RETURN_WINDOW] - 1.0)


def _aligned(frame, last, reason):
    """Frame trimmed to `last`, or the rejection reason if it does not end there."""
    if frame is None or len(frame) == 0:
        return None, reason.replace("unaligned", "missing")
    trimmed = _upto(frame, last)
    if len(trimmed) == 0 or trimmed.index[-1] != last:
        return None, reason
    return trimmed, None


def compression_mode(stock, spy, sector, *, now, spy_regime) -> tuple[str | None, str | None]:
    """Return ("broad"|"isolated", None) or (None, rejection_reason) for the last completed bar."""
    stock = completed_frame(stock, now)
    if stock is None or len(stock) == 0:
        return None, "missing_stock"
    last = stock.index[-1]
    spy_ok, reason = _aligned(completed_frame(spy, now), last, "unaligned_spy")
    if reason:
        return None, reason
    if spy_regime.trend == "bearish":
        return "broad", None
    sector_ok, reason = _aligned(completed_frame(sector, now), last, "unaligned_sector")
    if reason:
        return None, reason
    if min(len(stock), len(sector_ok)) <= RETURN_WINDOW:
        return None, "short_history"
    if _return_63(stock) < _return_63(sector_ok):
        return "isolated", None
    return None, "not_sector_laggard"


def _reaction_days(report_ts, calendar) -> set:
    """Reaction session(s) of one report; an intraday one counts both readings (conservative)."""
    report = ec.report_from_timestamp(report_ts)
    timings = (ec.BEFORE_OPEN, ec.AFTER_CLOSE) if report.timing == ec.UNCONFIRMED else (report.timing,)
    days = {ec.reaction_session(ec.Report(report.date, t), calendar) for t in timings}
    return days - {None}


def _aware(value) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def earnings_clear_for_ten_sessions(ticker, decision_at, snapshot, calendar) -> tuple[bool, str]:
    """True only when a fresh, verified calendar shows no report reaction in sessions 1-10 after the signal.

    NO-LOOKAHEAD: only `snapshot` as observed at or before `decision_at` is read; a
    snapshot observed later, a failed query, or a stale one never yields True.
    """
    if not _aware(decision_at):
        return False, "earnings_timestamp_invalid"
    if snapshot is None or not snapshot.query_ok:
        return False, "earnings_unknown"
    if snapshot.observed_at > decision_at:
        return False, "earnings_stale"
    signal_day = now_et(decision_at).date()
    age = calendar.sessions_between(now_et(snapshot.observed_at).date(), signal_day)
    if age is None or age > MAX_SNAPSHOT_AGE_SESSIONS:
        return False, "earnings_stale"
    window = calendar.sessions(signal_day + dt.timedelta(days=1), calendar.last)[:EARNINGS_WINDOW_SESSIONS]
    if len(window) < EARNINGS_WINDOW_SESSIONS:
        return False, "earnings_unknown"
    if any(_reaction_days(report, calendar) & set(window) for report in snapshot.reports):
        return False, "earnings_within_window"
    return True, "clear"
