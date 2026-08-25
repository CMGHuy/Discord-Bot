# v62 — The Discord message system: index and shared conventions

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement each part task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** One presentation kit — `swingbot/core/presentation/` — owning every
colour, glyph, number format and embed part the bot sends to Discord, adopted
by all five automated channels and all command modules, with an AST guard test
that makes bypassing it a test failure.

**Spec:** `docs/superpowers/specs/2026-08-25-v62-discord-message-system-design.md`

**Architecture:** `components.py` returns **whole embed parts**, not values —
a call site that wants a confidence field asks for one rather than assembling
a name/value pair out of tokens. That is what makes the kit hard to half-use.
`tokens.py` and `ansi.py` beneath it are pure and testable without a Discord
object. Part 1 builds the kit and changes nothing visible; Part 2 flips the
five automated channels and the shared colour ramp; Part 3 finishes the
command modules and widens the guard to the whole surface.

**Tech Stack:** Python 3.11+, discord.py, pytest. One CSS token in the Angular
SPA (`frontend/src/styles/tokens.css`). No new dependencies.

**Bump:** bot minor (1.4.3 → 1.5.0), assigned at release time after Part 3 is
green — not before. **Edge:** none (integrity).

## Parts

| Part | Scope | Tasks | Visible change? |
|---|---|---|---|
| `_1` | `core/presentation/` kit, guard test, dead-code deletions, docs | M1–M9 | **None.** Nothing imports the kit yet. |
| `_2` | The five automated channels + the shared ramp flip | M10–M20 | **Yes.** This is where it starts looking different. |
| `_3` | The command modules, guard widened to everything | M21–M29 | Yes, command output. |

Each part executes in its own worktree named for that part's file stem, per
`docs/claude/document-conventions.md`, and merges before the next begins.

---

## Global Constraints

These apply to **every task in every part**. They are not repeated per task.

### C1 — v61 must be merged first

`v61` Part 2 splits `embeds.py` into `snapshots.py` · `requirements.py` ·
`plan_table.py` · `alert_embeds.py` · `lifecycle_embeds.py` + a facade, under
a byte-identical move invariant. This plan rewrites those bodies.

**Every path in Parts 2 and 3 is a post-v61 path.** Before starting Part 2,
confirm the split has landed:

```bash
ls swingbot/core/scanning/alert_embeds.py swingbot/core/scanning/lifecycle_embeds.py
```

Both must exist. If they do not, stop — v61 has not merged, and this plan's
file paths are wrong.

### C2 — Direction is shape; colour is quality

`▲` (U+25B2) and `▼` (U+25BC) always answer long/short. Green/red always
answer good/bad — confidence on alerts, outcome on closed trades, severity on
warnings. **They never swap jobs.** No task may reintroduce a colour that
encodes direction.

### C3 — No ANSI block line exceeds 32 characters

This is the rule that keeps the phone promise, and the one most likely to
erode silently. `tests/presentation/test_ansi.py::test_no_builder_exceeds_width`
(Task M4) enforces it across every builder.

### C4 — The embed title is plain text and self-sufficient

Push notifications strip an embed to its title. Titles carry ticker, direction
and horizon in plain text, with no reliance on the body, on colour, or on
ANSI.

### C5 — Colour only inside `core/presentation/`

No `discord.Color` reference and no `discord.Embed(color=...)` keyword outside
`swingbot/core/presentation/`. Enforced by AST in
`tests/presentation/test_no_adhoc_color.py` (Task M8), scoped to migrated
packages and widened as parts land.

### C6 — Emoji are semantic labels, never decoration

At most one per line, and only where it is genuinely the fastest label. The
surviving set is fixed in Task M9's docstring; anything not on it is removed
rather than restyled.

### C7 — Verification is narrow per task, full once at the end

Per task: `python scripts/dev/testrun.py file tests/<the file this task touched>.py`
(~7s). **Never `full` inside a task.** Task M29 runs
`python scripts/dev/testrun.py full` once, over everything all three parts
implemented.

### C8 — Numbers go through the kit

Prices via `tokens.fmt_price`, percentages via `tokens.fmt_pct` (always
signed), R-multiples via `tokens.fmt_r`. No `f"{x:.2f}"` on a price in a
builder.

### C9 — Do not bump `VERSION.json` inside a task

The release bump is its own commit after Part 3 is green, per
`working-conventions.md`. Regenerate `swingbot/admin/version_history.json`
immediately after that bump commit.

---

## Parallelisation

### Part 1

- **Sequential:** M1 before everything — it introduces `ACCENT_RAMP` and
  `accent_for_level`, which M2, M3, M5 and M7 all consume.
- **Group 1 (parallel):** M3, M9 — `ansi.py` and the deletions/docs share no
  file with each other and neither consumes the other's symbols. (M9 touches
  `swingbot/admin/helpers.py`, `CLAUDE.md`, `docs/claude/architecture.md`.)
- **Sequential:** M2 after M1 (same file, `tokens.py`). M4 after M3 (same
  file). M5, M6, M7 after M4 — all three write `components.py`, so they are
  sequential **with each other** regardless of their inputs. M8 last: the
  guard test asserts against the package the earlier tasks create, and running
  it before they exist fails for the right reason at the wrong time.

### Part 2

- **Sequential throughout for `alert_embeds.py`:** M11 → M12 → M13 → M14 all
  edit one file, and M12 consumes the section accumulator M11 reshapes.
- **Group 2 (parallel):** M10, M15 — `frontend/src/styles/tokens.css` and
  `lifecycle_embeds.py` are disjoint and share no symbol.
- **Sequential:** M16, M17 after M15 (same file, `lifecycle_embeds.py`).
  M19 after M11 (it retires what M11 replaces; doing it first leaves
  `build_embed` calling a function that no longer exists). M20 last — it
  deletes `embed_theme.py`, so every call site must already be migrated.

### Part 3

- **Group 3 (parallel):** M21, M22, M23, M24, M25, M26 — one command module
  each (`trades.py`, `plans.py`+`history.py`, `stats.py`, `info.py`,
  `views.py`, `slash.py`), no shared file, and all six consume only the kit
  that Part 1 froze. This is the widest group in the plan and the reason
  Part 3 is fast.
- **Sequential:** M27 after Group 3 (it sweeps whatever those six leave
  behind, so it must see their result). M28 after M27 — widening the guard to
  `swingbot/commands/` fails until the last module is migrated. M29 last.

**Concurrent sessions share this working tree.** Two agents dispatched onto
tasks in different groups above are safe; two agents on the same group's
sequential chain are not, and the second silently overwrites the first.

---

## Where the visual language is defined

One table, so no task has to re-derive it. Task M1 writes it; every later task
reads it.

| Concept | Rendering | Owner |
|---|---|---|
| Direction | `▲` long, `▼` short | `tokens.direction_glyph` |
| Confidence | `Lv5 · 91` | `tokens.confidence_label` |
| Follow score | `▰▰▰▰▱ 82` | `tokens.follow_meter` |
| Accent, level 1–5 | red → amber → grey → yellow-green → green | `tokens.accent_for_level` |
| Accent, outcome | green win · red loss · grey scratch | `tokens.accent_for_outcome` |
| Accent, gate failed | grey `0x95A5A6` | `tokens.ACCENT_BLOCKED` |
| Plan headline | `▲ 197.15 → 220.81 / 185.32` | `components.plan_headline` |

## Deleted vocabulary

Every one of these is removed, not restyled. Listed here so a task that finds
a stray reference knows it is intentional rather than an oversight.

| Symbol | Location | Replaced by |
|---|---|---|
| `CONFIDENCE_COLORS` | `embeds.py:151` | `tokens.ACCENT_RAMP` |
| `CONFIDENCE_EMOJI` | `embeds.py:158` | nothing — D5 |
| `CONFIDENCE_ANSI` | `embeds.py:165` | `ansi.FG` |
| `confidence_color()` | `embeds.py:168` | `tokens.accent_for_level` |
| `LEVEL_COLORS` | `embed_theme.py:25` | `tokens.ACCENT_RAMP` |
| `WEAK_COLOR` | `embed_theme.py:32` | nothing — D6 |
| `_LEVEL_CHIPS` | `embed_theme.py:34` | `tokens.confidence_label` |
| `_BADGE_CHIPS` | `embed_theme.py:35` | nothing — D6 |
| `plan_color()` | `embed_theme.py:50` | `tokens.accent_for_level` |
| `level_chip()` | `embed_theme.py:60` | `tokens.confidence_label` |
| `badge_chip()` | `embed_theme.py:64` | nothing — D6 |
| `_confidence_hex()` | `admin/helpers.py:342` | nothing — dead |
| `_sources_str()` | `admin/helpers.py:347` | nothing — dead duplicate |
