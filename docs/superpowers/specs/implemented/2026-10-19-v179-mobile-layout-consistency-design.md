# v179 — Mobile layout consistency: compact rows, a trade drawer, one style per primitive

**Version:** ui 1.31.0 · bot 2.12.0 (at writing)
**Bump:** ui minor — every phone user sees a different Trades, Dashboard, Watchlist, Research and Risk (rows become two-line items that open a drawer), and the Dashboard opens trades in a drawer on every device; bot none.
**Edge:** none (integrity) — readability and touch ergonomics of the admin UI. It changes no signal, gate, stop, size or badge.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, financial-advisor
**Status:** spec written 2026-10-19 from a mobile audit and a brainstorm with the partner (phone-table pattern, drawer scope and the playback of §3 approved in chat: "do it").

## 1. Why

The partner asked for every screen to be checked on a phone and reorganised so
that components are consistent, no text overflows, everything is responsive
and easy to read. Mid-audit they added two requirements in their own words:

- "use the drawer component to display the trade information in the
  Dashboard page";
- "make sure that texts are aligned with each other. In the same row, they
  should have the same height. Not this text higher than the other text and
  vice versa."

v95 (implemented) built the responsive scaffolding: `BREAKPOINTS`,
`ViewportService.isPhone()/isNarrow()`, column demotion ladders
(`inlineFrom`), 44px controls under a coarse pointer. This spec is the
follow-on audit of what is still wrong on top of it.

## 2. What the audit found (production, 2026-10-19)

Method: `frontend/scripts/browse.mjs shots` at 390px and 768px for all 27
routes/tabs, plus a Playwright DOM audit at 390px (mobile + touch emulation)
measuring text clipping, elements past the viewport edge, tap targets
under 44px, sub-11px text and baseline offsets between side-by-side text in
one flex/grid row. Observed on screen, not inferred from CSS.

### 2.1 Overflow

- **Analytics → Attribution** pushes the page 102px wide. The Strategy ×
  horizon `sb-heat-grid` clips after `7m` (8m/9m off-screen, not in a scroll
  box); `sb-bar-list` puts its `n=` column at x=462 and the value at x=398;
  `sb-waterfall` labels and the pager's last button sit past the edge.
- **Analytics → Partials** is 58px wide: the two-column `sb-stat-tile` grid
  runs to x=418 (the right tile's text is cut: "Closed runners that reached
  TP…"), and `sb-bar-list`, `sb-histogram`, `sb-share-bar`, a table panel and
  the footer all overflow with it.
- **Tab bars** (`sb-tab-bar` on Analytics, the System settings group strip)
  run off the right edge ("Pip…", "Scan…") with no affordance that they
  scroll.

### 2.2 Tables on a phone show two columns

Trades, Dashboard Open positions, Watchlist and Research registry render the
full table inside a horizontal scroller. At 390px, Open positions shows
ticker and P&L, with Plan cut mid-number; Trades shows ticker and half of
Plan; Research's registry wraps names to three lines and the badge-tier
column to five. Nothing signals that more columns exist off-screen except a
thin scrollbar.

### 2.3 The same thing looks different on each page

- **Stat tiles.** Analytics and Risk: large left-aligned value, label above,
  `N=` below. Calendar: small centred tiles, and three of them ("BEST DAY
  +173.48 €", "WORST DAY −73.33 €", "AVERAGE DAY") put label and value on one
  line while the others stack them. Tile heights in one row differ
  (Analytics "Total R" vs "ExpR").
- **Filter areas.** Trades: chip row → `Columns 12/29` → a grey 27px-tall
  "Filters 13" block → ~60px of empty space → `Sort` select. Watchlist: a
  27px "All" chip, a 44px input and a grey "Filters 2" block side by side at
  three heights. Analytics: five selects wrap 2 + 3 with unequal widths.
  Calendar: segmented control, then full-width-ish selects at another width.
- **Panel headers.** Inner padding between header and first row varies
  (Trade detail: "Levels" vs "Opened"). The Dashboard "Trading performance"
  header stacks a bordered "Today" button over a borderless "All days" one.
- **Numbers.** In one list some values are monospace and some proportional
  (Trade detail: `240.40` mono, `5.51%` and `1,000.00` sans).

### 2.4 Text in one row sits at different heights

Measured as baseline offset between side-by-side text in one row:

| Where | What | Offset |
|---|---|---|
| Trade detail title | `MRVL` 18px beside `● CLOSED` 11.7px, centred not baseline-aligned | 3px |
| Calendar totals | "Win rate" vs "Winning days" | 4px |
| Calendar tiles | inline label + value at two sizes ("BEST DAY +173.48 €") | visible |
| Versions | "RUNNING NOW" label vs the version pills | visible |
| Dashboard | "TRADING PERFORMANCE" label vs the stacked Today/All days | visible |
| Analytics | `N=972 closed · as of …` vs the R/%/$ segmented control | visible |
| Analytics | Equity panel header "Equity N=972 −2,150.95 € ⓘ" | visible |

### 2.5 Readability and touch

- 9.9px text: section labels (`sb-panel > h2.sb-label`), pager and select
  labels, side-menu tagline and footer, `sb-stat-tile` label/sample,
  freshness stamp, outcome-strip captions.
- Under 44px tap targets on phone: side-menu links 171×34, filter chips
  ×27, `Columns` trigger ×27, table sort buttons ×14, header cells ×27,
  `sb-row-link` 51×17, "View all"/"all" links ×16, checkboxes 13×13,
  `sb-segmented` segments 28–34px wide, panel-header table toggle 28×16.

## 3. Design

### 3.1 Phone tables become compact rows plus a drawer

Below 640px (`ViewportService.isPhone()`), `sb-data-table` renders each row
as a **compact row**: two lines, the row's identity and its key facts, full
width, at least 44px tall. Tapping it opens `sb-drawer` (already a bottom
sheet below 640px) holding the rest of that row. Tablet and desktop keep the
table exactly as today.

- **Declared, not hand-built.** Each table says which columns fill line 1
  and line 2 of its compact row (and in what order) in its column
  definitions, next to the existing v95 demotion data. `sb-data-table` does
  the rendering; no workspace builds its own cards.
- **The drawer body** lists every other visible column as label/value pairs,
  plus the row's existing actions (`sb-row-actions` where the table has
  them) and, where the row has a detail page, an "Open full …" link.
- **Applies to:** Trades, Dashboard Open positions, Watchlist, Watchlist →
  ticker detail's trade list, Research registry, Risk open positions.
  Any other `sb-data-table` gets the behaviour automatically
  once it declares compact fields; a table without the declaration keeps
  today's scroller (so nothing regresses before it is migrated).
- **Sort and paging stay.** The phone sort `<select>` and pager remain above
  and below the compact list.
- Expandable rows (the ▸ disclosure) are replaced on phone by the drawer;
  the expanded content is the drawer's content.
- **Money and risk floor.** A table of open positions (Dashboard, Trades,
  Risk) keeps P&L as an amount (€) and either the stop distance or the risk
  amount on line 1 or 2 — never only behind a tap.
- **Badge floor.** The Research registry and any strategy row keep the badge
  tier on line 1, and the evidence freshness stays on the compact row, so a
  WEAK strategy never reads like a validated one.

### 3.2 The Dashboard trade drawer, on every device

On the Dashboard, activating a trade in **Open positions** or **Recent
activity** opens `sb-drawer` with that trade instead of navigating away — on
desktop a side drawer, on phone the bottom sheet. Partner's choice: every
device.

- Content: ticker, direction, status, P&L (% and amount), the plan levels
  (trigger/entry, stop, TP1, TP2, R:R), opened/held, strategy and horizon,
  the row's existing actions, and **"Open full trade →"** to `/trades/:id`.
- The header carries a **"Paper trade"** marker (the bot is paper-only;
  a drawer styled like a position ticket must not read as a live position).
- The open trade is in the URL as a query parameter, written as a **pushed**
  history entry (never `replaceUrl`), so Back closes the drawer and the state
  is linkable. *(Builder's call on the name. There is no precedent to copy:
  Research's drawer is store-only state, `research.store.ts` `selectedId`.)*
- Data comes from the row already loaded; no extra fetch is required for the
  summary. Anything not on the row is out of the drawer, not fetched.
- **Row source.** `sb-positions-table` owns its own `TradesStore`
  (`positions-table.ts`), so the Dashboard does not reach into it: the row
  arrives through `rowActivate` and the Dashboard holds it in a signal.
  Activity rows resolve from the Dashboard's own `TradesStore`.
- **A link whose trade is not loaded** (a reload while an Open positions row
  was open, a closed trade older than the activity window, a shared link):
  the Dashboard looks the id up in the rows it holds; if absent it navigates
  to `/trades/:id` with `replaceUrl` instead of opening an empty drawer or
  fetching.
- The drawer is the same component the phone compact rows open (§3.1), so the
  Dashboard on phone gets one consistent behaviour.

### 3.3 One standard per shared primitive

House style, chosen by Claude during the brainstorm (the partner approved the
playback):

- **`sb-stat-tile`**: the Analytics/Risk layout everywhere — label, value,
  `N=`, hint, stacked, left-aligned. Calendar's centred and inline variants
  are removed. Tiles in one grid row stretch to equal height. The tile grid
  is `repeat(auto-fit, minmax(<min>, 1fr))` so it never overflows (fixes
  Partials).
- **Filter area (`sb-control-bar` / `sb-filter-bar`)**: one row pattern —
  chips (scrollable single line on phone), then `Filters`, `Columns` and
  `Sort` as same-height 44px controls on one line that wraps as a unit. The
  grey "Filters N" block is restyled as a normal button with a count badge.
  Selects in a filter grid share one width rule (two equal columns on
  phone).
- **`sb-tab-bar`** (and the System settings group strip): horizontally
  scrollable with an edge fade where more tabs exist, and the active tab is
  scrolled into view on load and change.
- **`sb-panel` / `sb-panel-header`**: one header height and one gap to the
  first content row on every panel; label, counts (`N=`), actions and the
  hint glyph sit on one baseline. The Dashboard performance header puts
  Today / All days in an `sb-segmented` control on the header line.
- **Numbers**: every numeric value (`.num`, table numeric cells, key/value
  values, stat values) uses the same tabular numeric font. Label text stays
  in the UI font.
- **Charts and grids** (`sb-heat-grid`, `sb-bar-list`, `sb-histogram`,
  `sb-share-bar`, `sb-waterfall`): either reflow to the container width or
  scroll inside their own box with a visible edge fade. They never widen the
  page. `sb-bar-list` drops to a two-line item (label + value/N on one line,
  bar on the next) when its container is narrow.

### 3.4 Alignment and readability

- **Mixed sizes on one line align on the text baseline**
  (`align-items: baseline` or `last baseline`), never centre. This covers
  the trade title, Calendar totals, Versions "Running now", panel headers,
  the Analytics population line, and any key/value row.
- **Minimum text size 11px** (`0.6875rem`) everywhere, including
  `.sb-label`, pager/select labels, stat-tile label/sample, side-menu
  tagline and footer, freshness stamps, chip text.
- **Every interactive control at least 44×44px on phone and tablet**
  (hit area — the visible element may stay smaller if a padded hit area
  reaches 44px): side-menu links, chips, `Columns`/`Filters` triggers,
  sort headers, row links, "View all" links, checkboxes, `sb-segmented`
  segments, panel-header toggles.
- Small copy defects found on the way are fixed with it (e.g. Trade detail
  "Confirmed by:Fib" missing a space; Analytics Partials population reads
  "N=— closed").
- **An empty sample reads as "no data", never a dash beside a value**: a
  population line or tile with no N says "no closed trades" (or "n/a" where
  the unit is not trades).

### 3.5 Guarding it

The audit becomes a checked-in, repeatable check so the defects cannot come
back:

- A Playwright audit script under `frontend/scripts/` that visits every route
  and tab at 390, 768 and 1440px against a running instance and reports, per
  page: horizontal page overflow, text past the viewport outside a scroll
  box, clipped text that is not `sr-only`, interactive elements under 44px
  (phone/tablet only), text under 11px, and baseline offsets over 2px
  between side-by-side text in one row. Exit non-zero on any finding not in
  an explicit allow-list file (each allow-list entry carries a reason).
- Unit tests (the existing Angular spec setup) for the new behaviour:
  compact-row rendering from declarations, drawer open/close from the URL,
  stat-tile single variant, tab-bar scroll-into-view.
- The Playwright audit is a pre-merge check, not CI (see §6a.6).

## 4. Goals, non-goals, anti-goals

**Goals:** zero horizontal page scroll and zero clipped text on every route
at 390, 768 and 1440px; one look per primitive; baseline-aligned rows; 11px
minimum text; 44px touch targets on phone and tablet; Dashboard trades in a
drawer on every device; phone tables readable without sideways scrolling.

**Non-goals:** new data, new endpoints, new metrics; changing desktop table
layouts beyond the shared-primitive fixes; redesigning chart internals
(candles, equity chart) beyond keeping them inside their box; the Gallery
page beyond showing the new primitive variants.

**Anti-goals** (failure even if it "works"):
- Phone users lose access to a column they can see today — every visible
  column must be reachable in the compact row or its drawer.
- Each workspace hand-rolls its own cards or media queries instead of
  declaring compact fields.
- Desktop gets visibly worse (denser, smaller, or loses the full-page trade
  route).
- The Dashboard drawer fetches more than today's page already does.
- Any existing cost, tax, paper-trade or pre-tax caption or ⓘ hint
  disappears in the migration (stat-tile unification, Calendar variants,
  drawer content). Captions move with their figure; they are never dropped.

**Blast radius and rollback.** The shared primitives (`sb-data-table`,
`sb-stat-tile`, `sb-panel`, `sb-tab-bar`, control bars) are used by every
admin workspace, so a defect shows on every page — but only in the admin UI:
no alert channel, store, schema or backtest is touched. Rollback is a plain
image rollback (`scripts/ops/rollback_to.sh`).

## 5. Constraints

- Every UI change is designed and checked at phone, tablet and desktop
  together (`docs/claude/ui-design.md`); browser checks via Playwright only,
  signed in with `.env` credentials loaded inside the script.
- Table paging rules stay as in `ui-design.md` § Tables and pagers
  (5/10/20/50/100/All, per device class).
- Every function changed stays under cyclomatic complexity 15.
- The v95 column-priority declarations remain the single source of which
  columns exist per class; compact-row fields extend that declaration, not
  a second list.
- Motion follows the existing motion system (drawer enter/exit already
  defined; phone motion preference stays off by default).

## 6. Left to the builder

- Exact compact-row field choices per table (guided by: identity + direction
  + the one number a trader checks first on line 1; plan or price context on
  line 2).
- The query-parameter name for the Dashboard drawer and how it composes with
  existing Dashboard parameters.
- Whether tab-bar scrolling uses CSS scroll-snap or plain overflow.
- The order of work and how to split it into plan parts.

## 6a. Decisions from the builder check

A fresh builder read this spec and asked seven questions. None needed the
partner; each is settled here as Claude's call (or by the code) so the plan
does not guess.

1. **Compact fields vs v95 `inlineFrom`.** On phone, the compact row
   *replaces* the pinned-cell inlining; `inlineFrom` keeps governing tablet.
   `ColumnDef` gains one optional compact declaration (line 1 or 2, plus
   order). The drawer lists every column the user's `Columns` choice makes
   visible that is not already on the compact row; a column hidden through
   the picker stays hidden in the drawer too ("reachable" means everything
   the table would show today).
2. **Drawer cells render each column's existing cell template** (badges,
   `sb-plan-cell`, `sb-pnl-cell`, …), laid out as label/value pairs — no
   plain-text re-rendering and no second renderer per column.
3. **Dashboard rows are full trade rows** (answered by code): Open positions
   comes from `sb-positions-table`'s own `TradesStore`, and Recent activity's
   `ActivityEvent`s are derived from trade rows the Dashboard's `TradesStore`
   already holds (`activity.ts:deriveActivity`, event id
   `<trade id>:<kind>`). The drawer resolves the trade row from those, so §3.2
   needs no fetch.
4. **Two drawer contents, one `sb-drawer`.** A generic row drawer owned by
   `sb-data-table` (§3.1), with an optional `detailLink(row)` input — tables
   with no detail page (Versions, Risk, Research registry) simply show no
   link. The Dashboard uses a trade-specific `sb-trade-drawer` content
   component (§3.2) for both Open positions and Recent activity on every
   device.
   **Precedence:** `sb-data-table` gets one input choosing what a phone row
   tap does — open the generic drawer (default) or emit `rowActivate` only.
   A page that already owns a drawer for its rows (Research registry,
   Dashboard positions) sets "emit only", so one tap never opens two drawers.
   Every existing `rowActivate` consumer is checked and its choice stated in
   the plan.
5. **URL state:** only the Dashboard trade drawer writes a query parameter.
   Research keeps its store-only drawer. Generic table drawers are local
   component state; they close on Escape, backdrop tap, navigation and page
   change.
6. **The audit** runs against a local instance on the `/replicate-prod-db`
   replica or read-only against production, as the builder prefers. The
   allow-list may cover canvas/third-party chart internals with a reason per
   entry. It is a Node/Playwright script, **not** a pytest suite and **not**
   in CI: it is a documented pre-merge check and runs in the plan's final
   verification task. §3.5's CI option is closed. **Ownership:** the plan
   records the check in `docs/claude/ui-design.md` § Checklist (with its
   `AGENTS.md` mirror) as a step for any UI change; every allow-list entry
   carries a reason and a date, and an entry whose target no longer exists is
   removed by the script's own run (it reports stale entries).
7. **Phone sorting** uses only the existing phone sort `<select>`; compact
   mode renders no header row, so header sort buttons do not exist there.
   Tablet/desktop header sort buttons get the 44px hit area under coarse
   pointers.

## 6b. Corrections from the code brief

The plan brief (`.superpowers/briefs/2026-10-19-v179-mobile-layout-consistency.md`)
read the code and found places where this spec was wrong or vague. These
override the sections above.

1. **Versions has no `sb-data-table`** (`versions.ts` renders `sb-timeline`
   cards). It drops out of §3.1's list; only the "Running now" baseline fix
   (§3.4) applies to it.
2. **Research:** the `rowActivate` + store-only drawer belongs to the
   **Pre-registration ledger** table (`research.ts` ~113-166), not the
   registry. The ledger sets "emit only" (§6a.4); the **registry** takes the
   generic drawer, with the §3.1 badge floor.
3. **Recent activity rows are not interactive today** (a plain `<li>`
   list). They become buttons that open the trade drawer. `ActivityEvent`
   gains an explicit `tradeId` field rather than parsing it out of
   `id` (`<tradeId>:<kind>`).
4. **Today, `rowActivate` navigates away** on Trades, Dashboard positions and
   Watchlist. On phone, Trades and Watchlist switch to the generic drawer
   (whose "Open full …" link keeps the old destination). The Dashboard
   switches to the trade drawer on every device.
5. **`sb-tab-bar` already has edge fades**; it only lacks
   scroll-active-into-view. The System settings group strip is
   `nav.category-rail` (`system/settings-tab.ts`), not a tab bar. It gets the
   same fade and scroll-into-view treatment.
6. **The 9.9px text comes from the shell zoom preference** (`--text-scale`,
   here set to 90%), not a token bug. The 11px floor is applied as a clamp
   in the micro/label tokens (`max(11px, …)`). Zoom still scales everything
   above the floor. *(Claude's call: a zoomed-out view should fit more, but
   not drop its smallest labels below legibility.)* After any `tokens.css`
   edit, `python scripts/dev/dump_tokens.py` regenerates the jsdom fixture.
7. **Partials' `.kpis` grid is already `auto-fit`**, so its 58px overflow has
   another origin. The plan task reproduces it in a browser before fixing it.
8. **The Dashboard route has `runGuardsAndResolvers: 'always'`**, so pushing
   the drawer's query parameter would re-run the resolver and refetch. The
   route's rerun rule changes so that a change to the drawer parameter alone
   does not re-resolve. A unit test pins that §3.2 "no extra fetch" holds.
9. **The v80 "no cards" decision is reversed on purpose.** The test that pins
   it (`data-table.spec.ts`) and the docstring at `data-table.ts` (~518-537)
   are rewritten to record compact rows, citing this spec.
10. **The complexity gate is Python-only**: radon cannot read TypeScript and
    ESLint has no complexity rule. TS functions are still kept small and
    table-driven, but no gate enforces it here.

## 7. Success criteria

1. The audit script reports zero unallowed findings on every route and tab
   at 390, 768 and 1440px against production data (replica or prod).
2. Screenshots at the three widths for every route are attached to the final
   plan task and reviewed.
3. On the Dashboard at 1440px and 390px, clicking/tapping an open position
   or an activity row opens the drawer; Back closes it; "Open full trade"
   reaches `/trades/:id`.
4. Full test suite green (`python scripts/dev/testrun.py full`: 0 failed,
   0 xfailed), complexity gate clean, **and** the frontend gates the CI
   `frontend-test` job runs: `npm test` and `npm run lint` in `frontend/`.
5. A column-reachability unit test per migrated table: compact row plus
   drawer together cover every column the table shows today at that device
   class (the §6a.1 rule), so the §4 anti-goal is verified, not stated.

## Panel review

Spec review, 2026-10-19, against e48ca1f0. No BLOCKING findings.

- staff-engineer: "Research already does the same" was false (store-only drawer, `replaceUrl` only for filters) -- applied (§3.2, §6a.5).
- staff-engineer: linkable vs no-fetch clash for a trade not in loaded rows -- applied (§3.2: redirect to `/trades/:id`).
- staff-engineer: positions-table owns its own `TradesStore`; name the row-source seam -- applied (§3.2 Row source).
- staff-engineer: Research would get two drawers for one tap; precedence for every `rowActivate` consumer -- applied (§6a.4).
- staff-engineer: audit and allow-list need an owner and an expiry rule -- applied (§6a.6).
- staff-engineer: success criteria must name `npm test` and `npm run lint` -- applied (§7.4).
- staff-engineer: no blast-radius/rollback note -- applied (§4).
- financial-advisor: compact rows need a floor for money/risk fields -- applied (§3.1).
- financial-advisor: badge tier and freshness must stay on registry compact rows -- applied (§3.1).
- financial-advisor: no cost/tax/paper caption may be dropped in the migration -- applied (§4 anti-goal).
- financial-advisor: "N=— closed" fix must say what replaces the blank -- applied (§3.4).
- financial-advisor: drawer must say it is a paper trade -- applied (§3.2).
- financial-advisor: verify column reachability, not just state it -- applied (§7.5).
