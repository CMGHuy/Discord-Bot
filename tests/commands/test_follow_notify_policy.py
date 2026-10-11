"""v152 D1: follow_notify's event mapping and mention policy (pure tables)."""
import ast
import inspect

import pytest

from swingbot.commands.scanning import follow_notify as fn
from swingbot.core.planning.plan_manager import _STOPPED_REASONS, PlanEvent
from swingbot.core.presentation.kinds import Kind

FOLLOWING = frozenset({"taken"})
WATCH = frozenset({"watch"})
BOTH = frozenset({"watch", "taken"})


def _event(transition, reason=None):
    return PlanEvent("p1", transition, {"reason": reason} if reason else {})


@pytest.mark.parametrize("transition, reason, expected, kind", [
    ("near_stop", None, "near_stop", Kind.NEAR_STOP),
    ("tp1_partial", None, "tp1", Kind.TP1_HIT),
    ("closed", "win", "tp1", Kind.TP1_HIT),
    ("closed", "tp1_runner_tp2", "tp2", Kind.WIN),
    ("closed", "loss", "stopped", Kind.STOPPED),
    ("closed", "scratch", "stopped", Kind.STOPPED),
    ("closed", "tp1_runner_be", "stopped", Kind.STOPPED),
    ("closed", "tp1_runner_trail", "stopped", Kind.STOPPED),
    ("cancelled_expired", None, "expired", Kind.EXPIRED),
    ("closed", "time_exit", "closed_other", Kind.EXITED),
    ("closed", "stall_exit", "closed_other", Kind.EXITED),
    ("closed", "tp1_runner_progress_stall", "closed_other", Kind.EXITED),
    ("closed", None, "closed_other", Kind.EXITED),
    ("cancelled_invalidated", None, "closed_other", Kind.INVALIDATED),
    ("cancelled_risk_cap", None, "closed_other", Kind.RISK_CAP),
])
def test_each_transition_picks_its_notify_event_and_kind(transition, reason, expected, kind):
    event = _event(transition, reason)
    assert fn.notify_event_for(event) == expected
    assert fn.kind_for(event, expected) is kind


@pytest.mark.parametrize("transition", ["filled", "be_moved", "stop_moved", "pyramid_add",
                                        "time_exit_due", "time_exit_unresolved"])
def test_other_transitions_are_not_notify_events(transition):
    assert fn.notify_event_for(_event(transition)) is None


def test_every_stopped_reason_is_mapped():
    assert {reason for (t, reason), ev in fn._BY_REASON.items() if ev == "stopped"} == set(
        _STOPPED_REASONS)


def test_the_six_events_share_one_table():
    assert fn.NOTIFY_EVENTS == ("near_stop", "tp1", "tp2", "stopped", "expired", "closed_other")
    assert tuple(fn.EVENT_LABELS) == fn.NOTIFY_EVENTS
    assert tuple(fn.WATCH_DEFAULTS) == fn.NOTIFY_EVENTS
    assert set(fn._BY_TRANSITION.values()) | set(fn._BY_REASON.values()) == set(fn.NOTIFY_EVENTS)
    assert "Following only" in fn.EVENT_LABELS["closed_other"]


def test_imperative_kinds_are_never_used():
    source = inspect.getsource(fn)
    assert "MOVE_STOP" not in source and "Kind.CANCEL" not in source


@pytest.mark.parametrize("event", ["near_stop", "tp1", "tp2", "stopped", "expired", "closed_other"])
def test_following_defaults_on_for_every_event(event):
    assert fn.mentions_user(FOLLOWING, event, {}) is True
    assert fn.mentions_user(BOTH, event, {}) is True


@pytest.mark.parametrize("event, expected", [
    ("near_stop", False), ("tp1", True), ("tp2", True), ("stopped", True),
    ("expired", False), ("closed_other", False),
])
def test_watch_only_defaults(event, expected):
    assert fn.mentions_user(WATCH, event, {}) is expected


def test_an_explicit_toggle_overrides_the_default_for_either_kind():
    assert fn.mentions_user(WATCH, "near_stop", {"near_stop": True}) is True
    assert fn.mentions_user(WATCH, "tp1", {"tp1": False}) is False
    assert fn.mentions_user(FOLLOWING, "stopped", {"stopped": False}) is False


def test_watch_only_is_never_mentioned_for_closed_other_even_when_toggled_on():
    assert fn.mentions_user(WATCH, "closed_other", {"closed_other": True}) is False


def test_silent_watch_mode_drops_watch_only_mentions_but_not_following():
    prefs = {"watch_mode": "silent", "tp1": True}
    assert fn.mentions_user(WATCH, "tp1", prefs) is False
    assert fn.mentions_user(FOLLOWING, "tp1", prefs) is True
    assert fn.mentions_user(BOTH, "tp1", prefs) is True
    assert fn.mentions_user(WATCH, "tp1", {"watch_mode": "mention"}) is True


def test_eligible_mentions_are_sorted_and_use_each_users_prefs():
    followers = {30: WATCH, 10: FOLLOWING, 20: WATCH}
    prefs = {20: {"watch_mode": "silent"}}
    assert fn.eligible_mentions(followers, "tp1", prefs) == [10, 30]
    assert fn.eligible_mentions(followers, "near_stop", prefs) == [10]
    assert fn.eligible_mentions(followers, "closed_other", {}) == [10]
    assert fn.eligible_mentions({}, "tp1", {}) == []


def test_closed_other_posts_only_with_a_following_follower():
    assert fn.posts_message("closed_other", {1: WATCH}) is False
    assert fn.posts_message("closed_other", {}) is False
    assert fn.posts_message("closed_other", {1: WATCH, 2: BOTH}) is True


@pytest.mark.parametrize("event", ["near_stop", "tp1", "tp2", "stopped", "expired"])
def test_every_other_event_posts_with_or_without_followers(event):
    assert fn.posts_message(event, {}) is True
    assert fn.posts_message(event, {1: WATCH}) is True


def test_the_policy_is_tables_not_if_chains():
    tree = ast.parse(inspect.getsource(fn))
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            assert not (node.orelse and isinstance(node.orelse[0], ast.If)), (
                f"if/elif chain at line {node.lineno}: use a table")
