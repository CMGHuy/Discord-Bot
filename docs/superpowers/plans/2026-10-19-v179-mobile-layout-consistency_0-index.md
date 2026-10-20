# v179 — Mobile layout consistency: compact rows, a trade drawer, one style per primitive: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Dispatch `task-implementer` at each task's `**Model:**` tier and escalate per `docs/claude/model-routing.md`. **Never read a part whole**: `grep -n "^### Task V179-9:" -A 400 docs/superpowers/plans/2026-10-19-v179-mobile-layout-consistency_3-tables.md`.

**Bump:** ui minor
**Edge:** none (integrity) — readability and touch ergonomics of the admin UI; no signal, gate, stop, size or badge changes.
**Screen:** exempt (integrity)
**Spec:** [2026-10-19-v179-mobile-layout-consistency-design.md](../specs/2026-10-19-v179-mobile-layout-consistency-design.md) — §6a and §6b override the earlier sections.
**Brief:** `.superpowers/briefs/2026-10-19-v179-mobile-layout-consistency.md`
**Worktree:** every task runs in `.claude/worktrees/2026-10-19-v179-mobile-layout-consistency` (branch of the same name, created in V179-1; `docs/claude/document-lifecycle.md`). V179-21 merges to `main` and runs `/panel` and `/close-out`.

## Goal

The partner opened every admin screen on a phone and found it hard to use. On
a 390px screen the Trades, Dashboard, Watchlist and Research tables show two
columns and hide the rest behind a thin scrollbar; Analytics → Attribution and
Partials push the page sideways; tab bars run off the edge; the same primitive
(a stat tile, a filter row, a panel header) looks different on each page; text
in one row sits at different heights; labels drop to 9.9px; and many controls
are 14–34px tall under a thumb. The partner also asked, in their own words, for
the Dashboard to open trades in a drawer and for text in one row to share a
baseline.

Once this ships, a phone user sees each table row as a two-line compact item
(identity and the number a trader checks first, then plan or price context)
and taps it to open a bottom-sheet drawer with every other column the table
shows today, rendered with the same cell templates. The Dashboard opens a
trade in a drawer on every device — side drawer on desktop, bottom sheet on
phone — with a "Paper trade" marker and an "Open full trade →" link; the open
trade sits in the URL as a pushed query parameter, so Back closes it and the
link can be shared. Every primitive has one look: one stat-tile layout, one
filter/control row, one panel header height on one baseline, one numeric font.
Text never falls below 11px (even at the 90% zoom preference), and every
control has a 44px hit area on phone and tablet.

How it works: compact rows are **declared**, not hand-built. `ColumnDef` gains
one optional `compact` slot (line 1 or 2 plus an order) next to v95's
`inlineFrom`; `sb-data-table` renders the compact list and owns a generic row
drawer. A table without the declaration keeps today's scroller, so nothing
regresses before it is migrated. Shared fixes go into the primitives and
tokens (a floor in the text tokens, a `.sb-hit` hit-area utility, baseline
alignment in panel and control rows, scroll-active-into-view on tab rails,
containment for heat-grid, bar-list, histogram, share-bar and waterfall), so
workspaces change only to declare their compact fields or to fix a
page-specific defect.

What it leaves alone: no data, endpoint, metric, store or schema changes, no
backend code; desktop table layouts stay as they are (apart from the shared
primitive fixes); the full-page trade route stays; and the Dashboard drawer
fetches nothing the page does not already load. Every cost, tax, paper-trade
or ⓘ caption travels with its figure.

Success is measured by a checked-in Playwright audit
(`frontend/scripts/layout-audit.mjs`) that reports zero unallowed findings —
page overflow, off-screen or clipped text, sub-44px targets on phone/tablet,
sub-11px text, baseline offsets over 2px — on every route and tab at 390, 768
and 1440px; by screenshots at those widths; by a column-reachability unit test
per migrated table; by the Dashboard drawer round trip (open, Back closes,
"Open full trade" reaches `/trades/:id`); and by green `testrun.py full`,
`npm test` and `npm run lint`.

## Architecture

- **Tokens and global styles (V179-1, V179-2).** `styles/tokens.css`: the two
  text tokens that can fall below 11px at 90% zoom get a floor
  (`--text-micro: max(11px, calc(11px * var(--text-scale)))`, same shape for
  `--text-chip`); a `--font-num` token feeds `.num` and every numeric value;
  the 44px block widens from `(pointer: coarse), (max-width: 639px)` to
  `(pointer: coarse), (max-width: 1023px)` (spec §3.4 "phone and tablet") and
  sets a new `--hit-min: 44px` (default `24px`). `styles.css` gains `.sb-hit`,
  a centred `::after` hit area of `max(100%, var(--hit-min))` in both axes. The
  jsdom token fixture is regenerated with `python scripts/dev/dump_tokens.py`.
- **Primitives (V179-3..V179-8).** `sb-panel`/`sb-panel-header`/`sb-control-row`
  align on the baseline with one header height; `sb-stat-tile` has one stacked
  variant and Calendar loses its inline/centred overrides; the filter area is
  one row pattern (`sb-control-bar`, `sb-filter-bar`, `sb-toolbar`,
  `sb-column-picker`); `ui/scroll-rail.ts` shares edge-fade measuring and
  scroll-active-into-view between `sb-tab-bar` and the System `nav.category-rail`;
  charts reflow or scroll in their own box; Partials' overflow is reproduced in
  a browser and fixed at its root.
- **Compact rows and the generic drawer (V179-9, V179-10).** Pure helpers in
  `ui/data-table/compact.ts`; `sb-data-table` renders `ul.compact-list` below
  640px when any rendered column declares `compact` — no header row, no
  chevron, phone sort `<select>` and pager kept, column footers as a totals
  line. A tap opens the table's own `sb-drawer` (`phoneTap = 'drawer'`) or only
  emits `rowActivate` (`'emit'`). A testing helper reads `[data-col]` keys from
  the compact row and the drawer so each table's reachability test is short.
- **Per-table declarations (V179-11..V179-13).** `trades.columns.ts` (Trades
  and Dashboard positions), Watchlist, ticker-detail trades, Research registry
  (generic drawer, badge floor) and ledger (`emit`), Risk exposure.
- **Dashboard trade drawer (V179-14..V179-16).** `ActivityEvent.tradeId`,
  activity rows as buttons, the `sb-trade-drawer` content component, a
  `[drawer-header]` slot on `sb-drawer`, and the Dashboard wiring: query
  parameter `trade`, pushed history entry, `rerunExceptQueryParam('trade')`
  replacing `runGuardsAndResolvers: 'always'` on the Dashboard route, row held
  in a signal, not-loaded id → `/trades/:id` with `replaceUrl`.
- **Page fixes (V179-17, V179-18)** and **the guard (V179-19..V179-21)**: the
  audit script with a pure, `node --test`-tested library and a dated,
  reasoned allow-list; `ui-design.md` § Checklist plus its `AGENTS.md` mirror;
  the verification sweep; the one full-suite task, merge, bump, panel,
  close-out.

## Global Constraints

- Frontend only: nothing under `swingbot/`, `bot.py`, `admin_ui.py`, `scripts/` or any store/schema changes. Files outside `frontend/` that do change: `tests/charts/resolved_tokens.json` (regenerated), `docs/claude/ui-design.md`, `AGENTS.md`, `VERSION.json`, `swingbot/admin/version_history.json`, the v179 results doc.
- Paths in tasks are relative to `frontend/src/app/` unless they start with `frontend/`, `docs/`, `tests/` or are repo-root files; `Create:`/`Modify:` lines in tasks always use the full repo path.
- Narrow test run per task: `cd frontend && npx ng test --watch=false --include <spec path relative to frontend/>` (e.g. `--include src/app/ui/stat-tile.spec.ts`); Python files only via `python scripts/dev/testrun.py file <test>`. `npm test`, `npm run lint` and `testrun.py full` run once, in V179-21.
- Styles are not loaded in jsdom and `matchMedia` never matches: phone/viewport behaviour is forced with `sb-data-table`'s `cardsAt`/`viewportAt` inputs; CSS is asserted as source text (`readFileSync` + `rule(selector)`), as `ui/layout.spec.ts` does.
- After any edit to `styles/tokens.css` run `python scripts/dev/dump_tokens.py` and commit `tests/charts/resolved_tokens.json` in the same commit; then `python scripts/dev/testrun.py file tests/charts/test_chart_theme.py`.
- 11px text floor: `max(11px, …)` inside the token, so zoom (`ZOOM_CHOICES = [90, 100, 110, 125]`, `shell/shell.ts:60`) still scales everything above the floor.
- 44px: every interactive control has a hit area ≥ 44×44px under `(pointer: coarse), (max-width: 1023px)`; the visible element may stay smaller when `.sb-hit` pads it.
- Mixed text sizes on one line align with `align-items: baseline` (or `last baseline`), never `center`.
- `ColumnDef.compact` extends the v95 declaration; there is no second column list. On phone the compact row **replaces** pinned-cell inlining; `inlineFrom` keeps governing tablet. A column hidden through the `Columns` picker stays hidden in the drawer.
- Drawer and compact cells render each column's existing `cell` template (else `text(col, row)`) through one shared `<ng-template>`; no second renderer per column.
- Money floor: open-position tables (Trades, Dashboard positions, Risk) keep P&L as an amount (€) and the stop distance or risk amount on line 1 or 2. Badge floor: Research registry keeps the badge tier on line 1 and evidence freshness on the compact row.
- Only the Dashboard trade drawer writes a query parameter (`trade`, pushed, never `replaceUrl`); `replaceUrl` only for the not-loaded redirect and for removing the parameter after a cold-link open. Generic table drawers are component state and close on Escape, backdrop tap, navigation and page change.
- The Dashboard drawer fetches nothing: a unit test asserts no extra HTTP request and no resolver re-run when only `trade` changes.
- No caption, ⓘ hint, `N=` sample, paper-trade, cost, tax or pre-tax text is dropped; it moves with its figure.
- Tables without a `compact` declaration keep today's phone scroller; the v80 "no cards" test is rewritten for undeclared tables, not deleted (spec §6b.9), and the `data-table.ts` docstring (~518-537) records the reversal citing v179.
- Browser checks use Playwright only (`frontend/scripts/browse.mjs`), signed in with `.env` credentials loaded inside the script and never printed; local instance = `/replicate-prod-db`, then `cd frontend && npm run build`, then `python admin_ui.py` (serves the SPA at `http://localhost:1234`); `--base http://localhost:1234 --widths 1440,768,390`. Each UI-changing part ends with that check in its last task.
- TS functions stay small and table-driven (no tool enforces complexity for TS, §6b.10); any Python touched stays < 15.
- Every task commits on the worktree branch in scoped commits; nothing is pushed until V179-21.

## Review Focus

- A trade row with nulls (no stop, no P&L amount, PENDING with only a trigger): the compact row shows an em dash, never `NaN`, `undefined` or an empty line — owned by V179-11's test.
- A table whose user hid every compact-declared column via the `Columns` picker: falls back to today's scroller rather than an empty compact row — owned by V179-9's test.
- Opening `/dashboard?trade=<id>` cold (reload or shared link) before `TradesStore` has loaded: waits for the load, then redirects only if still absent — owned by V179-16's test.
- Closing the Dashboard drawer with × after a cold-link open: removes the parameter with `replaceUrl` (no history entry Back would reopen); after an in-page open it goes `Location.back()` — owned by V179-16's test.
- The 90% zoom preference: every text token stays ≥ 11px while 125% still grows — owned by V179-1's test.

## Contracts (final; parts consume these names verbatim)

```ts
// ui/data-table/data-table.types.ts  (V179-9)
export interface CompactSlot { line: 1 | 2; order: number }
export type PhoneTap = 'drawer' | 'emit';
export interface DetailLink { commands: unknown[]; label: string }   // label e.g. 'Open full trade →'
// ColumnDef<T> gains:  compact?: CompactSlot;

// ui/data-table/compact.ts  (V179-9)
export interface CompactLines<T> { line1: ColumnDef<T>[]; line2: ColumnDef<T>[] }
export function compactLines<T>(columns: ColumnDef<T>[], rendered: readonly string[]): CompactLines<T>;
export function hasCompact<T>(columns: ColumnDef<T>[], rendered: readonly string[]): boolean;   // any rendered column has `compact`
export function drawerColumns<T>(columns: ColumnDef<T>[], rendered: readonly string[]): ColumnDef<T>[];  // rendered, not on the compact row, rendered order

// sb-data-table  (V179-9 compact rows; V179-10 drawer)
//   protected readonly compact: Signal<boolean>   // phone() && hasCompact(columns(), renderedKeys)
//   phoneTap = input<PhoneTap>('drawer');  detailLink = input<((row: T) => DetailLink | null) | null>(null);
//   protected readonly drawerRow = signal<T | null>(null);
// DOM: ul.compact-list > li.compact-row > button.compact-hit > .line1 / .line2 > [data-col="<key>"]
//      .compact-footer [data-col]   (column footers in compact mode)
//      sb-drawer.row-drawer > dl.drawer-fields > div[data-col] (dt label, dd value); expansion template after the dl; a.drawer-detail-link

// ui/data-table/testing/reachability.ts  (V179-10)
export function compactKeys(root: ParentNode): string[];
export function drawerKeys(root: ParentNode): string[];
export function openRowDrawer(root: HTMLElement, index?: number): void;
export function phoneViewport(): Provider;   // ViewportService stub (viewport/isPhone/isNarrow signals) for workspace specs

// ui/scroll-rail.ts  (V179-6)
export function edgeFades(el: HTMLElement): { start: boolean; end: boolean };
export function revealActive(container: HTMLElement, active: Element | null): void;   // no-op when scrollIntoView is missing (jsdom)

// workspaces/dashboard/panels/activity.ts  (V179-14)
// ActivityEvent gains:  tradeId: string;
// sb-recent-activity gains:  eventActivate = output<ActivityEvent>();  each row renders button.event-hit

// ui/layout.ts sb-drawer  (V179-15):  <ng-content select="[drawer-header]" /> inside the header, after the h2

// workspaces/dashboard/trade-drawer.ts  (V179-15)
// TradeDrawer, selector 'sb-trade-drawer', input row = input.required<TradeRow>();
//   renders .paper-marker "Paper trade" (attribute drawer-header, projected into sb-drawer's header),
//   ticker, direction, status, P&L % and €, plan levels (trigger/entry, stop, TP1, TP2, R:R), opened/held,
//   strategy and horizon, sb-row-actions, a.full-trade "Open full trade →" to ['/trades', row.id]
//   its own template holds the sb-drawer (projection needs it there); outputs closed = output<void>(),
//   actionDone = output<void>() (a row action reloads the data and closes the drawer)

// routing/route-rerun.ts  (V179-16)
export function rerunExceptQueryParam(name: string): (from: ActivatedRouteSnapshot, to: ActivatedRouteSnapshot) => boolean;
// false only when path params are equal and the query params differ in `name` alone; true otherwise (identical URLs rerun, as 'always').

// sb-positions-table  (V179-16):  phoneTap = input<PhoneTap>('drawer'), passed to its sb-data-table
// Dashboard (V179-16): query param 'trade'; protected drawerTrade = signal<TradeRow | null>(null);
//   openTrade(row: TradeRow): void; openActivity(event: ActivityEvent): void; closeTrade(): void

// styles (V179-1, V179-2): --font-num, --hit-min, .sb-hit; .num { font-family: var(--font-num) }

// frontend/scripts/layout-audit-lib.mjs  (V179-19)
export const ROUTES: readonly string[];      // every route and tab (27); :id/:plan/:symbol/:date resolved at run time from the API
export const CHECKS: readonly ['overflow', 'offscreen', 'clipped', 'tap', 'text', 'baseline'];
export function classify(findings, allow, today): { unallowed, allowed, stale };
// allow-list entry: { route, width ('*' or number), check, selector, reason, date: 'YYYY-MM-DD' }
// CLI: node frontend/scripts/layout-audit.mjs [--base URL] [--widths 390,768,1440] [--out DIR] [--allow FILE] [--settle MS] [--prune]
//      exit 1 on any unallowed finding; prints stale allow-list entries
```

**`rowActivate` consumers and their `phoneTap` (spec §6a.4):** Trades → `drawer` (detailLink `/trades/:id`, "Open full trade →"); Dashboard positions → `emit` (the trade drawer on every device); Watchlist → `drawer` (detailLink `/watchlist/:symbol`, "Open ticker →"); Research ledger → `emit` (its store-only drawer); Research registry → `drawer` (no detailLink); Risk exposure → `drawer` (detailLink `/trades/:trade_id`, "Open full trade →" — keeps the ticker-cell link's destination, which a compact row cannot tap); ticker-detail trades → `drawer` (detailLink `/trades/:id`); `data-table.spec.ts` host → default; gallery demo → `drawer`. Tablet and desktop keep today's `rowActivate` navigation on Trades and Watchlist.

## Parallelisation

All tasks share one worktree; at most 2 implementers at once, and only on disjoint files.

| Task | May run alongside | Sequential edge and why |
|---|---|---|
| V179-1 | — | first: creates the worktree and the tokens every later task reads |
| V179-2 | — | after V179-1: same `styles/tokens.css` media block and `styles.css` |
| V179-3 | V179-4, V179-5 | after V179-2: `panel-header.ts` hit area set there; `layout.ts` shared with V179-6 and V179-15 |
| V179-4 | V179-3, V179-5, V179-7 | after V179-2 (uses `--font-num`); `calendar.ts`, `stat-tile.ts` only here |
| V179-5 | V179-3, V179-4, V179-7 | after V179-2: `filter-bar.ts`, `column-picker.ts` hit areas set there |
| V179-6 | V179-4, V179-5 | after V179-3: same file `ui/layout.ts` |
| V179-7 | V179-4, V179-5 | after V179-6: the heat-grid fade imports `edgeFades` from `ui/scroll-rail.ts`; chart files only |
| V179-8 | — | after V179-4 and V179-7: the Partials repro must see the fixed tiles and charts; ends Parts 1–2 with the browser check |
| V179-9 | — | after V179-2 (sort-button hit area in `data-table.ts`); creates the compact contract |
| V179-10 | — | after V179-9: same `data-table.ts`, consumes `compactLines`/`drawerColumns` |
| V179-11 | V179-12 | after V179-10: consumes `compact`, `phoneTap`, `detailLink`, the reachability helpers |
| V179-12 | V179-11 | after V179-10; watchlist files only |
| V179-13 | — | after V179-11 and V179-12 (the workspace-consistency guard covers all migrated tables); ends Part 3 with the browser check |
| V179-14 | V179-15 | after V179-2 (`recent-activity.ts` all-link hit area) |
| V179-15 | V179-14 | after V179-6 (same `ui/layout.ts`) |
| V179-16 | — | after V179-11, V179-14, V179-15: positions declarations, `eventActivate`, `TradeDrawer` |
| V179-17 | V179-16, V179-18 | after V179-3; trade-detail files only |
| V179-18 | V179-17 | after V179-3 (baseline control row) and V179-16 (Dashboard drawer in place for the Part 4 browser check); ends Part 4 with the browser check |
| V179-19 | V179-17, V179-18 | disjoint files (`frontend/scripts/`, docs) |
| V179-20 | — | after every UI task and V179-19: runs the audit over the finished branch |
| V179-21 | — | last: the single full-suite run, merge, bump, panel, close-out |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-10-19-v179-mobile-layout-consistency_1-tokens-and-panels.md` | V179-1..V179-4 | worktree, text floor, numeric font, 44px hit areas, panel baseline, stat-tile single variant |
| 2 | `2026-10-19-v179-mobile-layout-consistency_2-controls-and-charts.md` | V179-5..V179-8 | control/filter row, tab-bar and category-rail reveal, chart containment, Partials repro and fix, Parts 1–2 browser check |
| 3 | `2026-10-19-v179-mobile-layout-consistency_3-tables.md` | V179-9..V179-12 | compact rows, generic drawer, per-table declarations and reachability tests |
| 3b | `2026-10-19-v179-mobile-layout-consistency_3b-research-risk-and-check.md` | V179-13 | Research and Risk declarations, no-hand-rolled-cards guard, Part 3 browser check (split for the 1500-line rule) |
| 4 | `2026-10-19-v179-mobile-layout-consistency_4-dashboard-and-pages.md` | V179-14..V179-16 | activity rows, trade drawer, Dashboard URL wiring |
| 4b | `2026-10-19-v179-mobile-layout-consistency_4b-page-fixes.md` | V179-17..V179-18 | per-page fixes, Part 4 browser check (split for the 1500-line rule) |
| 5 | `2026-10-19-v179-mobile-layout-consistency_5-audit-and-close-out.md` | V179-19..V179-21 | audit script and docs, three-width verification, full suite, merge, panel, close-out |

## Task ledger

| Task | Title | Part | Model | Files created / modified | Creates (consumed later) |
|---|---|---|---|---|---|
| V179-1 | Worktree, 11px text floor and numeric font token | 1 | sonnet | worktree; M `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `ui/strip-plot.ts`, `ui/tokens.spec.ts`, `ui/text-styles.spec.ts`, `tests/charts/resolved_tokens.json` | `--font-num`; floored `--text-micro`/`--text-chip` |
| V179-2 | 44px hit areas on phone and tablet | 1 | sonnet | M `frontend/src/styles/tokens.css`, `frontend/src/styles.css`, `ui/button.ts`, `ui/hint.ts`, `shell/profile-menu.ts`, `shell/shell.css`, `ui/filter-bar.ts`, `ui/column-picker.ts`, `ui/row-link.ts`, `ui/segmented.ts`, `ui/form-controls.ts`, `ui/panel-header.ts`, `workspaces/dashboard/positions-table.ts`, `workspaces/dashboard/panels/recent-activity.ts`, `ui/tokens.spec.ts`, `ui/button.spec.ts`, `ui/hint.spec.ts`, `tests/charts/resolved_tokens.json`; C `ui/hit-area.spec.ts` | `--hit-min`, `.sb-hit`, media query `(pointer: coarse), (max-width: 1023px)` |
| V179-3 | Panel, panel-header and control-row baseline with one header height | 1 | sonnet | M `ui/layout.ts` (Panel, ControlRow), `ui/panel-header.ts`, `ui/layout.spec.ts`, `ui/panel-header.spec.ts` | baseline `sb-control-row`, `sb-panel` header rule |
| V179-4 | `sb-stat-tile` single variant; Calendar totals migrated | 1 | sonnet | M `ui/stat-tile.ts`, `ui/stat-tile.spec.ts`, `workspaces/calendar/calendar.ts`, `workspaces/calendar/day/calendar-day.ts`, calendar specs, `workspaces/gallery/gallery.ts`, `workspaces/workspace-consistency.spec.ts` | one stacked tile; guard against `::ng-deep` into `sb-stat-tile` |
| V179-5 | One filter/control row pattern | 2 | sonnet | M `ui/control-bar.ts`, `ui/filter-bar.ts`, `ui/toolbar.ts`, `ui/column-picker.ts` and their specs | `.toolbar-sheet-button` with a count badge |
| V179-6 | Scroll-active-into-view for `sb-tab-bar` and the settings category rail | 2 | sonnet | C `ui/scroll-rail.ts`, `ui/scroll-rail.spec.ts`; M `ui/layout.ts` (TabBar), `ui/layout.spec.ts`, `workspaces/system/settings-tab.ts` and its spec | `edgeFades`, `revealActive` |
| V179-7 | Chart and grid containment | 2 | sonnet | M `ui/heat-grid.ts`, `ui/bar-list.ts`, `ui/histogram.ts`, `ui/share-bar.ts`, `ui/waterfall.ts` and their specs | two-line `sb-bar-list` under a narrow container |
| V179-8 | Partials and Attribution overflow: browser repro, root-cause fix, Parts 1–2 browser check | 2 | sonnet | M `workspaces/analytics/tabs/partials.ts`, `workspaces/analytics/tabs/attribution.ts` (as the repro shows), their specs | — |
| V179-9 | `ColumnDef.compact` and compact-row rendering; v80 test reversed | 3 | sonnet | M `ui/data-table/data-table.types.ts`, `ui/data-table/data-table.ts`, `ui/data-table/data-table.spec.ts`; C `ui/data-table/compact.ts`, `ui/data-table/compact.spec.ts` | `CompactSlot`, `PhoneTap`, `DetailLink`, `compactLines`, `hasCompact`, `drawerColumns`, `compact` signal, compact DOM contract |
| V179-10 | Generic row drawer, `phoneTap` precedence, `detailLink`, gallery demo | 3 | sonnet | M `ui/data-table/data-table.ts`, `ui/data-table/data-table.spec.ts`, `workspaces/gallery/gallery.ts`, `workspaces/gallery/gallery.spec.ts`; C `ui/data-table/testing/reachability.ts` | `phoneTap`, `detailLink` inputs, `drawerRow`, `compactKeys`, `drawerKeys`, `openRowDrawer` |
| V179-11 | Trades and Dashboard-positions compact declarations (money floor) | 3 | sonnet | M `workspaces/trades/trades.columns.ts`, `workspaces/trades/trades.columns.spec.ts`, `workspaces/trades/trades.ts`, `workspaces/trades/trades.spec.ts` | `compact` on `tradeColumns` |
| V179-12 | Watchlist and ticker-detail compact declarations | 3 | sonnet | M `workspaces/watchlist/watchlist.ts`, `workspaces/watchlist/ticker-detail.ts` and their specs | — |
| V179-13 | Research registry (badge floor), ledger `emit`, Risk exposure (money floor); no-hand-rolled-cards guard; Part 3 browser check | 3b | sonnet | M `workspaces/research/research.ts`, `workspaces/risk/risk.ts`, their specs, `workspaces/workspace-consistency.spec.ts` | — |
| V179-14 | `ActivityEvent.tradeId` and interactive activity rows | 4 | sonnet | M `workspaces/dashboard/panels/activity.ts`, `workspaces/dashboard/panels/recent-activity.ts` and their specs | `tradeId`, `eventActivate` |
| V179-15 | `sb-trade-drawer` content and the drawer header slot | 4 | sonnet | C `workspaces/dashboard/trade-drawer.ts`, `workspaces/dashboard/trade-drawer.spec.ts`; M `ui/layout.ts` (Drawer), `ui/layout.spec.ts` | `TradeDrawer`, `[drawer-header]` slot |
| V179-16 | Dashboard drawer wiring: `trade` param, rerun rule, redirect, positions `emit` | 4 | opus | C `routing/route-rerun.ts`, `routing/route-rerun.spec.ts`; M `workspaces/dashboard/dashboard.ts`, `workspaces/dashboard/dashboard.routes.ts`, `workspaces/dashboard/positions-table.ts`, `workspaces/dashboard/dashboard.spec.ts`, `workspaces/dashboard/positions-table.spec.ts`, `app.routes.spec.ts` | `rerunExceptQueryParam`, `openTrade`, `openActivity`, `closeTrade`, `drawerTrade` |
| V179-17 | Trade-detail fixes: title baseline, "Confirmed by:" space, one numeric face in cards | 4b | haiku | M `workspaces/trades/trade-detail.ts`, `workspaces/trades/why/sizing-panel.ts`, `workspaces/trades/why/if-it-gets-there.ts`, `ui/status-indicator.ts`, `workspaces/trades/why/why-panel.ts`, `workspaces/trades/strategy-record-card.ts`, `workspaces/trades/scores-card.ts`, `workspaces/trades/why/levels-block.ts`, their specs | — |
| V179-18 | Versions "Running now", Dashboard performance segmented header, Analytics population line and empty N; Part 4 browser check | 4b | sonnet | M `workspaces/versions/versions.ts`, `workspaces/dashboard/panels/trading-performance.ts`, `workspaces/dashboard/dashboard.spec.ts`, `workspaces/analytics/scope-bar.ts`, their specs | — |
| V179-19 | Layout audit script, allow-list, `ui-design.md` checklist and `AGENTS.md` mirror | 5 | sonnet | C `frontend/scripts/layout-audit.mjs`, `frontend/scripts/layout-audit-lib.mjs`, `frontend/scripts/layout-audit-lib.test.mjs`, `frontend/scripts/layout-audit.allow.json`; M `docs/claude/ui-design.md`, `AGENTS.md` | `ROUTES`, `CHECKS`, `classify`, CLI |
| V179-20 | Three-width verification: audit to zero, screenshots, Dashboard drawer round trip | 5 | sonnet | C `docs/superpowers/results/2026-10-19-v179-layout-audit.md`; M any file a finding traces to | audit report |
| V179-21 | Full suite, `npm test`, lint, ui minor bump, merge, `/panel`, `/close-out` | 5 | sonnet | M `VERSION.json`, `swingbot/admin/version_history.json` (regenerated; the bump runs inside `/close-out`); no push — a push to `main` deploys, so it waits for the partner | merged branch on `main` |
