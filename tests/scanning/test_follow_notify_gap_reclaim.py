"""V192-11: the follow-notify channel's mapping of the waiting market plan's
events: the reclaim order is its own event; the two cancels are closed_other.
Also the lifecycle embed's Why field for the two cancels."""
import pytest

from swingbot import config
from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning.plan_manager import PlanEvent
from swingbot.core.presentation.kinds import Kind
from swingbot.core.scanning.lifecycle_embeds import build_plan_event_embed
from tests.planning.test_plan_engine_model import _plan

FOLLOWING = frozenset({"taken"})
WATCH = frozenset({"watch"})


def _waiting(direction="bullish", status="PENDING"):
    levels = (dict(stop_loss=98.5, tp1=103.0) if direction == "bullish"
              else dict(stop_loss=101.5, tp1=97.0, tp2=95.0))
    return _plan(source="confluence", strategy="S/R Confluence", direction=direction,
                 trigger_price=100.0, waits_next_open=True, status=status, **levels)


ORDER = {"entry_price": 100.0, "open_price": 99.0, "reclaim_level": 99.5,
         "order": "buy_stop", "tif": "DAY"}


@pytest.mark.parametrize("transition, event, kind", [
    ("gap_reclaim_order", "reclaim_order", Kind.RECLAIM_ORDER),
    ("cancelled_open_through_stop", "closed_other", Kind.INVALIDATED),
    ("cancelled_gap_no_reclaim", "closed_other", Kind.EXPIRED),
])
def test_mapping_and_kind(transition, event, kind):
    plan_event = PlanEvent("p1", transition, {})
    assert fn.notify_event_for(plan_event) == event
    assert fn.kind_for(plan_event, event) is kind


def test_reclaim_order_is_a_registered_notify_event():
    assert "reclaim_order" in fn.NOTIFY_EVENTS and "reclaim_order" in fn.COPY
    assert fn.NOTIFY_EVENTS.index("reclaim_order") == fn.NOTIFY_EVENTS.index("closed_other") - 1
    assert fn.mentions_user(FOLLOWING, "reclaim_order", {}) is True
    assert fn.mentions_user(WATCH, "reclaim_order", {}) is False
    assert fn.mentions_user(WATCH, "reclaim_order", {"reclaim_order": True}) is True
    assert fn.posts_message("reclaim_order", {1: WATCH}) is True


@pytest.mark.parametrize("direction, order, side", [("bullish", "buy-stop", "long"),
                                                    ("bearish", "sell-stop", "short")])
def test_the_reclaim_order_copy(direction, order, side):
    line = fn.message_line(_waiting(direction), "reclaim_order", "gap_reclaim_order",
                           {**ORDER, "open_price": 99.0 if direction == "bullish" else 101.0})
    opened = "99.00" if direction == "bullish" else "101.00"
    assert line == (f"Paper plan update: AAPL {side} opened at {opened}, toward its stop; it "
                    f"now enters only on a DAY {order} at 100.00 this session.")
    assert not [p for p in fn.FORBIDDEN_PHRASES if p in line.lower()]


@pytest.mark.parametrize("transition, phrase", [
    ("cancelled_open_through_stop", "cancelled: opened at or through its stop."),
    ("cancelled_gap_no_reclaim", "cancelled: opened toward stop, no reclaim."),
])
def test_the_cancel_copy(transition, phrase):
    line = fn.message_line(_waiting(status="CANCELLED"), "closed_other", transition, {})
    assert line == f"Paper plan update: AAPL long {phrase}"


def test_the_cancels_post_only_with_a_following_follower():
    assert fn.posts_message("closed_other", {1: WATCH}) is False
    assert fn.posts_message("closed_other", {1: FOLLOWING}) is True


def test_the_reclaim_order_embed_renders(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")
    embed = fn.build_notify_embed(_waiting(), "reclaim_order", "gap_reclaim_order", ORDER)
    assert "STOP ORDER AT ENTRY" in embed.title
    assert "DAY buy-stop at 100.00" in embed.description


def _why(embed):
    return next(f.value for f in embed.fields if f.name == "Why")


@pytest.mark.parametrize("transition, detail, expected", [
    ("cancelled_open_through_stop", {"live_price": 98.0, "phase": "open"},
     "Opened at 98.00, at or through the stop 98.50, before the 100.00 entry. "
     "Never opened; no position, no P&L."),
    ("cancelled_gap_no_reclaim", {"entry_price": 100.0, "session": "2026-10-14"},
     "Opened toward the stop and never reclaimed the 100.00 entry in the "
     "2026-10-14 session. Never opened; no position, no P&L."),
])
def test_the_lifecycle_embed_states_why(monkeypatch, transition, detail, expected):
    monkeypatch.setattr(config, "ADMIN_PUBLIC_URL", "https://example.test")
    embed = build_plan_event_embed(_waiting(status="CANCELLED"), PlanEvent("p1", transition, detail))
    assert _why(embed) == expected
