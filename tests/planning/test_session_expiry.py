"""v144: an outlook plan's cancellation reason, from session D's own bars."""
import datetime as dt

import pandas as pd

from swingbot.core.planning import session_expiry as se
from tests.planning.test_plan_engine_model import _plan

D = dt.date(2026, 10, 12)          # Monday, full session, EDT (UTC-4)
HALF = dt.date(2026, 11, 27)       # Friday after Thanksgiving, 13:00 ET close


def _bull(**kw):
    base = dict(source="confluence", entry_type="stop_entry", direction="bullish",
                trigger_price=102.0, stop_loss=100.5, tp1=106.0, origin="next_session",
                valid_session=D.isoformat(), created_at="2026-10-09")
    base.update(kw)
    return _plan(**base)


def _daily(d_high=101.40, d_low=100.80, last=D):
    days = pd.bdate_range(end=pd.Timestamp(last), periods=20)
    rows = [(100.0, 100.75, 99.25, 100.0, 1e6)] * 19 + [(101.0, d_high, d_low, 101.2, 1e6)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"], index=days)


def _hourly(day, last_utc_hour, high=101.10, low=100.90):
    starts = pd.date_range(f"{day} 13:30", f"{day} {last_utc_hour}", freq="h", tz="UTC")
    return pd.DataFrame({"Open": 101.0, "High": high, "Low": low, "Close": 101.0, "Volume": 1e5},
                        index=starts)


def test_hourly_bar_is_used_only_when_it_reaches_the_last_rth_hour():
    full = _hourly(D, "19:30")                      # 15:30 ET start: covers the close
    assert se.hourly_session_bar(full, D) == se.SessionBar(101.10, 100.90, "hourly")
    partial = _hourly(D, "17:30")                   # 13:30 ET: the 4h refresh window
    assert se.hourly_session_bar(partial, D) is None
    assert se.hourly_session_bar(None, D) is None


def test_half_day_coverage_is_judged_against_the_1300_close():
    assert se.hourly_session_bar(_hourly(HALF, "17:30"), HALF) is not None   # 12:30 ET (EST, UTC-5)


def test_session_bar_falls_back_to_the_daily_bar_then_to_nothing():
    daily = _daily()
    assert se.session_bar(D, hourly=_hourly(D, "17:30"), daily=daily) == se.SessionBar(101.40, 100.80, "daily")
    assert se.session_bar(D, hourly=None, daily=_daily(last=D - dt.timedelta(days=3))) is None
    assert se.session_bar(D, hourly=None, daily=None) is None


def test_atr_comes_from_bars_strictly_before_d():
    assert abs(se.atr_before(_daily(), D) - 1.5) < 1e-6


def test_never_triggered_states_the_distance_in_percent_and_atr():
    verdict = se.classify_expiry(_bull(), D, hourly=None, daily=_daily())
    assert verdict == se.Verdict(se.NEVER_TRIGGERED,
                                 "High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger")


def test_a_short_reads_the_low():
    plan = _bull(direction="bearish", trigger_price=98.0, stop_loss=99.5, tp1=94.0)
    verdict = se.classify_expiry(plan, D, hourly=None, daily=_daily(d_high=99.4, d_low=98.6))
    assert verdict.message == "Low 98.60 stopped 0.6% (0.4 ATR) short of the 98.00 trigger"


def test_a_reach_the_polls_missed_still_says_what_happened():
    verdict = se.classify_expiry(_bull(), D, hourly=None, daily=_daily(d_high=102.05))
    assert verdict.code == se.NEVER_TRIGGERED
    assert verdict.message == "High 102.05 reached the 102.00 trigger between polls; no live print filled it"


def test_no_atr_drops_the_atr_clause():
    hourly = _hourly(D, "19:30", high=101.40)
    verdict = se.classify_expiry(_bull(), D, hourly=hourly, daily=None)
    assert verdict.message == "High 101.40 stopped 0.6% short of the 102.00 trigger"


def test_no_bar_at_all_is_no_session_data():
    verdict = se.classify_expiry(_bull(), D, hourly=None, daily=None)
    assert verdict == se.Verdict(se.NO_SESSION_DATA,
                                 "No price data for 2026-10-12; plan expired unevaluated")


def test_in_session_messages_and_codes():
    plan = _bull()
    assert se.in_session_message(plan, "cancelled_invalidated", {"live_price": 100.4}) == \
        "Traded 100.40 through the 100.50 stop before triggering; the setup broke"
    gap = {"entry_price": 104.1, "stop_loss": 100.5, "planned_loss_pct": 3.4582, "max_planned_loss_pct": 2.0}
    assert se.in_session_message(plan, "cancelled_risk_cap", gap) == \
        "Gapped to 104.10 past the 102.00 trigger; the stop distance (3.5%) is over the 2% cap"
    touch = dict(gap, entry_price=102.0, planned_loss_pct=2.4)
    assert se.in_session_message(plan, "cancelled_risk_cap", touch).startswith("Triggered at 102.00;")
    assert se.in_session_message(plan, "filled", {}) is None
    assert se.in_session_message(plan, "cancelled_expired", {}) is None
    assert (se.code_for("cancelled_invalidated"), se.code_for("cancelled_risk_cap"),
            se.code_for("filled")) == (se.INVALIDATED, se.RISK_CAP, None)


def test_cancel_reason_reads_the_cancelled_transition():
    plan = _bull()
    assert se.cancel_reason(plan) is None
    plan.status_history = [{"status": "CANCELLED", "reason": "never_triggered", "at": "x"}]
    assert se.cancel_reason(plan) == "never_triggered"


def test_session_bar_ignores_bars_after_d():
    """Truncation: bars dated after D never change D's high/low."""
    daily = _daily()
    later = pd.DataFrame([(100.0, 150.0, 50.0, 100.0, 1e6)],
                         columns=daily.columns, index=[pd.Timestamp(D) + pd.Timedelta(days=1)])
    extended = pd.concat([daily, later])
    assert se.session_bar(D, hourly=None, daily=extended) == se.session_bar(D, hourly=None, daily=daily)
    assert se.atr_before(extended, D) == se.atr_before(daily, D)
