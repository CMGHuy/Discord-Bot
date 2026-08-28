"""Pure presentation values shared by Discord and the admin SPA."""

import discord


#: Confidence level -> accent colour, worse to better.
ACCENT_RAMP: dict[int, int] = {
    1: 0xFF5470,
    2: 0xFFB43D,
    3: 0x9BA3BD,
    4: 0x9ACD32,
    5: 0x17C98E,
}

#: A setup that failed a configured gate is inert, not a loss.
ACCENT_BLOCKED: int = 0x9BA3BD

_OUTCOME_ACCENTS: dict[str, int] = {
    "win": ACCENT_RAMP[5],
    "loss": ACCENT_RAMP[1],
    "scratch": ACCENT_RAMP[3],
}


def accent_for_level(level: int | None) -> discord.Color:
    """Return an ordinal accent, defaulting unknown levels to the bottom."""
    return discord.Color(ACCENT_RAMP.get(level or 0, ACCENT_RAMP[1]))


def accent_for_outcome(outcome: str) -> discord.Color:
    """Return the shared win/loss/scratch accent for a closed trade."""
    return discord.Color(_OUTCOME_ACCENTS.get((outcome or "").lower(),
                                              ACCENT_RAMP[3]))


ABSENT = "—"
_UP = "▲"
_DOWN = "▼"
_MINUS = "−"


def direction_glyph(direction: str) -> str:
    """Return the direction shape; unknown directions are explicitly absent."""
    if direction == "bullish":
        return _UP
    if direction == "bearish":
        return _DOWN
    return ABSENT


def confidence_label(level: int | None, score: float | None) -> str:
    """Render the shared confidence form, such as ``Lv5 · 91``."""
    if level is None:
        return ABSENT
    if score is None:
        return f"Lv{level}"
    return f"Lv{level} · {round(score)}"


def follow_meter(score: float) -> str:
    """Render a bounded five-block follow-score bar and its exact score."""
    score = max(0.0, min(100.0, float(score)))
    filled = max(0, min(5, round(score / 20)))
    return f"{'▰' * filled}{'▱' * (5 - filled)} {round(score)}"


def fmt_price(x: float | None, sym: str = "") -> str:
    """Render equities at 2dp and sub-one prices at 4dp."""
    if x is None:
        return ABSENT
    return f"{sym}{x:.2f}" if abs(x) >= 1.0 else f"{sym}{x:.4f}"


def fmt_pct(x: float | None) -> str:
    """Render a signed percentage with a typographically aligned minus."""
    if x is None:
        return ABSENT
    if x > 0:
        return f"+{x:.1f}%"
    if x < 0:
        return f"{_MINUS}{abs(x):.1f}%"
    return "0.0%"


def fmt_r(x: float | None) -> str:
    """Render a signed R-multiple with its unit included."""
    if x is None:
        return ABSENT
    if x < 0:
        return f"{_MINUS}{abs(x):.1f}R"
    return f"{x:.1f}R"
