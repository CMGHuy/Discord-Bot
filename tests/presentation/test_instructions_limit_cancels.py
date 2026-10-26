"""v187 D3: the execution feed words the two new pending cancels -- a limit
cancelled beyond its cancel level, and a limit that touched at or through its
stop -- instead of falling through to the risk-cap sentence (KeyError)."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.presentation import tokens
from tests.planning.test_plan_engine_model import _plan

NEW_CANCELS = ("cancelled_limit", "cancelled_gap_through_stop")


def _limit(direction="bullish", **kw):
    levels = (dict(trigger_price=100.0, stop_loss=98.5, tp1=102.0, limit_cancel_level=101.0)
              if direction == "bullish" else
              dict(trigger_price=100.0, stop_loss=101.5, tp1=98.0, limit_cancel_level=99.0))
    base = dict(entry_type="limit", direction=direction, entry_price=None,
                status="PENDING", **levels)
    base.update(kw)
    return _plan(**base)


def _event(transition, **detail):
    return PlanEvent("p1", transition, detail)


def test_a_limit_cancel_explains_the_cancel_level():
    instruction = ins.instruction_for(
        _limit(), _event("cancelled_limit", live_price=101.2, limit_cancel_level=101.0))
    assert (instruction.verb, instruction.tone) == (ins.CANCEL, "inert")
    assert instruction.headline == "CANCEL BUY STOP 100.00"
    assert instruction.lines == (
        "Price ran past the limit's cancel level 101.00 at 101.20 before the order "
        "filled. Nothing was opened.",)


def test_a_gap_through_the_stop_explains_why_nothing_opened():
    instruction = ins.instruction_for(
        _limit("bearish"),
        _event("cancelled_gap_through_stop", entry_price=100.0, live_price=101.6,
               stop_loss=101.5))
    assert (instruction.verb, instruction.tone) == (ins.CANCEL, "inert")
    assert instruction.headline == "CANCEL SELL STOP 100.00"
    assert instruction.lines == (
        "Price touched the limit at 101.60, already at or through the stop 101.50. "
        "The order is cancelled, nothing was opened.",)


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_new_cancels_carry_no_lead_glyph(transition):
    assert ins._CANCEL_LEADS[transition] == ""
    assert ins._BUILDERS[transition] is ins._cancelled


def test_every_cancel_lead_is_empty_or_a_feed_symbol():
    assert all(key == "" or key in tokens.FEED_SYMBOLS for key in ins._CANCEL_LEADS.values())


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_a_stated_outlook_reason_still_wins(transition):
    instruction = ins.instruction_for(
        _limit(), _event(transition, live_price=101.2, limit_cancel_level=101.0,
                         reason_message="Ran past the cancel level"))
    assert instruction.lines == ("Ran past the cancel level",)


def test_every_pending_cancel_event_has_a_builder_and_a_lead():
    from swingbot.core.planning import plan_manager
    cancels = getattr(plan_manager, "PENDING_CANCEL_EVENTS", None)
    if cancels is None:              # V187-8 not merged into this branch yet
        cancels = frozenset({"cancelled_expired", "cancelled_invalidated",
                             "cancelled_risk_cap", *NEW_CANCELS})
    assert cancels <= set(ins._BUILDERS)
    assert cancels <= set(ins._CANCEL_LEADS)


@pytest.mark.parametrize("transition,detail,expected", [
    ("cancelled_limit", dict(live_price=98.8, limit_cancel_level=99.0),
     "Price ran past the limit's cancel level 99.00 at 98.80 before the order "
     "filled. Nothing was opened."),
    ("cancelled_gap_through_stop",
     dict(entry_price=100.0, live_price=101.6, stop_loss=101.5),
     "Price touched the limit at 101.60, already at or through the stop 101.50. "
     "The order is cancelled, nothing was opened."),
])
def test_limit_cancel_wording_precedes_compression_dispatch(transition, detail, expected):
    from swingbot.core.market.strategy_types import COMPRESSION_SHORT

    instruction = ins.instruction_for(
        _limit("bearish", strategy=COMPRESSION_SHORT), _event(transition, **detail))
    assert instruction.lines == (expected,)
