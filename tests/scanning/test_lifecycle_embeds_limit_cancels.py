"""v187 D3: the two new pending cancels render as CANCEL in the history
embeds and the execution feed, each with a Why field from its own detail."""
import pytest

from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning import execution_embeds, lifecycle_embeds
from swingbot.core.scanning.embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

NEW_CANCELS = ("cancelled_limit", "cancelled_gap_through_stop")


def _limit(**kw):
    base = dict(entry_type="limit", direction="bullish", trigger_price=100.0,
                entry_price=None, stop_loss=98.5, tp1=102.0, tp2=104.0,
                limit_cancel_level=101.0, status="CANCELLED")
    base.update(kw)
    return _plan(**base)


def _why(embed) -> str:
    return next(f.value for f in embed.fields if f.name == "Why")


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_both_tables_map_the_new_cancels_to_cancel(transition):
    assert lifecycle_embeds.PLAN_EVENT_KINDS[transition] is Kind.CANCEL
    assert execution_embeds._EVENT_KINDS[transition] is Kind.CANCEL


@pytest.mark.parametrize("transition", NEW_CANCELS)
def test_the_feed_styles_the_new_cancels_as_cancel(transition):
    event = PlanEvent("p1", transition, {})
    assert execution_embeds._event_style(_limit(), event, None) == (Kind.CANCEL, None, None)


def test_a_limit_cancel_embed_names_the_level_and_the_price():
    embed = build_plan_event_embed(_limit(), PlanEvent(
        "p1", "cancelled_limit", {"live_price": 101.2, "limit_cancel_level": 101.0}))
    assert embed.title == "🚫 ▲ LONG AAPL · CANCEL"
    assert embed.color.value == kinds.MANAGE_AMBER
    assert _why(embed) == (
        "Price ran to 101.20, past the limit's cancel level 101.00, before the "
        "100.00 limit filled. Never opened; no position, no P&L.")


def test_a_gap_through_stop_embed_names_the_limit_the_price_and_the_stop():
    embed = build_plan_event_embed(_limit(), PlanEvent(
        "p1", "cancelled_gap_through_stop",
        {"entry_price": 100.0, "live_price": 98.4, "stop_loss": 98.5}))
    assert embed.title == "🚫 ▲ LONG AAPL · CANCEL"
    assert _why(embed) == (
        "Touched the 100.00 limit at 98.40, already at or through the stop 98.50. "
        "Never opened; no position, no P&L.")


def test_a_stated_outlook_reason_still_wins():
    embed = build_plan_event_embed(_limit(), PlanEvent(
        "p1", "cancelled_limit", {"live_price": 101.2, "limit_cancel_level": 101.0,
                                  "reason_message": "Ran past the cancel level",
                                  "reason_code": "limit_cancelled"}))
    assert _why(embed) == "Ran past the cancel level (limit_cancelled)"


def test_every_pending_cancel_event_has_a_kind_and_fields():
    from swingbot.core.planning import plan_manager
    cancels = getattr(plan_manager, "PENDING_CANCEL_EVENTS", None)
    if cancels is None:              # V187-8 not merged into this branch yet
        cancels = frozenset({"cancelled_expired", "cancelled_invalidated",
                             "cancelled_risk_cap", *NEW_CANCELS})
    assert cancels <= set(lifecycle_embeds.PLAN_EVENT_KINDS)
    assert cancels <= set(lifecycle_embeds._EVENT_FIELDS)
    assert cancels <= set(execution_embeds._EVENT_KINDS)
