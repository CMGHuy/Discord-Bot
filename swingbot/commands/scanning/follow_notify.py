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

import asyncio
import datetime as dt
import logging

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.db.repositories.notifications import MAX_ATTEMPTS
from swingbot.core.infra.posted_log import log_posted
from swingbot.core.planning.plan_manager import _STOPPED_REASONS, PlanEvent, resting_stop
from swingbot.core.presentation import instructions
from swingbot.core.presentation.kinds import Kind

log = logging.getLogger(__name__)

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
FOOTER = "Paper plan update, not advice. R is before costs and tax."
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
    observed_at = detail.get("observed_at")
    if observed_at is not None:
        timestamp = dt.datetime.fromisoformat(observed_at) if isinstance(observed_at, str) else observed_at
        observed = timestamp.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return (f"was {distance_text} from its stop at {observed}, "
                f"last observed {ui.fmt_price(detail.get('price'))}.")
    return f"is {distance_text} from its stop, last {ui.fmt_price(detail.get('price'))}."


def _tp1_copy(plan, transition: str, detail: dict) -> str:
    if transition == "closed":
        return _target_close_copy(plan, "TP1", detail)
    fill = detail.get("exit_price")
    fill = plan.tp1 if fill is None else fill
    return f"reached TP1 at {ui.fmt_price(fill)}."


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


# --------------------------------------------------------------------------
# Delivery (V152-17): claim, send, mention, retry sweep.
# --------------------------------------------------------------------------

#: A pending row is re-sent once it has sat this long since its last attempt.
RETRY_AFTER = dt.timedelta(seconds=60)

#: (plan_id, notify_event) keys already claimed, in any state. Seeded once
#: from plan_notifications; after the first claim a near-stop that fires on
#: every in-band tick costs one set lookup and no database call.
_CLAIMED: set[tuple[str, str]] | None = None
_BAD_CHANNEL_IDS: set[str] = set()

#: Discord accepted these messages, but their sent state is not confirmed in DB.
#: Sweeps retry settlement only while this process remembers the success.
#: After a restart, an unsettled row is indistinguishable from an unsent claim;
#: recovering it can duplicate the message. Repeated crashes before settlement
#: cannot have a durable duplicate bound without Discord-side idempotency.
_UNSETTLED: set[tuple[str, str]] = set()


def _notify_channel(bot):
    """The notify channel, or None when D1 is off or the id is unusable.
    Never wrapped in silence(): the mentions must ping."""
    raw = str(getattr(config, "DISCORD_CHANNEL_NOTIFY_ID", "") or "").strip()
    if not raw:
        return None
    try:
        return bot.get_channel(int(raw))
    except (TypeError, ValueError):
        if raw not in _BAD_CHANNEL_IDS:
            _BAD_CHANNEL_IDS.add(raw)
            log.warning("follow_notify: DISCORD_CHANNEL_NOTIFY_ID=%r is not a channel id; "
                        "follower notifications are off", raw)
        return None


# Sync store calls: always run through asyncio.to_thread.

def _load_plan(plan_id: str):
    from swingbot.core.planning.plan_store import PlanStore
    return PlanStore().get(plan_id)


def _audience(plan_id: str) -> tuple[dict, dict]:
    from swingbot.core.db.repositories.followers import followers_repo
    from swingbot.core.db.repositories.notify_prefs import notify_prefs_repo
    followers = followers_repo().followers(plan_id)
    prefs = notify_prefs_repo().prefs_many(list(followers)) if followers else {}
    return followers, prefs


def _claim(plan_id: str, notify_event: str, doc: dict) -> bool:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().claim(plan_id, notify_event, doc)


def _mark_sent(plan_id: str, notify_event: str) -> None:
    from swingbot.core.db.repositories.notifications import notifications_repo
    notifications_repo().mark_sent(plan_id, notify_event)


def _record_failure(plan_id: str, notify_event: str) -> str:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().record_failure(plan_id, notify_event)


def _pending_rows(cutoff: dt.datetime) -> list[dict]:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().pending_older_than(cutoff)


def _claimed_keys() -> set[tuple[str, str]]:
    from swingbot.core.db.repositories.notifications import notifications_repo
    return notifications_repo().claimed_keys()


async def _claimed_cache() -> set[tuple[str, str]]:
    global _CLAIMED
    if _CLAIMED is None:
        try:
            _CLAIMED = set(await asyncio.to_thread(_claimed_keys))
        except Exception:
            log.warning("follow_notify: could not seed the claim cache; "
                        "claims still dedupe in the database", exc_info=True)
            _CLAIMED = set()
    return _CLAIMED


def _stored_detail(detail: dict) -> dict:
    """The event detail as the claim stores it: manager bookkeeping keys dropped."""
    return {key: value for key, value in (detail or {}).items() if not str(key).startswith("_")}


def _send_kwargs(embed, mentions: list[int], plan_id: str) -> dict:
    """push_kwargs plus the Chart button, and either the mentions or silent."""
    from swingbot.commands.views import chart_only_view
    kwargs = ui.push_kwargs(embed)
    kwargs["view"] = chart_only_view(plan_id)
    if not mentions:
        kwargs.update(silent=True, allowed_mentions=discord.AllowedMentions.none())
        return kwargs
    tags = " ".join(f"<@{user_id}>" for user_id in mentions)
    kwargs["content"] = f"{kwargs.get('content', '')}\n{tags}".strip()
    kwargs["allowed_mentions"] = discord.AllowedMentions(
        users=[discord.Object(id=user_id) for user_id in mentions], roles=False, everyone=False)
    return kwargs


async def _note_failure(plan_id: str, notify_event: str) -> None:
    try:
        state = await asyncio.to_thread(_record_failure, plan_id, notify_event)
    except Exception:
        log.warning("follow_notify: could not count the failed attempt for %s on plan %s",
                    notify_event, plan_id, exc_info=True)
        return
    if state == "failed":
        log.warning("follow_notify: giving up on %s for plan %s after %d attempts",
                    notify_event, plan_id, MAX_ATTEMPTS)


async def _settle_sent(plan_id: str, notify_event: str) -> None:
    """Retry the sent write without repeating a known successful Discord send."""
    try:
        await asyncio.to_thread(_mark_sent, plan_id, notify_event)
    except Exception:
        log.warning("follow_notify: %s for plan %s was sent but not marked sent; "
                    "the sweep will retry settlement", notify_event, plan_id, exc_info=True)
    else:
        _UNSETTLED.discard((plan_id, notify_event))


async def _send_and_settle(channel, plan, notify_event: str, transition: str,
                           detail: dict, audience: tuple[dict, dict]) -> int:
    """Send one claimed message; mark it sent, or count the failed attempt."""
    followers, prefs = audience
    try:
        embed = build_notify_embed(plan, notify_event, transition, detail)
        mentions = eligible_mentions(followers, notify_event, prefs)
        await channel.send(**_send_kwargs(embed, mentions, plan.plan_id))
    except Exception:
        log.warning("follow_notify: %s for plan %s not sent; the retry sweep will try again",
                    notify_event, plan.plan_id, exc_info=True)
        await _note_failure(plan.plan_id, notify_event)
        return 0
    _UNSETTLED.add((plan.plan_id, notify_event))
    log_posted(embed, plan.ticker, channel)
    await _settle_sent(plan.plan_id, notify_event)
    return 1


async def _deliver(channel, claimed: set, event: PlanEvent) -> int:
    notify_event = notify_event_for(event)
    key = (event.plan_id, notify_event)
    if notify_event is None or key in claimed:
        return 0
    plan = await asyncio.to_thread(_load_plan, event.plan_id)
    if plan is None:
        return 0
    audience = await asyncio.to_thread(_audience, event.plan_id)
    if not posts_message(notify_event, audience[0]):
        return 0
    detail = _stored_detail(event.detail)
    if notify_event == "near_stop":
        detail["observed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    doc = {"transition": event.transition, "detail": detail}
    inserted = await asyncio.to_thread(_claim, event.plan_id, notify_event, doc)
    claimed.add(key)
    if not inserted:
        return 0
    return await _send_and_settle(channel, plan, notify_event, event.transition,
                                  event.detail, audience)


async def notify_followers(bot, events: list[PlanEvent]) -> int:
    """Post each mappable plan event to the notify channel once; returns messages sent.

    Independent of the execution feed: loops._post_plan_events calls it
    whatever the feed did. One event's failure never stops the batch."""
    channel = _notify_channel(bot)
    if channel is None or not events:
        return 0
    claimed = await _claimed_cache()
    sent = 0
    for event in events:
        try:
            sent += await _deliver(channel, claimed, event)
        except Exception:
            log.warning("follow_notify: could not handle %s for plan %s",
                        event.transition, event.plan_id, exc_info=True)
    return sent


async def _retry_row(channel, row: dict) -> int:
    key = (row["plan_id"], row["event"])
    if key in _UNSETTLED:
        await _settle_sent(*key)
        return 0
    plan = await asyncio.to_thread(_load_plan, row["plan_id"])
    if plan is None:
        return 0
    audience = await asyncio.to_thread(_audience, row["plan_id"])
    return await _send_and_settle(channel, plan, row["event"], row.get("transition", ""),
                                  row.get("detail") or {}, audience)


async def retry_pending_notifications(bot, now: dt.datetime | None = None) -> int:
    """Recover pending claims older than RETRY_AFTER; returns messages sent.

    Known successful sends retry only settlement; other claims are re-sent.
    Runs once per trade_monitor tick, whether or not the tick had events."""
    channel = _notify_channel(bot)
    if channel is None:
        return 0
    now = now or dt.datetime.now(dt.timezone.utc)
    try:
        rows = await asyncio.to_thread(_pending_rows, now - RETRY_AFTER)
    except Exception:
        log.warning("follow_notify: could not read pending notifications", exc_info=True)
        return 0
    sent = 0
    for row in rows:
        try:
            sent += await _retry_row(channel, row)
        except Exception:
            log.warning("follow_notify: retry of %s for plan %s failed",
                        row.get("event"), row.get("plan_id"), exc_info=True)
    return sent
