import datetime as dt
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from swingbot.core.market import events
from swingbot.core.market.session import nyse_calendar
from swingbot.core.scanning import strategy_pass as sp
from swingbot.core.scanning.compression_context import earnings_clear_for_ten_sessions as gate
from tests.helpers import make_ohlcv

ET, UTC, CAL = ZoneInfo("America/New_York"), dt.timezone.utc, nyse_calendar()
SIGNAL = dt.datetime(2026, 9, 17, 17, tzinfo=ET)  # Thursday, after close
SESSIONS = CAL.sessions(dt.date(2026, 9, 18), dt.date(2026, 10, 20))  # SESSIONS[0] is session 1


def _snap(*reports, observed=SIGNAL, ok=True):
    return events.EarningsSnapshot(observed_at=observed, reports=tuple(reports), query_ok=ok, source="test")


def _before_open(day):
    return dt.datetime.combine(day, dt.time(7), tzinfo=ET)


def _after_close(day):
    return dt.datetime.combine(day, dt.time(16, 30), tzinfo=ET)


def test_missing_or_failed_calendar_is_unknown_never_clear():
    assert gate("ABC", SIGNAL, None, CAL) == (False, "earnings_unknown")
    assert gate("ABC", SIGNAL, _snap(ok=False), CAL) == (False, "earnings_unknown")


@pytest.mark.parametrize("n", [1, 10])
def test_before_open_report_on_session_one_or_ten_rejects(n):
    assert gate("ABC", SIGNAL, _snap(_before_open(SESSIONS[n - 1])), CAL) == (False, "earnings_within_window")


def test_before_open_report_on_session_eleven_passes():
    assert gate("ABC", SIGNAL, _snap(_before_open(SESSIONS[10])), CAL) == (True, "clear")


def test_after_close_report_reacts_next_session():
    assert gate("ABC", SIGNAL, _snap(_after_close(SESSIONS[9])), CAL) == (True, "clear")  # reaction = session 11
    assert gate("ABC", SIGNAL, _snap(_after_close(SESSIONS[8])), CAL) == (False, "earnings_within_window")


def test_report_on_signal_day_after_close_reacts_session_one():
    assert gate("ABC", SIGNAL, _snap(_after_close(dt.date(2026, 9, 17))), CAL) == (False, "earnings_within_window")


def test_preopen_decision_anchors_window_on_the_signal_bar_not_today():
    thursday_bar, friday = dt.date(2026, 9, 17), dt.date(2026, 9, 18)
    pre_open = dt.datetime(2026, 9, 18, 8, tzinfo=ET)  # signal bar is Thursday; Friday is session 1
    snap = _snap(_before_open(friday), observed=pre_open)
    assert gate("ABC", pre_open, snap, CAL, signal_bar_date=thursday_bar) == (False, "earnings_within_window")
    assert gate("ABC", pre_open, snap, CAL) == (False, "earnings_within_window")  # derived from the clock
    # session 11 from the Thursday bar is Friday 10-02: clear; anchoring on today would wrongly call it session 10
    assert gate("ABC", pre_open, _snap(_before_open(SESSIONS[10]), observed=pre_open), CAL,
                signal_bar_date=thursday_bar) == (True, "clear")


def test_intraday_report_is_treated_conservatively():
    mid = dt.datetime.combine(SESSIONS[9], dt.time(12), tzinfo=ET)  # reaction session 10 or 11
    assert gate("ABC", SIGNAL, _snap(mid), CAL) == (False, "earnings_within_window")


def test_fresh_successful_empty_response_is_clear():
    assert gate("ABC", SIGNAL, _snap(), CAL) == (True, "clear")


def test_stale_snapshot_rejects_at_six_sessions_not_five():
    five = dt.datetime.combine(CAL.sessions(dt.date(2026, 9, 1), dt.date(2026, 9, 17))[-6], dt.time(17), tzinfo=ET)
    six = dt.datetime.combine(CAL.sessions(dt.date(2026, 9, 1), dt.date(2026, 9, 17))[-7], dt.time(17), tzinfo=ET)
    assert gate("ABC", SIGNAL, _snap(observed=five), CAL) == (True, "clear")
    assert gate("ABC", SIGNAL, _snap(observed=six), CAL) == (False, "earnings_stale")


def test_snapshot_observed_after_decision_is_not_known_then():
    later = SIGNAL + dt.timedelta(hours=1)
    assert gate("ABC", SIGNAL, _snap(observed=later), CAL) == (False, "earnings_stale")


def test_naive_timestamps_are_rejected():
    naive = dt.datetime(2026, 9, 17, 17)
    with pytest.raises(ValueError):
        _snap(observed=naive)
    with pytest.raises(ValueError):
        _snap(naive)
    assert gate("ABC", naive, _snap(), CAL) == (False, "earnings_timestamp_invalid")


def test_utc_and_et_instants_agree():
    report = _before_open(SESSIONS[0])
    assert gate("ABC", SIGNAL.astimezone(UTC), _snap(report.astimezone(UTC)), CAL) == (False, "earnings_within_window")


def test_calendar_that_does_not_cover_the_window_is_unknown():
    short = type(CAL)([dt.date(2026, 9, 17), dt.date(2026, 9, 18)])
    assert gate("ABC", SIGNAL, _snap(), short) == (False, "earnings_unknown")


class _Frame:
    def __init__(self, idx): self.index, self.empty = idx, len(idx) == 0


def _ticker_returning(frame=None, exc=None):
    def factory(symbol):
        def get_earnings_dates(limit):
            if exc:
                raise exc
            return frame
        return SimpleNamespace(get_earnings_dates=get_earnings_dates)
    return factory


def test_adapter_distinguishes_network_failure_from_empty_answer(monkeypatch):
    now = dt.datetime(2026, 9, 17, 21, tzinfo=UTC)
    monkeypatch.setattr(events.yf, "Ticker", _ticker_returning(exc=RuntimeError("boom")))
    failed = events.earnings_snapshot("ABC", now=now)
    assert (failed.query_ok, failed.reports) == (False, ())
    monkeypatch.setattr(events.yf, "Ticker", _ticker_returning(frame=_Frame([])))
    empty = events.earnings_snapshot("ABC", now=now)
    assert (empty.query_ok, empty.reports, empty.observed_at) == (True, (), now)
    import pandas as pd
    ts = pd.Timestamp("2026-10-29 16:30", tz=ET)
    monkeypatch.setattr(events.yf, "Ticker", _ticker_returning(frame=_Frame([ts])))
    assert events.earnings_snapshot("ABC", now=now).reports == (ts.to_pydatetime().astimezone(UTC),)


def test_adapter_never_substitutes_an_etf_answer_silently(monkeypatch):
    monkeypatch.setattr(events.yf, "Ticker", _ticker_returning(exc=RuntimeError("boom")))
    stock = events.earnings_snapshot("ABC", now=SIGNAL)
    etf = events.earnings_snapshot("SPY", now=SIGNAL)
    assert not stock.query_ok and etf.query_ok and etf.source == "nonreporting_instrument"


def _deps(snapshot, now=SIGNAL):
    return sp._PassDeps(SimpleNamespace(all=lambda: []), None, "shadow", set(), None,
                        compression_of=lambda t, f: ("broad", None),
                        earnings_of=(lambda t: snapshot) if snapshot is not False else None, now=now)


def _frame():
    return make_ohlcv([100 + i for i in range(80)], start="2026-06-25")[lambda d: d.index.date <= dt.date(2026, 9, 17)]


def test_pass_gate_runs_for_compression_only_and_counts_by_mode():
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT
    frame = _frame()
    within = _snap(_before_open(SESSIONS[0]))
    stamp, reason = sp._compression_context("ABC", COMPRESSION_SHORT, frame, _deps(within))
    assert reason == "earnings_within_window" and stamp == {"compression_mode": "broad"}
    assert sp._compression_context("ABC", COMPRESSION_SHORT, frame, _deps(_snap()))[1] is None
    assert sp._compression_context("ABC", COMPRESSION_SHORT, frame, _deps(False))[1] == "earnings_unknown"
    assert sp._compression_context("ABC", "MACD", frame, _deps(within)) == ({}, None)  # other strategies untouched
    result = sp.PassResult()
    sp._emit_signal(result, frame, ticker="ABC", strategy=COMPRESSION_SHORT, direction="bullish",
                    horizon="2w", bar_date="2026-09-17", regime=None, deps=_deps(within))
    assert result.earnings_excluded_by_mode == {"broad": 1}
    assert result.compression_reasons == {"earnings_within_window": 1} and result.plans == []
