import { AnalyticsPartials, PartialsBreakdownRow, PartialsKpis } from '../../../api/models';

/** v142 — one `/analytics/partials` payload, shaped from the Python test
 *  book (`tests/analytics/test_partials.py::_book`). Shared by the store
 *  and tab specs so both read the same response. */
const KPIS: PartialsKpis = {
  tp1_rate: 85.7, tp1_rate_n: 7, tp1_tp2_rate: 25, tp1_tp2_n: 4,
  beat_all_out: 80, beat_all_out_n: 5, mean_runner_delta_r: 0.324,
  median_tp1_exit_sessions: 2, tp1_exit_n: 5,
};

const row = (key: string, n: number, thin: boolean): PartialsBreakdownRow => ({ ...KPIS, key, n, thin });

export const PARTIALS_FIXTURE: AnalyticsPartials = {
  kpis: KPIS,
  funnel: [
    { stage: 'filled', n: 8 }, { stage: 'tp1', n: 6 }, { stage: 'runner_closed', n: 5 }, { stage: 'tp2', n: 1 },
  ],
  outcomes: [
    { bucket: 'tp2', n: 1, share: 16.7, avg_runner_r: 4 },
    { bucket: 'trail', n: 1, share: 16.7, avg_runner_r: 3 },
    { bucket: 'floor', n: 1, share: 16.7, avg_runner_r: 1.34 },
    { bucket: 'stall', n: 0, share: 0, avg_runner_r: null },
    { bucket: 'time', n: 0, share: 0, avg_runner_r: null },
    { bucket: 'manual', n: 1, share: 16.7, avg_runner_r: 2.5 },
    { bucket: 'no_tp2', n: 1, share: 16.7, avg_runner_r: 2.4 },
    { bucket: 'open', n: 1, share: 16.7, avg_runner_r: null },
  ],
  counterfactuals: {
    actual_exp_r: 2.324, all_out_exp_r: 2, giveback: [0.2, 1.26, 0.6, 0.4],
    ladder: [
      { level_r: 1.5, touch_rate: 100, cf_exp_r: 1.75, n: 4 },
      { level_r: 2, touch_rate: 100, cf_exp_r: 2, n: 4 },
      { level_r: 2.5, touch_rate: 100, cf_exp_r: 2.25, n: 4 },
      { level_r: 3, touch_rate: 50, cf_exp_r: 2.2175, n: 4 },
      { level_r: 4, touch_rate: 25, cf_exp_r: 2.3425, n: 4 },
    ],
    split: [
      { fraction: 0.33, exp_r: 2.4342, n: 5 }, { fraction: 0.5, exp_r: 2.324, n: 5 },
      { fraction: 0.67, exp_r: 2.2138, n: 5 },
    ],
    path_unavailable: 1, runner_r_unavailable: 0,
  },
  holds: {
    entry_tp1: { p25: 2, median: 2, p75: 2, points: [2, 2, 2, 2, 2, 2] },
    tp1_exit: { p25: 2, median: 2, p75: 2, points: [2, 2, 2, 2, 4] },
    entry_exit: { p25: 4, median: 4, p75: 4, points: [4, 4, 4, 4, 6] },
  },
  breakdowns: {
    strategy: [row('MACD', 2, true), row('RSI', 4, true)],
    horizon: [row('4w', 6, true)],
    side: [row('bearish', 0, true), row('bullish', 6, true)],
    month: [
      { ...row('2026-09', 12, false), tp1_rate: null, tp1_rate_n: null, beat_all_out: 75 },
      { ...row('2026-10', 6, true), tp1_rate: null, tp1_rate_n: null },
    ],
  },
  thin_n: 10,
  population: { filled: 8, partial: 6, unreadable: 0 },
  scope: { from: null, to: null, ledger: 'main', strategy: null, horizon: null, direction: null },
  n: 8,
};
