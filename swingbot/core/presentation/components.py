"""Whole reusable Discord embed parts rather than presentation tokens."""

import logging
from typing import NamedTuple
from urllib.parse import urlsplit

import discord

from swingbot.core.presentation import ansi, kinds, tokens
from swingbot.core.presentation.kinds import Kind

_LOG = logging.getLogger(__name__)
_WARNED_BASES: set[str] = set()


class EmbedField(NamedTuple):
    """One field shaped to unpack directly into ``embed.add_field``."""

    name: str
    value: str
    inline: bool


def plan_headline(*, direction: str, entry: float | None, target: float | None,
                  stop: float | None, target_pct: float | None,
                  stop_pct: float | None, r: float | None) -> str:
    """Return the fenced ANSI alert headline, enforcing phone-safe lines."""
    return ansi.block(ansi.plan_lines(
        direction=direction, entry=entry, target=target, stop=stop,
        target_pct=target_pct, stop_pct=stop_pct, r=r,
    ))


def levels_block(*, direction: str, entry: float | None, stop: float | None,
                 tp1: float | None, tp2: float | None = None) -> str:
    """Fenced ANSI levels block for NEW SETUP and ENTRY embeds (v110 §3)."""
    return ansi.block(ansi.levels_lines(direction=direction, entry=entry, stop=stop,
                                        tp1=tp1, tp2=tp2))


def result_headline(*, direction: str, entry: float | None, exit_price: float | None,
                    stop: float | None, pct: float | None, r: float | None) -> str:
    """Fenced ANSI result block for RESULT embeds: the realised R green or red."""
    return ansi.block(ansi.result_lines(direction=direction, entry=entry,
                                        exit_price=exit_price, stop=stop, pct=pct, r=r))


def confidence_field(level: int | None, score: float | None) -> EmbedField:
    """Return the inline confidence field that pairs with follow score."""
    return EmbedField("Confidence", tokens.confidence_label(level, score), True)


def follow_field(score: float, breakdown: str | None = None) -> EmbedField:
    """Return the inline follow meter with an optional explanatory line."""
    value = tokens.follow_meter(score)
    if breakdown:
        value = f"{value}\n{breakdown}"
    return EmbedField("Follow", value, True)


def blocked_by_field(unmet: list[tuple[str, str]]) -> EmbedField | None:
    """Return a full-width actual-versus-required failed-gates field."""
    if not unmet:
        return None
    body = "\n".join(f"{label}: {detail}" for label, detail in unmet)
    return EmbedField("⚠ Blocked by", body, False)


def plan_link(plan_id: str | None, base: str | None) -> str | None:
    """Build a plan title link from an explicitly supplied HTTP(S) base."""
    if not base:
        return None
    try:
        parts = urlsplit(base)
        valid = (not any(char.isspace() for char in base)
                 and parts.scheme in {"http", "https"} and bool(parts.netloc))
    except ValueError:
        valid = False
    if not valid:
        if base not in _WARNED_BASES:
            _WARNED_BASES.add(base)
            _LOG.warning("Invalid plan link base: %r", base)
        return None
    return f"{base.rstrip('/')}/plans/{plan_id}" if plan_id else None


def apply_chrome(embed: discord.Embed, *, accent: discord.Color | None = None,
                 plan_id: str | None = None, kind: Kind | None = None,
                 level: int | None = None, r: float | None = None,
                 blocked: bool = False, link_base: str | None = None) -> None:
    """Apply the stripe, footer and timestamp in place.

    Pushed builders pass ``kind`` (v110): the stripe and footer come from the
    registry. Command replies keep passing ``accent`` and the disclaimer
    footer, so their look is unchanged."""
    if kind is not None:
        embed.color = discord.Color(kinds.stripe(kind, level=level, r=r, blocked=blocked))
        text = kinds.footer(kind, plan_id)
    elif accent is None:
        raise ValueError("apply_chrome needs a kind (pushed message) or an accent (command reply)")
    else:
        embed.color = accent
        text = f"{tokens.DISCLAIMER} · plan {plan_id[:8]}" if plan_id else tokens.DISCLAIMER
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text=text)
    link = plan_link(plan_id, link_base)
    if link is not None:
        embed.url = link


class PushEmbed(discord.Embed):
    """A discord.Embed that also carries its push-preview line (v110 §4).

    A phone push shows a message's ``content``, never the embed title, so every
    pushed builder returns one of these and every sender passes
    ``push_kwargs(embed)`` to ``send()``. Carrying the line on the embed keeps
    the alert tuples' shape unchanged. ``kind`` is kept for v111's
    "alert posted" log line and is never sent."""

    __slots__ = ("push_text", "kind")


def push_embed(kind: Kind, ticker: str = "", direction: str | None = None,
               detail: str = "", *, description: str | None = None) -> PushEmbed:
    """A PushEmbed whose title and push line both come from the registry."""
    embed = PushEmbed(title=kinds.title(kind, ticker, direction, detail), description=description)
    embed.push_text = kinds.content_line(kind, ticker, direction, detail)
    embed.kind = kind
    return embed


def push_kwargs(embed) -> dict:
    """send() kwargs for one pushed embed: the embed, plus its content line if it has one."""
    text = getattr(embed, "push_text", None)
    return {"embed": embed, "content": text} if text else {"embed": embed}
