"""Pure presentation values shared by Discord and the admin SPA."""

import discord


#: Confidence level -> accent colour, worse to better.
ACCENT_RAMP: dict[int, int] = {
    1: 0xFF5470,
    2: 0xFFB43D,
    3: 0x9EA2AD,
    4: 0x9ACD32,
    5: 0x17C98E,
}

#: A setup that failed a configured gate is inert, not a loss.
# Level 3 and blocked are the admin's --text-secondary (v80 D1), so a neutral
# embed and a neutral admin label are the same grey.
ACCENT_BLOCKED: int = 0x9EA2AD

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


def accent_blocked() -> discord.Color:
    """Return the inert accent for a setup that failed a configured gate."""
    return discord.Color(ACCENT_BLOCKED)


ABSENT = "—"
_UP = "▲"
_DOWN = "▼"
_MINUS = "−"

DISCLAIMER = ("Technical signal only, based on today's still-developing daily "
              "candle -- not financial advice.")

SECTION_ORDER = (
    "headline", "plan", "blocked", "quality", "confluence",
    "changes", "branches", "track_record", "warnings",
)


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


def fmt_money(amount: float, currency: str) -> str:
    """'+$500.00' / '-$500.00' -- an explicitly signed currency figure.

    One helper because this exact format string had been hand-copied into
    three surfaces (the two-leg sizing block, the TP1-hit alert and the
    !liveplans board) and got the sign wrong twice on the way: once as a
    hardcoded '+' with no abs() ('+$-500.00'), and once as a bare '' for the
    negative branch, which renders a banked *loss* as a positive-looking
    '$500.00'. The sign is the whole point of the figure, so it lives in
    exactly one place. v170 moved it here from scanning/plan_table.py
    (``signed_money`` there is this same object) so presentation/instructions
    can use it without importing scanning. The minus is ASCII, unlike
    fmt_r's U+2212 (v170 A9: changing either would alter every surface)."""
    return f"{'+' if amount >= 0 else '-'}{currency}{abs(amount):,.2f}"


#: v170: the execution feed's one table of symbols. Every glyph the feed
#: prints comes from here (presentation/instructions.py holds no glyph
#: literal), each glyph has exactly one meaning, and the !help legend is
#: generated from it. The warning sign stays reserved for block warnings.
FEED_SYMBOLS: dict[str, str] = {
    "entry": "▶",          # ▶
    "stop": "\U0001f6d1",       # 🛑
    "tp1": "\U0001f4b0",        # 💰
    "runner": "\U0001f3c3",     # 🏃
    "tp2": "\U0001f3af",        # 🎯
    "trail": "〜",          # 〜
    "breakeven": "⚖",      # ⚖ (no variation selector)
    "expiry": "⏳",         # ⏳
    "invalid": "⛔",        # ⛔
    "if_fills": "\U0001f512",   # 🔒
    "pnl": "\U0001f9fe",        # 🧾
    "win": "✅",            # ✅
    "loss": "❌",           # ❌
    "flat": "➖",           # ➖
    "at_or_above": "≥",    # ≥
    "at_or_below": "≤",    # ≤
}

#: The legend's word for each FEED_SYMBOLS key, same keys, same order.
FEED_SYMBOL_WORDS: dict[str, str] = {
    "entry": "entry",
    "stop": "stop",
    "tp1": "first target (TP1)",
    "runner": "runner",
    "tp2": "second target (TP2)",
    "trail": "trailing stop",
    "breakeven": "stop to break-even",
    "expiry": "time limit",
    "invalid": "invalidation",
    "if_fills": "if the stop fills",
    "pnl": "profit and loss",
    "win": "win",
    "loss": "loss",
    "flat": "flat",
    "at_or_above": "at or above",
    "at_or_below": "at or below",
}

#: Every feed P&L figure is paper and gross: the tracker knows no fees,
#: slippage or tax (tracking/performance.py module docstring).
COST_BASIS = "(paper, gross)"
COST_BASIS_SENTENCE = "Feed dollars: paper account, before fees, slippage and tax."


def feed_legend() -> str:
    """The !help legend line, built from FEED_SYMBOLS so it cannot drift."""
    pairs = " · ".join(f"{glyph} {FEED_SYMBOL_WORDS[key]}"
                       for key, glyph in FEED_SYMBOLS.items())
    return f"Feed symbols: {pairs}. {COST_BASIS_SENTENCE}"
