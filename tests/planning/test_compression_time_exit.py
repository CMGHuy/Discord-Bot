"""v119 Task 7: the compression short's ten-session paper close and its notice.

The fill session is session 1 and the tenth exit bar is fill index + 9, in the
replay walker and in the live manager alike. Live, a `time_exit_due` notice goes
out by min(15:30 ET, close - 20 min); only an official closing-auction price may
persist the paper close; a notice sent never closes a plan; stop and target keep
priority over the time rule.
"""
import datetime as dt
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from swingbot.core.market.session import nyse_calendar
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning import plan_manager as pm
from swingbot.core.planning import time_exit as te
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus
from swingbot.core.planning.plan_manager import Delivery, PlanManager
from swingbot.core.planning.plan_store import PlanStore
from swingbot.core.planning.plan_types import plan_from_dict, plan_to_dict
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan

ET = ZoneInfo("America/New_York")
FRI_FILL = dt.date(2026, 1, 16)        # Friday before the MLK Monday holiday
FRI_TENTH = dt.date(2026, 1, 30)
HALF_FILL = dt.date(2026, 11, 13)      # tenth session = Fri 2026-11-27, 13:00 close
HALF_TENTH = dt.date(2026, 11, 27)
STD_TENTH = dt.date(2026, 12, 1)       # fill 2026-11-17 -> tenth session, 16:00 close
STD_FILL = dt.date(2026, 11, 17)


def _at(day, hour, minute, second=0):
    return datetime(day.year, day.month, day.day, hour, minute, second, tzinfo=ET)


def _fill_history(fill_day):
    stamp = _at(fill_day, 10, 0).astimezone(dt.timezone.utc).isoformat()
    return [{"status": "PENDING", "reason": None, "at": "2026-01-01T00:00:00+00:00"},
            {"status": "ACTIVE", "reason": "stop_entry_fill", "at": stamp}]


def _short(fill_day=STD_FILL, **kw):
    base = dict(strategy=COMPRESSION_SHORT, horizon_key="2w", direction="bearish",
                entry_type="stop_entry", trigger_price=100.0, entry_price=100.0,
                stop_loss=101.0, tp1=95.0, tp1_fraction=1.0, tp2=None, expiry_bars=1,
                hold_cap_bars=10, created_at="2026-11-10", status=PlanStatus.ACTIVE,
                status_history=_fill_history(fill_day))
    base.update(kw)
    return _plan(**base)


def _auction(price=99.0, source="official_auction"):
    return lambda ticker, day: (price, source, "2026-12-01T21:00:05+00:00")


def _env(plan=None, *, price=99.5, auction=None):
    feed = FakePriceFeed([("AAPL", price)])
    store = PlanStore()
    store.add(plan or _short())
    return store, PlanManager(store, feed.get_price, auction_close_fn=auction)


def _kinds(events):
    return [e.transition for e in events]


def _only(events, transition):
    return [e for e in events if e.transition == transition]


# -- calendar -----------------------------------------------------------------

def test_tenth_session_counts_the_fill_session_as_one_across_a_holiday():
    cal = nyse_calendar()
    assert te.tenth_session(FRI_FILL, cal) == FRI_TENTH
    assert te.tenth_session(FRI_FILL, cal) == cal.sessions(FRI_FILL, dt.date(2026, 2, 28))[9]


def test_tenth_session_refuses_a_fill_that_is_not_a_session_or_outside_coverage():
    cal = nyse_calendar()
    with pytest.raises(ValueError):
        te.tenth_session(dt.date(2026, 1, 17), cal)            # Saturday
    with pytest.raises(ValueError):
        te.tenth_session(dt.date(2030, 12, 27), cal)           # fewer than 10 sessions left


def test_fill_day_comes_from_the_first_active_transition_not_created_at():
    plan = _short(fill_day=dt.date(2026, 11, 17), created_at="2026-11-10")
    assert te.fill_day_from_history(plan.status_history) == dt.date(2026, 11, 17)
    with pytest.raises(ValueError):
        te.fill_day_from_history([{"status": "PENDING", "at": "2026-11-10"}])


def test_late_evening_utc_fill_stamp_is_the_et_session_date():
    history = [{"status": "ACTIVE", "at": "2026-11-17T20:30:00+00:00"}]    # 15:30 ET
    assert te.fill_day_from_history(history) == dt.date(2026, 11, 17)


def test_notice_deadline_is_1530_standard_and_twenty_minutes_before_an_early_close():
    std = te.official_close_at(STD_TENTH)
    half = te.official_close_at(HALF_TENTH)
    assert std.time().isoformat() == "16:00:00" and std.tzinfo is not None
    assert te.notice_deadline(std).time().isoformat() == "15:30:00"
    assert half.time().isoformat() == "13:00:00"
    assert te.notice_deadline(half).time().isoformat() == "12:40:00"


def test_official_close_is_none_when_the_schedule_does_not_cover_the_date():
    assert te.official_close_at(dt.date(2026, 1, 19)) is None        # MLK holiday
    assert te.official_close_at(dt.date(2026, 1, 17)) is None        # Saturday
    assert te.official_close_at(dt.date(2031, 3, 3)) is None         # past coverage


# -- replay: the tenth exit bar is fill index + 9 ------------------------------

def _flat(n=30, price=100.0):
    rows = [(price, price + 0.2, price - 0.2, price, 1e6)] * n
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"],
                        index=pd.bdate_range("2026-11-02", periods=n))


def test_replay_times_out_on_the_tenth_session_with_a_daily_close_proxy_leg():
    res = simulate_exit(_flat(), 5, _short(entry_type="market"), scale_out=True)
    assert res.outcome == "timeout"
    assert res.exit_index == res.entry_index + 9
    assert res.legs[0]["reason"] == "time_exit"
    assert res.legs[0]["price_basis"] == "daily_close_proxy"


def test_replay_stop_on_the_tenth_bar_keeps_priority_over_the_time_close():
    df = _flat()
    df.iloc[14, df.columns.get_loc("High")] = 101.5            # entry 5 -> tenth bar is 14
    res = simulate_exit(df, 5, _short(entry_type="market"), scale_out=True)
    assert (res.outcome, res.exit_index, res.legs[0]["reason"]) == ("loss", 14, "stop")


def test_replay_target_on_the_tenth_bar_keeps_priority_over_the_time_close():
    df = _flat()
    df.iloc[14, df.columns.get_loc("Low")] = 94.0
    res = simulate_exit(df, 5, _short(entry_type="market"), scale_out=True)
    assert (res.outcome, res.exit_index) == ("win", 14)


def test_replay_other_strategies_keep_their_bar_count():
    plan = _short(entry_type="market", strategy="Fibonacci")
    res = simulate_exit(_flat(), 5, plan, scale_out=True)
    assert res.exit_index == res.entry_index + 10            # hold_cap_bars unchanged for them
    assert res.legs[0]["reason"] == "timeout"


def test_live_bar_count_at_the_tenth_session_equals_the_replay_exit_offset(monkeypatch):
    import swingbot.core.marketdata.data as data
    df = _flat()
    monkeypatch.setattr(data, "get_daily_data", lambda ticker: df.iloc[:15])   # through bar 14
    live_bars = pm._bars_since("AAPL", "2026-11-09T10:00:00")                  # fill bar = index 5
    res = simulate_exit(df, 5, _short(entry_type="market"), scale_out=True)
    assert live_bars == res.exit_index - res.entry_index == 9


# -- live: notice, idempotency, close -------------------------------------------

def test_no_notice_before_the_deadline_and_none_before_the_due_day():
    _, mgr = _env(auction=_auction())
    assert mgr.poll(now=_at(STD_TENTH, 15, 29)) == []
    assert mgr.poll(now=_at(dt.date(2026, 11, 30), 15, 45)) == []      # session 9


def test_due_notice_at_1530_carries_cover_size_and_auction_time_and_does_not_close():
    store, mgr = _env(auction=_auction())
    events = mgr.poll(now=_at(STD_TENTH, 15, 30, 30))
    due = _only(events, "time_exit_due")
    assert len(due) == 1
    assert due[0].detail["cover_fraction"] == 1.0
    assert due[0].detail["auction_time"].startswith("2026-12-01T16:00:00")
    assert due[0].detail["late"] is False
    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE                 # a notice never closes a plan
    assert plan.time_exit_due_date == "2026-12-01"
    assert [n["transition"] for n in plan.pending_time_notices] == ["time_exit_due"]


def test_repeated_polls_and_a_restart_emit_one_due_notice_once_acknowledged():
    store, mgr = _env(auction=_auction())
    first = mgr.poll(now=_at(STD_TENTH, 15, 30, 30))
    notice_id = _only(first, "time_exit_due")[0].detail["notice_id"]
    pm_events = mgr.poll(now=_at(STD_TENTH, 15, 31))
    assert [e.detail["notice_id"] for e in pm_events] == [notice_id]   # resend, same stable id
    store_after = PlanStore()
    pm_ack = PlanManager(store_after, lambda t: 99.5, auction_close_fn=_auction())
    pm.ack_notified([Delivery("p1", "notice", notice_id)])
    assert store.get("p1").pending_time_notices == []
    restarted = PlanManager(PlanStore(), lambda t: 99.5, auction_close_fn=_auction())
    repeats = restarted.poll(now=_at(STD_TENTH, 15, 40)) + pm_ack.poll(now=_at(STD_TENTH, 15, 41))
    assert _only(repeats, "time_exit_due") == []


def test_notice_id_is_plan_transition_and_session_date():
    assert te.time_notice_id("p1", "time_exit_due", STD_TENTH) == "p1:time_exit_due:2026-12-01"


def test_missed_1530_poll_sends_immediately_marked_late():
    _, mgr = _env(auction=_auction())
    events = mgr.poll(now=_at(STD_TENTH, 15, 50))
    due = _only(events, "time_exit_due")
    assert len(due) == 1 and due[0].detail["late"] is True


def test_restart_after_due_before_close_does_not_restage_and_still_closes():
    store, mgr = _env(auction=_auction(99.0))
    mgr.poll(now=_at(STD_TENTH, 15, 35))
    restarted = PlanManager(PlanStore(), lambda t: 99.5, auction_close_fn=_auction(99.0))
    mid = restarted.poll(now=_at(STD_TENTH, 15, 45))
    assert _only(mid, "time_exit_due") == [] or all(
        e.detail["notice_id"].endswith("2026-12-01") for e in _only(mid, "time_exit_due"))
    assert store.get("p1").status == PlanStatus.ACTIVE
    closed = restarted.poll(now=_at(STD_TENTH, 16, 0, 20))
    assert _kinds(_only(closed, "closed")) == ["closed"]
    assert store.get("p1").status == PlanStatus.CLOSED


def test_official_auction_close_persists_one_terminal_leg_for_an_active_plan():
    store, mgr = _env(auction=_auction(98.0))
    mgr.poll(now=_at(STD_TENTH, 15, 40))
    events = mgr.poll(now=_at(STD_TENTH, 16, 0, 20))
    closed = _only(events, "closed")
    assert len(closed) == 1
    detail = closed[0].detail
    assert detail["reason"] == "time_exit" and detail["exit_price"] == 98.0
    assert detail["leg"]["reason"] == "time_exit"
    assert detail["leg"]["price_basis"] == "official_auction"
    assert detail["leg"]["r"] == pytest.approx(2.0)          # short 100 -> 98 on a 1.0 risk
    plan = store.get("p1")
    assert plan.status == PlanStatus.CLOSED
    assert plan.status_history[-1]["reason"] == "time_exit"
    mgr.poll(now=_at(STD_TENTH, 16, 5))                      # never a second close
    history = store.get("p1").status_history
    assert [h["status"] for h in history].count(PlanStatus.CLOSED) == 1


def test_closing_poll_without_a_prior_due_notice_still_notices_late_then_closes():
    store, mgr = _env(auction=_auction(99.0))
    events = mgr.poll(now=_at(STD_TENTH, 16, 0, 20))
    assert _kinds(events) == ["time_exit_due", "closed"]
    assert events[0].detail["late"] is True


@pytest.mark.parametrize("auction", [None,
                                     lambda t, d: None,
                                     lambda t, d: (99.0, "last_quote", "x"),
                                     lambda t, d: (99.0, "daily_close", "x"),
                                     lambda t, d: (0.0, "official_auction", "x")])
def test_missing_or_unofficial_close_price_is_an_explicit_notice_never_a_fill(auction):
    store, mgr = _env(auction=auction)
    events = mgr.poll(now=_at(STD_TENTH, 16, 1))
    assert _only(events, "closed") == []
    assert len(_only(events, "time_exit_unresolved")) == 1
    plan = store.get("p1")
    assert plan.status == PlanStatus.ACTIVE and plan.legs_realized == []
    assert plan.time_exit_due_date == "2026-12-01"           # no duplicate MOC staging


def test_unresolved_notice_is_sent_once_per_day_then_reconciles_when_the_price_arrives():
    prices = {"value": None}
    store, mgr = _env(auction=lambda t, d: prices["value"])
    first = mgr.poll(now=_at(STD_TENTH, 16, 1))
    notice_id = _only(first, "time_exit_unresolved")[0].detail["notice_id"]
    pm.ack_notified([Delivery("p1", "notice", notice_id)])
    assert _only(mgr.poll(now=_at(STD_TENTH, 16, 2)), "time_exit_unresolved") == []
    prices["value"] = (98.5, "official_auction", "2026-12-01T21:00:05+00:00")
    late = mgr.poll(now=_at(STD_TENTH, 16, 45))
    assert len(_only(late, "closed")) == 1
    assert store.get("p1").status == PlanStatus.CLOSED


def test_a_poll_the_next_day_still_resolves_the_missed_due_session():
    store, mgr = _env(auction=_auction(99.2))
    events = mgr.poll(now=_at(dt.date(2026, 12, 2), 10, 0))
    assert len(_only(events, "closed")) == 1
    assert _only(events, "closed")[0].detail["exit_price"] == 99.2


def test_unavailable_exchange_schedule_fails_closed_with_an_unresolved_notice(monkeypatch):
    monkeypatch.setattr(te, "official_close_at", lambda day: None)
    store, mgr = _env(auction=_auction())
    events = mgr.poll(now=_at(STD_TENTH, 16, 30))
    assert _kinds(events) == ["time_exit_unresolved"]
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_stop_before_the_time_close_wins_after_the_moc_was_staged():
    store, mgr = _env(auction=_auction(99.0))
    mgr.poll(now=_at(STD_TENTH, 15, 35))
    feed_mgr = PlanManager(PlanStore(), lambda t: 101.5, auction_close_fn=_auction(99.0))
    events = feed_mgr.poll(now=_at(STD_TENTH, 15, 50))
    closed = _only(events, "closed")
    assert [e.detail["reason"] for e in closed] == ["loss"]
    assert store.get("p1").status == PlanStatus.CLOSED
    assert store.get("p1").status_history[-1]["reason"] == "loss"


def test_stop_on_the_close_poll_beats_the_auction_price():
    store, mgr = _env(price=101.5, auction=_auction(99.0))
    events = mgr.poll(now=_at(STD_TENTH, 16, 0, 10))
    assert [e.detail["reason"] for e in _only(events, "closed")] == ["loss"]


def test_due_and_terminal_notices_queue_side_by_side_and_ack_independently():
    store, mgr = _env(auction=_auction(99.0))
    due_events = mgr.poll(now=_at(STD_TENTH, 15, 35))
    due_id = _only(due_events, "time_exit_due")[0].detail["notice_id"]
    stop_mgr = PlanManager(PlanStore(), lambda t: 101.5, auction_close_fn=_auction())
    stop_mgr.poll(now=_at(STD_TENTH, 15, 50))
    plan = store.get("p1")
    assert plan.pending_notice["transition"] == "closed"
    assert [n["id"] for n in plan.pending_time_notices] == [due_id]
    resent = stop_mgr.resend_notices()
    assert sorted(_kinds(resent)) == ["closed", "time_exit_due"]
    pm.ack_notified([Delivery("p1", "notice", due_id)])
    plan = store.get("p1")
    assert plan.pending_time_notices == [] and plan.pending_notice["transition"] == "closed"
    pm.ack_notified([Delivery("p1", "notice", "closed")])
    assert store.get("p1").pending_notice is None


def test_resend_never_drops_an_old_time_notice():
    store, mgr = _env(auction=_auction())
    mgr.poll(now=_at(STD_TENTH, 15, 35))
    plan = store.get("p1")
    plan.pending_time_notices[0]["at"] = "2020-01-01T00:00:00+00:00"
    store.update(plan)
    assert _kinds(mgr.resend_notices()) == ["time_exit_due"]
    assert len(store.get("p1").pending_time_notices) == 1


def test_ack_removes_only_the_matching_time_notice():
    store, mgr = _env(auction=lambda t, d: None)
    mgr.poll(now=_at(STD_TENTH, 15, 35))
    mgr.poll(now=_at(STD_TENTH, 16, 5))
    ids = [n["id"] for n in store.get("p1").pending_time_notices]
    assert len(ids) == 2
    pm.ack_notified([Delivery("p1", "notice", ids[0])])
    assert [n["id"] for n in store.get("p1").pending_time_notices] == [ids[1]]


def test_early_close_notice_at_1240_and_close_at_1300():
    store, mgr = _env(_short(fill_day=HALF_FILL), auction=_auction(99.0))
    assert mgr.poll(now=_at(HALF_TENTH, 12, 39)) == []
    due = _only(mgr.poll(now=_at(HALF_TENTH, 12, 40, 30)), "time_exit_due")
    assert len(due) == 1 and due[0].detail["auction_time"].startswith("2026-11-27T13:00:00")
    assert _only(mgr.poll(now=_at(HALF_TENTH, 12, 59)), "closed") == []
    assert len(_only(mgr.poll(now=_at(HALF_TENTH, 13, 0, 5)), "closed")) == 1


def test_friday_before_a_monday_holiday_fill_closes_on_the_tenth_session():
    store, mgr = _env(_short(fill_day=FRI_FILL), auction=_auction(99.0))
    assert mgr.poll(now=_at(dt.date(2026, 1, 29), 16, 1)) == []              # session 9
    events = mgr.poll(now=_at(FRI_TENTH, 16, 0, 5))
    assert [e.transition for e in events] == ["time_exit_due", "closed"]


def test_persisted_partial_closes_its_remaining_fraction_and_keeps_the_prior_leg():
    first_leg = {"fraction": 0.5, "exit_price": 95.0, "r": 5.0, "reason": "tp1",
                 "closed_at": "2026-11-20T15:00:00+00:00"}
    plan = _short(status=PlanStatus.PARTIAL, tp1_fraction=0.5, tp2=90.0,
                  legs_realized=[dict(first_leg)], working_stop=100.0)
    plan.status_history.append({"status": "PARTIAL", "reason": "tp1_partial",
                                "at": "2026-11-20T15:00:00+00:00"})
    store, mgr = _env(plan, price=97.0, auction=_auction(98.0))
    events = mgr.poll(now=_at(STD_TENTH, 16, 0, 10))
    due = _only(events, "time_exit_due")
    assert due[0].detail["cover_fraction"] == pytest.approx(0.5)
    closed = _only(events, "closed")
    assert closed[0].detail["reason"] == "time_exit"
    saved = store.get("p1")
    assert saved.status == PlanStatus.CLOSED
    assert saved.legs_realized[0] == first_leg
    assert len(saved.legs_realized) == 2
    last = saved.legs_realized[1]
    assert last["fraction"] == pytest.approx(0.5) and last["reason"] == "time_exit"
    assert last["exit_price"] == 98.0 and last["price_basis"] == "official_auction"


def test_other_strategies_get_no_time_notices():
    plan = _short(strategy="Fibonacci")
    store, mgr = _env(plan, auction=_auction())
    assert mgr.poll(now=_at(STD_TENTH, 16, 5)) == []
    assert store.get("p1").status == PlanStatus.ACTIVE


def test_plan_without_a_recorded_fill_is_left_alone():
    plan = _short(status_history=[])
    store, mgr = _env(plan, auction=_auction())
    assert mgr.poll(now=_at(STD_TENTH, 16, 5)) == []


# -- persisted shape ---------------------------------------------------------------

def test_plan_json_written_before_this_task_loads_with_empty_time_fields():
    row = plan_to_dict(_short())
    for name in ("pending_time_notices", "time_exit_due_date", "time_exit_unresolved_date"):
        del row[name]
    plan = plan_from_dict(row)
    assert plan.pending_time_notices == []
    assert plan.time_exit_due_date is None and plan.time_exit_unresolved_date is None


def test_time_fields_round_trip_through_the_store():
    plan = _short(time_exit_due_date="2026-12-01", created_at="2026-11-10T00:00:00+00:00",
                  pending_time_notices=[
        {"id": "p1:time_exit_due:2026-12-01", "transition": "time_exit_due",
         "detail": {"late": False}, "at": "2026-12-01T20:30:00+00:00", "acked": False}])
    store = PlanStore()
    store.add(plan)
    assert store.get("p1") == plan


# -- the Discord instruction ------------------------------------------------------------

def test_due_instruction_names_cover_side_auction_time_and_late():
    from swingbot.core.presentation.instructions import instruction_for
    from swingbot.core.planning.plan_manager import PlanEvent
    plan = _short()
    event = PlanEvent("p1", "time_exit_due", {
        "cover_fraction": 1.0, "auction_time": "2026-12-01T16:00:00-05:00", "late": True,
        "notice_id": "p1:time_exit_due:2026-12-01"})
    instruction = instruction_for(plan, event)
    text = " ".join([instruction.headline, *instruction.lines])
    assert "LATE" in text and "BUY TO COVER" in text and "16:00" in text


def test_unresolved_instruction_is_urgent_and_says_no_price():
    from swingbot.core.presentation.instructions import instruction_for
    from swingbot.core.planning.plan_manager import PlanEvent
    event = PlanEvent("p1", "time_exit_unresolved", {
        "reason": "official closing-auction price unavailable",
        "notice_id": "p1:time_exit_unresolved:2026-12-01"})
    instruction = instruction_for(_short(), event)
    assert "UNRESOLVED" in instruction.headline.upper()
