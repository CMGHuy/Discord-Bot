"""v187 D3: the two new pending cancels in the follow channel (factual, never
an imperative kind) and in an outlook plan's catalogue (code + message)."""
import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning import session_expiry as se
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation.kinds import Kind
from tests.planning.test_plan_engine_model import _plan

NEW_CANCELS = ("cancelled_limit", "cancelled_gap_through_stop")

_DETAIL = {
    "cancelled_limit": {"live_price": 101.2, "limit_cancel_level": 101.0},
    "cancelled_gap_through_stop": {"entry_price": 100.0, "live_price": 98.4, "stop_loss": 98.5},
}


def _limit(**kw):
    base = dict(entry_type="limit", direction="bullish", trigger_price=100.0,
                entry_price=None, stop_loss=98.5, tp1=102.0, tp2=104.0,
                limit_cancel_level=101.0, status="CANCELLED")
    base.update(kw)
    return _plan(**base)


# --- follow channel ------------------------------------------------------------

@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_new_cancels_are_closed_other_and_render_invalidated(transition):
    event = PlanEvent("p1", transition, _DETAIL[transition])
    assert fn.notify_event_for(event) == "closed_other"
    assert fn.kind_for(event, "closed_other") is Kind.INVALIDATED


@pytest.mark.parametrize("transition, line", [
    ("cancelled_limit", "Paper plan update: AAPL long cancelled: limit cancelled before fill."),
    ("cancelled_gap_through_stop",
     "Paper plan update: AAPL long cancelled: gapped through the stop before fill."),
])
def test_the_follow_copy_names_the_reason(transition, line):
    assert fn.message_line(_limit(), "closed_other", transition, _DETAIL[transition]) == line


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_follow_copy_is_factual(transition):
    line = fn.message_line(_limit(), "closed_other", transition, _DETAIL[transition]).lower()
    assert not [phrase for phrase in fn.FORBIDDEN_PHRASES if phrase in line]


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_follow_embed_builds(transition):
    embed = fn.build_notify_embed(_limit(), "closed_other", transition, _DETAIL[transition])
    assert "INVALIDATED" in embed.title
    assert "cancelled:" in embed.push_text


def test_every_pending_cancel_event_announces_something():
    from swingbot.core.planning import plan_manager
    cancels = getattr(plan_manager, "PENDING_CANCEL_EVENTS", None)
    if cancels is None:              # V187-8 not merged into this branch yet
        cancels = frozenset({"cancelled_expired", "cancelled_invalidated",
                             "cancelled_risk_cap", *NEW_CANCELS})
    assert all(fn.notify_event_for(PlanEvent("p1", t, {})) is not None for t in cancels)


# --- outlook catalogue ---------------------------------------------------------

def test_the_new_codes():
    assert (se.LIMIT_CANCELLED, se.GAP_THROUGH_STOP) == ("limit_cancelled", "gap_through_stop")
    assert se.code_for("cancelled_limit") == se.LIMIT_CANCELLED
    assert se.code_for("cancelled_gap_through_stop") == se.GAP_THROUGH_STOP


def test_the_limit_cancel_message():
    assert se.in_session_message(_limit(), "cancelled_limit", _DETAIL["cancelled_limit"]) == (
        "Ran to 101.20, past the 101.00 cancel level, before the 100.00 limit filled")


def test_the_gap_through_stop_message():
    assert se.in_session_message(
        _limit(), "cancelled_gap_through_stop", _DETAIL["cancelled_gap_through_stop"]) == (
        "Touched the 100.00 limit at 98.40, already at or through the 98.50 stop; "
        "nothing opened")


def test_other_transitions_still_have_no_message():
    assert se.in_session_message(_limit(), "filled", {}) is None
    assert se.in_session_message(_limit(), "cancelled_expired", {}) is None
