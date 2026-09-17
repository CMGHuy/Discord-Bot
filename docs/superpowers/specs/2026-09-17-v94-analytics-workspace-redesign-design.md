Version: ui 1.18.3 · bot 1.9.2
Bump: ui minor · bot patch
Edge: none (integrity)
Depends on: v93 Phase 1b (read side) merged to `main` — this spec absorbs its `ledger` dimension, WEAK tile and soak column as inputs.

# v94 — Analytics workspace redesign: six question-ordered tabs, one scope, honest charts

## 1. Why

The Analytics workspace (`frontend/src/app/workspaces/analytics/analytics.ts`, 2,233
lines, five tabs) is the accretion of four redesigns — v30, v63, v78, v85 — each of
which added panels without re-homing the ones already there. Read cold on
2026-09-17, the Performance tab stacks twelve sections in the order they were
added, not the order a trader asks questions in:

- **One question answered four times.** Win rate appears in the KPI row, the
  Overall panel and the Derived panel. Sharpe appears three times; profit factor,
  max drawdown and expectancy twice. Record, Overall, Risk-adjusted and Derived are
  four chip panels answering "how are we doing".
- **Scope is a lie.** Two independent date-range controls on one tab. The range
  applies to the equity curve, the derived chips and the range-scoped histograms,
  and silently does *not* apply to exit quality, the strategy heat grid,
  calibration, or any panel reading the analytics snapshot (`by[dim]`
  breakdowns, direction, weekday, strategy contribution). A screen that hides how
  scoped its data is has a correctness bug (`CLAUDE.md`, UX seat).
- **The finding that explains the book is buried.** Exit quality — winners bank
  ~43% of their available move, losers held 2.1× longer than winners (memory
  `prod-live-book-2026-09-10`, the evidence base of the live v92 harvest plan) —
  sits below a collapsed Breakdowns disclosure at the bottom of the tab.
- **Silent degradation.** Exit-quality, risk-metrics and by-dimension fetches
  render an empty panel on failure. Nothing distinguishes "no trades" from
  "request failed".
- **False confidence in thin cells.** The strategy × horizon win-rate heat grid is
  460 cells over 782 closed trades (36 of 46 strategies under the N=20 floor); it
  colours a 3-trade cell as confidently as a 140-trade one.
- **Computed, never shown.** The API already returns rolling win rate, rolling
  returns, cumulative R per strategy and an SPY benchmark series; the page reads
  none of them.

This is `Edge: none (integrity)`. It changes no trading logic. It exists so the
person deciding what to work on next reads the book as it is.

## 2. What already exists (do not rebuild)

- **Primitives** in `frontend/src/app/ui/`: `sb-line-chart` (with a crosshair
  tooltip already), `sb-histogram`, `sb-bar-list` (signed/rate modes, withheld
  rows), `sb-donut`, `sb-scatter`, `sb-sparkline`, `sb-stat-tile`,
  `sb-metric-chip`, `sb-matrix` (correlation heat grid), `sb-control-bar`,
  `sb-filter-bar`, `sb-async`, `sb-hint`, `sb-freshness`, `sb-data-table`.
  Tokens in `frontend/src/styles/tokens.css`: `--chart-1…6` categorical,
  `--pos/--neg/--warn/--info` status, `--text-hero/--text-metric/…` scale.
- **Backend** in `swingbot/core/analytics/`: `metrics.py` (the single definition
  of every statistic, including `rolling_win_rate`, `cumulative_pnl_by_strategy`,
  `calendar_returns`, `hold_by_outcome`, `in_date_range`), `aggregate.stats_by`
  over `DIMENSIONS` with `MIN_CELL_N = 20`, `exit_quality.py`, `calibration.py`,
  `insights.py`, `journal.py`. Routes in `swingbot/admin/api_v1/analytics.py`.
- **Store** `frontend/src/app/stores/analytics.store.ts` (1,479 lines): typed
  rows, `rateOrWithheld`, `binRMultiples`, bar transforms from v89.
- **v93** (must be merged first): `ledger` in `aggregate.DIMENSIONS`,
  `performance.weak`, `by-dimension` strategy rows carrying `soak`, `Dashboard.realized_weak`.

Everything above is reused. What changes is *where* it is shown, *what scope* it
obeys, and *how honestly* it renders.

## 3. Design

### 3.1 Six tabs, in the order a trader asks (D1)

| Tab | Question | Scope |
|---|---|---|
| **Overview** | Am I making money? | control bar |
| **Attribution** | Where does it come from? | control bar |
| **Execution** | Am I executing well? | control bar |
| **Edge** | Is the edge holding, and is the model calibrated? | control bar; calibration panels all-time |
| **Pipeline** | What is coming? | all-time |
| **Tuning** | Operations (grid jobs, proposals) | none |

Calibration folds into Edge: "does confidence predict outcome" and "is the edge
decaying" are one question asked of the model and of time. Tuning is unchanged in
function and restyled only. The `?tab=` query parameter keeps its role; old values
(`performance`, `strategies`, `calibration`, `plans`) redirect to their new home so
bookmarks survive.

### 3.2 One control bar, every panel obeys it (D2)

Under the tab strip, using `sb-control-bar`:

```
[Range: Last 30d ▾] [Ledger: main ▾] [Strategy: any ▾] [Horizon: any ▾] [Direction: both ▾]
                                     Unit: (R) % $   ·   N=312 closed · built 09:41 · 2 panels all-time
```

- **Range first**, as a preset list — `30d · 90d · YTD · All · Custom…` — not two
  bare date inputs. Custom reveals from/to.
- **Ledger** offers `main · weak · both` (v93). Default `main`.
- **State lives in the URL** (`?tab=&from=&to=&ledger=&strategy=&horizon=&direction=&unit=`),
  so a filtered view is a link and survives tab switches and reload.
- **The bar reports the population it produced**: closed-trade N for the scope,
  the freshness stamp, and a count of panels on the active tab that are all-time.
- **On Tuning** the bar collapses to the unit toggle only. Nothing pretends to
  scope a job list.
- **Refetch keeps the frame.** On scope change every panel holds its last render
  at reduced opacity until new data lands. No skeleton flash, no layout jump.

### 3.3 Unit toggle: R headline, currency always visible (D3)

`R` is the default. The toggle picks the *headline* unit for every panel that can
restate itself (KPI tiles, equity curve, monthly strip, waterfall, grouped table,
bar lists). The currency amount is **always present** — the second line of every
KPI tile, a row in every hover readout, a total in each panel header — never
hidden behind the toggle. Panels with one natural unit (win rate, exit efficiency,
calibration) ignore it. `unit` is a control-bar preference and a URL parameter.

### 3.4 Panel chrome: every panel says what it rests on (D4)

New `sb-panel-header` used by every panel on the page: title · **N** · optional
**all-time** badge · `sb-hint` glyph opening the metric's definition and formula ·
a **Table** action that renders the panel's series as a small `sb-data-table`
(no value is reachable only by colour or hover). New `sb-panel-error`: a compact
"could not load · Retry" surface that replaces the chart on fetch failure. The
three silent-degradation paths (exit quality, risk metrics, by-dimension) route
through it; "no trades in scope" uses `sb-empty-state`, so the two states never
look alike.

### 3.5 Backend contract: one scope, parsed once (D5)

New `swingbot/core/analytics/scope.py`:

```python
@dataclass(frozen=True)
class BookScope:
    start: str | None; end: str | None          # ISO dates, inclusive
    ledger: str = "main"                        # main | weak | both
    strategy: str | None = None
    horizon: str | None = None
    direction: str | None = None                # bullish | bearish

def parse_scope(args: Mapping[str, str]) -> BookScope   # 400 "invalid" on bad values
def select(closed: list[dict], scope: BookScope) -> list[dict]
def echo(scope: BookScope, n: int) -> dict               # {"scope": {...}, "n": n}
```

Every scoped route reads `parse_scope(request.args)`, filters with `select`, and
includes `echo(...)` at the top level of its payload. The frontend sends the same
query string to every endpoint.

| Endpoint | Change |
|---|---|
| `GET /analytics/performance` | scoped (replaces its ad-hoc `from`/`to`); adds `rolling_wr`, `rolling_exp_r` (trailing 50 closed, per trade index, with date) |
| `GET /analytics/equity-curve` | scoped; `points[]` gains `cum_pnl` (currency) and `cum_pct`; `benchmark.spy_indexed[]` (percent, indexed to range start) |
| `GET /analytics/by-dimension` | scoped; `dim` accepts every `aggregate.DIMENSIONS` value plus `ledger`; rows are `StatRow` fields + `avg_win_r`, `avg_loss_r`, `total_pnl`, `badge`, `soak`; **rate fields are `null` when `n < MIN_CELL_N`**, computed server-side, never left to the client |
| `GET /analytics/heat-grid` (new) | scoped; `{rows:[strategy…], cols:[horizon…], cells:[{r,c,n,exp_r,win_rate}], folded:{n_strategies, cells}}` — rows are strategies with total `n >= MIN_CELL_N`; the rest fold into one `Other` row |
| `GET /analytics/exit-quality` | scoped (was all-time) |
| `GET /analytics/journal` | scoped |
| `GET /analytics/strategies` | scoped for contribution and cumulative-R series; registry rows stay all-time and say so (`scope: "all-time"` on that block) |
| `GET /analytics/calibration` | unchanged, returns `scope: "all-time"` |
| `GET /analytics/plans` | unchanged, returns `scope: "all-time"` |

**The page stops reading `GET /analytics/snapshot`.** The snapshot is a cached
all-time artefact built for the Dashboard and Discord; it is the root of the
"range does not apply" problem. It is untouched and the Dashboard keeps using it.

Nothing in the scan, planning, sizing or exit path is touched. Read side only.

### 3.6 Overview (D6)

```
KPI row (6 + WEAK when ledger=both): Total R ($) · ExpR · Win rate · Profit factor · Max DD · Sharpe
   each: headline in unit · currency line · N · trailing-30-trade sparkline
┌ Equity (unit), SPY grey context in % mode only ┬ Outcome: [wins ▓▓▓▓░░░ losses] ┐
│ Drawdown pane below, shared x-axis             │ avg win · avg loss · payoff · streaks │
├ R distribution (histogram, 0 line, mean|median)┼ Monthly: 12 signed bars → Calendar ┤
```

- Equity and drawdown are **two stacked panes sharing one x-axis**, not a toggle.
- SPY appears only in `%` mode, indexed to the range start — **one axis, never a
  dual axis**; in R mode a footnote says why it is absent.
- The win/loss donut is removed: a 53/47 split is what a donut renders worst. It
  becomes one horizontal part-to-whole bar with avg win R, avg loss R and payoff
  ratio beside it; streaks (current, best, worst) beneath.
- Monthly returns is a twelve-bar signed strip linking to the Calendar workspace,
  which owns the day grid. No duplicate calendar.
- Record / Overall / Risk-adjusted / Derived chip panels are **deleted**; every
  figure they held is either a KPI tile, a hover readout, or a row in the panel
  Table view. Nothing is lost; nothing is shown four times.

### 3.7 Attribution (D7)

A **measure toggle** `ExpR · Total R · Win rate` (v85 D40, extended) drives every
panel on the tab.

- **Total-R waterfall by strategy** (new `sb-waterfall`): baseline 0 → book total,
  top 8 by |total R| plus `Other`, positive steps `--pos`, negative `--neg`.
- **ExpR-vs-N dot plot** (new `sb-dot-plot`): one dot per cell of the picked
  dimension, x = N (log), y = measure, vertical floor line at `MIN_CELL_N`,
  hollow dots below it. The honesty instrument: +0.5R on 9 trades is visibly not
  +0.2R on 140.
- **Strategy × horizon heat grid** on `sb-matrix` with a floor-aware cell
  renderer: cells under the floor render blank with their N and a dotted outline;
  cell picker `ExpR · Win rate · N`. ExpR uses the diverging ramp centred on 0;
  win rate and N a single-hue sequential ramp. Rows come from `/heat-grid`
  (fat strategies + `Other`).
- **Four bar lists** — horizon, direction, weekday, month — signed, N labels,
  withheld rows for thin cells.
- **Grouped table** with a dimension picker over every dimension (strategy,
  horizon, badge, confidence, direction, weekday, month, ticker, source, ledger),
  sortable, ExpR column with inline bar, badge and soak rail on strategy rows.

### 3.8 Execution (D8)

```
Strip: efficiency median · disposition ratio · hold W / L · journal coverage
┌ Exit efficiency, winners (histogram, median) ┬ MFE vs MAE scatter, 1R quadrants, 24px hits ┐
├ Hold time by outcome: two strip plots        ┼ Exit reason mix: one stacked bar, "unrecorded" explicit ┤
├ By holding period · By planned R:R           ┼ Journal: digest · lessons · N ┤
```

- The strip states the exit-quality verdict in four numbers before any chart.
- The two exit-quality donuts are removed. Exit reason becomes one stacked bar
  where **`unrecorded` is its own segment** (58% of the live book on
  2026-09-10 — a data-quality signal the reader must see, not a slice to hide).
- Hold time by outcome is drawn as two strip plots (new `sb-strip-plot`) with
  medians — the disposition effect is a shape, not a sentence.
- Winners-only histograms carry a **coverage** figure (MFE/MAE/efficiency journal
  coverage) in the strip and in their headers.

### 3.9 Edge (D9)

```
[edge-decay banner when firing]
Rolling win rate (trailing 50 closed) — pooled reference line
Rolling ExpR (shared x-axis) — zero line
Cumulative R per strategy: small multiples, one pane per fat strategy, shared y, "Other" pane
Strategy registry table: badge · N · ExpR · WR · sparkline · soak (v93) · drift
Calibration (all-time badge): quality-score deciles ┬ confidence level table · tier table
```

- Rolling win rate and rolling ExpR **lead the tab** — the direct answer to "is
  the edge holding", computed today and rendered nowhere.
- Cumulative R per strategy as **small multiples** (new `sb-small-multiples`
  wrapping `sb-line-chart`), shared y-scale, never one twelve-line chart.
- Badge drift becomes a column of the registry table, not a separate table.
- Calibration keeps its three views. The tier table's data path is verified
  against live data (it has rendered empty before: writer used `levels`, reader
  `tiers` — memory `prod-live-book-2026-09-10`).

### 3.10 Pipeline and Tuning (D10)

Pipeline keeps funnel, fill rate, badge and tier distribution on the new panel
chrome, all-time badge, N on funnel stages. Tuning: restyle only — same jobs,
grid results, proposals, confirm dialogs.

### 3.11 Primitive work (D11)

- **Shared hover layer** (`ui/chart-hover.ts`): per-mark tooltip for bars, cells,
  dots and strips; hovered mark lifts; hit target ≥ 24px and larger than the mark;
  keyboard focus gets the same readout. `sb-line-chart`'s existing tooltip moves
  onto it so every chart reads one way. Values lead, labels follow; series keyed
  by a stroke, not a box; labels inserted via `textContent`.
- **New primitives**: `sb-waterfall`, `sb-dot-plot`, `sb-strip-plot`,
  `sb-share-bar` (part-to-whole), `sb-small-multiples`, `sb-panel-header`,
  `sb-panel-error`. Each is standalone, OnPush, takes plain data inputs, and has
  a spec.
- **Palette**: `--chart-1…6` run through the dataviz validator against
  `--surface` in both themes; failures are re-stepped in `tokens.css`. A strategy
  keeps its hue across filters (colour follows the entity, never its rank):
  hue assignment is by all-time rank of the top 8 strategies, frozen per session,
  everything else is `Other` in `--text-faint`. Never a generated ninth hue.
- **Marks**: 2px lines, thin bars with 4px rounded data-ends, 2px surface gap
  between adjacent fills, recessive solid grid, no dashed rules, text in text
  tokens never series colour.

### 3.12 Design pass (D12)

Lighter panel chrome (hairline `--border`), recessive grids, one typographic
hierarchy from `--text-hero` to `--text-micro`, `--section-gap` rhythm, and an
explicit light and dark check per tab. Implementers load the `frontend-design`
skill at this task. The 2,233-line `analytics.ts` splits into six tab components
(`tabs/overview.ts`, `attribution.ts`, `execution.ts`, `edge.ts`, `pipeline.ts`,
`tuning.ts`) over one `AnalyticsStore`, with the control bar and tab strip in a
thin shell. Files stay under ~400 lines each.

## 4. Honesty rules the payload and the page must keep

1. **Thin cells never show a rate.** `n < MIN_CELL_N` → rate fields `null` from
   the server; the client renders blank + N + dotted outline. Composition
   (counts, totals) still includes them.
2. **Every panel states its N and its scope.** Scoped panels echo the bar's N;
   all-time panels carry the badge.
3. **Absence is labelled.** `unrecorded` exit reasons, missing journal coverage,
   SPY absent in R mode — each is a visible label, never an omitted slice.
4. **Failure is not emptiness.** Fetch failure → `sb-panel-error`; zero trades →
   `sb-empty-state`.
5. **One axis per chart.** Two measures of different scale → two panes or indexed
   series, never a dual axis.

## 5. Non-goals

Dashboard, Risk and Calendar workspaces (unchanged); CSV export; Discord output;
any change to scan, planning, sizing or exit logic; adopting a charting library;
per-panel filters (the bar is the only scope); mobile-first layout beyond the
existing breakpoints; changing `MIN_CELL_N` or making it a setting.

## 6. Testing

- `tests/analytics/test_scope.py`: parse (defaults, each param, invalid → 400
  shape), `select` on every field, `echo`.
- Every scoped route: asserts `scope` echo, `n`, and that the same query string
  yields the same N across endpoints (`tests/admin/test_api_v1_analytics.py`).
- `by-dimension`: rate fields `null` under the floor; `heat-grid`: fold row present
  and counted; `equity-curve`: `spy_indexed` starts at 0 at range start.
- Frontend: one spec per tab component and per new primitive; store spec for URL
  ⇄ scope round trip and the `?tab=` redirects; contract spec updated.
- Final task: `python scripts/dev/testrun.py full` once, `cd frontend && npm test`
  once, palette validator both themes, screenshot pass of six tabs × two themes.

## Parallelisation

- **Sequential first:** `scope.py` + `parse_scope` (every route consumes it);
  `sb-panel-header`/`sb-panel-error`/hover layer (every tab consumes them); the
  shell + store scope state (every tab component consumes it).
- **Group A (parallel, backend):** one route per task — performance,
  equity-curve, by-dimension, heat-grid, exit-quality, journal, strategies. Disjoint
  functions in `analytics.py`; tests appended to one file, so **commit per task**.
- **Group B (parallel, primitives):** waterfall, dot-plot, strip-plot, share-bar,
  small-multiples — one file + one spec each.
- **Group C (parallel, tabs, after A+B):** overview, attribution, execution,
  edge, pipeline, tuning — one component file + spec each.
- **Sequential last:** design pass (touches every tab file), palette validation
  (`tokens.css`), full verification.

## Success criteria

- Every panel on Overview, Attribution, Execution and the scoped half of Edge
  changes when the range, ledger, strategy, horizon or direction changes, and the
  bar's N matches every scoped panel's N.
- No metric appears in more than one place on a tab except as a hover readout or
  Table row.
- No cell with `n < 20` displays a rate anywhere on the page.
- Rolling win rate, rolling ExpR, cumulative R per strategy and SPY (in % mode)
  are visible for the first time.
- A killed endpoint produces a Retry surface, not an empty panel.
- Both suites green once at the end; palette validator passes both themes.
