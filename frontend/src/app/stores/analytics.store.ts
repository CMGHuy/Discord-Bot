import { computed, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { routeRequest } from '../routing/route-request';
import { Observable } from 'rxjs';
import {
  AnalyticsByDimension,
  AnalyticsCalibration,
  AnalyticsEquityCurve,
  AnalyticsExitQuality,
  AnalyticsDerived,
  AnalyticsHeatGrid,
  AnalyticsJournal,
  AnalyticsPerformance,
  AnalyticsPlans,
  AnalyticsStrategies,
  AnalyticsUnit,
  BookScope,
  HoldingBucket,
} from '../api/models';
import { HistogramBin } from '../ui/histogram';
import { BarRow } from '../ui/bar-list';
import { PreferencesStore } from './preferences.store';

/* -- row shapes ---------------------------------------------------------
 *
 * `models.ts` types the Analytics envelopes but leaves their rows as
 * `unknown[]` / `Record<string, unknown>`, because the API surface was built
 * before anything rendered these payloads and there was nothing to hold it
 * honest. The row types live HERE rather than being pushed back into
 * `models.ts` for one reason: this is the only file that reads them, and a
 * shape nobody reads is a shape that drifts from the server silently. Each
 * one below is copied from the Flask handler that produces it --
 * `swingbot/admin/api_v1/analytics.py`, `swingbot/admin/api_v1/jobs.py`,
 * `swingbot/admin/pages.py::_registry_rows` and
 * `swingbot/core/analytics/calibration.py` -- and the store narrows into them
 * at exactly one place per payload, so a server change breaks one cast rather
 * than fifteen template expressions.
 */

/** One row of `_registry_rows()`: the committed out-of-sample badge for a
 *  strategy, joined against how that strategy is actually doing live. */
export interface StrategyRow {
  strategy: string;
  /** `VALIDATED` or `WEAK` — whether it cleared its one-shot OOS bar. */
  status: string;
  /** OOS sample and result, from the committed validation registry. */
  n: number;
  win_rate: number;
  expectancy_r: number;
  window: string | null;
  run_date: string | null;
  /** Live counterparts. Null until there are closed trades to measure. */
  live_n: number | null;
  live_wr: number | null;
  delta_vs_oos: number | null;
  /** Pre-registered decay rule: live_n >= 20 and live_wr < oos_wr - 10. */
  decayed: boolean;
  /** Age of the evidence itself, derived server-side from `run_date` at read
   *  time and never stored: `fresh` | `aging` | `stale` | `unknown`. A
   *  different fact from `decayed` above, which is live-vs-OOS win-rate drift.
   *  Display only — nothing is gated on it. */
  evidence_decay: string;
  gate_description: string | null;
  /** Rolling 10-trade win rate, oldest first. Carries nulls for windows the
   *  server could not compute, which the sparkline cannot plot. */
  win_rate_series: (number | null)[];
}

export interface HeatmapCell {
  strategy: string;
  horizon: string;
  n: number | null;
  win_rate: number | null;
}

/** The strategy × horizon matrix, flattened. The server sends explicit cells
 *  plus both axes rather than a nested object, because the Python matrix is
 *  keyed by a tuple that JSON cannot express — see `_json_heatmap`. */
export interface Heatmap {
  strategies: string[];
  horizons: string[];
  cells: HeatmapCell[];
}

export interface DecileRow {
  decile: string;
  n: number;
  win_rate: number | null;
  expectancy_r: number | null;
}

export interface TierRow {
  level: number;
  n: number;
  win_rate: number | null;
  expectancy_r: number | null;
  /** Three-valued on purpose. `null` means "not enough live data to judge"
   *  (n < 10), which is a completely different statement from `false`
   *  ("judged, and it missed its band"). Rendering them the same way would
   *  turn "we don't know yet" into "it is broken". */
}

export interface DriftRow {
  strategy: string;
  oos_n: number;
  oos_wr: number;
  live_n: number;
  live_wr: number | null;
  delta_wr: number | null;
  drift_alert: boolean;
}

/** `get_stats()` for one confidence level, with the level attached. */
export interface ConfidenceRow {
  level: number;
  total: number;
  open: number;
  closed: number;
  wins: number;
  losses: number;
  win_rate: number | null;
}

export interface JobSummary {
  id: string;
  kind: string;
  state: string;
  started_at: string;
  finished_at: string | null;
  returncode: number | null;
}

/** `GET /jobs/:id` — a summary plus the last 50 log lines. */
export interface JobStatus extends JobSummary {
  log_tail: string;
}

export interface ProposalRow {
  filename: string;
  strategy: string;
  created_at: string;
  job_id: string;
  proposed_params: Record<string, unknown>;
  current_params: Record<string, unknown>;
  train_stats: Record<string, unknown>;
}

/* -- the six relocated metrics ------------------------------------------ */

/**
 * The six figures spec 3 moved out of the Dashboard header and spec v14
 * Decision 6 puts on Analytics → Performance.
 *
 * **This constant is the whole point of the relocation being auditable.**
 * The spec is blunt about it: "they must actually appear here; spec 3
 * accepted the cost of moving them, not of losing them." A hand-written list
 * of six template rows can lose one to a typo and nobody notices for months,
 * because a missing metric looks exactly like a metric that has no value yet.
 * Driving the render from this array — and checking the payload against it
 * (see `missingRelocated`) — makes a lost metric a visible defect instead.
 *
 * The keys match `analytics_performance()`'s `relocated` block verbatim.
 */
export const RELOCATED_METRICS = [
  { key: 'wins', label: 'Wins', unit: '', decimals: 0 },
  { key: 'losses', label: 'Losses', unit: '', decimals: 0 },
  { key: 'avg_realized_pct', label: 'Avg realised', unit: '%', decimals: 2 },
  { key: 'best_trade_pct', label: 'Best trade', unit: '%', decimals: 2 },
  { key: 'worst_trade_pct', label: 'Worst trade', unit: '%', decimals: 2 },
  { key: 'avg_holding_days', label: 'Avg holding', unit: 'd', decimals: 1 },
] as const;

/** One relocated metric, resolved against the payload and ready to render. */
export interface RelocatedMetric {
  key: string;
  label: string;
  unit: string;
  decimals: number;
  value: number | null;
  /** Green/red is P&L direction only, so only the three percentage metrics
   *  that ARE P&L may carry it. A count of wins is not money. */
  pnl: boolean;
}

const PNL_METRICS = new Set(['avg_realized_pct', 'best_trade_pct', 'worst_trade_pct']);

/* -- SR54: the derived figures ------------------------------------------ */

/**
 * The twelve figures `stats.html` derived in browser JS, now served.
 *
 * Same rationale as `RELOCATED_METRICS`: driving the render off one array
 * makes a lost figure a visible defect rather than a card that quietly stops
 * appearing. `decimals` is per-metric because these have genuinely different
 * scales — a Calmar of 1.2 and a volatility of 34.6% should not be rounded
 * the same way, and an expectancy of 0.08R disappears at one decimal.
 */
export const DERIVED_METRICS = [
  { key: 'total_return_pct', label: 'Total return', unit: '%', decimals: 2, pnl: true },
  { key: 'annualised_return_pct', label: 'Annualised', unit: '%', decimals: 2, pnl: true },
  { key: 'avg_win_pct', label: 'Avg win', unit: '%', decimals: 2, pnl: true },
  { key: 'avg_loss_pct', label: 'Avg loss', unit: '%', decimals: 2, pnl: true },
  { key: 'win_rate', label: 'Win rate', unit: '%', decimals: 1, pnl: false },
  { key: 'expectancy_r', label: 'Expectancy', unit: 'R', decimals: 3, pnl: true },
  { key: 'sharpe_ann', label: 'Sharpe (ann)', unit: '', decimals: 2, pnl: false },
  { key: 'sortino_ann', label: 'Sortino (ann)', unit: '', decimals: 2, pnl: false },
  { key: 'calmar', label: 'Calmar', unit: '', decimals: 2, pnl: false },
  { key: 'volatility_ann_pct', label: 'Volatility (ann)', unit: '%', decimals: 1, pnl: false },
  { key: 'trades_per_month', label: 'Trades / month', unit: '', decimals: 1, pnl: false },
  { key: 'pct_in_market', label: '% in market', unit: '%', decimals: 1, pnl: false },
] as const satisfies readonly {
  key: keyof AnalyticsDerived;
  label: string;
  unit: string;
  decimals: number;
  pnl: boolean;
}[];

/** One derived figure, resolved against the payload and ready to render. */
export interface DerivedMetric {
  key: keyof AnalyticsDerived;
  label: string;
  unit: string;
  decimals: number;
  /** Whether green/red P&L colouring applies. A Sharpe is not money. */
  pnl: boolean;
  value: number | null;
}

/** Every figure null — what the cards show before the first response, and
 *  what an empty date range legitimately returns. The two look identical on
 *  purpose: both mean "no number to show", not "the number is zero". */
const EMPTY_DERIVED: AnalyticsDerived = {
  avg_win_pct: null, avg_loss_pct: null, total_return_pct: null,
  annualised_return_pct: null, calmar: null, volatility_ann_pct: null,
  trades_per_month: null, pct_in_market: null, sharpe_ann: null,
  sortino_ann: null, win_rate: null, expectancy_r: null,
};

/** A payload number, or null. Not `Number(value)`: the endpoint returns JSON
 *  `null` for "no closed trades yet", and coercing that to 0 would report a
 *  best trade of exactly break-even on a fresh install. */
function numberOrNull(record: Record<string, unknown> | undefined, key: string): number | null {
  const value = record?.[key];
  return typeof value === 'number' ? value : null;
}

/* -- the store ---------------------------------------------------------- */

/** The six questions, in the order a trader asks them (spec v94 D1).
 *  Calibration folded into Edge; Performance split into Overview,
 *  Attribution and Execution. Tabs, not sub-navigation: a second level of
 *  nav inside one of six workspaces reintroduces exactly the depth the IA
 *  change removed. */
export type AnalyticsTab = 'overview' | 'attribution' | 'execution' | 'edge' | 'pipeline' | 'tuning';

export const ANALYTICS_TABS: readonly AnalyticsTab[] =
  ['overview', 'attribution', 'execution', 'edge', 'pipeline', 'tuning'] as const;

/** Old `?tab=` values keep working (spec D1). A bookmark or a Discord link
 *  posted before v94 lands on the tab that now answers its question rather
 *  than silently on Overview. */
export const LEGACY_TABS: Record<string, AnalyticsTab> = {
  performance: 'overview', strategies: 'edge', calibration: 'edge', plans: 'pipeline', tuning: 'tuning',
};

/** Every panel that can fail on its own terms, and therefore be retried on
 *  its own (spec v94 H4). */
export type PanelKey =
  | 'performance' | 'equityCurve' | 'byDimension' | 'heatGrid' | 'exitQuality'
  | 'journal' | 'strategies' | 'calibration' | 'plans';

export const DEFAULT_SCOPE: BookScope = {
  from: null, to: null, ledger: 'main', strategy: null, horizon: null, direction: null,
};

/** Common range shortcuts used by the v94 scope bar.  The value, rather than
 * the label, is deliberately what the URL control persists. */
export const RANGE_PRESETS = [
  { value: '30d', label: 'Last 30 days', days: 30 },
  { value: '90d', label: 'Last 90 days', days: 90 },
  { value: 'ytd', label: 'Year to date', days: null },
  { value: 'all', label: 'All time', days: null },
] as const;

const isoDate = (date: Date): string => date.toISOString().slice(0, 10);

/** Resolve a named preset against an explicit day, keeping this calculation
 * deterministic for tests and independent of the browser's time zone. */
export function presetRange(preset: string, today: Date): { from: string | null; to: string | null } {
  if (preset === 'all') return { from: null, to: null };
  if (preset === 'ytd') return { from: `${today.getUTCFullYear()}-01-01`, to: isoDate(today) };
  const days = RANGE_PRESETS.find((entry) => entry.value === preset)?.days;
  if (!days) return { from: null, to: null };
  const from = new Date(today);
  from.setUTCDate(from.getUTCDate() - (days - 1));
  return { from: isoDate(from), to: isoDate(today) };
}

/* -- row shapes the scoped payloads share ---------------------------------
 *
 * v94 retired `GET /analytics/snapshot` as this store's source: every panel
 * now reads a scoped endpoint instead, so there is no pre-built all-time blob
 * to narrow. The shapes below survive because the scoped payloads reuse them
 * (`aggregate.py`'s `StatRow` in particular), and every narrower still returns
 * null rather than 0 for anything it cannot read — `ui/format.ts`'s rule, and
 * the difference between "we don't know" and "it is zero" on a Sharpe ratio.
 */

/** One `StatRow` out of a `by`-dimension block (`aggregate.py:47-57`). */
export interface BreakdownRow {
  key: string;
  n: number | null;
  wins: number | null;
  losses: number | null;
  win_rate: number | null;
  expectancy_r: number | null;
  avg_r: number | null;
  profit_factor: number | null;
  total_pnl: number | null;
  total_r: number | null;
}


export interface Streaks {
  current: number | null;
  currentKind: string | null;
  bestWin: number | null;
  worstLoss: number | null;
}

/** Every dimension `aggregate.DIMENSIONS` serves, including v93's ledger.
 *  `tier` stays retired -- it would 400. */
export const BREAKDOWN_DIMENSIONS = [
  { value: 'strategy', label: 'Strategy' },
  { value: 'horizon', label: 'Horizon' },
  { value: 'direction', label: 'Direction' },
  { value: 'dow', label: 'Day of week' },
  { value: 'month', label: 'Month' },
  { value: 'badge', label: 'Badge' },
  { value: 'confidence', label: 'Confidence' },
  { value: 'source', label: 'Source' },
  { value: 'ledger', label: 'Ledger' },
  { value: 'ticker', label: 'Ticker' },
] as const;

export type BreakdownDimension = (typeof BREAKDOWN_DIMENSIONS)[number]['value'];

function snapNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Per-trade R, derived from consecutive `cum_r` deltas -- R9-01's endpoint
 *  gives a running total, not a per-trade figure, and this is the one place
 *  both the win/loss donut and its avg-R captions (D39, R9-04) read that
 *  derivation from, so the two cannot drift on how a "win" is decided. */
function perTradeRs(curve: AnalyticsEquityCurve | null): number[] {
  const points = curve?.points ?? [];
  let prev = 0;
  return points.map((p) => {
    const r = p.cum_r - prev;
    prev = p.cum_r;
    return r;
  });
}

export function rateOrWithheld(n: number, rate: number | null | undefined, floor: number): { count: number; withheld: boolean } {
  if (n < floor || rate == null) return { count: 0, withheld: true };
  return { count: rate, withheld: false };
}

export function zeroFilledBars(rows: BreakdownRow[], order: readonly (readonly [string, string])[], floor: number): BarRow[] {
  const byKey = new Map(rows.map((row) => [row.key, row]));
  return order.map(([key, label]) => {
    const row = byKey.get(key);
    const n = row?.n ?? 0;
    const value = rateOrWithheld(n, row?.win_rate, floor);
    return { label, value: value.withheld ? null : value.count, n, withheld: value.withheld };
  });
}

export function rateBars(buckets: readonly HoldingBucket[]): BarRow[] {
  return buckets.map((bucket) => ({ label: bucket.bucket, value: bucket.win_rate, n: bucket.n, withheld: bucket.win_rate === null }));
}

export function monthBars(rows: readonly { month: string; return_pct: number | null; n: number }[]): BarRow[] {
  return rows.map((row) => ({ label: row.month, value: row.return_pct, n: row.n }));
}
/** One histogram bin. */
export interface Bin {
  label: string;
  count: number;
}

/**
 * R-multiples binned at 0.5R.
 *
 * Bins rather than the raw list because the shape is the point: a healthy edge
 * is a cluster of small losses and a tail of larger wins, and that is a
 * statement about a distribution, not about any one trade. Clamped at ±5R so a
 * single outlier cannot flatten every other bin to invisibility.
 */
export function binRMultiples(values: number[], width = 0.5): Bin[] {
  if (!values.length) return [];
  const LIMIT = 5;
  const counts = new Map<number, number>();
  for (const value of values) {
    const clamped = Math.max(-LIMIT, Math.min(LIMIT, value));
    const bin = Math.floor(clamped / width) * width;
    counts.set(bin, (counts.get(bin) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([bin, count]) => ({
      label: `${bin > 0 ? '+' : ''}${bin.toFixed(1)}R`,
      count,
    }));
}

/**
 * One row of a tuning grid (SR51).
 *
 * `passes` and `row_index` are both computed server-side and carried on the
 * row. The acceptance bar is four conditions and it is the same bar
 * `scripts/backtest/tune_strategy.py` prints, so restating it here would be a second
 * definition that could disagree; the index is what `POST /proposals`
 * identifies a row by, and inferring it from array position would break the
 * moment anything sorted the table.
 */
export interface GridRow {
  row_index: number;
  params: Record<string, unknown>;
  paramLabel: string;
  n_eval: number | null;
  win_rate: number | null;
  expectancy_r: number | null;
  excluded_share: number | null;
  passes: boolean;
}

function toGridRows(raw: unknown[]): GridRow[] {
  return raw.flatMap((row, index) => {
    if (!isPlainRecord(row)) return [];
    const params = isPlainRecord(row['params']) ? row['params'] : {};
    return [{
      // The server's index if it sent one; the array position only as a
      // fallback, so a hand-written fixture still works.
      row_index: snapNumber(row['row_index']) ?? index,
      params,
      // Flattened once here rather than in the template: a cell that iterated
      // an object would be asserting the wire format.
      paramLabel: Object.entries(params)
        .map(([key, value]) => `${key}=${value}`)
        .join(', '),
      n_eval: snapNumber(row['n_eval']),
      win_rate: snapNumber(row['win_rate']),
      expectancy_r: snapNumber(row['expectancy_r']),
      excluded_share: snapNumber(row['excluded_share']),
      passes: row['passes'] === true,
    }];
  });
}

interface AnalyticsSlice {
  /** Which tab is open, projected from the URL's `?tab=`. Held here rather
   *  than in the component because it decides what gets fetched. */
  tab: AnalyticsTab;
  /** v94 D2: the ONE scope every scoped panel is fetched against. One state,
   *  one URL, one population — see `scopeN`. */
  scope: BookScope;
  unit: AnalyticsUnit;
  measure: 'exp_r' | 'total_r' | 'win_rate';
  /** Which figure the Attribution heat grid paints its cells with. */
  heatCell: 'exp_r' | 'win_rate' | 'n';
  /** Which dimension the Attribution breakdown is grouped by. */
  breakdown: string;
  /** Which panels' underlying tables the user has opened, by panel key. */
  tableOpen: Record<string, boolean>;

  /* Every panel is its own payload and its own error (spec v94 H4): a failed
   * fetch may never blank, or warn about, a neighbour that arrived fine. */
  performance: AnalyticsPerformance | null;   performanceError: string | null;
  equityCurve: AnalyticsEquityCurve | null;   equityCurveError: string | null;
  byDimension: AnalyticsByDimension | null;   byDimensionError: string | null;
  heatGrid: AnalyticsHeatGrid | null;         heatGridError: string | null;
  exitQuality: AnalyticsExitQuality | null;   exitQualityError: string | null;
  journal: AnalyticsJournal | null;           journalError: string | null;
  strategies: AnalyticsStrategies | null;     strategiesError: string | null;
  calibration: AnalyticsCalibration | null;   calibrationError: string | null;
  plans: AnalyticsPlans | null;               plansError: string | null;

  /** SR51 — the tracked job's grid, one row per parameter combination.
   *  Empty while it is still running, which the endpoint answers with a 200
   *  rather than a 404 so this never has to mean "something failed". */
  gridStrategy: string | null;
  grid: GridRow[];
  /** The row currently being staged, by index — so only its own button shows
   *  a pending state rather than the whole table going quiet. */
  proposing: number | null;
  proposeError: string | null;
  proposeResult: string | null;
  jobs: JobSummary[];
  /** The job whose progress is on screen — status plus a log tail. */
  job: JobStatus | null;
  proposals: ProposalRow[];

  loading: boolean;
  error: string | null;
  /** Kept apart from `error`: a failed launch is about the button that was
   *  just pressed, and showing it in the same place as "the admin is not
   *  responding" makes an actionable message look like a stale-data warning. */
  launching: boolean;
  launchError: string | null;
}

/**
 * Analytics — Overview, Attribution, Execution, Edge, Pipeline and Tuning
 * behind one `TabBar` (spec v94 D1).
 *
 * Follows `DashboardStore`'s shape: one server response per concern in, all
 * derivation in `withComputed`. Three things are specific to this workspace
 * and are the reason it is not six copies of the Dashboard store:
 *
 * **One scope, every panel.** v94 D2: `scope` is a single `BookScope` and
 * every scoped request is issued against it, so no two panels on one screen
 * can be answering about different populations. `scopeN()` reports the
 * population that scope actually produced, server-side, never inferred from
 * a chart's visible rows.
 *
 * **Only the open tab is fetched.** Spec v12's taxonomy says an `analytics`
 * event means "refetch the open Analytics view", not "refetch all six".
 * `LOADERS` reads `tab` and dispatches, so switching tabs is what triggers a
 * fetch — and a tab that has already loaded keeps its data on screen while
 * the next one arrives, rather than six payloads racing on entry.
 *
 * **Tuning listens to `jobs`, the other five to `analytics`.** This is the
 * bullet NG48 exists for: the Jinja page drove job progress with a 3-second
 * `setTimeout` poll and a full `window.location.reload()` on completion.
 * Here the server's watcher on `admin_jobs.json` and `tuning_results/` raises
 * `jobs`, the route refetches `GET /jobs/:id`, and the log tail and state
 * pill update in place. **There is deliberately no timer anywhere in this
 * file** — if one reappears, the polling came back.
 */
export const AnalyticsStore = signalStore(
  /* A factory, not a literal, for one reason: the remembered unit, measure
   * and scope have to be in place BEFORE the route resolver runs, and the
   * resolver's own `hydrate(scope, unit)` then overrides them from the URL.
   * The URL wins where it speaks; the preference answers where it is
   * silent. */
  withState<AnalyticsSlice>(() => {
    const preferences = inject(PreferencesStore).values();
    return {
      tab: 'overview',
      scope: { ...DEFAULT_SCOPE, ...(preferences.analyticsScope ?? {}) },
      unit: preferences.analyticsUnit ?? 'r',
      measure: preferences.analyticsMeasure ?? 'exp_r',
      heatCell: 'exp_r',
      breakdown: 'strategy',
      tableOpen: {},
      performance: null, performanceError: null,
      equityCurve: null, equityCurveError: null,
      byDimension: null, byDimensionError: null,
      heatGrid: null, heatGridError: null,
      exitQuality: null, exitQualityError: null,
      journal: null, journalError: null,
      strategies: null, strategiesError: null,
      calibration: null, calibrationError: null,
      plans: null, plansError: null,
      gridStrategy: null,
      grid: [],
      proposing: null,
      proposeError: null,
      proposeResult: null,
      jobs: [],
      job: null,
      proposals: [],
      loading: false,
      error: null,
      launching: false,
      launchError: null,
    };
  }),

  withComputed(({ performance, strategies, calibration, plans, jobs, job, breakdown, exitQuality,
                 journal, equityCurve, byDimension, scope, tab }) => ({
    /** The server-side population the ONE scope produced, never inferred from
     * a chart's visible rows. Read off whichever scoped payload this tab
     * actually fetched — every one of them echoes the same `n` for the same
     * scope, so the fallback chain cannot report two different populations. */
    scopeN: computed(() =>
      performance()?.n ?? byDimension()?.n ?? exitQuality()?.n ?? null),
    /** When the figures on screen were built. A screen that hides how stale
     *  its data is has a correctness bug. */
    asOf: computed(() => equityCurve()?.as_of ?? byDimension()?.as_of ?? null),
    /** A scope is shareable precisely because every non-default filter is
     * explicit. Ledger counts only when it differs from the default book. */
    activeFilterCount: computed(() => {
      const selected = scope();
      return (['from', 'to', 'strategy', 'horizon', 'direction'] as const)
        .filter((key) => selected[key]).length +
        (selected.ledger === DEFAULT_SCOPE.ledger ? 0 : 1);
    }),
    /** How many panels on the open tab ignore the bar (spec v94 D2/H2).
     *  Edge's registry/calibration evidence and every Pipeline panel are
     *  all-time by construction; saying so is the difference between a
     *  scoped screen and one that lies about being scoped. */
    allTimePanelCount: computed(() => (tab() === 'edge' ? 3 : tab() === 'pipeline' ? 4 : 0)),

    /** Served by the backend: the SPA never owns the suppression threshold. */
    minCellN: computed(() => exitQuality()?.min_cell_n ?? 0),

    /* -- the equity curve ------------------------------------------------ */

    equityCurveEmpty: computed(() => (equityCurve()?.points.length ?? 0) === 0),
    equityCurveAsOf: computed(() => equityCurve()?.as_of ?? null),

    /** Null (not 0) when there is no win/loss of that sign yet -- an empty
     *  average is not a zero-R one. */
    avgWinR: computed(() => {
      const wins = perTradeRs(equityCurve()).filter((r) => r > 0);
      return wins.length ? wins.reduce((sum, r) => sum + r, 0) / wins.length : null;
    }),
    avgLossR: computed(() => {
      const losses = perTradeRs(equityCurve()).filter((r) => r < 0);
      return losses.length ? losses.reduce((sum, r) => sum + r, 0) / losses.length : null;
    }),

    breakdownLabel: computed(
      () =>
        BREAKDOWN_DIMENSIONS.find((d) => d.value === breakdown())?.label ??
        breakdown(),
    ),

    /* -- performance --------------------------------------------------- */

    winRate: computed(() => performance()?.win_rate ?? null),
    winRateN: computed(() => performance()?.win_rate_n ?? null),
    expectancyR: computed(() => performance()?.expectancy_r ?? null),
    expectancyN: computed(() => performance()?.expectancy_n ?? null),

    /* -- SR54: the figures that used to be derived in the browser -------- */

    /**
     * The derived block, or an all-null one before the first response.
     *
     * All-null rather than `null` so the KPI grid renders its cards with em
     * dashes on first paint instead of collapsing and then reflowing when the
     * payload lands. `DERIVED_METRICS` drives the render off this, the same
     * pattern (and for the same auditability reason) as `RELOCATED_METRICS`.
     */
    derived: computed<AnalyticsDerived>(
      () => performance()?.derived ?? EMPTY_DERIVED),

    /** Server buckets mapped onto `sb-histogram`'s `{label, count}` contract.
     *  The label is the bucket's LOWER edge, which is what makes the default
     *  "starts with a minus sign means loss" predicate correct — labelling by
     *  midpoint would mark the bucket straddling zero as a win. */
    returnsHistogram: computed<HistogramBin[]>(() =>
      (performance()?.distributions?.returns ?? []).map((bucket) => ({
        label: `${bucket.lo.toFixed(1)}%`,
        count: bucket.count,
      }))),

    rHistogram: computed<HistogramBin[]>(() =>
      (performance()?.distributions?.r_multiples ?? []).map((bucket) => ({
        label: `${bucket.lo.toFixed(2)}R`,
        count: bucket.count,
      }))),
    calendarReturns: computed(() => performance()?.calendar ?? []),

    holdingPeriodBars: computed(() => rateBars(performance()?.holding_period_split ?? [])),
    riskRewardBars: computed(() => rateBars(performance()?.risk_reward_split ?? [])),
    monthBars: computed(() => monthBars(performance()?.calendar ?? [])),

    /* -- SR55: the journal's analytics half ----------------------------- */

    digest: computed<string[]>(() => journal()?.digest ?? []),
    lessons: computed<string[]>(() => journal()?.lessons ?? []),

    /** Entries behind the two lists above. Shown with them: a digest drawn
     *  from three entries and one drawn from three hundred read very
     *  differently, and neither list says so on its own. */
    journalEntryCount: computed(() => journal()?.entries_n ?? 0),

    /** True once the endpoint has answered with nothing to say — distinct
     *  from "has not answered yet", which must not render as "no lessons". */
    journalEmpty: computed(() => {
      const data = journal();
      return data !== null && data.digest.length === 0 && data.lessons.length === 0;
    }),

    totals: computed(() => {
      const block = performance()?.totals as Record<string, unknown> | undefined;
      return {
        total: numberOrNull(block, 'total'),
        open: numberOrNull(block, 'open'),
        closed: numberOrNull(block, 'closed'),
      };
    }),

    /** `get_stats_by_confidence()` is an object keyed by level 1–5, which
     *  JSON turns into string keys. Flattened into rows here so the table
     *  never iterates object keys and never has to sort them back into
     *  numeric order — "10" would sort before "2" if a sixth level appeared. */
    byConfidence: computed<ConfidenceRow[]>(() => {
      const block = performance()?.by_confidence as Record<string, unknown> | undefined;
      if (!block) return [];
      return Object.entries(block)
        .map(([level, stats]) => {
          const row = (stats ?? {}) as Record<string, unknown>;
          return {
            level: Number(level),
            total: numberOrNull(row, 'total') ?? 0,
            open: numberOrNull(row, 'open') ?? 0,
            closed: numberOrNull(row, 'closed') ?? 0,
            wins: numberOrNull(row, 'wins') ?? 0,
            losses: numberOrNull(row, 'losses') ?? 0,
            win_rate: numberOrNull(row, 'win_rate'),
          };
        })
        .sort((a, b) => a.level - b.level);
    }),

    /* -- strategies ---------------------------------------------------- */

    strategyRows: computed<StrategyRow[]>(
      () => (strategies()?.strategies ?? []) as StrategyRow[],
    ),

    /* -- calibration --------------------------------------------------- */

    deciles: computed<DecileRow[]>(() => (calibration()?.deciles ?? []) as DecileRow[]),
    tiers: computed<TierRow[]>(() => (calibration()?.levels ?? []) as TierRow[]),
    drift: computed<DriftRow[]>(() => (calibration()?.drift ?? []) as DriftRow[]),

    /* -- tuning -------------------------------------------------------- */

    /** True while a tuning job is queued or running. The launch form is
     *  hidden then, because the server allows exactly one job at a time and
     *  a second press returns a 409 — better not to offer it. */
    jobActive: computed(() => {
      const state = job()?.state;
      return state === 'running' || state === 'queued';
    }),

    /** Every job except the one whose progress is already displayed, so the
     *  history list does not repeat the card above it. */
    pastJobs: computed(() => {
      const current = job()?.id;
      return jobs().filter((entry) => entry.id !== current);
    }),

    /* -- plans ----------------------------------------------------------- */

    funnelChart: computed<HistogramBin[]>(() => {
      const f = plans()?.funnel;
      if (!f) return [];
      return [
        { label: 'Posted', count: f.posted },
        { label: 'Filled', count: f.filled },
        { label: 'Hit TP1', count: f.hit_tp1 },
        { label: 'Closed', count: f.closed },
      ];
    }),
    fillRatePct: computed(() => plans()?.fill_rate.fill_rate_pct ?? null),
    medianDaysToFill: computed(() => plans()?.fill_rate.median_days_to_fill ?? null),
    inFlight: computed(() => plans()?.in_flight ?? 0),
    badgeChart: computed<HistogramBin[]>(() =>
      Object.entries(plans()?.badges ?? {}).map(([label, count]) => ({ label, count }))),
    tierChart: computed<HistogramBin[]>(() =>
      Object.entries(plans()?.tiers ?? {})
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([label, count]) => ({ label, count }))),
  })),

  withComputed(({ deciles }) => ({
    /** A decile with no closed trades yet has `win_rate: null` -- omitted
     *  rather than charted as 0, which would read as "this decile loses
     *  every time" instead of "not enough data yet". */
    decileHistogram: computed<HistogramBin[]>(() =>
      deciles()
        .filter((d): d is typeof d & { win_rate: number } => d.win_rate !== null)
        .map((d) => ({ label: d.decile, count: d.win_rate }))),
  })),

  withMethods((store, api = inject(ApiClient), preferences = inject(PreferencesStore)) => {
    /** Every failure lands here, and none of them clear the data already on
     *  screen. A table that empties because one refetch failed is worse than
     *  a slightly stale one beside a warning — especially when the event
     *  stream reconnects seconds later. */
    const fail = (error: ApiError): void =>
      patchState(store, {
        loading: false,
        error: message(error),
      });

    /* -- one error handler per panel (spec v94 H4) ----------------------
     *
     * A failed fetch sets THAT panel's error and leaves its neighbours' data
     * untouched. The three silent-degradation paths v94 exists to remove are
     * the ones that had no error field at all -- a panel that fails without
     * saying so is indistinguishable from one measuring an empty book.
     */

    const message = (error: ApiError): string =>
      error.code === 'unavailable' ? 'The admin is not responding.' : error.message;

    const panelFail = (errorKey: string) => (error: ApiError): void =>
      patchState(store, { [errorKey]: message(error) } as never);

    const fetchPanel = <T>(source: Observable<T>, dataKey: string, errorKey: string): void => {
      source.subscribe({
        next: (value) => patchState(store, { [dataKey]: value, [errorKey]: null } as never),
        error: panelFail(errorKey),
      });
    };

    /** The one scope every scoped request is issued against (v94 D2). */
    const s = (): BookScope => store.scope();

    /* -- per-tab loaders -------------------------------------------------
     *
     * Each tab fetches exactly the payloads its own panels read, and nothing
     * else: `/performance` appears in four of them because four tabs read a
     * different part of it (the KPI row, the horizon/dow/month bars, the
     * holding-period and R:R splits, the rolling series), not because it is
     * a catch-all. */

    const loadOverview = (): void => {
      fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
      fetchPanel(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError');
    };
    const loadAttribution = (): void => {
      fetchPanel(api.analyticsByDimension(store.breakdown(), s()), 'byDimension', 'byDimensionError');
      fetchPanel(api.analyticsHeatGrid(s()), 'heatGrid', 'heatGridError');
      fetchPanel(api.analyticsStrategies(s()), 'strategies', 'strategiesError');
      fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
    };
    const loadExecution = (): void => {
      fetchPanel(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError');
      fetchPanel(api.analyticsJournal(s()), 'journal', 'journalError');
      fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
    };
    const loadEdge = (): void => {
      fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
      fetchPanel(api.analyticsStrategies(s()), 'strategies', 'strategiesError');
      fetchPanel(api.analyticsCalibration(), 'calibration', 'calibrationError');
    };
    const loadPipeline = (): void => fetchPanel(api.analyticsPlans(), 'plans', 'plansError');

    /** The registry list the Tuning launcher offers. Sourced from the server
     *  rather than hardcoded: it whitelists the strategy against
     *  `ALL_STRATEGIES` and 400s on anything else. */
    const loadStrategies = (): void =>
      fetchPanel(api.analyticsStrategies(s()), 'strategies', 'strategiesError');

    const loadProposals = (): void => {
      api.proposals().subscribe({
        next: (list) =>
          patchState(store, {
            proposals: (list.proposals ?? []) as ProposalRow[],
            error: null,
          }),
        error: fail,
      });
    };

    /**
     * Which job's progress to show: the one that is actually working, and
     * otherwise the most recent.
     *
     * Falling back to the newest finished job is deliberate. The Jinja page
     * reloaded the whole window the moment a job left `running`, which threw
     * away the log the user was reading at precisely the moment it became
     * interesting — a failed grid's traceback is in the last few lines.
     * `job_manager.all()` already sorts newest-first, so index 0 is that job.
     */
    const trackedJob = (jobs: JobSummary[]): JobSummary | null =>
      jobs.find((entry) => entry.state === 'running' || entry.state === 'queued') ??
      jobs[0] ??
      null;

    const loadJob = (id: string): void => {
      api.job(id).subscribe({
        next: (job) => patchState(store, { job: job as JobStatus, error: null }),
        error: fail,
      });

      // SR51. Fetched unconditionally rather than only for a finished job:
      // the endpoint answers 200 with an empty grid while one is still
      // running, and branching on state here would mean the results table
      // stayed blank for a job that finished between the two responses.
      api.jobResult(id).subscribe({
        next: (result) =>
          patchState(store, {
            gridStrategy: result.strategy,
            grid: toGridRows(result.grid ?? []),
          }),
        // Deliberately quiet. A missing result file is the ordinary state of a
        // running or failed job, and the panel renders nothing rather than
        // claiming an error the job's own state already explains.
        error: () => patchState(store, { grid: [], gridStrategy: null }),
      });
    };

    const loadTuning = (): void => {
      patchState(store, { loading: true });
      api.jobs().subscribe({
        next: (list) => {
          const jobs = (list.jobs ?? []) as JobSummary[];
          patchState(store, { jobs, loading: false, error: null });

          const tracked = trackedJob(jobs);
          if (tracked) loadJob(tracked.id);
          else patchState(store, { job: null });
        },
        error: fail,
      });

      loadProposals();

      // The launch form's strategy list comes from the registry, which the
      // Strategies tab already fetches. Only when it is missing: this runs on
      // every `jobs` event, and a running grid raises one per log flush --
      // refetching the whole registry each time would turn a progress update
      // into two payloads, one of which cannot have changed.
      if (store.strategies() === null) loadStrategies();
    };

    /**
     * One tab's route resolution: the route waits on the tab's FIRST payload
     * and the rest of its panels are fired alongside it.
     *
     * Waiting on all of them would hold the route open on the slowest, and
     * waiting on none would mount the page empty — the first payload is the
     * one the tab's headline panel reads, so the page is never shown before
     * the number it leads with exists.
     */
    const resolveOne = <T>(
      source: Observable<T>, dataKey: string, errorKey: string, rest: () => void = () => {},
    ): Observable<void> => routeRequest(source, {
      start: () => { patchState(store, { loading: true }); rest(); },
      next: (value) => patchState(store, {
        [dataKey]: value, [errorKey]: null, loading: false, error: null,
      } as never),
      error: (error: ApiError) => { fail(error); panelFail(errorKey)(error); },
    });

    const resolveOverview = (): Observable<void> =>
      resolveOne(api.analyticsPerformance(s()), 'performance', 'performanceError', () => {
        fetchPanel(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError');
      });

    const resolveAttribution = (): Observable<void> =>
      resolveOne(api.analyticsByDimension(store.breakdown(), s()), 'byDimension', 'byDimensionError', () => {
        fetchPanel(api.analyticsHeatGrid(s()), 'heatGrid', 'heatGridError');
        fetchPanel(api.analyticsStrategies(s()), 'strategies', 'strategiesError');
        fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
      });

    const resolveExecution = (): Observable<void> =>
      resolveOne(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError', () => {
        fetchPanel(api.analyticsJournal(s()), 'journal', 'journalError');
        fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError');
      });

    const resolveEdge = (): Observable<void> =>
      resolveOne(api.analyticsPerformance(s()), 'performance', 'performanceError', () => {
        fetchPanel(api.analyticsStrategies(s()), 'strategies', 'strategiesError');
        fetchPanel(api.analyticsCalibration(), 'calibration', 'calibrationError');
      });

    const resolvePipeline = (): Observable<void> =>
      resolveOne(api.analyticsPlans(), 'plans', 'plansError');

    const resolveTuning = (): Observable<void> => routeRequest(api.jobs(), {
      start: () => {
        patchState(store, { loading: true });
        loadProposals();
        if (store.strategies() === null) loadStrategies();
      },
      next: (list) => {
        const jobs = (list.jobs ?? []) as JobSummary[];
        patchState(store, { jobs, loading: false, error: null });
        const tracked = trackedJob(jobs);
        if (tracked) loadJob(tracked.id);
        else patchState(store, { job: null });
      },
      error: fail,
    });

    const RESOLVERS: Record<AnalyticsTab, () => Observable<void>> = {
      overview: resolveOverview, attribution: resolveAttribution, execution: resolveExecution,
      edge: resolveEdge, pipeline: resolvePipeline, tuning: resolveTuning,
    };

    const resolveTab = (tab: AnalyticsTab): Observable<void> => {
      patchState(store, { tab });
      return RESOLVERS[tab]();
    };

    const LOADERS: Record<AnalyticsTab, () => void> = {
      overview: loadOverview, attribution: loadAttribution, execution: loadExecution,
      edge: loadEdge, pipeline: loadPipeline, tuning: loadTuning,
    };

    const load = (): void => LOADERS[store.tab()]();

    return {
      /** The one way the tab arrives, and it comes from the URL. */
      setTab(tab: AnalyticsTab, loadNow = true): void {
        patchState(store, { tab });
        if (loadNow) load();
      },

      /**
       * Retry exactly the failed panel after `sb-panel-error` (spec v94 H4).
       *
       * One panel, one request: adjacent charts retain their current payload
       * and never flash back to an empty loading state because a neighbour
       * was retried.
       */
      reload(panel: PanelKey): void {
        const one: Record<PanelKey, () => void> = {
          performance: () => fetchPanel(api.analyticsPerformance(s()), 'performance', 'performanceError'),
          equityCurve: () => fetchPanel(api.analyticsEquityCurve(s()), 'equityCurve', 'equityCurveError'),
          byDimension: () => fetchPanel(api.analyticsByDimension(store.breakdown(), s()), 'byDimension', 'byDimensionError'),
          heatGrid: () => fetchPanel(api.analyticsHeatGrid(s()), 'heatGrid', 'heatGridError'),
          exitQuality: () => fetchPanel(api.analyticsExitQuality(s()), 'exitQuality', 'exitQualityError'),
          journal: () => fetchPanel(api.analyticsJournal(s()), 'journal', 'journalError'),
          strategies: () => fetchPanel(api.analyticsStrategies(s()), 'strategies', 'strategiesError'),
          calibration: () => fetchPanel(api.analyticsCalibration(), 'calibration', 'calibrationError'),
          plans: () => fetchPanel(api.analyticsPlans(), 'plans', 'plansError'),
        };
        one[panel]?.();
      },

      /** Which dimension the Attribution breakdown groups by. Unlike v85's
       *  snapshot-backed table this DOES refetch: `/by-dimension` serves one
       *  dimension per request, scoped, so the rows for another dimension
       *  are not already on hand. */
      setBreakdown(breakdown: string): void {
        patchState(store, { breakdown });
        fetchPanel(api.analyticsByDimension(breakdown, s()), 'byDimension', 'byDimensionError');
      },

      /**
       * v94 D2 — one shared scope feeds every scoped analytics request.
       *
       * The whole patch is applied in one call so a user picking a range
       * never triggers two requests, the second of which would race the
       * first and could land older numbers last.
       *
       * An out-of-order pair is normalised rather than rejected: a date
       * picker mid-edit legitimately passes through `from > to`, and
       * refusing it would surface an error for a state the user is about to
       * fix anyway.
       */
      setScope(patch: Partial<BookScope>): void {
        const next = { ...store.scope(), ...patch };
        if (next.from && next.to && next.from > next.to) [next.from, next.to] = [next.to, next.from];
        patchState(store, { scope: next });
        preferences.update((prefs) => ({ ...prefs, analyticsScope: next }));
        load();
      },
      /** Back to the default book, all-time. */
      clearScope(): void {
        patchState(store, { scope: DEFAULT_SCOPE });
        preferences.update((prefs) => ({ ...prefs, analyticsScope: DEFAULT_SCOPE }));
        load();
      },
      /** No refetch: every unit is already in the payload (spec v94 D3), so
       *  switching R/%/$ is a re-read of numbers already on screen. */
      setUnit(unit: AnalyticsUnit): void {
        patchState(store, { unit });
        preferences.update((prefs) => ({ ...prefs, analyticsUnit: unit }));
      },
      setMeasure(measure: 'exp_r' | 'total_r' | 'win_rate'): void {
        patchState(store, { measure });
        preferences.update((prefs) => ({ ...prefs, analyticsMeasure: measure }));
      },
      /** Which figure the heat grid paints. Local: the cells are all in the
       *  one `/heat-grid` payload. */
      setHeatCell(heatCell: 'exp_r' | 'win_rate' | 'n'): void {
        patchState(store, { heatCell });
      },
      /** Whether a panel's underlying table is open. Local, per panel. */
      setTableOpen(panel: string, open: boolean): void {
        patchState(store, { tableOpen: { ...store.tableOpen(), [panel]: open } });
      },
      /** Route resolvers hydrate before fetching; no request here. */
      hydrate(scope: BookScope, unit: AnalyticsUnit): void {
        patchState(store, { scope, unit });
      },

      resolveTab,
      load,
      loadTuning,

      /**
       * Launch a TRAIN-window grid search.
       *
       * No date argument is sent, and none can be: `build_tune_args` accepts
       * only `--strategy` and an optional `--be-trigger`, and asserts the
       * window is TRAIN. That firewall is what keeps the VALIDATION badges on
       * the Strategies tab meaningful, so the UI must not offer a way around
       * it — hence a strategy picker and nothing else.
       */
      startTune(strategy: string): void {
        patchState(store, { launching: true, launchError: null });
        api.startTuneJob({ strategy }).subscribe({
          next: () => {
            patchState(store, { launching: false });
            // One refetch, because the user just acted and expects to see the
            // job appear. Everything after this arrives on the `jobs` event.
            loadTuning();
          },
          error: (error: ApiError) =>
            patchState(store, {
              launching: false,
              launchError:
                error.code === 'conflict'
                  ? 'A job is already running — only one at a time.'
                  : error.message,
            }),
        });
      },

      /**
       * Stage one grid row as a proposal — SR51, the action that closes the
       * loop.
       *
       * Not an apply, and the server's own note says so: applying means
       * editing `entry_filters.DEFAULT_PARAMS` by hand, running the suite, and
       * only then spending a validation shot. This records a candidate.
       */
      propose(rowIndex: number): void {
        const jobId = store.job()?.id;
        if (!jobId) return;

        patchState(store, {
          proposing: rowIndex,
          proposeError: null,
          proposeResult: null,
        });
        api.createProposal({ job_id: jobId, row_index: rowIndex }).subscribe({
          next: (created) => {
            patchState(store, {
              proposing: null,
              // Named, not just "done": the proposals list below is sorted
              // newest-first and can be long, and "which one did I just add"
              // is the immediate next question.
              proposeResult: `Staged as ${created.filename}.`,
            });
            loadProposals();
          },
          error: (error: ApiError) =>
            patchState(store, {
              proposing: null,
              proposeError:
                error.code === 'not_found'
                  ? 'That job or row is no longer available — reload and try again.'
                  : error.message,
            }),
        });
      },

      removeProposal(filename: string): void {
        api.deleteProposal(filename).subscribe({
          // Refetch rather than splice the row out locally: the store holds
          // one server response and derives everything else, and a local
          // removal would be the start of a second, diverging copy.
          next: () => loadProposals(),
          error: fail,
        });
      },
    };
  }),

);
