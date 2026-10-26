# v195 — Graphite: the whole frontend redesigned: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V195-16:" -A 400 docs/superpowers/plans/2026-10-25-v195-graphite-frontend-redesign_6-shell-rail-topbar-phone.md`.

**Bump:** ui minor, bot patch
**Edge:** none (integrity) — no signal, gate, stop, size, badge or API change; the partner reads these screens to place real orders, and a calmer, consistent surface lowers the chance of misreading a plan without buying measurable expectancy.
**Screen:** exempt (integrity)
**Spec:** [2026-10-25-v195-graphite-frontend-redesign.md](../specs/2026-10-25-v195-graphite-frontend-redesign.md) — its `## Spec corrections` section wins over the body; its `## Panel review` is already applied.
**Brief:** `.superpowers/briefs/2026-10-25-v195-graphite-frontend-redesign.md` (gitignored; tasks cite repo files, never the brief)
**Worktree:** every task runs in `.claude/worktrees/2026-10-25-v195-graphite-frontend-redesign` (branch of the same name, cut from `main` **after v194 is merged**, created in V195-1's first step; `docs/claude/document-lifecycle.md`). The merge to `main` is V195-36's last step.
**Precondition:** v194 (`2026-10-25-v194-ui-tooltips-and-data-truth`) is implemented and merged. V195-1's first step proves it (`git grep -n "hintVerdict" frontend/scripts/layout-audit-lib.mjs` and `git grep -n "supportsPopover" frontend/src/app/ui/hint.ts` both print a line) and stops otherwise. Line numbers this plan cites for `hint.ts`, `layout.ts`, `metric-card.ts`, `stat-tile.ts`, `layout-audit-lib.mjs` and `layout-audit.mjs` are pre-v194: every task touching them re-reads the file first and edits by symbol, not by line.

## Goal

The admin UI has been refreshed piecemeal (Arctic Navy tokens in v167,
motion and ambient glow in v168, saturated valence hues in v181, mobile
consistency in v179), each correct on its own, and together it reads as
decorated rather than professional. An ambient glow, a hover lift and
route-entrance animations compete with the figures; panel headings,
pagers, filter bars and destructive actions differ from page to page; and
v194's root cause, a hover-lift transform that broke every tooltip, was a
symptom of that decoration. The partner reads these screens before placing
real resting orders, so a surface where a halt button looks like
housekeeping, or a loss is told from a gain by colour alone, is an
integrity risk, not a taste question.

Once this ships, the app is "Graphite": a neutral near-black ramp with
muted green and red, one steel-blue accent used only for interactive
state, no glow, no lift and almost no motion. Navigation is an
always-collapsed 48px icon rail in four groups (Monitor, Review, Insights,
System), a 40px top bar with a breadcrumb, killswitch and freshness chips
visible on every device, and a Ctrl/⌘K command palette that reaches every
page, ticker, trade and the density preference but never a destructive
action. Phones get a bottom tab bar and a More sheet. Every workspace is
rebuilt on one `sb-page` template (header with actions, scope bar, KPI
strip, primary panel, secondary grid), destructive actions live only in
the header and always confirm (`danger` for the killswitch alone,
`danger-quiet` for housekeeping), risk KPIs show money and % of account
together, performance strips lead with ExpR and show N, and every signed
figure carries a true minus. Rows are dense (28px) by default on desktop
and comfortable (44px) on request, while tablets, phones and coarse
pointers keep 44px targets. The Discord alert images move to the same
palette, with the entry line in the same accent as the app.

In idea: the change is layered so that each phase reads only the one
below it. Tier-1 palette literals are rewritten and tier-2 semantic
tokens keep their names, so most components change no code; primitives
are re-skinned on those tokens; the shell is rebuilt from primitives; the
page template is one more primitive; and each workspace is then a mapping
of its existing panels into the template's slots. The few behaviour
changes beyond the look are named and small: a root `SearchIndexStore`
over existing endpoints, the Scan-health and Data-source computeds moving
from `RiskStore` to `SystemStore` (with a `?tab=providers` System tab), a
per-device `ui.density` key, the orphaned `shell.sidebar` preference, and
one new layout-audit check (`rail-label`).

It leaves alone every backend API, schema and stored record, every route
path, the trading logic the bot computes, workspace boundaries (nothing is
merged, split or retired), the login page beyond its re-skin, and light
theme (dark only, the token layer stays theme-ready). Success is measured
by the unit suites staying green at every phase with the pinning specs
moved, not deleted (only the route-entrance specs and the shell's
expand/collapse cases retire, with their features); `workspace-consistency`
proving every route uses `sb-page`; `contrast.spec` holding every text and
valence pair at WCAG AA; `test_chart_theme.py` pinning the new Discord
theme; and the layout audit (every route, including `?tab=providers`, at
390 / 768 / 1440, with the new `rail-label` check) passing locally before
the merge and once more against production after deploy.

## Architecture

- **Tokens (Phase 1, V195-1..V195-7).** `palette.css` (tier 1, the only
  hued literals) is rewritten to the `--graphite-*` / `--grey-*` /
  `--steel-*` / `--green-500` / `--red-500` / `--amber-500` /
  `--violet-400` ramp; `tokens.css` tier 2 keeps every name and repoints;
  tier 3 moves to 6/4/2px radii, flat panels and a 12px micro floor.
  `tests/charts/resolved_tokens.json` is regenerated in the same commit as
  every `:root` edit, which couples the palette to
  `swingbot/core/charts/chart_style.py` `THEME` (V195-1 adds the `accent`
  key on the old palette; V195-2 moves every value). Density is
  `<html data-density="dense|comfortable">`, written by a root
  `DensityService` over `localStorage` (`ui.density`), and only the
  desktop fine-pointer media block reads it.
- **Primitives (Phase 2, V195-8..V195-13).** Look only, except: button
  variants `danger` (solid, killswitch) / `danger-quiet` (every existing
  `danger` call site), `ConfirmDialog.dangerVariant`, a `[header-actions]`
  slot on `sb-panel-header`, and `sb-data-table` losing its top pager.
- **Shell (Phase 3, V195-14..V195-20).** `shell/nav.ts` owns the four nav
  groups, the phone tabs and breadcrumb derivation; `RouteTitleService`
  gains a `detail` channel for detail routes; rail labels use a new
  `Hint.anchor` label mode (a sibling popover driven by the link's hover
  and focus, no extra tab stop). The palette's data comes from a new root
  `SearchIndexStore` that calls the existing `tickers()` and `trades()`
  endpoints lazily on first open.
- **Page template (Phase 4, V195-21).** `ui/page.ts` `sb-page` renders the
  page's single `<h1>` (so `route-focus.ts`'s `.workspace h1` finds it and
  `workspace-consistency`'s no-`<h1` ban on workspace sources still holds).
- **Workspaces (Phase 5, V195-22..V195-33)** map existing panels to slots.
- **Charts (Phase 6, V195-34)** confirm every in-app chart and SVG
  primitive reads tokens only and record the before/after alert image.
- **Release (Phase 7, V195-35..V195-36).** Audit check, full suite, audit
  run, results doc, merge.

**Plan decisions (gaps the spec leaves, filled from the code; the
controller checks them, see the return's OPEN):**

1. **Risk money on Risk.** `GET /risk` carries `heat.open_pct` and
   `heat.cap_pct` but no amount, and the spec allows no API change. The
   amount is `pct / 100 × account balance`, the same relation the server
   uses (`trade_risk_pct(t, balance)`, `swingbot/admin/api_v1/risk.py`).
   `RiskStore` reads the balance from the **existing** `api.dashboard()`
   (`Dashboard.account_balance`) beside `api.risk()`, as correction 3 does
   for `SystemStore`. A failed balance read shows `— · 1.42%`, never an
   invented figure. The Dashboard reads its own `balance()` and
   `riskUsedPct()`. One helper formats both: `riskUnits` (V195-7).
2. **Dashboard KPI strip** uses only figures the Dashboard already has:
   ExpR (N), win rate (N), open risk (money · %, linking to `/risk`),
   realised in period, open positions. The spec's "month R" is an example
   (§5.2 "e.g.") with no source field, so it is not added.
3. **Freshness chip** shows the bot's last successful tick
   (`ScanStatus.bot_last_success`, already fetched by
   `ConnectionStore.refresh()`; stored as `ConnectionStore.botLastSuccess`),
   falling back to `botLastSeen`.
4. **System default tab stays Settings** (correction 4); tab order Scan ·
   Providers · Settings · Logs; an unknown `?tab=` falls back to Settings.
5. **Discord pins.** V195-1 appends a `STYLE_PINS` row for `STYLE_VERSION
   = "v195a"` (accent key, old palette); V195-2 appends `"v195"` (Graphite
   values). Both rows are append-only.

## Global Constraints

- Frontend: Angular, zoneless, Vitest 4 through `@angular/build:unit-test`
  on jsdom. Narrow run: `npm --prefix "$WT/frontend" test -- --watch=false --include <spec path relative to frontend/>`;
  before each frontend commit also `npm --prefix "$WT/frontend" test -- --watch=false`
  (whole frontend) and `npm --prefix "$WT/frontend" run lint`. **Never `cd`
  in a Bash call** (it breaks the guardrail hooks): use `--prefix`, `-C` or
  absolute paths. `WT` is the worktree's absolute path.
- **No backend API, schema or data change.** The only Python edits are
  `swingbot/core/charts/chart_style.py` and `tests/charts/test_chart_theme.py`
  (V195-1, V195-2). No new endpoint; `SearchIndexStore`, `SystemStore` and
  `RiskStore` call existing `ApiClient` methods only.
- **Route paths do not change**; nothing is merged, split or retired.
- **Tokens.** Hued literals live only in `frontend/src/styles/palette.css`
  (plus the named `--chart-1..6` / `--quality-4` exceptions in
  `tokens.css` and the cold-load copies in `index.html` /
  `public/manifest.webmanifest`). Alpha tints are plain `rgba()` literals,
  never `color-mix()`. The token resolver reads only top-level `:root`
  with plain `var(--x)`: any `html[data-density=…]` or `@media` override
  sits outside `:root`. Regenerate `tests/charts/resolved_tokens.json`
  (`python scripts/dev/dump_tokens.py`) in the same commit as every `:root`
  edit of `palette.css` or `tokens.css`.
- **Contrast.** `--text`, `--text-secondary`, `--text-muted`, `--accent`,
  `--pos`, `--neg`, `--warn` pass WCAG AA (4.5:1) on `--bg`, `--surface`,
  `--surface-raised` and `--surface-overlay`; `--on-accent` passes on
  `--accent-fill` and `--accent-fill-hi`. A spec-table value that fails is
  adjusted until it passes, and the spec table is amended in the same
  commit. `--text-faint` (`#6b7280`) is a rule/divider/disabled-glyph
  colour, never text (correction 13).
- **Colour is never the only cue.** Every P&L, R and return figure carries
  an explicit sign, negatives with U+2212 `−` (correction 5); direction
  cells keep their `sb-direction-arrow` glyph.
- **Density.** `RowDensity = 'dense' | 'comfortable'` (never "compact":
  that names `isNarrow()` and the table column-set `Density`). Dense is
  the default. Density applies only under
  `@media (min-width: 1024px) and (pointer: fine)`; at `max-width: 1023px`
  or `(pointer: coarse)` the touch block (`--row-h`/`--control-h` 44px,
  16px control text, `--hit-min` 44px) wins. Entry, stop, target, size and
  risk-money figures render at ≥ 14px in both densities.
- **Breakpoints.** Width media queries use only 639/640/1023/1024/1439/1440/1919/1920
  (`breakpoint-guard.spec.ts`). `sm` (640–1023) is tablet, `md` (≥ 1024)
  desktop.
- **Destructive actions** (killswitch, restart bot, stop bot, clear log,
  discard settings, clear trades, close all, any delete) live only in the
  `sb-page` `[page-actions]` slot and always open `sb-confirm-dialog`:
  the killswitch as `danger`, everything else as `danger-quiet`. The
  command palette never registers one.
- **Risk and performance KPIs** (spec §5.2): risk tiles show money and %
  of account side by side (`riskUnits`), never one unit alone; performance
  strips put ExpR first and win rate after, every performance KPI shows
  `N=<n>` with the existing small-N cue (`StatTile.thin`, `MIN_SAMPLE_N`),
  and states paper / pre-cost / pre-tax in its hint, reusing v194's
  metric-basis wording (its exported caveat constant in `stat-tile.ts`).
- Every panel keeps its v194 hint text; no explanatory text is dropped.
  New explanation goes into `sb-hint` or visible text, never `title`
  (v194's `title-usage.spec.ts` gate stays green).
- Pinning specs are **updated, never deleted**. The only deleted specs:
  `frontend/src/app/ui/motion/route-entrance.spec.ts`,
  `frontend/src/app/ui/motion/no-replay.spec.ts`, and the shell's
  expand/collapse, overlay, ambient and wordmark cases in `shell.spec.ts`,
  each named in the commit that removes its feature.
- Every UI change is designed for, and checked at, 390, 768 and 1440
  (`docs/claude/ui-design.md` § Checklist). The layout audit runs once for
  the plan, in V195-36, against a local instance; tasks rely on unit
  tests and, where a task says so, a Playwright screenshot.
- Browsers are driven by Playwright only. Local instances log in with
  `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD`, loaded inside the script and
  never printed, echoed or logged.
- Every Python function stays under cyclomatic complexity 15
  (`scripts/dev/complexity_gate.py`); every TypeScript function is held to
  the same limit by `task-reviewer` and split by `docs/claude/code-complexity.md`
  (correction 16).
- Commits: frontend and backend changes go in separate commits, except
  V195-2 (one commit: the regenerated fixture and `THEME` cannot be green
  apart). No `VERSION.json` edit in any task (the bump is `/close-out`'s,
  from the `Bump:` line).

### Standard task close

Every task ends with `Close: standard (test: <path>)`, meaning these steps,
in order, and spells out only its deviations:

1. `git rev-parse --show-toplevel` prints the v195 worktree, and
   `git -C E:/Documents/Private/Projects/Discord-Bot status --short` shows
   nothing this task wrote into the main tree.
2. The narrow run of `<path>` is green (`0 failed`, `0 xfailed`):
   `.py` → `python scripts/dev/testrun.py file <path>`;
   `.spec.ts` → `npm --prefix "$WT/frontend" test -- --watch=false --include <path without the frontend/ prefix>`,
   then the whole frontend run and `npm --prefix "$WT/frontend" run lint`;
   `.mjs` → `node --test <path>`.
3. `python scripts/dev/complexity_gate.py` → exit 0.
4. `git add` the task's files by name and commit
   `<feat|fix|test|docs|chore|refactor>(v195): <summary> (V195-<n>)`, ending with
   the `Co-Authored-By:` trailer from the session's attribution reminder.
   A task touching both `swingbot/` and `frontend/` makes two commits
   (except V195-2, see Global Constraints).

## Parallelisation

- **Phase 1 tokens, V195-1 → V195-2 → V195-3 → V195-4 → V195-5 → V195-6,
  sequential**: V195-1 and V195-2 both edit `chart_style.py` and
  `test_chart_theme.py`; V195-2, V195-3, V195-5 and V195-6 all edit
  `tokens.css`, `tokens.spec.ts` and `resolved_tokens.json`; V195-4 and
  V195-5 both edit `shell.css`, `motion.css` and `motion-css.spec.ts`
  (V195-5 deletes `--glow-ambient` only after V195-4 removed its consumer).
- **V195-7** (`format.ts`, `risk-units.ts`, format specs) is file-disjoint
  from the token tasks and may run beside V195-3..V195-6.
- **Phase 2 primitives, V195-8 → V195-13**: after V195-6 (they read the
  final tokens and the `.sb-lift`-free markup). Sequential where named:
  V195-8 and V195-9 both edit `layout.ts` (Drawer/Panel) and `gallery.ts`;
  V195-11 and V195-12 both edit `stat-tile.ts`/`metric-card.ts` specs'
  neighbours (`async.ts` consumers); V195-13 edits `trades.columns.ts`
  and `dashboard.ts`, which V195-8 also edits. Run them in id order.
- **Phase 3 shell, after V195-13**: V195-14 (`icon.ts`, `hint.ts`) and
  V195-15 (`shell/nav.ts`, `breadcrumb.ts`, `route-title.service.ts`) are
  file-disjoint and may run in parallel. V195-16 → V195-17 → V195-18 are
  sequential (all rewrite `shell.html`/`shell.css`/`shell.ts`/`shell.spec.ts`)
  and start after both V195-14 and V195-15. V195-19 (new files
  `search-index.store.ts`, `palette-items.ts`) needs only V195-15
  (`NAV_GROUPS`) and may run beside V195-16..V195-18. V195-20 after
  V195-18 and V195-19 (it mounts in the shell and consumes both).
- **Phase 4, V195-21** after V195-20 (spec: phases sequential; it consumes
  `RouteTitleService.detail` and the primitives).
- **Phase 5 lanes, after V195-21**, file-disjoint:
  - **System + Risk** V195-22 → V195-23 → V195-24 → V195-25: V195-22 and
    V195-23 edit `system.store.ts` and `risk.store.ts`; V195-23 and V195-25
    edit `risk.ts` and `risk.spec.ts`; V195-23 and V195-24 edit `system.ts`
    and `scan-tab.ts`.
  - **Dashboard + Watchlist** V195-26 → V195-27 → V195-28: V195-26 and
    V195-27 edit `dashboard.spec.ts`; V195-28 runs after them only to keep
    the lane one implementer (no shared file).
  - **Review** V195-29 → V195-30 → V195-31: V195-29 and V195-30 both edit
    `trades.routes`-scoped specs and `trade-drawer` neighbours; V195-31
    (Calendar, Cancels) has no shared file and may run in parallel.
  - **Insights** V195-32.
  - **V195-33 after every Phase 5 task** (its `workspace-consistency`
    assertion needs every route on `sb-page`; it also edits `gallery.ts`).
- **Phase 6, V195-34** needs only V195-2 (token values) and may run beside
  Phases 3–5; it creates `docs/superpowers/results/2026-10-25-v195-layout-audit.md`,
  which V195-36 appends to, so it lands before V195-36.
- **V195-35** (`frontend/scripts/` only) needs the rail markup from V195-16
  and may run beside V195-17..V195-34.
- **V195-36 last.**

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-25-v195-graphite-frontend-redesign_1-palette-and-shape-tokens.md` | V195-1..V195-3 | worktree; Discord `accent`; Graphite palette; radii, flat panels, 12px floor |
| 2 | `2026-10-25-v195-graphite-frontend-redesign_2-decoration-and-density.md` | V195-4..V195-6 | ambient and route entrance removed; lift and motion shrink; density |
| 3 | `2026-10-25-v195-graphite-frontend-redesign_3-signs-buttons-panels.md` | V195-7..V195-9 | true minus and `riskUnits`; `danger`/`danger-quiet`; panel and panel header |
| 4 | `2026-10-25-v195-graphite-frontend-redesign_4-controls-kpi-states.md` | V195-10..V195-12 | flat controls; one KPI strip; states and overlays |
| 5 | `2026-10-25-v195-graphite-frontend-redesign_5-tables-hint-nav.md` | V195-13..V195-15 | one pager, never-collapsed columns; `search` icon and `Hint.anchor`; nav model and breadcrumb |
| 6 | `2026-10-25-v195-graphite-frontend-redesign_6-shell-rail-topbar-phone.md` | V195-16..V195-18 | icon rail; top-bar cluster and density menu; phone tab bar and More sheet |
| 7 | `2026-10-25-v195-graphite-frontend-redesign_7-palette-and-page.md` | V195-19..V195-21 | `SearchIndexStore` and ranking; command palette; `sb-page` |
| 8 | `2026-10-25-v195-graphite-frontend-redesign_8-system-regrouping.md` | V195-22..V195-24 | scan health to `SystemStore`; Providers tab; System on `sb-page` |
| 9 | `2026-10-25-v195-graphite-frontend-redesign_9-risk-and-dashboard.md` | V195-25..V195-27 | Risk on `sb-page`; performance strip ExpR first; Dashboard on `sb-page` |
| 10 | `2026-10-25-v195-graphite-frontend-redesign_10-watchlist-and-review.md` | V195-28..V195-30 | Watchlist and ticker detail; Trades; trade and plan detail |
| 11 | `2026-10-25-v195-graphite-frontend-redesign_11-calendar-insights-gallery.md` | V195-31..V195-33 | Calendar, day, Cancels; Analytics, Research, Reports; Versions, gallery, consistency gate |
| 12 | `2026-10-25-v195-graphite-frontend-redesign_12-charts-audit-release.md` | V195-34..V195-36 | chart theme and alert image; `rail-label` audit check; full suite, audit, merge |

## Task ledger

| Task | Title | Part | Model | Spec § | Files created / modified | Creates | Consumes |
|---|---|---|---|---|---|---|---|
| V195-1 | Worktree (v194-merged precondition); Discord `THEME` gains `accent` on the old palette, `ENTRY_COLOR` reads it, `STYLE_PINS` row `v195a` | 1 | sonnet | Phase 6; Spec corrections | M `swingbot/core/charts/chart_style.py`, `tests/charts/test_chart_theme.py` | worktree branch `2026-10-25-v195-graphite-frontend-redesign`; `THEME["accent"]` (resolved `--accent`); `STYLE_VERSION = "v195a"`; `STYLE_PINS` row `(<digest>, "v195a")`; `COLOUR_CONSTANTS["ENTRY_COLOR"] = "accent"` | `THEME`, `STYLE_VERSION`, `ENTRY_COLOR`, `STYLE_PINS`, `COLOUR_CONSTANTS`, `_theme_digest`, `resolve_tokens` |
| V195-2 | Graphite palette: tier 1 rewritten, tier 2 repointed, `--chart-1..6`/`--quality-4` and alpha tints re-derived, cold-load `--bg`, fixture regenerated, Discord `THEME` values and `STYLE_PINS` row `v195` (one commit) | 1 | sonnet | 1.1; Phase 6; Spec corrections | M `frontend/src/styles/palette.css`, `frontend/src/styles/tokens.css`, `frontend/src/index.html`, `frontend/public/manifest.webmanifest`, `tests/charts/resolved_tokens.json`, `swingbot/core/charts/chart_style.py`, `tests/charts/test_chart_theme.py`, `frontend/src/app/ui/tokens.spec.ts`, `frontend/src/app/ui/contrast.spec.ts`, `frontend/src/app/ui/primitives.spec.ts`, `frontend/src/app/ui/chart-palette.spec.ts`, `docs/superpowers/specs/2026-10-25-v195-graphite-frontend-redesign.md` (only if a value is adjusted for AA) | tier-1 tokens `--graphite-950` `#0d0f12`, `--graphite-900` `#15181d`, `--graphite-850` `#1c2128`, `--graphite-800` `#1f242b`, `--graphite-750` `#23272e`, `--graphite-700` `#2d333b`, `--graphite-500` `#6b7280`, `--grey-400` `#9aa4b2`, `--grey-300` `#c9d1d9`, `--grey-100` `#e6e8eb`, `--steel-400` `#6ea8fe`, `--steel-500`, `--steel-600` (accent fills, values chosen for `--on-accent` ≥ 4.5), `--green-500` `#3fb68b`, `--red-500` `#e5534b`, `--amber-500` `#d29922`, `--violet-400` `#b392f0`; alpha `--graphite-950-a72`, `--green-500-a12`, `--red-500-a12`, `--amber-500-a12`, `--steel-400-a18`, `--violet-400-a14`; `STYLE_VERSION = "v195"`; `STYLE_PINS` row `(<digest>, "v195")` | `THEME`, `STYLE_PINS`, `resolve_tokens`, `resolveToken`, `HEX_ALLOWLIST` |
| V195-3 | Tier-3 shape and type: 6/4/2px radii, flat `--panel-bg`, no panel shadow, flat button fill, 12px micro/chip floor | 1 | sonnet | 1.3; 1.5; 1.2; Spec corrections | M `frontend/src/styles/tokens.css`, `tests/charts/resolved_tokens.json`, `frontend/src/app/ui/tokens.spec.ts`, `frontend/src/app/ui/text-styles.spec.ts`, `frontend/src/app/ui/elevation.spec.ts` | tier-3 values `--panel-radius: 6px`, `--control-radius: 4px`, `--chip-radius: 4px`, `--radius-sm: 2px`, `--panel-bg: var(--surface)`, `--panel-shadow: none`, `--btn-fill: var(--accent-fill)`, `--btn-fill-hover: var(--accent-fill-hi)`; `--text-micro`/`--text-chip` floor `12px` | `--panel-radius`, `--control-radius`, `--chip-radius`, `--panel-bg`, `--panel-shadow`, `--btn-fill`, `--text-micro`, `--text-chip` |
| V195-4 | Shell ambient glow and the route-entrance directive removed; their specs and shell cases retired | 2 | sonnet | 1.2; Testing | M `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.spec.ts`, `frontend/src/app/ui/elevation.spec.ts`; D `frontend/src/app/ui/motion/route-entrance.ts`, `frontend/src/app/ui/motion/route-entrance.spec.ts`, `frontend/src/app/ui/motion/no-replay.spec.ts` | — | `RouteEntrance`, `RouteEntryService`, `.ambient` |
| V195-5 | Lift, entrance keyframes, button glow and ambient drift deleted; `motion.css` shrunk to ~120ms colour transitions, flash, dialog/sheet and the `data-motion` guards; decoration tokens deleted | 2 | sonnet | 1.2; Testing | M `frontend/src/styles/motion.css`, `frontend/src/styles/tokens.css`, `tests/charts/resolved_tokens.json`, `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/figure.ts`, `frontend/src/app/ui/chart-container.ts`, `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/metric-card.ts`, `frontend/src/app/ui/stat-strip.ts`, `frontend/src/app/ui/motion-css.spec.ts`, `frontend/src/app/ui/primitives.spec.ts`, `frontend/src/app/ui/elevation.spec.ts`, `frontend/src/app/ui/tokens.spec.ts` | deleted tokens `--glow-ambient`, `--glow-accent`, `--panel-shadow-lift`, `--dur-enter`; deleted classes `.sb-lift`, `.sb-enter`, `.sb-entering`; `--dur-ui: 120ms` | `.sb-lift`, `--panel-shadow-lift`, `--glow-accent`, `--glow-ambient`, `--dur-enter`, `MotionService` |
| V195-6 | Density: `DensityService` over `localStorage` `ui.density` (dense default, try/catch), `data-density` on `<html>`, desktop fine-pointer token block, touch block widened to coarse pointers, order figures ≥ 14px | 2 | sonnet | 1.4; Spec corrections; Testing | C `frontend/src/app/ui/density.service.ts`, `frontend/src/app/ui/density.service.spec.ts`; M `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `tests/charts/resolved_tokens.json`, `frontend/src/app/app.config.ts`, `frontend/src/app/ui/tokens.spec.ts`, `frontend/src/app/ui/register.spec.ts`, `frontend/src/app/ui/hit-area.spec.ts` | `RowDensity = 'dense' \| 'comfortable'`; `DENSITY_PREF_KEY = 'ui.density'`; `interface DensityStorage { get(key: string): string \| null; set(key: string, value: string): void }`; `DENSITY_STORAGE` (`InjectionToken<DensityStorage>`, root factory over `localStorage`, every call in try/catch); `readDensity(storage: DensityStorage): RowDensity`; `DensityService` (root: `density: Signal<RowDensity>`, `set(d: RowDensity): void`, writes `document.documentElement.dataset['density']`); tokens `--cell-pad-y`, `--cell-pad-x`, `--panel-pad`; `.register-instrument` `--register-figure: var(--text-body)` | `--row-h`, `--control-h`, `--hit-min`, `--text-table`, `--register-figure`, `provideAppInitializer` |
| V195-7 | True minus in `pct`, `money`, `rMultiple`; `MINUS`; `riskUnits` (money · % of account); sign spec | 3 | sonnet | 1.1; 5.2; Spec corrections; Testing | C `frontend/src/app/ui/risk-units.ts`, `frontend/src/app/ui/risk-units.spec.ts`; M `frontend/src/app/ui/format.ts`, `frontend/src/app/ui/format.spec.ts`, `frontend/src/app/ui/unit-format.spec.ts`, and every spec asserting an ASCII `-` negative from these helpers (named in the task from a grep) | `MINUS = '\u2212'` (exported from `format.ts`); `riskUnits(pct: number \| null \| undefined, balance: number \| null \| undefined, unit: string): string` (`amount(pct / 100 * balance, unit, 0) + ' · ' + <v194 risk-percent formatter>(pct)`; `ABSENT` money part when balance or pct is null; `ABSENT` whole when pct is null) | `pct`, `money`, `rMultiple`, `signed`, `amount`, `ABSENT`, `inUnit` |
| V195-8 | Button variants: `danger` solid (killswitch only), new `danger-quiet`; every existing `danger` call site renamed; `ConfirmDialog.dangerVariant` | 3 | sonnet | Phase 2; Phase 4; Spec corrections | M `frontend/src/app/ui/button.ts`, `frontend/src/app/ui/button.spec.ts`, `frontend/src/app/ui/confirm-dialog.ts`, `frontend/src/app/ui/controls.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/system/logs-tab.ts`, `frontend/src/app/workspaces/system/scan-tab.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`, `frontend/src/app/workspaces/analytics/tabs/tuning.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/gallery/gallery.ts` | `ButtonVariant` member `'danger-quiet'`; `ConfirmDialog.dangerVariant` (`input<'danger' \| 'danger-quiet'>('danger-quiet')`, used when `destructive()`) | `ButtonVariant`, `Button`, `ConfirmDialog`, `destructive` |
| V195-9 | Panel, panel header and section head re-skinned: surface + hairline, 13px semibold sentence-case title, hint beside it, quiet meta right, `[header-actions]` slot | 3 | sonnet | Phase 2; 1.3 | M `frontend/src/app/ui/layout.ts`, `frontend/src/app/ui/layout.spec.ts`, `frontend/src/app/ui/panel-header.ts`, `frontend/src/app/ui/panel-header.spec.ts`, `frontend/src/app/ui/section-head.ts`, `frontend/src/app/ui/section-head.spec.ts`, `frontend/src/styles.css`, `frontend/src/app/ui/text-styles.spec.ts` | `sb-panel-header` projection slot `[header-actions]` | `Panel`, `PanelHeader`, `SectionHead`, `Hint` |
| V195-10 | Flat controls: chip, segmented, form controls, filter bar, control bar, toolbar (4px radius, accent only on primary/selected) | 4 | sonnet | Phase 2 | M `frontend/src/app/ui/chip.ts`, `frontend/src/app/ui/chip.spec.ts`, `frontend/src/app/ui/segmented.ts`, `frontend/src/app/ui/segmented.spec.ts`, `frontend/src/app/ui/form-controls.ts`, `frontend/src/app/ui/form-controls.spec.ts`, `frontend/src/app/ui/filter-bar.ts`, `frontend/src/app/ui/filter-bar.spec.ts`, `frontend/src/app/ui/control-bar.ts`, `frontend/src/app/ui/toolbar.ts`, `frontend/src/app/ui/toolbar.spec.ts` | — | `Chip`, `Segmented`, `FilterBar`, `ControlBar`, `Toolbar`, `--control-radius`, `--chip-radius` |
| V195-11 | One KPI-strip look: stat strip, stat tile and metric card as hairline-split cells in one bordered surface | 4 | sonnet | Phase 2 | M `frontend/src/app/ui/stat-strip.ts`, `frontend/src/app/ui/stat-strip.spec.ts`, `frontend/src/app/ui/stat-tile.ts`, `frontend/src/app/ui/stat-tile.spec.ts`, `frontend/src/app/ui/metric-card.ts`, `frontend/src/app/ui/metric-card.spec.ts`, `frontend/src/styles.css` | — | `StatStrip`, `StatTile`, `MetricCard`, `MIN_SAMPLE_N` |
| V195-12 | Empty, loading and error states in the panel body, one style each; dialogs, drawer and toasts on the overlay surface with the one shadow token | 4 | sonnet | Phase 2 | M `frontend/src/app/ui/empty-state.ts`, `frontend/src/app/ui/empty-state.spec.ts`, `frontend/src/app/ui/spinner.ts`, `frontend/src/app/ui/panel-error.ts`, `frontend/src/app/ui/panel-error.spec.ts`, `frontend/src/app/ui/async.ts`, `frontend/src/app/ui/async.spec.ts`, `frontend/src/app/ui/confirm-dialog.ts`, `frontend/src/app/ui/layout.ts`, `frontend/src/app/shell/toast-host.ts`, `frontend/src/app/shell/toast-host.spec.ts`, `frontend/src/app/ui/elevation.spec.ts` | — | `EmptyState`, `Spinner`, `PanelError`, `Async`, `Drawer`, `--shadow-overlay` |
| V195-13 | Tables: one pager at the bottom (top pager deleted), density-driven rows, muted micro header; never-collapsed columns (ticker, side, stop, risk money where carried, R/P&L, badge tier) | 5 | sonnet | Phase 2; Spec corrections | M `frontend/src/app/ui/data-table/data-table.ts`, `frontend/src/app/ui/data-table/data-table.spec.ts`, `frontend/src/app/workspaces/trades/trades.columns.ts`, `frontend/src/app/workspaces/trades/trades.columns.spec.ts`, `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` | `DataTable.showHeaderPager` deleted | `DataTable`, `tradeColumns`, `inlineFrom`, `isInline`, `--row-h`, `--cell-pad-y`, `--cell-pad-x` |
| V195-14 | `search` icon; `Hint.anchor` label mode (sibling popover opened by the anchor's hover and focus, no extra tab stop) | 5 | sonnet | Phase 3; Spec corrections | M `frontend/src/app/ui/icon.ts`, `frontend/src/app/ui/icon.spec.ts`, `frontend/src/app/ui/hint.ts`, `frontend/src/app/ui/hint.spec.ts` | `'search'` in `ICON_NAMES`; `Hint.anchor` (`input<HTMLElement \| null>(null)`; non-null renders no trigger button and opens on the anchor's `mouseenter`/`focus`, closes on `mouseleave`/`blur`/Escape, sets the anchor's `aria-describedby`) | `ICON_NAMES`, `IconName`, `Hint` |
| V195-15 | Nav model (four groups, phone tabs), breadcrumb derivation, `RouteTitleService.detail`, `sb-breadcrumb` | 5 | sonnet | 5.1; Phase 3 | C `frontend/src/app/shell/nav.ts`, `frontend/src/app/shell/nav.spec.ts`, `frontend/src/app/shell/breadcrumb.ts`, `frontend/src/app/shell/breadcrumb.spec.ts`; M `frontend/src/app/routing/route-title.service.ts`, `frontend/src/app/routing/route-title.service.spec.ts` | `interface NavEntry { path: string; label: string; icon: IconName }`; `interface NavGroup { id: string; label: string; entries: readonly NavEntry[] }`; `NAV_GROUPS` (Monitor: Dashboard, Watchlist, Risk · Review: Trades, Calendar, Cancels · Insights: Analytics, Research, Reports · System: System, Versions); `PHONE_TABS` (`/dashboard`, `/watchlist`, `/trades`, `/risk`); `navEntryFor(url: string): { group: NavGroup; entry: NavEntry } \| null`; `breadcrumbFor(url: string, detail: string \| null): string[]`; `detailCrumb(ticker: string \| null, id: string \| number \| null): string` (`'NVDA #812'`); `RouteTitleService.detail` (`Signal<string \| null>`, cleared on every title update); `RouteTitleService.setDetail(detail: string \| null): void`; `Breadcrumb` (`sb-breadcrumb`, not a heading) | `RouteTitleService`, `SubtitleTitleStrategy`, `IconName` |
| V195-16 | Icon rail: 48px always-collapsed rail in four groups, dividers without text, `Hint.anchor` labels, active bar; 40px top bar with the breadcrumb; shell `<h1>` removed; expand/collapse, overlay, hamburger and `shell.sidebar` read/write deleted | 6 | sonnet | Phase 3; Spec corrections; Rollback | M `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts`, `frontend/src/app/shell/nav-indicator.ts`, `frontend/src/app/shell/nav-indicator.spec.ts`, `frontend/src/app/shell/route-focus.spec.ts` | rail markup `nav.rail` > `ul.nav[aria-label]` > `li > a.rail-link[aria-label]` + sibling `sb-hint` (anchor mode); CSS `--rail-w: 48px`, `--topbar-h: 40px`; deleted `railed`, `overlay`, `overlayOpen`, `toggleSidebar`, `userCollapsed`, `applyStoredSidebar` | `NAV_GROUPS`, `Breadcrumb`, `Hint.anchor`, `NavIndicator`, `focusWorkspaceHeading` |
| V195-17 | Top-bar right cluster: killswitch chip (all devices, links to `/risk`), freshness chip (all devices), scan progress, clock, profile menu with Density; tape strip under the top bar | 6 | sonnet | Phase 3; 1.4 | C `frontend/src/app/shell/killswitch-chip.ts`, `frontend/src/app/shell/killswitch-chip.spec.ts`, `frontend/src/app/shell/freshness-chip.ts`, `frontend/src/app/shell/freshness-chip.spec.ts`; M `frontend/src/app/stores/connection.store.ts`, `frontend/src/app/stores/connection.store.spec.ts`, `frontend/src/app/shell/profile-menu.ts`, `frontend/src/app/shell/profile-menu.spec.ts`, `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts`, `frontend/src/app/shell/tape/tape.css` | `KillswitchChip` (`sb-killswitch-chip`, `on = input<boolean \| null>(null)`, renders "Armed" / "Halted" / nothing for null, `routerLink="/risk"`); `FreshnessChip` (`sb-freshness-chip`, `at = input<string \| null>(null)`, `now = input.required<number>()`, renders "Scan <age>" or "No scan yet"); `ConnectionStore.botLastSuccess` (state, from `ScanStatus.bot_last_success`); `ProfileMenu.density` (`input<RowDensity>('dense')`); `ProfileMenu.densityChanged` (`output<RowDensity>()`) | `DensityService`, `RowDensity`, `ScanProgressStrip`, `Tape`, `Segmented`, `killswitchOn`, `botLastSeen` |
| V195-18 | Phone: top bar collapses to title, killswitch and freshness chips and a search icon; bottom tab bar (56px + safe area); More sheet with the remaining pages and the search field | 6 | sonnet | Phase 3 | C `frontend/src/app/shell/phone-tab-bar.ts`, `frontend/src/app/shell/phone-tab-bar.spec.ts`, `frontend/src/app/shell/more-sheet.ts`, `frontend/src/app/shell/more-sheet.spec.ts`; M `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts` | `PhoneTabBar` (`sb-phone-tab-bar`, `moreOpen = input(false)`, `moreRequested = output<void>()`); `MoreSheet` (`sb-more-sheet`, `open = input(false)`, `closed = output<void>()`, `searchRequested = output<void>()`) | `PHONE_TABS`, `NAV_GROUPS`, `KillswitchChip`, `FreshnessChip`, `ViewportService`, `FocusTrap` |
| V195-19 | `SearchIndexStore` (root, lazy, session cache, 60s refresh, failure flag) and palette items and ranking | 7 | sonnet | 3.1; Testing | C `frontend/src/app/stores/search-index.store.ts`, `frontend/src/app/stores/search-index.store.spec.ts`, `frontend/src/app/shell/palette/palette-items.ts`, `frontend/src/app/shell/palette/palette-items.spec.ts` | `SearchIndexStore` (root; state `tickers: Ticker[]`, `trades: TradeRow[]`, `loadedAt: number \| null`, `failed: boolean`; `ensure(now?: number): void` fetches `api.tickers()` and `api.trades({ per_page: 200, sort: '-opened_at' })` on first call and again when `now - loadedAt > SEARCH_INDEX_TTL_MS`); `SEARCH_INDEX_TTL_MS = 60_000`; `type PaletteGroup = 'tickers' \| 'trades' \| 'pages' \| 'preferences'`; `interface PaletteItem { key: string; group: PaletteGroup; label: string; sub?: string; route: string \| null; queryParams?: Record<string, string>; density?: RowDensity; recency?: number }`; `TAB_PAGES`; `PREFERENCE_ITEMS`; `pageItems(groups: readonly NavGroup[]): PaletteItem[]`; `tickerItems(tickers: readonly Ticker[]): PaletteItem[]`; `tradeItems(rows: readonly TradeRow[]): PaletteItem[]` (`/plans/:id` for an unfilled plan, else `/trades/:id`); `rankPaletteItems(query: string, items: readonly PaletteItem[]): PaletteItem[]`; `emptyQueryItems(items: readonly PaletteItem[]): PaletteItem[]` (pages, then the five most recent trades) | `NAV_GROUPS`, `tickers`, `trades`, `Ticker`, `TradeRow`, `RowDensity`, `MarketIndexStore` |
| V195-20 | Command palette: Ctrl/⌘K, `/` outside text fields and the top-bar trigger; overlay (sheet on phone), focus trap, Esc, ↑/↓/Enter; "tickers unavailable" row; no destructive action registered | 7 | sonnet | 3.1; Testing | C `frontend/src/app/shell/palette/command-palette.ts`, `frontend/src/app/shell/palette/command-palette.spec.ts`; M `frontend/src/app/shell/shell.ts`, `frontend/src/app/shell/shell.html`, `frontend/src/app/shell/shell.css`, `frontend/src/app/shell/shell.spec.ts`, `frontend/src/app/shell/more-sheet.ts` | `CommandPalette` (`sb-command-palette`, `open = input(false)`, `closed = output<void>()`); `isTypingTarget(el: Element \| null): boolean` (exported from `command-palette.ts`); shell `paletteOpen` signal and `openPalette()` | `SearchIndexStore`, `rankPaletteItems`, `emptyQueryItems`, `pageItems`, `tickerItems`, `tradeItems`, `PREFERENCE_ITEMS`, `DensityService`, `FocusTrap`, `MoreSheet`, `searchRequested` |
| V195-21 | `sb-page` template: header (one `<h1>`, description, `[page-actions]`), `[page-scope]`, `[page-kpis]`, `[page-primary]`, `[page-secondary]` (2 columns at `lg`); empty slots take no space | 7 | sonnet | Phase 4; Spec corrections; Testing | C `frontend/src/app/ui/page.ts`, `frontend/src/app/ui/page.spec.ts` | `Page` (`sb-page`; `heading = input<string \| null>(null)` falling back to `RouteTitleService.title()`; `description = input<string \| null>(null)` falling back to `RouteTitleService.subtitle()`); slots `[page-actions]`, `[page-scope]`, `[page-kpis]`, `[page-primary]`, `[page-secondary]` | `RouteTitleService`, `ConfirmDialog`, `dangerVariant`, `danger-quiet` |
| V195-22 | `SystemStore` reads `api.risk()` for scan health and data source; `providers` tab and `resolveProviders`; `systemTab` learns `providers`; tab order Scan · Providers · Settings · Logs | 8 | sonnet | 5.1; Spec corrections | M `frontend/src/app/stores/system.store.ts`, `frontend/src/app/stores/system.store.spec.ts`, `frontend/src/app/workspaces/system/system.routes.ts` | `SYSTEM_TABS = ['scan', 'providers', 'settings', 'logs']`; `SystemStore` state `risk: Risk \| null`, `riskError: string \| null`; computeds `SystemStore.scanDurations`, `SystemStore.scanLatestS`, `SystemStore.scanSlowdown`, `SystemStore.dataSources`; method `resolveProviders()` (`forkJoin` of `resolveHealth()` and the `/risk` read) | `SYSTEM_TABS`, `SystemTab`, `resolveTab`, `resolveHealth`, `systemTab`, `risk`, `ScanHealth`, `DataSourcesHealth` |
| V195-23 | Providers tab (Data providers, Data source, Scan health, Swallowed errors); Scan tab and Risk lose those panels; `RiskStore` drops the four computeds | 8 | sonnet | 5.1; Testing | C `frontend/src/app/workspaces/system/providers-tab.ts`, `frontend/src/app/workspaces/system/providers-tab.spec.ts`; M `frontend/src/app/workspaces/system/system.ts`, `frontend/src/app/workspaces/system/scan-tab.ts`, `frontend/src/app/workspaces/system/scan-tab.spec.ts`, `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`, `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/stores/risk.store.spec.ts` | `ProvidersTab` (`sb-providers-tab`) | `SystemStore.scanDurations`, `SystemStore.scanLatestS`, `SystemStore.scanSlowdown`, `SystemStore.dataSources`, `resolveProviders`, `ProviderHealthPanel`, `SwallowedErrorsPanel`, `RiskStore` |
| V195-24 | System on `sb-page`: tab bar in the scope bar; restart bot, stop bot, clear log and discard settings in `[page-actions]` per tab, each `danger-quiet` behind `sb-confirm-dialog` | 8 | sonnet | 5.2; Phase 4 | M `frontend/src/app/workspaces/system/system.ts`, `frontend/src/app/workspaces/system/scan-tab.ts`, `frontend/src/app/workspaces/system/scan-tab.spec.ts`, `frontend/src/app/workspaces/system/logs-tab.ts`, `frontend/src/app/workspaces/system/logs-tab.spec.ts`, `frontend/src/app/workspaces/system/settings-tab.ts`, `frontend/src/app/workspaces/system/settings-tab.spec.ts`; C `frontend/src/app/workspaces/system/system.spec.ts` | — | `Page`, `ProvidersTab`, `ConfirmDialog`, `dangerVariant`, `restartBot`, `clearLogs`, `SYSTEM_TABS` |
| V195-25 | Risk on `sb-page`: killswitch control in `[page-actions]` (`danger`, confirm `dangerVariant="danger"`); KPI strip open risk and cap headroom as money · %, top sector, max cluster; portfolio heat primary; rest secondary | 9 | sonnet | 5.2; 5.1; Phase 4 | M `frontend/src/app/workspaces/risk/risk.ts`, `frontend/src/app/workspaces/risk/risk.spec.ts`, `frontend/src/app/stores/risk.store.ts`, `frontend/src/app/stores/risk.store.spec.ts` | `RiskStore` state `balance: number \| null` (from `api.dashboard()` in `resolve()`, failure leaves `null` and does not fail the route); `RiskStore.headroomPct` (computed, `cap_pct - open_pct`, `null` when either is null) | `Page`, `riskUnits`, `dangerVariant`, `toggleKillswitch`, `openHeatPct`, `heatCapPct`, `sectorHeat`, `clusters`, `dashboard`, `account_balance`, `StatTile` |
| V195-26 | Trading performance: ExpR first, win rate after, `N=` on every performance KPI with the small-N cue, basis (paper, pre-cost, pre-tax) in each hint; mobile summary matches | 9 | sonnet | 5.2; Spec corrections | M `frontend/src/app/workspaces/dashboard/panels/trading-performance.ts`, `frontend/src/app/workspaces/dashboard/panels/trading-performance.spec.ts` | — | `TradingPerformance`, `MetricCard`, `MIN_SAMPLE_N`, `expectancyN`, `winRateN` |
| V195-27 | Dashboard on `sb-page`: KPI strip (ExpR, win rate, open risk money · % linking to `/risk`, realised in period, open positions); Close all in `[page-actions]` (`danger-quiet`); open positions primary; recent activity and movers secondary | 9 | sonnet | 5.2; 5.1; Phase 4; 1.4 | M `frontend/src/app/workspaces/dashboard/dashboard.ts`, `frontend/src/app/workspaces/dashboard/dashboard.spec.ts`, `frontend/src/app/workspaces/dashboard/positions-table.ts`, `frontend/src/app/workspaces/dashboard/positions-table.spec.ts` | — | `Page`, `riskUnits`, `balance`, `riskUsedPct`, `expectancyR`, `winRate`, `openTrades`, `dangerVariant` |
| V195-28 | Watchlist and ticker detail on `sb-page` (ticker detail: breadcrumb detail segment = symbol, no scope bar; order figures ≥ 14px) | 10 | sonnet | 5.2; Phase 4; 1.4 | M `frontend/src/app/workspaces/watchlist/watchlist.ts`, `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, `frontend/src/app/workspaces/watchlist/ticker-detail.ts`, `frontend/src/app/workspaces/watchlist/ticker-detail.spec.ts` | — | `Page`, `setDetail`, `SectionHead` |
| V195-29 | Trades on `sb-page`: toolbar in the scope bar, trade table primary, Clear open / Clear history in `[page-actions]` (`danger-quiet`) | 10 | sonnet | 5.2; Phase 4 | M `frontend/src/app/workspaces/trades/trades.ts`, `frontend/src/app/workspaces/trades/trades.spec.ts` | — | `Page`, `Toolbar`, `ToolbarControl`, `dangerVariant`, `TRADES_CONTROLS` |
| V195-30 | Trade detail and plan detail on `sb-page`: breadcrumb detail `NVDA #812`, no scope bar, delete in `[page-actions]`, entry/stop/target/size/risk figures ≥ 14px | 10 | sonnet | 5.2; 1.4; Phase 4 | M `frontend/src/app/workspaces/trades/trade-detail.ts`, `frontend/src/app/workspaces/trades/trade-detail.spec.ts`, `frontend/src/app/workspaces/plans/plan-detail.ts`, `frontend/src/app/workspaces/plans/plan-detail.spec.ts`, `frontend/src/app/workspaces/dashboard/trade-drawer.ts`, `frontend/src/app/workspaces/dashboard/trade-drawer.spec.ts` | — | `Page`, `setDetail`, `detailCrumb`, `dangerVariant` |
| V195-31 | Calendar, calendar day (detail segment = long date) and Cancels on `sb-page` | 11 | sonnet | 5.2; Phase 4 | M `frontend/src/app/workspaces/calendar/calendar.ts`, `frontend/src/app/workspaces/calendar/calendar.spec.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.ts`, `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts`, `frontend/src/app/workspaces/cancels/cancels.ts`, `frontend/src/app/workspaces/cancels/cancels.spec.ts` | — | `Page`, `setDetail`, `StatStrip`, `StatTile` |
| V195-32 | Analytics (scope bar = `scope-bar.ts` + tabs), Research and Reports on `sb-page`; performance strips ExpR first with N | 11 | sonnet | 5.2; Phase 4 | M `frontend/src/app/workspaces/analytics/analytics.ts`, `frontend/src/app/workspaces/analytics/analytics.spec.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.ts`, `frontend/src/app/workspaces/analytics/tabs/overview.spec.ts`, `frontend/src/app/workspaces/research/research.ts`, `frontend/src/app/workspaces/research/research.spec.ts`, `frontend/src/app/workspaces/reports/reports.ts`, `frontend/src/app/workspaces/reports/reports.spec.ts` | — | `Page`, `TabBar`, `StatTile`, `MIN_SAMPLE_N` |
| V195-33 | Versions on `sb-page`; `/ui` gallery re-laid out as the primitive reference (`danger` / `danger-quiet`, `sb-page`, KPI strip, rail label hint); `workspace-consistency` asserts every route entry uses `sb-page` | 11 | sonnet | 5.1; 5.2; Testing | M `frontend/src/app/workspaces/versions/versions.ts`, `frontend/src/app/workspaces/versions/versions.spec.ts`, `frontend/src/app/workspaces/gallery/gallery.ts`, `frontend/src/app/workspaces/gallery/gallery.spec.ts`, `frontend/src/app/workspaces/workspace-consistency.spec.ts` | `PAGE_ROUTES` (spec constant: the route entry component files that must contain `<sb-page` and import `Page`) | `Page`, `workspaceSources`, `Hint.anchor` |
| V195-34 | Charts: in-app chart chrome and plan lines read tokens (entry accent solid, target/stop dashed pos/neg); SVG primitives hold no chart-local colour (source-scan spec); before/after Discord alert image recorded | 12 | sonnet | Phase 6; Testing | M `frontend/src/app/ui/chart/chart-theme.ts`, `frontend/src/app/ui/chart/chart-theme.spec.ts`, `frontend/src/app/ui/chart/plan-lines.spec.ts`; C `frontend/src/app/ui/chart/svg-colour.spec.ts`, `docs/superpowers/results/2026-10-25-v195-layout-audit.md` | `docs/superpowers/results/2026-10-25-v195-layout-audit.md` (sections `## Alert image`, `## Layout audit`, `## Notes`) | `chartPalette`, `chartOptions`, `CHART_CHROME`, `ENTRY_COLOR`, `THEME` |
| V195-35 | Layout audit: `ROUTES` gains `/system?tab=providers`; `CHECKS` gains `rail-label` after v194's hint check; pure `railLabelVerdict`; Playwright focus pass over the rail at widths ≥ 640 | 12 | sonnet | Phase 7 | M `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.mjs` | `railLabelVerdict(entry: { name: string, hintVisible: boolean }) -> { ok: boolean, reason: 'no-name' \| 'hint-hidden' \| null }`; `CHECKS` member `'rail-label'` (ninth, last); `ROUTES` member `'/system?tab=providers'` (29 routes); `auditRailLabels(page, width)` (in `layout-audit.mjs`, skips widths < 640) | `ROUTES`, `CHECKS`, `countByCheck`, `auditWidth` |
| V195-36 | Full suite; local layout audit at 390/768/1440 (every route, `rail-label` included); results doc (audit, orphaned `shell.sidebar`, before/after image); merge to `main`; post-deploy production audit recorded | 12 | haiku | Phase 7; Rollback | M `docs/superpowers/results/2026-10-25-v195-layout-audit.md`, `frontend/scripts/layout-audit.allow.json` (only for a finding the task records as accepted) | — | `railLabelVerdict`, `CHECKS`, `ROUTES` |
