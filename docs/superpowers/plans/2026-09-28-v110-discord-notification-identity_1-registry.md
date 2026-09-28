# v110 — Part 1: registry and presentation parts

Header, goal, global constraints, resolved spec gaps, parallelisation and conventions live in [`_0-index`](2026-09-28-v110-discord-notification-identity_0-index.md). Every task below implicitly includes its Global Constraints.

# Phase A — Registry and presentation parts

### Task V110-1: `presentation/kinds.py` — families, kinds, ramps and the four helpers

**Files:**
- Create: `swingbot/core/presentation/kinds.py`
- Test: `tests/presentation/test_kinds.py` (new)

**Interfaces:**
- Consumes: `tokens.DISCLAIMER`, `tokens.ABSENT`, `tokens.direction_glyph`, `tokens.fmt_r` (existing, `swingbot/core/presentation/tokens.py`).
- Produces (every later task relies on these exact names):
  - Enums `Family`, with properties `.badge`, `.label` and `.colour`, and `Kind`, with properties `.family`, `.label`, `.rule`, `.emoji` and `.disclaimer`.
  - Kind members: `SETUP_ALERT STRATEGY_SIGNAL TICKET_PLACE TICKET_DO_NOT_PLACE SETUP_SIMPLE DIGEST ENTRY_TRIGGERED FILLED BE_MOVED TP1_HIT MOVE_STOP CANCEL RISK_CAP PLAN_UPDATE NEAR_STOP NEAR_TP CLOSED_TRADE STOPPED WIN SCRATCHED EXITED CLOSE_AT_MARKET EXPIRED INVALIDATED SCAN_SUMMARY HEALTHCHECK HEALTH_ALERT HEALTH_RECOVERED BOT_ONLINE CONFIG_CHANGE RETROSPECTIVE DEEP_SCAN`.
  - Constants: `SETUP_RAMP: dict[int, int]`, `SETUP_BLOCKED`, `ENTRY_TEAL`, `MANAGE_AMBER`, `WATCH_STOP_ORANGE`, `WATCH_TP_LIME`, `RESULT_GREENS: tuple`, `RESULT_REDS: tuple`, `RESULT_GREY`, `SYSTEM_SLATE`, `HEALTH_RED`, `HEALTH_GREEN`, `SCRATCH_BAND = 0.05` and `OUTCOME_MARKS: dict[str, str]`.
  - Style helpers:
    - `badge(kind) -> str`
    - `title(kind, ticker, direction=None, detail="") -> str`
    - `content_line(kind, ticker, direction=None, detail="") -> str`
    - `stripe(kind, level=None, r=None, blocked=False) -> int`
    - `footer(kind, plan_id=None) -> str`
  - Outcome and plan helpers:
    - `outcome_mark(outcome) -> str`
    - `outcome_detail(outcome, r=None) -> str`
    - `outcome_for_r(r) -> str`
    - `result_r(outcome, r) -> float | None`
    - `side_word(direction) -> str`
    - `plan_badge_text(badge) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/presentation/test_kinds.py`:

```python
"""v110: the notification registry -- table-driven over every Kind."""
import pytest

from swingbot.core.presentation import kinds, tokens
from swingbot.core.presentation.kinds import Family, Kind

ALL_KINDS = list(Kind)
DIRECTIONS = (None, "bullish", "bearish")


def _family_colours(family):
    colours = set()
    for kind in (k for k in Kind if k.family is family):
        for level in (None, 1, 2, 3, 4, 5):
            for r in (None, -3.0, -1.5, -0.5, 0.0, 0.5, 1.5, 3.0):
                for blocked in (False, True):
                    colours.add(kinds.stripe(kind, level=level, r=r, blocked=blocked))
    return colours


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
def test_every_kind_has_a_family(kind):
    assert isinstance(kind.family, Family)


def test_every_family_is_used():
    assert {k.family for k in Kind} == set(Family)


def test_badge_and_label_pairs_are_unique():
    pairs = [(kinds.badge(k), k.label) for k in Kind]
    assert len(pairs) == len(set(pairs))


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
def test_only_new_setup_kinds_carry_the_disclaimer(kind):
    assert kind.disclaimer is (kind.family is Family.NEW_SETUP)


@pytest.mark.parametrize("level,expected", [
    (1, 0xA5CDFF), (2, 0x74AEFF), (3, 0x3D8BFF), (4, 0x1F66E0), (5, 0x0B44B0),
    (None, 0xA5CDFF), (0, 0xA5CDFF), (9, 0xA5CDFF),
])
def test_setup_stripe_follows_the_confidence_ramp(level, expected):
    assert kinds.stripe(Kind.SETUP_ALERT, level=level) == expected


def test_blocked_setup_and_do_not_place_are_the_muted_grey_blue():
    assert kinds.stripe(Kind.SETUP_ALERT, level=5, blocked=True) == kinds.SETUP_BLOCKED
    assert kinds.stripe(Kind.TICKET_DO_NOT_PLACE, level=5) == kinds.SETUP_BLOCKED


@pytest.mark.parametrize("r,expected", [
    (0.5, kinds.RESULT_GREENS[0]), (1.0, kinds.RESULT_GREENS[1]),
    (1.99, kinds.RESULT_GREENS[1]), (2.0, kinds.RESULT_GREENS[2]),
    (-0.5, kinds.RESULT_REDS[0]), (-1.5, kinds.RESULT_REDS[1]), (-2.5, kinds.RESULT_REDS[2]),
    (0.0, kinds.RESULT_GREY), (0.05, kinds.RESULT_GREY), (-0.04, kinds.RESULT_GREY),
    (None, kinds.RESULT_GREY),
])
def test_result_stripe_steps_by_abs_r(r, expected):
    assert kinds.stripe(Kind.EXITED, r=r) == expected


@pytest.mark.parametrize("kind,expected", [
    (Kind.SCRATCHED, kinds.RESULT_GREY), (Kind.EXPIRED, kinds.RESULT_GREY),
    (Kind.INVALIDATED, kinds.RESULT_GREY), (Kind.FILLED, kinds.ENTRY_TEAL),
    (Kind.ENTRY_TRIGGERED, kinds.ENTRY_TEAL), (Kind.MOVE_STOP, kinds.MANAGE_AMBER),
    (Kind.RISK_CAP, kinds.MANAGE_AMBER), (Kind.NEAR_STOP, kinds.WATCH_STOP_ORANGE),
    (Kind.NEAR_TP, kinds.WATCH_TP_LIME), (Kind.SCAN_SUMMARY, kinds.SYSTEM_SLATE),
    (Kind.HEALTH_ALERT, kinds.HEALTH_RED), (Kind.HEALTH_RECOVERED, kinds.HEALTH_GREEN),
])
def test_fixed_kinds_use_their_own_colour(kind, expected):
    assert kinds.stripe(kind, level=5, r=3.0) == expected


def test_no_stripe_colour_is_shared_across_families():
    seen = {}
    for family in Family:
        for colour in _family_colours(family):
            owner = seen.setdefault(colour, family)
            assert owner is family, f"{colour:#08x} used by {owner.name} and {family.name}"


def test_every_ramp_step_is_distinct():
    assert len(set(kinds.SETUP_RAMP.values()) | {kinds.SETUP_BLOCKED}) == 6
    assert len(set(kinds.RESULT_GREENS) | set(kinds.RESULT_REDS) | {kinds.RESULT_GREY}) == 7


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_content_line_starts_with_the_badge(kind, direction):
    assert kinds.content_line(kind, "AAPL", direction).startswith(kinds.badge(kind))


@pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
@pytest.mark.parametrize("direction", DIRECTIONS)
def test_titles_never_carry_the_retired_circles(kind, direction):
    for text in (kinds.title(kind, "AAPL", direction), kinds.content_line(kind, "AAPL", direction)):
        assert "🟢" not in text and "🔴" not in text


def test_title_shapes():
    assert kinds.title(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐") == "🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert kinds.title(Kind.MOVE_STOP, "NVDA", "bearish") == "✂️ ▼ SHORT NVDA · MOVE STOP"
    assert kinds.title(Kind.BE_MOVED, "NVDA", "bullish") == "🛡️ ▲ LONG NVDA · BREAK-EVEN"
    assert (kinds.title(Kind.HEALTH_ALERT, "", detail="3 failed tick(s) in a row")
            == "🚨 HEALTH ALERT · 3 failed tick(s) in a row")
    assert kinds.title(Kind.NEAR_TP, "AAPL") == "👀 AAPL · NEARING TP"


def test_content_line_names_the_family():
    assert (kinds.content_line(Kind.CLOSED_TRADE, "AAPL", "bullish", kinds.outcome_detail("win", 1.8))
            == "🏁 RESULT · ▲ LONG AAPL · CLOSED · ✅ WIN +1.8R")
    assert (kinds.content_line(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐")
            == "🆕 NEW SETUP · ▲ LONG AAPL · ALERT · Lv4 ⭐")
    assert kinds.content_line(Kind.BOT_ONLINE, "") == "🤖 SYSTEM · ONLINE"


def test_footer_carries_the_disclaimer_only_on_new_setup():
    assert kinds.footer(Kind.SETUP_ALERT, "0123456789ab") == f"{tokens.DISCLAIMER} · plan 01234567"
    assert kinds.footer(Kind.TICKET_PLACE) == tokens.DISCLAIMER
    assert kinds.footer(Kind.CLOSED_TRADE, "0123456789ab") == "RESULT · plan 01234567"
    assert kinds.footer(Kind.BOT_ONLINE) == "SYSTEM"
    assert kinds.footer(Kind.NEAR_STOP, "p1") == "WATCH · plan p1"


def test_family_badges_never_double_as_outcome_or_direction_marks():
    badges = {f.badge for f in Family}
    assert not badges & (set(kinds.OUTCOME_MARKS.values()) | {"▲", "▼"})


@pytest.mark.parametrize("outcome,r,expected", [
    ("win", 1.8, "✅ WIN +1.8R"), ("loss", -1.0, "❌ LOSS −1.0R"),
    ("scratch", 0.0, "⚪ SCRATCH 0.0R"), ("manual", None, "🔒 MANUAL CLOSE"),
    ("expired", None, "⏹️ EXPIRED"), ("invalidated", None, "⏹️ INVALIDATED"),
])
def test_outcome_detail(outcome, r, expected):
    assert kinds.outcome_detail(outcome, r) == expected


@pytest.mark.parametrize("r,expected", [
    (0.5, "win"), (0.06, "win"), (0.05, "scratch"), (-0.05, "scratch"),
    (-0.2, "loss"), (None, "scratch"),
])
def test_outcome_for_r_uses_the_instruction_tone_band(r, expected):
    assert kinds.outcome_for_r(r) == expected


@pytest.mark.parametrize("outcome,r,expected", [
    ("win", -2.0, 2.0), ("loss", 2.0, -2.0), ("loss", -1.5, -1.5),
    ("manual", 2.0, None), ("scratch", 0.3, None), ("win", None, None),
])
def test_result_r_signs_the_stripe_by_outcome(outcome, r, expected):
    assert kinds.result_r(outcome, r) == expected


def test_plan_badge_text_keeps_the_check_mark_for_outcomes_only():
    assert kinds.plan_badge_text("VALIDATED") == "VALIDATED"
    assert kinds.plan_badge_text("WEAK") == "⚠️ WEAK"


def test_side_word():
    assert kinds.side_word("bullish") == "LONG"
    assert kinds.side_word("bearish") == "SHORT"
    assert kinds.side_word(None) == tokens.ABSENT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python scripts/dev/testrun.py file tests/presentation/test_kinds.py`
Expected: FAIL — `ImportError: cannot import name 'kinds'`.

- [ ] **Step 3: Write the implementation**

Create `swingbot/core/presentation/kinds.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python scripts/dev/testrun.py file tests/presentation/test_kinds.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/presentation/kinds.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/presentation/kinds.py tests/presentation/test_kinds.py
git commit -m "feat(v110): notification kind registry -- families, kinds, stripe ramps, title/content/stripe/footer

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/presentation/kinds.py tests/presentation/test_kinds.py
```

---

### Task V110-2: ANSI price blocks — restyled headline, levels block, result block

**Files:**
- Modify: `swingbot/core/presentation/ansi.py` (`plan_lines`, plus the new `direction_line`, `r_multiple`, `levels_lines` and `result_lines`)
- Modify: `swingbot/core/presentation/components.py` (add `levels_block` and `result_headline`)
- Modify: `swingbot/core/presentation/__init__.py` (export `levels_block` and `result_headline`)
- Test: `tests/presentation/test_ansi.py`, `tests/presentation/test_components.py`

**Interfaces:**
- Consumes: `tokens.direction_glyph`, `fmt_price`, `fmt_pct`, `fmt_r`, `ABSENT`.
- Produces:
  - `ansi.direction_line(direction) -> str`
  - `ansi.r_multiple(entry, stop, target) -> float | None`
  - `ansi.levels_lines(*, direction, entry, stop, tp1, tp2=None) -> list[str]`
  - `ansi.result_lines(*, direction, entry, exit_price, stop, pct, r) -> list[str]`
  - `ui.levels_block(*, direction, entry, stop, tp1, tp2=None) -> str`
  - `ui.result_headline(*, direction, entry, exit_price, stop, pct, r) -> str`
  - `ansi.plan_lines` now returns **three** lines: side, levels, magnitudes. Its signature is unchanged.

- [ ] **Step 1: Write the failing tests**

In `tests/presentation/test_ansi.py`, replace everything from `def _plan(**kw):` to the end of the file with:

```python
def _plan(**kw):
    base = dict(direction="bullish", entry=197.15, target=220.81, stop=185.32,
                target_pct=12.0, stop_pct=-6.0, r=2.4)
    base.update(kw)
    return ansi.plan_lines(**base)


def _plain(line):
    return ansi._ESCAPE_RE.sub("", line)


def test_plan_lines_are_side_levels_magnitudes():
    assert len(_plan()) == 3


def test_first_line_names_the_side_in_its_colour():
    assert _plan()[0] == ansi.paint("▲ LONG", "green")
    assert _plan(direction="bearish")[0] == ansi.paint("▼ SHORT", "red")


def test_unknown_direction_is_an_unpainted_dash():
    assert _plan(direction="sideways")[0] == "—"


def test_second_line_reads_entry_arrow_target_slash_stop():
    assert _plain(_plan()[1]) == "197.15 → 220.81 / 185.32"


def test_entry_is_cyan_target_green_stop_red():
    line = _plan()[1]
    assert ansi.paint("197.15", "cyan") in line
    assert ansi.paint("220.81", "green") in line
    assert ansi.paint("185.32", "red") in line


def test_third_line_carries_the_magnitudes_with_r_in_yellow():
    line = _plan()[2]
    assert "+12.0%" in _plain(line) and "−6.0%" in _plain(line)
    assert ansi.paint("2.4R", "yellow") in line


def test_a_missing_entry_still_produces_three_readable_lines():
    lines = _plan(entry=None, r=None)
    assert len(lines) == 3
    assert "—" in _plain(lines[1])


def test_no_plan_line_exceeds_width():
    lines = ansi.plan_lines(direction="bearish", entry=99999.99, target=88888.88,
                            stop=11111.11, target_pct=-123.4, stop_pct=45.6, r=-12.3)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
    ansi.block(lines)


def test_r_multiple_is_reward_over_risk():
    assert ansi.r_multiple(100.0, 95.0, 110.0) == 2.0
    assert ansi.r_multiple(100.0, 100.0, 110.0) is None
    assert ansi.r_multiple(None, 95.0, 110.0) is None


def test_levels_lines_paint_every_level():
    lines = ansi.levels_lines(direction="bullish", entry=100.0, stop=95.0, tp1=110.0, tp2=120.0)
    assert [_plain(line) for line in lines] == [
        "▲ LONG", "entry 100.00", "stop  95.00", "TP1   110.00 2.0R", "TP2   120.00 4.0R"]
    assert ansi.paint("100.00", "cyan") in lines[1]
    assert ansi.paint("95.00", "red") in lines[2]
    assert ansi.paint("110.00", "green") in lines[3]
    assert ansi.paint("2.0R", "yellow") in lines[3]


def test_levels_lines_omit_a_missing_tp2_and_an_undefined_r():
    lines = ansi.levels_lines(direction="bearish", entry=100.0, stop=100.0, tp1=90.0)
    assert len(lines) == 4
    assert _plain(lines[3]) == "TP1   90.00"


def test_levels_lines_stay_phone_safe():
    lines = ansi.levels_lines(direction="bearish", entry=99999.99, stop=11111.11,
                              tp1=88888.88, tp2=77777.77)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
    ansi.block(lines)


@pytest.mark.parametrize("r,colour", [(1.8, "green"), (-1.0, "red"), (0.0, "white"), (None, "white")])
def test_result_lines_paint_the_realised_r_by_sign(r, colour):
    lines = ansi.result_lines(direction="bullish", entry=100.0, exit_price=109.0,
                              stop=95.0, pct=9.0, r=r)
    assert len(lines) == 3
    assert ansi.paint(tokens.fmt_r(r), colour) in lines[2]
    assert _plain(lines[1]) == "100.00 → 109.00 / 95.00"


def test_result_lines_stay_phone_safe():
    lines = ansi.result_lines(direction="bearish", entry=99999.99, exit_price=88888.88,
                              stop=11111.11, pct=-123.4, r=-12.3)
    for line in lines:
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH
```

Also add `from swingbot.core.presentation import tokens` to the imports at the top of `test_ansi.py`, below `from swingbot.core.presentation import ansi`.

Append to `tests/presentation/test_components.py`:

```python
def test_levels_block_is_a_fenced_ansi_block():
    out = c.levels_block(direction="bullish", entry=100.0, stop=95.0, tp1=110.0)
    assert out.startswith("```ansi\n") and out.endswith("\n```")
    assert "100.00" in out and "110.00" in out


def test_result_headline_is_a_fenced_ansi_block():
    out = c.result_headline(direction="bearish", entry=100.0, exit_price=94.0,
                            stop=105.0, pct=6.0, r=1.2)
    assert out.startswith("```ansi\n") and "94.00" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_ansi.py tests/presentation/test_components.py`
Expected: FAIL. `plan_lines` still returns two lines, `levels_lines` / `result_lines` / `r_multiple` / `direction_line` do not exist, and `c.levels_block` raises `AttributeError`.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/presentation/ansi.py`, replace the whole `plan_lines` function with:

```python
_SIDE_WORDS = {"bullish": "LONG", "bearish": "SHORT"}
_SIDE_COLOURS = {"bullish": "green", "bearish": "red"}


def direction_line(direction: str) -> str:
    """``▲ LONG`` in green or ``▼ SHORT`` in red; an unknown direction is an unpainted dash."""
    side = _SIDE_WORDS.get(direction)
    if side is None:
        return tokens.ABSENT
    return paint(f"{tokens.direction_glyph(direction)} {side}", _SIDE_COLOURS[direction])


def r_multiple(entry: float | None, stop: float | None, target: float | None) -> float | None:
    """Reward over risk for one target; None when a level is missing or risk is zero."""
    if entry is None or stop is None or target is None:
        return None
    risk = abs(entry - stop)
    return abs(target - entry) / risk if risk else None


def plan_lines(*, direction: str, entry: float | None, target: float | None,
               stop: float | None, target_pct: float | None,
               stop_pct: float | None, r: float | None) -> list[str]:
    """Return the three-line, phone-safe plan headline: side, levels, magnitudes."""
    levels = (
        f"{paint(tokens.fmt_price(entry), 'cyan')} → "
        f"{paint(tokens.fmt_price(target), 'green')} / "
        f"{paint(tokens.fmt_price(stop), 'red')}"
    )
    magnitudes = (
        f"  {paint(tokens.fmt_pct(target_pct), 'green')} "
        f"{paint(tokens.fmt_pct(stop_pct), 'red')} "
        f"{paint(tokens.fmt_r(r), 'yellow')}"
    )
    return [direction_line(direction), levels, magnitudes]


def _target_line(name: str, target: float | None, entry: float | None,
                 stop: float | None) -> str:
    line = f"{name:<5} {paint(tokens.fmt_price(target), 'green')}"
    reward = r_multiple(entry, stop, target)
    return line if reward is None else f"{line} {paint(tokens.fmt_r(reward), 'yellow')}"


def levels_lines(*, direction: str, entry: float | None, stop: float | None,
                 tp1: float | None, tp2: float | None = None) -> list[str]:
    """The NEW SETUP / ENTRY price block: side, entry, stop, TP1 and TP2 with R."""
    lines = [
        direction_line(direction),
        f"{'entry':<5} {paint(tokens.fmt_price(entry), 'cyan')}",
        f"{'stop':<5} {paint(tokens.fmt_price(stop), 'red')}",
        _target_line("TP1", tp1, entry, stop),
    ]
    if tp2 is not None:
        lines.append(_target_line("TP2", tp2, entry, stop))
    return lines


def _realised_colour(r: float | None) -> str:
    if not r:
        return "white"
    return "green" if r > 0 else "red"


def result_lines(*, direction: str, entry: float | None, exit_price: float | None,
                 stop: float | None, pct: float | None, r: float | None) -> list[str]:
    """The RESULT price block: side, entry → exit / stop, and the realised move."""
    return [
        direction_line(direction),
        (f"{paint(tokens.fmt_price(entry), 'cyan')} → {tokens.fmt_price(exit_price)} / "
         f"{paint(tokens.fmt_price(stop), 'red')}"),
        f"  {tokens.fmt_pct(pct)} {paint(tokens.fmt_r(r), _realised_colour(r))}",
    ]
```

In `swingbot/core/presentation/components.py`, add below `plan_headline`:

```python
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
```

In `swingbot/core/presentation/__init__.py`, extend the components import to:

```python
from swingbot.core.presentation.components import (  # noqa: F401
    EmbedField, apply_chrome, blocked_by_field, confidence_field, follow_field,
    levels_block, plan_headline, result_headline,
)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_ansi.py tests/presentation/test_components.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/presentation/ansi.py swingbot/core/presentation/components.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/presentation/ansi.py swingbot/core/presentation/components.py swingbot/core/presentation/__init__.py tests/presentation/test_ansi.py tests/presentation/test_components.py
git commit -m "feat(v110): ANSI price blocks -- restyled plan headline, levels block, result block

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/presentation/ansi.py swingbot/core/presentation/components.py swingbot/core/presentation/__init__.py tests/presentation/test_ansi.py tests/presentation/test_components.py
```

---

### Task V110-3: `apply_chrome(kind=…)` and the `PushEmbed` push line

**Files:**
- Modify: `swingbot/core/presentation/components.py` (`apply_chrome`, plus the new `PushEmbed`, `push_embed` and `push_kwargs`)
- Modify: `swingbot/core/presentation/__init__.py` (exports and module docstring)
- Test: `tests/presentation/test_components.py`

**Interfaces:**
- Consumes: V110-1's `kinds.stripe`, `kinds.footer`, `kinds.title`, `kinds.content_line` and `Kind`.
- Produces:
  - `ui.apply_chrome(embed, *, accent=None, plan_id=None, kind=None, level=None, r=None, blocked=False) -> None`. With `kind`, the stripe and footer come from the registry. Without it, `accent` is required and the legacy disclaimer footer is kept for command replies. With neither, it raises `ValueError`.
  - `ui.PushEmbed(discord.Embed)` with a `push_text` slot.
  - `ui.push_embed(kind, ticker="", direction=None, detail="", *, description=None) -> PushEmbed`, which sets `title` and `push_text` from the registry.
  - `ui.push_kwargs(embed) -> dict`: `{"embed": e, "content": e.push_text}` when the embed carries a push line, else `{"embed": e}`. This also holds for plain embeds and the strings the existing tests pass.

- [ ] **Step 1: Write the failing tests**

Append to `tests/presentation/test_components.py`:

```python
from swingbot.core.presentation import kinds
from swingbot.core.presentation.kinds import Kind


def test_apply_chrome_with_a_kind_takes_the_registry_stripe_and_footer():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.CLOSED_TRADE, r=2.5, plan_id="a4f19c2233445566")
    assert embed.color.value == kinds.RESULT_GREENS[2]
    assert embed.footer.text == "RESULT · plan a4f19c22"
    assert embed.timestamp is not None


def test_apply_chrome_new_setup_keeps_the_disclaimer():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=5, plan_id="a4f19c2233445566")
    assert embed.color.value == kinds.SETUP_RAMP[5]
    assert embed.footer.text == f"{t.DISCLAIMER} · plan a4f19c22"


def test_apply_chrome_blocked_setup_is_the_muted_grey_blue():
    embed = discord.Embed(title="x")
    c.apply_chrome(embed, kind=Kind.SETUP_ALERT, level=5, blocked=True)
    assert embed.color.value == kinds.SETUP_BLOCKED


def test_apply_chrome_needs_a_kind_or_an_accent():
    with pytest.raises(ValueError):
        c.apply_chrome(discord.Embed(title="x"))


def test_push_embed_carries_title_and_push_line():
    embed = c.push_embed(Kind.SETUP_ALERT, "AAPL", "bullish", "Lv4 ⭐", description="body")
    assert isinstance(embed, discord.Embed)
    assert embed.title == "🆕 ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert embed.push_text == "🆕 NEW SETUP · ▲ LONG AAPL · ALERT · Lv4 ⭐"
    assert embed.description == "body"


def test_push_kwargs_adds_content_only_when_the_embed_has_a_push_line():
    pushed = c.push_embed(Kind.BOT_ONLINE)
    assert c.push_kwargs(pushed) == {"embed": pushed, "content": "🤖 SYSTEM · ONLINE"}
    plain = discord.Embed(title="x")
    assert c.push_kwargs(plain) == {"embed": plain}
    assert c.push_kwargs("EMBED") == {"embed": "EMBED"}


def test_the_package_exports_the_push_helpers():
    from swingbot.core import presentation as ui
    assert ui.push_embed is c.push_embed and ui.push_kwargs is c.push_kwargs
    assert ui.PushEmbed is c.PushEmbed
```

Also add `import pytest` to the top of `tests/presentation/test_components.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: FAIL. `apply_chrome()` has no `kind` parameter (`TypeError`), and `push_embed` does not exist.

- [ ] **Step 3: Write the implementation**

In `swingbot/core/presentation/components.py`, change the import line to `from swingbot.core.presentation import ansi, kinds, tokens` and add `from swingbot.core.presentation.kinds import Kind` below it. Then replace `apply_chrome` with:

```python
def apply_chrome(embed: discord.Embed, *, accent: discord.Color | None = None,
                 plan_id: str | None = None, kind: Kind | None = None,
                 level: int | None = None, r: float | None = None,
                 blocked: bool = False) -> None:
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


class PushEmbed(discord.Embed):
    """A discord.Embed that also carries its push-preview line (v110 §4).

    A phone push shows a message's ``content``, never the embed title, so every
    pushed builder returns one of these and every sender passes
    ``push_kwargs(embed)`` to ``send()``. Carrying the line on the embed keeps
    the alert tuples' shape unchanged."""

    __slots__ = ("push_text",)


def push_embed(kind: Kind, ticker: str = "", direction: str | None = None,
               detail: str = "", *, description: str | None = None) -> PushEmbed:
    """A PushEmbed whose title and push line both come from the registry."""
    embed = PushEmbed(title=kinds.title(kind, ticker, direction, detail), description=description)
    embed.push_text = kinds.content_line(kind, ticker, direction, detail)
    return embed


def push_kwargs(embed) -> dict:
    """send() kwargs for one pushed embed: the embed, plus its content line if it has one."""
    text = getattr(embed, "push_text", None)
    return {"embed": embed, "content": text} if text else {"embed": embed}
```

In `swingbot/core/presentation/__init__.py`, change the components import to:

```python
from swingbot.core.presentation.components import (  # noqa: F401
    EmbedField, PushEmbed, apply_chrome, blocked_by_field, confidence_field, follow_field,
    levels_block, plan_headline, push_embed, push_kwargs, result_headline,
)
```

In its module docstring, replace `Three modules, smallest dependency first:` with `Four modules, smallest dependency first:`. Insert this entry after the `tokens.py` entry:

```
  kinds.py       v110: the registry of pushed notification kinds -- six
                 families, one Kind per event, the stripe ramps, and the
                 title / content_line / stripe / footer helpers that are the
                 only way a pushed builder styles a message. Pure.
```

Append this line to the `components.py` entry: `PushEmbed carries a pushed message's content line; senders use push_kwargs().`

- [ ] **Step 4: Run tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py tests/presentation/test_no_adhoc_color.py tests/presentation/test_kinds.py`
Expected: PASS, 0 failed.

- [ ] **Step 5: Complexity**

Run: `python -m radon cc -s -n C swingbot/core/presentation/components.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/presentation/components.py swingbot/core/presentation/__init__.py tests/presentation/test_components.py
git commit -m "feat(v110): apply_chrome takes the kind; PushEmbed carries the push-preview line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- swingbot/core/presentation/components.py swingbot/core/presentation/__init__.py tests/presentation/test_components.py
```

---

