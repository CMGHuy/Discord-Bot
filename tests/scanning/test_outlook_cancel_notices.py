"""v144: an outlook plan's cancel notice says why, in the catalogue's words."""
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import instructions as ins
from swingbot.core.scanning.lifecycle_embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

MESSAGE = "High 101.40 stopped 0.6% (0.4 ATR) short of the 102.00 trigger"


def _outlook():
    return _plan(source="confluence", entry_type="stop_entry", trigger_price=102.0, stop_loss=100.5,
                 tp1=106.0, tp2=None, status="CANCELLED", origin="next_session", valid_session="2026-10-12")


def _expired(**extra):
    return PlanEvent("p1", "cancelled_expired", {
        "bars_waited": 1, "cancel_resting_order": True, "eligible_session": "2026-10-12",
        "expires_at": "2026-10-12T16:00:00-04:00", **extra})


def _why(embed):
    return next(field.value for field in embed.fields if field.name == "Why")


def test_the_feed_instruction_quotes_the_reason():
    event = _expired(reason_code="never_triggered", reason_message=MESSAGE)
    assert ins.instruction_for(_outlook(), event).lines == (MESSAGE,)


def test_the_lifecycle_embed_quotes_the_reason_and_code():
    event = _expired(reason_code="never_triggered", reason_message=MESSAGE)
    assert _why(build_plan_event_embed(_outlook(), event)) == f"{MESSAGE} (never_triggered)"


def test_an_in_session_cancel_uses_it_too():
    event = PlanEvent("p1", "cancelled_invalidated", {
        "live_price": 100.4, "reason_code": "invalidated",
        "reason_message": "Traded 100.40 through the 100.50 stop before triggering; the setup broke"})
    assert _why(build_plan_event_embed(_outlook(), event)).endswith("(invalidated)")


def test_a_regular_expiry_renders_as_before():
    plan = _plan(entry_type="stop_entry", trigger_price=102.0, expiry_bars=5, status="CANCELLED")
    event = PlanEvent("p1", "cancelled_expired", {"bars_waited": 6})
    assert ins.instruction_for(plan, event).lines == ("not triggered within 5 sessions",)
    assert _why(build_plan_event_embed(plan, event)).startswith("Never triggered — 6 bar(s) waited")
