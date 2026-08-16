# v30 — Analytics: five tabs, new charts throughout, and the bugs found while planning them

Version: ui 1.5.1 · bot 1.1.4
Bump: `ui minor (1.5.x → 1.6.0)` — a fifth tab appears, the Performance tab's
layout changes shape, and three data views that were text lists become charts.
Someone who used Analytics yesterday has to look at it anew, which is the shape
of a minor in `working-conventions.md`. The Discord bot is untouched.

## Goal

Redesign the Analytics workspace (`frontend/src/app/workspaces/analytics/`,
1526 lines) across all four existing tabs plus a new fifth one: more charts,
clearer structure, pagination on every table that can grow, a working phone
layout, and two bugs fixed along the way that surfaced only from reading the
page closely enough to plan this.

## What's wrong today — found by reading, not assumed

**A genuine mislabeling, not a duplicate.** Two panels are both titled
"R-multiple distribution." One (`store.rHistogram()`, from
`GET /analytics/performance`'s `distributions.r_multiples`) is scoped to the
date-range control above it. The other (`store.rMultipleBins()`, computed
client-side from `GET /analytics/snapshot`'s `r_multiples`, "forwarded
verbatim") is always all-time. Both views are legitimate — recent window vs.
full history — but nothing on screen says which is which.

**The alignment bug.** `.panel-subtitle` and `.section-help` carry no
horizontal padding of their own. Inside a `[flush]="true"` panel (`Panel`
strips its body's padding so a table can run edge-to-edge) that leaves them
flush against the panel's left border, while the panel's own `<header>` keeps
its 14px padding — so a subtitle sits visibly left of the heading above it.
Hits "Strategy registry" / "out-of-sample validation status per strategy"
(Strategies tab) and "Tier calibration" / "Badge drift" (Calibration tab).

**A documented regression.** The Calibration tab's "Quality score vs outcome"
panel carries this comment: *"the Jinja chart drew an 80% line across the
deciles; this table has no chart to draw it on, so it says the target
instead."* The SPA rewrite dropped the chart and kept only the sentence.

**Three data views the store already computes and nothing renders.**
`rollingReturns` and `benchmarkSeries` (SPY's cumulative % return) are fetched
and computed in `analytics.store.ts` and never referenced in the template.
`cumulativeByStrategy` carries a full per-strategy time series but the
template only ever shows `fmtCumulative()` — the last point — whose own doc
comment says *"the full series is in the payload for whoever plots it."*

**No pagination anywhere**, on six `sb-data-table`s that can each grow
(strategy registry, breakdown, confidence, deciles, tiers, drift) plus three
hand-rolled `<table>`/`<ul>` blocks (tuning grid results, past jobs,
proposals) that have no pagination mechanism at all.

**Uneven phone support.** Every `sb-data-table` usage already gets a
built-in card layout below the `sm` breakpoint (`data-table.ts`, spec v18
Decision 9) — that part is free. The three hand-rolled tables don't: they
overflow into a `.scroller { overflow-x: auto }`, which works but isn't a
card.

## Design

### 1. Bug fixes

- `.panel-subtitle` / `.section-help`: `padding: 0 var(--space-14)` when
  inside a flush panel — a `.panel .body.flush > &` rule, or an explicit
  class if that selector proves too broad once other flush-panel content is
  checked.
- Rename the two R-multiple panels: "R-multiple distribution (selected
  range)" and "R-multiple distribution (all-time)". Both stay.

### 2. `sb-line-chart` — one new shared component

Neither existing primitive fits a multi-series time series: `Sparkline` is a
deliberately minimal 100×24 single-series spark with no axes by design
(`sparklinePath`'s own contract); `Histogram` is bars-only. New component,
`frontend/src/app/ui/line-chart.ts`:

- Input: one or more named series, each `{date: string, value: number}[]`.
- A shared x-axis (dates, ticked sensibly for the span) and an auto-scaled
  y-axis with visible labels — same auto-scale idea as `sparklinePath`, but
  drawn rather than implied.
- A legend whenever there's more than one series; none for a single series
  (the panel heading already names it) — same rule the dataviz skill's
  categorical-color guidance uses elsewhere in this app (see the Versions
  timeline's segment shading for the precedent: one hue family, no sixth hue
  invented for this).
- Hover crosshair + tooltip reading every series' value at that date.
- No entrance/transition animation on data change, matching this app's
  existing "no card-flash on refresh" rule (spec 3) — a value updates in
  place.

Built once, used three times below, and available for whatever the next
line-shaped need turns out to be.

Separately, `Histogram` gains one optional input: a `referenceLine?: number`
(0–1 fraction of the tallest bin, or a raw value — pick one during planning)
rendered as a horizontal line across the bars. This is a small, additive
change to an existing bar-list component, not a new chart type.

### 3. Performance tab — four labeled sub-sections

No new navigation (a second tab-strip inside a tab was considered and
rejected — the panels stay reachable by scrolling, just grouped). Existing
panels move under a sub-heading; nothing here changes what a panel shows,
only where it sits:

- **Snapshot** (all-time) — Record, Overall, Risk-adjusted, Streaks.
- **Distributions** — Return distribution, R-multiple distribution ×2
  (relabeled per the bug fix above), By month, By holding period.
  - *By month* becomes a bar chart on the existing `Histogram` component
    (`{label: month, count: return_pct}` — the field is generically a
    number, not literally a count; the component's `negative` predicate
    already colors P&L-shaped bars correctly).
  - *By holding period* stays a table — each bucket carries two numbers
    (count and win rate), which doesn't fit a single-value bar, and it's
    only 4–5 rows.
- **Over time** (new section, on `sb-line-chart`) — Account balance and
  Drawdown (upgraded from `Sparkline` — real axes now), with an optional SPY
  benchmark line overlaid on Account balance from `benchmarkSeries`;
  **Rolling returns** (new, from the previously-unused `rollingReturns`);
  **Cumulative return by strategy** (rebuilt as one line per strategy from
  the full series already in `cumulativeByStrategy`, replacing the
  last-point-only list).
- **By segment** — Journal, Confidence table, Breakdown table.

The date-range control's placement and scope are unchanged.

### 4. Calibration tab — the restored chart

"Quality score vs outcome" gets a bar chart above the existing table: one bar
per decile, height = realised win rate, `Histogram`'s new `referenceLine` at
80%. The table stays below it for exact numbers — the chart shows the shape
(a healthy calibration is an upward staircase), the table gives the figures.

### 5. New "Plans" tab

Backend: a new aggregation over `PlanStore().all()`, following the same
"walk every plan, said in the same shape `_plan_rows()` already established"
pattern rather than inventing a second one. Exact endpoint shape (extend
`/analytics/performance`, or add `/analytics/plans`) is a planning decision.

- **Lifecycle funnel** — Posted (all plans, ever) → Filled (reached ACTIVE)
  → Hit TP1 (reached PARTIAL) → Closed (fully resolved). Plans currently
  sitting at PENDING/ACTIVE/PARTIAL are "in flight" and reported as their
  own count, not folded into a stage they haven't finished.
- **Fill rate / time-to-fill** — over *resolved* plans only (CLOSED or
  CANCELLED; in-flight plans excluded, since including them would bias the
  rate toward "undecided"): % that ever reached ACTIVE vs. cancelled/expired
  while still PENDING, plus median time from a plan's first `status_history`
  entry to its ACTIVE transition, for the ones that filled.
- **Badge / tier distribution** — bar chart, count of plans by VALIDATED/WEAK
  badge and by A/B/C tier.

### 6. Pagination

- The six `sb-data-table` panels: wire up the `[pagination]` input the
  component already supports. Client-side (slice the already-fetched array)
  — Analytics data isn't naturally page-shaped at the API level the way
  Trades' collection endpoint is, so no backend change is needed for paging
  itself.
- **Tuning grid results**: convert the hand-rolled `<table>` to
  `sb-data-table` — the rows (param label, N, win rate, ExpR, excluded%,
  pass chip, Propose button) are genuinely tabular, so this gets pagination
  *and* the free phone-card layout in one move.
- **Past jobs**: same conversion, for consistency, despite low volume.
- **Proposals**: each is a card with its own nested parameter-diff table —
  not flat row data, so it doesn't fit `sb-data-table`. Gets its own simple
  client-side pagination over the list of cards (5–10 per page) instead.
- **The strategy/horizon heatmap** stays a matrix with horizontal scroll —
  pagination and card-layout both assume row-shaped data, which a matrix
  isn't. Accepted as-is.

## Out of scope

- Strategies and Tuning tabs get pagination and the alignment fix, but no
  new charts — nothing found there matches "data the store already has and
  nothing renders" the way Performance and Calibration did. The Strategy
  registry's per-row rolling-win-rate sparkline and the heatmap are already
  visual.
- No backend change to `/analytics/snapshot` or `/analytics/performance`
  beyond whatever the Plans tab's new endpoint needs — the six-chart list
  above is entirely servable from data already being fetched.
