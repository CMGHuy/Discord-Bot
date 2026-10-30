"""v189 A7: the delete vocabulary.

`cancelled_trade_deleted` (a PENDING plan whose placeholder trade was deleted)
joins every table a pending cancel lives in, as the v187 limit cancels did.
A `closed` event with reason `trade_deleted` (an ACTIVE/PARTIAL plan whose
trade was deleted) has no exit price: the feed and the follow channel say the
position is no longer monitored -- no exit, no R, no result block.
"""
import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning import plan_manager
from swingbot.core.planning import session_expiry as se
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

EVENT = "cancelled_trade_deleted"
CANCEL_DETAIL = {"reason": "trade_deleted", "live_price": None}
CLOSE_DETAIL = {"reason": "trade_deleted"}
DIRECTIONS = ("bullish", "bearish")
WHY = ("The trade record was deleted before the order filled. Nothing was opened and "
       "the plan is no longer monitored.")


def _levels(direction):
    sign = 1 if direction == "bullish" else -1
    return dict(direction=direction, trigger_price=100.0, stop_loss=100.0 - 5 * sign,
                tp1=100.0 + 10 * sign, tp2=100.0 + 20 * sign)


def _cancelled(direction="bullish"):
    plan = _plan(entry_type="stop_entry", **_levels(direction))
    record_transition(plan, PlanStatus.CANCELLED, reason="trade_deleted",
                      at="2026-10-23T15:00:00+00:00")
    return plan


def _closed_partial(direction="bullish"):
    sign = 1 if direction == "bullish" else -1
    plan = _plan(entry_type="stop_entry", entry_price=100.0, **_levels(direction))
    record_transition(plan, PlanStatus.ACTIVE, reason="stop_entry_fill", at="t0")
    plan.legs_realized.append({"fraction": 0.5, "exit_price": 100.0 + 10 * sign,
                               "r": 2.0, "reason": "tp1"})
    record_transition(plan, PlanStatus.PARTIAL, reason="tp1_partial", at="t1")
    record_transition(plan, PlanStatus.CLOSED, reason="trade_deleted", at="t2")
    return plan


def _texts(instruction):
    return [instruction.headline, *instruction.lines, *instruction.warnings]


# --- cancelled_trade_deleted -----------------------------------------------------

def test_it_is_a_pending_cancel_and_a_notice():
    assert EVENT in plan_manager.PENDING_CANCEL_EVENTS
    assert EVENT in plan_manager.NOTICE_EVENTS
    assert plan_manager._TRANSITION_LOG[EVENT] == ("trade deleted", "live_price")


@pytest.mark.parametrize("direction, order", [("bullish", "BUY STOP"), ("bearish", "SELL STOP")])
def test_the_feed_words_the_cancel(direction, order):
    instruction = ins.instruction_for(_cancelled(direction), PlanEvent("p1", EVENT, CANCEL_DETAIL))
    assert (instruction.verb, instruction.tone) == (ins.CANCEL, "inert")
    assert instruction.headline == f"CANCEL {order} 100.00"
    assert instruction.lines == (WHY,)
    assert ins._CANCEL_LEADS[EVENT] == ""
    assert ins._BUILDERS[EVENT] is ins._cancelled


def test_both_embed_tables_render_it_as_cancel():
    assert lifecycle_embeds.PLAN_EVENT_KINDS[EVENT] is Kind.CANCEL
    assert execution_embeds._EVENT_KINDS[EVENT] is Kind.CANCEL
    assert execution_embeds._event_style(_cancelled(), PlanEvent("p1", EVENT, CANCEL_DETAIL),
                                         None) == (Kind.CANCEL, None, None)


def test_the_history_embed_says_why():
    embed = build_plan_event_embed(_cancelled(), PlanEvent("p1", EVENT, CANCEL_DETAIL))
    assert embed.title == "🚫 ▲ LONG AAPL · CANCEL"
    why = next(f.value for f in embed.fields if f.name == "Why")
    assert why == ("The trade record was deleted before the 100.00 order filled. "
                   "Never opened; no position, no P&L.")


def test_the_outlook_code_and_message():
    assert se.TRADE_DELETED == "trade_deleted"
    assert se.code_for(EVENT) == se.TRADE_DELETED
    assert se.in_session_message(_cancelled(), EVENT, CANCEL_DETAIL) == (
        "The trade record was deleted before the order filled; nothing opened")


def test_the_follow_channel_posts_it_as_a_factual_cancel():
    event = PlanEvent("p1", EVENT, CANCEL_DETAIL)
    assert fn.notify_event_for(event) == "closed_other"
    assert fn.kind_for(event, "closed_other") is Kind.INVALIDATED
    line = fn.message_line(_cancelled(), "closed_other", EVENT, CANCEL_DETAIL)
    assert line == "Paper plan update: AAPL long cancelled: trade record deleted before fill."
    assert not [p for p in fn.FORBIDDEN_PHRASES if p in line.lower()]


def test_every_pending_cancel_event_has_every_row():
    cancels = plan_manager.PENDING_CANCEL_EVENTS
    assert cancels <= set(ins._BUILDERS) and cancels <= set(ins._CANCEL_LEADS)
    assert cancels <= set(lifecycle_embeds.PLAN_EVENT_KINDS)
    assert cancels <= set(lifecycle_embeds._EVENT_FIELDS)
    assert cancels <= set(execution_embeds._EVENT_KINDS)
    assert all(fn.notify_event_for(PlanEvent("p1", t, {})) is not None for t in cancels)


# --- closed with reason trade_deleted ------------------------------------------------

@pytest.mark.parametrize("direction, exit_verb", [("bullish", "SELL AT MARKET"),
                                                  ("bearish", "BUY TO COVER AT MARKET")])
def test_the_feed_says_no_longer_monitored_with_no_exit(direction, exit_verb):
    instruction = ins.instruction_for(_closed_partial(direction),
                                      PlanEvent("p1", "closed", CLOSE_DETAIL))
    assert (instruction.verb, instruction.tone) == (ins.EXITED, "inert")
    assert instruction.headline == "NO LONGER MONITORED · trade record deleted"
    text = "\n".join(_texts(instruction))
    assert exit_verb in text
    assert "@" not in text and "n/a" not in text


def test_the_feed_embed_is_a_grey_withdrawn_result_with_no_r(monkeypatch):
    plan = _closed_partial()
    event = PlanEvent("p1", "closed", CLOSE_DETAIL)
    monkeypatch.setattr(execution_embeds, "_event_money", lambda plan_: None)
    instruction = ins.instruction_for(plan, event)
    assert execution_embeds._event_style(plan, event, instruction) == (Kind.INVALIDATED, None, None)
    embed = execution_embeds.build_instruction_embed(plan, event)
    assert "INVALIDATED" in embed.title
    assert "NO LONGER MONITORED" in embed.description


def test_the_follow_channel_says_no_longer_monitored():
    plan = _closed_partial()
    event = PlanEvent("p1", "closed", CLOSE_DETAIL)
    assert fn.notify_event_for(event) == "closed_other"
    assert fn.kind_for(event, "closed_other") is Kind.INVALIDATED
    line = fn.message_line(plan, "closed_other", "closed", CLOSE_DETAIL)
    assert line == "Paper plan update: AAPL long is no longer monitored: its trade record was deleted."
    embed = fn.build_notify_embed(plan, "closed_other", "closed", CLOSE_DETAIL)
    assert "INVALIDATED" in embed.title
    assert embed.push_text == line


@pytest.mark.parametrize("reason", ["time_exit", "loss"])
def test_an_ordinary_close_is_unchanged(reason):
    plan = _closed_partial()
    event = PlanEvent("p1", "closed", {"reason": reason, "exit_price": 104.0})
    assert fn.kind_for(event, "closed_other") is Kind.EXITED
    kind, block, r = execution_embeds._event_style(plan, event, ins.instruction_for(plan, event))
    assert kind is Kind.EXITED and block is not None and r is not None
