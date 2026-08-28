"""Whole reusable Discord embed parts rather than presentation tokens."""

from typing import NamedTuple

from swingbot.core.presentation import ansi, tokens


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
