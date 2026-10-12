"""v152 D1: the follow-notify channel (DISCORD_CHANNEL_NOTIFY_ID).

Factual paper-plan updates for plans people follow -- near stop, TP1, TP2,
stopped, expired, and closed/cancelled for Following followers only -- each
mentioning the followers who want it. This first part is pure policy: which
PlanEvent is which notify event, which Kind it renders as, and whom it
mentions. The factual copy table and linked embed build on these policies;
claim / send / retry delivery (V152-17) builds on the same tables. No if/elif
chains: every rule is a table.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.planning.plan_manager import _STOPPED_REASONS, PlanEvent, resting_stop
from swingbot.core.presentation import instructions
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


# Factual paper-plan copy is independent of the imperative execution feed.
FORBIDDEN_PHRASES = (
    "exit now", "move stop", "move your stop", "take profit", "sell now",
    "buy now", "close your", "you should",
)
FOOTER = "Paper plan update, not advice."
_STOP_LABELS = {
    "loss": "at its stop",
    "scratch": "at breakeven",
    "tp1_runner_be": "at its runner stop",
    "tp1_runner_trail": "at its trailing stop",
}
_EXIT_LABELS = {
    "time_exit": "time exit",
    "stall_exit": "stall exit",
    "tp1_runner_progress_stall": "structure exit",
}
_CANCEL_LABELS = {
    "cancelled_invalidated": "invalidated before entry",
    "cancelled_risk_cap": "risk cap reached",
}


def _signed_close_r(plan, detail: dict) -> str:
    value = round(instructions.total_r(plan, detail.get("exit_price")), 1)
    value = value if value else 0.0
    return ("+" if value > 0 else "") + ui.fmt_r(value)


def _near_stop_copy(plan, transition: str, detail: dict) -> str:
    distance = detail.get("r_dist")
    distance_text = f"{distance:.2f}R" if distance is not None else ui.ABSENT
    return f"is {distance_text} from its stop, last {ui.fmt_price(detail.get('price'))}."


def _tp1_copy(plan, transition: str, detail: dict) -> str:
    if transition == "closed":
        return _target_close_copy(plan, "TP1", detail)
    return f"reached TP1 at {ui.fmt_price(detail.get('price'))}."


def _target_close_copy(plan, target: str, detail: dict) -> str:
    return (f"closed at {target} {ui.fmt_price(detail.get('exit_price'))}: "
            f"{_signed_close_r(plan, detail)}.")


def _tp2_copy(plan, transition: str, detail: dict) -> str:
    return _target_close_copy(plan, "TP2", detail)


def _stopped_copy(plan, transition: str, detail: dict) -> str:
    label = _STOP_LABELS.get(detail.get("reason"), "at its stop")
    return (f"closed {label} {ui.fmt_price(detail.get('exit_price'))}: "
            f"{_signed_close_r(plan, detail)}.")


def _expired_copy(plan, transition: str, detail: dict) -> str:
    return "expired unfilled."


def _other_copy(plan, transition: str, detail: dict) -> str:
    if transition != "closed":
        label = _CANCEL_LABELS.get(transition, "withdrawn before entry")
        return f"cancelled: {label}."
    reason = detail.get("reason") or "other exit"
    label = _EXIT_LABELS.get(reason, reason.replace("_", " "))
    return (f"closed by {label} at {ui.fmt_price(detail.get('exit_price'))}: "
            f"{_signed_close_r(plan, detail)}.")


COPY = {
    "near_stop": _near_stop_copy,
    "tp1": _tp1_copy,
    "tp2": _tp2_copy,
    "stopped": _stopped_copy,
    "expired": _expired_copy,
    "closed_other": _other_copy,
}


def message_line(plan, notify_event: str, transition: str, detail: dict) -> str:
    """Describe the paper event and the current levels of any open position."""
    side = "long" if plan.direction == "bullish" else "short"
    phrase = COPY[notify_event](plan, transition, detail)
    line = f"Paper plan update: {plan.ticker} {side} {phrase}"
    if plan.status in {"ACTIVE", "PARTIAL"}:
        target = plan.tp1 if plan.status == "ACTIVE" else plan.tp2
        line += (f" Stop now at {ui.fmt_price(resting_stop(plan))}, "
                 f"remaining target {ui.fmt_price(target)}.")
    return line


def build_notify_embed(plan, notify_event: str, transition: str, detail: dict) -> ui.PushEmbed:
    """Build a registry-styled factual update, linked to the current admin URL."""
    kind = kind_for(PlanEvent(plan.plan_id, transition, detail), notify_event)
    line = message_line(plan, notify_event, transition, detail)
    embed = ui.push_embed(kind, plan.ticker, plan.direction, description=line)
    embed.push_text = line
    close_r = instructions.total_r(plan, detail.get("exit_price")) if transition == "closed" else None
    ui.apply_chrome(embed, kind=kind, plan_id=plan.plan_id, r=close_r,
                    link_base=config.ADMIN_PUBLIC_URL)
    embed.set_footer(text=embed.footer.text + " · " + FOOTER)
    return embed
