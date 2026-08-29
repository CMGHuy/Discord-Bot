# v62 part 1 — `core/presentation/`: the kit

Index and global constraints C1–C9: `2026-08-25-v62-discord-message-system_0-index.md`.
Read that first. **Nothing in this part changes what Discord renders** — no
existing module imports the kit until Part 2.

Worktree: `2026-08-25-v62-discord-message-system_1-kit`.

---

# Phase 1 — Tokens and ANSI

### Task M1: The accent ramp

**Files:**
- Create: `swingbot/core/presentation/__init__.py`
- Create: `swingbot/core/presentation/tokens.py`
- Create: `tests/presentation/__init__.py`
- Test: `tests/presentation/test_tokens.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ACCENT_RAMP: dict[int, int]`, `ACCENT_BLOCKED: int`,
  `accent_for_level(level: int | None) -> discord.Color`,
  `accent_for_outcome(outcome: str) -> discord.Color`. M2, M3, M5, M7 and all
  of Parts 2–3 consume these.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_tokens.py
import discord
from swingbot.core.presentation import tokens as t


def test_accent_ramp_is_monotonic_worse_to_better():
    """The bar is often the only signal, so it must read as ordinal.
    Red -> amber -> grey -> yellow-green -> green. No categorical hue
    (the SPA's --quality-4 blue) anywhere on it."""
    assert t.accent_for_level(1).value == 0xFF5470   # red
    assert t.accent_for_level(2).value == 0xFFB43D   # amber
    assert t.accent_for_level(3).value == 0x9BA3BD   # grey
    assert t.accent_for_level(4).value == 0x9ACD32   # yellow-green
    assert t.accent_for_level(5).value == 0x17C98E   # green


def test_unknown_level_falls_back_to_the_bottom_of_the_ramp():
    """A missing level is not a good level. None and out-of-range both
    render as level 1 rather than raising -- an alert with a broken
    confidence field should still post."""
    assert t.accent_for_level(None).value == 0xFF5470
    assert t.accent_for_level(0).value == 0xFF5470
    assert t.accent_for_level(9).value == 0xFF5470


def test_outcome_accents_are_the_same_three_colours_as_the_ramp_ends():
    """Green/red mean the same thing on a closed trade as on an alert --
    that is the whole point of C2. Scratch is the ramp's own grey, not a
    fourth colour."""
    assert t.accent_for_outcome("win").value == 0x17C98E
    assert t.accent_for_outcome("loss").value == 0xFF5470
    assert t.accent_for_outcome("scratch").value == 0x9BA3BD


def test_unknown_outcome_is_grey_not_a_crash():
    assert t.accent_for_outcome("").value == 0x9BA3BD
    assert t.accent_for_outcome("garbage").value == 0x9BA3BD


def test_blocked_accent_is_the_neutral_grey():
    """A setup that failed a gate is not a LOSS -- it never opened. It
    reads as inert, not as bad."""
    assert t.ACCENT_BLOCKED == 0x9BA3BD
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.presentation'`

- [ ] **Step 3: Create the package and write the minimal implementation**

```python
# swingbot/core/presentation/__init__.py
"""
The one place the bot's Discord presentation is defined -- colours, glyphs,
number formats, and the embed parts built from them.

Three modules, smallest dependency first:

  tokens.py      pure values: the accent ramp, direction glyphs, the
                 confidence label, the follow meter, number formatters.
                 No discord.Embed anywhere; importable and testable on its
                 own.
  ansi.py        the ``` ansi ``` code block, which is one of exactly two
                 places Discord renders colour (the other being an embed's
                 4px accent bar). 8 foreground colours, hard 32-char line cap.
  components.py  whole embed PARTS -- a field, a headline, the chrome. Call
                 sites ask for a part rather than assembling one out of
                 tokens, which is what stops the kit being half-used.

It lives in core/ rather than in core/scanning/ (where embed_theme.py used
to) because ~12 swingbot/commands/* modules need it, and
`commands -> core.scanning` for a colour is a dependency that misdescribes
the code.

tests/presentation/test_no_adhoc_color.py enforces that no module outside
this package touches discord.Color at all.
"""
```

```python
# swingbot/core/presentation/tokens.py
"""
Pure presentation values. No discord.Embed is constructed here and nothing
in this module reads a plan object -- everything takes plain scalars, so
every rule below is testable without a Discord object or a fixture.

The ramp is ORDINAL by design (v62 D2). The admin SPA shares it via
frontend/src/styles/tokens.css's --quality-1..5; if you change a value here,
change it there too or the two surfaces disagree about what a level looks
like, which is the exact bug v62 exists to remove.
"""
import discord

#: Confidence level -> accent colour, worse to better.
#:
#: Monotonic on purpose. The SPA's original ramp put --info blue at level 4,
#: which reads as "informational" rather than "nearly top" on a 4px bar seen
#: at a glance. Level 4 is yellow-green here and in tokens.css.
ACCENT_RAMP: dict[int, int] = {
    1: 0xFF5470,   # red      -- SPA --neg
    2: 0xFFB43D,   # amber    -- SPA --warn
    3: 0x9BA3BD,   # grey     -- SPA --text-secondary
    4: 0x9ACD32,   # yellow-green
    5: 0x17C98E,   # green    -- SPA --pos
}

#: A setup that failed a configured gate. Deliberately the ramp's own grey
#: and NOT red: it never opened, so it is inert rather than a loss.
ACCENT_BLOCKED: int = 0x9BA3BD

_OUTCOME_ACCENTS: dict[str, int] = {
    "win": ACCENT_RAMP[5],
    "loss": ACCENT_RAMP[1],
    "scratch": ACCENT_RAMP[3],
}


def accent_for_level(level: int | None) -> discord.Color:
    """The accent bar for a confidence level.

    An unknown or missing level falls back to the BOTTOM of the ramp, not
    the middle: a broken confidence field should not make a plan look
    better than it is, and an alert with one bad field should still post.
    """
    return discord.Color(ACCENT_RAMP.get(level or 0, ACCENT_RAMP[1]))


def accent_for_outcome(outcome: str) -> discord.Color:
    """The accent bar for a closed trade. Same three colours as the ramp's
    ends, because green/red must mean the same thing on every channel (C2)."""
    return discord.Color(_OUTCOME_ACCENTS.get((outcome or "").lower(),
                                              ACCENT_RAMP[3]))
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python -m pytest tests/presentation/test_tokens.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/__init__.py swingbot/core/presentation/tokens.py tests/presentation/__init__.py tests/presentation/test_tokens.py
git commit -m "feat(v62): the accent ramp -- one ordinal colour scale for every channel"
```

---

### Task M2: Glyphs, labels and number formatters

**Files:**
- Modify: `swingbot/core/presentation/tokens.py` (append)
- Test: `tests/presentation/test_tokens.py` (append)

**Interfaces:**
- Consumes: nothing from M1 at runtime; same file.
- Produces: `direction_glyph(direction: str) -> str`,
  `confidence_label(level: int | None, score: float | None) -> str`,
  `follow_meter(score: float) -> str`, `fmt_price(x, sym="") -> str`,
  `fmt_pct(x) -> str`, `fmt_r(x) -> str`. Every builder in Parts 2–3 uses
  these; C8 forbids inline float formatting of a price.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/presentation/test_tokens.py

def test_direction_glyph_is_shape_never_colour():
    """C2. The same two glyphs the admin SPA uses (direction-arrow.ts:51),
    so Discord and the dashboard say long/short identically."""
    assert t.direction_glyph("bullish") == "▲"   # up triangle
    assert t.direction_glyph("bearish") == "▼"   # down triangle


def test_direction_glyph_of_something_unknown_is_an_em_dash():
    """Not a triangle. Guessing a direction is worse than admitting we
    do not have one."""
    assert t.direction_glyph("") == "—"
    assert t.direction_glyph("sideways") == "—"


def test_confidence_label_is_level_and_score():
    """v62 D5 -- the form confidence-cell.ts already renders."""
    assert t.confidence_label(5, 91) == "Lv5 · 91"
    assert t.confidence_label(1, 0) == "Lv1 · 0"


def test_confidence_label_without_a_score_shows_the_level_alone():
    """A missing score is not a zero score. 'Lv5 - 0' would read as a
    terrible level-5 plan."""
    assert t.confidence_label(5, None) == "Lv5"


def test_confidence_label_without_a_level_is_an_em_dash():
    assert t.confidence_label(None, 91) == "—"


def test_follow_meter_is_a_five_block_bar_plus_the_number():
    assert t.follow_meter(82.0) == "▰▰▰▰▱ 82"
    assert t.follow_meter(0.0) == "▱▱▱▱▱ 0"
    assert t.follow_meter(100.0) == "▰▰▰▰▰ 100"


def test_follow_meter_clamps_out_of_range_scores():
    """The bar has five blocks and cannot render six. A score outside
    0-100 is a bug upstream, but it must not produce a ragged bar."""
    assert t.follow_meter(-30.0) == "▱▱▱▱▱ 0"
    assert t.follow_meter(400.0) == "▰▰▰▰▰ 100"


def test_fmt_price_keeps_four_decimals_below_one():
    """Carried over from embed_theme.fmt_price: 2dp is typical equity
    granularity, but 2dp on a sub-1.00 ticker loses all precision."""
    assert t.fmt_price(1234.5) == "1234.50"
    assert t.fmt_price(0.4321) == "0.4321"
    assert t.fmt_price(12.5, "€") == "€12.50"


def test_fmt_price_of_none_is_an_em_dash_not_zero():
    """A price we do not have is not a price of zero -- the same rule the
    SPA's format.ts states for every figure it renders."""
    assert t.fmt_price(None) == "—"


def test_fmt_pct_always_carries_its_sign():
    """So a gain and a loss are told apart without reading the colour --
    which matters because an ANSI block is the only place colour exists,
    and plain fields have none at all."""
    assert t.fmt_pct(12.0) == "+12.0%"
    assert t.fmt_pct(-6.0) == "−6.0%"
    assert t.fmt_pct(0.0) == "0.0%"
    assert t.fmt_pct(None) == "—"


def test_fmt_pct_uses_a_real_minus_sign_not_a_hyphen():
    """U+2212. A hyphen is narrower than a digit even in a mono face, so
    a column of hyphen-negatives does not align -- same reasoning as the
    SPA's own signed()."""
    assert "−" in t.fmt_pct(-6.0)
    assert "-" not in t.fmt_pct(-6.0)


def test_fmt_r_names_its_unit():
    """Unlike the SPA's R column, an ANSI headline has no header row above
    it to name the unit, so the value carries it."""
    assert t.fmt_r(2.4) == "2.4R"
    assert t.fmt_r(-1.0) == "−1.0R"
    assert t.fmt_r(None) == "—"
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_tokens.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'direction_glyph'`

- [ ] **Step 3: Append the implementation**

```python
# append to swingbot/core/presentation/tokens.py

#: Renders wherever a value is absent. Never a zero, never a blank -- the
#: difference between "we do not know" and "it is nothing" is load-bearing on
#: a P&L. Same convention as the SPA's format.ts ABSENT.
ABSENT = "—"

_UP = "▲"
_DOWN = "▼"

#: U+2212 MINUS SIGN, not U+002D HYPHEN. A hyphen is narrower than a digit
#: even in a mono face, so inside an ANSI block a column of negatives does
#: not line up with a column of positives.
_MINUS = "−"


def direction_glyph(direction: str) -> str:
    """C2: direction is shape, never colour. The same two glyphs
    frontend/src/app/ui/direction-arrow.ts renders, so the two surfaces
    cannot disagree about which way a plan points."""
    if direction == "bullish":
        return _UP
    if direction == "bearish":
        return _DOWN
    return ABSENT


def confidence_label(level: int | None, score: float | None) -> str:
    """'Lv5 · 91' (v62 D5). A missing SCORE degrades to the level alone
    rather than printing a zero -- 'Lv5 · 0' would read as a terrible
    level-5 plan. A missing LEVEL has nothing to say and is an em dash."""
    if level is None:
        return ABSENT
    if score is None:
        return f"Lv{level}"
    return f"Lv{level} · {round(score)}"


def follow_meter(score: float) -> str:
    """'▰▰▰▰▱ 82'. The bar and the number each round independently: the bar
    is a coarse 0-5 visual and the number beside it is the precise one, so
    they are allowed to disagree at a rounding boundary."""
    score = max(0.0, min(100.0, float(score)))
    filled = max(0, min(5, round(score / 20)))
    return f"{'▰' * filled}{'▱' * (5 - filled)} {round(score)}"


def fmt_price(x: float | None, sym: str = "") -> str:
    """2dp at or above 1.0 (typical equity granularity); 4dp below, where
    2dp would lose all precision on a penny ticker."""
    if x is None:
        return ABSENT
    return f"{sym}{x:.2f}" if abs(x) >= 1.0 else f"{sym}{x:.4f}"


def fmt_pct(x: float | None) -> str:
    """Always signed, one decimal. See _MINUS for why the negative is not
    a hyphen."""
    if x is None:
        return ABSENT
    if x > 0:
        return f"+{x:.1f}%"
    if x < 0:
        return f"{_MINUS}{abs(x):.1f}%"
    return "0.0%"


def fmt_r(x: float | None) -> str:
    """An R-multiple, unit included -- an ANSI headline has no header row
    above it to name the unit the way the SPA's R column does."""
    if x is None:
        return ABSENT
    if x < 0:
        return f"{_MINUS}{abs(x):.1f}R"
    return f"{x:.1f}R"
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_tokens.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/tokens.py tests/presentation/test_tokens.py
git commit -m "feat(v62): glyphs, confidence label, follow meter and number formatters"
```

---

### Task M3: The ANSI code block

**Files:**
- Create: `swingbot/core/presentation/ansi.py`
- Test: `tests/presentation/test_ansi.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `FG: dict[str, int]`, `paint(text: str, colour: str, bold: bool = True) -> str`,
  `block(lines: list[str]) -> str`, `MAX_LINE_WIDTH: int`. M4 and
  `components.plan_headline` (M5) consume these.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_ansi.py
import pytest
from swingbot.core.presentation import ansi


def test_paint_wraps_text_in_an_escape_pair():
    """Discord's ansi highlighter needs both the set and the reset; an
    unclosed sequence bleeds into the rest of the block."""
    assert ansi.paint("LONG", "green") == "[1;32mLONG[0m"


def test_paint_without_bold_uses_the_plain_intensity():
    assert ansi.paint("x", "red", bold=False) == "[0;31mx[0m"


def test_palette_is_the_eight_discord_actually_renders():
    """Discord's ansi block supports foreground 30-37 and nothing else.
    A 256-colour or truecolour sequence renders as literal text."""
    assert set(ansi.FG.values()) <= set(range(30, 38))


def test_block_fences_with_the_ansi_language_tag():
    """Without the tag Discord renders it as a plain code block and every
    escape sequence shows up as garbage characters."""
    out = ansi.block(["one", "two"])
    assert out.startswith("```ansi\n")
    assert out.endswith("\n```")
    assert "one\ntwo" in out


def test_block_rejects_a_line_over_the_width_cap():
    """C3. A code block does not wrap on mobile -- it scrolls sideways,
    which is the exact defect v62 exists to remove. Failing loudly at
    build time is the only way this stays true."""
    with pytest.raises(ValueError, match="exceeds"):
        ansi.block(["x" * (ansi.MAX_LINE_WIDTH + 1)])


def test_width_is_measured_on_visible_text_not_escape_bytes():
    """A painted line is mostly escape sequences by byte count. Measuring
    the raw string would cap the visible content at about 12 characters."""
    line = ansi.paint("x" * 30, "green")
    assert len(line) > ansi.MAX_LINE_WIDTH
    ansi.block([line])   # must not raise


def test_max_line_width_is_32():
    """Measured against a 390px iPhone viewport in Discord's mono face."""
    assert ansi.MAX_LINE_WIDTH == 32
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_ansi.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.presentation.ansi'`

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/presentation/ansi.py
"""
The ``` ansi ``` code block -- one of exactly TWO places Discord renders
colour. The other is an embed's 4px accent bar. Embed titles, descriptions
and field values are all one colour and there is no markdown for it.

The bot already knew this: build_simple_alert built a coloured direction
triangle in an inline ansi block precisely because "embed titles can't carry
color". That pattern lives here now instead of in one builder.

The 32-character cap is the load-bearing rule. A code block does NOT wrap in
the Discord client -- it scrolls horizontally -- so a wide block is unreadable
on a phone, which is what the old 65-70 character plan table was. block()
raises rather than truncating: a silently cut price is worse than a loud
build failure.
"""
import re

#: Discord's ansi highlighter renders foreground 30-37 and nothing else.
#: 256-colour and truecolour sequences come through as literal text.
FG: dict[str, int] = {
    "grey": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}

#: Measured against a 390px iPhone viewport in Discord's mono face.
MAX_LINE_WIDTH = 32

_ESCAPE_RE = re.compile(r"\[[0-9;]*m")


def paint(text: str, colour: str, bold: bool = True) -> str:
    """One coloured run. Always emits the reset -- an unclosed sequence
    bleeds into every following line of the block."""
    code = FG.get(colour, FG["white"])
    intensity = 1 if bold else 0
    return f"[{intensity};{code}m{text}[0m"


def visible_width(line: str) -> int:
    """Length of what a reader actually sees. A painted line is mostly
    escape bytes, so measuring len() would cap visible content at about
    twelve characters."""
    return len(_ESCAPE_RE.sub("", line))


def block(lines: list[str]) -> str:
    """Fence `lines` as an ansi code block.

    Raises ValueError if any line exceeds MAX_LINE_WIDTH once escape
    sequences are discounted. That is deliberate and is the enforcement
    point for C3.
    """
    for line in lines:
        width = visible_width(line)
        if width > MAX_LINE_WIDTH:
            raise ValueError(
                f"ansi line exceeds {MAX_LINE_WIDTH} visible chars ({width}): "
                f"{_ESCAPE_RE.sub('', line)!r}. A Discord code block does not "
                f"wrap -- it scrolls sideways off a phone."
            )
    body = "\n".join(lines)
    return f"```ansi\n{body}\n```"
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_ansi.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/ansi.py tests/presentation/test_ansi.py
git commit -m "feat(v62): the ansi block, with a hard 32-char visible-width cap"
```

---

### Task M4: The plan headline lines

**Files:**
- Modify: `swingbot/core/presentation/ansi.py` (append)
- Test: `tests/presentation/test_ansi.py` (append)

**Interfaces:**
- Consumes: `paint`, `block`, `MAX_LINE_WIDTH` from M3;
  `tokens.fmt_price`, `fmt_pct`, `fmt_r`, `direction_glyph` from M2.
- Produces: `plan_lines(direction, entry, target, stop, target_pct, stop_pct, r) -> list[str]`.
  `components.plan_headline` (M5) is its only caller.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/presentation/test_ansi.py
from swingbot.core.presentation import ansi as a


def _plan(**kw):
    base = dict(direction="bullish", entry=197.15, target=220.81, stop=185.32,
                target_pct=12.0, stop_pct=-6.0, r=2.4)
    base.update(kw)
    return a.plan_lines(**base)


def test_plan_lines_are_two_lines():
    """Levels on one, magnitudes on the other. Three lines pushes the
    chart below the first screenful on a phone."""
    assert len(_plan()) == 2


def test_first_line_reads_entry_arrow_target_slash_stop():
    """Deliberately the same `entry -> target / stop` form the admin SPA's
    PlanCell renders, so the two surfaces read identically."""
    plain = a._ESCAPE_RE.sub("", _plan()[0])
    assert plain == "▲ 197.15 → 220.81 / 185.32"


def test_a_short_plan_leads_with_the_down_triangle():
    plain = a._ESCAPE_RE.sub("", _plan(direction="bearish")[0])
    assert plain.startswith("▼ ")


def test_the_triangle_is_green_for_long_and_red_for_short():
    """The one place a direction may carry colour: C2 forbids the ACCENT
    BAR encoding direction, not the glyph itself, and inside the block the
    colour is redundant reinforcement of a shape that already says it."""
    assert "[1;32m▲" in _plan()[0]
    assert "[1;31m▼" in _plan(direction="bearish")[0]


def test_target_is_green_and_stop_is_red():
    long_line = _plan()[0]
    assert a.paint("220.81", "green") in long_line
    assert a.paint("185.32", "red") in long_line


def test_a_short_plan_still_paints_target_green_and_stop_red():
    """Colour follows ROLE, not magnitude. On a short the target is the
    lower number; anything inferring role from size renders every long
    correctly and inverts silently on every short."""
    line = _plan(direction="bearish", target=170.00, stop=205.00)[0]
    assert a.paint("170.00", "green") in line
    assert a.paint("205.00", "red") in line


def test_second_line_carries_the_magnitudes():
    plain = a._ESCAPE_RE.sub("", _plan()[1])
    assert "+12.0%" in plain and "−6.0%" in plain and "2.4R" in plain


def test_a_missing_second_target_still_produces_two_lines():
    """A PENDING plan has no fill and a v2 runner has no fixed TP2. Neither
    is a reason to emit a ragged one-line headline."""
    lines = _plan(entry=None, r=None)
    assert len(lines) == 2
    assert "—" in a._ESCAPE_RE.sub("", lines[0])


def test_no_builder_exceeds_width():
    """C3, enforced against realistic worst-case inputs: a five-digit
    price on every leg plus a two-digit R."""
    lines = a.plan_lines(direction="bearish", entry=99999.99, target=88888.88,
                         stop=11111.11, target_pct=-123.4, stop_pct=45.6, r=-12.3)
    for line in lines:
        assert a.visible_width(line) <= a.MAX_LINE_WIDTH, a._ESCAPE_RE.sub("", line)
    a.block(lines)   # must not raise
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_ansi.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'plan_lines'`

- [ ] **Step 3: Append the implementation**

```python
# append to swingbot/core/presentation/ansi.py
from swingbot.core.presentation import tokens


def plan_lines(
    *,
    direction: str,
    entry: float | None,
    target: float | None,
    stop: float | None,
    target_pct: float | None,
    stop_pct: float | None,
    r: float | None,
) -> list[str]:
    """The alert headline, as two lines for block().

        ▲ 197.15 → 220.81 / 185.32
          +12.0%   −6.0%   2.4R

    Levels on the first line, magnitudes on the second. Two, not three:
    a third line pushes the chart below the first screenful on a phone.

    Colour follows ROLE, never magnitude -- the target is painted green and
    the stop red on a SHORT too, where the target is the lower number.
    Anything inferring role from size renders every long correctly and
    inverts silently on every short, which is the worst version of the bug
    because the cell still looks plausible.
    """
    glyph = tokens.direction_glyph(direction)
    glyph_colour = "green" if direction == "bullish" else "red"

    levels = (
        f"{paint(glyph, glyph_colour)} "
        f"{tokens.fmt_price(entry)} → "
        f"{paint(tokens.fmt_price(target), 'green')} / "
        f"{paint(tokens.fmt_price(stop), 'red')}"
    )
    magnitudes = (
        f"  {paint(tokens.fmt_pct(target_pct), 'green')}  "
        f"{paint(tokens.fmt_pct(stop_pct), 'red')}  "
        f"{paint(tokens.fmt_r(r), 'white', bold=False)}"
    )
    return [levels, magnitudes]
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_ansi.py`
Expected: `VERDICT: PASS`

If `test_no_builder_exceeds_width` fails, the fix is the *layout*, not the
cap: drop the two-space separators in `magnitudes` to one. Never raise
`MAX_LINE_WIDTH` — it is measured against a real viewport.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/ansi.py tests/presentation/test_ansi.py
git commit -m "feat(v62): the two-line plan headline, role-coloured and width-capped"
```

---

# Phase 2 — Components

### Task M5: Headline, confidence and follow parts

**Files:**
- Create: `swingbot/core/presentation/components.py`
- Test: `tests/presentation/test_components.py`

**Interfaces:**
- Consumes: `ansi.plan_lines`, `ansi.block`, `tokens.confidence_label`,
  `tokens.follow_meter`.
- Produces: `EmbedField` (NamedTuple: `name: str`, `value: str`, `inline: bool`),
  `plan_headline(...) -> str`, `confidence_field(level, score) -> EmbedField`,
  `follow_field(score, breakdown=None) -> EmbedField`. M6, M7 and every
  builder in Parts 2–3 consume these.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_components.py
from swingbot.core.presentation import components as c


def test_plan_headline_is_a_fenced_ansi_block():
    out = c.plan_headline(direction="bullish", entry=197.15, target=220.81,
                          stop=185.32, target_pct=12.0, stop_pct=-6.0, r=2.4)
    assert out.startswith("```ansi\n")
    assert out.endswith("\n```")
    assert "197.15" in out


def test_confidence_field_is_named_and_inline():
    """Inline so it pairs with Follow on one row rather than each taking
    a full-width row of its own on a phone."""
    f = c.confidence_field(5, 91)
    assert f.name == "Confidence"
    assert f.value == "Lv5 · 91"
    assert f.inline is True


def test_follow_field_appends_the_breakdown_on_its_own_line():
    """The meter answers 'how strong'; the breakdown answers 'why'. One
    field, two lines -- a second field would push the chart down."""
    f = c.follow_field(82.0, breakdown="badge +30 · regime +20")
    assert f.value == "▰▰▰▰▱ 82\nbadge +30 · regime +20"


def test_follow_field_without_a_breakdown_is_just_the_meter():
    assert c.follow_field(82.0).value == "▰▰▰▰▱ 82"


def test_fields_are_a_named_tuple_so_they_unpack_into_add_field():
    """Call sites do `embed.add_field(*field)`; a dict or a bare tuple
    would make that read as magic."""
    name, value, inline = c.confidence_field(3, 50)
    assert (name, value, inline) == ("Confidence", "Lv3 · 50", True)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_components.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'swingbot.core.presentation.components'`

- [ ] **Step 3: Write the implementation**

```python
# swingbot/core/presentation/components.py
"""
Whole embed PARTS -- a field, a headline, the chrome -- not values.

That distinction is the point of the package. A call site that wants a
confidence field asks for one; it does not assemble a name/value/inline
triple out of tokens and get the name or the inline flag subtly wrong. It is
what makes the kit hard to half-use, and half-use is exactly what produced
the 32 ad-hoc colour call sites v62 exists to remove.

Fields are returned rather than added, so a builder keeps control of ORDER
(see tokens.SECTION_ORDER) and can drop a field it has no data for.
"""
from typing import NamedTuple

from swingbot.core.presentation import ansi, tokens


class EmbedField(NamedTuple):
    """One embed field, shaped to unpack straight into add_field:

        embed.add_field(*components.confidence_field(level, score))
    """
    name: str
    value: str
    inline: bool


def plan_headline(
    *,
    direction: str,
    entry: float | None,
    target: float | None,
    stop: float | None,
    target_pct: float | None,
    stop_pct: float | None,
    r: float | None,
) -> str:
    """The fenced ansi headline for an alert's description. Raises if the
    result would scroll on a phone -- see ansi.block."""
    return ansi.block(ansi.plan_lines(
        direction=direction, entry=entry, target=target, stop=stop,
        target_pct=target_pct, stop_pct=stop_pct, r=r,
    ))


def confidence_field(level: int | None, score: float | None) -> EmbedField:
    """Inline, so it pairs with follow_field on one row instead of each
    taking a full-width row on a phone."""
    return EmbedField("Confidence", tokens.confidence_label(level, score), True)


def follow_field(score: float, breakdown: str | None = None) -> EmbedField:
    """The meter answers 'how strong', the optional breakdown answers
    'why'. One field with two lines rather than two fields -- a second
    field pushes the chart below the fold."""
    value = tokens.follow_meter(score)
    if breakdown:
        value = f"{value}\n{breakdown}"
    return EmbedField("Follow", value, True)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/components.py tests/presentation/test_components.py
git commit -m "feat(v62): headline, confidence and follow as embed parts"
```

---

### Task M6: The `⚠ Blocked by` field

**Files:**
- Modify: `swingbot/core/presentation/components.py` (append)
- Test: `tests/presentation/test_components.py` (append)

**Interfaces:**
- Consumes: `EmbedField` from M5.
- Produces: `blocked_by_field(unmet: list[tuple[str, str]]) -> EmbedField | None`.
  M13 (`alert_embeds.py`) is its caller.

**Why this exists:** today an unmet requirement is a red ANSI annotation
buried mid-table (`⚠ needs ≥ 5.0%`). "Is this worth acting on" is half of what
the first screenful must answer, so it becomes a field of its own (v62 D7).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/presentation/test_components.py

def test_blocked_by_lists_each_unmet_requirement_with_actual_and_required():
    """Naming only the parameter ('reward') tells you where to look;
    naming the gap tells you whether it is close."""
    f = c.blocked_by_field([("Reward", "3.1% — needs ≥ 5.0%"),
                            ("R:R", "1.4:1 — needs ≥ 2.0:1")])
    assert f.name == "⚠ Blocked by"
    assert f.value == ("Reward: 3.1% — needs ≥ 5.0%\n"
                       "R:R: 1.4:1 — needs ≥ 2.0:1")


def test_blocked_by_is_full_width_not_inline():
    """Two requirements at 30+ chars each cannot share a row on a phone."""
    assert c.blocked_by_field([("Reward", "x")]).inline is False


def test_blocked_by_is_none_when_everything_clears():
    """None, not an empty field. An empty '⚠ Blocked by' on a passing
    setup reads as a rendering fault, and the caller can simply skip a
    None rather than testing the value."""
    assert c.blocked_by_field([]) is None
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_components.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'blocked_by_field'`

- [ ] **Step 3: Append the implementation**

```python
# append to swingbot/core/presentation/components.py

def blocked_by_field(unmet: list[tuple[str, str]]) -> EmbedField | None:
    """The gates this setup did not clear, as (label, detail) pairs.

    `detail` carries actual AND required ("3.1% — needs ≥ 5.0%"), because
    naming only the parameter tells you where to look while naming the gap
    tells you whether it is close.

    Returns None rather than an empty field when everything clears: an
    empty '⚠ Blocked by' on a passing setup reads as a rendering fault,
    and a caller can skip a None without inspecting its value.

    Full width -- two requirements at 30+ characters each cannot share a
    row on a phone.
    """
    if not unmet:
        return None
    body = "\n".join(f"{label}: {detail}" for label, detail in unmet)
    return EmbedField("⚠ Blocked by", body, False)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/components.py tests/presentation/test_components.py
git commit -m "feat(v62): the Blocked-by field -- unmet gates get their own answer"
```

---

### Task M7: Chrome and section order

**Files:**
- Modify: `swingbot/core/presentation/components.py` (append)
- Modify: `swingbot/core/presentation/tokens.py` (append `SECTION_ORDER`, `DISCLAIMER`)
- Modify: `swingbot/core/presentation/__init__.py` (public surface)
- Test: `tests/presentation/test_components.py` (append)

**Interfaces:**
- Consumes: `tokens.accent_for_level`, `tokens.accent_for_outcome`.
- Produces: `apply_chrome(embed, *, accent, plan_id=None) -> None`,
  `tokens.SECTION_ORDER`, `tokens.DISCLAIMER`. Every builder in Parts 2–3
  ends with an `apply_chrome` call.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/presentation/test_components.py
import discord
from swingbot.core.presentation import tokens as t


def test_apply_chrome_sets_accent_footer_and_timestamp():
    e = discord.Embed(title="x")
    c.apply_chrome(e, accent=t.accent_for_level(5), plan_id="a4f19c2233445566")
    assert e.color.value == 0x17C98E
    assert e.timestamp is not None
    assert t.DISCLAIMER in e.footer.text
    assert "plan a4f19c22" in e.footer.text


def test_apply_chrome_without_a_plan_id_shows_the_disclaimer_alone():
    e = discord.Embed(title="x")
    c.apply_chrome(e, accent=t.accent_for_level(3))
    assert e.footer.text == t.DISCLAIMER


def test_apply_chrome_truncates_the_plan_id_to_eight_chars():
    """A full uuid in a footer is noise; eight characters is enough to
    find the plan in the admin and short enough to skim past."""
    e = discord.Embed(title="x")
    c.apply_chrome(e, accent=t.accent_for_level(1), plan_id="0123456789abcdef")
    assert "plan 01234567" in e.footer.text
    assert "89abcdef" not in e.footer.text


def test_apply_chrome_returns_none_so_call_sites_read_as_a_statement():
    e = discord.Embed(title="x")
    assert c.apply_chrome(e, accent=t.accent_for_level(5)) is None


def test_section_order_is_a_fixed_tuple_with_blocked_before_the_chart_fold():
    """Field order must not depend on the order the builder happened to
    compute things in. 'blocked' sits high because a failed gate is half
    of the first-screenful question."""
    assert t.SECTION_ORDER[:4] == ("headline", "plan", "blocked", "quality")
    assert isinstance(t.SECTION_ORDER, tuple)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_components.py -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'apply_chrome'`

- [ ] **Step 3: Append the implementations**

```python
# append to swingbot/core/presentation/tokens.py

DISCLAIMER = ("Technical signal only, based on today's still-developing daily "
              "candle -- not financial advice.")

#: Fixed rendering order for an alert's fields. A builder buckets each field
#: it wants into one of these named sections and flushes in this order,
#: regardless of the order it computed them in.
#:
#: 'blocked' sits third, above 'quality': a failed gate is half of the
#: "is this worth acting on" question the first screenful must answer, and
#: burying it is what v62 D7 exists to fix. Everything from 'changes' down
#: falls below the chart on a phone, which is deliberate.
SECTION_ORDER = (
    "headline", "plan", "blocked", "quality", "confluence",
    "changes", "branches", "track_record", "warnings",
)
```

```python
# append to swingbot/core/presentation/components.py
import discord


def apply_chrome(embed: discord.Embed, *, accent: discord.Color,
                 plan_id: str | None = None) -> None:
    """Accent bar, footer and timestamp -- the three things EVERY embed the
    bot sends must carry, in one call so a builder cannot forget one.

    Mutates in place and returns None, so a call site reads as a plain
    statement rather than needing to reassign.

    The plan id is truncated to eight characters: a full id in a footer is
    noise, and eight is enough to find it in the admin.
    """
    embed.color = accent
    embed.timestamp = discord.utils.utcnow()
    text = tokens.DISCLAIMER
    if plan_id:
        text = f"{tokens.DISCLAIMER} · plan {plan_id[:8]}"
    embed.set_footer(text=text)
```

```python
# append to swingbot/core/presentation/__init__.py
from swingbot.core.presentation.components import (   # noqa: F401
    EmbedField, apply_chrome, blocked_by_field, confidence_field,
    follow_field, plan_headline,
)
from swingbot.core.presentation.tokens import (       # noqa: F401
    ABSENT, ACCENT_BLOCKED, ACCENT_RAMP, DISCLAIMER, SECTION_ORDER,
    accent_for_level, accent_for_outcome, confidence_label, direction_glyph,
    fmt_pct, fmt_price, fmt_r, follow_meter,
)
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `python scripts/dev/testrun.py file tests/presentation/test_components.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/ tests/presentation/test_components.py
git commit -m "feat(v62): chrome, section order and the package's public surface"
```

---

# Phase 3 — Enforcement, deletions and docs

### Task M8: The AST guard test

**Files:**
- Create: `tests/presentation/test_no_adhoc_color.py`

**Interfaces:**
- Consumes: nothing at runtime — it reads source files.
- Produces: `GUARDED_PACKAGES: tuple[str, ...]`. **M20 and M28 widen this
  tuple**; nothing else in the plan touches this file.

**Why AST and not a regex.** A regex over the source would also match
`discord.Color` inside a string, a comment or a docstring — and this codebase
has many, several of them quoting the very call sites being removed (see
`embeds.py:757-759`). A regex-based guard would be permanently red or
permanently disabled. This is a requirement, not an implementation detail.

- [ ] **Step 1: Write the failing test**

```python
# tests/presentation/test_no_adhoc_color.py
"""
v62 C5: colour is defined in swingbot/core/presentation/ and nowhere else.

The shape of this test is precedented -- tests/test_env_example_sync.py also
asserts a structural invariant rather than a behaviour. The technique is not:
this is the first test in the repo to import `ast`, and that is deliberate.
A regex would also match `discord.Color` inside a docstring or a comment, of
which this codebase has several that quote the exact call sites being removed,
so a regex guard would be permanently red or quietly disabled.

GUARDED_PACKAGES widens as v62's parts land:
  Part 1 (M8)  -- core/presentation only, so this is green from the start
  Part 2 (M20) -- + core/scanning
  Part 3 (M28) -- + commands, which is then the whole surface
"""
import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Widened by M20 and M28. See the module docstring.
GUARDED_PACKAGES: tuple[str, ...] = (
    "swingbot/core/presentation",
)

ALLOWED = "swingbot/core/presentation"


def _guarded_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for pkg in GUARDED_PACKAGES:
        out.extend(sorted((REPO / pkg).rglob("*.py")))
    return out


def _colour_offences(tree: ast.AST) -> list[tuple[int, str]]:
    """Every `discord.Color`/`discord.Colour` attribute access, and every
    `color=`/`colour=` keyword on a `discord.Embed(...)` call."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("Color", "Colour"):
            if isinstance(node.value, ast.Name) and node.value.id == "discord":
                hits.append((node.lineno, f"discord.{node.attr}"))
        if isinstance(node, ast.Call):
            func = node.func
            is_embed = (
                (isinstance(func, ast.Attribute) and func.attr == "Embed")
                or (isinstance(func, ast.Name) and func.id == "Embed")
            )
            if is_embed:
                for kw in node.keywords:
                    if kw.arg in ("color", "colour"):
                        hits.append((node.lineno, f"Embed({kw.arg}=...)"))
    return hits


@pytest.mark.parametrize("path", _guarded_files(), ids=lambda p: p.name)
def test_no_adhoc_colour_outside_the_presentation_package(path):
    rel = path.relative_to(REPO).as_posix()
    if rel.startswith(ALLOWED):
        pytest.skip("the presentation package is where colour is allowed to live")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offences = _colour_offences(tree)
    assert not offences, (
        f"{rel} sets colour directly: "
        + ", ".join(f"line {n}: {what}" for n, what in offences)
        + ". Use swingbot.core.presentation (accent_for_level / "
          "accent_for_outcome / apply_chrome) instead -- v62 C5."
    )


def test_the_guard_actually_catches_an_offence():
    """Without this the guard could pass because the detector is broken
    rather than because the tree is clean -- the failure mode that makes a
    green suite meaningless."""
    tree = ast.parse("import discord\ne = discord.Embed(color=discord.Color.red())")
    assert _colour_offences(tree)


def test_the_guard_ignores_colour_named_in_a_docstring_or_comment():
    """The reason this is AST and not a regex. embeds.py:757-759 documents
    'Embed titles can't carry color' in prose, and several builders name
    discord.Color in comments explaining why they no longer use it."""
    tree = ast.parse('"""Embed titles cannot carry color."""\n# discord.Color.red()\n')
    assert not _colour_offences(tree)
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/presentation/test_no_adhoc_color.py -v`
Expected: FAIL — the file does not exist yet. After creating it, expected
result is PASS with every parametrised case **skipped** (the only guarded
package is the allowed one) plus the two detector tests passing. A guard that
is green because it inspects nothing is why
`test_the_guard_actually_catches_an_offence` exists.

- [ ] **Step 3: Confirm the detector is genuinely exercised**

Run:

```bash
python -m pytest tests/presentation/test_no_adhoc_color.py -v -k "actually_catches or ignores_colour"
```

Expected: 2 passed. These two are the tests that have real assertions in
Part 1; the parametrised ones start doing work at M20.

- [ ] **Step 4: Run the whole presentation test directory**

Run: `python scripts/dev/testrun.py file tests/presentation/`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/presentation/test_no_adhoc_color.py
git commit -m "test(v62): AST guard -- colour lives in core/presentation and nowhere else"
```

---

### Task M9: Dead-code deletions and the docs

**Files:**
- Modify: `swingbot/admin/helpers.py` — delete `_confidence_hex` (line 342),
  delete `_sources_str` (line 347), delete the `CONFIDENCE_COLORS` import (line 24)
- Modify: `CLAUDE.md` — the "`swingbot/core/` is ten packages" bullet
- Modify: `docs/claude/architecture.md` — the module map

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. This task removes.

**Verified during the v62 spec's research:** all three are unreferenced
anywhere in `swingbot/`, `tests/` or `scripts/`. They are Jinja-era leftovers
from the UI deleted 2026-08-14 (Release B). Removing the import also kills one
consumer of the accidental `engine.py → embeds.py` re-export chain that v61
Part 2 complains about.

- [ ] **Step 1: Re-verify they are still dead before deleting anything**

Run:

```bash
git grep -n "_confidence_hex" -- 'swingbot/**/*.py' 'tests/**/*.py' 'scripts/**/*.py'
git grep -n "_sources_str" -- 'swingbot/admin/**/*.py'
git grep -n "CONFIDENCE_COLORS" -- 'swingbot/admin/**/*.py'
```

Expected: the first returns only the definition at `swingbot/admin/helpers.py:342`.
The second returns only the definition at `helpers.py:347`. The third returns
only the import at `helpers.py:24` and the use inside `_confidence_hex`.

**If any returns a real caller, stop and do not delete it** — something landed
between the spec and this task, and the spec's claim needs correcting first.

- [ ] **Step 2: Delete all three**

Remove from `swingbot/admin/helpers.py`:

```python
from swingbot.core.scanning.engine import CONFIDENCE_COLORS   # line 24
```

```python
def _confidence_hex(level: int) -> str:                        # line 342
    r, g, b = CONFIDENCE_COLORS.get(level, (150, 150, 150))
    return f"#{r:02x}{g:02x}{b:02x}"


def _sources_str(sources) -> str:                              # line 347
    return ", ".join(dict.fromkeys(sources)) if sources else "n/a"
```

Leave `embeds.py`'s own `_sources_str` alone — that one is live.

- [ ] **Step 3: Run the admin tests**

Run: `python scripts/dev/testrun.py file tests/admin/`
Expected: `VERDICT: PASS`. A failure here means one of the three was not dead
after all; revert and re-check Step 1.

- [ ] **Step 4: Update the two docs**

In `CLAUDE.md`, the token-discipline bullet currently reads:

> **`swingbot/core/` is ten packages, no flat modules** — `marketdata/`,
> `market/`, `planning/`, `backtesting/`, `tracking/`, `infra/`, `edge/`,
> `scanning/`, `analytics/`, `charts/`.

Replace with:

> **`swingbot/core/` is eleven packages, no flat modules** — `marketdata/`,
> `market/`, `planning/`, `backtesting/`, `tracking/`, `infra/`, `edge/`,
> `scanning/`, `analytics/`, `charts/`, `presentation/`.

In `docs/claude/architecture.md`, add `presentation/` to the module map with
one line naming what it owns:

> `presentation/` — every colour, glyph, number format and embed part the bot
> sends to Discord. `tokens.py` (pure values) → `ansi.py` (the one place
> colour exists besides the accent bar, 32-char cap) → `components.py` (whole
> embed parts). Nothing outside this package may touch `discord.Color` —
> `tests/presentation/test_no_adhoc_color.py` asserts it by AST.

- [ ] **Step 5: Commit**

```bash
git add swingbot/admin/helpers.py CLAUDE.md docs/claude/architecture.md
git commit -m "refactor(v62): delete three Jinja-era dead helpers; document core/presentation"
```

---

## Part 1 exit check

Before merging this part's worktree:

```bash
python scripts/dev/testrun.py file tests/presentation/
python scripts/dev/testrun.py fast
git grep -n "core.presentation" -- 'swingbot/core/scanning/**/*.py' 'swingbot/commands/**/*.py'
```

The first two must be `VERDICT: PASS`. **The third must return nothing** —
if any builder imports the kit already, this part is no longer invisible and
the Part 2 boundary has leaked. That is the property that makes Part 1 safe to
merge on its own.

Part 2 begins at `_2-channels.md`.
