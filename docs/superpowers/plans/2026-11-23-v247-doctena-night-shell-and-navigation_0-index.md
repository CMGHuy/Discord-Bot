# v247 — Doctena night, plan 3 of 5: Shell and navigation (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V247-8" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v240-doctena-night-restyle-design.md](../specs/2026-11-23-v240-doctena-night-restyle-design.md) — plan 3 of its "What follows" list (§5, §6, and the rail / nav / tab-bar / long-press lines of §8, §9 and §11).
**Brief:** `.superpowers/briefs/2026-11-23-v247-doctena-night-shell-and-navigation.md` — its Traps and symbol verdicts override the spec's "before" text.
**Runs after:** plan 1 ([v240 theme and type](implemented/2026-11-23-v240-doctena-night-theme-and-type_0-index.md)) and plan 2 ([v241 icons](implemented/2026-11-23-v241-doctena-night-icons_0-index.md)), both merged. **Runs before:** v246 plan A, then plan 4 (drawer core). One worktree at a time (spec "Interleaved with v246").

## Goal

The admin SPA's rail is 80px wide and labels every icon with its page name,
Calendar hides as a tab inside Trades, the top bar's wordmark reads
"BomeoCapital" with no space, and the phone's bottom bar holds a fixed set of
four pages the partner cannot change. The doctena-night restyle (spec v240)
asked for an icon-only rail (D5), Calendar as its own destination (D7), the
wordmark "Bomeo Capital" (D8), and a phone tab bar whose pages the partner
picks, with a press-and-hold that names a tab (D9). Plans 1 and 2 already
moved the fonts, colours and icons; this plan moves the shell around them.

Once this ships, the rail is 64px wide and shows only 24px icons in 44×44
targets. Each link keeps its page name as its `aria-label`, and an anchored
`sb-hint` shows that name on hover (after a short delay), on keyboard focus,
and on a 500ms touch press. Only one tooltip is open at a time. The active
entry has the `--accent-soft` fill and a 3px `--accent` bar on the rail's
inner edge. Calendar sits after Trades in the rail at `/calendar`. The old
`/trades/calendar[/:date]` URLs redirect there with their query string, so
bookmarks and Discord links still land. Trades loses its section tabs.
`spa.py` lists `calendar` as a destination, so no later close-out deletes it.
On a phone the bar defaults to Home, Watchlist, Trades, Calendar, then More.
Tabs share the width equally and the active one gets the accent pill. Press
and hold shows a tab's name above it, and **Edit tab bar** in the More sheet
opens an editor where the partner moves pages between the bar and More. The
choice is saved in this browser under `localStorage['ui.tabbar']`.

How it works: `Hint` gains a public API (`openDelay`, `placement`,
`openPinned()`, `dismiss()`, one open hint app-wide). A new `sbLongPress`
directive emits on a held touch or pen press and knows nothing about hints;
the rail and the tab bar each wire its output to their hint's `openPinned()`.
`TabBarPrefs` is a root service holding the chosen paths as a signal. It
validates them against `navEntriesFor(isAdmin)` on every read and persists
them through its own `TAB_BAR_STORAGE` token, the way `THEME_STORAGE` does.
`PhoneTabBar`, `MoreSheet`, `phoneTabPathFor` and the editor all read it.

What it leaves alone: drawers, the bottom-sheet gesture and `sb-data-table`
(plan 4 and plan 5); desktop row clicks; the tokens, fonts and icons plans 1
and 2 set; every data, schema, alert and trading path. The only Python
change is the `WORKSPACES` tuple's grouping in `swingbot/admin/spa.py`.

Success is measured by tests and one browser check. Component and spec tests
cover the rail's 64px width, missing labels, `aria-label`s and per-link hints
opening on hover, focus and long-press. They also cover the nav order, the
redirects with their query, the breadcrumbs, `phoneTabPathFor` on detail
routes, every `ui.tabbar` validation case, the long-press timing and
cancellation rules, the editor's partition invariant, the announcements and
the focus return. A Python test pins `calendar` as a served destination. The
closing task runs a Playwright check at 390, 820 and 1440px (rail tooltip;
editor round-trip remove Watchlist / add Risk / reload / Reset). It also runs
`frontend/scripts/layout-audit.mjs` at the three widths.

## Architecture

- **One nav model, still.** `shell/nav.ts` stays the single source for the
  rail, palette, breadcrumb, section tabs, dock state and phone bar.
  Calendar becomes a plain `NavEntry`; Trades becomes a single page. The
  phone bar's default list becomes the exported `DEFAULT_PHONE_TAB_PATHS`,
  mapped to entries by `phoneTabsFor(paths)`, which applies the "Home" label.
- **Routes flip in place.** `app.routes.ts` loads the Calendar workspace at
  `calendar`. `trades/calendar` and `trades/calendar/:date` become relative
  string redirects to `calendar` / `calendar/:date`, declared before
  `trades/:id`. The old `calendar` redirects and the `'/calendar'` alias are
  deleted, so no pair of redirects points at each other.
- **Hint owns tooltips; long-press owns gestures.** `sbLongPress` emits
  `longPress` and nothing else. The host template wires it to a template
  ref: `(longPress)="hint.openPinned()"`. `Hint` keeps its three open
  reasons (pinned, hovered, focused). A module-level "current open hint"
  makes one opening hint dismiss the previous one.
- **Per-browser storage, own token.** `TabBarPrefs` mirrors `ThemeService`.
  It uses `TAB_BAR_STORAGE` (an `InjectionToken`, `providedIn: 'root'`,
  factory wrapping `localStorage` in try/catch) and specs swap in a Map.
  `PreferencesStore` is for account-level settings: `theme.service.ts`'s
  header records why a per-browser choice is the exception, and the spec
  chose per browser (D9).
- **The shell hosts the editor.** `sb-tab-bar-editor` (its own component,
  wrapping `sb-drawer`) sits in `shell.html` beside `sb-more-sheet`, so the
  More sheet's diff stays small for plan 4 and its focus trap never contains
  the drawer. The More sheet only gains an **Edit tab bar** button
  (`editRequested`) and an `editing` input that mutes its Escape handler
  while the editor is open. Focus returns to the Edit button through
  `sb-drawer`'s `FocusTrap` restore.

## Decisions this index fixes (controller decisions 1–5, then this writer's)

1. **Default phone tabs follow the spec:** Home, Watchlist, Trades,
   Calendar, then More, the rail's order. The two specs that pin
   Calendar-before-Trades (`nav.spec.ts`, `phone-tab-bar.spec.ts`) flip
   (controller).
2. **Hint API gaps are explicit tasks** (V247-5, V247-6) before the rail
   tooltip and long-press tasks (controller).
3. **`TabBarPrefs` gets its own `TAB_BAR_STORAGE` token**, the way
   `THEME_STORAGE` / `DENSITY_STORAGE` do; no shared wrapper (controller).
4. **Spec §11 E2E lines** are covered by component/spec tests plus a
   Playwright check at 390/820/1440 in V247-16. It logs in via
   `POST /api/v1/session` with `.env` `ADMIN_USERNAME`/`ADMIN_PASSWORD`,
   loaded inside the script and never printed. `node frontend/scripts/layout-audit.mjs`
   also runs at the three widths (controller).
5. **Every hard-coded `/trades/calendar` link** in production code, and every
   test, probe and smoke string the brief lists, is flipped here (controller).
6. **Hover delay.** The spec cites "the existing hint delay", but none exists
   (the brief's verdict). `Hint.openDelay` (ms, default `0`) delays only the
   hover reason. Focus, click and `openPinned()` stay immediate, and every
   existing hint keeps opening at once. The rail and tab-bar hints pass
   `HINT_HOVER_DELAY_MS = 300`, exported from `ui/hint.ts`.
7. **One open hint app-wide**, not per rail: opening any `sb-hint` (hover,
   focus, pin or `openPinned()`) dismisses the one that was open.
8. **Tab label size.** The spec says 11px, but the repo's micro token is
   `--text-micro: max(12px, …)`, the readability floor every label uses.
   The tab label keeps `var(--text-micro)` and gains weight 600, and no new
   11px literal or token is added. The controller may override.
9. **Long-press tooltip text** is the destination's rail label, so the
   Home tab's tooltip reads "Dashboard"; every other tab's reads its label.
   The More button gets no hint.
10. **Wordmark family** becomes `var(--font-sans)` (the wordmark holds no
    figures, so it leaves the `--font-mono`/`tabular-nums` gate's scope);
    `Bomeo` weight 700 `--text`, a real space, `Capital` weight 500
    `--accent`.
11. **Active rail bar.** The `.rail-link.active::after` is a 3px
    `--accent` bar with `--pill-radius` corners, placed on the rail's inner
    (right) edge: `right: calc((var(--rail-width) - 44px) / -2)`. The
    `.rail-pill` span is removed; the 44×44 `.rail-link` carries the
    `--accent-soft` fill.
12. **Layout audit's `rail-label` check** keeps its id (the `CHECKS` list is
    pinned). It is redefined for the icon-only rail: every
    `nav.rail a.rail-link` needs an accessible name and an
    `aria-describedby` pointing at a `role="tooltip"` whose text equals that
    name. `railLabelVerdict({ name, tooltip })` returns `no-name`, then
    `no-tooltip`, then `tooltip-not-name`.
13. **Breadcrumbs follow the model.** A trade detail reads
    `Trades / NVDA #812` (the "Book" crumb goes with Trades' sections), and
    `SECTION_LABEL_OVERRIDES` drops `'/trades'`. A calendar day reads
    `Calendar / <day title>` with `Calendar` linking `/calendar`.
14. **Editor reorder rules.** Dashboard is pinned at index 0 with no
    buttons. Move up is disabled at index 1, move down at the last index.
    Remove is on every non-Dashboard row; add is disabled while
    `paths().length >= MAX_TAB_PAGES` (4 pages, Dashboard included). Announcements
    read: `"<Label> moved to position <n>"`, `"<Label> added to the tab bar"`,
    `"<Label> moved to More"`, `"Tab bar reset to default"`,
    `"Tab bar restored"`.
15. **Reset/Undo.** Reset stores the pre-reset paths and shows an inline
    **Undo** for `UNDO_MS = 8000`. Undo restores them, and the timer is
    cleared on Undo, Done or close. Done closes the drawer; edits already
    applied stay applied.

## Global Constraints

- Frontend root `frontend/src/app/` (written `app/` below). Angular
  zoneless, signals, `ChangeDetectionStrategy.OnPush`, standalone
  components, vitest through `ng test`.
- Per-task verification is narrow:
  `cd frontend && npx ng test --watch=false --include <spec> [--include <spec>]`;
  Node script tests `node --test frontend/scripts/<file>.test.mjs`; Python
  `python scripts/dev/testrun.py file <test file>`. A 60s
  `Timeout waiting for worker` is load: re-run once. **No task runs the
  full suite; CI does.**
- Rail: `--rail-width: 64px`; each `.rail-link` a 44×44 target with a 24px
  icon (`[size]="24"`, never a CSS svg override); no `.rail-label` in the
  DOM; `aria-label="<label>"` and `aria-current="page"` on the active link.
- Rail order: Dashboard, Watchlist, Trades, Calendar, Risk, Insights; System
  at the foot, admin only.
- Long-press: `LONG_PRESS_MS = 500`, `LONG_PRESS_SLOP_PX = 10`; pointer type
  `touch` or `pen` only; a second pointer, a move over 10px, `pointerup`
  before 500ms or `pointercancel` cancels; the click after a fired press is
  swallowed; touch-originated `contextmenu` is prevented; hosts get class
  `sb-long-press` (`-webkit-touch-callout: none; -webkit-user-select: none;
  user-select: none;` in `frontend/src/styles.css`).
- Long-press tooltip stays until the next pointerdown anywhere or Escape;
  no timed close.
- `ui.tabbar`: a JSON array of nav paths. On read: `/trades/calendar` maps
  to `/calendar`; unknown, duplicate and not-visible paths are dropped;
  `/dashboard` is forced first; it is truncated to `MAX_TAB_PAGES = 4`;
  empty or not JSON gives the default. A throwing storage gives the default
  and never breaks the shell.
- Editor: at most 4 pages plus More, at least Dashboard. 44px targets on
  up/down/remove/add. The disabled-add reason is the inline text
  `The bar holds 4 pages. Remove one to add another.` above the Under More
  list. An `aria-live="polite"` region carries the announcements. Every nav
  page the login may see is in exactly one of the two lists.
- Navigation, brand, active, current and focus rules never read
  `--pos`/`--neg` (`ui/money-colour.spec.ts` `NAV_FILES` gate); no text
  rule reads `--text-faint`; no hex in a `.ts` file; no px radius literal
  (use `--pill-radius`, `--control-radius`, `--panel-radius`).
- Frontend functions stay small (the Python complexity gate covers
  `spa.py`, whose change adds no branch).
- Commit in scoped commits inside the plan's worktree; never stage another
  session's files.

## Plan 1 and plan 2 contracts this plan relies on

- `sb-icon` `size` input (`16 | 20 | 24`); names `info`, `edit`, `up`,
  `down`, `plus`, `minus`, `close`, `more`, `calendar`, `brand` exist
  (`app/ui/icon.ts`).
- `--pill-radius`, `--accent`, `--accent-soft`, `--control-border` tokens
  (`frontend/src/styles/tokens.css`).
- `ui/money-colour.spec.ts` `NAV_FILES` and the `shell.css` nav-selector
  scan (V240-10); `ui/type-gates.spec.ts` `tabular-nums` gate (V240-9).
- `sb-hint` always draws `info` and has no `glyph` input (V241-5).

## Parallelisation

The plan runs **in id order in one worktree** (the spec's plans are strictly
sequential, and plan 4 shares `more-sheet.ts` with this one). Sequential
edges and their reasons:

- V247-1 → V247-2: the redirect flip and the alias removal ship together
  (spec §6: no pair of redirects pointing at each other mid-branch).
- V247-1 → V247-3: V247-3's links target the new `/calendar` route.
- V247-1 → V247-4: the probe and audit route lists mirror the new routes.
- V247-2 → V247-11: consumes `DEFAULT_PHONE_TAB_PATHS` and `phoneTabsFor`.
- V247-5 → V247-6: both edit `ui/hint.ts` and `ui/hint.spec.ts`.
- V247-6 → V247-8, V247-9, V247-13: they consume `openDelay`,
  `HINT_HOVER_DELAY_MS`, `openPinned()` and `placement`.
- V247-7 → V247-9, V247-13: they consume `LongPress` (`sbLongPress`,
  `longPress` output).
- V247-8 → V247-9 → V247-10: all three edit `shell/shell.html`,
  `shell/shell.css` and `shell/shell.spec.ts`.
- V247-2 → V247-12: both edit `shell/nav.ts`, `phone-tab-bar.ts`,
  `more-sheet.ts` and their specs.
- V247-11 → V247-12 → V247-13: `TabBarPrefs` is consumed by the bar, and
  V247-13 edits `phone-tab-bar.ts` after V247-12.
- V247-11 → V247-14 → V247-15: the editor consumes `TabBarPrefs`; V247-15
  edits `tab-bar-editor.ts` after V247-14.
- V247-12 → V247-15: both edit `more-sheet.ts` and its spec.
- V247-10 → V247-15: both edit `shell.html` and `shell.spec.ts`
  (V247-15 also `shell.ts`).
- Every task → V247-16: the browser check exercises the finished shell.

Safe in parallel if the controller wants to: **V247-4 ∥ V247-5 ∥ V247-7**
after V247-1. They touch disjoint files (Python and probe scripts vs
`ui/hint.ts` vs `ui/long-press.ts` + `styles.css`) and share no contract.
**V247-11 ∥ V247-8** after V247-2 and V247-6: new `shell/tab-bar-prefs.ts`
vs the shell template, with no contract between them.

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V247-1 | Calendar workspace at `/calendar`; `/trades/calendar[/:date]` redirect to it | 1 | sonnet | M `frontend/src/app/app.routes.ts`, M `frontend/src/app/app.routes.spec.ts` | route `path: 'calendar'` (authGuard, title 'Calendar', subtitle 'P&L by day', `calendarRoutes`); redirects `trades/calendar` → `calendar`, `trades/calendar/:date` → `calendar/:date` |
| V247-2 | Nav model: Calendar after Trades, Trades a single page, alias gone, default phone tabs flipped | 1 | sonnet | M `frontend/src/app/shell/nav.ts`, M `frontend/src/app/shell/nav.spec.ts`, M `frontend/src/app/shell/breadcrumb.ts` (comments), M `frontend/src/app/shell/breadcrumb.spec.ts`, M `frontend/src/app/shell/section-tabs.spec.ts`, M `frontend/src/app/shell/palette/palette-items.ts` (comment), M `frontend/src/app/shell/palette/palette-items.spec.ts`, M `frontend/src/app/shell/live/dock-state.spec.ts`, M `frontend/src/app/shell/more-sheet.spec.ts`, M `frontend/src/app/shell/phone-tab-bar.ts` (doc comment), M `frontend/src/app/shell/phone-tab-bar.spec.ts`, M `frontend/src/app/shell/shell.spec.ts` (route stubs and nav rows only) | `export const DEFAULT_PHONE_TAB_PATHS: readonly string[] = ['/dashboard', '/watchlist', '/trades', '/calendar']`; `export function phoneTabsFor(paths: readonly string[], entries: readonly NavEntry[] = NAV_ENTRIES): NavEntry[]` (unknown paths dropped, "Home" label applied); `PHONE_TABS = phoneTabsFor(DEFAULT_PHONE_TAB_PATHS)` (kept until V247-12); `phoneTabPathFor(url: string, tabs: readonly NavEntry[] = PHONE_TABS): string \| null` |
| V247-3 | Every production `/trades/calendar` link points at `/calendar`; old-paths gate flipped | 1 | sonnet | M `frontend/src/app/workspaces/calendar/calendar.ts`, M `frontend/src/app/workspaces/calendar/calendar.spec.ts`, M `frontend/src/app/workspaces/calendar/day/calendar-day.ts`, M `frontend/src/app/workspaces/calendar/day/calendar-day.spec.ts`, M `frontend/src/app/workspaces/analytics/tabs/overview.ts`, M `frontend/src/app/routing/old-paths.spec.ts` | `OLD_PATH_WORDS` without `'calendar'`; a forbidden-link rule for `/trades/calendar` |
| V247-4 | `spa.py` lists `calendar` as a destination; probe, smoke and audit route lists follow | 1 | haiku | M `swingbot/admin/spa.py`, M `tests/admin/test_spa_serving.py`, M `scripts/dev/smoke_spa.py`, M `scripts/ops/admin_browser_probe.py`, M `tests/scripts/test_admin_browser_probe.py`, M `frontend/scripts/layout-audit-lib.mjs`, M `frontend/scripts/layout-audit-lib.test.mjs`, M `frontend/scripts/admin-page-timing.mjs` | `WORKSPACES` first row gains `"calendar"`; layout-audit `ROUTES` hold `'/calendar'`, `'/calendar/:date'` |
| V247-5 | `Hint`: hover open delay, public `dismiss()`, one open hint app-wide | 2 | sonnet | M `frontend/src/app/ui/hint.ts`, M `frontend/src/app/ui/hint.spec.ts` | `export const HINT_HOVER_DELAY_MS = 300`; `Hint.openDelay = input(0)`; `Hint.dismiss(): void` (public; replaces protected `close()` at every call site) |
| V247-6 | `Hint`: `openPinned()` and anchor `placement: 'beside' \| 'above'` | 2 | sonnet | M `frontend/src/app/ui/hint.ts`, M `frontend/src/app/ui/hint.spec.ts` | `Hint.openPinned(): void`; `Hint.placement = input<'beside' \| 'above'>('beside')`; `export function placeAbove(anchor: {top; bottom; left; right; width}, pop: {width; height}, viewport: {width; height}, margin = 8): { top: number; left: number }` |
| V247-7 | `sbLongPress` directive | 2 | sonnet | C `frontend/src/app/ui/long-press.ts`, C `frontend/src/app/ui/long-press.spec.ts`, M `frontend/src/styles.css` | `export const LONG_PRESS_MS = 500`; `export const LONG_PRESS_SLOP_PX = 10`; `@Directive({ selector: '[sbLongPress]' }) export class LongPress { readonly longPress = output<void>() }`; host class `sb-long-press` |
| V247-8 | Rail: 64px, icons only, `aria-label`, one anchored hint per link, accent bar | 3 | sonnet | M `frontend/src/app/shell/shell.html`, M `frontend/src/app/shell/shell.css`, M `frontend/src/app/shell/shell.ts`, M `frontend/src/app/shell/shell.spec.ts` | `Shell.railHintDelay = HINT_HOVER_DELAY_MS` (protected); per-link template refs `#link` / `#hint` |
| V247-9 | Rail long-press opens the hint; layout audit's `rail-label` check redefined | 3 | sonnet | M `frontend/src/app/shell/shell.html`, M `frontend/src/app/shell/shell.ts`, M `frontend/src/app/shell/shell.spec.ts`, M `frontend/scripts/layout-audit-lib.mjs`, M `frontend/scripts/layout-audit-lib.test.mjs`, M `frontend/scripts/layout-audit.mjs` | `railLabelVerdict({ name, tooltip })` → `no-name` / `no-tooltip` / `tooltip-not-name` |
| V247-10 | Wordmark "Bomeo Capital"; `LABELS.brand` | 3 | haiku | M `frontend/src/app/shell/shell.html`, M `frontend/src/app/shell/shell.css`, M `frontend/src/app/shell/shell.spec.ts`, M `frontend/src/app/ui/icon.ts`, M `frontend/src/app/ui/icon.spec.ts` | none |
| V247-11 | `TabBarPrefs`: validated per-browser tab list | 4 | sonnet | C `frontend/src/app/shell/tab-bar-prefs.ts`, C `frontend/src/app/shell/tab-bar-prefs.spec.ts` | `TAB_BAR_PREF_KEY = 'ui.tabbar'`; `MAX_TAB_PAGES = 4`; `interface TabBarStorage { get(key: string): string \| null; set(key: string, value: string): void }`; `TAB_BAR_STORAGE: InjectionToken<TabBarStorage>`; `sanitizeTabPaths(raw: unknown, visible: readonly NavEntry[]): string[]`; `readTabPaths(storage: TabBarStorage, visible: readonly NavEntry[]): string[]`; `@Injectable({providedIn:'root'}) class TabBarPrefs { paths: Signal<readonly string[]>; tabs: Signal<readonly NavEntry[]>; underMore: Signal<readonly NavEntry[]>; canAdd: Signal<boolean>; isDefault: Signal<boolean>; set(paths: readonly string[]): void; add(path: string): void; remove(path: string): void; moveUp(path: string): void; moveDown(path: string): void; reset(): readonly string[] }` |
| V247-12 | Phone bar and More sheet read `TabBarPrefs`; equal-width tabs, accent pill, 600 labels | 4 | sonnet | M `frontend/src/app/shell/nav.ts`, M `frontend/src/app/shell/nav.spec.ts`, M `frontend/src/app/shell/phone-tab-bar.ts`, M `frontend/src/app/shell/phone-tab-bar.spec.ts`, M `frontend/src/app/shell/more-sheet.ts`, M `frontend/src/app/shell/more-sheet.spec.ts` | `PHONE_TABS` deleted; `phoneTabPathFor(url: string, tabs: readonly NavEntry[]): string \| null` (tabs required); `morePageGroups(entries: readonly NavEntry[], tabs: readonly NavEntry[]): MoreGroup[]` (both required) |
| V247-13 | Tab press-and-hold shows the tab's name above it | 4 | sonnet | M `frontend/src/app/shell/phone-tab-bar.ts`, M `frontend/src/app/shell/phone-tab-bar.spec.ts` | `PhoneTabBar` tab hints: `placement="above"`, text = rail label |
| V247-14 | Tab-bar editor: two lists, move/add/remove, inline reason, live preview, announcements | 5 | sonnet | C `frontend/src/app/shell/tab-bar-editor.ts`, C `frontend/src/app/shell/tab-bar-editor.spec.ts`, M `frontend/src/app/ui/money-colour.spec.ts` (`NAV_FILES` += `'app/shell/tab-bar-editor.ts'`) | `@Component({ selector: 'sb-tab-bar-editor' }) class TabBarEditor { open = input(false); closed = output<void>() }`; `.announce[aria-live=polite]` region; `export const ADD_LIMIT_REASON = 'The bar holds 4 pages. Remove one to add another.'` |
| V247-15 | Reset with 8s Undo, Done; More sheet's Edit tab bar action; shell wiring and focus return | 5 | sonnet | M `frontend/src/app/shell/tab-bar-editor.ts`, M `frontend/src/app/shell/tab-bar-editor.spec.ts`, M `frontend/src/app/shell/more-sheet.ts`, M `frontend/src/app/shell/more-sheet.spec.ts`, M `frontend/src/app/shell/shell.html`, M `frontend/src/app/shell/shell.ts`, M `frontend/src/app/shell/shell.spec.ts` | `export const UNDO_MS = 8000`; `MoreSheet.editRequested = output<void>()`; `MoreSheet.editing = input(false)`; `Shell.editorOpen` signal, `openEditor()`, `closeEditor()` |
| V247-16 | Browser check at 390/820/1440 (rail tooltip, editor round-trip) and the layout audit | 5 | sonnet | C `frontend/scripts/shell-nav-check.mjs` | none |

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-23-v247-doctena-night-shell-and-navigation_1-calendar-destination.md` | V247-1..V247-4 | Route flip, nav model, hard-coded links and the old-paths gate, `spa.py` and the probe/audit route lists |
| 2 | `2026-11-23-v247-doctena-night-shell-and-navigation_2-hint-and-long-press.md` | V247-5..V247-7 | `Hint`'s new public API (delay, dismiss, one-at-a-time, `openPinned`, above placement) and `sbLongPress` |
| 3 | `2026-11-23-v247-doctena-night-shell-and-navigation_3-rail-and-wordmark.md` | V247-8..V247-10 | The 64px icon rail with hints and long-press, the audit's rail check, the wordmark |
| 4 | `2026-11-23-v247-doctena-night-shell-and-navigation_4-tab-bar.md` | V247-11..V247-13 | `TabBarPrefs`, the bar and More sheet reading it, tab press-and-hold |
| 5 | `2026-11-23-v247-doctena-night-shell-and-navigation_5-editor-and-check.md` | V247-14..V247-16 | The tab-bar editor, the Edit action and shell wiring, the closing browser check |

## Handoff

Controller decisions for the brief's contradictions (2026-11-23), recorded
as Decisions 1–5 above:

1. Default phone tabs follow the spec: Home, Watchlist, Trades, Calendar,
   More (the rail's order). The two specs pinning Calendar-before-Trades
   flip.
2. The Hint API gaps (open delay, programmatic open, one at a time, open
   above) are explicit tasks (V247-5, V247-6) before the rail tooltip
   (V247-8/9) and long-press (V247-9, V247-13) tasks.
3. `TabBarPrefs` gets its own storage token (`TAB_BAR_STORAGE`), like
   `THEME_STORAGE` / `DENSITY_STORAGE`; no shared wrapper.
4. Spec §11 E2E lines with no e2e home are covered by component/spec tests
   and the V247-16 Playwright check at 390/820/1440. That check logs in via
   `POST /api/v1/session` with `.env` `ADMIN_USERNAME`/`ADMIN_PASSWORD`,
   never printed. `node frontend/scripts/layout-audit.mjs` also runs at the
   three widths.
5. Every hard-coded `/trades/calendar` link in production code and every
   test, probe and smoke string the brief lists is flipped (V247-2, V247-3,
   V247-4).

Open for the controller: Decision 6 (300ms hover delay), Decision 8
(`--text-micro` 12px floor instead of the spec's 11px tab label) and
Decision 7 (one open hint app-wide).

Guide chapters: no file under `docs/guide/` cites the shell or nav files.
The close-out records `guide: no reader-visible change` unless
`scripts/dev/guide_sources.py` reports otherwise.
