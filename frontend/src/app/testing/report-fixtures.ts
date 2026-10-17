import {
  AttributionMonotonicity,
  AttributionPopulation,
  AttributionQuartiles,
  ExpectancyAttribution,
  GateCounterfactual,
  ReportEnvelope,
} from '../api/models';

/* Shared by every Reports spec (store, both tabs, the shell), so the two
 * tabs cannot be tested against two different ideas of the wire. The key
 * sets are pinned against the real builders in `report-fixtures.spec.ts`.
 *
 * Cases each fixture carries on purpose:
 *   ATTRIBUTION  verdict of record WEAK (2026-10-12, n 214) while the latest
 *                reading says PREDICTIVE: the page must show WEAK as THE
 *                verdict; one thin bucket (`earnings` `0-5`, n 12); one
 *                factor at q 0.04 (a screen candidate) and one at q 0.31
 *                (not); one bucket at q 0.08 (candidate) and a THIN bucket at
 *                q 0.01 (must NOT be marked: thin enters no marker). v146
 *                itself leaves a thin bucket's q null; the 0.01 proves the
 *                page does not depend on that.
 *   GATES        live `rs` is WAITING at n 29 (its `latest` is filled on
 *                purpose: below the floor the page shows none of it); TRAIN
 *                `rs` is the persisted "no TRAIN population" note cell; live
 *                `risk_cap` has a verdict of record GATE EARNS that differs
 *                from its latest reading INCONCLUSIVE; TRAIN `compression` is
 *                in-sample; a `risk_cap` row is over-cap with a dollar figure.
 *
 * Units are the reports' own: v146 `win_rate` in percent, v147 win and fill
 * rates as fractions.
 */

const rr = (median: number): AttributionQuartiles => ({ p25: median - 0.25, median, p75: median + 0.25 });

const mono = (over: Partial<AttributionMonotonicity> = {}): AttributionMonotonicity => ({
  n: 214, spearman_rho: 0.18, tercile_spread: 0.22, ci_low: 0.03, ci_high: 0.41, p: 0.02,
  inverted: false, tercile_n: [71, 72, 71], rr_by_tercile: [rr(1.8), rr(1.9), rr(2.0)], ...over,
});

const LIVE: AttributionPopulation = {
  window: { first_week: '2026-07-06', last_week: '2026-10-05' },
  n: 214,
  monotonicity: mono(),
  factors: [
    { key: 'RSI trend alignment', n: 214, n_pos: 120, n_zero: 94, delta: 0.19, ci_low: 0.04, ci_high: 0.35, p: 0.004, q: 0.04 },
    { key: 'MACD momentum', n: 214, n_pos: 101, n_zero: 113, delta: 0.03, ci_low: -0.12, ci_high: 0.18, p: 0.2, q: 0.31 },
  ],
  buckets: {
    regime2_state: [
      { label: 'bull_quiet', n: 140, win_rate: 58, exp_r: 0.24, exp_r_gross: 0.27, thin: false,
        delta: 0.3, ci_low: 0.05, ci_high: 0.52, p: 0.01, q: 0.08 },
      { label: 'bear_volatile', n: 74, win_rate: 41, exp_r: -0.06, exp_r_gross: -0.03, thin: false,
        delta: -0.3, ci_low: -0.52, ci_high: -0.05, p: 0.3, q: 0.42 },
    ],
    earnings: [
      { label: '0-5', n: 12, win_rate: 33, exp_r: -0.4, exp_r_gross: -0.37, thin: true,
        delta: -0.58, ci_low: null, ci_high: null, p: null, q: 0.01 },
      { label: '>20', n: 202, win_rate: 54, exp_r: 0.16, exp_r_gross: 0.19, thin: false,
        delta: 0.56, ci_low: null, ci_high: null, p: null, q: 0.6 },
    ],
  },
  splits: {
    direction: {
      bullish: mono({ n: 170 }),
      bearish: mono({ n: 44, tercile_spread: -0.05, ci_low: -0.3, ci_high: 0.2, p: 0.7 }),
    },
    horizon: { '2w': mono({ n: 150 }), '3m': mono({ n: 64 }) },
  },
  notes: ['Closed trades from the trades table, both ledgers.'],
};

const TRAIN: AttributionPopulation = {
  window: { first_week: '2019-01-07', last_week: '2023-12-25' },
  n: 3120,
  monotonicity: mono({ n: 3120, spearman_rho: 0.06, tercile_spread: 0.04, ci_low: -0.02, ci_high: 0.1, p: 0.2,
                       tercile_n: [1040, 1040, 1040] }),
  factors: [
    { key: 'RSI trend alignment', n: 3120, n_pos: 1700, n_zero: 1420, delta: 0.05, ci_low: -0.01, ci_high: 0.11, p: 0.1, q: 0.2 },
    { key: 'MACD momentum', n: 3120, n_pos: 1500, n_zero: 1620, delta: 0.01, ci_low: -0.04, ci_high: 0.06, p: 0.6, q: 0.7 },
  ],
  buckets: {
    regime2_state: [
      { label: 'bull_quiet', n: 2100, win_rate: 52, exp_r: 0.11, exp_r_gross: 0.14, thin: false,
        delta: 0.09, ci_low: -0.02, ci_high: 0.2, p: 0.15, q: 0.3 },
      { label: 'bear_volatile', n: 1020, win_rate: 47, exp_r: 0.02, exp_r_gross: 0.05, thin: false,
        delta: -0.09, ci_low: -0.2, ci_high: 0.02, p: 0.3, q: 0.5 },
    ],
    earnings: [
      { label: '0-5', n: 310, win_rate: 50, exp_r: 0.05, exp_r_gross: 0.08, thin: false,
        delta: -0.04, ci_low: -0.15, ci_high: 0.07, p: 0.4, q: 0.5 },
      { label: '>20', n: 2810, win_rate: 51, exp_r: 0.09, exp_r_gross: 0.12, thin: false,
        delta: 0.04, ci_low: -0.07, ci_high: 0.15, p: 0.4, q: 0.5 },
    ],
  },
  splits: {
    direction: { bullish: mono({ n: 2500 }), bearish: mono({ n: 620 }) },
    horizon: { '2w': mono({ n: 2200 }), '3m': mono({ n: 920 }) },
  },
  notes: ['TRAIN confluence replay, not level-gated; VALIDATION is never read.'],
};

export const ATTRIBUTION: ExpectancyAttribution = {
  generated_at: '2026-10-20T21:30:00+00:00',
  verdict: 'PREDICTIVE',
  verdict_of_record: { verdict: 'WEAK', date: '2026-10-12', n: 214 },
  looks: 37,
  seed: 42,
  provenance: { n_resamples: 10000 },
  populations: { live: LIVE, train: TRAIN },
};

export const GATES: GateCounterfactual = {
  generated_at: '2026-10-20T21:45:00+00:00',
  live_window: '2026-10-01..2026-10-20',
  bh_family: 5,
  seed: 42,
  limitations: ['Portfolio state: every blocked candidate is simulated as a lone trade.'],
  cells: [
    { gate: 'rs', population: 'live', verdict: 'WAITING', n: 29, taken_n: 40, verdict_of_record: null,
      latest: { difference: -0.3, ci_low: -0.9, ci_high: 0.2, q: 0.4, p: 0.3 }, in_sample: false, note: null },
    { gate: 'rs', population: 'train', verdict: 'WAITING', n: 0, taken_n: 0, verdict_of_record: null,
      latest: null, in_sample: false, note: 'no TRAIN population' },
    { gate: 'risk_cap', population: 'live', verdict: 'INCONCLUSIVE', n: 46, taken_n: 52,
      verdict_of_record: { verdict: 'GATE EARNS', date: '2026-10-14', n: 31 },
      latest: { difference: -0.08, ci_low: -0.31, ci_high: 0.12, q: 0.44, p: 0.35 }, in_sample: false, note: null },
    { gate: 'risk_cap', population: 'train', verdict: 'GATE EARNS', n: 412, taken_n: 900,
      verdict_of_record: { verdict: 'GATE EARNS', date: '2026-10-14', n: 412 },
      latest: { difference: -0.21, ci_low: -0.33, ci_high: -0.09, q: 0.01, p: 0.002 }, in_sample: false, note: null },
    { gate: 'compression', population: 'live', verdict: 'INCONCLUSIVE', n: 38, taken_n: 33,
      verdict_of_record: { verdict: 'INCONCLUSIVE', date: '2026-10-16', n: 30 },
      latest: { difference: 0.05, ci_low: -0.2, ci_high: 0.3, q: 0.7, p: 0.7 }, in_sample: false, note: null },
    { gate: 'compression', population: 'train', verdict: 'GATE COSTS', n: 260, taken_n: 140,
      verdict_of_record: { verdict: 'GATE COSTS', date: '2026-10-14', n: 260 },
      latest: { difference: 0.17, ci_low: 0.04, ci_high: 0.3, q: 0.03, p: 0.01 }, in_sample: true, note: null },
  ],
  rows: [
    { gate: 'rs', reason: 'rs_below_floor', population: 'live', blocked_n: 29, no_plan_n: 4,
      fill_rate: 0.72, blocked_exp_r: -0.2, blocked_win_rate: 0.4, taken_n: 40, taken_exp_r: 0.1,
      taken_win_rate: 0.52, taken_realised_exp_r: 0.08, near_miss_n: 9, near_miss_exp_r: 0.05,
      rest_n: 20, rest_exp_r: -0.31, dollar_risk: null, over_cap: false, in_sample: false },
    { gate: 'risk_cap', reason: 'risk_cap_exceeded', population: 'live', blocked_n: 46, no_plan_n: 0,
      fill_rate: 0.8, blocked_exp_r: 0.02, blocked_win_rate: 0.48, taken_n: 52, taken_exp_r: 0.1,
      taken_win_rate: 0.52, taken_realised_exp_r: 0.09, near_miss_n: 12, near_miss_exp_r: 0.08,
      rest_n: 34, rest_exp_r: 0, dollar_risk: 412.5, over_cap: true, in_sample: false },
    { gate: 'compression', reason: 'range_too_wide', population: 'train', blocked_n: 260, no_plan_n: 11,
      fill_rate: 0.66, blocked_exp_r: 0.27, blocked_win_rate: 0.55, taken_n: 140, taken_exp_r: 0.1,
      taken_win_rate: 0.5, taken_realised_exp_r: null, near_miss_n: null, near_miss_exp_r: null,
      rest_n: null, rest_exp_r: null, dollar_risk: null, over_cap: false, in_sample: true },
  ],
};

export const ok = <T extends { generated_at: string }>(result: T): ReportEnvelope<T> => ({
  status: 'ok', generated_at: result.generated_at, result,
});

export const NOT_RUN: ReportEnvelope<never> = { status: 'not_run', generated_at: null, result: null };
