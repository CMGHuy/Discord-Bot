"""v81: the execution feed's instructions, as pure data. Every string a reader
places an order from is pinned here."""
import datetime as dt

import pytest

from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from tests.planning.test_plan_engine_model import _plan

SIZING = {"shares": 2439.02, "risk_amount": 10000.0}


def _long_pending(**kw):
    base = dict(entry_type="stop_entry", direction="bullish", trigger_price=102.5,
                entry_price=None, stop_loss=98.4, tp1=106.0, tp1_fraction=0.5,
                tp2=110.0, trail_atr_mult=3.0, breakeven_trigger_fraction=0.5,
                created_at="2026-09-10", expiry_bars=5, status="PENDING")
    base.update(kw)
    return _plan(**base)


def _short_pending(**kw):
    base = dict(entry_type="stop_entry", direction="bearish", trigger_price=97.5,
                entry_price=None, stop_loss=101.6, tp1=94.0, tp1_fraction=0.5,
                tp2=None, trail_atr_mult=2.5, breakeven_trigger_fraction=0.5,
                created_at="2026-09-11", expiry_bars=3, status="PENDING")
    base.update(kw)
    return _plan(**base)


def _event(transition, **detail):
    return PlanEvent("p1", transition, detail)


# --- the order ticket --------------------------------------------------------

def test_a_long_stop_entry_ticket_is_a_complete_bracket():
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       sizing=SIZING, currency="$", level=5)
    assert (t.verb, t.tone, t.level, t.ticker, t.plan_id) == (ins.PLACE, "level", 5, "AAPL", "p1")
    assert t.headline == "BUY STOP 102.50 · 2,439 sh (risk $10,000)"
    assert t.lines == (
        "SELL STOP 98.40",
        "TP1 SELL LIMIT 106.00 · 1,219 sh (50%)",
        "RUNNER 1,220 sh → TP2 110.00 / trail 3×ATR — stop moves are pinged here",
        "Stop → entry once price reaches 104.25",
        "Cancel if: not triggered by the close of ≈ Thu 17 Sep (5 sessions), "
        "or price reaches 98.40 first",
    )
    assert t.warnings == ()


def test_a_short_ticket_swaps_every_side_and_survives_missing_sizing():
    t = ins.ticket_for(_short_pending(), logged=True, not_logged_reason=None,
                       sizing=None, level=4)
    assert t.headline == "SELL STOP 97.50 · size n/a"
    assert t.lines == (
        "BUY STOP 101.60",
        "TP1 BUY LIMIT 94.00 · 50%",
        "RUNNER 50% → trail 2.5×ATR — stop moves are pinged here",
        "Stop → entry once price reaches 95.75",
        "Cancel if: not triggered by the close of ≈ Wed 16 Sep (3 sessions), "
        "or price reaches 101.60 first",
    )


def test_a_market_entry_ticket_has_no_cancel_clause():
    t = ins.ticket_for(_long_pending(entry_type="market", trigger_price=100.0,
                                     stop_loss=95.0, tp1=110.0),
                       logged=True, not_logged_reason=None, sizing=None)
    assert t.headline == "BUY AT MARKET ~100.00 · size n/a"
    assert not any(line.startswith("Cancel if") for line in t.lines)


def test_a_short_market_entry_says_sell_short():
    t = ins.ticket_for(_short_pending(entry_type="market"), logged=True,
                       not_logged_reason=None, sizing=None)
    assert t.headline.startswith("SELL SHORT AT MARKET ~97.50")


def test_an_unlogged_alert_says_do_not_place_and_why():
    t = ins.ticket_for(_long_pending(), logged=False, not_logged_reason="already open",
                       sizing=SIZING, currency="$")
    assert (t.verb, t.tone) == (ins.DO_NOT_PLACE, "inert")
    assert t.headline == "DO NOT PLACE — already open"
    assert t.lines == ("levels: entry 102.50 · stop 98.40 · TP1 106.00",)


def test_cap_blocks_keep_place_and_are_named_above_the_orders():
    warnings = ins.block_warnings(
        heat={"allowed": False, "open_heat": 6.2, "cap": 6.0},
        cluster={"allowed": False, "cluster": ["AMD", "NVDA"],
                 "correlated_heat": 4.1, "cap": 3.0},
        kill={"on": True, "reason": "3 consecutive losses"},
    )
    assert warnings == (
        "⚠ over portfolio heat cap — open 6.2% / cap 6.0%; the bot tracks this at full size",
        "⚠ over correlated-cluster cap — AMD, NVDA at 4.1% / cap 3.0%; "
        "the bot tracks this at full size",
        "⚠ kill switch on (3 consecutive losses) — the bot tracks this at full size",
    )
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       sizing=SIZING, warnings=warnings)
    assert t.verb == ins.PLACE
    assert t.warnings == warnings


def test_no_blocks_means_no_warnings():
    assert ins.block_warnings(heat=None, cluster=None, kill=None) == ()


@pytest.mark.parametrize("created_at,bars,expected", [
    ("2026-09-10", 5, dt.date(2026, 9, 17)),            # Thursday + 5 weekdays
    ("2026-09-11", 1, dt.date(2026, 9, 14)),            # Friday -> Monday
    ("2026-09-12T14:00:00", 1, dt.date(2026, 9, 14)),   # a Saturday stamp still counts weekdays
])
def test_approx_last_trigger_session_counts_weekdays(created_at, bars, expected):
    assert ins.approx_last_trigger_session(created_at, bars) == expected


@pytest.mark.parametrize("value,expected", [(0.8, "+0.8R"), (-1.1, "−1.1R"), (0.0, "0.0R")])
def test_signed_r(value, expected):
    assert ins.signed_r(value) == expected


# --- lifecycle instructions --------------------------------------------------

def test_filled():
    plan = _long_pending(status="ACTIVE", entry_price=102.61)
    i = ins.instruction_for(plan, _event("filled", entry_price=102.61))
    assert (i.verb, i.headline) == (ins.FILLED, "FILLED @ 102.61 (bot)")
    assert i.lines == (
        "Confirm your broker filled; the bot's R is measured from 102.61",
        "Resting: SELL STOP 98.40 · TP1 SELL LIMIT 106.00",
    )


def test_break_even_waits_for_the_close():
    plan = _long_pending(status="ACTIVE", entry_price=102.61, working_stop=102.61)
    i = ins.instruction_for(plan, _event("be_moved", working_stop=102.61))
    assert (i.verb, i.headline) == (ins.MOVE_STOP, "MOVE STOP → 102.61 after today's close")
    assert i.lines == ("break-even; keep 98.40 until then",)


def test_tp1_partial_names_the_filled_shares_and_the_runner_stop():
    plan = _long_pending(status="PARTIAL", entry_price=102.61, working_stop=104.87)
    i = ins.instruction_for(plan, _event("tp1_partial", fraction=0.5, exit_price=106.0,
                                         r=0.8052, working_stop=104.87), sizing=SIZING)
    assert (i.verb, i.tone) == (ins.MOVE_STOP, "good")
    assert i.headline == "TP1 FILLED 1,219 sh @ 106.00 (+0.8R)"
    assert i.lines == ("MOVE STOP on the runner → 104.87 now (runner floor)",)


def test_a_trail_move():
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=106.67, new=115.0,
                                         r_moved=1.666, effective="now"))
    assert i.headline == "MOVE STOP → 115.00 now"
    assert i.lines == ("trail; +1.7R since the last ping",)


def test_a_resent_runner_floor_is_labelled_as_the_floor():
    floor = runner_floor(100.0, 110.0)
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=floor)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=floor,
                                         r_moved=2.333, effective="now"))
    assert i.headline == "MOVE STOP → 106.67 now"
    assert i.lines == ("runner floor; +2.3R since the last ping",)


def test_a_resent_break_even_keeps_its_next_session_timing():
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=100.0,
                                         r_moved=1.0, effective="next_session"))
    assert i.headline == "MOVE STOP → 100.00 after today's close"
    assert i.lines == ("break-even; +1.0R since the last ping",)


def test_cancellations_name_the_order_to_cancel():
    expired = ins.instruction_for(_long_pending(), _event("cancelled_expired", bars_waited=6))
    assert (expired.verb, expired.tone) == (ins.CANCEL, "inert")
    assert expired.headline == "CANCEL BUY STOP 102.50"
    assert expired.lines == ("not triggered within 5 sessions",)

    invalidated = ins.instruction_for(_short_pending(),
                                      _event("cancelled_invalidated", live_price=101.7))
    assert invalidated.headline == "CANCEL SELL STOP 97.50"
    assert invalidated.lines == ("price reached the stop 101.60 before triggering",)


def test_a_regular_session_stop_out():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=94.5,
                                         session="regular", notified_stop=95.0,
                                         bot_stop=95.0))
    assert (i.verb, i.tone) == (ins.EXITED, "bad")
    assert i.headline == "EXITED @ 94.50 — stop · −1.1R total"
    assert i.lines == ("If your broker order did not fill: SELL AT MARKET",)


def test_an_extended_hours_exit_says_close_at_market():
    plan = _plan(direction="bearish", status="CLOSED", entry_price=100.0,
                 stop_loss=105.0, tp1=90.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=105.5,
                                         session="extended", notified_stop=105.0,
                                         bot_stop=105.0))
    assert (i.verb, i.headline) == (ins.CLOSE_AT_MARKET, "CLOSE AT MARKET now")
    assert i.lines == (
        "BUY TO COVER AT MARKET: the bot exited on an extended-hours print @ 105.50; "
        "resting stop orders do not fire outside regular hours",
        "−1.1R total",
    )


def test_a_trail_exit_warns_when_the_readers_stop_lagged():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 115.0, "r": 3.0,
                                 "reason": "tp1_runner_trail"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_trail", exit_price=115.0,
                                         session="regular", notified_stop=113.9,
                                         bot_stop=115.0))
    assert (i.verb, i.tone) == (ins.EXITED, "good")
    assert i.headline == "EXITED @ 115.00 — trail · +2.5R total"
    assert i.lines == (
        "If your broker order did not fill: SELL AT MARKET",
        "your last pinged stop was 113.90 — that order may still be open",
    )


def test_an_unknown_transition_is_refused():
    with pytest.raises(ValueError):
        ins.instruction_for(_long_pending(), _event("pyramid_add"))
