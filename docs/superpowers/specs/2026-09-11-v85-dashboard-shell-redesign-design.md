# v85 — Dashboard, shell and workspace redesign

Bump: ui minor per wave (three) · bot patch in waves 2 and 3 — numbers resolve
at close-out from the then-current `VERSION.json`.
Edge: none (integrity)

## What this is

A visual and structural redesign of the whole admin SPA: the shared chrome
(top bar, left nav), the Dashboard, and the seven remaining workspaces —
Trades, Watchlist, Risk, Analytics, Calendar, System, Versions — each
recomposed against a supplied mockup rather than merely restyled.

Mockups: `images/Mock up.png`, `images/Mock up full view.png` (shell and
Dashboard), `images/Dashboard Trades Watchlist Risk.png` (sheet 1) and
`images/Analytics Versions Calendar System.png` (sheet 2).

`Bump: ui minor` per wave follows the `ui 1.2.0` precedent — "the SPA refresh
(plan v21): every workspace rebuilt" — which is what this is. `bot patch`: the
bot gains metrics, endpoints and a boot-time deploy marker; how it trades is
untouched.

`Edge: none (integrity)` — this buys no expectancy, no harvest, no volume. It
is operator tooling. Stated rather than dressed up.

## What the mockups are not

The mockups are branded for a fictional institutional desk with a $24M capital
book: cash balance, allocation across equities / fixed income / alternatives,
an Equities / Options / Futures / FX tab row, and per-release uptime and
latency telemetry. This bot holds no capital, trades one asset class, and
records paper swings only.

The rule this spec applies throughout, decided in the brainstorm: **keep the
mockup's geometry, density and rhythm; fill each slot with an instrument this
bot genuinely measures, and where the instrument is worth having but does not
exist yet, build the backend for it.** A slot with no honest occupant is
dropped and its neighbours reflow. Nothing renders against a placeholder.

## Findings established during the brainstorm

Verified in the code, not assumed. They constrain the design.

1. **The theme already is the mockups' palette.** `frontend/src/styles/tokens.css`
   defines `--bg: #0c0f16`, `--surface: #131722`, `--pos: #17c98e`,
   `--neg: #ff5470`, `--accent: #5593ff`. No shared-token retune is needed —
   only additions (a hero-size type token; the scale currently tops out at
   `--text-metric: 28px` and the mockups' hero figure is roughly double).
2. **Expectancy already is mean realised R.** `expectancy_r` in
   `swingbot/core/analytics/metrics.py:220` is "mean `r_multiple()` over closed
   trades". An "Avg realised R" metric would print the same number twice under
   two labels. Resolved in D9.
3. **`clear_open()` deletes, it does not close.**
   `swingbot/core/tracking/performance.py:1267` drops every `status='open'`
   record and saves to disk immediately. It realises nothing. The "close all"
   action in D13 must therefore be built, never wired to this.
4. **There is no create-trade endpoint.** The bot authors plans; the admin
   never does. The mockups' "+ New Trade" button has nothing behind it.
5. **`TradeGroup` is used only by the Dashboard** (`dashboard.ts`, its own
   spec, and `trades.store.spec.ts`). Rebuilding the positions table as tabs
   does not reach the Trades workspace.
6. **Row actions are already backed — except delete.** `closeTrade`,
   `cancelTrade`, `deleteTrade`, `setTradeNote` all exist in
   `api-client.ts:121-149`. But `delete_trade` in `admin/api_v1/trade_commands.py`
   **refuses plan-backed rows** with a 422 ("Plans cannot be deleted; cancel a
   PENDING plan or close an active one") — deletion is for legacy trade records
   only, and essentially every Dashboard row is plan-backed. Resolved in D13.
7. **Portfolio history is 30 daily points, not intraday.** `equity_30d` on the
   dashboard payload. The mockups' intraday curve has no backing series.
8. **Every manual state change must notify the bot.** `close_trade` and
   `cancel_trade` each append to `data/manual_close_notify.json` via
   `_queue_notify`. The bot is a separate process and that file is the only way
   it learns a human closed something; without it the Discord trade-history
   channel goes quiet. Any bulk action inherits this obligation per position.
9. **Closing needs no new pricing logic.** A plan-backed close is
   `record_transition(plan, PlanStatus.CLOSED, reason="manual", at=…)` plus
   `TradeLog.close_trade_manual()` on the linked legacy row. The current price
   is resolved inside `close_trade_manual`.
10. **Frontend tests are vitest** via `@angular/build:unit-test`. One spec runs
    as `npx ng test --include <path>` from `frontend/` — verified, ~55s, exit 0.
    `scripts/dev/testrun.py` is pytest only and does not run them.
11. **The chart primitives the mockups need mostly exist, hand-rolled.**
    `ui/sparkline.ts`, `ui/donut.ts`, `ui/line-chart.ts`, `ui/histogram.ts`,
    `ui/scatter.ts`, `ui/magnitude.ts`, and the whole `ui/chart/` package. Only
    a radial gauge, a correlation heatmap and a release timeline are genuinely
    new. The zero-third-party constraint therefore costs three components, not
    a charting library.
12. **Watchlist serves no market data at all.** `GET /watchlist/tickers`
    returns symbol, company name, open/closed trade counts and next earnings —
    no price, no changes, no series, no score. Sheet 1's watchlist row is
    almost entirely new backend.
13. **Risk already computes the mockup's two hardest panels in spirit.**
    `GET /risk` returns `heat.open_pct`, `heat.cap_pct`, an intentionally
    **unclamped** `utilisation_pct`, `sector_heat`, `clusters`, `throttle`,
    `killswitch` and `scan_health`. Sheet 1's gauge and Risk Budget are
    compositions of numbers that already exist.
14. **Analytics is five tabs and ~25 panels**, far more than sheet 2's single
    page. The Performance tab alone holds Record, Overall, Risk-adjusted,
    Streaks, three distributions, five by-dimension breakdowns, Journal and
    by-confidence.
15. **System's settings already have a preview step.**
    `POST /system/settings/preview` exists, so sheet 2's "3 unsaved changes →
    Review Changes" footer has a real backing flow rather than needing one.
16. **`images/logo.png` is a photorealistic brushed-metal serif monogram on a
    white ground.** It cannot take the accent colour, will not read at 24px on
    `--bg`, and has no collapsed-rail form. Resolved in D3.

## Decisions

Decision ids are stable, not sequential. D1–D21 were assigned before the
seven-workspace mockups arrived and keep their numbers wherever they survive
unchanged; D22 onward are this revision's, and the sections below group them by
surface rather than by id. Where a later decision supersedes an earlier one the
earlier one says so in place.

### The shell

**D1 — Nav keeps the real routes and the real grouping, and gains two.** The
existing entries stay under the same MONITOR / REVIEW / SYSTEM headers,
restyled. Sheet 1's second group adds **Research** and **Reports**; both are
built as honest stubs (D24). Sheet 2's flat, label-free rail is *not* adopted —
with ten destinations the group headers are what stop the rail reading as an
undifferentiated list. The `ui`/`bot`/updated version block stays exactly where
it is at the foot of the rail, including its rail-collapsed behaviour.

**D2 — The top bar becomes one row,** wordmark → ticker → status cluster, and
takes **sheet 2's treatment** of the tape: five named index quotes with value
and signed change, followed by a "Live" dot and a running clock, rather than
sheet 1's single "MARKETS LIVE" pill. The dot means one thing only — the event
stream is connected (D30).

**D3 — Branding is adopted, and the mark is redrawn.** The product takes the
mockups' two-tone wordmark and the "Trade smarter. Build further." rail footer
tagline. The monogram is **authored as an inline SVG** on the existing 16×16
icon grid at 1.5 stroke width, not shipped as `images/logo.png` (finding 16).
Wordmark, tagline and monogram all come from tokens and adapt to the collapsed
rail. The PWA manifest and document titles follow the same name.

**D4 — The page title moves into the top bar,** driven by route data, with a
subtitle beneath it. No workspace renders its own `<h1>`.

**D5 — A live clock and date join the status cluster.** One timer at shell
level, `OnPush`, writing to a signal — never a per-second re-render of the app.

**D6 — The text-zoom control moves into the profile menu,** beside sign-out.

**D7 — No search box in the top bar, no notification bell.** Settings search is
a System-local control (D27), not global chrome.

### Cross-cutting primitives

**D22 — One shared control bar.** A single `sb-control-bar` sits directly
beneath the top bar on every workspace: filters and chips left, scope controls
right, active-count and Clear built in. Each page fills its slots. The mockups
place per-page controls differently on every sheet; nine independently placed
control clusters would drift apart the first time one was edited alone, and
would not survive 390px. One component, one accessible implementation, one
place the eye learns to look.

**D23 — Sample size is part of every derived metric.** A new `sb-stat-tile`
renders value, label and **N** together. Any figure computed from fewer than a
configured minimum — a constant of 30 in wave 1, becoming a System setting in
wave 3 (D27), so the primitive ships before the control that tunes it — renders de-emphasised with
a tooltip naming how many more closed trades it needs. Nothing is hidden — a
thin number is still shown, visibly untrustworthy. This is a single primitive
precisely so the rule cannot drift between Analytics, Risk and Calendar.

**D24 — Research and Reports are honest stubs.** Each renders a panel naming
what is planned for it and linking to the nearest surface that serves the need
today — Research → Ticker detail, Reports → Analytics and the CSV export.
Neither advertises a capability that does not exist, and neither is a blank
route.

**D25 — Three new chart primitives, everything else composed.** `sb-gauge`
(radial, unclamped past 100), `sb-matrix` (correlation heatmap with outlined
cluster blocks), `sb-timeline` (release rail). All other mockup charts are
compositions of the existing primitives from finding 11.

**D26 — New state goes through existing stores.** Watchlist tags ride inside
the existing watchlist structure, per-page control-bar preferences ride in
`PreferencesStore`, deploy markers append to the existing events path. **No new
top-level JSON file**, so v67's JSON→Postgres migration inventory does not grow
and nothing written here needs migrating twice.

**D30 — Freshness is per panel, never global.** The header's Live dot reports
stream connectivity only. Each panel carries its own "as of HH:MM:SS" derived
from its data's own timestamp, greys past a per-panel staleness threshold, and
on a failed refetch keeps the previous figures on screen with a stale marker.
A single page-level clock would be wrong the moment a quote is two seconds old
while a risk metric is fifteen minutes old.

### Dashboard

**D8 — Portfolio Value is simplified to figure + change + sparkline.**

**D9 — Trading Performance carries eight metrics,** the eighth being a **payoff
ratio** (avg win R ÷ avg loss R), null rather than 0 when there are no losers.

**D10 — The Today / All-days scope control moves into the Trading Performance
panel** — and, with D22, into that panel's slot of the shared control bar.

**D11 — The positions section becomes one tabbed table.** Five tabs, lazily
fetched.

**D12 — The table keeps all its machinery.** Column picker, compact/full
density, reorder, and their preference reconciliation.

**D13 — Row actions and one bulk action.** Close / Cancel / Note per row;
"Close all open" as the single bulk action, built fresh (finding 3), notifying
per position (finding 8), behind confirm copy that names exactly what happens.

**D14 — No panel overflow menu.**

**D15 — Recent Activity is derived, not logged.**

**D16 — Two backend additions:** payoff ratio on the dashboard payload, and a
`TradeLog` bulk close with its endpoint.

**D17 — The bottom row is Recent Activity + Market Movers + Watchlist.**

**D18 — Explanatory copy moves behind affordances, and none of it is lost.**

**D31 — The Dashboard part is diffed against sheet 1 and amended, not
rewritten.** Sheet 1's Dashboard shows a KPI row of four, an equity curve with
a 1D/1W/1M/YTD/1Y/ALL range toggle, an allocation donut and an Active Trades
table. Part 3 of the plan is re-read beside it and only genuine divergences are
changed. Expected amendments: the equity-curve range toggle (constrained by
finding 7 — ranges shorter than the 30 daily points are omitted rather than
faked), and the KPI tile set. The allocation donut has no honest occupant on a
single-asset-class paper book; its slot is taken by exposure by horizon.

### Trades

**D32 — A chip lane, a date range, and a count footer.** The mockup's asset
classes have no counterpart, so the always-visible chip lane is
*All · Open · Closed · Pending · Win · Loss · Long · Short* — the filters
actually reached for, promoted out of the collapsible filter bar, which keeps
strategy, horizon and symbol. A real date-range picker is added, backed by new
`from`/`to` query parameters on `GET /trades`. The footer becomes
"Showing X–Y of N". All of it stays URL-driven: a filtered view must survive a
reload and be pasteable.

### Watchlist

**D33 — The full mockup row, served from cached bars in one batch.** Price,
1D%, 1W%, 1M% and a 30-day sparkline come from the existing daily OHLCV cache
in a single server-side batch per request — no per-row provider call, no new
external dependency, and the sparkline is free because the bars are already
there. Price is the last close, plus an intraday quote only while the market is
open. **Each row shows the date of the bar it was computed from**, so a stale
cache is visible rather than silent.

**D34 — "Signal" is the scanner's own live verdict,** not a price derivative:
the best current setup for that symbol with its confluence/quality score and
horizon, or an explicit "No setup" when the scanner sees nothing. This is the
one column on the page that is the bot's opinion rather than a restatement of
the sparkline beside it. Relative strength from `data/universe/rs_cache.json`
is deliberately *not* used for this column.

**D35 — Groups are tags, and they are view-only.** Symbols carry user-defined
tags stored inside the existing watchlist structure (D26); the chip row filters
the view by tag, and "+" creates one. **The scanner continues to scan every
symbol** — a tag never gates what the bot trades, which keeps this inside a UI
release and keeps the no-trading-change rule true.

### Risk

**D36 — The gauge is heat utilisation; the budget is the heat cap.** The
`sb-gauge` needle is `utilisation_pct` (finding 13), unclamped, so 130% reads
truthfully as past the redline rather than pinned at full. The Risk Budget
panel is cap · used · remaining, in R and in account currency. Both are
compositions of numbers that exist today, not a new composite score invented
for a dial — a blended index would hide which input moved.

**D37 — The full institutional metric set is computed for real.** VaR 95%,
expected shortfall, annualised volatility, beta vs SPY, Sharpe and max
drawdown, over the **open paper book's notional weights** against cached daily
bars; Sharpe is of the closed-trade R series. Every formula is stated in the
implementation plan and unit-tested against hand-worked fixtures. Each tile
carries its N and obeys D23 — on a book of ten to twenty paper swings these
numbers are thin, and the tile must say so rather than imply an institutional
sample.

**D38 — Correlation matrix and cluster list both stay, side by side.** The new
`sb-matrix` shows real pairwise correlation across open positions with the
bot's existing cluster groupings outlined on it; the existing cluster panel
continues beneath, unchanged. The grouping is what actually throttles position
size, so it keeps its own readable list rather than becoming a tooltip.
Killswitch and scan health are untouched.

### Analytics

**D39 — Sheet 2 replaces the Performance tab; the other four tabs are
restyled.** The Performance tab becomes the mockup composition: a six-tile KPI
row — **Total R · R per month · Sharpe of the R distribution · Max drawdown
(R) · Win rate · Profit factor** — an equity curve with an Equity | Drawdown
toggle, a win/loss donut with average win and loss R, a strategy table, and a
performance-by-horizon bar list.

**D40 — Strategy and horizon panels toggle between ExpR and total R.** A single
segmented control drives both. ExpR answers "which is better per shot"; total R
answers "which made the most", and rewards whichever strategy simply fired most
often — the trap ExpR exists to avoid. Both are worth seeing, neither is worth
conflating, so the control is explicit and its state is a control-bar
preference. The strategy table carries each strategy's VALIDATED / WEAK badge
as a rail beside its numbers, so the registry's own verdict sits next to the
figures that produced it.

**D41 — Displaced panels continue below in a collapsible Breakdowns band.**
Return distribution, both R-multiple distributions, by holding period, by
month, by planned R:R, by direction, by day of week, Streaks, Journal and
by-confidence all remain on the Performance tab, restyled, beneath the mockup
composition. Nothing is lost and nothing has to be relearned; the first screen
finally answers "how are we doing" without scrolling.

### Calendar

**D42 — Two panes, plus a cell-metric selector.** Grid left, a persistent day
detail pane right: total R and currency, trade count, winners, losers, average
trade, worst drawdown, and top contributors and detractors by symbol. A month
summary strip sits beneath the grid — month total, winning-day count and
percentage, average day, best day, worst day. A control-bar selector switches
what the cells encode: R · currency · trade count · win rate. The existing
by-weekday panel stays below. `GET /calendar/pnl/day` is extended to serve the
detail pane's contributors and detractors.

### System

**D27 — The tab bar stays; the Settings tab gains a sub-nav.** System keeps
Settings · Logs · Scan as tabs — a live log tail and a scan controller are
operations, not configuration, and putting them in a list of settings
categories would misfile them. Inside Settings, sheet 2's left category rail
replaces the current flat grouping, with a **settings search** above it and a
sticky "N unsaved changes · Discard Changes · Review Changes" footer wired to
the existing `POST /system/settings/preview` (finding 15). The minimum-N
threshold from D23 is a setting in this tab.

### Versions

**D28 — Each release carries both provenance and telemetry.** Provenance: the
commit range, the originating spec and plan, and the changelog lines.
Telemetry: uptime, error rate and median scan duration for that release's
window.

**D29 — Telemetry comes from a boot-time deploy marker in both containers.**
The bot and admin processes each append a marker (version, timestamp, git sha)
to the existing events path on startup; the API derives release windows from
consecutive markers and attributes log events and scan timings to them.
Existing releases are backfilled from git tags and `VERSION.json` history so
the timeline is populated on day one. The marker is append-only and its failure
degrades to "window unknown", never to a crash. **Nothing in the scan,
strategy, sizing or exit path is touched** — this writes one line at boot.

### Process

**D19 — Every workspace is redesigned in this plan,** not merely restyled. The
earlier "presentation only, no binding changes" framing is superseded: these
seven pages are recomposed against sheets 1 and 2, with the backend work each
needs.

**D20 — chrome-devtools MCP is fixed first.** It and playwright both timed out
on connect; visual verification of every task after it depends on the fix.

**D21 — One plan, three waves, three releases.** The work is well past a single
release, and a long-lived branch is the wrong shape for a repo where concurrent
sessions share the tree.

| Wave | Contents | Bump |
|---|---|---|
| 1 | MCP fix · tokens and icons · brand mark · shell (D1–D7, D22, D23, D25, D30) · the two Dashboard backend additions · Dashboard (D8–D18, D31) · tabbed positions table | ui minor |
| 2 | Trades (D32) · Watchlist (D33–D35) · Risk (D36–D38), with their endpoints | ui minor · bot patch |
| 3 | Analytics (D39–D41) · Calendar (D42) · System (D27) · Versions (D28, D29) · Research and Reports stubs (D24) · `/ui` gallery · full suite | ui minor · bot patch |

Each wave ends with its own full-suite run and its own close-out, so a
regression is bisectable to a handful of files rather than to forty.

## Out of scope

Command palette · notification centre · the mockups' Light and Luxury theme
variants · the alternate "Analytics Focus" and "Trades Focus" desktop layouts ·
asset allocation across asset classes · cash balance · options, futures and FX ·
intraday equity series · groups that gate what the scanner scans · a
create-trade endpoint · **any change to how the bot trades**.

## Responsive behaviour

**Every page stays usable at 390px.** The existing `ViewportService`
breakpoints (`isNarrow`, `isPhone`) and the rail/overlay sidebar behaviour are
reused unchanged — no new breakpoint vocabulary. Dense instruments degrade
rather than disappear:

- The correlation matrix and the watchlist table scroll horizontally inside
  their own `overflow-x` container; the page body never scrolls sideways.
- The Calendar's day pane moves below the grid.
- KPI rows reflow via `repeat(auto-fit, minmax(140px, 1fr))`, never a
  breakpoint list.
- The shared control bar wraps to a second line and its scope controls move
  under its filters.
- The merged top bar sheds, in order: subtitle, clock, then the tape becomes
  horizontally scrollable, then the title truncates.

A panel that vanishes at narrow width without saying so is the failure this
rule exists to prevent. Nothing is hidden on a phone.

The killswitch banner stays shell-level and unmissable: when engaged it renders
as a full-width alert strip directly beneath the top bar rather than competing
for space inside it.

## Loading, empty, error and honesty states

`sb-async` already owns loading skeletons, measured-zero empty states,
staleness badges and retry; every new panel adopts it rather than inventing a
second vocabulary. On top of that, four rules hold across all ten workspaces
and are enforced by an extended `workspace-consistency.spec.ts`:

1. **Sample size is adjacent to every derived metric**, and anything under the
   configured minimum renders de-emphasised with how many more trades it needs
   (D23).
2. **Freshness is per panel** (D30). One panel's failed fetch never blanks
   another's numbers, and a refetch failure keeps the last good figures with a
   stale marker.
3. **`null` is never `0`.** "Measured zero" and "no data yet" stay distinct —
   including the payoff ratio, which is null when there are no losers to divide
   by, exactly as `profit_factor` already is.
4. **Colour is never the only cue.** Every status signalled by colour carries a
   second cue: weight, a rail, or an icon.

## Testing

- **Frontend units:** the shell (title/subtitle from route data, merged tape,
  clock, zoom relocation); each new primitive (`sb-control-bar`, `sb-stat-tile`
  and its threshold behaviour, `sb-gauge` past 100%, `sb-matrix` with and
  without clusters, `sb-timeline`, `sb-freshness` staleness transitions); the
  tabbed positions table; each new panel component; the watchlist row's stale
  bar-date rendering; the Analytics ExpR ⇄ total-R toggle; the Calendar metric
  selector and day-pane derivation; the System settings search and
  unsaved-changes footer.
- **Backend units:** payoff ratio (winners only, losers only, mixed, no losers
  → null, no closed trades → null); bulk close (ACTIVE and PARTIAL closed,
  PENDING untouched, counts correct, empty book a no-op); the watchlist batch
  quote builder (missing bars, short history, stale cache); each risk metric
  against hand-worked fixtures, including the degenerate cases (one position,
  zero variance, missing benchmark bars); calendar day aggregation
  (contributors, detractors, ties); trades `from`/`to` filtering (inclusive
  bounds, invalid range, open-ended); deploy-marker parsing (missing marker,
  out-of-order markers, backfill from tags).
- **Visual:** chrome-devtools screenshots at each wave checkpoint, every
  workspace, at 1440px and 390px (D20).
- **Suite:** `python scripts/dev/testrun.py fast` while iterating; one full
  `testrun.py full` as each wave's own final verification task — three in the
  plan, never per task.

## Parallelisation

**Wave 1.** Sequential, in order: the MCP fix (D20); token and icon additions
plus the brand mark (one file each, consumed by everything after); the shell
itself, whose title/subtitle mechanism is a contract every workspace consumes;
then the shared primitives (D22, D23, D25, D30) as **Group P, parallel** — one
new file each, no shared file. Then **Group A (parallel)**: the two Dashboard
backend additions, disjoint files, no shared symbol. Then **Group B
(parallel)**: the new Dashboard panel components, one file each. Then
sequential: Dashboard page assembly, then the tabbed positions table and its
row actions.

**Wave 2.** **Group W2-BE (parallel)**: the watchlist batch quote/signal
endpoint, the trades date-range parameters, and the risk metrics + correlation
endpoint — three separate API modules, no shared file. Then **Group W2-UI
(parallel)**: Trades, Watchlist, Risk — one workspace each.

**Wave 3.** **Group W3-BE (parallel)**: the analytics equity-curve and
strategy/horizon endpoints, the calendar day extension, and the versions
provenance + telemetry endpoint with its deploy-marker writers. Then **Group
W3-UI (parallel)**: Analytics, Calendar, System, Versions, and the two stubs —
one workspace each. Then sequential: the `/ui` gallery additions, then
full-suite verification alone.

Concurrent sessions share this working tree, so the lettered groups are the
only places more than one agent may work at once, and only within a group.

## Risks

1. **The merged top bar and the shared control bar are on every page.** The two
   most likely regression sources in the plan, and the reason the primitives
   land in wave 1 with their own specs rather than emerging per page.
2. **The institutional risk metrics are thin by construction.** Ten to twenty
   open paper positions is not a sample that supports VaR or beta with
   confidence. D23's N-adjacent treatment is the mitigation, and it is not
   optional decoration — without it this page invites exactly the over-reading
   the repo's backtest methodology exists to prevent.
3. **The watchlist quote batch is the one new per-request cost.** Served from
   cache by design (D33), but a large watchlist against a cold cache is a slow
   first paint. The endpoint must degrade per symbol, never fail wholesale.
4. **The tabbed table is a rewrite of working code** carrying real subtlety in
   `reconcileReorder`. Its existing specs are the safety net; they get ported,
   not dropped.
5. **Close all open/partial is irreversible** and adjacent, in meaning, to a
   delete-everything action that already exists. D13's confirm copy is not
   decoration.
6. **Deploy markers touch the bot's startup path.** Append-only and
   fail-degrading by design (D29), but it is the one place this plan writes
   code into the process that trades.
7. **Three waves means three merges into a tree other sessions share.** Each
   wave's close-out confirms no concurrent activity before merging.
8. **The clock and the tape are per-second signals in shared chrome.** Done
   carelessly they re-render the app every second.
