"""v239: bear_regime notices for the v197 notify queue.

Payload half: the unfilled bullish plans issued under the old state, the
payload and the queue event -- one per session (transition_id
market_regime:<D>). Renderer half: one plain status embed in the v210 style:
headline in the shared vocabulary, the number line, the open-long count, the
unfilled bullish plans one per line, and the shadow footer. No Kind, no
disclaimer, no glyphs. WHEN to notify is regime_scan's call (V239-8). Pure
apart from config, read only for the target channel.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime

import discord

from swingbot import config
from swingbot.core import presentation as ui
from swingbot.core.infra.lifecycle_events import make_event
from swingbot.core.market import bear_regime as br
from swingbot.core.market import regime_episodes as ep
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.presentation import kinds, regime_text

KIND = "bear_regime"
FOOTER = "Shadow: no long blocked, no short issued, no plan cancelled."
GAP_NOTE_SESSIONS = 5
#: Discord caps a description at 4096 characters; the rest of the body fits in 596.
UNFILLED_BUDGET = 3500
FIRST_READING = "first reading"
NO_NUMBERS = "Numbers unavailable."
UNAVAILABLE = "unavailable"
_UNFILLED = "Unfilled bullish plans from the old state"
_LABELS = regime_text.LABELS
COLOURS = {_LABELS[ep.BEAR_KEY]: kinds.HEALTH_RED,
           _LABELS[ep.CORRECTION_STRESS_KEY]: kinds.WATCH_STOP_ORANGE,
           _LABELS[ep.CORRECTION_KEY]: kinds.MANAGE_AMBER,
           _LABELS[ep.NORMAL_KEY]: kinds.HEALTH_GREEN,
           _LABELS[ep.UNKNOWN_KEY]: kinds.RESULT_GREY,
           _LABELS[regime_text.PULLBACK]: kinds.SETUP_RAMP[3]}


def _unfilled_under_old_state(plan, new_state: str) -> bool:
    if getattr(plan, "status", None) != PlanStatus.PENDING:
        return False
    if getattr(plan, "direction", None) != "bullish" or not getattr(plan, "ticker", None):
        return False
    stamped = (getattr(plan, "entry_context", None) or {}).get("bear_regime")
    return stamped != new_state and getattr(plan, "trigger_price", None) is not None


def unfilled_bullish_rows(plans: Iterable, *, new_state: str) -> list[dict]:
    """PENDING bullish plans not stamped with ``new_state`` (no stamp = the old state)."""
    rows = [{"ticker": str(plan.ticker), "entry": float(plan.trigger_price)}
            for plan in plans if _unfilled_under_old_state(plan, new_state)]
    return sorted(rows, key=lambda row: row["ticker"])


def _labels(transition: ep.Transition | None) -> tuple[str, str | None, str]:
    if transition is None:
        return "pullback", None, _LABELS[regime_text.PULLBACK]
    old = _LABELS[transition.old] if transition.old is not None else None
    return "transition", old, _LABELS[transition.new]


def notice_payload(day: br.RegimeDay, transition: ep.Transition | None, *,
                   open_longs: int | None, unfilled: list[dict] | None,
                   gap_sessions: int | None, now: datetime) -> dict:
    if transition is None and not day.pullback_trigger:
        raise ValueError("regime_notice_without_cause")
    kind, old, new = _labels(transition)
    return {"occurred_at": now.isoformat(), "session_date": day.session_date.isoformat(),
            "kind": kind, "old_label": old, "new_label": new,
            "numbers": regime_text.number_line(spy_close=day.spy_close, sma50=day.sma50,
                                               sma200=day.sma200, vix_close=day.vix_close),
            "open_longs": open_longs, "unfilled": None if unfilled is None else list(unfilled),
            "gap_sessions": gap_sessions, "pullback": bool(day.pullback_trigger)}


def notice_event(payload: dict, *, session_date: date) -> dict:
    """The queue event; one per session. The channel is computed here, never via the bot."""
    channel = config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID or None
    return make_event(transition_id=f"market_regime:{session_date}", kind=KIND,
                      target_channel_id=channel, occurred_at=payload["occurred_at"],
                      payload=payload)


def headline(payload: dict) -> str:
    if payload["kind"] == "pullback":
        return f"Regime: {payload['new_label']}"
    return f"Regime: {payload['old_label'] or FIRST_READING} → {payload['new_label']}"


def _unfilled_block(rows: list[dict] | None) -> list[str]:
    if rows is None:
        return [f"{_UNFILLED}: {UNAVAILABLE}"]
    if not rows:
        return [f"{_UNFILLED}: none."]
    lines, used = [f"{_UNFILLED} ({len(rows)}):"], 0
    for row in rows:
        line = f"{row['ticker']} {row['entry']:.2f}"
        if used + len(line) + 1 > UNFILLED_BUDGET:
            break
        lines.append(line)
        used += len(line) + 1
    shown = len(lines) - 1
    if shown < len(rows):
        lines.append(f"… and {len(rows) - shown} more")
    return lines


def _body(payload: dict) -> str:
    gap = payload.get("gap_sessions")
    lines = [f"After a gap of {gap} sessions."] if gap is not None and gap > GAP_NOTE_SESSIONS else []
    lines.append(payload.get("numbers") or NO_NUMBERS)
    if payload["kind"] == "transition" and payload.get("pullback"):
        lines.append(f"{_LABELS[regime_text.PULLBACK]}: {regime_text.WORDS[regime_text.PULLBACK]}.")
    longs = payload.get("open_longs")
    lines += [f"For session {payload['session_date']}.", "",
              f"Open longs: {UNAVAILABLE if longs is None else longs}",
              *_unfilled_block(payload.get("unfilled")), "", FOOTER]
    return "\n".join(lines)


def build_regime_embed(event: dict) -> discord.Embed:
    """The status embed for one validated bear_regime event."""
    payload = event["payload"]
    colour = COLOURS.get(payload["new_label"], kinds.SYSTEM_SLATE)
    embed = ui.status_embed(headline(payload), _body(payload), colour)
    embed.set_footer(text=f"Event {event['event_id']}")
    embed.timestamp = datetime.fromisoformat(payload["occurred_at"])
    return embed
