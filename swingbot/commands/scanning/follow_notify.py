"""v152 D1: the follow-notify channel (DISCORD_CHANNEL_NOTIFY_ID).

Factual paper-plan updates for plans people follow -- near stop, TP1, TP2,
stopped, expired, and closed/cancelled for Following followers only -- each
mentioning the followers who want it. This first part is pure policy: which
PlanEvent is which notify event, which Kind it renders as, and whom it
mentions. The copy table and embed (V152-16) and the claim / send / retry
delivery (V152-17) build on these tables. No if/elif chains: every rule is
a table.
"""
from __future__ import annotations

from swingbot.core.planning.plan_manager import _STOPPED_REASONS, PlanEvent
from swingbot.core.presentation.kinds import Kind

NOTIFY_EVENTS = ("near_stop", "tp1", "tp2", "stopped", "expired", "closed_other")

# What the channel announces, in /notify's words (factual, no imperatives).
EVENT_LABELS = {
    "near_stop": "Near stop: price within 0.25R of the plan's stop (regular session)",
    "tp1": "TP1 reached",
    "tp2": "Closed at TP2",
    "stopped": "Closed at its stop (initial, breakeven or trailing)",
    "expired": "Expired unfilled",
    "closed_other": "Closed or cancelled for any other reason (Following only)",
}

# Posted only when the plan has at least one Following follower.
FOLLOWING_ONLY = frozenset({"closed_other"})

# (transition, reason) first, then transition; "closed" falls back to closed_other.
_BY_REASON: dict[tuple[str, str], str] = {
    ("closed", "win"): "tp1",                 # no-TP2 plan closed whole at TP1
    ("closed", "tp1_runner_tp2"): "tp2",
    **{("closed", reason): "stopped" for reason in sorted(_STOPPED_REASONS)},
}
_BY_TRANSITION: dict[str, str] = {
    "near_stop": "near_stop",
    "tp1_partial": "tp1",
    "cancelled_expired": "expired",
    "cancelled_invalidated": "closed_other",
    "cancelled_risk_cap": "closed_other",
    "closed": "closed_other",
}

_KIND_BY_EVENT = {
    "near_stop": Kind.NEAR_STOP,
    "tp1": Kind.TP1_HIT,
    "tp2": Kind.WIN,
    "stopped": Kind.STOPPED,
    "expired": Kind.EXPIRED,
}
_CLOSED_OTHER_KIND = {
    "closed": Kind.EXITED,
    "cancelled_invalidated": Kind.INVALIDATED,
    "cancelled_risk_cap": Kind.RISK_CAP,
}

FOLLOWING_DEFAULTS: dict[str, bool] = dict.fromkeys(NOTIFY_EVENTS, True)
WATCH_DEFAULTS: dict[str, bool] = {
    "near_stop": False,
    "tp1": True,
    "tp2": True,
    "stopped": True,
    "expired": False,
    "closed_other": False,
}


def notify_event_for(event: PlanEvent) -> str | None:
    """The notify event a PlanEvent announces, or None when it announces none."""
    reason = (event.detail or {}).get("reason")
    return _BY_REASON.get((event.transition, reason)) or _BY_TRANSITION.get(event.transition)


def kind_for(event: PlanEvent, notify_event: str) -> Kind:
    """The registry Kind the message renders as (never MOVE STOP or CANCEL)."""
    if notify_event == "closed_other":
        return _CLOSED_OTHER_KIND[event.transition]
    return _KIND_BY_EVENT[notify_event]


def mentions_user(kinds: frozenset[str], notify_event: str, prefs: dict) -> bool:
    """Whether one follower is mentioned. Following (a 'taken' row) wins over
    Watch; Watch-only is never mentioned for closed_other or in silent mode;
    otherwise an explicit per-event toggle beats the default."""
    following = "taken" in kinds
    if not following and (notify_event in FOLLOWING_ONLY or prefs.get("watch_mode") == "silent"):
        return False
    explicit = prefs.get(notify_event)
    if isinstance(explicit, bool):
        return explicit
    return (FOLLOWING_DEFAULTS if following else WATCH_DEFAULTS)[notify_event]


def eligible_mentions(followers: dict[int, frozenset[str]], notify_event: str,
                      prefs_by_user: dict[int, dict]) -> list[int]:
    """Sorted user ids to mention for one message."""
    return sorted(user_id for user_id, kinds in followers.items()
                  if mentions_user(kinds, notify_event, prefs_by_user.get(user_id, {})))


def posts_message(notify_event: str, followers: dict[int, frozenset[str]]) -> bool:
    """Every event posts, except closed_other without a Following follower."""
    return notify_event not in FOLLOWING_ONLY or any(
        "taken" in kinds for kinds in followers.values())
