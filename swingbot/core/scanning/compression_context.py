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
from zoneinfo import ZoneInfo

from swingbot.core.market import earnings_calendar as ec
from swingbot.core.market.session import RTH_CLOSE, nyse_calendar, now_et
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


def _signal_day(decision_at, calendar, signal_bar_date):
    """The last completed session at `decision_at`: the explicit bar date, else derived from the clock
    (before the close of a session day the in-progress bar is excluded, so the signal bar is the prior session)."""
    if signal_bar_date is not None:
        return signal_bar_date
    et = now_et(decision_at)
    day = et.date()
    if calendar.is_session(day) and et.time() < RTH_CLOSE:
        day -= dt.timedelta(days=1)
    earlier = calendar.sessions(calendar.first, day)
    return earlier[-1] if earlier else None


COMPRESSION_MODES = ("broad", "isolated")


def decision_time_for(bar_date: dt.date) -> dt.datetime:
    """The replay's decision instant for a signal bar: 17:00 ET on its own date, after the close
    (the live scan decides after the same completed bar; the bar is complete, the next is unseen)."""
    return dt.datetime.combine(bar_date, dt.time(17), tzinfo=ZoneInfo("America/New_York"))


def compression_mode_for(stock, spy, sector, *, now) -> tuple[str | None, str | None]:
    """compression_mode with the SPY regime read from SPY's completed bars up to the stock's last date.

    Fails closed (None, reason) when SPY has too little history for a regime.
    NO-LOOKAHEAD: SPY is cut to the stock's last completed date before the regime is read.
    """
    stock_done = completed_frame(stock, now)
    spy_done = completed_frame(spy, now)
    if stock_done is None or len(stock_done) == 0 or spy_done is None or len(spy_done) == 0:
        return compression_mode(stock, spy, sector, now=now, spy_regime=None)
    from swingbot import config
    from swingbot.core.scanning.regime import get_market_regime
    try:
        regime = get_market_regime(_upto(spy_done, stock_done.index[-1]), config.MARKET_REGIME_TICKER)
    except ValueError:
        return None, "spy_regime_unavailable"
    return compression_mode(stock, spy, sector, now=now, spy_regime=regime)


def decide_compression_entry(ticker, frame, *, mode, mode_reason, snapshot, now, calendar=None,
                             allowlist=COMPRESSION_MODES) -> tuple[dict, str | None]:
    """THE pre-entry decision, called before build_strategy_plan by the live pass and the research
    replay alike: (stamp, None) to build a plan, or (stamp, reason) to reject it.

    `mode`/`mode_reason` are compression_mode's verdict; the stamp carries the mode (and the signal bar
    date once admitted) onto the plan. A rejection after the mode is known still carries the mode, so the
    caller can split its counters broad/isolated. No timestamp or snapshot means no admission.
    """
    if mode is None:
        return {}, mode_reason or "no_mode"
    if mode not in allowlist:
        return {}, "mode_not_allowed"
    stamp = {"compression_mode": mode}
    bar_date = frame.index[-1].date()
    if now is None:
        return stamp, "earnings_unknown"
    clear, why = earnings_clear_for_ten_sessions(
        ticker, now, snapshot, calendar or nyse_calendar(), signal_bar_date=bar_date)
    if not clear:
        return stamp, why
    return {**stamp, "compression_bar_date": bar_date.isoformat()}, None


def compression_candidate_decision(ticker, stock, spy, sector, snapshot, *, now, calendar=None,
                                   allowlist=COMPRESSION_MODES) -> tuple[dict, str | None]:
    """Mode selection plus the shared decision, from raw frames: the research replay's entry point."""
    mode, why = compression_mode_for(stock, spy, sector, now=now)
    return decide_compression_entry(ticker, completed_frame(stock, now), mode=mode, mode_reason=why,
                                    snapshot=snapshot, now=now, calendar=calendar, allowlist=allowlist)


def earnings_clear_for_ten_sessions(ticker, decision_at, snapshot, calendar, *, signal_bar_date=None) -> tuple[bool, str]:
    """True only when a fresh, verified calendar shows no report reaction in sessions 1-10 after the signal bar.

    Sessions are counted from the signal bar (`signal_bar_date`, the last completed bar), never from the
    decision date: an intraday or pre-open decision has today as session 1.

    NO-LOOKAHEAD: only `snapshot` as observed at or before `decision_at` is read; a
    snapshot observed later, a failed query, or a stale one never yields True.
    """
    if not _aware(decision_at):
        return False, "earnings_timestamp_invalid"
    if snapshot is None or not snapshot.query_ok:
        return False, "earnings_unknown"
    if snapshot.observed_at > decision_at:
        return False, "earnings_stale"
    signal_day = _signal_day(decision_at, calendar, signal_bar_date)
    if signal_day is None:
        return False, "earnings_unknown"
    age = calendar.sessions_between(now_et(snapshot.observed_at).date(), signal_day)
    if age is None or age > MAX_SNAPSHOT_AGE_SESSIONS:
        return False, "earnings_stale"
    window = calendar.sessions(signal_day + dt.timedelta(days=1), calendar.last)[:EARNINGS_WINDOW_SESSIONS]
    if len(window) < EARNINGS_WINDOW_SESSIONS:
        return False, "earnings_unknown"
    if any(_reaction_days(report, calendar) & set(window) for report in snapshot.reports):
        return False, "earnings_within_window"
    return True, "clear"
