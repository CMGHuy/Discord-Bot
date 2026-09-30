"""v110: the one registry of notification kinds the bot pushes unprompted.

Every pushed message belongs to exactly one Family (badge, label, stripe
colour) and is one Kind (the specific event). The four helpers -- title,
content_line, stripe, footer -- are the only way a pushed builder styles a
message. Pure: no discord import, so it is testable on its own, and command
replies (which keep tokens.ACCENT_RAMP) never change colour as a side
effect. components.apply_chrome turns stripe() into a discord.Color.

Glyph rules (spec §1): ▲/▼ mean direction only, ✅/❌ mean outcome only,
🟢/🔴 never appear, and no family badge doubles as an outcome or direction
mark. tests/presentation/test_kinds.py enforces all four.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique

from swingbot.core.presentation import tokens

# Stripe colours (spec §3): distinguishable side by side in Discord's dark
# (#313338) and light (#FFFFFF) themes, and no value in two families.
SETUP_RAMP: dict[int, int] = {
    1: 0xA5CDFF,  # Lv1 light blue
    2: 0x74AEFF,
    3: 0x3D8BFF,
    4: 0x1F66E0,
    5: 0x0B44B0,  # Lv5 deep blue
}
SETUP_BLOCKED = 0x7D8CA3  # muted grey-blue: blocked / DO NOT PLACE
ENTRY_TEAL = 0x14B8A6
MANAGE_AMBER = 0xF5A524
WATCH_STOP_ORANGE = 0xFF6A13
WATCH_TP_LIME = 0xA3E635
RESULT_GREENS = (0x86EFAC, 0x22C55E, 0x15803D)  # abs(R) < 1, 1-2, >= 2
RESULT_REDS = (0xFCA5A5, 0xEF4444, 0xB91C1C)
RESULT_GREY = 0x9CA3AF  # scratch / manual / expired / invalidated
SYSTEM_SLATE = 0x5B6B82
HEALTH_RED = 0xE11D48
HEALTH_GREEN = 0x34D399

#: abs(R) at or below this is a scratch -- the same band instructions._closed
#: uses to pick its good/bad/neutral tone.
SCRATCH_BAND = 0.05

FIXED = "fixed"
LEVEL_RAMP = "level_ramp"
R_RAMP = "r_ramp"

OUTCOME_MARKS: dict[str, str] = {
    "win": "✅", "loss": "❌", "scratch": "⚪", "manual": "🔒",
    "expired": "⏹️", "invalidated": "⏹️",
}
_OUTCOME_WORDS: dict[str, str] = {
    "win": "WIN", "loss": "LOSS", "scratch": "SCRATCH", "manual": "MANUAL CLOSE",
    "expired": "EXPIRED", "invalidated": "INVALIDATED",
}
_SIDES: dict[str, str] = {"bullish": "LONG", "bearish": "SHORT"}


@dataclass(frozen=True)
class FamilySpec:
    badge: str
    label: str
    colour: int


@unique
class Family(Enum):
    NEW_SETUP = FamilySpec("🆕", "NEW SETUP", SETUP_RAMP[3])
    ENTRY = FamilySpec("🎯", "ENTRY", ENTRY_TEAL)
    MANAGE = FamilySpec("🛡️", "MANAGE", MANAGE_AMBER)
    WATCH = FamilySpec("👀", "WATCH", WATCH_STOP_ORANGE)
    RESULT = FamilySpec("🏁", "RESULT", RESULT_GREY)
    SYSTEM = FamilySpec("🩺", "SYSTEM", SYSTEM_SLATE)

    @property
    def badge(self) -> str:
        return self.value.badge

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def colour(self) -> int:
        return self.value.colour


@dataclass(frozen=True)
class KindSpec:
    family: Family
    label: str
    rule: str = FIXED
    emoji: str | None = None       # overrides the family badge when set
    colour: int | None = None      # FIXED-rule override of the family colour
    disclaimer: bool = False


def _setup(label: str, rule: str = LEVEL_RAMP, colour: int | None = None) -> KindSpec:
    return KindSpec(Family.NEW_SETUP, label, rule, colour=colour, disclaimer=True)


@unique
class Kind(Enum):
    # NEW SETUP -- the only family that carries the alert disclaimer.
    SETUP_ALERT = _setup("ALERT")              # full scan alert, digest entries
    STRATEGY_SIGNAL = _setup("STRATEGY")       # strategy alert and its simple mirror
    TICKET_PLACE = _setup("PLACE")             # v2 simple ticket
    TICKET_DO_NOT_PLACE = _setup("DO NOT PLACE", FIXED, SETUP_BLOCKED)
    SETUP_SIMPLE = _setup("SIMPLE")            # legacy simple mirror
    DIGEST = _setup("TOP PLANS")               # top-plans digest content line
    # ENTRY
    ENTRY_TRIGGERED = KindSpec(Family.ENTRY, "ENTRY TRIGGERED")
    FILLED = KindSpec(Family.ENTRY, "FILLED")
    # MANAGE
    BE_MOVED = KindSpec(Family.MANAGE, "BREAK-EVEN")
    TP1_HIT = KindSpec(Family.MANAGE, "TP1", emoji="💰")
    MOVE_STOP = KindSpec(Family.MANAGE, "MOVE STOP", emoji="✂️")
    CANCEL = KindSpec(Family.MANAGE, "CANCEL", emoji="🚫")
    RISK_CAP = KindSpec(Family.MANAGE, "RISK CAP", emoji="🚫")
    PLAN_UPDATE = KindSpec(Family.MANAGE, "PLAN UPDATE")   # history-only fallback
    # WATCH
    NEAR_STOP = KindSpec(Family.WATCH, "NEARING STOP", colour=WATCH_STOP_ORANGE)
    NEAR_TP = KindSpec(Family.WATCH, "NEARING TP", colour=WATCH_TP_LIME)
    # RESULT -- the outcome mark rides in the detail, via outcome_detail().
    CLOSED_TRADE = KindSpec(Family.RESULT, "CLOSED", R_RAMP)
    STOPPED = KindSpec(Family.RESULT, "STOPPED", R_RAMP)
    WIN = KindSpec(Family.RESULT, "WIN", R_RAMP)
    SCRATCHED = KindSpec(Family.RESULT, "SCRATCHED")
    EXITED = KindSpec(Family.RESULT, "EXITED", R_RAMP)
    CLOSE_AT_MARKET = KindSpec(Family.RESULT, "CLOSE AT MARKET", R_RAMP)
    EXPIRED = KindSpec(Family.RESULT, "EXPIRED")
    INVALIDATED = KindSpec(Family.RESULT, "INVALIDATED")
    # SYSTEM
    SCAN_SUMMARY = KindSpec(Family.SYSTEM, "SCAN")
    HEALTHCHECK = KindSpec(Family.SYSTEM, "HEALTHCHECK")
    HEALTH_ALERT = KindSpec(Family.SYSTEM, "HEALTH ALERT", emoji="🚨", colour=HEALTH_RED)
    HEALTH_RECOVERED = KindSpec(Family.SYSTEM, "RECOVERED", emoji="✅", colour=HEALTH_GREEN)
    BOT_ONLINE = KindSpec(Family.SYSTEM, "ONLINE", emoji="🤖")
    CONFIG_CHANGE = KindSpec(Family.SYSTEM, "CONFIG", emoji="⚙️")
    RETROSPECTIVE = KindSpec(Family.SYSTEM, "RETROSPECTIVE", emoji="📜")
    DEEP_SCAN = KindSpec(Family.SYSTEM, "WEEKEND DEEP SCAN", emoji="🔭")

    @property
    def family(self) -> Family:
        return self.value.family

    @property
    def label(self) -> str:
        return self.value.label

    @property
    def rule(self) -> str:
        return self.value.rule

    @property
    def emoji(self) -> str | None:
        return self.value.emoji

    @property
    def disclaimer(self) -> bool:
        return self.value.disclaimer


def badge(kind: Kind) -> str:
    """The event emoji when the kind has one, else its family badge."""
    return kind.emoji or kind.family.badge


def side_word(direction: str | None) -> str:
    return _SIDES.get(direction or "", tokens.ABSENT)


def _head(ticker: str, direction: str | None) -> str:
    side = _SIDES.get(direction or "")
    if side is None:
        return ticker
    return f"{tokens.direction_glyph(direction)} {side} {ticker}".rstrip()


def _join(*parts: str) -> str:
    return " · ".join(part for part in parts if part)


def title(kind: Kind, ticker: str, direction: str | None = None, detail: str = "") -> str:
    """``🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐`` -- badge, head, kind label, detail."""
    return f"{badge(kind)} {_join(_head(ticker, direction), kind.label, detail)}"


def content_line(kind: Kind, ticker: str, direction: str | None = None, detail: str = "") -> str:
    """The phone push preview: ``🏁 RESULT · ▲ LONG AAPL · CLOSED · ✅ WIN +1.8R``."""
    return f"{badge(kind)} {_join(kind.family.label, _head(ticker, direction), kind.label, detail)}"


def _fixed_stripe(kind: Kind, level: int | None, r: float | None, blocked: bool) -> int:
    return kind.value.colour if kind.value.colour is not None else kind.family.colour


def _level_stripe(kind: Kind, level: int | None, r: float | None, blocked: bool) -> int:
    if blocked:
        return SETUP_BLOCKED
    return SETUP_RAMP.get(level or 0, SETUP_RAMP[1])


def _r_stripe(kind: Kind, level: int | None, r: float | None, blocked: bool) -> int:
    if r is None or abs(r) <= SCRATCH_BAND:
        return RESULT_GREY
    step = 0 if abs(r) < 1.0 else 1 if abs(r) < 2.0 else 2
    return (RESULT_GREENS if r > 0 else RESULT_REDS)[step]


_STRIPE_RULES = {FIXED: _fixed_stripe, LEVEL_RAMP: _level_stripe, R_RAMP: _r_stripe}


def stripe(kind: Kind, level: int | None = None, r: float | None = None,
           blocked: bool = False) -> int:
    """The embed's stripe colour, by the kind's rule (fixed, level ramp, R ramp)."""
    return _STRIPE_RULES[kind.rule](kind, level, r, blocked)


def footer(kind: Kind, plan_id: str | None = None) -> str:
    """NEW SETUP keeps the disclaimer; every other family names itself."""
    base = tokens.DISCLAIMER if kind.disclaimer else kind.family.label
    return f"{base} · plan {plan_id[:8]}" if plan_id else base


def outcome_mark(outcome: str | None) -> str:
    return OUTCOME_MARKS.get((outcome or "").lower(), OUTCOME_MARKS["scratch"])


def _signed_r(r: float) -> str:
    text = tokens.fmt_r(r)
    return text if r < 0 or text == "0.0R" else f"+{text}"


def outcome_detail(outcome: str | None, r: float | None = None) -> str:
    """``✅ WIN +1.8R`` -- the RESULT title and push-line detail."""
    key = (outcome or "").lower()
    text = f"{outcome_mark(key)} {_OUTCOME_WORDS.get(key, key.upper())}"
    return text if r is None else f"{text} {_signed_r(r)}"


def outcome_for_r(r: float | None) -> str:
    """win / loss / scratch from a realised R, using SCRATCH_BAND."""
    if r is None or abs(r) <= SCRATCH_BAND:
        return "scratch"
    return "win" if r > 0 else "loss"


def result_r(outcome: str, r: float | None) -> float | None:
    """The R the stripe reads: the outcome picks the ramp's side, abs(R) the step.
    Manual, scratch and unknown-R closes return None, which is grey."""
    if r is None or outcome not in ("win", "loss"):
        return None
    return abs(r) if outcome == "win" else -abs(r)


def plan_badge_text(badge_name: str) -> str:
    """A plan's badge in pushed text. ✅ is outcome-only, so VALIDATED carries no mark."""
    return badge_name if badge_name == "VALIDATED" else f"⚠️ {badge_name}"
