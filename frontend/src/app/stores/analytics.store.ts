import { computed, effect, inject, untracked } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import {
  AnalyticsCalibration,
  AnalyticsDerived,
  AnalyticsJournal,
  AnalyticsPerformance,
  AnalyticsSnapshot,
  AnalyticsStrategies,
} from '../api/models';
import { HistogramBin } from '../ui/histogram';

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
  rr_override: number | null;
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
  tier: string;
  n: number;
  win_rate: number | null;
  expectancy_r: number | null;
  expected_band: string;
  /** Three-valued on purpose. `null` means "not enough live data to judge"
   *  (n < 10), which is a completely different statement from `false`
   *  ("judged, and it missed its band"). Rendering them the same way would
   *  turn "we don't know yet" into "it is broken". */
  ok: boolean | null;
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

/** The four tabs of spec v14 Decision 6. Tabs, not sub-navigation: a second
 *  level of nav inside one of six workspaces reintroduces exactly the depth
 *  the IA change removed. */
export type AnalyticsTab = 'performance' | 'strategies' | 'calibration' | 'tuning';

export const ANALYTICS_TABS: readonly AnalyticsTab[] = [
  'performance',
  'strategies',
  'calibration',
  'tuning',
] as const;

/* -- the snapshot (SR50) --------------------------------------------------
 *
 * `GET /analytics/snapshot` forwards the whole pre-built analytics blob, and
 * it already carries every figure `stats.html` charted: profit factor, Sharpe,
 * Sortino, max drawdown, streaks, the equity and drawdown series, R-multiples,
 * and a `by` block grouped along ten dimensions. `ApiClient.analyticsSnapshot()`
 * existed and no store called it, so the parity audit found seventeen "missing"
 * analytics rows whose data was being served the whole time.
 *
 * Narrowed here rather than in a template, and every narrower returns null
 * rather than 0 for anything it cannot read — `ui/format.ts`'s rule, and the
 * difference between "we don't know" and "it is zero" on a Sharpe ratio.
 */

/** One `StatRow` out of the `by` block (`aggregate.py:47-57`). */
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
}

export interface SeriesPoint {
  date: string;
  value: number;
}

export interface Streaks {
  current: number | null;
  currentKind: string | null;
  bestWin: number | null;
  worstLoss: number | null;
}

/** The dimensions the Breakdowns table can group by, in the order they are
 *  offered. A subset of `aggregate.py:DIMENSIONS`: `strategy` has the whole
 *  Strategies tab and `confidence` has its own table on this one, so offering
 *  them here as well would be three views of one number. */
export const BREAKDOWN_DIMENSIONS = [
  { value: 'ticker', label: 'Ticker' },
  { value: 'horizon', label: 'Horizon' },
  { value: 'direction', label: 'Direction' },
  { value: 'dow', label: 'Day of week' },
  { value: 'month', label: 'Month' },
  { value: 'tier', label: 'Tier' },
  { value: 'badge', label: 'Badge' },
  { value: 'source', label: 'Source' },
] as const;

export type BreakdownDimension = (typeof BREAKDOWN_DIMENSIONS)[number]['value'];

function snapNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function snapText(value: unknown): string | null {
  return typeof value === 'string' && value !== '' ? value : null;
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** `{date, balance}` / `{date, dd_pct}` points, flattened to one shape. A point
 *  missing either half is dropped: a gap in a series is not a zero, and
 *  drawing it as one invents a crash that never happened. */
function toSeries(raw: unknown[], valueKey: string): SeriesPoint[] {
  return raw.flatMap((point) => {
    if (!isPlainRecord(point)) return [];
    const date = snapText(point['date']);
    const value = snapNumber(point[valueKey]);
    return date !== null && value !== null ? [{ date, value }] : [];
  });
}

function toBreakdownRows(raw: unknown[]): BreakdownRow[] {
  return raw.flatMap((row) => {
    if (!isPlainRecord(row)) return [];
    const key = snapText(row['key']);
    if (key === null) return [];
    return [{
      key,
      n: snapNumber(row['n']),
      wins: snapNumber(row['wins']),
      losses: snapNumber(row['losses']),
      win_rate: snapNumber(row['win_rate']),
      expectancy_r: snapNumber(row['expectancy_r']),
      avg_r: snapNumber(row['avg_r']),
      profit_factor: snapNumber(row['profit_factor']),
      total_pnl: snapNumber(row['total_pnl']),
    }];
  });
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

  performance: AnalyticsPerformance | null;
  /**
   * SR54 — the date range scoping every derived figure, as `YYYY-MM-DD` or
   * null for unbounded.
   *
   * Held in the store rather than the component because it is a *fetch*
   * parameter: changing it re-requests `/analytics/performance`. A range kept
   * in component state would have to reach back into the store to trigger
   * that, which is the wiring spec v14 Decision 1 pushes into the store on
   * purpose.
   */
  rangeFrom: string | null;
  rangeTo: string | null;
  /** SR55 — the trailing-week digest and recurring lessons. Its own field
   *  and its own error for the same reason the snapshot has them: it comes
   *  from a different endpoint, and losing it is not a reason to warn about
   *  panels that arrived fine. */
  journal: AnalyticsJournal | null;
  journalError: string | null;
  /** SR50 — the pre-built blob, fetched alongside `performance`. */
  snapshot: AnalyticsSnapshot | null;
  /** Its own error: the snapshot self-heals on the server and can rebuild on
   *  the request, so a failure here is not a reason to warn about the rest of
   *  the tab, which came from a different endpoint that may be fine. */
  snapshotError: string | null;
  /** Which dimension the Breakdowns table is grouped by. */
  breakdown: BreakdownDimension;

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
  strategies: AnalyticsStrategies | null;
  calibration: AnalyticsCalibration | null;
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
 * Analytics — Performance, Strategies, Calibration and Tuning behind one
 * `TabBar` (spec v14 Decision 6).
 *
 * Follows `DashboardStore`'s shape: one server response per concern in, all
 * derivation in `withComputed`, and a `withHooks` effect whose first run IS
 * the initial load. Two things are specific to this workspace and are the
 * reason it is not just four copies of the Dashboard store:
 *
 * **Only the open tab is fetched.** Spec v12's taxonomy says an `analytics`
 * event means "refetch the open Analytics view", not "refetch all four". The
 * effect reads `tab` and dispatches, so switching tabs is what triggers a
 * fetch — and a tab that has already loaded keeps its data on screen while
 * the next one arrives, rather than four payloads racing on entry.
 *
 * **Tuning listens to `jobs`, the other three to `analytics`.** This is the
 * bullet NG48 exists for: the Jinja page drove job progress with a 3-second
 * `setTimeout` poll and a full `window.location.reload()` on completion.
 * Here the server's watcher on `admin_jobs.json` and `tuning_results/` raises
 * `jobs`, the effect refetches `GET /jobs/:id`, and the log tail and state
 * pill update in place. **There is deliberately no timer anywhere in this
 * file** — if one reappears, the polling came back.
 *
 * The event counters are read *conditionally*, inside the dispatch. Angular's
 * signal graph re-tracks dependencies on every run, so an `analytics` event
 * cannot refetch the jobs list while Tuning is open, and vice versa.
 */
export const AnalyticsStore = signalStore(
  withState<AnalyticsSlice>({
    tab: 'performance',
    performance: null,
    rangeFrom: null,
    rangeTo: null,
    journal: null,
    journalError: null,
    snapshot: null,
    snapshotError: null,
    breakdown: 'ticker',
    gridStrategy: null,
    grid: [],
    proposing: null,
    proposeError: null,
    proposeResult: null,
    strategies: null,
    calibration: null,
    jobs: [],
    job: null,
    proposals: [],
    loading: false,
    error: null,
    launching: false,
    launchError: null,
  }),

  withComputed(({ performance, strategies, calibration, jobs, job, snapshot, breakdown,
                 journal }) => ({
    /* -- SR50: the snapshot's own figures ------------------------------- */

    /** When the blob was assembled. Worth showing: the server serves a
     *  snapshot up to an hour old and rebuilds on demand past that, so "these
     *  numbers are from 09:15" is a real thing to know. */
    snapshotBuiltAt: computed(() => snapText(snapshot()?.built_at)),

    profitFactor: computed(() => snapNumber(snapshot()?.overall?.['profit_factor'])),
    sharpe: computed(() => snapNumber(snapshot()?.overall?.['sharpe'])),
    sortino: computed(() => snapNumber(snapshot()?.overall?.['sortino'])),
    maxDrawdownPct: computed(() => snapNumber(snapshot()?.overall?.['max_drawdown_pct'])),
    totalPnl: computed(() => snapNumber(snapshot()?.overall?.['total_pnl'])),

    /** Current run, and the best and worst ever. Never rendered even by the
     *  Jinja page, which computed them and dropped them on the floor. */
    streaks: computed<Streaks | null>(() => {
      const raw = snapshot()?.overall?.['streaks'];
      if (!isPlainRecord(raw)) return null;
      return {
        current: snapNumber(raw['current']),
        currentKind: snapText(raw['current_kind']),
        bestWin: snapNumber(raw['best_win_streak']),
        worstLoss: snapNumber(raw['worst_loss_streak']),
      };
    }),

    /** The account balance over time — the series behind the Dashboard's
     *  30-day sparkline, in full and in account currency. */
    equitySeries: computed<SeriesPoint[]>(() =>
      toSeries((snapshot()?.equity_curve?.points ?? []) as unknown[], 'balance'),
    ),

    /** How far below its own peak the account sat at each point. */
    drawdownSeries: computed<SeriesPoint[]>(() =>
      toSeries((snapshot()?.drawdown ?? []) as unknown[], 'dd_pct'),
    ),

    rMultipleBins: computed<Bin[]>(() =>
      binRMultiples(
        ((snapshot()?.r_multiples ?? []) as unknown[])
          .map(snapNumber)
          .filter((value): value is number => value !== null),
      ),
    ),

    /** The chosen dimension's rows, busiest group first — `stats_by` already
     *  sorts by trade count descending, which is the order every table in this
     *  cockpit wants. */
    breakdownRows: computed<BreakdownRow[]>(() =>
      toBreakdownRows((snapshot()?.by?.[breakdown()] ?? []) as unknown[]),
    ),

    breakdownLabel: computed(
      () =>
        BREAKDOWN_DIMENSIONS.find((d) => d.value === breakdown())?.label ??
        breakdown(),
    ),

    /* -- performance --------------------------------------------------- */

    /**
     * The six relocated metrics, resolved in the order the spec names them.
     * Every entry in `RELOCATED_METRICS` produces a row whether or not the
     * server sent it, so a metric that goes missing renders as an em dash and
     * is reported by `missingRelocated` — never silently disappears.
     */
    relocated: computed<RelocatedMetric[]>(() => {
      const block = performance()?.relocated as Record<string, unknown> | undefined;
      return RELOCATED_METRICS.map((metric) => ({
        ...metric,
        value: numberOrNull(block, metric.key),
        pnl: PNL_METRICS.has(metric.key),
      }));
    }),

    /**
     * Which of the six the payload did not carry at all.
     *
     * The distinction is `key in record` rather than "is null": a null is the
     * server saying "no closed trades yet", which is a legitimate answer. An
     * absent key means the relocation lost a metric somewhere between
     * `analytics_performance()` and here, which is the specific regression
     * spec v14 Decision 6 says must not happen. Empty while nothing has
     * loaded — an unanswered request has not lost anything.
     */
    missingRelocated: computed<string[]>(() => {
      const data = performance();
      if (!data) return [];
      const block = (data.relocated ?? {}) as Record<string, unknown>;
      return RELOCATED_METRICS.filter((metric) => !(metric.key in block)).map((m) => m.label);
    }),

    winRate: computed(() => performance()?.win_rate ?? null),
    expectancyR: computed(() => performance()?.expectancy_r ?? null),

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

    /** The derived figures resolved into render-ready rows. */
    derivedMetrics: computed<DerivedMetric[]>(() => {
      const block = performance()?.derived ?? EMPTY_DERIVED;
      return DERIVED_METRICS.map((metric) => ({
        ...metric,
        value: block[metric.key] ?? null,
      }));
    }),

    /** What the server says it scoped to — echoed back, not what we asked
     *  for. If the two ever disagree the range silently did not apply, which
     *  is exactly the failure this echo exists to make visible. */
    appliedRange: computed(() => performance()?.range ?? null),

    /** True once a bound is set, so the UI can offer "clear" and label the
     *  section as scoped rather than all-time. */
    rangeActive: computed(() => {
      const range = performance()?.range;
      return Boolean(range?.from || range?.to);
    }),

    /** Trades inside the window. Shown beside the figures because a Calmar
     *  computed on four trades and one computed on four hundred should not
     *  look equally authoritative. */
    rangeSampleSize: computed(() => performance()?.range?.n ?? 0),

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
    rollingReturns: computed(() => performance()?.rolling_returns ?? []),
    holdingSplit: computed(() => performance()?.holding_period_split ?? []),
    calendarReturns: computed(() => performance()?.calendar ?? []),

    /** `{strategy: points}` flattened into sorted series, so the chart never
     *  iterates object keys and never redraws in a different order. */
    cumulativeByStrategy: computed(() => {
      const block = performance()?.cumulative_by_strategy ?? {};
      return Object.entries(block)
        .map(([strategy, points]) => ({ strategy, points }))
        .sort((a, b) => a.strategy.localeCompare(b.strategy));
    }),

    /** SPY's cumulative % return, as a sorted series. Empty when the fetch
     *  was unavailable — the benchmark overlay is best-effort by design. */
    benchmarkSeries: computed(() => {
      const block = performance()?.benchmark?.spy_cum ?? {};
      return Object.entries(block)
        .map(([date, pct]) => ({ date, pct }))
        .sort((a, b) => a.date.localeCompare(b.date));
    }),

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

    heatmap: computed<Heatmap | null>(() => {
      const block = strategies()?.heatmap;
      if (!block) return null;

      // Read field by field rather than asserting the whole envelope: the
      // axes and the cells arrive as three independent lists, and a grid
      // built from a missing axis renders as an empty box instead of as
      // nothing at all.
      const axisStrategies = (block['strategies'] ?? []) as string[];
      const horizons = (block['horizons'] ?? []) as string[];
      const cells = (block['cells'] ?? []) as HeatmapCell[];
      if (!axisStrategies.length || !horizons.length) return null;

      return { strategies: axisStrategies, horizons, cells };
    }),

    /** Strategy names for the Tuning launcher. Sourced from the registry
     *  rather than hardcoded: the server whitelists the strategy against
     *  `ALL_STRATEGIES` and 400s on anything else, so a stale hardcoded list
     *  here would offer a choice that cannot be launched. */
    strategyNames: computed<string[]>(() =>
      ((strategies()?.strategies ?? []) as StrategyRow[]).map((row) => row.strategy),
    ),

    /* -- calibration --------------------------------------------------- */

    deciles: computed<DecileRow[]>(() => (calibration()?.deciles ?? []) as DecileRow[]),
    tiers: computed<TierRow[]>(() => (calibration()?.tiers ?? []) as TierRow[]),
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
  })),

  withMethods((store, api = inject(ApiClient)) => {
    /** Every failure lands here, and none of them clear the data already on
     *  screen. A table that empties because one refetch failed is worse than
     *  a slightly stale one beside a warning — especially when the event
     *  stream reconnects seconds later. */
    const fail = (error: ApiError): void =>
      patchState(store, {
        loading: false,
        error:
          error.code === 'unavailable' ? 'The admin is not responding.' : error.message,
      });

    const loadPerformance = (): void => {
      patchState(store, { loading: true });
      // SR54: the range travels to the server. See ApiClient.analyticsPerformance
      // for why it cannot be applied to an all-time payload on the client.
      api.analyticsPerformance({ from: store.rangeFrom(), to: store.rangeTo() })
        .subscribe({
          next: (performance) =>
            patchState(store, { performance, loading: false, error: null }),
          error: fail,
        });

      // SR55. A third request, and a third failure mode, for the same reason
      // the snapshot is separate: the journal lives in its own store and its
      // own module, and folding it into the performance response would make a
      // journal read failure empty the KPI cards.
      api.analyticsJournal().subscribe({
        next: (journal) => patchState(store, { journal, journalError: null }),
        error: (error: ApiError) =>
          patchState(store, {
            journalError:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });

      // SR50. A second request rather than a widened /analytics/performance:
      // the snapshot is a whole pre-built blob served by its own endpoint, and
      // folding it into the summary response would make every Performance
      // visit carry the equity curve whether or not the panels using it are on
      // screen. It fails on its own terms -- see `snapshotError`.
      api.analyticsSnapshot().subscribe({
        next: (snapshot) => patchState(store, { snapshot, snapshotError: null }),
        error: (error: ApiError) =>
          patchState(store, {
            snapshotError:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    };

    const loadStrategies = (): void => {
      patchState(store, { loading: true });
      api.analyticsStrategies().subscribe({
        next: (strategies) => patchState(store, { strategies, loading: false, error: null }),
        error: fail,
      });
    };

    const loadCalibration = (): void => {
      patchState(store, { loading: true });
      api.analyticsCalibration().subscribe({
        next: (calibration) =>
          patchState(store, { calibration, loading: false, error: null }),
        error: fail,
      });
    };

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

    const load = (): void => {
      switch (store.tab()) {
        case 'performance':
          return loadPerformance();
        case 'strategies':
          return loadStrategies();
        case 'calibration':
          return loadCalibration();
        case 'tuning':
          return loadTuning();
      }
    };

    return {
      /** The one way the tab arrives, and it comes from the URL. */
      setTab(tab: AnalyticsTab): void {
        patchState(store, { tab });
      },

      /** Which dimension the Breakdowns table groups by. Local state, not a
       *  query parameter: it refetches nothing — every dimension is already in
       *  the one snapshot — so there is no request for the URL to describe. */
      setBreakdown(breakdown: BreakdownDimension): void {
        patchState(store, { breakdown });
      },

      /**
       * SR54 — set the analytics date range and refetch.
       *
       * Unlike `setBreakdown` this DOES refetch, because the arithmetic lives
       * on the server. Both bounds are set together in one call so a user
       * picking a range never triggers two requests, the second of which
       * would race the first and could land older numbers last.
       *
       * An out-of-order pair is normalised rather than rejected: a date picker
       * mid-edit legitimately passes through `from > to`, and refusing it
       * would surface an error for a state the user is about to fix anyway.
       */
      setRange(from: string | null, to: string | null): void {
        const [lo, hi] = from && to && from > to ? [to, from] : [from, to];
        patchState(store, { rangeFrom: lo || null, rangeTo: hi || null });
        loadPerformance();
      },

      /** Back to all-time. */
      clearRange(): void {
        patchState(store, { rangeFrom: null, rangeTo: null });
        loadPerformance();
      },

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

  withHooks({
    onInit(store, events = inject(EventStream)) {
      const analytics = events.changes('analytics');
      const jobs = events.changes('jobs');

      effect(() => {
        // Reading `tab` makes a tab switch a fetch; reading the counter is
        // the event subscription. Which counter is read depends on the tab,
        // so an `analytics` event never disturbs a running job's log and a
        // `jobs` event never refetches the calibration tables.
        const tab = store.tab();
        if (tab === 'tuning') jobs();
        else analytics();

        // `untracked`, and this is not belt-and-braces: `loadTuning` reads
        // `strategies` to decide whether the launcher's option list is
        // already in hand. Tracked, that read would make the reply to its
        // own request re-trigger this effect, and every visit to the Tuning
        // tab would fetch the jobs list twice. The two dependencies this
        // effect is allowed to have are both above.
        untracked(() => store.load());
      });
    },
  }),
);
