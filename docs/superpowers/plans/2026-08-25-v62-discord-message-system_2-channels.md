# v62 part 2 — the five automated channels

Index and global constraints C1–C9: `2026-08-25-v62-discord-message-system_0-index.md`.
Read that first. **This is the part where Discord starts looking different.**

Worktree: `2026-08-25-v62-discord-message-system_2-channels`.

**Before the first task, check C1:**

```bash
ls swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/lifecycle_embeds.py
```

Both must exist. If they do not, v61 has not merged and every path below is
wrong — stop.

---

# Phase 4 — The shared ramp

### Task M10: Flip `--quality-4` to the monotonic ramp

**Files:**
- Modify: `frontend/src/styles/tokens.css:104`
- Test: `frontend/src/app/ui/confidence-cell.spec.ts` (verify, update if it asserts the hex)

**Interfaces:**
- Consumes: `tokens.ACCENT_RAMP[4]` from M1 — the two must agree.
- Produces: nothing importable. This is the SPA half of one visual decision.

**Why now and not in Part 1.** Part 1 is invisible by construction. This task
is the first user-visible change in the plan, and it belongs beside the Discord
ramp flip so both surfaces change in one part rather than disagreeing for the
length of a merge.

> **Trap.** Change `--quality-4` **only**. Do not touch `--info`.
> `frontend/src/app/ui/chart-palette.spec.ts:72` asserts
> `token('--chart-2') === token('--info')`, so editing `--info` to reach the
> new ramp value would break the chart series namespace v54 just landed.
> `--quality-4` currently *references* `--info`; it becomes a literal.

- [ ] **Step 1: Confirm the current value and the assertion that constrains it**

Run:

```bash
sed -n '101,105p' frontend/src/styles/tokens.css
grep -n "chart-2\|--info" frontend/src/app/ui/chart-palette.spec.ts
```

Expected: `--quality-4: var(--info);` and an assertion tying `--chart-2` to
`--info`.

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/app/ui/confidence-cell.spec.ts — append inside the existing describe
it('bands level 4 on the monotonic ramp, not on --info blue', () => {
  // v62 D2. The accent bar is read at a glance and is often the only
  // signal, so the ramp must be ordinal: worse -> better. Blue at level 4
  // reads as "informational", not "nearly top". This value is the SAME
  // number as swingbot/core/presentation/tokens.py's ACCENT_RAMP[4] --
  // if the two drift, Discord and the dashboard disagree about what a
  // level-4 plan looks like, which is the bug v62 exists to remove.
  const root = getComputedStyle(document.documentElement);
  expect(root.getPropertyValue('--quality-4').trim().toLowerCase())
    .toBe('#9acd32');
});

it('leaves --info alone', () => {
  // chart-palette.spec.ts asserts --chart-2 === --info. Reaching the new
  // ramp value by editing --info instead of --quality-4 would break the
  // chart series namespace.
  const root = getComputedStyle(document.documentElement);
  expect(root.getPropertyValue('--info').trim().toLowerCase()).toBe('#46c2ff');
});
```

- [ ] **Step 3: Run it to make sure it fails**

Run: `cd frontend && npx ng test --watch=false`
Expected: FAIL — `--quality-4` resolves to `#46c2ff`, not `#9acd32`.

- [ ] **Step 4: Make the change**

In `frontend/src/styles/tokens.css`, replace line 104:

```css
  --quality-4: var(--info);
```

with:

```css
  /* v62 D2: yellow-green, not --info blue. The quality ramp is ORDINAL --
     it is rendered as a 4px accent bar in Discord where it is often the
     only signal, and a categorical hue at level 4 reads as "informational"
     rather than "nearly top". Kept in lockstep with ACCENT_RAMP[4] in
     swingbot/core/presentation/tokens.py; changing one without the other
     makes the dashboard and Discord disagree about a level-4 plan.
     A literal, not var(--info): --chart-2 is asserted equal to --info
     (chart-palette.spec.ts), so --info itself must not move. */
  --quality-4: #9acd32;
```

- [ ] **Step 5: Run the frontend suite and commit**

Run: `cd frontend && npx ng test --watch=false`
Expected: all files passed. `chart-palette.spec.ts` must still be green.

```bash
git add frontend/src/styles/tokens.css frontend/src/app/ui/confidence-cell.spec.ts
git commit -m "feat(v62): quality ramp goes monotonic -- level 4 is yellow-green, not info blue"
```

---

# Phase 5 — The alert

### Task M11: The alert headline replaces the wide table

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` — `build_embed`
- Test: `tests/scanning/test_embeds_v3.py`

**Interfaces:**
- Consumes: `components.plan_headline`, `tokens.SECTION_ORDER`,
  `plan_table.plan_numbers_for_display`.
- Produces: nothing new. It changes what `build_embed` puts in
  `embed.description`.

**What changes.** `embed.description` currently holds the free-text
`explanation`, and the plan lives in a ~15-row ANSI table built by
`_build_trade_plan_table`. After this task the description leads with the
two-line ANSI headline; the explanation follows it; the wide table is gone.

> `plan_numbers_for_display` stays the source of every price. It is, per
> `architecture.md`, THE cutover switch deciding whether alerts show legacy
> scenario numbers or v2 plan numbers. Do not read `plan.entry` directly.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_embeds_v3.py
from swingbot.core.presentation import ansi


def test_alert_description_leads_with_the_ansi_plan_headline(alert_item):
    """v62 D4. The trade is the first thing on the first screenful."""
    embed = build_embed(alert_item, "some explanation", None, None, None)
    assert embed.description.startswith("```ansi\n")


def test_alert_headline_carries_entry_target_stop_in_the_spa_form(alert_item):
    embed = build_embed(alert_item, "some explanation", None, None, None)
    plain = ansi._ESCAPE_RE.sub("", embed.description)
    assert "→" in plain and "/" in plain


def test_the_explanation_survives_below_the_headline(alert_item):
    """The headline replaces the TABLE, not the prose -- the explanation is
    the only thing saying why the level is there."""
    embed = build_embed(alert_item, "some explanation", None, None, None)
    assert "some explanation" in embed.description


def test_the_wide_plan_table_is_gone(alert_item):
    """The 65-70 char rows that scrolled sideways on a phone. If this
    fails, _build_trade_plan_table is still being called somewhere."""
    embed = build_embed(alert_item, "x", None, None, None)
    for line in embed.description.splitlines():
        assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH or not line.startswith(" ")


def test_no_description_line_scrolls_on_a_phone(alert_item):
    """C3, asserted on the real builder rather than only on ansi.block."""
    embed = build_embed(alert_item, "x", None, None, None)
    inside_block = False
    for line in embed.description.splitlines():
        if line.startswith("```"):
            inside_block = not inside_block
            continue
        if inside_block:
            assert ansi.visible_width(line) <= ansi.MAX_LINE_WIDTH, line
```

Use whatever fixture `test_embeds_v3.py` already builds its items from — read
the top of that file first and reuse it rather than inventing `alert_item`.

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/scanning/test_embeds_v3.py -v -k "headline or wide_plan_table"`
Expected: FAIL — the description starts with the explanation, not a fence.

- [ ] **Step 3: Rewrite the description assembly in `build_embed`**

```python
from swingbot.core import presentation as ui
from swingbot.core.scanning.plan_table import plan_numbers_for_display

    # v62 D4: the plan IS the headline. Two ansi lines, <=32 visible chars
    # each, so it cannot scroll sideways on a phone -- which is exactly what
    # the ~15-row table this replaces did (65-70 char rows, and a Discord
    # code block does not wrap).
    #
    # plan_numbers_for_display is the cutover funnel (architecture.md): it
    # decides legacy-vs-v2 pricing for every surface at once. Reading
    # plan.entry directly here would let this embed quote a different number
    # from the simple-alert mirror.
    nums = plan_numbers_for_display(plan_v2, {
        "entry": plan.entry, "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit, "target2": plan.target2_price})

    headline = ui.plan_headline(
        direction=result.trend,
        entry=nums["entry"],
        target=nums["take_profit"],
        stop=nums["stop_loss"],
        target_pct=plan.target_distance_pct,
        # Always negative. stop_distance_pct is stored as a magnitude, and a
        # stop sits on the losing side of entry by construction -- for a
        # SHORT as much as for a long, since the sign is about P&L, not about
        # which way the price moves.
        stop_pct=-abs(plan.stop_distance_pct),
        r=plan.risk_reward_ratio,
    )
    embed.description = f"{headline}{explanation[:3500]}"
```

Delete the `_build_trade_plan_table(item)` call and the field it was added as.
`explanation` is truncated to 3500 rather than 4000: the headline block costs
roughly 120 characters and `embed.description` caps at 4096.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: `VERDICT: PASS`. Several existing tests in this file assert the old
table's rows; delete those assertions — they describe a layout that no longer
exists, and the tests above replace them.

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/alert_embeds.py tests/scanning/test_embeds_v3.py
git commit -m "feat(v62): the alert leads with a phone-width plan headline"
```

---

### Task M12: Confidence and follow fields; badge and emoji vocabularies removed

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` — `build_embed`
- Test: `tests/scanning/test_embeds_badges.py`

**Interfaces:**
- Consumes: `components.confidence_field`, `components.follow_field`,
  `tokens.accent_for_level`.
- Produces: nothing new.

**What changes.** The `🧭 Follow score` field and the quality line become kit
components. `theme.level_chip`, `theme.badge_chip` and `theme.plan_color` calls
go. The accent comes from confidence level alone (D6).

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_embeds_badges.py

def _field(embed, name):
    return next((f for f in embed.fields if f.name == name), None)


def test_confidence_field_reads_level_and_score(alert_item):
    embed = build_embed(alert_item, "x", None, None, None)
    assert _field(embed, "Confidence").value.startswith("Lv")
    assert " · " in _field(embed, "Confidence").value


def test_follow_field_is_the_meter(alert_item):
    embed = build_embed(alert_item, "x", None, None, None)
    value = _field(embed, "Follow").value
    assert value[0] in "▰▱"


def test_the_badge_is_not_rendered_anywhere(alert_item):
    """v62 D6, and its recorded consequence: WEAK is invisible in Discord.
    It survives in the admin and the trade record only. If this test ever
    fails because someone re-added the chip, read D6 before 'fixing' it."""
    embed = build_embed(alert_item, "x", None, None, None)
    blob = f"{embed.title}{embed.description}" + "".join(
        f"{f.name}{f.value}" for f in embed.fields)
    assert "VALIDATED" not in blob
    assert "WEAK" not in blob


def test_a_weak_plan_gets_its_levels_colour_not_amber(weak_alert_item):
    """The other half of D6. plan_color used to force amber for WEAK at any
    level; with the badge no longer rendered, that amber would have had no
    visible cause."""
    embed = build_embed(weak_alert_item, "x", None, None, None)
    assert embed.color.value != 0xE67E22


def test_the_level_digit_emoji_are_gone(alert_item):
    """_LEVEL_CHIPS (1..5 as keycap emoji) and CONFIDENCE_EMOJI (coloured
    circles) are both deleted -- v62 D5. Two emoji vocabularies for one
    value was half the inconsistency."""
    embed = build_embed(alert_item, "x", None, None, None)
    blob = f"{embed.title}{embed.description}" + "".join(
        f"{f.name}{f.value}" for f in embed.fields)
    for chip in ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "🔴", "🟠", "🟡", "🟢"):
        assert chip not in blob
```

Add a `weak_alert_item` fixture beside the existing one, identical except
`badge="WEAK"`.

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/scanning/test_embeds_badges.py -v`
Expected: FAIL — the badge chip is still in the headline prefix.

- [ ] **Step 3: Replace the field assembly**

```python
    # v62 D6: the accent is the confidence LEVEL and nothing else. It used
    # to be theme.plan_color(badge, level), which forced amber for a WEAK
    # badge at any level; with the badge no longer rendered (D6) that amber
    # would have been an off-colour alert with no visible cause.
    embed.color = ui.accent_for_level(conf.level)

    sections["quality"].append(ui.confidence_field(conf.level, conf.score))
    if plan_v2 is not None:
        today = datetime.now(timezone.utc).date()
        score = follow_score(plan_v2, today=today)
        breakdown = " · ".join(
            f"{label} +{pts:.0f}" if "quality" not in label else label
            for label, pts in follow_breakdown(plan_v2, today)
        )
        sections["quality"].append(ui.follow_field(score, breakdown))
```

Delete the `chip_prefix` line (the `level_chip`/`badge_chip` pair) and the
`quality_line` that names the badge.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/alert_embeds.py tests/scanning/test_embeds_badges.py
git commit -m "feat(v62): confidence and follow as kit fields; badge and emoji chips removed"
```

---

### Task M13: `⚠ Blocked by`, and the fail accent

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` — `build_embed`
- Test: `tests/scanning/test_embeds_v3.py`

**Interfaces:**
- Consumes: `components.blocked_by_field`, `tokens.ACCENT_BLOCKED`,
  `requirements.RequirementCheck` (v61's module).
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_embeds_v3.py

def test_an_unmet_requirement_gets_its_own_field(blocked_alert_item):
    """v62 D7. It used to be a red annotation buried mid-table; 'is this
    worth acting on' is half the first-screenful question."""
    embed = build_embed(blocked_alert_item, "x", None, None, None)
    field = next(f for f in embed.fields if f.name == "⚠ Blocked by")
    assert "needs" in field.value


def test_a_blocked_alert_takes_the_inert_accent_not_red(blocked_alert_item):
    """Grey, not red: it never opened, so it is inert rather than a loss.
    C2 -- red means a bad OUTCOME."""
    from swingbot.core.presentation import tokens
    embed = build_embed(blocked_alert_item, "x", None, None, None)
    assert embed.color.value == tokens.ACCENT_BLOCKED


def test_a_clean_alert_has_no_blocked_field(alert_item):
    embed = build_embed(alert_item, "x", None, None, None)
    assert all(f.name != "⚠ Blocked by" for f in embed.fields)


def test_blocked_by_sits_above_the_quality_fields(blocked_alert_item):
    """SECTION_ORDER puts 'blocked' third. Below 'quality' it would fall
    under the chart on a phone, which is where it was."""
    embed = build_embed(blocked_alert_item, "x", None, None, None)
    names = [f.name for f in embed.fields]
    assert names.index("⚠ Blocked by") < names.index("Confidence")
```

Add a `blocked_alert_item` fixture whose requirement checks include at least
one unmet entry.

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/scanning/test_embeds_v3.py -v -k blocked`
Expected: FAIL — no field named `⚠ Blocked by`.

- [ ] **Step 3: Wire it in**

```python
    # v62 D7. requirements._build_requirement_checks already computes both
    # the actual value and the configured threshold for every gate; this
    # surfaces the failures as one field instead of annotating rows of a
    # table nobody can read on a phone.
    unmet = [(r.label, r.detail) for r in item.requirements if not r.ok]
    blocked = ui.blocked_by_field(unmet)
    if blocked is not None:
        sections["blocked"].append(blocked)
        embed.color = ui.accent_blocked()
```

C5 forbids constructing a `discord.Color` here, so the accent comes from the
kit. Add `accent_blocked()` to `tokens.py` beside `ACCENT_BLOCKED`:

```python
def accent_blocked() -> discord.Color:
    """The accent for a setup that failed a configured gate. Grey, not red:
    it never opened, so it is inert rather than a loss (C2)."""
    return discord.Color(ACCENT_BLOCKED)
```

Export it from `__init__.py` alongside the others.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/presentation/ swingbot/core/scanning/alert_embeds.py tests/scanning/test_embeds_v3.py
git commit -m "feat(v62): unmet gates get a Blocked-by field and the inert accent"
```

---

### Task M14: `build_simple_alert` onto the kit

**Files:**
- Modify: `swingbot/core/scanning/alert_embeds.py` — `build_simple_alert`
- Test: `tests/scanning/test_simple_alerts.py`

**Interfaces:**
- Consumes: `components.plan_headline`, `tokens.accent_for_level`,
  `tokens.confidence_label`.
- Produces: nothing new.

**The one behaviour change to be deliberate about.** This builder's accent is
currently green-LONG / red-SHORT — the exception `embeds.py` documents in its
own docstring. C2 removes it: the accent becomes the confidence ramp, and
direction survives as the `▲`/`▼` already in the title and the ANSI block.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_simple_alerts.py
from swingbot.core.presentation import tokens


def test_the_accent_is_confidence_not_direction(simple_item):
    """v62 C2 removes the documented 'one exception'. A long and a short at
    the same confidence level now share an accent -- direction is carried by
    the triangle, which is a channel colour-blind readers also get."""
    embed = build_simple_alert(simple_item)
    assert embed.color.value == tokens.ACCENT_RAMP[simple_item.conf.level]


def test_a_short_at_the_same_level_gets_the_same_accent(simple_item, short_simple_item):
    assert build_simple_alert(simple_item).color.value == \
           build_simple_alert(short_simple_item).color.value


def test_the_title_still_names_direction_in_plain_text(simple_item):
    """C4. A push notification strips the embed to its title, so the title
    cannot rely on the accent or the ansi block to say long/short."""
    embed = build_simple_alert(simple_item)
    assert "LONG" in embed.title
    assert embed.title.startswith("▲")


def test_confidence_reads_lv_and_score(simple_item):
    embed = build_simple_alert(simple_item)
    assert tokens.confidence_label(simple_item.conf.level,
                                   simple_item.conf.score) in embed.description


def test_there_is_still_no_chart(simple_item):
    """The point of this channel: it stays readable on a phone and costs no
    render time."""
    assert build_simple_alert(simple_item).image.url is None
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/scanning/test_simple_alerts.py -v -k accent`
Expected: FAIL — the accent is `discord.Color.green()`, not the ramp.

- [ ] **Step 3: Rewrite the builder's colour and confidence line**

```python
    # v62 C2: the accent answers "how good", never "which way". This
    # builder used to be the documented exception -- green LONG / red
    # SHORT -- and it is the exception no longer. Direction survives as
    # the triangle in the title (C4: notifications strip to the title)
    # and in the ansi block below.
    embed = discord.Embed(
        title=f"{arrow} {direction} — {result.ticker}",
        description=(
            f"{ui.plan_headline(...)}"
            f"Confidence: {ui.confidence_label(conf.level, conf.score)}\n"
            f"Horizon: {result.horizon_label}\n"
            f"Setup: {setup}\n\n"
            f"{plan_line}"
        ),
    )
    ui.apply_chrome(embed, accent=ui.accent_for_level(conf.level),
                    plan_id=plan_v2.plan_id if plan_v2 else None)
```

The inline `direction_block` (the hand-built ` ```ansi ` fence) is replaced by
`ui.plan_headline(...)` — that inline pattern is what `ansi.py` was extracted
from, and leaving both would be two implementations of one idea.

Keep the 🎯/💰/🛑 labels on `plan_line`: they pass C6's test, because they
disambiguate four numbers on one line.

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_simple_alerts.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/alert_embeds.py tests/scanning/test_simple_alerts.py
git commit -m "feat(v62): simple-alerts joins the colour rule -- accent is confidence, not direction"
```

---

# Phase 6 — Lifecycle and cleanup

### Task M15: `build_closed_trade_embed`

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py`
- Test: `tests/tracking/test_closed_pnl_pct.py`, `tests/scanning/test_embeds_v3.py`

**Interfaces:**
- Consumes: `tokens.accent_for_outcome`, `components.plan_headline`,
  `components.apply_chrome`, `tokens.fmt_pct`, `tokens.fmt_r`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_embeds_v3.py
from swingbot.core.presentation import tokens as tk


def test_a_win_takes_the_ramps_green(win_trade):
    assert build_closed_trade_embed(win_trade).color.value == tk.ACCENT_RAMP[5]


def test_a_loss_takes_the_ramps_red(loss_trade):
    assert build_closed_trade_embed(loss_trade).color.value == tk.ACCENT_RAMP[1]


def test_a_scratch_takes_the_ramps_grey(scratch_trade):
    """A break-even close is neither. Grey is the ramp's own neutral, not
    a fourth colour invented for this one case."""
    assert build_closed_trade_embed(scratch_trade).color.value == tk.ACCENT_RAMP[3]


def test_the_headline_shows_entry_to_exit_not_entry_to_target(win_trade):
    """A closed trade has an exit. Showing the target it was AIMED at
    would be describing a plan that no longer applies."""
    embed = build_closed_trade_embed(win_trade)
    plain = ansi._ESCAPE_RE.sub("", embed.description)
    assert tk.fmt_price(win_trade["exit_price"]) in plain


def test_realised_percent_and_r_are_both_present(win_trade):
    embed = build_closed_trade_embed(win_trade)
    plain = ansi._ESCAPE_RE.sub("", embed.description)
    assert "%" in plain and "R" in plain
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/scanning/test_embeds_v3.py -v -k "win_trade or loss_trade or scratch"`
Expected: FAIL — colours come from `discord.Color.green()` / `.red()` /
`from_rgb(90, 98, 117)`, none of which equal the ramp.

- [ ] **Step 3: Replace the colour block and the headline**

```python
    # v62 C2: the same three colours the alert ramp uses at its ends, so
    # green means the same thing on this channel as on that one. The old
    # from_rgb(90, 98, 117) grey was a fourth colour invented for scratch.
    outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "scratch"

    embed.description = ui.plan_headline(
        direction=trade.get("direction", ""),
        entry=trade.get("entry"),
        target=trade.get("exit_price"),      # where it actually went
        stop=trade.get("stop_loss"),
        target_pct=trade.get("pnl_pct"),
        stop_pct=None,
        r=trade.get("r_multiple"),
    )
    ui.apply_chrome(embed, accent=ui.accent_for_outcome(outcome),
                    plan_id=trade.get("plan_id"))
```

- [ ] **Step 4: Run the tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_v3.py`
Expected: `VERDICT: PASS`

- [ ] **Step 5: Commit**

```bash
git add swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_embeds_v3.py
git commit -m "feat(v62): closed-trade embeds share the ramp's outcome colours"
```

---

### Task M16: `build_near_close_embed`

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py`
- Test: `tests/tracking/test_near_tp_bypass.py`

**Interfaces:**
- Consumes: `tokens.accent_for_outcome`, `components.apply_chrome`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/tracking/test_near_tp_bypass.py
from swingbot.core.presentation import tokens as tk
from swingbot.core.scanning.lifecycle_embeds import build_near_close_embed


def test_near_stop_warns_in_the_ramps_red(near_sl_warning):
    """Approaching a stop is bad news about a LIVE position, which is the
    'bad' half of C2 -- same red as a realised loss."""
    assert build_near_close_embed(near_sl_warning).color.value == tk.ACCENT_RAMP[1]


def test_near_target_uses_the_ramps_green(near_tp_warning):
    assert build_near_close_embed(near_tp_warning).color.value == tk.ACCENT_RAMP[5]


def test_the_title_says_which_without_relying_on_colour(near_sl_warning):
    """C4 -- a push notification is title-only, and C2's accessibility
    half means colour is never the sole channel."""
    title = build_near_close_embed(near_sl_warning).title
    assert "stop" in title.lower()
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/tracking/test_near_tp_bypass.py -v -k ramp`
Expected: FAIL — `discord.Color.red()` is `0xE74C3C`, not `ACCENT_RAMP[1]`.

- [ ] **Step 3: Replace the colour choice**

```python
    # v62 C2. Approaching a stop is bad news about a live position; the
    # same red a realised loss gets, because green/red must mean one thing.
    accent = ui.accent_for_outcome("loss" if is_sl else "win")
    ui.apply_chrome(embed, accent=accent, plan_id=t.get("plan_id"))
```

- [ ] **Step 4: Run the tests and commit**

Run: `python scripts/dev/testrun.py file tests/tracking/test_near_tp_bypass.py`
Expected: `VERDICT: PASS`

```bash
git add swingbot/core/scanning/lifecycle_embeds.py tests/tracking/test_near_tp_bypass.py
git commit -m "feat(v62): near-close warnings take the shared outcome colours"
```

---

### Task M17: `PLAN_EVENT_STYLES` and `build_plan_event_embed`

**Files:**
- Modify: `swingbot/core/scanning/lifecycle_embeds.py`
- Test: `tests/scanning/test_transition_embeds.py`

**Interfaces:**
- Consumes: `tokens.accent_for_outcome`, `tokens.ACCENT_RAMP`,
  `components.apply_chrome`.
- Produces: nothing new.

**What changes.** `PLAN_EVENT_STYLES` currently maps ten events to eight
different `discord.Color` constants — blue, dark_grey, dark_red, teal, gold,
red, light_grey, green. Eight hues for one axis is the inconsistency in
miniature. Each event maps to one of the ramp's three outcome colours plus
the inert grey.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/scanning/test_transition_embeds.py
from swingbot.core.presentation import tokens as tk
from swingbot.core.scanning.lifecycle_embeds import PLAN_EVENT_STYLES

_ALLOWED = {tk.ACCENT_RAMP[1], tk.ACCENT_RAMP[3], tk.ACCENT_RAMP[5], tk.ACCENT_BLOCKED}


def test_every_plan_event_uses_a_ramp_colour():
    """Eight hues (blue, teal, gold, dark_red, light_grey, ...) for one
    axis is the inconsistency v62 removes. Four colours, each meaning the
    same thing it means everywhere else."""
    for key, (_title, colour) in PLAN_EVENT_STYLES.items():
        assert colour.value in _ALLOWED, f"{key} uses an off-ramp colour"


def test_good_events_are_green_and_bad_events_are_red():
    assert PLAN_EVENT_STYLES["tp1_partial"][1].value == tk.ACCENT_RAMP[5]
    assert PLAN_EVENT_STYLES["tp1_runner_tp2"][1].value == tk.ACCENT_RAMP[5]
    assert PLAN_EVENT_STYLES["loss"][1].value == tk.ACCENT_RAMP[1]


def test_neutral_events_are_grey_not_a_hue_of_their_own():
    """'filled' and 'be_moved' are progress, not verdicts -- blue and teal
    said 'a different KIND of thing', which is not what the bar means."""
    for key in ("filled", "be_moved", "scratch", "cancelled_expired",
                "cancelled_invalidated"):
        assert PLAN_EVENT_STYLES[key][1].value in (tk.ACCENT_RAMP[3], tk.ACCENT_BLOCKED)


def test_the_event_emoji_survive_because_they_are_labels():
    """C6: at most one per line, and only where it is the fastest label.
    A lifecycle title is exactly that case -- the glyph IS the category."""
    assert PLAN_EVENT_STYLES["tp1_partial"][0].startswith("💰")
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/scanning/test_transition_embeds.py -v`
Expected: FAIL — `filled` is `discord.Color.blue()`.

- [ ] **Step 3: Remap the table**

```python
from swingbot.core.presentation import tokens as _tk

# v62 C2: four colours, not eight. Progress events (filled, be_moved) are
# grey because they are not verdicts -- the old blue/teal said "a different
# KIND of thing", which is not what an ordinal bar means. Cancelled and
# expired take the inert grey for the same reason a blocked alert does:
# nothing was lost, the plan simply never ran.
_GOOD = _tk.accent_for_outcome("win")
_BAD = _tk.accent_for_outcome("loss")
_NEUTRAL = _tk.accent_for_outcome("scratch")
_INERT = _tk.accent_blocked()

PLAN_EVENT_STYLES = {
    "filled":                ("🎯 ENTRY TRIGGERED — {ticker}", _NEUTRAL),
    "cancelled_expired":     ("⏱ Plan expired — {ticker}", _INERT),
    "cancelled_invalidated": ("❌ Plan invalidated — {ticker}", _INERT),
    "be_moved":              ("🛡 Stop moved to break-even — {ticker}", _NEUTRAL),
    "tp1_partial":           ("💰 TP1 banked — {ticker}", _GOOD),
    "loss":                  ("🔴 Stopped out — {ticker}", _BAD),
    "scratch":               ("⚪ Scratched at break-even — {ticker}", _NEUTRAL),
    "tp1_runner_be":         ("🟢 Win — runner closed at its floor — {ticker}", _GOOD),
    "tp1_runner_tp2":        ("🟢🟢 Win — runner hit TP2 — {ticker}", _GOOD),
    "tp1_runner_trail":      ("🟢 Win — trail locked profit — {ticker}", _GOOD),
}
```

> C6 note: `tp1_runner_tp2`'s double 🟢🟢 is two emoji on one line. Reduce it
> to one — the title already says "hit TP2", so the second glyph is
> decoration, which C6 forbids.

- [ ] **Step 4: Run the tests and commit**

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Expected: `VERDICT: PASS`

```bash
git add swingbot/core/scanning/lifecycle_embeds.py tests/scanning/test_transition_embeds.py
git commit -m "feat(v62): plan-event styles collapse from eight hues to the ramp's four"
```

---

### Task M18: The retrospective adopts the formatters only

**Files:**
- Modify: `swingbot/core/tracking/retrospective.py`
- Test: `tests/scanning/test_embeds_v3.py` is **not** the right file — use
  the retrospective's own tests; find them with
  `git grep -l "build_daily_retrospective" -- tests/`

**Interfaces:**
- Consumes: `tokens.fmt_price`, `tokens.fmt_pct`, `tokens.fmt_r`,
  `tokens.direction_glyph`.
- Produces: nothing new.

> **This channel has no embed.** `build_daily_retrospective` returns
> `list[str]` — plain-text chunks posted by `commands/scanning.py:1160`. It is
> chunked because a day's recap exceeds Discord's per-message limit, and an
> embed description caps at 4096 characters, so converting it is a redesign of
> what the retrospective *is*. **Out of scope for v62** — see the spec's
> "Correction: the retrospective has no embed". This task changes number
> formatting and glyphs only, so the recap agrees with every other channel
> about what `−6.0%` and `▲` look like.

- [ ] **Step 1: Find every hand-rolled number format in the module**

Run:

```bash
grep -nE ':\.[0-9]f|\{[a-z_]+:\+?\.[0-9]f\}|"▲"|"▼"' swingbot/core/tracking/retrospective.py
```

Every hit is a candidate. A price becomes `tokens.fmt_price`, a percentage
`tokens.fmt_pct`, an R-multiple `tokens.fmt_r`, a direction arrow
`tokens.direction_glyph`.

- [ ] **Step 2: Write the failing test**

```python
def test_the_recap_uses_the_shared_minus_sign(sample_trades):
    """U+2212, not a hyphen -- so a losing figure in the recap looks
    identical to the same figure in an alert. The two used to differ."""
    body = "\n".join(build_daily_retrospective(sample_trades))
    assert "−" in body


def test_the_recap_signs_its_percentages(sample_trades):
    body = "\n".join(build_daily_retrospective(sample_trades))
    assert "+" in body


def test_the_recap_is_still_plain_text_chunks(sample_trades):
    """Not an embed, deliberately -- see the spec's correction note. A day's
    recap exceeds an embed description's 4096-char cap."""
    out = build_daily_retrospective(sample_trades)
    assert isinstance(out, list)
    assert all(isinstance(chunk, str) for chunk in out)
```

- [ ] **Step 3: Run it to make sure it fails, then substitute the formatters**

Run: `python -m pytest <the retrospective test file> -v`

Replace each hand-rolled format found in Step 1 with the kit call. Do not
change what the recap says or how it chunks.

- [ ] **Step 4: Run the tests and commit**

Run: `python scripts/dev/testrun.py file <the retrospective test file>`
Expected: `VERDICT: PASS`

```bash
git add swingbot/core/tracking/retrospective.py <the test file>
git commit -m "feat(v62): the daily recap formats its numbers through the kit"
```

---

### Task M19: Retire the wide plan table

**Files:**
- Modify: `swingbot/core/scanning/plan_table.py` — delete
  `_build_trade_plan_table` and `_ansi_bad`
- Test: `tests/scanning/test_embeds_v3.py`

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. `plan_numbers_for_display`, `badge_field_for`,
  `quality_lines`, `entry_line`, `leg_rows` and `_v2_plan` **all stay** —
  only the wide table and its red-annotation helper go.

> v61 created this module around `_build_trade_plan_table` and this task guts
> it. That is expected, not an accident: v61 is a move-only refactor and v62 is
> the content change that follows. The module keeps its name because
> `plan_numbers_for_display` — the legacy/v2 cutover switch — still lives here
> and is what `architecture.md` points at.

- [ ] **Step 1: Prove nothing still calls them**

Run:

```bash
git grep -n "_build_trade_plan_table\|_ansi_bad" -- 'swingbot/**/*.py' 'tests/**/*.py'
```

Expected: definitions only. M11 removed the one production call. **If a caller
remains, do M11 first** — deleting now leaves an import error.

- [ ] **Step 2: Delete both functions**

Remove `_build_trade_plan_table` (and its ~120 lines of row assembly) and
`_ansi_bad`. Leave the module docstring, and add one line to it:

```python
# The wide key:value table this module was named for was retired in v62:
# its rows ran 65-70 characters and a Discord code block does not wrap, so
# on a phone the values sat off-screen behind a horizontal scroll. The
# replacement is components.plan_headline -- two lines, 32 chars.
# plan_numbers_for_display stays and is still THE legacy-vs-v2 cutover
# switch every consumer of plan prices must route through (architecture.md).
```

- [ ] **Step 3: Run the scanning tests**

Run: `python scripts/dev/testrun.py file tests/scanning/`
Expected: `VERDICT: PASS`

- [ ] **Step 4: Commit**

```bash
git add swingbot/core/scanning/plan_table.py
git commit -m "refactor(v62): retire the wide plan table -- a code block does not wrap"
```

---

### Task M20: Delete `embed_theme.py` and widen the guard

**Files:**
- Delete: `swingbot/core/scanning/embed_theme.py`
- Delete: `tests/scanning/test_embed_theme.py` (its rules now live in
  `tests/presentation/test_tokens.py`)
- Modify: `tests/presentation/test_no_adhoc_color.py` — `GUARDED_PACKAGES`

**Interfaces:**
- Consumes: nothing.
- Produces: `GUARDED_PACKAGES` gains `swingbot/core/scanning`.

- [ ] **Step 1: Prove every call site has migrated**

Run:

```bash
git grep -n "embed_theme" -- 'swingbot/**/*.py' 'tests/**/*.py'
```

Expected: only the module itself and its own test. **Any other hit means a
builder was missed** — migrate it before continuing rather than deleting the
module out from under it.

- [ ] **Step 2: Widen the guard and watch it fail**

In `tests/presentation/test_no_adhoc_color.py`:

```python
GUARDED_PACKAGES: tuple[str, ...] = (
    "swingbot/core/presentation",
    "swingbot/core/scanning",      # v62 Part 2 (M20)
)
```

Run: `python -m pytest tests/presentation/test_no_adhoc_color.py -v`

Expected: **it may fail**, and that is the point — every failure names a file
and line where colour is still set directly. Fix each by routing through
`ui.accent_for_level` / `ui.accent_for_outcome` / `ui.apply_chrome`. Do not
widen the `ALLOWED` prefix to silence it.

- [ ] **Step 3: Delete the module and its test**

```bash
git rm swingbot/core/scanning/embed_theme.py tests/scanning/test_embed_theme.py
```

- [ ] **Step 4: Run the full scanning and presentation suites**

Run:

```bash
python scripts/dev/testrun.py file tests/presentation/
python scripts/dev/testrun.py file tests/scanning/
```

Expected: `VERDICT: PASS` for both.

- [ ] **Step 5: Commit**

```bash
git add -A swingbot/core/scanning tests/presentation tests/scanning
git commit -m "refactor(v62): delete embed_theme.py; guard now covers core/scanning"
```

---

## Part 2 exit check

```bash
python scripts/dev/testrun.py fast
git grep -n "embed_theme\|CONFIDENCE_COLORS\|CONFIDENCE_EMOJI\|plan_color" -- 'swingbot/**/*.py'
```

`fast` must be `VERDICT: PASS`, and the grep must return **nothing** — every
symbol in the index's "Deleted vocabulary" table is gone from the tree.

Part 3 begins at `_3-commands.md`.
