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

The mockups are the layout reference, and **this spec wins where they
differ**. The panel review changed the dock's rows and wording. For example,
the mockup's "XLE short filled" reads "paper fill" here.

All figures in the mockups are sample data. Icons are placeholder squares;
glyphs stay the current `sb-icon` set until Phase 2.

## Decisions (partner, 2026-10-29)

| # | Decision |
|---|---|
| D1 | Direction C: labelled rail, a top bar led by the wordmark, a right-hand Live dock on desktop, and a live strip that opens the dock as a sheet on tablet and phone. |
| D2 | The two-tone **BomeoCapital** wordmark returns: JetBrains Mono bold, `-0.02em`, "Bomeo" in `--text`, "Capital" in `--accent`, the pre-v195 `.brand .word` treatment. It leads the top bar on every device. The diamond mark heads the rail on desktop and tablet, and sits before the wordmark on phone. |
| D3 | Eleven rail pages become **six destinations**, with sub-pages as tabs inside their section. Old URLs redirect. |
| D4 | Dock: a per-page default (open on Dashboard and Risk, collapsed to an edge tab everywhere else). The user's toggle overrides it and is remembered per page. |
| D5 | The killswitch, freshness and connection chips and the clock move into the dock and strip. **Only the killswitch chip stays in the top bar.** The ticker tape keeps its strip under the bar. A stale or disconnected alarm also shows in the top bar, but only while it applies (§3, panel). |
| D6 | The dock's Activity section is real data, from a new read-only endpoint. The panel folded it into one DB-only `GET /api/v1/live` read (§5). |

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
  destinations. The breadcrumb reads `Destination / Section`, for example
  `Trades / Calendar`. The plan drops `NavGroup` unless another consumer
  still needs it.
- **Resolving a URL.** `navEntryFor` today resolves by first segment only.
  It gains a second-segment rule. The second segment is a section exactly
  when it is one of that destination's section path words (`calendar`,
  `cancels`, `analytics`, `research`, `reports`, `versions`). Anything else
  there (`/trades/812`) is a detail id and keeps the destination's first
  section active. `/trades/calendar/2026-10-01` resolves to Trades /
  Calendar. Old paths resolve through `ALIASES` to their new entry, so a
  rail highlight never blinks during a redirect.
- **Label invariant.** Today `nav.spec.ts` holds that a rail label equals its
  route's title. That cannot hold for `Insights` (a redirect-only path) or
  for System's "Health". The new invariant: **every section label equals
  its route's `title`, and a destination's label equals the title of its
  first section, except where `nav.ts` records an explicit override with a
  comment.** Insights → Analytics and System → Health are the two overrides.
- **Section tabs.** A new `sb-section-tabs` renders a destination's sections
  as a segmented control. Each segment is a `routerLink` with
  `aria-current="page"` on the active one. It sits at the top of the
  workspace, above the page's `sb-page` header, and is drawn by the shell
  from the nav model, never by each workspace.
- **System's own tabs.** System keeps its `?tab=` query tabs (settings, scan,
  providers, logs) inside the Health section. Only Versions becomes a path
  section.

### 2. Routes and redirects

- **New routes.** These load the existing workspace modules unchanged:
  - `trades/calendar` and `trades/calendar/:date` (Calendar's day child,
    `calendar.routes.ts:52`)
  - `trades/cancels`
  - `insights/analytics`, `insights/research` and `insights/reports`
  - `system/versions`

  A page's component, store and resolver do not move in Phase 1. Only the
  URL that reaches it changes. In `app.routes.ts` all the `trades/<section>`
  routes are declared **before** `trades/:id`, so a section word is never
  read as a trade id.
- **Redirects.** Each old path redirects to its new path and **keeps the
  query string and fragment**:
  - `calendar` and `calendar/:date`
  - `cancels`
  - `analytics`, `research` and `reports`
  - `versions`

  Keeping the query string matters because Analytics state lives in query
  params, and bookmarks carry deep links. `insights` with no section goes to
  `insights/analytics`. The `calendar/:date` redirect follows the
  `universe/:symbol` precedent at `app.routes.ts:100-101`.
- **In-app links.** Every `routerLink`, `navigate` and palette route into a
  moved page moves to its new path, including:
  - `calendar.ts:258`
  - `calendar-day.ts:127,131,133`
  - `analytics/tabs/overview.ts:175`
  - the seven Analytics and Reports entries in `palette-items.ts:65-71`

  The plan's brief greps for the rest. A test asserts that no `routerLink`
  in `frontend/src` points at an old path.
- **Bot-side links.** None. The only SPA link the bot builds is
  `/plans/{id}` (`swingbot/core/presentation/components.py:84`), which does
  not move.
- **Server.** `swingbot/admin/spa.py` `WORKSPACES` adds `insights` and keeps
  every old name, so a hard reload of an old URL still serves `index.html`
  and Angular redirects it. `scripts/dev/smoke_spa.py` follows suit: the new
  paths join `WORKSPACES` and the six old names join `LEGACY_WORKSPACES`.
- **When the old names go.** The six old names stay in `spa.py` and the SPA
  redirects until **Phase 4's close-out**. Its spec owns removing them
  together with `cockpit` and `universe`. A comment beside each list says
  so, matching the NG57 precedent at `spa.py:42`.

### 3. Shell layout per device

Breakpoints are the existing `ui/breakpoints.ts` classes. Nothing new is
invented.

| | Desktop | Tablet | Phone |
|---|---|---|---|
| Rail | 80px: diamond mark on top, then Dashboard, Watchlist, Trades, Risk, Insights with icon and label; System at the foot; the version hint at the foot as today | same 80px rail | none |
| Top bar | wordmark · divider · breadcrumb · *(flex)* · alarm chip (only while it applies) · killswitch chip · Ctrl K search · profile | same | diamond + wordmark · *(flex)* · alarm chip · killswitch chip · search icon · profile |
| Live | 320px dock on the right of the workspace (§4) | live strip under the tape; opens the dock as a right-side sheet | live strip under the tape; opens the dock as a bottom sheet |
| Tape | strip under the top bar | same | same, as today |
| Bottom | — | — | tab bar: Home, Watchlist, Trades, Risk, More |

- **Rail items.** Each has a 24px icon over an 11px label, a 64×52px hit
  area, and an active pill in `--accent-soft` behind the icon. The existing
  `sb-nav-indicator` bar is retired: the pill is the indicator. Labels are
  always rendered, so the `sb-hint` per link goes away. The brand keeps its
  hint ("Bomeo Capital · Dashboard").
- **Alarm chip.** It shows only while data is stale (freshness past its
  existing threshold), the event stream is `dead` or `degraded`, or the bot
  is not alive. It is the one live-state signal that must not depend on the
  dock being open. When nothing is wrong it renders nothing, so the top bar
  stays clean. It names the problem ("Data stale 12 min", "Disconnected",
  "Bot down") and opens the dock.
- **More sheet (phone).** It lists Insights (with its three sections),
  System (Health, Versions) and the profile actions. These are the entries
  that do not fit the four tabs.
- **Unchanged.** The engaged-killswitch alarm strip, the "killswitch state
  unavailable" strip, the scan-progress bar hung from the top bar, the
  route-loading overlay, focus management (`route-focus.ts`) and the command
  palette all keep their behaviour. They only move with the elements they
  are attached to.

### 4. Live dock

A new shell component, `sb-live-dock`, holds four sections, each its own
small component so it can be tested alone. All times are **Berlin local**
(the app's existing clock convention), with a relative age beside them
("14:32 · 6 min ago").

1. **Bot.**
   - Scanner state: running, idle or down, from the connection store
     (`botAlive`, `botHealthy`).
   - Last successful scan time and age.
   - Data freshness: the current `sb-freshness-chip` content, as a row.
   - Event-stream connection: the current `sb-connection-status`, as a row.
   - Market session: pre-market, open, after-hours or closed, with the time
     to the next open when closed. It comes from the session state the
     connection store already exposes (`marketActive`, and the
     `known-traps.md` § session state machine); the brief confirms which
     signal carries more than open/closed. If only open/closed exists, the
     row shows that and nothing is invented.
   - Killswitch state, in plain language: "Active: new alerts paused since
     09:31" when engaged, "Clear" when not.
   - This absorbs the top bar's freshness and connection chips and the
     clock.
2. **Plans awaiting order.** A count of open plans not yet filled, expired or
   cancelled. This is the pre-open list a trader places resting orders
   from. It shows the soonest expiry ("next expires in 2 sessions", from
   the plan's existing validity) and links to Trades → Book filtered to
   those plans. It is a **state count, not a since-last-visit badge**: it
   does not grow with every scan or clear when seen. It drops only when a
   plan fills, expires or is cancelled, so it never nudges the trader to
   check the screen.
3. **Portfolio heat.**
   - Open heat against the cap, as both **dollars and percent**, e.g.
     "$2,010 at risk · 4.2% of $48,210 · cap 6% ($2,893)", plus a meter.
   - The room left under the cap, in dollars and percent.
   - Values are **not clamped**: 130% of the cap reads 130%.
   - Amber from 80% of the cap. Over 100% the row also reads **"Over cap"**,
     so near-cap and over-cap cannot look alike. Whether the colour also
     turns red is the risk-manager's call, and Phase 1 keeps the existing
     never-red rule.
   - Heat means exactly what the Risk page means by it: the same read-model
     function, not a reimplementation. The brief names the function and
     whether it counts resting orders; the dock labels the figure the same
     way the Risk page does.
   - The dock never shows a lower exposure than Risk does.
   - The section carries an "as of" age.
4. **Activity.** The last 8 events from `GET /api/v1/live` (§5): time and
   age, one-line text, and a tone. Every P&L line reads "(paper, pre-cost)".
   The R figure shows its dollar value beside it in the neutral text colour.
   A "Full activity log →" link goes to System → Logs.

**Data source.** The dock reads **only `GET /api/v1/live`** (§5) and the
root-scoped connection store. It never instantiates `RiskStore`, which is
route-scoped on `/risk` (`risk.routes.ts:6`) and whose `GET /risk` v201
measured at 4.1 s quiet and up to 52 s during a scan. `/live` refreshes on
the `trades`, `scan`, `bot` and `risk` events, debounced to one request per
2 s.

**Open/collapsed state** (D4):

- Collapsed, the dock is a 40px edge tab: a "Live" label rotated vertically,
  a status dot, the heat figure, and the count of plans awaiting order.
- The edge tab turns warning-toned, with the warning named in its accessible
  label, whenever:
  - heat is at or above 80% of the cap, or over the cap
  - data is stale, or the stream is disconnected
  - the bot is down
  - the killswitch is active

  A collapsed choice can therefore never hide an alarm state. It does not
  force the dock open: the partner's choice holds.
- Default open on `/dashboard` and `/risk`. Default collapsed on every other
  destination.
- The toggle is stored through the existing root-scoped `PreferencesStore`,
  which is server-side `ui_preferences`, read once at shell start, and
  rejects browser storage by design (spec v13). There is **no browser-storage
  fallback**. The value is a map keyed by the **destination path** (`/trades`,
  `/insights`), never by a section path or an old path, so redirects and
  sections cannot fork it.
- A failed preference read falls back to the per-page default, never to an
  error.
- At tablet and phone widths the dock never docks. It opens only as the
  sheet.

**Live strip** (tablet and phone): one 40px line. It shows:

- a status dot with the last scan age
- `Heat $2,010 · 4.2% / 6%` (amber near the cap, "Over cap" above it)
- `N awaiting order`
- "Live ›"

It takes the same warning tone as the edge tab. Tapping it opens the sheet.
The sheet holds the same `sb-live-dock` content and traps focus
(`ui/focus-trap.ts`, the pattern `more-sheet.ts` already uses). Escape and a
backdrop tap close it.

### 5. `GET /api/v1/live`

This is a read-only endpoint in a new `swingbot/admin/api_v1/live.py`,
registered like its siblings and behind the same auth. It reads **Postgres
only** and never calls a market-data provider, so it stays fast while v201's
slow `/risk` and `/dashboard` paths are still being fixed. v202 does not
depend on v201 and can land before or after it.

- **Response.** Four sections, each carrying its own `availability`
  (`ok` / `partial` / `unavailable`) and `as_of`:

  ```json
  {
    "heat": {...},
    "awaiting": {"count": 3, "next_expiry": "..."},
    "killswitch": {"engaged": true, "since": "..."},
    "events": [{"at": "...", "kind": "...", "text": "...", "tone": "...", "ref": "..."}]
  }
  ```

  `events` is newest first. `?limit=` sets its length: default 8, maximum 50.
  `ref` is the trade id or plan id to link to, or null.
- **Heat.** It calls the Risk page's heat read-model function. If that
  function needs live prices, `/live` returns the last stored heat figures
  with their timestamp instead, and the dock shows the age. The brief
  decides which applies, after reading `risk_read_model.py`. **Heat is never
  recomputed differently from Risk.**
- **Event kinds in Phase 1.** Every kind comes from data that already
  exists, and the brief names the exact doc keys for each:

  | `kind` | Source | Text (example) |
  |---|---|---|
  | `plan_alerted` | `plans.created_at` | `Alert · MSFT long · entry 418.50` |
  | `paper_filled` | the plan's `status_history` entry for the fill transition (its `at`; `plan_manager.py:1069-1081`) | `Paper fill · XLE short at 92.10` |
  | `tp1_hit` | the plan's first realized leg (`legs_realized`) and its time, *if* the leg carries one | `TP1 · NVDA · +1.0R ($210) (paper, pre-cost)` |
  | `trade_closed` | `trades.closed_at` with the outcome, R and dollar P&L in `doc` | `NVDA closed · TP2 · +2.1R ($441) (paper, pre-cost)` |
  | `killswitch` | the current `killswitch` row: `engaged` and `engaged_at` | `Killswitch engaged` or `Killswitch released` |
  | `scan_finished` | the `scan_progress` doc's finish time and new-plan count, *if* those keys exist | `Scan finished · 3 new plans` |

- **What the sources can and cannot say.**
  - `trades.opened_at` is the record-creation time at alert, not a fill
    (`performance.py:785`), so it is **never** used for a "filled" line.
    The only "fill" in the feed is `paper_filled`, which is the bot's
    simulated paper fill. It is labelled "Paper fill", because a trader's
    own resting order may fill differently, or not at all.
  - The `killswitch` table holds one current-state row: `release()`
    overwrites `engaged_at` (`killswitch.py:42-45`). So the feed shows only
    the **latest** transition, worded by the `engaged` flag, and never
    claims an engagement at a release time. A killswitch history is named
    in What follows.
  - `scan_progress` is ephemeral and holds the last scan only
    (`schema.py:190-194`). `bot_heartbeat.ts` is a liveness beat, not a
    finish time. If the `scan_progress` doc carries no finish time and
    count, `scan_finished` is dropped. The Bot section's "last successful
    scan" then comes from the connection store, as today.
  - `tp1_hit` is included only if a realized leg carries its own time.
    Otherwise it joins stop moves under What follows.
  - **Stop moves are not in the feed.** No persisted record holds their
    time; they are live events only (`plan_manager.py:268`). The trader is
    not left without a follow-up, because Discord already sends each one as
    a MOVE STOP instruction (`execution_embeds.py:32`,
    `lifecycle_embeds.py:491`). Persisting them for the dock is a follow-up
    spec (What follows).
- **Shape.** Each kind is one row-builder function. A table-driven
  dispatcher merges, sorts and truncates the rows, which keeps every
  function under complexity 15.
- **Failure.** If one source query raises, that section or kind is dropped,
  its `availability` becomes `partial` with the kind named, and the
  endpoint still answers 200. If every source of a section fails, that
  section is `unavailable`. The dock never shows an empty list that looks
  like a quiet day.

### 6. Error, empty and stale states

| Situation | What the shell shows |
|---|---|
| Connection store has no `/health` yet | Bot section rows show `—`. No row claims "Running" before an answer. |
| Heat `unavailable` | "Heat unavailable" with the panel-error retry. The strip and edge tab show `Heat —`. |
| Heat is stored, not live | The figures plus "as of 14:05 · 27 min ago". |
| Activity `unavailable` | "Activity unavailable" plus a retry. |
| Activity `partial` | The events, then a faint line: "Some sources unavailable: …". |
| No events today, last scan recent | "Nothing yet today". |
| No events, last scan older than the scan interval allows | "No scan since 09:00 (5h ago)", in warning tone. A missed scan must never read as a quiet day. |
| Killswitch state unknown | The existing "Killswitch ?" chip reading (71dd8e40), unchanged. |
| Preference read fails | The per-page dock default applies. |

### 7. Rollback

If the image is rolled back after v202 (`scripts/ops/rollback_to.sh`):

- Bookmarks to `/insights/...` and `/system/versions` 404 at the server,
  because the old `spa.py` has no `insights` prefix.
- `/trades/calendar` opens trade detail with the id "calendar" and shows its
  not-found state.
- The dock-preference map stays in `ui_preferences`, unused and harmless.
- No data, schema or bot behaviour changes, so there is nothing to undo
  beyond the image.

### 8. Testing

Every behaviour ships its unit tests in the same task, empty and failure
cases included (partner rule).

- **Nav model.**
  - Six entries, with the sections for each.
  - The second-segment rule: a section word against a detail id, and
    `calendar/:date`.
  - Old paths resolve through `ALIASES`.
  - The new label invariant, with its two recorded overrides.
  - The breadcrumb reads `Destination / Section`.
- **Routes.**
  - Every old path, including `calendar/:date`, redirects with its query
    string and fragment kept.
  - `trades/calendar` and `trades/cancels` are not matched as `trades/:id`.
  - `insights` goes to `insights/analytics`.
  - No `routerLink` or palette route points at an old path.
- **Shell.**
  - The wordmark renders as two spans, "Capital" in the accent class (the
    pre-v195 test, restored).
  - The rail shows six labelled links.
  - The top bar keeps only the killswitch chip, plus the alarm chip in
    exactly its three conditions.
  - The phone tab bar and More sheet list the right entries.
  - The tape strip is still present.
- **Dock.**
  - Per-page default; toggle; persistence through `PreferencesStore`, keyed
    by destination path.
  - A failed read falls back to the default.
  - It never docks at tablet or phone widths.
  - The edge tab content and its warning tone in each listed condition.
  - Each section's loading, unavailable, partial, stale and empty states.
  - Heat in dollars and percent, unclamped, amber at 80%, "Over cap" above
    100%.
  - The awaiting-order count and next expiry.
  - The killswitch wording.
  - The "No scan since" warning.
  - It never touches `RiskStore`.
- **Strip and sheet.** Contents, warning tone, the open and close paths
  (tap, Escape, backdrop) and the focus trap.
- **API.**
  - Each kind's row builder, including `trades.opened_at` never yielding a
    fill line.
  - Killswitch engaged and released wording.
  - Merge, sort and limit; the `limit` bounds.
  - Per-section `partial` and `unavailable`.
  - Heat equals the Risk page's figures for the same book.
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
- Recording any event the bot does not already persist: stop moves, a
  killswitch history, and TP1 if its leg has no time.

## What follows

- Phase 2 spec: the foundations library in the same Figma file, then the
  token and CSS changes.
- A bot spec that persists stop moves (and TP1 times, and killswitch
  transitions if they are still missing) as an event log, so the dock can
  list them. `Edge: harvest`: the trader amends resting orders from them.
- A concentration row in the dock: sector and correlated-cluster heat, from
  the Risk read model (financial-advisor).
- Phase 4's close-out removes the six old route names together with
  `cockpit` and `universe`.

## Panel review

Run 2026-10-29 on 7bb63bf3, serially: staff-engineer (opus), then
financial-advisor and veteran-trader (sonnet).

**BLOCKING**

- veteran-trader 1: the `trade_opened` text "filled at" claimed a fill from
  `trades.opened_at`, which is the alert time. **Applied:** `opened_at` is
  never a fill. `plan_alerted` and `paper_filled` (from `status_history`)
  replace it, and the fill is labelled paper.
- veteran-trader 2: stop moves and TP1 were deferred, leaving a resting
  order without a follow-up. **Applied in part:** `tp1_hit` is in Phase 1
  when its leg is timestamped. Stop moves stay out because no record holds
  their time. Discord already sends each as a MOVE STOP instruction
  (`execution_embeds.py:32`), so the trader has the follow-up. Persisting
  them is a named follow-up spec.

**ADVISORY**

- staff-engineer 1: the dock would instantiate the slow, route-scoped
  `RiskStore`. **Applied:** the dock reads only the DB-only `/live`
  endpoint; heat comes from the same read model, stored if it needs prices.
- staff-engineer 2: the `calendar/:date` redirect was missing and the
  in-app links were understated. **Applied:** both redirect routes, the
  links listed, and a no-old-path test.
- staff-engineer 3, veteran-trader 8: the `killswitch` row holds only the
  current state. **Applied:** the latest transition only, worded by
  `engaged`; a history is a follow-up.
- staff-engineer 4, financial-advisor 1: "filled" wording. **Applied** (see
  veteran-trader 1).
- staff-engineer 5: `scan_finished` sources were not real columns.
  **Applied:** named as `scan_progress` doc keys, dropped if absent.
- staff-engineer 6: `PreferencesStore` already exists and rejects
  localStorage. **Applied:** server-side only, keyed by destination path.
- staff-engineer 7: `navEntryFor` is first-segment only, and the label
  invariant breaks. **Applied:** a second-segment rule and a new invariant
  with recorded overrides.
- staff-engineer 8: there was no removal owner for the legacy names.
  **Applied:** Phase 4 close-out.
- staff-engineer 9: there was no rollback story. **Applied:** §7.
- staff-engineer 10: the Discord-drift claim and the bot-links task were
  no-ops. **Applied:** both removed.
- financial-advisor 2: R-only, pre-cost P&L. **Applied:** "(paper,
  pre-cost)" and a dollar figure in the neutral colour.
- financial-advisor 3: heat in dollars, over-cap distinct, one definition.
  **Applied.** Red over the cap is left to the risk-manager.
- financial-advisor 4, veteran-trader 3/4: the "N new plans" badge nudges
  checking and has no baseline. **Applied:** replaced by a "plans awaiting
  order" state count with the next expiry.
- financial-advisor 5, veteran-trader 5: a collapsed dock hides alarms.
  **Applied:** the edge tab and strip take a warning tone in the listed
  conditions.
- financial-advisor 6, veteran-trader 7: no staleness on the feed.
  **Applied:** Berlin-local times with age, "as of" on heat, and a "No scan
  since" warning.
- financial-advisor 7: the killswitch was not stated in plain language.
  **Applied:** "Active: new alerts paused since …".
- financial-advisor 8: no concentration row. **Applied:** named in What
  follows.
- veteran-trader 6: stale or disconnected state was lost from the top bar,
  and the market session showed only open/closed. **Applied:** an alarm
  chip shown only while it applies, and a session row as far as the
  existing state supports.
