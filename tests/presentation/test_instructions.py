"""v81: the execution feed's instructions, as pure data. Every string a reader
places an order from is pinned here."""
import datetime as dt
import re

import pytest

from swingbot.core.planning.exit_sim import runner_floor
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from tests.planning.test_plan_engine_model import _plan

MONEY = ins.money_from(2439.02, "$")


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


def _settled(amount, *, shares=9, record_shares=9.9):
    """A close's money as V170-4 builds it from a linked, settled record."""
    return ins.Money(currency="$", shares=shares, realized_amount=amount,
                     record_shares=record_shares)

def _spec_long(**kw):
    """The spec's §2 example ticket: 54 sh between 182.40 / 177.80 / 189.10 / 195.00."""
    base = dict(trigger_price=182.4, stop_loss=177.8, tp1=189.1, tp2=195.0,
                trail_atr_mult=2.0, created_at="2026-10-15")
    base.update(kw)
    return _long_pending(**base)


def _usd(line: str) -> float:
    """The signed dollar figure after 'if hit' in one line."""
    sign, digits = re.search(r"if hit ([+-])\$([\d,]+\.\d\d)", line).groups()
    return (1 if sign == "+" else -1) * float(digits.replace(",", ""))


# --- money ------------------------------------------------------------------

def test_money_from_floors_shares_and_keeps_the_record_count():
    assert ins.money_from(54.41, "$", realized_amount=12.5) == ins.Money(
        currency="$", shares=54, realized_amount=12.5, record_shares=54.41)
    assert ins.money_from(None, "$") == ins.Money(currency="$", shares=None)
    assert ins.money_from(0.4, "$").shares is None             # under one share: unsized


def test_unpriced_money_keeps_the_share_count_and_drops_every_dollar():
    assert ins.money_from(54.41, "$", realized_amount=1.0, priced=False) == ins.Money(
        currency="$", shares=54, realized_amount=None, record_shares=None)


# --- the order ticket --------------------------------------------------------

def test_a_long_stop_entry_ticket_is_a_complete_bracket():
    t = ins.ticket_for(_long_pending(), logged=True, not_logged_reason=None,
                       money=MONEY, level=5)
    assert (t.verb, t.tone, t.level, t.ticker, t.plan_id) == (ins.PLACE, "level", 5, "AAPL", "p1")
    assert t.headline == "▶ BUY STOP 102.50 · 2,439 sh"
    assert t.lines == (
        "🛑 SELL STOP 98.40 · if hit -$9,999.90 · −1.0R",
        "💰 SELL LIMIT 106.00 · 1,219 sh · if hit +$4,266.50 · +0.9R",
        "🏃 1,220 sh: 🎯 SELL LIMIT 110.00 · if hit +$9,150.00 · +1.8R · "
        "〜 trail 3×ATR, stop moves pinged here",
        "⚖ stop → entry at ≥ 104.25",
        "⏳ CANCEL after Thu 17 Sep (5 sessions) · ⛔ CANCEL if ≤ 98.40 first",
    )
    assert t.warnings == ()


def test_the_spec_example_ticket():
    t = ins.ticket_for(_spec_long(), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$"))
    assert t.headline == "▶ BUY STOP 182.40 · 54 sh"
    assert t.lines == (
        "🛑 SELL STOP 177.80 · if hit -$248.40 · −1.0R",
        "💰 SELL LIMIT 189.10 · 27 sh · if hit +$180.90 · +1.5R",
        "🏃 27 sh: 🎯 SELL LIMIT 195.00 · if hit +$340.20 · +2.7R · "
        "〜 trail 2×ATR, stop moves pinged here",
        "⚖ stop → entry at ≥ 185.75",
        "⏳ CANCEL after Thu 22 Oct (5 sessions) · ⛔ CANCEL if ≤ 177.80 first",
    )


@pytest.mark.parametrize("index,shares,level", [(0, 54, 177.80), (1, 27, 189.10), (2, 27, 195.00)])
def test_every_projected_dollar_is_printed_shares_times_printed_move(index, shares, level):
    t = ins.ticket_for(_spec_long(), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$"))
    assert _usd(t.lines[index]) == pytest.approx(shares * (level - 182.40), abs=0.005)


def test_a_sized_short_ticket_flips_verbs_comparisons_and_signs():
    t = ins.ticket_for(_short_pending(tp2=90.0), logged=True, not_logged_reason=None,
                       money=ins.money_from(30.6, "$"))
    assert t.headline == "▶ SELL STOP 97.50 · 30 sh"
    assert t.lines == (
        "🛑 BUY STOP 101.60 · if hit -$123.00 · −1.0R",
        "💰 BUY LIMIT 94.00 · 15 sh · if hit +$52.50 · +0.9R",
        "🏃 15 sh: 🎯 BUY LIMIT 90.00 · if hit +$112.50 · +1.8R · "
        "〜 trail 2.5×ATR, stop moves pinged here",
        "⚖ stop → entry at ≤ 95.75",
        "⏳ CANCEL after Wed 16 Sep (3 sessions) · ⛔ CANCEL if ≥ 101.60 first",
    )


def test_a_short_ticket_survives_missing_sizing_with_r_only():
    t = ins.ticket_for(_short_pending(), logged=True, not_logged_reason=None, level=4)
    assert t.headline == "▶ SELL STOP 97.50 · size n/a"
    assert t.lines == (
        "🛑 BUY STOP 101.60 · if hit −1.0R",
        "💰 BUY LIMIT 94.00 · 50% · if hit +0.9R",
        "🏃 50%: 〜 trail 2.5×ATR, stop moves pinged here",
        "⚖ stop → entry at ≤ 95.75",
        "⏳ CANCEL after Wed 16 Sep (3 sessions) · ⛔ CANCEL if ≥ 101.60 first",
    )


def test_unpriced_money_prints_shares_but_no_dollars():
    t = ins.ticket_for(_spec_long(), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$", priced=False))
    assert t.headline == "▶ BUY STOP 182.40 · 54 sh"
    assert not any("$" in line for line in t.lines)
    assert t.lines[1] == "💰 SELL LIMIT 189.10 · 27 sh · if hit +1.5R"


def test_no_tp2_means_no_runner_figure():
    t = ins.ticket_for(_spec_long(tp2=None), logged=True, not_logged_reason=None,
                       money=ins.money_from(54.9, "$"))
    assert t.lines[2] == "🏃 27 sh: 〜 trail 2×ATR, stop moves pinged here"


def test_a_market_entry_ticket_has_no_cancel_clause():
    t = ins.ticket_for(_long_pending(entry_type="market", trigger_price=100.0,
                                     stop_loss=95.0, tp1=110.0),
                       logged=True, not_logged_reason=None)
    assert t.headline == "▶ BUY AT MARKET ~100.00 · size n/a"
    assert not any("CANCEL" in line for line in t.lines)


def test_a_short_market_entry_says_sell_short():
    t = ins.ticket_for(_short_pending(entry_type="market"), logged=True,
                       not_logged_reason=None)
    assert t.headline.startswith("▶ SELL SHORT AT MARKET ~97.50")


def test_an_unlogged_alert_says_do_not_place_and_why():
    t = ins.ticket_for(_long_pending(), logged=False, not_logged_reason="already open",
                       money=MONEY)
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
                       money=MONEY, warnings=warnings)
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

def _tp1_leg():
    """The spec example's banked TP1 leg: half at 189.10 from 182.40 (risk 4.60)."""
    return {"fraction": 0.5, "exit_price": 189.1, "r": 6.7 / 4.6, "reason": "tp1"}


def test_filled():
    plan = _long_pending(status="ACTIVE", entry_price=102.61)
    i = ins.instruction_for(plan, _event("filled", entry_price=102.61))
    assert (i.verb, i.headline) == (ins.FILLED, "▶ FILLED @ 102.61 (bot)")
    assert i.lines == (
        "Confirm your broker filled; the bot's R is measured from 102.61",
        "Resting: 🛑 SELL STOP 98.40 · 💰 SELL LIMIT 106.00",
    )


def test_break_even_is_effective_immediately_and_projects_flat():
    plan = _long_pending(status="ACTIVE", entry_price=102.61, working_stop=102.61)
    i = ins.instruction_for(plan, _event("be_moved", working_stop=102.61), money=MONEY)
    assert (i.verb, i.headline) == (ins.MOVE_STOP, "🛑 MOVE SELL STOP → 102.61 now")
    assert i.lines == ("⚖ break-even", "🔒 if it fills: +$0.00 · 0.0R total")


def test_break_even_without_money_projects_r_only():
    plan = _long_pending(status="ACTIVE", entry_price=102.61, working_stop=102.61)
    i = ins.instruction_for(plan, _event("be_moved", working_stop=102.61))
    assert i.lines == ("⚖ break-even", "🔒 if it fills: 0.0R total")


def test_tp1_partial_names_the_filled_shares_the_realised_dollars_and_the_runner_stop():
    plan = _long_pending(status="PARTIAL", entry_price=102.61, working_stop=104.87)
    i = ins.instruction_for(plan, _event("tp1_partial", fraction=0.5, exit_price=106.0,
                                         r=0.8052, working_stop=104.87), money=MONEY)
    assert (i.verb, i.tone) == (ins.MOVE_STOP, "good")
    # realised = record 2439.02 × 0.5 × (106.00 − 102.61) = 4,134.14 (record arithmetic, A3)
    assert i.headline == "💰 TP1 FILLED 1,219 sh @ 106.00 · 🧾 +$4,134.14 · +0.8R"
    assert i.lines == ("🛑 MOVE SELL STOP on the runner → 104.87 now (runner floor)",)


def test_the_spec_example_tp1_uses_the_records_fractional_shares():
    plan = _spec_long(status="PARTIAL", entry_price=182.4, working_stop=186.87)
    event = _event("tp1_partial", working_stop=186.87, **_tp1_leg())
    i = ins.instruction_for(plan, event, money=ins.money_from(54.41, "$"))
    # 27 sh printed (floor of 54 × 0.5); $ = 54.41 × 0.5 × 6.70 = 182.27, not 27 × 6.70
    assert i.headline == "💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +$182.27 · +1.5R"


@pytest.mark.parametrize("money,expected", [
    (ins.money_from(54.41, "$", priced=False), "💰 TP1 FILLED 27 sh @ 189.10 · 🧾 +1.5R"),
    (None, "💰 TP1 FILLED 50% @ 189.10 · 🧾 +1.5R"),
])
def test_tp1_without_a_linked_record_prints_no_dollars(money, expected):
    plan = _spec_long(status="PARTIAL", entry_price=182.4, working_stop=186.87)
    event = _event("tp1_partial", working_stop=186.87, **_tp1_leg())
    assert ins.instruction_for(plan, event, money=money).headline == expected


def test_a_trail_move():
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=106.67, new=115.0,
                                         r_moved=1.666, effective="now"))
    assert i.headline == "🛑 MOVE SELL STOP → 115.00 now"
    assert i.lines == ("〜 trail; +1.7R since the last ping", "🔒 if it fills: +3.0R total")


def test_a_resent_runner_floor_is_labelled_as_the_floor():
    floor = runner_floor(100.0, 110.0)
    plan = _plan(status="PARTIAL", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=floor)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=floor,
                                         r_moved=2.333, effective="now"))
    assert i.headline == "🛑 MOVE SELL STOP → 106.67 now"
    assert i.lines == ("🏃 runner floor; +2.3R since the last ping",
                       "🔒 if it fills: +1.3R total")


def test_a_resent_break_even_is_effective_now():
    # "effective" is stamped "now" unconditionally (see stop_move_event) --
    # no same-session delay to keep, so a resent notice reads the same way.
    plan = _plan(status="ACTIVE", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=95.0, new=100.0,
                                         r_moved=1.0, effective="now"))
    assert i.headline == "🛑 MOVE SELL STOP → 100.00 now"
    assert i.lines == ("⚖ break-even; +1.0R since the last ping", "🔒 if it fills: 0.0R total")


def test_a_stop_move_projection_adds_the_banked_leg():
    plan = _spec_long(status="PARTIAL", entry_price=182.4, working_stop=186.0,
                      legs_realized=[_tp1_leg()])
    money = ins.money_from(54.41, "$")
    usd, r_total = ins.stop_projection(plan, 186.0, money)
    # open 27 sh × (186.00 − 182.40) = 97.20, banked 54.41 × 0.5 × 6.70 = 182.2735
    assert usd == pytest.approx(279.4735, abs=1e-6)
    # 0.5 × 1.4565 banked + 0.5 × 0.7826 open
    assert r_total == pytest.approx(1.1196, abs=1e-4)
    i = ins.instruction_for(plan, _event("stop_moved", old=185.0, new=186.0, r_moved=0.78,
                                         effective="now"), money=money)
    assert i.lines == ("〜 trail; +0.8R since the last ping",
                       "🔒 if it fills: +$279.47 · +1.1R total")


def test_a_short_stop_move_says_buy_stop_and_signs_a_loss():
    plan = _short_pending(status="ACTIVE", entry_price=97.5, working_stop=99.0)
    i = ins.instruction_for(plan, _event("stop_moved", old=101.6, new=99.0, r_moved=0.63,
                                         effective="now"), money=ins.money_from(30.6, "$"))
    assert i.headline == "🛑 MOVE BUY STOP → 99.00 now"
    # 30 sh × (99.00 − 97.50) against a short = −45.00; R −1.5/4.1 = −0.37
    assert i.lines == ("⚖ break-even; +0.6R since the last ping",
                       "🔒 if it fills: -$45.00 · −0.4R total")


def test_an_unpriced_projection_is_r_only():
    plan = _spec_long(status="PARTIAL", entry_price=182.4, legs_realized=[_tp1_leg()])
    usd, r_total = ins.stop_projection(plan, 186.0, ins.money_from(54.41, "$", priced=False))
    assert usd is None and r_total == pytest.approx(1.1196, abs=1e-4)


def test_cancellations_name_the_order_to_cancel():
    expired = ins.instruction_for(_long_pending(), _event("cancelled_expired", bars_waited=6))
    assert (expired.verb, expired.tone) == (ins.CANCEL, "inert")
    assert expired.headline == "⏳ CANCEL BUY STOP 102.50"
    assert expired.lines == ("not triggered within 5 sessions",)

    invalidated = ins.instruction_for(_short_pending(),
                                      _event("cancelled_invalidated", live_price=101.7))
    assert invalidated.headline == "⛔ CANCEL SELL STOP 97.50"
    assert invalidated.lines == ("price reached the stop 101.60 before triggering",)

    risk_capped = ins.instruction_for(_long_pending(), _event(
        "cancelled_risk_cap", entry_price=102.5, stop_loss=98.4,
        planned_loss_pct=4.0, max_planned_loss_pct=2.0))
    assert (risk_capped.verb, risk_capped.tone) == (ins.CANCEL, "inert")
    assert risk_capped.headline == "CANCEL BUY STOP 102.50"
    assert risk_capped.lines == (
        "triggered at 102.50 but risked 4.0% against stop 98.40 -- above the 2.0% cap; "
        "never filled",)


# --- closes (v170: outcome lead, exit glyph, settled $ beside R) -------------

def test_a_regular_session_stop_out():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=94.5,
                                         session="regular", notified_stop=95.0,
                                         bot_stop=95.0), money=_settled(-49.5))
    assert (i.verb, i.tone) == (ins.EXITED, "bad")
    assert i.headline == "❌ EXITED @ 94.50 · 🛑 stop"
    assert i.lines == ("🧾 -$49.50 · −1.1R (paper, gross)",
                       "If your broker order did not fill: SELL AT MARKET")


def test_an_extended_hours_exit_says_close_at_market():
    plan = _plan(direction="bearish", status="CLOSED", entry_price=100.0,
                 stop_loss=105.0, tp1=90.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=105.5,
                                         session="extended", notified_stop=105.0,
                                         bot_stop=105.0))
    assert (i.verb, i.tone) == (ins.CLOSE_AT_MARKET, "bad")
    assert i.headline == "❌ CLOSE AT MARKET now"
    assert i.lines == (
        "BUY TO COVER AT MARKET: the bot exited on an extended-hours print @ 105.50; "
        "resting stop orders do not fire outside regular hours",
        "🧾 −1.1R (paper, gross)",
    )


def test_a_trail_exit_warns_when_the_readers_stop_lagged():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=115.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 115.0, "r": 3.0,
                                 "reason": "tp1_runner_trail"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_trail", exit_price=115.0,
                                         session="regular", notified_stop=113.9,
                                         bot_stop=115.0), money=_settled(250.0))
    assert (i.verb, i.tone) == (ins.EXITED, "good")
    assert i.headline == "✅ EXITED @ 115.00 · 〜 trail"
    assert i.lines == (
        "🧾 +$250.00 · +2.5R (paper, gross)",
        "If your broker order did not fill: SELL AT MARKET",
        "your last pinged stop was 113.90 — that order may still be open",
    )


def test_an_unknown_transition_is_refused():
    with pytest.raises(ValueError):
        ins.instruction_for(_long_pending(), _event("pyramid_add"))


def test_progress_stall_close_says_close_at_market():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0,
                 working_stop=100.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 112.0, "r": 2.4,
                                 "reason": "tp1_runner_progress_stall"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_progress_stall",
                                         exit_price=112.0, session="regular"))
    assert i.verb == ins.CLOSE_AT_MARKET
    assert i.headline.startswith("✅ CLOSE AT MARKET now — higher high failed")
    assert "no resting order covers this exit" in i.lines[0]
    assert i.lines[1] == "🧾 +2.2R (paper, gross)"



def test_a_break_even_scratch_leads_flat_and_prints_zero_dollars_signed():
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="scratch", exit_price=100.0,
                                         session="regular"), money=_settled(0.0))
    assert (i.verb, i.tone) == (ins.EXITED, "neutral")
    assert i.headline == "➖ EXITED @ 100.00 · ⚖ break-even"
    assert i.lines[0] == "🧾 +$0.00 · 0.0R (paper, gross)"


def test_a_short_runner_tp2_win_flips_the_exit_verb():
    plan = _plan(direction="bearish", status="CLOSED", entry_price=100.0, stop_loss=105.0,
                 tp1=94.0, tp2=90.0,
                 legs_realized=[{"fraction": 0.5, "exit_price": 94.0, "r": 1.2, "reason": "tp1"},
                                {"fraction": 0.5, "exit_price": 90.0, "r": 2.0,
                                 "reason": "tp1_runner_tp2"}])
    i = ins.instruction_for(plan, _event("closed", reason="tp1_runner_tp2", exit_price=90.0,
                                         session="regular"),
                            money=_settled(80.0, shares=10, record_shares=10.0))
    assert (i.verb, i.tone) == (ins.EXITED, "good")
    assert i.headline == "✅ EXITED @ 90.00 · 🎯 TP2"
    assert i.lines == ("🧾 +$80.00 · +1.6R (paper, gross)",
                       "If your broker order did not fill: BUY TO COVER AT MARKET")


@pytest.mark.parametrize("money", [None, _settled(None)],
                         ids=["no linked record", "record not settled"])
def test_an_unsettled_close_prints_r_only_never_an_estimate(money):
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason="loss", exit_price=94.5,
                                         session="regular"), money=money)
    assert i.lines[0] == "🧾 −1.1R (paper, gross)"
    assert not any("$" in text for text in (i.headline, *i.lines))


@pytest.mark.parametrize("reason,word", [
    ("loss", "🛑 stop"), ("scratch", "⚖ break-even"), ("win", "🎯 target"),
    ("tp1_runner_be", "🏃 runner floor"), ("tp1_runner_trail", "〜 trail"),
    ("tp1_runner_tp2", "🎯 TP2"), ("time_exit", "ten-session time exit"),
])
def test_every_exit_word_gets_its_glyph_where_the_table_has_one(reason, word):
    plan = _plan(status="CLOSED", entry_price=100.0, stop_loss=95.0, tp1=110.0)
    i = ins.instruction_for(plan, _event("closed", reason=reason, exit_price=104.0,
                                         session="regular"))
    assert i.headline == f"✅ EXITED @ 104.00 · {word}"


@pytest.mark.parametrize("r,key", [(0.06, "win"), (0.05, "flat"), (0.0, "flat"),
                                   (-0.05, "flat"), (-0.06, "loss")])
def test_outcome_key_uses_the_close_tone_bands(r, key):
    assert ins.outcome_key(r) == key


def test_pnl_line_signs_both_figures_and_states_the_cost_basis():
    assert ins.pnl_line(1.66, _settled(412.5)) == "🧾 +$412.50 · +1.7R (paper, gross)"
    assert ins.pnl_line(-1.0, _settled(-250.0)) == "🧾 -$250.00 · −1.0R (paper, gross)"
    assert ins.pnl_line(-1.0, _settled(None)) == "🧾 −1.0R (paper, gross)"
    assert ins.pnl_line(0.4, None) == "🧾 +0.4R (paper, gross)"



@pytest.mark.parametrize("r", [-0.0, 0.0, 0.01, -0.01, -0.04, 0.04])
def test_pnl_line_prints_a_scratch_as_plain_zero_r(r):
    line = ins.pnl_line(r, _settled(0.0))
    assert line == "🧾 +$0.00 · 0.0R (paper, gross)"
    assert "+-" not in line and "−−" not in line
