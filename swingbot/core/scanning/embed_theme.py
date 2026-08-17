"""
Single source of truth for the confidence-level/badge-driven visual
language every embed builder in swingbot/core/scanning/embeds.py uses from
here on -- colors, chip glyphs, the follow-score progress bar, price
formatting, and the fixed section order fields are grouped into.
Centralizing this here means "what does a WEAK plan look like" or "what
order do fields render in" is answered by reading ONE small module instead
of grepping every embed builder for its own ad-hoc color/order logic.

v32 Task 11: A/B/C tier (quality.py's own 0-100 quality_score bands,
independent of confidence.py's method-count-plus-quality level) is retired
in favour of confidence LEVEL as the single vocabulary. LEVEL_COLORS/
level_chip() replace TIER_COLORS/tier_chip(), same 3-color visual language
(green/yellow/grey) mapped onto the 5-level scale (UNIFIED_CONFIDENCE
stayed default-off after v32's VALIDATION FAIL -- see
docs/superpowers/plans/implemented/v32-train-preregistration.md -- so this is still the
1-5 legacy scale, not 1-6).
"""
import discord

# Level accent colors -- used only for a VALIDATED plan. A WEAK plan is
# always amber (see plan_color) regardless of which level it landed at,
# since "did this pass the 80% OOS bar at all" dominates "how confident is
# it, conditional on having cleared the bar" for visual triage.
LEVEL_COLORS = {
    5: 0x2ECC71,  # green (Very High)
    4: 0x2ECC71,  # green (High)
    3: 0xF1C40F,  # yellow (Medium)
    2: 0x95A5A6,  # grey (Low)
    1: 0x95A5A6,  # grey (Very Low)
}
WEAK_COLOR = 0xE67E22  # amber

_LEVEL_CHIPS = {5: "5️⃣", 4: "4️⃣", 3: "3️⃣", 2: "2️⃣", 1: "1️⃣"}
_BADGE_CHIPS = {"VALIDATED": "✅ VALIDATED", "WEAK": "⚠️ WEAK"}

DISCLAIMER = "Technical signal only, based on today's still-developing daily candle -- not financial advice."

# Fixed rendering order for build_embed's fields -- every field the
# builder wants to show is bucketed into one of these named sections
# (see embeds.py's `sections: dict[str, list]` accumulator added in
# Task B2) and flushed in this exact order regardless of the order the
# code below happened to compute them in.
SECTION_ORDER = (
    "headline", "plan", "quality", "confluence",
    "changes", "branches", "track_record", "warnings",
)


def plan_color(badge: str, level: int) -> discord.Color:
    """VALIDATED plans get their level's accent color; WEAK plans are
    always amber, independent of level -- badge (did it clear the bar)
    matters more for at-a-glance triage than level (how confident is it,
    conditional on having cleared the bar)."""
    if badge == "WEAK":
        return discord.Color(WEAK_COLOR)
    return discord.Color(LEVEL_COLORS.get(level, LEVEL_COLORS[1]))


def level_chip(level: int) -> str:
    return _LEVEL_CHIPS.get(level, "1️⃣")


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


def apply_footer(embed, *, plan_id: str | None = None) -> None:
    """Stamps embed.timestamp = now (UTC) and a single shared footer
    format across every embed builder in embeds.py: the disclaimer,
    plus ' · plan {first 8 chars of plan_id}' when a plan_id is given.
    Mutates embed in place; returns None so call sites read as a plain
    statement (`apply_footer(embed, plan_id=...)`) rather than needing
    to reassign anything."""
    embed.timestamp = discord.utils.utcnow()
    text = DISCLAIMER
    if plan_id:
        text = f"{DISCLAIMER} · plan {plan_id[:8]}"
    embed.set_footer(text=text)


def fmt_price(x: float, sym: str) -> str:
    """2 decimal places for anything at or above 1.0 (typical equity
    price granularity); 4 decimal places below 1.0 (penny stocks/FX-like
    tickers where 2dp would lose all precision)."""
    if abs(x) >= 1.0:
        return f"{sym}{x:.2f}"
    return f"{sym}{x:.4f}"
