# v241 — Doctena night, plan 2 of 5: Icons (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V241-3" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) — plan 2 of its "What follows" list (§4, the icon lines of §8–§11). Its `### Corrections from the plan 2 code brief (2026-11-23)` section overrides the text above it and the mockups.
**Brief:** `.superpowers/briefs/v240-plan2-icons.md`
**Runs after:** plan 1, [v240 theme and type](2026-11-23-v240-doctena-night-theme-and-type_0-index.md) (19 tasks). Plans 1 to 5 run strictly in order, one worktree at a time.
**Number:** v241 (partner, 2026-11-23). Commits `fdca0ef4` and `c1946a17` also say `(v241)`; they are plan 1's index and part 1 from before that plan was renumbered to v240, so the counter would skip v241. This plan was briefly v242 (`f974abc0`, `a50cb948`); plan 3 takes v242.

## Goal

The admin UI draws its icons on a 16×16 grid at a 1.5 stroke, and several
controls still use typed characters as icons: `▲`/`▼` for long and short,
`×` to close a drawer, `▾`/`▸` to expand a panel or a table row, `◉`/`○` for
the live-tape toggle, a letter `i` in a CSS circle for help. Text glyphs
change shape with the font (plan 1 moves everything to Jost), sit off the
baseline, and read differently from the drawn icons next to them. The spec's
doctena-night restyle (D6) redraws every icon so each one says what it
means: a gauge for Dashboard, binoculars for Watchlist, a shield with a
percent sign for Risk, a finish flag for a closed trade.

Once this ships, `sb-icon` draws on a 24×24 grid at a 1.8 stroke with round
caps and joins, at 16px in tables and inline text, 20px in lists and 24px in
the rail and phone tab bar, through a new `size` input. Pending's sand and
Partial's banked half are filled sub-paths. Nine new names (`info`, `long`,
`short`, `close`, `edit`, `up`, `down`, `plus`, `minus`) join the set. The
direction arrow, the drawer close button, the panel and row toggles, the
tape toggle, the versions "now" marker, the Guide's fold marker and the help
trigger all draw icons instead of characters.

Every existing icon keeps its name, so the redraw reaches every caller
without touching it. Icons stay `aria-hidden`; each control keeps the
accessible name it carries today, and a test pins that for the seven
controls the swap touches. A glyph inside a sentence or a value stays text:
`1.40×`, `1.5 × ATR`, `115.26 → 123.05`, the banked-target `✓` in
`plan-cell.ts`, and the server-built `⚠ SQUEEZE RISK` prefix. The rail's
64px layout, tooltips and Calendar entry are plan 3; this plan only sets the
rail icons' size.

Success is measured by tests: every `ICON_NAMES` entry renders a 24-grid
path and has a label, no two names share a glyph, `size` sets the rendered
width and height, a filled sub-path renders with `fill="currentColor"`, each
swapped control keeps its accessible name, and a source scan fails if a
replaced glyph (`ⓘ ▲ ▼ ▾ ▸ ◉ ○`, their character references, or a
standalone close `×`) reappears in a template or stylesheet.

## Architecture

- **`ui/icon.ts` is the only drawing source.** `PATHS` (one stroked `d` per
  name) gains a sibling `FILLS: Partial<Record<IconName, string>>`, rendered
  as a second `<path class="fill" fill="currentColor" stroke="none">` after
  the stroked one (the svg keeps `fill="none"`; `icon.spec.ts`'s
  unique-glyph test reads the first path). The svg's `viewBox` is
  `0 0 24 24` at every size; `size` sets only `width`/`height`.
- **Callers pick a size, never override the svg in CSS.** The one override
  (`shell.css:89`, `.rail-pill sb-icon svg {width:24px; height:24px}`) is
  deleted in favour of `[size]="24"`.
- **Glyph sites swap in place.** Each site keeps its element, class and
  accessible name; only the glyph text becomes `<sb-icon ... title="" />`
  (empty `title` so the icon adds no tooltip of its own inside a labelled
  control, as the rail does today). The Guide's markdown `<details>` marker
  is rendered HTML with no Angular component, so it draws the same chevron
  paths through a CSS `mask-image` data URI.
- **One gate closes the plan.** `ui/icon-glyphs.spec.ts` scans every
  non-spec source (`allSources()` with `stripComments`) for the replaced
  glyphs and checks, table-driven, that each guarded control's source still
  carries its accessible name.

## Decisions this index fixes (spec silent or corrected; controller may override)

1. **Stroke 1.8 at every size**, the rail brand included (spec correction;
   mockup 4's 2.0 at 16px and its 26px brand are not followed).
2. **Size per surface:** `24` on the rail pills and rail brand
   (`shell.html:9,19,33`) and the phone tab bar (`phone-tab-bar.ts:38,50`);
   `20` on the recent-activity event icon (`recent-activity.ts:39`) and the
   profile-menu items (`profile-menu.ts:100,135`); every other caller keeps
   the default `16`.
3. **Glyph to icon mapping:**
   - `direction-arrow.ts` `▲`/`▼` → `long`/`short` (colour stays
     `--pos`/`--neg`, spec §1 and the financial-advisor ruling);
   - drawer close `×` → `close`;
   - panel toggle and data-table row toggle `▾` (expanded) / `▸`
     (collapsed) → `down` / `expand`;
   - watchlist tape toggle `○` (not in tape) / `◉` (in tape) → `plus` /
     `minus` (the button keeps `aria-pressed` and its aria-label);
   - versions `&#9650; now` → `<sb-icon name="up" title="" />` before "now";
   - Guide `summary::before` `▸`/`▾` → CSS mask of the `expand`/`down` paths;
   - `sb-hint` trigger → `info` for every caller; its `glyph` input is
     deleted, and `shell.html:45` `glyph="v"` and `dashboard.ts:312`
     `glyph="?"` drop the attribute (partner, 2026-11-23, in the spec
     correction).
4. **Stays text (spec correction):** `plan-cell.ts:290` `✓` (a value
   suffix), `plan-detail.ts:217` `⚠` (server string from
   `short_notice.py:21`), and every `×` used as multiplication.
5. **`voice-chip.ts` keeps its hand-rolled speaker svg.** The spec names no
   `speaker` icon; adding one would add scope. Flagged for the controller.
6. **No `grip`** (spec §4 and the correction).
7. **New labels** (`LABELS`): `info` 'Information', `long` 'Long', `short`
   'Short', `close` 'Close', `edit` 'Edit', `up` 'Move up', `down` 'Move
   down', `plus` 'Add', `minus` 'Remove'. Existing labels are unchanged.

## Global Constraints

- Grid: `viewBox="0 0 24 24"`, `stroke-width="1.8"`, `stroke-linecap="round"`,
  `stroke-linejoin="round"`, `stroke="currentColor"`, `fill="none"` and
  `aria-hidden="true"` on the svg. Filled sub-path:
  `<path class="fill" fill="currentColor" stroke="none">`, rendered second.
- `export type IconSize = 16 | 20 | 24;` and `readonly size = input<IconSize>(16)`;
  the svg's `width` and `height` attributes equal `size()`.
- Paths are copied verbatim from the brief §6 table (the `analytics` bulb,
  not mockup 4's bars). Every path keeps a one-line comment saying what it
  shows.
- Every existing `ICON_NAMES` entry keeps its name and position; the nine
  new names are appended in the order `info, long, short, close, edit, up,
  down, plus, minus` (36 names).
- Icons are `aria-hidden`; the accessible name lives on the control. Never
  add a second name inside a labelled control ("Trades Trades").
- Per-task verification is narrow:
  `cd frontend && npx ng test --watch=false --include <spec>` (one or a few
  spec files; a 60s `Timeout waiting for worker` is load, so re-run once).
  No task runs the full suite; CI does.
- Frontend only: no Python, schema or bot change.
- Commit in scoped commits inside the plan's worktree; never stage another
  session's files.

## Plan 1 contracts this plan relies on (from its ledger)

- V240-6 / V240-7: `export function styleRules(name: string, source: string): StyleRule[]`
  and `export type StyleRule = { selector: string; body: string }` in
  `frontend/src/app/ui/testing/style-rules.ts` (`.ts` `styles:` literals and
  `.css` files; escaped backticks handled). V241-3, V241-6 and V241-7 read
  CSS rules through it.
- V240-8: `sb-button` text is uppercase; icon variants reset it. The
  watchlist tape toggle (`variant="ghost"`) holds an icon after V241-7.
- V240-9 / V240-16: `ui/type-gates.spec.ts` runs with no pending lists.
  V241-5 deletes `hint.ts`'s `.glyph` rule (the only `--font-mono` rule this
  plan removes), which can only reduce offenders.
- V240-10: `NAV_FILES` in `ui/money-colour.spec.ts`; `direction-arrow.ts`
  is not a nav file and keeps `--pos`/`--neg`.
- V240-3 / V240-5 edit `ui/primitives.spec.ts`; V241-7 edits only its
  `(?<!&)` comment afterwards.
- Existing (not plan 1): `allSources(): Source[]` and `stripComments(source)`
  in `frontend/src/app/ui/testing/all-sources.ts`.

## Parallelisation

The plan runs **in id order in one worktree** (the spec's five plans are
strictly sequential). Sequential edges and their reasons:

- V241-1 → V241-2: both edit `ui/icon.ts` and `ui/icon.spec.ts`.
- V241-1 → V241-3: V241-3 consumes the `size` input.
- V241-2 → V241-4, V241-5, V241-6, V241-7: they consume the new names
  (`long`, `short`, `info`, `close`, `down`, `up`, `plus`, `minus`).
- V241-2 → V241-4: both edit `workspaces/gallery/gallery.spec.ts`.
- V241-3 → V241-5: both edit `shell/shell.html` (and possibly
  `shell.spec.ts`).
- V241-4, V241-5, V241-6, V241-7 → V241-8: the gate asserts the glyphs are
  gone and reads the swapped sources.

Safe to run in parallel if the controller wants to: **V241-4 ∥ V241-6 ∥
V241-7** after V241-2 (disjoint files: direction arrow, confidence cell,
gallery spec and the `tokens.css` comment vs `layout.ts`/`data-table.ts` vs
watchlist, versions, guide and `primitives.spec.ts`; no contract between
them).

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V241-1 | `sb-icon` on the 24 grid: filled sub-paths, 1.8 stroke, all 27 names redrawn (svg fixed at 16px) | 1 | sonnet | M `frontend/src/app/ui/icon.ts`, M `frontend/src/app/ui/icon.spec.ts`, M `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts` (old `partial`/`opened` path pins) | `const FILLS: Partial<Record<IconName, string>>` (`pending`, `opened`, `partial`); second `<path class="fill">` |
| V241-1b | `size` input: `IconSize`, width/height binding | 1 | sonnet | M `frontend/src/app/ui/icon.ts`, M `frontend/src/app/ui/icon.spec.ts` | `export type IconSize = 16 \| 20 \| 24`; `Icon.size = input<IconSize>(16)` |
| V241-2 | Nine new names, their labels, and the full set in the gallery | 1 | haiku | M `frontend/src/app/ui/icon.ts`, M `frontend/src/app/ui/icon.spec.ts`, M `frontend/src/app/workspaces/gallery/gallery.ts`, M `frontend/src/app/workspaces/gallery/gallery.spec.ts` | `IconName` gains `'info' \| 'long' \| 'short' \| 'close' \| 'edit' \| 'up' \| 'down' \| 'plus' \| 'minus'`; gallery `iconNames: readonly IconName[] = ICON_NAMES` |
| V241-3 | Sizes per surface: rail and tab bar 24, lists 20; the `shell.css` svg override deleted | 1 | sonnet | M `frontend/src/app/shell/shell.html`, M `frontend/src/app/shell/shell.css`, M `frontend/src/app/shell/shell.spec.ts`, M `frontend/src/app/shell/phone-tab-bar.ts`, M `frontend/src/app/shell/phone-tab-bar.spec.ts`, M `frontend/src/app/shell/profile-menu.ts`, M `frontend/src/app/shell/profile-menu.spec.ts`, M `frontend/src/app/workspaces/dashboard/panels/recent-activity.ts`, M `frontend/src/app/workspaces/dashboard/panels/recent-activity.spec.ts` | none |
| V241-4 | Direction arrows draw `long`/`short` icons | 1 | sonnet | M `frontend/src/app/ui/direction-arrow.ts`, M `frontend/src/app/ui/direction-arrow.spec.ts`, M `frontend/src/app/ui/confidence-cell.spec.ts`, M `frontend/src/app/workspaces/gallery/gallery.spec.ts`, M `frontend/src/styles/tokens.css` (line-49 comment only) | `.arrow` span keeps `aria-label`/`title` and holds `<sb-icon [name]="icon()" title="" />` |
| V241-5 | `sb-hint` draws the `info` icon; the `glyph` input is deleted | 2 | sonnet | M `frontend/src/app/ui/hint.ts`, M `frontend/src/app/ui/hint.spec.ts`, M `frontend/src/app/shell/shell.html` (line 45), M `frontend/src/app/shell/shell.spec.ts` (only if it pins `glyph="v"`), M `frontend/src/app/workspaces/dashboard/dashboard.ts` (line 312), M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` (only if it pins `?`) | `button.trigger > sb-icon[name=info]` |
| V241-6 | Drawer close, panel toggle and row-detail toggle draw icons | 2 | sonnet | M `frontend/src/app/ui/layout.ts`, M `frontend/src/app/ui/layout.spec.ts`, M `frontend/src/app/ui/data-table/data-table.ts`, M `frontend/src/app/ui/data-table/data-table.spec.ts` | `button.close > sb-icon[name=close]`; `button.panel-toggle` / `button.detail-toggle` hold `sb-icon` `down` (expanded) or `expand` (collapsed) |
| V241-7 | Tape toggle, versions "now" marker and the Guide's fold marker | 2 | sonnet | M `frontend/src/app/workspaces/watchlist/watchlist.ts`, M `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, M `frontend/src/app/workspaces/versions/versions.ts`, M `frontend/src/app/workspaces/versions/versions.spec.ts`, M `frontend/src/app/workspaces/guide/guide.ts`, M `frontend/src/app/workspaces/guide/guide.spec.ts`, M `frontend/src/app/ui/primitives.spec.ts` (the `(?<!&)` comment only) | `button.tape-toggle > sb-icon` `plus`/`minus`; `.ticks .now > sb-icon[name=up]` |
| V241-8 | Glyph gate and accessible-name guard | 2 | sonnet | C `frontend/src/app/ui/icon-glyphs.spec.ts` | `REPLACED_GLYPHS` and `GUARDED_SITES` consts in that spec |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-23-v241-doctena-night-icons_1-icon-set.md` | V241-1..V241-4 (with V241-1b) | The 24-grid component with `size` and fills, the full redraw, the new names, sizes per surface, direction arrows |
| 2 | `2026-11-23-v241-doctena-night-icons_2-glyph-swaps.md` | V241-5..V241-8 | Help trigger, drawer close and toggles, tape toggle, versions and Guide markers, the glyph gate |

## Handoff

- Guide chapters: no file under `docs/guide/` cites `icon.ts`, `hint.ts`
  or `direction-arrow.ts`. The close-out records `guide: no reader-visible
  change` unless `scripts/dev/guide_sources.py` reports a chapter whose
  `sources:` touches this plan's diff.
- Open for the controller: Decision 3's tape-toggle mapping (`plus`/`minus`)
  and Decision 5 (`voice-chip.ts` speaker stays hand-rolled).
- Plan 3 builds the 64px rail on V241-3's `[size]="24"` rail icons; it must
  not restore a CSS svg override.
