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
import { AnalyticsCalibration, AnalyticsPerformance, AnalyticsStrategies } from '../api/models';

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

interface AnalyticsSlice {
  /** Which tab is open, projected from the URL's `?tab=`. Held here rather
   *  than in the component because it decides what gets fetched. */
  tab: AnalyticsTab;

  performance: AnalyticsPerformance | null;
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

  withComputed(({ performance, strategies, calibration, jobs, job }) => ({
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
      api.analyticsPerformance().subscribe({
        next: (performance) =>
          patchState(store, { performance, loading: false, error: null }),
        error: fail,
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
