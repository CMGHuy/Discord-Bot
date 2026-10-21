import { OverrideFidelity, OverrideRowDto, OverrideSummary, OverrideVerdict } from '../../../api/models';

/* v173 — one payload per row kind: a stamped individual override (counted),
 * an estimated (approx) row, a bulk-clear row and a stale row; plus the three
 * verdict states the badge words differently. Figures are illustrative, in the
 * shape GET /api/v1/analytics/override-fidelity returns. */

const row = (patch: Partial<OverrideRowDto>): OverrideRowDto => ({
  plan_id: 'p', ticker: 'AAA', horizon: '2w', direction: 'bullish', state_at_close: 'ACTIVE',
  close_date: '2026-10-07', bulk: false, approx: false, price_source: 'quote', status: 'resolved',
  actual_r: 0.168, engine_r: -1.019, delta_r: 1.187, delta_r_gross: 1.207, actual_usd: 8.4,
  engine_usd: -50.95, delta_usd: 59.35, engine_exit_reason: 'stop', outcome: 'helped',
  source: 'manual', ...patch,
});

const WAITING: OverrideVerdict = {
  state: 'WAITING', n: 1, needed: 30, weeks: 1, week_floor: 10, open_n: 0,
  excluded_share: 0.5, evaluable: false, waiting_on: ['count', 'weeks', 'excluded'],
  recorded: false, recorded_on: null, mean_delta_r: null, mean_delta_r_gross: null, ci: null,
  sum_delta_r: null, sum_delta_usd: null, bar_close_n: 0,
};

export const OVERRIDE_FIDELITY_FIXTURE: OverrideFidelity = {
  rows: [
    row({ plan_id: 'a', ticker: 'AAA' }),
    row({ plan_id: 'b', ticker: 'BBB', close_date: '2026-10-06', approx: true,
      price_source: 'session_close', actual_r: -0.5, engine_r: -0.2, delta_r: -0.3,
      delta_r_gross: -0.28, actual_usd: null, engine_usd: null, delta_usd: null,
      engine_exit_reason: 'runner_trail', outcome: 'hurt' }),
    row({ plan_id: 'c', ticker: 'CCC', close_date: '2026-09-30', bulk: true,
      actual_usd: null, engine_usd: null, delta_usd: null }),
    row({ plan_id: 'd', ticker: 'DDD', close_date: '2026-09-22', status: 'stale',
      state_at_close: 'PARTIAL', actual_r: null, engine_r: null, delta_r: null,
      delta_r_gross: null, actual_usd: null, engine_usd: null, delta_usd: null,
      engine_exit_reason: null, outcome: null }),
  ],
  summary: {
    n_by_status: { resolved: 1, open: 0, unstamped: 0, stale: 1, ambiguous: 0,
      parity_mismatch: 0, split_affected: 0, unreplayable: 0 },
    bulk_n: 1, bulk_dates: { '2026-09-30': 1 }, approx_n: 1, counted_n: 1,
    sum_delta_r: 1.187, sum_delta_r_gross: 1.207, sum_delta_usd: 59.35, usd_missing_n: 0,
    helped: 1, hurt: 0, neutral: 0,
    splits: {
      state_at_close: { ACTIVE: { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
      horizon: { '2w': { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
      direction: { bullish: { n: 1, sum_delta_r: 1.187, sum_delta_usd: 59.35 } },
    },
  },
  verdict: WAITING,
  engine_flags: { stall_exit_enabled: false, runner_structure_exit: 'off' },
  asof: '2026-10-19',
  currency_symbol: '$',
};

/** WAITING with the count met: 34 counted, but 8 of 10 weeks, 2 open, 25% left out. */
export const VERDICT_WAITING_ON: OverrideVerdict = {
  ...WAITING, n: 34, weeks: 8, open_n: 2, excluded_share: 0.25,
  waiting_on: ['weeks', 'open', 'excluded'],
};

/** WAITING with every floor met and nothing recorded yet. */
export const VERDICT_FLOORS_MET: OverrideVerdict = {
  ...WAITING, n: 34, weeks: 11, open_n: 0, excluded_share: 0.1, evaluable: true, waiting_on: [],
};

/** A stored COST record: state, n, weeks, the mean/CI/sums and bar_close_n are the
 *  recorded figures; open_n, excluded_share, evaluable and waiting_on are live. */
export const VERDICT_RECORDED_COST: OverrideVerdict = {
  ...WAITING, state: 'COST', n: 31, weeks: 12, open_n: 0, excluded_share: 0.05, evaluable: true,
  waiting_on: [], recorded: true, recorded_on: '2026-12-04', mean_delta_r: -0.22,
  mean_delta_r_gross: -0.2, ci: [-0.24, -0.2], sum_delta_r: -6.82, sum_delta_usd: -1364,
  bar_close_n: 2,
};

/** The fixture with a patched verdict, summary or row list (the specs' one builder). */
export function overrideFixture(patch: {
  verdict?: Partial<OverrideVerdict>; summary?: Partial<OverrideSummary>; rows?: OverrideRowDto[];
} = {}): OverrideFidelity {
  const base = OVERRIDE_FIDELITY_FIXTURE;
  return {
    ...base,
    rows: patch.rows ?? base.rows,
    summary: { ...base.summary, ...patch.summary },
    verdict: { ...base.verdict, ...patch.verdict },
  };
}
