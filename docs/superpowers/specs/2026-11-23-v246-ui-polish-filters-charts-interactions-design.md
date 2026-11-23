# v246 — UI polish: aligned filter bars, one chart theme, audit fixes at three widths, presets and drill-down

**Version:** ui 1.47.0 · bot 2.19.6
**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** ux-designer, staff-engineer, financial-advisor

## Why

On 2026-11-23 the partner asked for four things on bomeo-capital.com and for
a review of every page at every device size, down to the small details:

1. The dashboard's **Recent activity** rows should show only the signed R
   (`SOFI −1.00R`), not `SOFI Closed at −1.00R`.
2. **Calendar** should be its own page at the same level as Watchlist and
   Trades, on desktop and tablet too. (This is already in the v240 spec as
   its plan 3, which has not been written. See "Relation to v240".)
3. When a row of inputs and dropdowns has labels above them, **every control
   in that row must line up**, whether it has a label or not.
4. The **charts** should look better.

The audit used Playwright screenshots of production (ui 1.47.0) at 1440×900,
820×1180 and 390×844 across Dashboard, Watchlist, Trades, Calendar, Risk and
Insights → Analytics. Each finding below says which width it was seen at. The
partner approved the design section by section on 2026-11-23.

## Relation to v240

v240 §6 already designs Calendar as its own page (`/calendar`, its own icon
in the side menu after Trades, Trades losing its Book/Calendar sections, old
links redirecting, the `spa.py` change). Its plan 3, "Shell and
navigation", has not been written. **Partner decision (2026-11-23): Calendar
ships through v240 plan 3, written next. This spec does not repeat it.**
Every v246 plan runs after v240 plan 3 is merged. Plan B's table work also
runs after v240 plan 4 (drawer core), because both edit
`ui/data-table/`.

Already fixed on `main`, waiting for a deploy, so not in scope: the focus
outline drawn around every page title on load (b0061a3d, "do not focus the
page heading when the page opens").

## Decisions (partner, 2026-11-23)

- D1. One spec, three plans: **A** = requests 1, 3 and 4. **B** = the audit
  fixes. **C** = the interaction ideas. A ships first.
- D2. Plan C takes all four ideas: chart crosshair and click-through to
  trades, saved filters and presets, the most important columns first on
  tablet and phone, and undo toasts / loading placeholders / value flashes /
  one "Updated" stamp per page.
- D3. Destructive buttons: Clear open, Clear history and Close all
  open/partial move into a "⋯" page-actions menu. Engage killswitch stays
  visible on Risk, as an outlined danger button instead of solid red. All
  confirm dialogs stay as they are.
- D4. Charts: time series (Analytics equity and drawdown) move onto
  `lightweight-charts`, which is already a dependency and already draws the
  Dashboard equity candles. One shared theme covers it and every SVG chart.
  Bars, the R distribution and the mini charts stay SVG but use the theme.
- D5. Saved filters and presets are stored **on the server, per login**, so
  they follow the partner between phone, tablet and desktop.
- D6. Calendar ships through v240 plan 3 (see "Relation to v240").

## Design

### Plan A §1. Recent activity shows the R only

`workspaces/dashboard/panels/activity.ts:58` builds a closed row's detail as
`` `Closed${r != null ? ` at ${rMultiple(r)}` : ''}` ``. After: a closed row
with R reads just `rMultiple(r)` (`−1.00R`), coloured by sign the way the
panel already colours R. A closed row **without** an R keeps the word
`Closed`, so the row is never blank. Opened rows (`at 204.46`) and cancelled
rows are unchanged. The R is the book's R, **pre-tax and before modelled
frictions**, the same basis as the "pre-tax, before modelled frictions"
caveat the Dashboard already prints. The panel's hint says so. The row's
accessible name keeps the status word ("SOFI closed, −1.00R"), so dropping
the visible word costs a screen reader nothing. `activity.spec.ts:31-34` and
`recent-activity.spec.ts:116` change with it. A new case covers a closed row
with no R. The trade drawer's "Closed at" field (`trade-drawer.ts:90`) is a
price label, not this text, and stays.

### Plan A §2. Every control in a row lines up

**What's wrong.** `ui/control-bar.ts:35` lays the bar out as a flex row with
`align-items: center`. A field with a label above it (`STRATEGY` + select) is
taller than a control with no label (the month arrows, the €/R/Trades/Win
rate switch, the date range), so centring puts their boxes at different
heights. Seen at 1440 and 820 on Calendar (the month arrows and the €/R
switch sit about 28px above the selects), on Analytics (the date boxes sit
above the Ledger, Strategy, Horizon and Direction selects, and the R/%/€
switch drops to a row of its own), and on Trades (the date range sits
unlabelled on the chip row, and the Ticker and Strategy boxes are about
twice as wide as the selects).

**The rule.** One component, `sb-field`, in a new `ui/field.ts`. It wraps
one control with a label slot above it: `label` input. With `label` empty,
the slot still takes up the label's line height (`aria-hidden` filler). That
keeps every field in a bar the same height, and the controls line up
whether or not they show a label. `size` input `s | m | l` (S for a
single-value select such as Horizon or Direction, M for Strategy or a date,
L for a free-text search such as Ticker). The widths are tokens:
`--field-s`, `--field-m`, `--field-l` in `styles/tokens.css`, with values
chosen in the plan from the widest current option label at each size.

**The bars that exist (staff-engineer review).** There are four layouts,
not one:
- `sb-control-bar` (`control-bar.ts:35`, `align-items: center`): used by
  Trades, the Analytics scope bar and the Gallery.
- `sb-filter-bar` (`filter-bar.ts:43`): **already** `flex-end`.
- `sb-toolbar` (`toolbar.ts:80-91`, 8 consumers including Watchlist).
- Calendar's month row: its own flex (`calendar.ts:407`), with no shared
  bar.

`sb-control-bar` and `sb-toolbar` switch to `align-items: flex-end`, so
fields line up along the bottom even if a label wraps. Calendar's month row
moves into an `sb-control-bar`. Every control inside these bars is wrapped
in an `sb-field`.

**Control height.** Every control in a bar consumes the `--control-h`
token: `sb-select`, `sb-text-input`, `sb-date-range`'s two inputs,
`sb-segmented`, the month arrows and the "Clear N" button. The token is
28px at its base and 44px below 1024px (`styles/tokens.css:311,410`), so
touch targets come free.

**Test.** A test gives each consumer bar a fixed size and asserts every
control's bottom edge is the same, at both token values.

**Date ranges.** `sb-date-range` becomes one field: one label ("Opened",
"Range"), with From and To inline at M width each and the dash between them.
Below 640px the field takes the full row and From / To split it 50/50.
That fixes the Analytics date range running off the screen at 390 (the
second date was clipped).

**Toggle groups.** The €/R/Trades/Win rate switch, R/%/€, 1H/4H/1D/1W,
Open + closed / Closed only, and Compact/Full all render as `sb-segmented`
in one style, with a label when they sit in a bar ("Show", "Units",
"Interval", "Trades", "Density"). Compact/Full stops being two plain-text
buttons.

**Consumers in this plan:** Trades (`trades.ts`), Calendar (`calendar.ts`),
Analytics scope bar (`analytics/scope-bar.ts`), Watchlist (`watchlist.ts`),
and the Dashboard trading-performance toggles. The other `sb-toolbar` and
`sb-control-bar` consumers (System logs/scan/settings, Research, Tuning,
Partials, Attribution, Benchmark) get the `flex-end` change now. Their
controls are wrapped in `sb-field` by plan B's B10.

**The consistency gate.** Plan A extends `workspace-consistency.spec.ts`:
a control in a bar that sits outside an `sb-field` fails. It ships with an
allowlist naming those not-yet-wrapped consumers, so it passes when A
merges. B10 empties the allowlist and deletes it.

**Phone.**
- `control-bar.ts:72-76` keeps the two-column grid below 640px. Fields fill
  their grid cell (full width, not their desktop size), so a 2-2-1 stack
  shows equal widths, not the ragged "each select as wide as its text" seen
  at 390.
- Controls that take a full row below 640px (month arrows, segmented
  groups, "Clear N") drop the empty label filler, so they leave no blank
  line.
- A segmented group with 3 or more options takes the full row, splits it
  into equal segments, and never wraps.

### Plan A §3. One chart theme, and the time series on lightweight-charts

**What's wrong.**
- Dashboard equity candles: a handful of thin candles with gaps between
  them. The axis prints `997800.00` without thousands separators, a stray
  `)` sits at the left of the time axis (1440), and at 390 the current-value
  tag covers an axis label.
- Analytics equity and drawdown: hand-drawn SVG step lines in a blue that
  appears nowhere else on the site. No axes, no zero line. Drawdown is drawn
  as a line instead of a shaded area below zero.
- R distribution buckets are labelled at odd centres (−4.9R, −3.9R, −3.0R).

**`ui/chart/chart-theme.ts`** (new). One module exports:
- the series colours, read from the CSS tokens at runtime so the Navy and
  Black themes both work: up/win = `--money-pos`, down/loss =
  `--money-neg`, neutral line = `--accent`, grid = `--border-subtle`,
  axis text = `--text-secondary`, crosshair = `--text-tertiary`;
- `priceFormat` (thousands separators, 2 decimals, the true minus sign from
  v240 plan 2b) and `rFormat` (signed, `R` suffix);
- `applyChartTheme(chart)`, which sets layout, grid, crosshair, time scale
  and price scale options on any `lightweight-charts` instance;
- `SVG_CHART_TOKENS` for the SVG charts (stroke widths, bar radius, gap,
  label size).

The theme listens to `theme.service.ts` so a theme switch repaints the
charts without a reload.

**`sb-time-series`** (new, `ui/chart/time-series.ts`). A thin
`lightweight-charts` wrapper: `kind: 'area' | 'baseline' | 'candles'`, a
`points` input, `valueFormat: 'price' | 'r' | 'pct'`, and a `height`
input. It owns create/resize/destroy (a `ResizeObserver`, removed on
destroy) and applies the theme.
- `area` draws the equity curve: the accent line with an accent→transparent
  gradient underneath.
- `baseline` with base 0 draws drawdown: the area below zero filled with
  `--money-neg` at low opacity, plus a zero line.

The Analytics Overview equity and drawdown move onto it and keep their N and
total labels in the card header. The drawdown header adds the money units a
retail trader feels: max drawdown in € and the longest losing streak, read
from what `risk_metrics.py` already computes. Neither is a new
calculation.

**Linked scrolling.** The two charts scroll together. `lightweight-charts`
5 has no shared time scale, so each chart subscribes to the other's
`subscribeVisibleLogicalRangeChange`, with a guard flag against
ping-pong. `sb-time-series` unsubscribes in its `DestroyRef.onDestroy`,
alongside its `ResizeObserver` and its `theme.service` subscription. A
spec asserts all three are released on destroy.

**Dashboard equity** (`dashboard/panels/equity-candles.ts`) calls
`applyChartTheme` and uses `priceFormat`. Its last-value tag shifts so it
never sits on top of an axis label (`lastValueVisible` with
`priceScale.scaleMargins`, or the tag moved into the header next to the
balance on narrow widths; the plan picks after measuring at 390). The stray
`)` tick goes. The time axis shows only whole hours or days.

**SVG charts** (`line-chart.ts`, `histogram.ts`, `bar-list.ts`,
`sparkline.ts`, `share-bar.ts`, `gauge.ts`) take colours and stroke values
from `SVG_CHART_TOKENS` instead of their own literals. The R distribution
puts its buckets on whole-R edges (`[−5,−4)`, … `[5,6)`) and labels each by
its lower edge.

**Out of plan A, into plan C:** the crosshair *tooltip* and click-through.
Plan A turns the crosshair line on but adds no click handling.

### Plan B. Audit fixes

Each item names the width where it was seen. All are fixed and then checked
at all three widths.

**B1. Phone header overlap (390).** The profile button sits on top of the
"Armed" pill and turns its text into "Arm@d". Shell header: the right-side
items get a gap and `flex-shrink: 0`. Below 480px the profile button shrinks
to 32px, and "Enable voice" shows only its icon (it keeps its accessible
name and gets a tooltip).

**B2. Page-actions menu (all widths).** A new `sb-page-actions` component:
a "⋯" button (`--control-h`, accessible name "More actions") that opens a
menu, anchored to the button on desktop and tablet and a bottom sheet below
1024px (reusing v240 plan 4's sheet). It holds Trades' **Clear open** and
**Clear history** and the Dashboard's **Close all open/partial**. Each item
keeps its current confirm dialog and copy. Danger items are red text in the
menu and come last, after a divider. Keyboard:
- Enter or Space opens the menu.
- Arrow keys move between items, and Home/End jump to the first/last.
- Esc closes it, and focus returns to the "⋯" button.
- The bottom sheet traps focus with `ui/focus-trap.ts`.

Close all's confirm copy states what is being closed: the number of open
and partial positions and the € currently at risk (open risk from the
Dashboard tile). Risk's **Engage killswitch** stays in
the page header as an outlined danger button (`--money-neg` border and
text, transparent fill), with a 16px gap after Refresh. At 390, Refresh and
Killswitch sit on one row.

**B3. Big numbers fit (390, 820).** `stat-tile` / `metric-card` values
wrapped mid-value (`59,701 € ·` / `5.98%`, `−131.22` / `€`, `997,659.81` /
`€`).
- The value and its unit sit in one non-breaking group.
- The value's font size steps down from `--text-kpi` through two smaller
  steps until it fits (a `ResizeObserver` measures it once per resize, never
  per frame).
- A compound value (`159 € · 0.02%`) puts its second half on a second line
  at the secondary size instead of wrapping arbitrarily.
- **The sign and the unit are never dropped, and a value is never cut
  with "…".** If a value still doesn't fit at the smallest step
  (`--text-body`), the whole value wraps onto a second line. A clipped
  `−131…` would read as a different number.
- **No reveal is hover-only (ux-designer, BLOCKING).** With a fine pointer
  (`@media (pointer: fine)`), titles are capped at two lines ending with
  "…" and the full title sits in the tile's hint. With a coarse pointer
  (touch), titles wrap in full with no cap. Values sit on a shared baseline across a row, so a long
  title no longer pushes its value below its neighbours' (seen on Analytics:
  "MAX DRAWDOWN · CUMULATIVE R, SELECTED RANGE").
- Open Risk on the Dashboard uses the same size as its neighbours (it is
  larger today).

**B4. Tables (1440, 820).**
- The last column was cut off with no sign of it: Dashboard open positions
  (Opened column) and Trades (P&L). `sb-data-table` gets a right-edge scroll
  shadow while there is more to the right, and keeps its first column
  pinned.
- Status shows as one badge everywhere: `Pending`, `Open 35%`, `Partial`,
  `Closed`, `Cancelled`. Today it's a bare % bar for open trades and
  `• CLOSED` for closed ones. The open progress bar stays inside the badge
  with a tooltip: "35% of the way from entry to TP1". The same sentence is
  also printed in the expanded row or drawer, so touch has a way to read
  it.
- The badge tier (VALIDATED / WEAK / …) becomes a coloured badge instead of
  plain white capitals. **Only VALIDATED is green** (`--money-pos` family).
  WEAK is a muted amber. Every other tier is neutral grey. No tier uses the
  loss red. A WEAK strategy must never read as a pass (`known-traps.md`
  § Live plans are almost never VALIDATED).

**B5. Calendar (all widths).**
- Today gets an outlined marker.
- Days outside the month are dimmed to `--text-tertiary`, with no tint even
  if they had trades.
- Sat and Sun columns are half width at ≥ 1024px, never narrower than
  64px.
- The count in each cell's corner gets a label: "22 trades" in weekday
  columns at ≥ 1024px. Weekend columns and narrower widths show just "22".
  The day page (one tap away) states the count in words, so no tooltip is
  needed.
- In the weekday tables, numeric columns and their headings are
  right-aligned and day names left-aligned (headings and numbers point
  different ways today).
- The phone day list shows `Mon 2 Nov` instead of `2026-11-02`.
- The "thin sample" note appears once per card instead of under each tile.

**B6. Watchlist (all widths).**
- Company names stop wrapping to 3 lines (which triples the row height
  today). With a fine pointer: one line, "…", and the full name on hover.
  With a coarse pointer: up to two lines, and the full name in the row's
  expanded view or drawer.
- The price cell drops the repeated date (`2026-11-23`) when it is today and
  keeps the age ("30 s ago").
- The `TAPE` column gets the heading "Tape" with a hint saying what +/−
  means. The plan reads `tape-prefs.ts` to word it.
- The card title stops repeating "Watchlist" (menu, page tab and card): it
  becomes "Symbols".
- The per-row trash icon moves into a row "⋯" menu. Removal uses plan C's
  undo toast once that ships; until then it keeps today's confirm dialog.
- At 390, the "All" chip sits beside the symbol search instead of alone on
  a row, and each card shows price and age on one line.

**B7. Risk (all widths).**
- The heat bar becomes full width, 8px tall, with tick marks at the 6% cap
  and today's used share (today it's a 1px line across half the card).
- While on `/risk`, the Live panel hides its Portfolio-heat block (the page
  already shows it) and links to the page instead.
- At 390, Refresh and Killswitch sit on one row (B2).

**B8. Analytics (all widths).**
- Dropdowns take the `sb-field` sizes.
- The two win rates get names that tell them apart. The tile becomes "Win
  rate (net R)" and the Outcome bar becomes "Wins (any profit)", each with a
  hint saying what it counts. Today, 28.99% beside "Wins 52%" reads as a
  contradiction.
  - The hint names the cause. The tile counts **trades** by net R (N=238
    scored). The Outcome bar counts **rows**, legs included (854 + 779 =
    1,633), and partial exits make a losing trade's TP1 leg a "win".
    The plan confirms these figures against `overview.ts` before writing
    the copy.
  - The hint adds that win rate is a constraint, not the edge, and that
    ExpR leads. The tile order keeps ExpR first, as it is today
    (`edge-priorities.md`).
- By month shows the last 12 months, with empty months greyed and labelled
  "no trades", instead of one bar and a half-empty card.

**B9. Dashboard (all widths).**
- Market movers: each tab becomes a two-column list (ticker, change), never
  a ragged three-column grid with a single item on the last row.
- The range chips (TODAY…ALL) use `sb-segmented` like the rest.

**B10. The `sb-field` sweep.** The remaining bars (System logs/scan/
settings, Research, Tuning, Partials, Attribution, Benchmark) wrap their
controls in `sb-field`.

### Plan C. Interactions

**C1. Crosshair tooltip and click-through.**
- **Tooltip.** Every `sb-time-series` shows a tooltip under the crosshair:
  date, value, and for equity the day's change. SVG bars use the existing
  `sb-chart-tooltip` with the same layout.
- **Touch: one gesture, one meaning.** A tap pins the tooltip, and a tap
  elsewhere clears it. Navigation is never on the bare tap. The pinned
  tooltip holds a "View N trades →" link, which is the drill-down.
- **Mouse.** A click does the same as following that link.
- **Keyboard and screen reader.** The chart host is focusable
  (`tabindex=0`, labelled with the chart's title). Arrow keys step through
  the points or bars, an `aria-live="polite"` region reads the tooltip
  text, and Enter follows "View N trades". The card's existing "Table"
  link remains the full data list.
- **Where the drill-down goes.** Trades, filtered to that slice:
  - `closedOn=YYYY-MM-DD` and `closedMonth=YYYY-MM` map onto the server's
    existing `closed_from` / `closed_to` filter (`trades.py:85-93`).
  - `rBucket=lo:hi` is **new server-side work** (staff-engineer review): a
    new allowlisted filter in `swingbot/admin/api_v1/trades.py`'s filter
    table (`:1121-1186`), with tests, built in plan C's backend part.
- **The slice chip.** The active slice shows as a removable chip in the
  control bar, with its N ("Closed on 5 Nov · N=3 ✕"). It carries the
  calendar's "thin sample" note when N is below the threshold the calendar
  uses, so a single trade doesn't read as a pattern. It counts toward
  "Clear N".
- **Calendar** keeps its day page: a day cell opens it, as it does today.

**C2. Saved filters and presets (server, per login).**
- **In the address.** Every filter on Trades, Analytics, Watchlist and
  Calendar already lives in the query string or moves there, so reloads and
  shared links keep it.
- **Last used.** Each page's last-used query is saved per login and
  restored when the page opens with no query string. An explicit query
  string always wins. It is **not** saved on every filter change: it's
  written at most once per 2 s (trailing debounce), and on page leave or
  `visibilitychange → hidden`. The admin runs one worker with 16 threads
  (`deploy/gunicorn.conf.py:20-24`), and v206 showed what chatty polling
  does to it.
- **Named presets** per page: save current, rename, delete, set as default.
  A "Presets" field leads the filter bar (an `sb-select` with a "Save
  current…" item that opens a small name dialog). The dialog uses the
  `confirm-dialog` focus pattern: focus moves to the name input, Esc
  cancels, focus returns to the select.
- **Storage: no new table (staff-engineer review).** Both live in the
  existing per-owner store `ui_preferences`
  (`swingbot/core/db/repositories/preferences.py`), under one key per
  owner row:

  ```
  filter_presets: {<page>: {last_used: {...},
                            presets: [{name, query, is_default}]}}
  ```

  That means no Alembic revision and no second per-user UI store. Last-used
  is its own field, so it can't collide with a preset name and doesn't
  count toward the cap.
- **The owner key.**
  - The admin, whether a session login or a Basic-auth call with no
    principal (`auth.py:50-58`), writes to the existing `"admin"` owner row
    (`preferences.py:13`). Renaming `ADMIN_USERNAME` in `.env` therefore
    orphans nothing.
  - A viewer writes to `viewer:<user_id>`. Deleting a viewer from
    `admin_users` deletes that owner row in the same transaction (the users
    delete path, with a test).
  - The admin's existing column-picker preferences sit in the same row,
    beside the new key. Writes are read-modify-write of the
    `filter_presets` key only, under a row lock (`SELECT … FOR UPDATE`), so
    a preset save never clobbers the column prefs or a concurrent save.
- **Endpoints.** `GET /api/v1/filter-presets?page=`,
  `PUT /api/v1/filter-presets/<page>/last-used`,
  `POST /api/v1/filter-presets/<page>`, and
  `PATCH/DELETE /api/v1/filter-presets/<page>/<name>`. The owner always
  comes from the principal, never from the request. They sit outside
  `/api/v1/system`, so they aren't admin-only.
- **Validation.** `page` must be one of the four. `query` is a flat
  string→string map of at most 40 keys, each value at most 200 characters,
  and only known keys for that page are kept (the frontend sends its list).
  `name` is 1–60 characters. Each owner holds at most 50 presets per page.
  A duplicate name returns 409.
- **Access: the first viewer write (staff-engineer review).** v207 defines a
  viewer as read-only (`principals.py:4`), and `_viewer_may` refuses every
  non-GET (`access.py:47-50`). This spec amends that contract by exactly
  one path:
  - a new `VIEWER_WRITE_PREFIXES = ("/api/v1/filter-presets",)` in
    `access.py`, matched on segment boundaries like
    `ADMIN_ONLY_PREFIXES`;
  - a row in `tests/admin/access_expectations.py` for every new Flask rule,
    so `test_access_contract.py` stays the authority.

  Everything else stays default-deny.
- **Failures.** If a preset save fails, the page keeps working with its
  current filters and shows an inline error. If the last-used restore
  fails, the page opens unfiltered.

**C3. The most important columns first on tablet and phone.**
- Every Trades column gets an `inlineFrom` (the `ui/priority.ts` model from
  v95). At 820: ticker, status, P&L, R and plan are inline. Origin,
  strategy, horizon, confidence, badge, note and opened are demoted.
  Their `DemotionTarget` is **the trade drawer** that v240 plan 5 makes
  the narrow-width tap destination. Plan C runs after v240 plan 5, so one
  tap does one thing (open the drawer), with no expand-then-drawer double
  step. If the order ever slips, C3 waits, never ships a temporary
  expanded-row target.
- At 390 the card shows the same order.
- The column picker still overrides: a column the partner turns on shows
  inline at any width, and the table scrolls sideways with the B4 shadow.
- The Dashboard open-positions table uses the same priorities.

**C4. Undo, loading placeholders, flashes, one stamp.**
- **Undo toast** (`sb-toast` service, new). Reversible actions run at once
  and show "Removed MRVL · Undo" for 6 seconds: watchlist remove, preset
  delete. Undo calls the reverse API (re-add / re-create). The toast is
  announced through an `aria-live="polite"` region.
  - The timer pauses while the toast is hovered or holds focus (WCAG
    2.2.1).
  - Below 1024px the toast sits above the bottom tab bar (offset by the bar
    height plus 8px), and above the on-screen keyboard when one is open
    (`visualViewport`). Destructive trade
  actions (clear, close, killswitch) keep their confirm dialogs and never
  use undo.
- **Loading placeholders.** Stat tiles, tables (5 placeholder rows) and
  charts show a neutral outline in their final size while their first load
  is pending, instead of an empty space and a spinner, so nothing jumps
  when data arrives. Later refreshes keep the old data on screen. If the
  first load fails, the placeholder is replaced by the existing
  `panel-error` (what failed plus Retry). A placeholder never stays on
  screen indefinitely.
- **Flash.** `[sbFlash]` (exists, `ui/flash.ts`) is applied to every live
  price and P&L cell on Dashboard, Trades and Watchlist: a 600ms tint by
  sign when the value changes. It stays scoped to the cell, as v168 §4
  requires, and is off when the device asks for reduced motion.
- **One "Updated" stamp per page.** One `sb-freshness` in the page header
  replaces the scattered per-card "2 min ago" labels (at 1440 the Dashboard
  shows five).
  - **The stamp shows the oldest source's age** (prices, scan, FX, market
    movers), not the page-load time. A fresh page can never hide a lagging
    feed (financial-advisor review).
  - It turns amber when that oldest age passes `STALE_AFTER_SEC`.
  - Hover or tap opens a list of each source and its age, so the stale
    one is named.
  - No card keeps a stamp of its own.

## Error, empty and edge states

- Recent activity: a closed row with no R reads "Closed" (§A1).
- `sb-field` without a label: the label line still takes its height but
  holds no text, and the control keeps its own accessible name.
- `sb-time-series` with 0 points shows the card's existing empty state;
  with 1 point it draws a marker with no line.
- Charts read their theme colours from the tokens once the view has
  loaded. A missing token falls back to the Navy value and logs once.
- Page-actions menu with no items is not rendered.
- KPI fit: a value too long even at the smallest step (`--text-body`)
  wraps whole onto a second line. Never "…", never a lost sign or unit
  (§B3).
- Presets: a duplicate name is a 409 with "A preset with that name exists".
  A saved preset whose query contains a key that's no longer known has that
  key dropped silently on apply.
- Drill-down with an empty slice: Trades shows its empty state with the
  slice chip, so the partner can clear it.
- Undo after the 6s window does nothing (the toast is gone). If undo fails,
  an inline error toast appears with no retry loop.

## Three devices

Every plan checks its screens at 390, 820 and 1440 with Playwright
(`ui-design.md`). It logs in with `.env`'s `ADMIN_USERNAME` /
`ADMIN_PASSWORD` through `POST /api/v1/session`, never printed. Each
finding above names the width it was seen at, and its fix is checked at
all three. Touch targets stay at least 44px below 1024px: the "⋯" menus,
segmented options, preset select, toast Undo and the calendar cells. Each
plan's closing task also runs `node frontend/scripts/layout-audit.mjs` at
the three widths (overflow, target size, text size). Every new hint and
tooltip has a tap path. Nothing is hover-only (§B3, §B4, §B6, §C1).

## Testing

Every plan updates the existing tests it affects and adds tests for what's
new, edge and empty cases included, frontend and backend alike:

- **A:** `activity.spec.ts`; `field.spec.ts`; a bottom-edge alignment spec
  per consumer bar; `chart-theme.spec.ts` (formats, token read, theme
  switch); `time-series.spec.ts` (kinds, resize, destroy, 0/1 point);
  R-distribution bucket edges; the `workspace-consistency.spec.ts` gate
  extended so a control in `sb-control-bar` / `sb-filter-bar` that sits
  outside an `sb-field` fails.
- **B:** a spec per component touched (`page-actions`, `stat-tile` fit,
  status badge, data-table scroll shadow, calendar today/outside/weekend,
  watchlist truncation, heat bar), plus a header-overlap test at 390
  (bounding boxes don't intersect).
- **C:** backend tests for the preset endpoints:
  - CRUD, owner scoping (a viewer can't reach the admin's or another
    viewer's presets), Basic-auth admin mapping to `"admin"`;
  - limits, the 409, one default per page;
  - the column prefs untouched by a preset write;
  - the viewer-delete cleanup;
  - `access_expectations.py` rows;
  - the `rBucket` trades filter. Frontend specs for preset UI, query restore precedence,
  drill-down parameters and chips, `inlineFrom` per column at the three
  widths, toast with undo and expiry, placeholders, flash under reduced
  motion, single freshness stamp.

No plan runs the full suite. CI does (CLAUDE.md).

## Out of scope

- Calendar as its own page, the 64px icon rail and phone tab-bar editing
  (v240 plan 3).
- Bottom-sheet drawers and table tap behaviour (v240 plans 4–5). Plan B
  reuses the sheet once it exists.
- Discord chart PNGs (`chart_style.py`).
- A light theme.
- Sharing presets between logins.

## What follows

Five plans, numbered v246 like this spec, each at most 20 tasks. They are
split up front (staff-engineer review), never compressed:

1. **Plan A — requests**: Recent activity R, `sb-field` + bar alignment +
   date range + segmented sweep on the five named consumers, the gate
   allowlist, chart theme, `sb-time-series`, Analytics equity/drawdown
   move, Dashboard candle fixes, SVG token sweep, R-distribution edges.
2. **Plan B1 — audit fixes, part 1**: B1–B5 (header, page actions, KPI
   fit, tables, Calendar).
3. **Plan B2 — audit fixes, part 2**: B6–B10 (Watchlist, Risk, Analytics,
   Dashboard, the `sb-field` sweep, which empties A's allowlist).
4. **Plan C1 — interactions backend**: preset endpoints on
   `ui_preferences`, owner keying, viewer-delete cleanup, the
   `VIEWER_WRITE_PREFIXES` access change, the `rBucket` trades filter.
5. **Plan C2 — interactions frontend**: C1 tooltips/drill-down, C2 UI and
   address/restore, C3 priority columns, C4 toast/placeholders/flash/
   stamp. If C2 measures over 20 tasks at writing time, it splits again
   (C2a: C1 + C2 UI; C2b: C3 + C4).

**Order:** v240 plan 3 → v246 A → v240 plan 4 → v246 B1 → v246 B2 →
v240 plan 5 → v246 C1 → v246 C2. The same interleave is recorded in
v240's "What follows", so the two specs never disagree about what's next.
Why:
- A edits the Trades and Calendar control bars, which v240 plan 3 moves.
- B's tables and the page-actions sheet build on v240 plan 4's
  `sb-data-table` tap rule and bottom sheet.
- C's priority columns change the same `sb-data-table` consumers v240
  plan 5 moves into drawers.

None of these run in parallel. Each pair edits shared shell or table files.

## Panel review

Run 2026-11-23 on ee049953, serially: ux-designer (sonnet), staff-engineer
(opus), financial-advisor (sonnet).

**BLOCKING**
- ux-designer: hover-only reveals (KPI "…" values, two-line titles, watchlist names, status and count tooltips) are unreadable on touch -- applied: no value is ever cut with "…"; coarse-pointer titles and names wrap; status text repeated in the drawer; calendar count reads in words on the day page (§B3, §B4, §B5, §B6, Three devices).
- financial-advisor: the bare R in Recent activity doesn't say its cost basis -- applied: stated as pre-tax, before modelled frictions, in the panel hint (§A1).

**ADVISORY**
- ux-designer: tap both pins the tooltip and navigates -- applied: tap pins, "View N trades" link navigates (§C1).
- ux-designer: chart drill-down is pointer-only -- applied: focusable host, arrow-key stepping, aria-live readout, Enter follows (§C1).
- ux-designer: "⋯" menu and preset dialog keyboard behaviour unstated -- applied (§B2, §C2).
- ux-designer: `--control-h` is 28px base / 44px below 1024; alignment test should run at both -- applied (§A2).
- ux-designer: name `layout-audit.mjs` in each plan's closing task -- applied (Three devices).
- ux-designer: empty label filler leaves gaps in the phone grid; segmented groups below 640px unspecified -- applied (§A2 Phone).
- ux-designer: "22 trades" in half-width weekend columns -- applied: short form there, 64px minimum (§B5).
- ux-designer: toast position, pause and first-load failure of placeholders -- applied (§C4).
- ux-designer: expanded row vs v240 drawer tap conflict -- applied: drawer is the target; C3 waits rather than ship an interim (§C3).
- ux-designer: closed row must still announce its status -- applied: accessible name keeps "closed" (§A1).
- staff-engineer: bar seam misnamed (sb-filter-bar already flex-end; sb-toolbar and Calendar's own flex unnamed) -- applied (§A2).
- staff-engineer: consistency gate goes red at A's merge -- applied: allowlist shipped by A, emptied by B10 (§A2).
- staff-engineer: `filter_presets` table ignores schema.py conventions -- applied by removal: no new table, presets live in the existing `ui_preferences` store (§C2).
- staff-engineer: last-used row collides with names and the cap -- applied: its own field (§C2).
- staff-engineer: Basic-auth admin has no principal; env username rename and viewer delete orphan rows -- applied: `"admin"` owner for both admin paths, `viewer:<user_id>` deleted with the user (§C2).
- staff-engineer: first viewer write needs an explicit rule and contract rows -- applied: `VIEWER_WRITE_PREFIXES` + `access_expectations.py` rows, v207 amended by one path (§C2).
- staff-engineer: last-used saved on every change starves the single worker -- applied: 2 s debounce plus save on leave/hidden (§C2).
- staff-engineer: `rBucket` needs a server filter -- applied: plan C1 backend work; closedOn/closedMonth reuse `closed_from`/`closed_to` (§C1).
- staff-engineer: plans B and C exceed 20 tasks -- applied: split into B1/B2 and C1/C2 now (What follows).
- staff-engineer: interleave contradicts v240's "strictly in this order" -- applied: recorded in v240's What follows in the same commit.
- staff-engineer: lightweight-charts has no shared time scale; teardown unstated -- applied: visible-range subscriptions with guard, all released in DestroyRef (§A3).
- financial-advisor: win-rate rename should name the cause and keep ExpR leading -- applied (§B8).
- financial-advisor: KPI fit could clip a sign or unit -- applied: sign and unit never dropped, wrap instead of "…" (§B3).
- financial-advisor: keep Close all on the Dashboard's open-risk tile -- rejected: the partner chose the "⋯" menu for it (D3); applied the other half, the confirm copy states the positions and € at risk being closed (§B2).
- financial-advisor: drawdown only in R/% -- applied: max drawdown in € and longest losing streak in the card header (§A3).
- financial-advisor: one page stamp can hide a stale feed -- applied: the stamp shows the oldest source's age and lists each source (§C4).
- financial-advisor: drill-down slice shown without N -- applied: chip carries N and the thin-sample note (§C1).
- financial-advisor: coloured tier badge could make WEAK read as a pass -- applied: only VALIDATED green, WEAK muted amber, never loss red (§B4).
