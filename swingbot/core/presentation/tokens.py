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
