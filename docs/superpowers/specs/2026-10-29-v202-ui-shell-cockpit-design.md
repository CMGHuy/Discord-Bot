# v202 — UI redesign Phase 1: six-destination IA and the cockpit shell

**Version:** ui 1.37.2 · bot 2.15.7
**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor, veteran-trader

## Why

The partner asked for the whole admin UI to be redesigned, starting in Figma
with mockups. "Whole UI" is four projects, so the work is phased. This spec
is Phase 1, the information architecture and the shell. Each later phase
gets its own spec:

1. **IA & shell** (this spec): what the destinations are, and the frame
   around every page.
2. Foundations: a Figma library of tokens (light/dark), type and core
   components, then the matching CSS.
3. Key screens: Dashboard, Trades, Plans, Watchlist.
4. The remaining workspaces.

Structure comes first, so that Phases 2–4 design into the final navigation
instead of reworking it later.

What is wrong with the shell today (v195):

- **Eleven rail entries, unlabelled.** The 48px rail shows eleven glyphs in
  four groups split by thin rules. A label appears only on hover or focus,
  so nobody reads the rail at a glance, and on a touch tablet there is no
  hover at all.
- **Related pages are scattered.** Calendar and Cancels are separate
  top-level destinations, although both are views of the trade book.
  Analytics, Research and Reports are three entries for one question ("what
  do the measurements say"). Versions is a top-level entry for a page
  visited once a release.
- **Live state is spread across small chips.** Killswitch, freshness,
  connection and clock share the top bar's right edge. Portfolio heat
  against the cap is not in the shell at all: it is one page away on Risk.
  For a desk that trades real money from these alerts, heat is the one
  number that should never leave the screen.
- **The brand was lost.** The two-tone `BomeoCapital` wordmark was removed in
  fdf6b78a (v195, the 48px rail had no room for it), leaving a lone diamond.
  The partner wants the wordmark back.

## Mockups

Figma file (partner's drafts):
https://www.figma.com/design/HgebQyvl9rBjBSYMEmPHq7, page "Phase 1 — IA &
Shell". Three directions were mocked at 1440 / 834 / 390px. The partner chose
**C, cockpit + live dock**:

- Desktop: https://www.figma.com/design/HgebQyvl9rBjBSYMEmPHq7?node-id=5-708
- Tablet and phone sit to its right in the same row.
- The IA card: https://www.figma.com/design/HgebQyvl9rBjBSYMEmPHq7?node-id=5-1244

All figures in the mockups are sample data. Icons are placeholder squares;
glyphs stay the current `sb-icon` set until Phase 2.

## Decisions (partner, 2026-10-29)

| # | Decision |
|---|---|
| D1 | Direction C: labelled rail, a top bar led by the wordmark, a right-hand Live dock on desktop, and a live strip that opens the dock as a sheet on tablet and phone. |
| D2 | The two-tone **BomeoCapital** wordmark returns: JetBrains Mono bold, `-0.02em`, "Bomeo" in `--text`, "Capital" in `--accent`, the pre-v195 `.brand .word` treatment. It leads the top bar on every device. The diamond mark heads the rail on desktop and tablet, and sits before the wordmark on phone. |
| D3 | Eleven rail pages become **six destinations**, with sub-pages as tabs inside their section. Old URLs redirect. |
| D4 | Dock: a per-page default (open on Dashboard and Risk, collapsed to an edge tab everywhere else). The user's toggle overrides it and is remembered per page. |
| D5 | The killswitch, freshness and connection chips and the clock move into the dock and strip. **Only the killswitch chip stays in the top bar.** The ticker tape keeps its strip under the bar. |
| D6 | The dock's Activity section is real data, from a new read-only `GET /api/v1/activity` endpoint. |

## Design

### 1. Navigation model

`frontend/src/app/shell/nav.ts` stays the single nav model. It feeds the rail,
the phone tab bar and More sheet, the command palette and the breadcrumb.
`NavEntry` gains an optional `sections` list, and the model becomes six
entries:

| Destination | Path | Sections (tabs) |
|---|---|---|
| Dashboard | `/dashboard` | — |
| Watchlist | `/watchlist` | — (symbol detail stays `/watchlist/:symbol`) |
| Trades | `/trades` | Book `/trades` · Calendar `/trades/calendar` · Cancels `/trades/cancels` |
| Risk | `/risk` | — |
| Insights | `/insights` → `/insights/analytics` | Analytics · Research `/insights/research` · Reports `/insights/reports` |
| System | `/system` | Health `/system` · Versions `/system/versions` |

- **Groups.** The rail draws no group dividers: six labelled entries need
  none. System sits at the rail's foot, apart from the five work
  destinations. `NavGroup` is kept only if the breadcrumb still needs a
  group name. The plan decides after reading `breadcrumb.ts`, and the
  breadcrumb then reads `Destination / Section`, e.g. `Trades / Calendar`.
- **Section tabs.** A new `sb-section-tabs` renders a destination's sections
  as a segmented control. Each segment is a `routerLink` with
  `aria-current="page"` on the active one. It sits at the top of the
  workspace, above the page's `sb-page` header, and is drawn by the shell
  from the nav model, never by each workspace.
- **Detail routes.** `/trades/:id`, `/plans/:id` and `/watchlist/:symbol`
  keep their parent destination active (today's `ALIASES` rule). In
  `app.routes.ts`, `trades/calendar` and `trades/cancels` are declared
  **before** `trades/:id`, so neither word is read as a trade id.
- **System's own tabs.** System keeps its `?tab=` query tabs (settings, scan,
  providers, logs) inside the Health section. Only Versions becomes a path
  section.

### 2. Routes and redirects

- **New routes.** `trades/calendar`, `trades/cancels`, `insights/analytics`,
  `insights/research`, `insights/reports` and `system/versions` each load the
  existing workspace module unchanged. A page's component, store and
  resolver do not move in Phase 1. Only the URL that reaches it changes.
- **Redirects.** `calendar`, `cancels`, `analytics`, `research`, `reports`
  and `versions` redirect to their new path and **keep the query string and
  fragment**. That matters because Analytics state lives in query params,
  and Discord alerts and bookmarks carry deep links. `insights` with no
  section goes to `insights/analytics`.
- **Server.** `swingbot/admin/spa.py` `WORKSPACES` adds `insights` and keeps
  every old name, so a hard reload of an old URL still serves `index.html`
  and Angular redirects it. `scripts/dev/smoke_spa.py` follows suit: the new
  paths join `WORKSPACES` and the six old names join `LEGACY_WORKSPACES`.
- **Bot-side links.** Any link the bot writes (Discord embeds, admin links)
  into one of the six moved pages is updated to the new path. The redirects
  keep old messages working, so this is tidiness, not a fix. The plan's
  brief greps `swingbot/` and `bot.py` for them.
- **In-app links.** Every `routerLink` or `navigate` into a moved page moves
  to the new path. The plan greps for them; one was found at design time.

### 3. Shell layout per device

Breakpoints are the existing `ui/breakpoints.ts` classes. Nothing new is
invented.

| | Desktop | Tablet | Phone |
|---|---|---|---|
| Rail | 80px: diamond mark on top, then Dashboard, Watchlist, Trades, Risk, Insights with icon and label; System at the foot; the version hint at the foot as today | same 80px rail | none |
| Top bar | wordmark · divider · breadcrumb · *(flex)* · killswitch chip · Ctrl K search · profile | same | diamond + wordmark · *(flex)* · killswitch chip · search icon · profile |
| Live | 320px dock on the right of the workspace (§4) | live strip under the tape; opens the dock as a right-side sheet | live strip under the tape; opens the dock as a bottom sheet |
| Tape | strip under the top bar | same | same, as today |
| Bottom | — | — | tab bar: Home, Watchlist, Trades, Risk, More |

- **Rail items.** Each has a 24px icon over an 11px label, a 64×52px hit
  area, and an active pill in `--accent-soft` behind the icon. The existing
  `sb-nav-indicator` bar is retired: the pill is the indicator. Labels are
  always rendered, so the `sb-hint` per link goes away. The brand keeps its
  hint ("Bomeo Capital · Dashboard").
- **More sheet (phone).** It lists Insights (with its three sections),
  System (Health, Versions) and the profile actions. These are the entries
  that do not fit the four tabs.
- **Unchanged.** The engaged-killswitch alarm strip, the "killswitch state
  unavailable" strip, the scan-progress bar hung from the top bar, the
  route-loading overlay, focus management (`route-focus.ts`) and the command
  palette all keep their behaviour. They only move with the elements they
  are attached to.

### 4. Live dock

A new shell component, `sb-live-dock`, holds three sections, each its own
small component so it can be tested alone.

1. **Bot.**
   - Scanner state: running, idle or down, from the connection store
     (`botAlive`, `botHealthy`).
   - Last scan time.
   - Data freshness: the current `sb-freshness-chip` content, as a row.
   - Event-stream connection: the current `sb-connection-status`, as a row.
   - Market open or closed (`marketActive`).
   - Killswitch state.
   - This absorbs the top bar's freshness and connection chips and the
     clock.
2. **Portfolio heat.**
   - Open heat % against the cap, as a meter, from the risk store's
     `openHeatPct`, `heatCapPct`, `heatMeterFraction` and `heatNearCap`
     (amber from 80% of the cap, never red, the existing rule).
   - The room left under the cap.
   - Pending orders.
   - The values are *not clamped*, as the risk store already documents:
     130% of the cap reads 130%.
   - The risk store is root-scoped or provided by the shell, so the dock
     can read it on every page. The plan's brief confirms which and how it
     refreshes on the `risk` event.
3. **Activity.** The last 8 events from `GET /api/v1/activity` (§5): time,
   one-line text, and a tone colour (positive / negative / warning /
   neutral). A "Full activity log →" link goes to System → Logs. The
   section refreshes on the `trades`, `scan`, `bot` and `risk` events.

**Open/collapsed state** (D4):

- Collapsed, the dock is a 40px edge tab: a "Live" label rotated vertically,
  a status dot and the heat figure. Clicking it opens the dock.
- Default open on `/dashboard` and `/risk`. Default collapsed on every other
  destination.
- The toggle writes `{destinationPath: boolean}` through the existing
  `PreferencesStore` (or `ui_preferences`, if that is where per-user UI
  preferences already live; the brief decides, and browser storage is the
  fallback only).
- A blocked or failed preference read falls back to the default, never to
  an error.
- At tablet and phone widths the dock never docks. It opens only as the
  sheet.

**Live strip** (tablet and phone): one 40px line. It shows a status dot with
the last scan time, `Heat 4.2% / 6%` (amber near the cap) and `N new plans`,
then "Live ›". Tapping it opens the sheet. The sheet holds the same
`sb-live-dock` content and traps focus (`ui/focus-trap.ts`, the pattern
`more-sheet.ts` already uses). Escape and a backdrop tap close it.

### 5. `GET /api/v1/activity`

This is a read-only endpoint in a new `swingbot/admin/api_v1/activity.py`,
registered like its siblings and behind the same auth.

- **Query.** `?limit=` defaults to 8, with a maximum of 50.
- **Response.** `{events: [{at, kind, text, tone, ref}], availability}`,
  newest first. `ref` is the trade id or plan id to link to, or null.
- **Event kinds in Phase 1.** Every kind comes from a column that already
  exists. No schema change.

  | `kind` | Source | Text (example) |
  |---|---|---|
  | `plan_created` | `plans.created_at` | `New plan · MSFT long` |
  | `trade_opened` | `trades.opened_at` | `XLE short filled at 92.10` |
  | `trade_closed` | `trades.closed_at` and the outcome and R in `doc` | `NVDA closed · TP2 · +2.1R` |
  | `killswitch` | `killswitch.engaged_at` | `Killswitch engaged` |
  | `scan_finished` | the last finished scan (`scan_progress` or `bot_heartbeat`; the brief picks the column that carries a finish time) | `Scan finished · 3 new plans` |

- **Deferred kinds.** TP1 hits and stop trails are *not* in Phase 1. No
  column records their time, and the brief confirms whether `trades.doc`
  carries one. If it does, they join as `tp_hit` and `stop_moved`. If not,
  they are named in What follows.
- **Shape.** Each kind is one function returning rows. A table-driven
  dispatcher merges them, sorts and truncates, which keeps every function
  under complexity 15. The text is built server-side so the Discord and web
  wordings cannot drift apart.
- **Failure.** If one source query raises, that kind is dropped and
  `availability` becomes `partial` with the kind named. The endpoint still
  answers 200. If every source fails, it returns `events: []` with
  `availability: unavailable`. The dock shows "Activity unavailable", never
  an empty list that looks like a quiet day.

### 6. Error and empty states

| Situation | What the shell shows |
|---|---|
| Connection store has no `/health` yet | Bot section rows show `—`. No row claims "Running" before an answer. |
| Risk read failed | Heat section: "Heat unavailable" with the panel-error retry. The strip shows `Heat —`. |
| Activity `unavailable` | "Activity unavailable" plus a retry. |
| Activity `partial` | The events, then a faint line: "Some sources unavailable: …". |
| No events | "Nothing yet today". This differs from unavailable. |
| Killswitch state unknown | The existing "Killswitch ?" chip reading (71dd8e40), unchanged. |
| Preference read blocked | The per-page dock default applies. |

### 7. Testing

Every behaviour ships its unit tests in the same task, empty and failure
cases included (partner rule).

- **Nav model.** Six entries; sections per destination; `navEntryFor`
  resolves section paths, detail aliases and old paths; the breadcrumb reads
  `Destination / Section`.
- **Routes.** Every old path redirects to its new one with the query string
  and fragment kept. `trades/calendar` is not matched as `trades/:id`.
  `insights` goes to `insights/analytics`.
- **Shell.** The wordmark renders as two spans, "Capital" in the accent class
  (the pre-v195 test, restored). The rail shows six labelled links. The top
  bar keeps only the killswitch chip. The phone tab bar and More sheet list
  the right entries. The tape strip is still present.
- **Dock.**
  - Per-page default.
  - Toggle and persistence.
  - Blocked storage falls back.
  - It never docks at tablet or phone widths.
  - Collapsed edge tab content.
  - Each section's loading, unavailable, partial and empty states.
  - Heat is unclamped and turns amber at 80%.
- **Strip and sheet.** Contents, the open and close paths (tap, Escape,
  backdrop) and the focus trap.
- **API.**
  - Each kind's row builder.
  - Merge, sort and limit.
  - The `limit` bounds.
  - A failing source gives `partial`; all failing gives `unavailable`.
  - Auth required.
  - These tests run against the shared `swing-db` replica after
    `/replicate-prod-db`.
- **Server.** `spa.py` serves the new and the old paths; `smoke_spa.py`
  lists are updated.
- **Layout.** Each finished shell is checked at the three device widths per
  `ui-design.md`: no horizontal scroll, 44px touch targets, and the dock not
  overlapping content.

## Out of scope

- New colours, type scale, spacing or component styling (Phase 2). Phase 1
  uses today's tokens.
- Changing any page's content or layout (Phases 3–4). A page moves under a
  new URL unchanged.
- Light theme work beyond what today's tokens already do.
- TP1 and stop-trail activity events unless `trades.doc` already timestamps
  them (§5).

## What follows

- Phase 2 spec: the foundations library in the same Figma file, then the
  token and CSS changes.
- If TP1 and stop-move times are not recorded, a small bot spec to record
  them, which turns on those two activity kinds.
