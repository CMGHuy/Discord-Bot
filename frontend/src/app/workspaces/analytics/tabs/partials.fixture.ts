import {
  AnalyticsPartials, PartialsBreakdownRow, PartialsEnding, PartialsEndingCard, PartialsEndingRow, PartialsKpis,
  PartialsOddsSegment, PartialsRunnerEndings, PartialsShare,
} from '../../../api/models';

/** v142 — one `/analytics/partials` payload, shaped from the Python test
 *  book (`tests/analytics/test_partials.py::_book`). Shared by the store
 *  and tab specs so both read the same response. */
const KPIS: PartialsKpis = {
  tp1_rate: 85.7, tp1_rate_n: 7, tp1_tp2_rate: 25, tp1_tp2_n: 4,
  beat_all_out: 80, beat_all_out_n: 5, mean_runner_delta_r: 0.324,
  median_tp1_exit_sessions: 2, tp1_exit_n: 5,
};

const row = (key: string, n: number, thin: boolean): PartialsBreakdownRow => ({ ...KPIS, key, n, thin });

/** v219 — the index's worked `runner_endings` block for `_book()` + `MANUAL`:
 *  A tp2, C trail, B floor, D manual ("other"); F (no TP2) is out; D is not
 *  decidable (manual close), so 3 decidable runners and no giveback. */
type RTuple = [number, number | null, number | null, number | null, number | null];
type PathTuple = [number, number | null, number | null, number | null];
const share = (n: number, denominator: number, pct: number | null, lo: number | null, hi: number | null): PartialsShare =>
  ({ n, denominator, share: pct, lo, hi, thin: true });
const endingRow = (ending: PartialsEnding, s: PartialsShare, r: RTuple, path: PathTuple,
  sessions: number | null): PartialsEndingRow => ({
  ending, ...s, r_n: r[0], avg_r: r[1], median_r: r[2], total_r: r[3], vs_all_out: r[4],
  path_n: path[0], best_r: path[1], progress: path[2], gave_back: path[3], sessions,
});
const cardsOf = (rows: PartialsEndingRow[]): PartialsEndingCard[] =>
  (['tp2', 'floor', 'giveback', 'trail'] as const).map((ending) => {
    const { n, denominator, share: pct, lo, hi, thin } = rows.find((r) => r.ending === ending)!;
    return { ending, n, denominator, share: pct, lo, hi, thin };
  });
const seg = (ending: PartialsOddsSegment['ending'], n: number, pct: number | null, lo: number | null,
  hi: number | null): PartialsOddsSegment => ({ ending, n, share: pct, lo, hi });

const QUARTER = share(1, 4, 25, 4.6, 69.9);
const ROWS: PartialsEndingRow[] = [
  endingRow('tp2', QUARTER, [1, 4, 4, 2, 1], [1, 4.2, 100, 0.2], 4),
  endingRow('trail', QUARTER, [1, 3, 3, 1.5, 0.5], [1, 3.6, 80, 0.6], 2),
  endingRow('floor', QUARTER, [1, 1.34, 1.34, 0.67, -0.33], [1, 2.6, 30, 1.26], 2),
  endingRow('other', QUARTER, [1, 2.5, 2.5, 1.25, 0.25], [0, null, null, null], 2),
  endingRow('giveback', share(0, 3, 0, 0, 56.2), [0, null, null, null, null], [0, null, null, null], null),
];
const THIRD = (ending: PartialsOddsSegment['ending']) => seg(ending, 1, 33.3, 6.1, 79.2);
const HALF = [seg('tp2', 1, 50, 9.5, 90.5), seg('trail', 1, 50, 9.5, 90.5),
  seg('floor', 0, 0, 0, 65.8), seg('other', 0, 0, 0, 65.8)];

export const RUNNER_ENDINGS_FIXTURE: PartialsRunnerEndings = {
  n: 4, decidable: 3, cards: cardsOf(ROWS), rows: ROWS,
  odds: [
    { level: 25, n: 3, thin: true, split: [THIRD('tp2'), THIRD('trail'), THIRD('floor'), seg('other', 0, 0, 0, 56.2)] },
    { level: 50, n: 2, thin: true, split: HALF },
    { level: 75, n: 2, thin: true, split: HALF },
  ],
  excluded: { no_tp2: 1, runner_r_unavailable: 0, manual_close: 1, unpathed: 0, no_tp2_distance: 0 },
};

/** Every runner still open: a measured zero, not an error. */
const NONE = share(0, 0, null, null, null);
const EMPTY_ROWS = (['tp2', 'trail', 'floor', 'other', 'giveback'] as const).map((ending) =>
  endingRow(ending, NONE, [0, null, null, null, null], [0, null, null, null], null));
export const RUNNER_ENDINGS_EMPTY: PartialsRunnerEndings = {
  n: 0, decidable: 0, cards: cardsOf(EMPTY_ROWS), rows: EMPTY_ROWS,
  odds: [25, 50, 75].map((level) => ({
    level, n: 0, thin: true,
    split: (['tp2', 'trail', 'floor', 'other'] as const).map((e) => seg(e, 0, null, null, null)),
  })),
  excluded: { no_tp2: 0, runner_r_unavailable: 0, manual_close: 0, unpathed: 0, no_tp2_distance: 0 },
};

export const PARTIALS_FIXTURE: AnalyticsPartials = {
  kpis: KPIS,
  funnel: [
    { stage: 'filled', n: 8 }, { stage: 'tp1', n: 6 }, { stage: 'runner_closed', n: 5 }, { stage: 'tp2', n: 1 },
  ],
  runner_endings: RUNNER_ENDINGS_FIXTURE,
  counterfactuals: {
    actual_exp_r: 2.324, all_out_exp_r: 2, giveback: [0.2, 1.26, 0.6],
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
    path_unavailable: 1, runner_r_unavailable: 0, giveback_excluded: 2,
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
