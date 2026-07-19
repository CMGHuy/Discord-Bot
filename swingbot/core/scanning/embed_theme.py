"""
Single source of truth for the tier/badge-driven visual language every
embed builder in swingbot/core/scanning/embeds.py uses from here on --
colors, chip glyphs, the follow-score progress bar, price formatting,
and the fixed section order fields are grouped into. Centralizing this
here means "what does a WEAK plan look like" or "what order do fields
render in" is answered by reading ONE small module instead of grepping
every embed builder for its own ad-hoc color/order logic.
"""
import discord

# Tier accent colors -- used only for a VALIDATED plan. A WEAK plan is
# always amber (see plan_color) regardless of which tier it landed in,
# since "did this pass the 80% OOS bar at all" dominates "which tier
# within the passing set" for visual triage.
TIER_COLORS = {
    "A": 0x2ECC71,  # green
    "B": 0xF1C40F,  # yellow
    "C": 0x95A5A6,  # grey
}
WEAK_COLOR = 0xE67E22  # amber

_TIER_CHIPS = {"A": "🅰", "B": "🅱", "C": "🅲"}
_BADGE_CHIPS = {"VALIDATED": "✅ VALIDATED", "WEAK": "⚠️ WEAK"}

# Fixed rendering order for build_embed's fields -- every field the
# builder wants to show is bucketed into one of these named sections
# (see embeds.py's `sections: dict[str, list]` accumulator added in
# Task B2) and flushed in this exact order regardless of the order the
# code below happened to compute them in.
SECTION_ORDER = (
    "headline", "plan", "quality", "confluence",
    "changes", "branches", "track_record", "warnings",
)


def plan_color(badge: str, tier: str) -> discord.Color:
    """VALIDATED plans get their tier's accent color; WEAK plans are
    always amber, independent of tier -- badge (did it clear the bar)
    matters more for at-a-glance triage than tier (how good is it,
    conditional on having cleared the bar)."""
    if badge == "WEAK":
        return discord.Color(WEAK_COLOR)
    return discord.Color(TIER_COLORS.get(tier, TIER_COLORS["C"]))


def tier_chip(tier: str) -> str:
    return _TIER_CHIPS.get(tier, "🅲")


def badge_chip(badge: str) -> str:
    return _BADGE_CHIPS.get(badge, badge)


def follow_chip(score: float) -> str:
    """5-block progress bar plus the rounded integer score, e.g.
    '▰▰▰▰▱ 82'. Blocks filled and the printed number are each their own
    independent round() -- the bar is a coarse 0-5 visual, the number
    next to it is the precise one, and they're allowed to disagree at
    a rounding boundary (see test_follow_chip's docstring note)."""
    score = max(0.0, min(100.0, score))
    filled = round(score / 20)
    filled = max(0, min(5, filled))
    bar = "▰" * filled + "▱" * (5 - filled)
    return f"{bar} {round(score)}"


def fmt_price(x: float, sym: str) -> str:
    """2 decimal places for anything at or above 1.0 (typical equity
    price granularity); 4 decimal places below 1.0 (penny stocks/FX-like
    tickers where 2dp would lose all precision)."""
    if abs(x) >= 1.0:
        return f"{sym}{x:.2f}"
    return f"{sym}{x:.4f}"
