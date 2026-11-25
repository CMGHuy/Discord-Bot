# v246 — UI polish, Plan A of five: requests (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task at a time (`grep -n "^### Task V246-7" -A 400 <part file>`); never read a part whole.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [2026-11-23-v246-ui-polish-filters-charts-interactions-design.md](../specs/2026-11-23-v246-ui-polish-filters-charts-interactions-design.md) — **Plan A of five** ("What follows" item 1: §A1 Recent activity, §A2 control alignment, §A3 charts, plus the A rows of "Error, empty and edge states", "Three devices" and "Testing"). Plans B1, B2, C1 and C2 take later, fresh numbers and are out of scope here.
**Brief:** `.superpowers/briefs/2026-11-23-v246-ui-polish-plan-a-requests.md` — its §0 mismatches and §7 traps override the spec's "before" text wherever they disagree.
**Runs after:** v247 (v240 plan 3, shell and navigation), not yet implemented. **Runs before:** v240 plan 4 (drawer core), then v246 B1. One worktree at a time; nothing here runs in parallel with v247.

## Goal

On 2026-11-23 the partner asked for three things on bomeo-capital.com that
this plan delivers (the fourth, Calendar as its own page, ships in v247).
The Dashboard's Recent activity reads `SOFI Closed at −1.00R`, where "Closed
at" repeats what the row's icon already says. Rows of filters do not line
up: a select with a label above it is taller than a control without one,
and the bars centre them, so on Calendar the month arrows and the €/R
switch float about 28px above the selects (seen at 1440 and 820), on
Analytics the date boxes sit above the selects and the second date is
clipped at 390, and on Trades the Ticker and Strategy boxes are twice as
wide as the selects. And the charts look unfinished: the Analytics equity
and drawdown are hand-drawn SVG step lines in a blue used nowhere else, with
no axes and no zero line; the Dashboard equity axis prints `997800.00`, a
stray `)` sits on its time axis and at 390 the last-value tag covers an axis
label; the R distribution labels its buckets at odd centres (−4.9R, −3.9R).

Once this ships, a closed Recent-activity row reads `SOFI −1.00R`, coloured
by sign, while its accessible name still says "SOFI closed, −1.00R" and the
panel hint states the R is pre-tax and before modelled frictions. Every
control in a filter bar sits in one `sb-field`: a label line above (an empty
filler line when the control has no label), a width token `--field-s/m/l`,
and the shared `--control-h` height (28px, 44px below 1024px). The bars
align their fields along the bottom edge, so Trades, Calendar, the
Analytics scope bar, Watchlist and the Dashboard toggles line up at every
width; Calendar's metric switch and Trades' Compact/Full become
`sb-segmented` like the rest. A consistency gate fails any new control in a
bar outside an `sb-field`, with an allowlist for the bars plan B10 wraps
later. The charts share one theme module (`chart-theme.ts`, extended, not
created): thousands separators and the true minus on price axes, a signed
`R` format, one `applyChartTheme(chart)`, and `SVG_CHART_TOKENS` for the six
SVG charts. A new `sb-time-series` wrapper draws the Analytics equity as an
accent area and the drawdown as a shaded baseline below zero, the two
scrolling together, and the drawdown header adds max drawdown in € and the
longest losing streak. The R distribution buckets sit on whole-R edges,
labelled by their lower edge.

How it works: `sb-field` provides an injection token that `sb-select` and
`sb-text-input` read, so a wrapped control drops its own visible label and
keeps its accessible name (one label path per bar). Alignment is CSS
(`align-items: flex-end` on `sb-control-bar`, `sb-toolbar` and an opt-in
`sb-control-row align="end"`), asserted from CSS source per consumer in `ng test`
(jsdom has no layout) and measured by bottom edge in Playwright at
390/820/1440 in the closing task, which covers both `--control-h` values.
The whole-R edges are a server change: an opt-in `whole_r=True` mode on
`metrics.histogram`, used only by the R-distribution payload.

What it leaves alone: the bars of System logs/scan/settings, Research,
Tuning, Partials, Attribution and Benchmark get the flex-end change but keep
unwrapped controls until B10; the crosshair tooltip and click-through (plan
C); the returns and exit-quality histograms and their golden snapshot
entries, which stay byte-identical; every number the app computes (the
drawdown header reads values that already exist); Discord chart PNGs.

How we know it worked: the narrow specs named in each task pass; the
closing task's Playwright check reports one bottom edge per bar on Trades,
Calendar, Analytics, Watchlist and Dashboard at 390, 820 and 1440, and
`node frontend/scripts/layout-audit.mjs` reports no overflow, target-size
or text-size finding on those pages; CI's full run is green after the push.

## Architecture

- **Recent activity** (V246-1): `deriveActivity()` drops the "Closed at"
  prefix; `recent-activity.ts` gives `button.event-hit` its own
  `aria-label`; `PANEL_HELP.recentActivity` gains the cost-basis sentence.
- **Whole-R buckets** (V246-2): `metrics.histogram(values, *, bins=20,
  whole_r=False)`; `page_bodies.py` passes `whole_r=True` for
  `distributions.r_multiples` only. The `{lo, hi, count}` shape is
  unchanged (no schema change). The frontend `rBins` labels by lower edge.
- **Fields** (V246-3, V246-4): new `ui/field.ts` (`sb-field`, `SB_FIELD`
  token), three width tokens in `styles/tokens.css`; `form-controls.ts`
  and `date-range.ts` read the field context and the `--sb-control-w`
  custom property the field sets.
- **Bars** (V246-5, V246-6): `sb-segmented` gains the phone full-row rule;
  `sb-control-bar` and `sb-toolbar` align to `flex-end`; `sb-control-row`
  gains opt-in `align="end"` (default stays `last baseline`, decision 8).
- **Consumers** (V246-7..V246-10): Trades, Calendar, Analytics scope bar,
  Watchlist, Dashboard trading-performance and equity-candles toggles wrap
  their controls in `sb-field`.
- **Gate** (V246-11): `workspace-consistency.spec.ts` gains the field rule
  and `FIELD_GATE_ALLOWLIST`.
- **Chart theme** (V246-12): `ui/chart/chart-theme.ts` gains `priceFormat`,
  `rFormat`, `pctFormat`, `applyChartTheme`, `SVG_CHART_TOKENS` and the
  Navy fallback for a missing token.
- **Time series** (V246-13, V246-14): new `ui/chart/time-series.ts`
  (`sb-time-series`) and `ui/chart/time-scale-sync.ts` (`TimeScaleSync`).
- **Chart consumers** (V246-15..V246-17): Analytics Overview moves onto
  `sb-time-series`; Dashboard equity candles adopt the theme and lose the
  axis defects; the six SVG charts read `SVG_CHART_TOKENS`.
- **Check** (V246-18): Playwright bottom-edge check plus the layout audit.

**Tech stack:** Angular (zoneless, signals, standalone components), vitest
under `ng test` with jsdom, `lightweight-charts` ^5.2.1 (already a
dependency), Playwright ^1.64.1 for the closing check; Python 3.11 + pytest
for the one backend task.

## Global Constraints

- Frontend paths are under `frontend/src/app/` unless written in full.
- Narrow verification only: `python scripts/dev/testrun.py file <test>` for
  Python, `cd frontend && npx ng test --watch=false --include <spec>` for a
  frontend spec (or `python scripts/dev/testrun.py changed`). No task runs
  the full suite; CI does.
- Tokens only, never literals or invented names. The spec's names map to
  real tokens (Handoff decision 3): `--money-pos` → `--pos`, `--money-neg` →
  `--neg`, `--border-subtle` → `--border`, `--text-tertiary` →
  `--text-muted` (`--text-faint` only where the spec means the faintest
  step). `resolveToken()` in `ui/testing/theme-tokens.ts` throws on an
  unknown name; specs use it to prove a token exists.
- Every control in a bar consumes `var(--control-h)` (28px base, 44px
  below 1024px, `styles/tokens.css:311,410`). Touch targets stay ≥ 44px
  below 1024px.
- The true minus (U+2212) for every negative number shown; reuse
  `ui/format.ts` (`fixed`, `rMultiple`, `num`, `money`), never a new
  formatter for the same job.
- `sb-toolbar` projection rule (brief Trap 3): every projected control is a
  single element carrying `slot="<id>"`, never inside a host-side
  `@if`/`@for`; once a control sits in an `sb-field`, the `sb-field`
  carries the `slot`.
- `sb-control-bar` slot rule (brief Trap 4, NG8011): one `ng-container`
  per slot; an `@if` with several roots inside a slot drops all but the
  first.
- `chartOptions()` resets `timeScale.timeVisible`; every re-application of
  the theme on the Dashboard chart is followed by `timeScaleOptions(data)`
  (brief Trap 5). `applyChartTheme` keeps that contract.
- jsdom has no layout and no `ResizeObserver`: alignment is asserted from
  CSS source in `ng test` (the `readFileSync` pattern of
  `ui/control-bar.spec.ts`) and measured only in Playwright; chart specs
  stub `ResizeObserver` and fake `createChart` (pattern:
  `workspaces/dashboard/panels/equity-candles.spec.ts`).
- Recent-activity R is coloured by sign only and never worded as a verdict.
- V246-2's Python stays under cyclomatic complexity 15
  (`scripts/dev/complexity_gate.py`); TypeScript helpers stay small and
  named.
- Browser checks log in with `.env`'s `ADMIN_USERNAME` / `ADMIN_PASSWORD`
  through `POST /api/v1/session`, loaded inside the script and never
  printed; Playwright only.
- Commits are scoped (one task, one or two commits), never one big one.

## Parallelisation

Default: run the tasks in id order, one at a time. Sequential edges and
their reasons:

- **v247 → this plan.** Plan A starts once v247 is merged. Files v247 also
  edits, and the task here that edits them after it:
  - `workspaces/calendar/calendar.ts` and `calendar.spec.ts` — **V247-3**
    (links flip to `/calendar`) → **V246-8**.
  - `workspaces/analytics/tabs/overview.ts` — **V247-3** (Overview's
    calendar link) → **V246-2**, **V246-15**.
  - `ui/hit-area.spec.ts` — **V247-3** and **V247-8** → **V246-5** (adds
    the segmented phone row; merges against their rows).
  - `frontend/scripts/layout-audit.mjs`, `layout-audit-lib.mjs` —
    **V247-4**, **V247-9** (route list gains `calendar`, `rail-label`
    redefined) → **V246-18** (runs the audit, does not edit it).
- V246-3 → V246-4: V246-4 consumes `SB_FIELD`, `FieldContext` and the
  `--sb-control-w` property.
- V246-3, V246-4, V246-5, V246-6 → V246-7, V246-8, V246-9, V246-10: the
  consumers wrap controls in `sb-field` and rely on the label drop, the
  date-range field layout, the segmented phone rule and the flex-end bars.
- V246-7..V246-10 → V246-11: the gate must pass on the wrapped consumers;
  its allowlist names only the bars B10 wraps.
- V246-2 → V246-15: both edit `workspaces/analytics/tabs/overview.ts` and
  `overview.spec.ts`.
- V246-10 → V246-16: both edit `workspaces/dashboard/panels/equity-candles.ts`
  and its spec.
- V246-12 → V246-13, V246-16, V246-17: they consume `applyChartTheme`,
  `priceFormat`, `rFormat`, `pctFormat` and `SVG_CHART_TOKENS`.
- V246-16 → V246-16b: same file; 16b edits the `timeScaleOptions()` 16 defines.
- V246-13 → V246-13b → V246-14: all three edit `time-series.ts` in order; V246-14 adds the `sync` input.
- V246-14 → V246-15: Overview links its two charts with `TimeScaleSync`.
- Every task → V246-18: the browser check exercises the finished pages.

Safe in parallel if the controller wants to (disjoint files, no contract
between them): **V246-1 ∥ V246-2 ∥ V246-3** at the start (dashboard panel
files vs Python and `overview.ts` vs `ui/field.ts` and `tokens.css`), and
**V246-12 ∥ V246-5** (`chart-theme.ts` vs `segmented.ts`). The partner's
default is one subagent at a time; parallel runs only when asked.

## Task ledger

| ID | Title | Part | Model | Files (C create, M modify) | Symbols for later tasks |
|---|---|---|---|---|---|
| V246-1 | Recent activity shows the signed R only; accessible name keeps the status; cost-basis hint | 1 | haiku | M `frontend/src/app/workspaces/dashboard/panels/activity.ts`, M `.../panels/activity.spec.ts`, M `.../panels/recent-activity.ts`, M `.../panels/recent-activity.spec.ts`, M `.../panels/panel-help.ts` | none |
| V246-2 | R distribution on whole-R edges: `histogram(..., whole_r=True)` for `r_multiples` only; labels by lower edge (bot patch) | 1 | sonnet | M `swingbot/core/analytics/metrics.py`, M `swingbot/core/analytics/page_bodies.py`, M `tests/analytics/test_metrics_derived.py`, M `tests/admin_snapshots/golden/performance_main.json`, M `frontend/src/app/workspaces/analytics/tabs/overview.ts`, M `.../tabs/overview.spec.ts` | `metrics.histogram(values: list[float], *, bins: int = 20, whole_r: bool = False) -> list[dict]`; `distributions.r_multiples` rows `{lo, hi, count}` with integer `lo`/`hi`; frontend `rBins` label = lower edge (`−5R`, `0R`, `+1R`) |
| V246-3 | `sb-field` and the `--field-s/m/l` width tokens | 1 | sonnet | C `frontend/src/app/ui/field.ts`, C `frontend/src/app/ui/field.spec.ts`, M `frontend/src/styles/tokens.css`, M `frontend/src/app/ui/tokens.spec.ts`, M `frontend/src/app/workspaces/gallery/gallery.ts` | `Field` (`sb-field`): `label = input<string>('')`, `size = input<FieldSize>('m')`, `fullRow = input<boolean>(false)`; `export type FieldSize = 's' \| 'm' \| 'l' \| 'auto'`; `export interface FieldContext { readonly label: Signal<string> }`; `export const SB_FIELD = new InjectionToken<FieldContext>('SB_FIELD')`; host sets `--sb-control-w` (the size token; `100%` below 640px; unset for `auto`); tokens `--field-s`, `--field-m`, `--field-l` |
| V246-4 | `sb-select` / `sb-text-input` drop their visible label inside `sb-field`; `sb-date-range` as one field (M + M inline, 50/50 below 640px) | 1 | sonnet | M `frontend/src/app/ui/form-controls.ts`, M `frontend/src/app/ui/form-controls.spec.ts`, M `frontend/src/app/ui/date-range.ts`, M `frontend/src/app/ui/date-range.spec.ts` | `Select`/`TextInput` inject `SB_FIELD` optionally: inside a field no `.sb-label`, `aria-label` = own `label()` ?? `ariaLabel()` ?? field `label()`; `select`/`input` width `var(--sb-control-w, auto)`; `DateRange` inputs width `var(--field-m)`, `height: var(--control-h)`, host full width and inputs `flex: 1 1 0` below 640px (no new inputs) |
| V246-5 | `sb-segmented` in a bar: 3+ options take the full row below 640px, equal segments, never wrap | 2 | sonnet | M `frontend/src/app/ui/segmented.ts`, M `frontend/src/app/ui/segmented.spec.ts`, M `frontend/src/app/ui/hit-area.spec.ts` | `Segmented.many: Signal<boolean>` (options ≥ 3), host class `many` |
| V246-6 | Bars align on the bottom edge: `sb-control-bar`, `sb-toolbar` → `flex-end`, `sb-control-row` opt-in `align="end"`; phone fields fill their grid cell | 2 | sonnet | M `frontend/src/app/ui/control-bar.ts`, M `frontend/src/app/ui/control-bar.spec.ts`, M `frontend/src/app/ui/toolbar.ts`, M `frontend/src/app/ui/toolbar.spec.ts`, M `frontend/src/app/ui/layout.ts`, M `frontend/src/app/ui/layout.spec.ts` | `.clear` height `var(--control-h)`; CSS-source assertion pattern `expect(css).toMatch(/align-items:\s*flex-end/)` reused by V246-7..10 |
| V246-7 | Trades toolbar: controls in `sb-field` (dates "Opened" M+M, Ticker L, Strategy M, selects S/M); Compact/Full → `sb-segmented` "Density" | 2 | sonnet | M `frontend/src/app/workspaces/trades/trades.ts`, M `frontend/src/app/workspaces/trades/trades.spec.ts` | none |
| V246-8 | Calendar month row: arrows, metric switch (→ `sb-segmented` "Show") and selects in `sb-field`s inside `sb-control-row` | 2 | sonnet | M `frontend/src/app/workspaces/calendar/calendar.ts`, M `frontend/src/app/workspaces/calendar/calendar.spec.ts` | none |
| V246-9 | Analytics scope bar: Range/Ledger/Strategy/Horizon/Direction in `sb-field`, date range "Range", Unit segmented "Units" | 3 | sonnet | M `frontend/src/app/workspaces/analytics/scope-bar.ts`, M `frontend/src/app/workspaces/analytics/scope-bar.spec.ts` | none |
| V246-10 | Watchlist search in `sb-field` L; equity-candles toggles labelled ("Interval", "Trades") in `sb-field` (trading-performance presets left to B9, decision 12) | 3 | sonnet | M `frontend/src/app/workspaces/watchlist/watchlist.ts`, M `frontend/src/app/workspaces/watchlist/watchlist.spec.ts`, M `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, M `.../panels/equity-candles.spec.ts`, M `frontend/src/app/workspaces/dashboard/dashboard.spec.ts` | none |
| V246-11 | Consistency gate: a control in a bar outside `sb-field` fails; allowlist for the B10 bars | 3 | sonnet | M `frontend/src/app/workspaces/workspace-consistency.spec.ts` | `FIELD_GATE_ALLOWLIST: readonly string[]` (workspace file names B10 empties and deletes) |
| V246-12 | Chart theme: `priceFormat`, `rFormat`, `pctFormat`, `applyChartTheme`, `SVG_CHART_TOKENS`, Navy fallback logged once | 4 | sonnet | M `frontend/src/app/ui/chart/chart-theme.ts`, M `frontend/src/app/ui/chart/chart-theme.spec.ts` | `export function themedToken(name: string): string` (Navy fallback, warned once); `export const priceFormat: PriceFormatCustom`; `export const rFormat: PriceFormatCustom`; `export const pctFormat: PriceFormatCustom`; `export function applyChartTheme(chart: IChartApi, palette: ChartPalette = chartPalette()): void`; `export const SVG_CHART_TOKENS` (`{ line, pos, neg, grid, axisText, crosshair }` token names + `strokeWidth`, `strokeWidthThin`, `barRadius`, `barGap`, `labelSize`) |
| V246-13 | `sb-time-series`: area / baseline / candles, value formats, height, resize, theme repaint, destroy, 0/1 point | 4 | opus | C `frontend/src/app/ui/chart/time-series.ts`, C `frontend/src/app/ui/chart/time-series.spec.ts`, M `frontend/src/app/workspaces/gallery/gallery.ts` | `TimeSeries` (`sb-time-series`): `kind = input.required<TimeSeriesKind>()`, `points = input.required<readonly TimeSeriesDatum[]>()`, `valueFormat = input<TimeSeriesFormat>('price')`, `height = input<number>(220)`, `label = input.required<string>()`; `export type TimeSeriesKind = 'area' \| 'baseline' \| 'candles'`; `export type TimeSeriesFormat = 'price' \| 'r' \| 'pct'`; `export interface TimeSeriesPoint { time: string; value: number }`; `export interface TimeSeriesCandle { time: string; open: number; high: number; low: number; close: number }`; `export type TimeSeriesDatum = TimeSeriesPoint \| TimeSeriesCandle`; `export function collapseByDay<T extends { time: string }>(points: readonly T[]): T[]` (last per day wins) |
| V246-13b | `sb-time-series` edge states: non-finite dropped, 0/1 point, fit on first width, ResizeObserver, theme repaint, destroy releases all | 4 | opus | M `frontend/src/app/ui/chart/time-series.ts`, M `frontend/src/app/ui/chart/time-series.spec.ts` | none |
| V246-14 | Linked scrolling: `TimeScaleSync` with a ping-pong guard; `sb-time-series` `sync` input released on destroy | 4 | sonnet | C `frontend/src/app/ui/chart/time-scale-sync.ts`, C `frontend/src/app/ui/chart/time-scale-sync.spec.ts`, M `frontend/src/app/ui/chart/time-series.ts`, M `frontend/src/app/ui/chart/time-series.spec.ts` | `export class TimeScaleSync { register(chart: IChartApi): () => void }`; `TimeSeries.sync = input<TimeScaleSync \| null>(null)` |
| V246-15 | Analytics Overview equity (area) and drawdown (baseline) on `sb-time-series`, linked; drawdown header shows max drawdown € and longest losing streak | 5 | sonnet | M `frontend/src/app/workspaces/analytics/tabs/overview.ts`, M `.../tabs/overview.spec.ts` | none |
| V246-16 | Dashboard equity candles: `applyChartTheme`, `priceFormat`, last-value tag clear of axis labels at 390, whole hour/day ticks | 5 | opus | M `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, M `.../panels/equity-candles.spec.ts` | `CANDLE_SCALE_MARGINS`, `wholeTickLabel(time, type)` (exported from `equity-candles.ts`; its spec and V246-16b only) |
| V246-16b | Dashboard equity candles: confirm the stray `)` at the left of the time axis in Chromium and keep edge tick labels whole | 5 | opus | M `frontend/src/app/workspaces/dashboard/panels/equity-candles.ts`, M `.../panels/equity-candles.spec.ts` | none |
| V246-17 | SVG token sweep: line-chart, histogram, bar-list, sparkline, share-bar, gauge read `SVG_CHART_TOKENS` | 5 | sonnet | M `frontend/src/app/ui/line-chart.ts`, M `frontend/src/app/ui/line-chart.spec.ts`, M `frontend/src/app/ui/histogram.ts`, M `frontend/src/app/ui/histogram.spec.ts`, M `frontend/src/app/ui/bar-list.ts`, M `frontend/src/app/ui/bar-list.spec.ts`, M `frontend/src/app/ui/sparkline.ts`, C `frontend/src/app/ui/sparkline.spec.ts`, M `frontend/src/app/ui/share-bar.ts`, M `frontend/src/app/ui/share-bar.spec.ts`, M `frontend/src/app/ui/gauge.ts`, M `frontend/src/app/ui/gauge.spec.ts` | none |
| V246-18 | Closing browser check: bottom-edge alignment per bar and the layout audit at 390/820/1440 | 5 | sonnet | C `frontend/scripts/v246-bar-alignment-check.mjs`, C `frontend/scripts/v246-bar-alignment-check-lib.mjs`, C `frontend/scripts/v246-bar-alignment-check-lib.test.mjs` | none |

`.../panels/` is `frontend/src/app/workspaces/dashboard/panels/`;
`.../tabs/` is `frontend/src/app/workspaces/analytics/tabs/`. 18 rows; the
cap is 20, so at most two `b` splits fit before this plan is a `SCOPE`.

## Parts

| Part | File | Tasks | Scope |
|---|---|---|---|
| 1 | `2026-11-23-v246-ui-polish-requests_1-activity-r-and-field.md` | V246-1..V246-4 | Recent activity R, whole-R buckets (the backend task), `sb-field` and its tokens, the label drop and the date-range field |
| 2 | `2026-11-23-v246-ui-polish-requests_2-bars-trades-calendar.md` | V246-5..V246-8 | Segmented phone rule, flex-end bars, Trades and Calendar wrapped |
| 3 | `2026-11-23-v246-ui-polish-requests_3-analytics-watchlist-gate.md` | V246-9..V246-11 | Analytics scope bar, Watchlist and Dashboard toggles, the consistency gate |
| 4 | `2026-11-23-v246-ui-polish-requests_4-chart-theme-and-time-series.md` | V246-12..V246-14 (incl. V246-13b) | Theme exports, `sb-time-series`, linked scrolling |
| 5 | `2026-11-23-v246-ui-polish-requests_5-chart-consumers-and-check.md` | V246-15..V246-18 (incl. V246-16b) | Overview charts, Dashboard candles, SVG sweep, closing check |

## Handoff

Partner decisions (2026-11-24), binding on every part writer and
implementer:

1. **R-distribution whole-R edges.** Add an optional whole-R bin mode to
   `metrics.histogram` (`whole_r: bool = False`), used only by the
   R-distribution payload (`page_bodies.py` `distributions.r_multiples`).
   `returns` and `exit_quality` histograms and their golden snapshot
   entries stay byte-identical, pinned by a regression test. This is the
   bot-patch backend task (V246-2). `metrics.histogram`'s default
   behaviour does not change.
2. **`sb-field` owns the label.** A control inside `sb-field` renders no
   label of its own; its `label` input stays for standalone use, and
   `aria-label` still names the control. One label path per bar (V246-3,
   V246-4).
3. **Token mapping** (the spec's names do not exist): `--money-pos` →
   `--pos`, `--money-neg` → `--neg`, `--border-subtle` → `--border`,
   `--text-tertiary` → `--text-muted` (`--text-faint` where the spec means
   the faintest step). No new colour tokens.
4. **The bar inventory is the brief's, not the spec's.** Trades =
   `sb-toolbar` + a summary-only `sb-filter-bar`; Calendar's month row =
   `sb-control-row`; `sb-control-bar` = Analytics scope bar + Gallery only;
   Calendar's metric switch is `sb-button variant=segment`; Trades'
   Compact/Full is two ghost buttons. Plan against the real code.
5. `ui/chart/chart-theme.ts` and `lightweight-charts` already exist:
   extend, never create.
6. **Drawdown header:** max drawdown € from `overview.ts` `maxDrawdown()`,
   longest losing streak from the existing `worst_loss_streak` payload
   field. No backend work.
7. Plan A runs after v247; every shared-file dependency is named in
   `## Parallelisation`.

Writer decisions (index, 2026-11-24) — the controller should confirm:

8. **Calendar stays in `sb-control-row`.** The spec says its month row
   "moves into an `sb-control-bar`"; with decision 4 the row is already a
   shared bar (`sb-control-row`), and `sb-control-bar` would add a "Clear N"
   and filter/scope slots Calendar does not use. V246-8 wraps Calendar's
   controls in `sb-field` inside it. The gate (V246-11) treats
   `sb-control-row` as a bar.
   **Amended (partner, 2026-11-24): opt-in, not global.** `sb-control-row`
   keeps v179 §3.4's `last baseline` as its default; V246-6 adds an opt-in
   `align="end"` input (host attribute → `align-items: flex-end`) that only
   v246's bars set (Calendar's month row in V246-8, trading-performance only
   if a v246 task wraps it). The ~15 other `sb-control-row` users (Versions
   headline, settings save bar, Watchlist forms, confirm dialog) are
   untouched and `layout.spec.ts`'s baseline pin stays; V246-6 adds a pin for
   the opt-in. The gate (V246-11) checks that a v246 bar using
   `sb-control-row` sets `align="end"`.
9. **Alignment test = CSS source + Playwright.** The spec's "a test gives
   each consumer bar a fixed size and asserts every control's bottom edge
   is the same, at both token values" cannot run in jsdom. Each consumer
   task asserts its CSS/template source (field wrappers present, bar
   `flex-end`, `--control-h` consumed); V246-18 measures bottom edges in
   Chromium at 1440 (28px) and at 820 and 390 (44px).
10. **`sb-field` input names** are `label`, `size` and `fullRow` (the spec
    names `label` and `size`; `fullRow` carries "controls that take a full
    row below 640px drop the empty label filler"). `size='auto'` is for
    month arrows and segmented groups, which have no width token.
11. **Whole-R bucket range** is `floor(min)` to `floor(max) + 1`, step 1,
    empty interior buckets kept (the function's existing rule); `bins` is
    ignored in that mode. No tail clamp: an outlier shows as its own
    bucket, never folded into a neighbour.

Part-writer decisions (part 3, 2026-11-24, accepted by the controller):

12. **Trading-performance presets stay unwrapped in Plan A.** The spec's
    "Dashboard trading-performance toggles" are the Interval/Trades groups
    inside `sb-equity-candles`; the Today…All presets are converted to
    `sb-segmented` by §B9 (plan B2), so wrapping them now would add a caption
    B9 rewrites. V246-10 edits `equity-candles` and one line of
    `dashboard.spec.ts` instead.
13. **Group names contain their visible caption** (WCAG 2.5.3): "Unit" →
    "Units", "Candle timeframe" → "Candle interval", "Equity basis" →
    "Trades counted". The Analytics custom date range (shown only for
    "Custom…") has no caption of its own; Benchmark mode's range reads "Range".
14. **`FIELD_GATE_ALLOWLIST` is measured, not copied:** today it holds only
    `research/research.ts`; a stale entry fails the gate. The gate checks
    `sb-control-bar`, `sb-toolbar` and `sb-control-row align="end"`; an
    `sb-control-row` holding an `sb-field` must set `align="end"`.
15. **Text items in field bars align on `last baseline`** (`.scope-line`,
    equity `.controls/.readout`), so text sits on the controls' text line,
    not the caption's.

Controller decisions (part 4, 2026-11-25):

16. **V246-13 split into V246-13 + V246-13b** (20 KB task cap); 19 tasks.
    `themedToken()` is a V246-12 export (`chartPalette()` reads through it);
    no `ChartPalette` field is added, so the two palette fixture specs stay
    untouched.
17. **Gallery gate:** `gallery.spec.ts` fails for any `ui/` `sb-` selector the
    Gallery does not render. V246-3 gains Step 6b (an `sb-field` exhibit) and
    V246-13 adds the `sb-time-series` exhibit; part-5 writers check this for
    any new `ui/` selector.

Controller decisions (part 5, 2026-11-25):

18. **V246-16 split into V246-16 + V246-16b**; 20 ledger rows, the cap. The
    stray `)` is inferred from lightweight-charts source (a half-cut edge
    tick label); V246-16b confirms it in Chromium first and fixes it with
    `timeScale.fixLeftEdge: true` (no drag past the oldest loaded candle;
    paging still fires). Any other source returns BLOCKED.
19. **Visible changes accepted as spec-following:** V246-15 plots drawdown in
    R in every unit (fixes R printed as € today); V246-16 hides the
    last-value tag below 640px (the balance above shows it); V246-17 single-series
    `sb-line-chart` → `--accent`, histogram/bar-list labels →
    `--text-secondary`, sparkline stroke 1px.
20. **`maxDrawdown()` starts its peak at 0 (d04e2b46, accepted 2026-11-25).**
    Cumulative P&L is 0 before the first close, matching the server's
    `drawdown_r` (`peak = 0.0` in `page_bodies.py`), so a scope whose first
    close is a loss reports it as drawdown. This changes the Max drawdown
    tile's money line and the V246-15 header; a spec pins it.
