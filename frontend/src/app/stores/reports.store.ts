import { computed, inject } from '@angular/core';
import { ParamMap } from '@angular/router';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable } from 'rxjs';

import { ApiClient } from '../api/api-client';
import {
  AttributionBucket,
  AttributionMonotonicity,
  AttributionPopulation,
  AttributionWindow,
  ExpectancyAttribution,
  GateCell,
  GateCounterfactual,
  GateCounterfactualRow,
  ReportEnvelope,
} from '../api/models';
import { routeRequest } from '../routing/route-request';
import { BarRow } from '../ui/bar-list';
import { ChipTone } from '../ui/chip';

/* -- the fixed wording -------------------------------------------------- */

/** A factor or bucket is a Stage -2 screen CANDIDATE below this q. The page
 *  compares the q the server computed; it never computes one. */
export const SCREEN_CANDIDATE_Q = 0.10;
/** Display text only, for the "N 17 / 30" progress figure. Whether a cell is
 *  below the floor is v147's `WAITING` verdict, never a test against this. */
export const FLOOR_N_DISPLAY = 30;

export const R_CAPTION = 'R units, net of frictions as v146/v147 compute them, pre-tax.';
export const LATEST_HEADING = 'Latest reading — descriptive';
export const PORTFOLIO_NOTE = 'simulated as a lone trade; ignores heat and correlation caps';
export const HOLDOUT_NOTE = 'live window inside the 2026 holdout; a follow-on screen needs an unseen one';
export const OVER_CAP_NOTE = 'a trade the dollar-risk rule forbids; not a tradable alternative';
const IN_SAMPLE = 'in-sample';

export type ReportTab = 'attribution' | 'gates';

export function tabFromParams(params: ParamMap): ReportTab {
  return params.get('tab') === 'gates' ? 'gates' : 'attribution';
}

type PopulationKey = 'live' | 'train';
const POPULATIONS: readonly PopulationKey[] = ['live', 'train'];
const POPULATION_LABEL: Record<PopulationKey, 'Live' | 'TRAIN'> = { live: 'Live', train: 'TRAIN' };

/* -- expectancy attribution (v146) -------------------------------------- */

export interface VerdictView {
  label: string;
  tone: ChipTone;
  date: string;
  n: number;
  /** "inverted" is reported inside NOT PREDICTIVE, never as its own verdict. */
  inverted: boolean;
}

/** One population's monotonicity reading. `present: false` renders as "not
 *  in this run" and every figure is null: absent is never zero. */
export interface ReadingView {
  population: 'Live' | 'TRAIN';
  present: boolean;
  /** `first_week..last_week`, the population's ISO entry Mondays. */
  window: string | null;
  n: number | null;
  rho: number | null;
  spread: number | null;
  ciLow: number | null;
  ciHigh: number | null;
}

export interface DeltaView {
  n: number;
  delta: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  q: number | null;
}

export interface FactorView {
  /** v146's display name, e.g. `MACD momentum`. */
  key: string;
  live: DeltaView | null;
  train: DeltaView | null;
  candidate: boolean;
}

export interface DimensionView {
  key: string;
  label: string;
  /** Null when that population is absent from the run. */
  live: BarRow[] | null;
  train: BarRow[] | null;
  /** "<bucket> (<population>)" for each non-thin bucket below the q line. */
  candidates: string[];
}

export interface SplitView {
  axis: 'Direction' | 'Horizon';
  name: string;
  live: ReadingView | null;
  train: ReadingView | null;
}

export interface AttributionView {
  verdict: VerdictView;
  readings: ReadingView[];
  factors: FactorView[];
  dimensions: DimensionView[];
  splits: SplitView[];
  looks: number;
  seed: number;
}

const ATTRIBUTION_TONE: Record<string, ChipTone> = {
  PREDICTIVE: 'good',
  WEAK: 'warn',
  'NOT PREDICTIVE': 'neutral',
};

/** v146's grouping keys, in its own order. */
const DIMENSION_LABEL: Record<string, string> = {
  confidence_decile: 'Confidence decile',
  confidence_level: 'Confidence level',
  confluence: 'Confluence',
  regime2_state: 'Regime',
  rs_quintile: 'RS quintile',
  direction: 'Direction',
  horizon: 'Horizon',
  earnings: 'Earnings proximity',
  earnings_in_hold: 'Earnings inside the hold',
};

const isCandidate = (q: number | null): boolean => q !== null && q < SCREEN_CANDIDATE_Q;

const windowText = (window: AttributionWindow | null | undefined): string | null =>
  window ? `${window.first_week}..${window.last_week}` : null;

function reading(
  population: PopulationKey,
  mono: AttributionMonotonicity | null | undefined,
  window: AttributionWindow | null | undefined,
): ReadingView {
  const label = POPULATION_LABEL[population];
  if (!mono) {
    return { population: label, present: false, window: null, n: null, rho: null, spread: null, ciLow: null, ciHigh: null };
  }
  return {
    population: label, present: true, window: windowText(window), n: mono.n, rho: mono.spearman_rho,
    spread: mono.tercile_spread, ciLow: mono.ci_low, ciHigh: mono.ci_high,
  };
}

function factorViews(result: ExpectancyAttribution): FactorView[] {
  const side = (population: PopulationKey, key: string): DeltaView | null => {
    const factor = result.populations[population]?.factors.find((f) => f.key === key);
    return factor
      ? { n: factor.n, delta: factor.delta, ciLow: factor.ci_low, ciHigh: factor.ci_high, q: factor.q }
      : null;
  };
  const keys = new Set<string>();
  for (const population of POPULATIONS) {
    for (const factor of result.populations[population]?.factors ?? []) keys.add(factor.key);
  }
  return [...keys].map((key) => {
    const live = side('live', key);
    const train = side('train', key);
    return { key, live, train, candidate: isCandidate(live?.q ?? null) || isCandidate(train?.q ?? null) };
  });
}

const barRow = (bucket: AttributionBucket): BarRow => ({
  label: bucket.label, value: bucket.exp_r, n: bucket.n, withheld: bucket.thin,
});

function dimensionViews(result: ExpectancyAttribution): DimensionView[] {
  const source: AttributionPopulation | null = result.populations.live ?? result.populations.train;
  return Object.keys(source?.buckets ?? {}).map((key) => {
    const buckets = (population: PopulationKey) => result.populations[population]?.buckets[key] ?? null;
    const candidates: string[] = [];
    for (const population of POPULATIONS) {
      for (const bucket of buckets(population) ?? []) {
        // A thin bucket enters no marker, whatever its q says.
        if (!bucket.thin && isCandidate(bucket.q)) {
          candidates.push(`${bucket.label} (${POPULATION_LABEL[population]})`);
        }
      }
    }
    return {
      key,
      label: DIMENSION_LABEL[key] ?? key,
      live: buckets('live')?.map(barRow) ?? null,
      train: buckets('train')?.map(barRow) ?? null,
      candidates,
    };
  });
}

function splitViews(result: ExpectancyAttribution): SplitView[] {
  const axes: readonly ['direction' | 'horizon', 'Direction' | 'Horizon'][] = [
    ['direction', 'Direction'], ['horizon', 'Horizon'],
  ];
  const out: SplitView[] = [];
  for (const [key, axis] of axes) {
    const names = new Set<string>();
    for (const population of POPULATIONS) {
      for (const name of Object.keys(result.populations[population]?.splits[key] ?? {})) names.add(name);
    }
    for (const name of names) {
      const side = (population: PopulationKey): ReadingView | null => {
        const pop = result.populations[population];
        const mono = pop?.splits[key][name];
        return mono ? reading(population, mono, pop?.window) : null;
      };
      out.push({ axis, name, live: side('live'), train: side('train') });
    }
  }
  return out;
}

/** Everything the Expectancy-attribution tab draws. Pure, so the display
 *  rules are tested here once rather than through a template. */
export function attributionView(result: ExpectancyAttribution): AttributionView {
  const record = result.verdict_of_record;
  const inverted = POPULATIONS.some((p) => result.populations[p]?.monotonicity.inverted === true);
  return {
    verdict: {
      label: record.verdict,
      tone: ATTRIBUTION_TONE[record.verdict] ?? 'neutral',
      date: record.date,
      n: record.n,
      inverted,
    },
    readings: POPULATIONS.map((p) =>
      reading(p, result.populations[p]?.monotonicity, result.populations[p]?.window)),
    factors: factorViews(result),
    dimensions: dimensionViews(result),
    splits: splitViews(result),
    looks: result.looks,
    seed: result.seed,
  };
}

/* -- gate counterfactual (v147) ----------------------------------------- */

export interface GateVerdictView {
  label: string;
  tone: ChipTone;
  date: string;
  n: number;
  /** The verdict as a historical measurement, never an instruction. */
  sentence: string;
}

export interface GateLatestView {
  difference: number | null;
  ciLow: number | null;
  ciHigh: number | null;
  q: number | null;
}

/** One gate x reason row. Rates are v147's FRACTIONS (0-1). */
export interface GateRowView {
  reason: string;
  blockedN: number;
  noPlanN: number;
  fillRate: number | null;
  blockedExpR: number | null;
  blockedWinRate: number | null;
  takenN: number;
  takenExpR: number | null;
  takenWinRate: number | null;
  /** The taken arm's booked R, shown beside the re-walk; never the taken ExpR. */
  takenRealisedExpR: number | null;
  nearMissN: number | null;
  nearMissExpR: number | null;
  restN: number | null;
  restExpR: number | null;
  dollarRisk: number | null;
  overCap: boolean;
}

export interface GateCellView {
  /** `<gate>:<population>`, the table's row key. */
  id: string;
  gate: string;
  population: 'Live' | 'TRAIN';
  /** `verdict`: a verdict of record exists. `waiting`: below v147's floor.
   *  `note`: a fixed non-verdict state v147 persisted, such as "no TRAIN
   *  population". */
  state: 'verdict' | 'waiting' | 'note';
  verdict: GateVerdictView | null;
  n: number;
  note: string | null;
  /** Null unless a verdict of record exists: a reading below the floor, or
   *  under a note, is not shown at all. */
  latest: GateLatestView | null;
  labels: string[];
  rows: GateRowView[];
}

const GATE_TONE: Record<string, ChipTone> = {
  'GATE EARNS': 'good',
  'GATE COSTS': 'warn',
  INCONCLUSIVE: 'neutral',
};

const GATE_SENTENCE: Record<string, string> = {
  'GATE EARNS': 'Over these trades, the gate’s blocked setups returned less than its taken ones.',
  'GATE COSTS': 'Over these trades, the gate’s blocked setups returned more than its taken ones.',
  INCONCLUSIVE: 'Over these trades, the difference between blocked and taken setups is not distinguishable from zero.',
};

const rowView = (row: GateCounterfactualRow): GateRowView => ({
  reason: row.reason,
  blockedN: row.blocked_n,
  noPlanN: row.no_plan_n,
  fillRate: row.fill_rate,
  blockedExpR: row.blocked_exp_r,
  blockedWinRate: row.blocked_win_rate,
  takenN: row.taken_n,
  takenExpR: row.taken_exp_r,
  takenWinRate: row.taken_win_rate,
  takenRealisedExpR: row.taken_realised_exp_r,
  nearMissN: row.near_miss_n,
  nearMissExpR: row.near_miss_exp_r,
  restN: row.rest_n,
  restExpR: row.rest_exp_r,
  dollarRisk: row.dollar_risk,
  overCap: row.over_cap,
});

function cellState(cell: GateCell): GateCellView['state'] {
  if (cell.note !== null) return 'note';
  return cell.verdict_of_record === null ? 'waiting' : 'verdict';
}

function cellLabels(cell: GateCell, state: GateCellView['state']): string[] {
  if (state !== 'verdict') return [];
  const labels: string[] = [];
  if (cell.in_sample) labels.push(IN_SAMPLE);
  if (cell.population === 'live') labels.push(PORTFOLIO_NOTE, HOLDOUT_NOTE);
  return labels;
}

function cellVerdict(cell: GateCell, state: GateCellView['state']): GateVerdictView | null {
  const record = cell.verdict_of_record;
  if (state !== 'verdict' || !record) return null;
  return {
    label: record.verdict,
    tone: GATE_TONE[record.verdict] ?? 'neutral',
    date: record.date,
    n: record.n,
    sentence: GATE_SENTENCE[record.verdict] ?? '',
  };
}

function cellLatest(cell: GateCell, state: GateCellView['state']): GateLatestView | null {
  const latest = cell.latest;
  if (state !== 'verdict' || !latest) return null;
  return { difference: latest.difference, ciLow: latest.ci_low, ciHigh: latest.ci_high, q: latest.q };
}

function cellView(cell: GateCell, rows: readonly GateCounterfactualRow[]): GateCellView {
  const state = cellState(cell);
  return {
    id: `${cell.gate}:${cell.population}`,
    gate: cell.gate,
    population: POPULATION_LABEL[cell.population],
    state,
    verdict: cellVerdict(cell, state),
    n: cell.n,
    note: cell.note,
    latest: cellLatest(cell, state),
    labels: cellLabels(cell, state),
    rows: rows
      .filter((row) => row.gate === cell.gate && row.population === cell.population)
      .map(rowView),
  };
}

/** One view per cell, in the report's order, each carrying its own
 *  gate x reason rows. */
export function gatesView(result: GateCounterfactual): GateCellView[] {
  return result.cells.map((cell) => cellView(cell, result.rows));
}

/* -- the store ---------------------------------------------------------- */

interface ReportsSlice {
  tab: ReportTab;
  attributionEnvelope: ReportEnvelope<ExpectancyAttribution> | null;
  gatesEnvelope: ReportEnvelope<GateCounterfactual> | null;
  loading: boolean;
  error: string | null;
}

/**
 * The Reports workspace's data: the latest v146 and v147 results.
 *
 * Each tab fetches only its own report, on navigation. There is no event
 * wiring: a result changes only when someone runs a report script on the VM.
 * Nothing here computes a figure; the two `*View` functions above only
 * rearrange what the report modules already decided.
 */
export const ReportsStore = signalStore(
  withState<ReportsSlice>({
    tab: 'attribution',
    attributionEnvelope: null,
    gatesEnvelope: null,
    loading: false,
    error: null,
  }),
  withComputed(({ tab, attributionEnvelope, gatesEnvelope }) => ({
    /** The active tab's envelope: what `asyncInputs` reads. */
    data: computed<ReportEnvelope<unknown> | null>(() =>
      tab() === 'gates' ? gatesEnvelope() : attributionEnvelope()),
    attribution: computed<AttributionView | null>(() => {
      const result = attributionEnvelope()?.result;
      return result ? attributionView(result) : null;
    }),
    gates: computed<GateCellView[] | null>(() => {
      const result = gatesEnvelope()?.result;
      return result ? gatesView(result) : null;
    }),
  })),
  withComputed(({ data }) => ({
    notRun: computed(() => data()?.status === 'not_run'),
    generatedAt: computed<string | null>(() => data()?.generated_at ?? null),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    const failed = (message: string, code: string | number) => patchState(store, {
      loading: false,
      error: code === 'unavailable'
        ? 'The admin is not responding — the report is unavailable.'
        : message,
    });
    const resolveTab = (tab: ReportTab): Observable<void> => {
      patchState(store, { tab });
      if (tab === 'gates') {
        return routeRequest(api.reportGateCounterfactual(), {
          start: () => patchState(store, { loading: true }),
          next: (gatesEnvelope) => patchState(store, { gatesEnvelope, loading: false, error: null }),
          error: (error) => failed(error.message, error.code),
        });
      }
      return routeRequest(api.reportExpectancyAttribution(), {
        start: () => patchState(store, { loading: true }),
        next: (attributionEnvelope) => patchState(store, { attributionEnvelope, loading: false, error: null }),
        error: (error) => failed(error.message, error.code),
      });
    };
    return {
      resolveTab,
      load(): void { resolveTab(store.tab()).subscribe({ error: () => undefined }); },
    };
  }),
);
