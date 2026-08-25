# v62 — The Discord message system

Version: ui 1.8.5 · bot 1.4.3
Bump: bot minor (1.4.3 → 1.5.0)
Edge: none (integrity)

## What this is

One presentation kit, `swingbot/core/presentation/`, that owns every colour,
glyph, number format and embed part the bot sends to Discord — and an AST
guard test that makes bypassing it a test failure rather than a habit.

Every channel and every command adopts it: the five automated channels
(alerts, simple-alerts, closed-trades, retrospective, firehose) and the
~12 `swingbot/commands/*` modules.

`Bump:` is a **minor** because every message the bot sends changes shape.
`working-conventions.md`'s test for a minor is "someone who used this
yesterday has to look at it anew", and that is exactly what this does. It is
not a minor because the diff is large.

`Edge:` is `none (integrity)` and the spec will not dress that up. It buys no
discriminator and harvests no R. What it does buy is stated in the next
section, and one part of it is closer to a correctness fix than to cosmetics.

## Why this is not only cosmetics

### Two colour ramps are live and they contradict each other

`build_embed` picks its accent colour at runtime from one of two tables:

- `theme.plan_color(badge, level)` (`embed_theme.py:50`) when a v2 plan exists
  — `embeds.py:499`
- `confidence_color(level)` (`embeds.py:168`) otherwise — `embeds.py:507`

They disagree:

| Level | `CONFIDENCE_COLORS` (`embeds.py:151`) | `LEVEL_COLORS` (`embed_theme.py:25`) |
|---|---|---|
| 1 | red `(231,76,60)` | grey `0x95A5A6` |
| 2 | orange `(230,126,34)` | grey `0x95A5A6` |
| 3 | yellow `(241,196,15)` | yellow `0xF1C40F` |
| 4 | yellow-green `(154,205,50)` | green `0x2ECC71` |
| 5 | green `(39,174,96)` | green `0x2ECC71` |

So **the same confidence level renders a different colour depending on whether
`PLAN_ENGINE_V2` is on**, and at level 1 the two say opposite things: red means
danger, grey means inert. A reader who learns the colour under one engine
setting is misled under the other. That is a communication bug, not a taste
question.

### The accent bar means three different things

Same 4px bar, three vocabularies:

- **alerts** — confidence level (`embeds.py:499/507`)
- **simple-alerts** — direction, green LONG / red SHORT (`embeds.py:730`).
  `embeds.py:715` calls this out in its own docstring as "the one recorded
  exception to green/red meaning outcome rather than direction"
- **closed-trades** — outcome, green win / red loss (`embeds.py:854/858`)

You cannot learn one rule and apply it. That is the concrete thing behind
"not oriented".

### The design system exists and is not adopted

`embed_theme.py` (101 lines) already holds a colour ramp, level chips, badge
chips, a `▰▰▰▰▱` meter, `SECTION_ORDER`, `apply_footer` and `fmt_price`. It is
used by `build_embed` and by two `apply_footer` calls. Everything else —
`build_simple_alert`, `build_closed_trade_embed`, `build_near_close_embed`,
the `PLAN_EVENT_STYLES` table, and all 12 command modules — goes around it.
**32 ad-hoc `discord.Color.*` call sites across 7 modules.**

The problem is therefore not "design a system". It is "finish the one that is
half-built, extend it to what it does not yet cover, and make bypassing it
fail a test".

### The alert does not fit a phone

`_build_trade_plan_table` (`embeds.py:261`) renders ~15 rows as one ANSI code
block, `f"{k.ljust(key_width)} : {v}"`. Rows such as
`Target confirmed by : EMA, VWAP, Fibonacci, structure` run 65–70 characters.
**Discord code blocks do not wrap** — they scroll horizontally. On a phone the
values sit off-screen.

## Decisions

### D1 — Direction is shape; colour is quality

`▲` / `▼` (U+25B2 / U+25BC) always answer long/short. Green/red always answer
good/bad — confidence on alerts, outcome on closed trades, severity on
warnings. **The two never swap jobs.**

This deletes the documented exception at `embeds.py:715`. It costs
simple-alerts its green/red direction bar, which becomes the confidence ramp;
direction survives there as the `▲`/`▼` already in its title and ANSI block.

It also matches the repo's own accessibility rule — `frontend/src/app/ui/format.ts:155`:
"Colour is never the only channel."

### D2 — One monotonic ramp, shared with the SPA

The accent bar is read at a glance and is often the only signal, so it must be
**ordinal**: worse → better, no categorical hues.

The SPA's ramp (`tokens.css:101-105`) is red → amber → grey → **blue** → green;
blue at level 4 reads as "informational", not "nearly top". The Discord ramp
and the SPA ramp are unified on a monotonic scale, which means editing
`--quality-4` in `frontend/src/styles/tokens.css`.

`--quality-N` has exactly two consumers — `frontend/src/app/ui/chip.ts` and
`frontend/src/app/ui/confidence-cell.ts` — so this is a small frontend edit.
Tier chips (A/B/C) shift hue with it; that is accepted, not overlooked.

**This spec therefore touches the frontend.** One file, one line, plus whatever
`chip.spec.ts` / `confidence-cell.spec.ts` assert about `--quality-4`.

### D3 — Colour lives in the accent bar and in `ansi` blocks, nowhere else

Discord renders embed titles, descriptions and field values in one colour.
There is no markdown for text colour. The only two mechanisms are the 4px
accent bar (full RGB) and an ` ```ansi ` code block (8 foreground colours,
30–37).

The bot already knows this and already solves it: `build_simple_alert`
(`embeds.py:757-764`) builds a coloured direction triangle in an ANSI block
precisely because "embed titles can't carry color". That inline pattern moves
into `presentation/ansi.py` and becomes the shared mechanism.

`CONFIDENCE_ANSI` (`embeds.py:165`) folds into the same module.

### D4 — The alert headline is the plan line, in ANSI

```
▲ 197.15 → 220.81 / 185.32
  +12.0%   −6.0%   2.4R
```

Two lines, ≤32 characters, so it cannot scroll on a phone. `▲` green, target
green, stop red — real colour, because it is inside an ANSI block.

`197.15 → 220.81 / 185.32` is deliberately the same `entry → target / stop`
form the admin SPA's own `PlanCell` renders, so the two surfaces read
identically.

### D5 — Confidence renders `Lv5 · 91`

Level and score, `·` separated — the form
`frontend/src/app/ui/confidence-cell.ts:41-45` already uses.

Both existing emoji vocabularies are deleted: `CONFIDENCE_EMOJI`
(🔴🟠🟡🟢🟢, `embeds.py:158`) and `_LEVEL_CHIPS` (1️⃣–5️⃣,
`embed_theme.py:34`).

### D6 — The badge is not rendered and does not affect colour

`plan_color(badge, level)` currently turns the whole embed amber whenever the
badge is `WEAK`, at any level. The badge is dropped from the body, so it also
stops driving colour — otherwise an off-colour alert would have no visible
cause.

**Recorded consequence:** `WEAK` becomes invisible in Discord. It survives in
the admin and in the trade record only. This was raised and chosen
deliberately; it is written here so it can be revisited as a decision rather
than discovered as a bug.

`plan_color(badge, level)` collapses to `accent_for_level(level)`.

### D7 — Failed gates get a field, not an annotation

Today an unmet requirement is a red ANSI annotation buried mid-table
(`⚠ needs ≥ 5.0%`). "Is this worth acting on" is half of what the first
screenful must answer, so unmet requirements become a dedicated
**`⚠ Blocked by`** field carrying actual-vs-required, and the accent drops to
the fail colour — replacing the `all_ok` grey at `embeds.py:507`.

### D8 — Emoji are semantic labels, never decoration

At most one per line, and only where it is genuinely the fastest label:
lifecycle titles (`🛡 Stop moved to break-even`), and simple-alerts' 🎯/💰/🛑
price labels, which survive because they disambiguate four numbers on one
line. Nothing decorative survives.

### D9 — The title is plain text and self-sufficient

Push notifications strip an embed to its title, so the title carries ticker,
direction and horizon in plain text with no reliance on embed body, colour or
ANSI. `build_simple_alert` already does this and says why
(`embeds.py:757-759`); it becomes the rule.

## Architecture

### The package

`swingbot/core/presentation/` — an eleventh `core/` package, alongside
`charts/`, which is already presentation and gives it precedent.

| Module | Owns |
|---|---|
| `tokens.py` | the one colour ramp, `▲`/`▼`, `Lv{n} · {score}`, the `▰▰▰▰▱` meter, `fmt_price` / `fmt_pct` / `fmt_r` |
| `ansi.py` | the ANSI headline builder, the 8-colour map (absorbs `CONFIDENCE_ANSI`) |
| `components.py` | `plan_headline(plan)`, `confidence_field(plan)`, `follow_field(plan)`, `blocked_by_field(reqs)`, `apply_chrome(embed, …)` |

`components.py` returns **whole embed parts**, not values. That is what makes
the kit hard to half-use: a call site that wants a confidence field asks for
one rather than assembling a name/value pair from tokens.

It cannot live in `core/scanning/` where `embed_theme.py` is today: twelve
`commands/*` modules need it, and `commands → core.scanning` for colour is a
dependency that misdescribes the code.

`embed_theme.py` is **absorbed and deleted**, not left as a facade — six call
sites, so a facade would be permanent clutter for no migration benefit.
`tests/scanning/test_embed_theme.py` moves to `tests/presentation/`.

### Adding an eleventh core package is a documented change

`CLAUDE.md` names the ten that exist, and `docs/claude/architecture.md` carries
the module map. Both are updated as tasks in Part 1, not left implied.

### Dead code removed along the way

All three verified unreferenced during this spec's research:

- `swingbot/admin/helpers.py:342` `_confidence_hex` — zero callers
- `swingbot/admin/helpers.py:347` `_sources_str` — zero callers; the live one
  is `embeds.py:173`
- `swingbot/admin/helpers.py:24` — the `CONFIDENCE_COLORS` import that feeds
  only `_confidence_hex`

All three are leftovers from the Jinja UI deleted 2026-08-14 (Release B).
Removing the import also kills one consumer of the accidental
`engine.py → embeds.py` re-export chain that v61 Part 2 complains about
(`_2-core-scanning.md:13`).

## Sequencing: this spec runs after v61

v61 Part 2 splits `embeds.py` into `snapshots.py` · `requirements.py` ·
`plan_table.py` · `alert_embeds.py` · `lifecycle_embeds.py` + a facade, under
a global constraint that **every moved function body is byte-identical**
(`_0-index.md`, C1). This spec rewrites exactly those bodies.

**v61 executes first.** This spec targets the post-v61 module layout, and its
plan must name the new paths, not `embeds.py`.

**Honest consequence:** v61 creates `plan_table.py` around
`_build_trade_plan_table`, and this spec's Part 2 largely guts that function —
the wide ASCII table is precisely what does not fit a phone. That is not
wasted work (v61 is move-only; this is the content change that follows), but a
module will be created and hollowed out within two plans, and that should be
visible rather than look like an accident.

`v58` (partial-plan reframe) also modifies `embeds.py` and is in the same
queue; whichever of v58/v62 runs second rebases onto the other.

## The channels

Every accent follows D1.

| Channel | Accent means | Headline |
|---|---|---|
| Alerts | confidence level | ANSI plan line + `+12.0% −6.0% 2.4R` |
| Simple-alerts | confidence level *(was direction — the D1 casualty)* | same, no chart |
| Closed-trades | outcome — win / loss / scratch | `▲ 197.15 → 214.90` + realised `+8.9% +1.6R` |
| Retrospective | the day's net outcome | day totals; no ANSI block |
| Firehose | confidence level (naturally duller) | same as alerts |

### The alert, in full

- **Title** — `AAPL · LONG · 2w`, plain text (D9)
- **ANSI headline** — the plan line (D4)
- **Fields, 2-up** — `Confidence Lv5 · 91` | `Follow ▰▰▰▰▱ 82`
- **Chart image**
- *below the fold* — `Confirmed by`, sizing, the scan diff, track record,
  warnings, and `⚠ Blocked by` when a gate fails (D7)
- **Footer** — plan id, scan time

`SECTION_ORDER` (`embed_theme.py:44`) survives as the ordering mechanism and
moves to `tokens.py`; the section list is re-cut to put the fold where it now
falls.

## Enforcement

A test walks the AST of `swingbot/commands/` and `swingbot/core/scanning/` and
**fails on any `discord.Embed(color=…)` or `discord.Color` reference outside
`core/presentation/`.**

The **shape** is precedented — `tests/test_env_example_sync.py` already asserts
a structural invariant by test rather than by convention. The **technique** is
not: no test in this repo currently imports `ast`. That is deliberate rather
than overlooked. A regex over the source would be simpler and would also catch
`discord.Color` inside a string, a comment or a docstring — of which this
codebase has many, several quoting the very call sites being removed. The plan
should treat "AST, not regex" as a requirement, not an implementation detail.

The test is scoped to migrated modules at first and widened as each part
lands, so the suite is green throughout rather than red from day one.

Without it, the design degrades exactly the way it already has once — 32
ad-hoc colour call sites is what "we agreed to use the theme module" produced.

## Parts

Each merges before the next, per `document-conventions.md`.

**Part 1 — the kit.** `core/presentation/` with `tokens.py`, `ansi.py`,
`components.py`. Guard test, scoped to the new package. The three dead-code
deletions. `--quality-4` in `tokens.css`. `CLAUDE.md` and `architecture.md`
updated. **Nothing user-visible changes** — this part is provably invisible in
Discord, which is what makes it safe to land first.

**Part 2 — the five automated channels.** `alert_embeds.py`,
`lifecycle_embeds.py`, `plan_table.py`. Guard widened to `core/scanning/`.
**This is where it starts looking different.**

**Part 3 — the commands.** The ~12 `swingbot/commands/*` modules. Guard
widened to `commands/`, which is then the whole surface.

## Testing

- **`tokens.py` and `ansi.py` are pure** — ramp boundaries, glyph selection,
  formatter edge cases (null, zero, sub-1 prices) unit-tested without a
  TestBed or a Discord object, the way `dashboard.helpers.ts` is split out on
  the frontend for the same reason.
- **`components.py` returns real `discord.Embed` parts** — asserted on field
  name, order and value, not on rendered pixels.
- **Width invariant.** A test asserts no ANSI block line exceeds 32
  characters, for every builder. This is the rule that keeps the phone
  promise, and it is the one most likely to erode silently.
- **The guard test** above.
- **Existing tests** — `tests/scanning/test_embed_theme.py` (moves),
  `test_embeds_badges.py`, `test_embeds_v3.py`, `test_transition_embeds.py`,
  `test_simple_alerts.py`, `test_embed_theme.py` all assert current output and
  will need rewriting per part. That rewriting is task work, not incidental.

## Out of scope

- The admin SPA's own presentation, beyond the one `--quality-4` token.
- Backend logging — its own spec, deliberately separate: different audience,
  no shared code, different definition of done.
- Any change to *which* messages are sent, to whom, or when. This spec changes
  how a message looks, never whether it is posted.
- Function decomposition inside the moved modules — that is v61 Phase B.
