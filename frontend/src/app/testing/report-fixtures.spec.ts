import { describe, expect, it } from 'vitest';

import { ATTRIBUTION, GATES, NOT_RUN, ok } from './report-fixtures';

/* The fixtures are hand-written; these key lists are what the real builders
 * emit (`expectancy_attribution.build_report`, v146, and
 * `gate_counterfactual_report.build_report`, v147), dumped from each module's
 * own test population on 2026-10-15. A fixture that drifts from the wire
 * fails here, before a Reports spec passes against a shape the server never
 * sends. */

const sorted = (value: object): string[] => Object.keys(value).sort();
const keyset = (...keys: string[]): string[] => [...keys].sort();

const V146_TOP = keyset('generated_at', 'verdict', 'verdict_of_record', 'looks', 'seed', 'provenance', 'populations');
const V146_RECORD = keyset('verdict', 'date', 'n');
const V146_POPULATION = keyset('window', 'n', 'monotonicity', 'factors', 'buckets', 'splits', 'notes');
const V146_WINDOW = keyset('first_week', 'last_week');
const V146_MONO = keyset(
  'n', 'spearman_rho', 'tercile_spread', 'ci_low', 'ci_high', 'p', 'inverted', 'tercile_n', 'rr_by_tercile');
const V146_QUARTILES = keyset('p25', 'median', 'p75');
const V146_FACTOR = keyset('key', 'n', 'n_pos', 'n_zero', 'delta', 'ci_low', 'ci_high', 'p', 'q');
const V146_BUCKET = keyset(
  'label', 'n', 'win_rate', 'exp_r', 'exp_r_gross', 'thin', 'q', 'delta', 'ci_low', 'ci_high', 'p');
const V146_GROUPINGS = [
  'confidence_decile', 'confidence_level', 'confluence', 'regime2_state', 'rs_quintile',
  'direction', 'horizon', 'earnings', 'earnings_in_hold',
];

const V147_TOP = keyset('generated_at', 'live_window', 'bh_family', 'seed', 'limitations', 'cells', 'rows');
const V147_CELL = keyset(
  'gate', 'population', 'verdict', 'n', 'taken_n', 'verdict_of_record', 'latest', 'in_sample', 'note');
const V147_LATEST = keyset('difference', 'ci_low', 'ci_high', 'q', 'p');
const V147_ROW = keyset(
  'gate', 'reason', 'population', 'blocked_n', 'no_plan_n', 'fill_rate', 'blocked_exp_r',
  'blocked_win_rate', 'taken_n', 'taken_exp_r', 'taken_win_rate', 'taken_realised_exp_r',
  'near_miss_n', 'near_miss_exp_r', 'rest_n', 'rest_exp_r', 'dollar_risk', 'over_cap', 'in_sample');

describe('ATTRIBUTION fixture carries the v146 wire shape', () => {
  it('has the top-level keys and the verdict-of-record keys', () => {
    expect(sorted(ATTRIBUTION)).toEqual(V146_TOP);
    expect(sorted(ATTRIBUTION.verdict_of_record)).toEqual(V146_RECORD);
  });

  it('gives every population the window, monotonicity, factor, bucket and split keys', () => {
    for (const population of [ATTRIBUTION.populations.live!, ATTRIBUTION.populations.train!]) {
      expect(sorted(population)).toEqual(V146_POPULATION);
      expect(sorted(population.window)).toEqual(V146_WINDOW);
      expect(sorted(population.monotonicity)).toEqual(V146_MONO);
      population.monotonicity.rr_by_tercile.forEach((q) => expect(sorted(q)).toEqual(V146_QUARTILES));
      population.factors.forEach((f) => expect(sorted(f)).toEqual(V146_FACTOR));
      expect(sorted(population.splits)).toEqual(['direction', 'horizon']);
      for (const axis of Object.values(population.splits)) {
        Object.values(axis).forEach((mono) => expect(sorted(mono)).toEqual(V146_MONO));
      }
    }
  });

  it('uses only real grouping names, and plain buckets carry exactly the bucket keys', () => {
    for (const population of [ATTRIBUTION.populations.live!, ATTRIBUTION.populations.train!]) {
      for (const [grouping, buckets] of Object.entries(population.buckets)) {
        expect(V146_GROUPINGS).toContain(grouping);
        if (grouping !== 'confidence_decile') {
          buckets.forEach((b) => expect(sorted(b)).toEqual(V146_BUCKET));
        }
      }
    }
  });

  it('states win rate in percent, as v146 computes it', () => {
    const rates = Object.values(ATTRIBUTION.populations.live!.buckets).flat().map((b) => b.win_rate!);
    expect(rates.every((rate) => rate > 1)).toBe(true);
  });
});

describe('GATES fixture carries the v147 wire shape', () => {
  it('has the top-level keys', () => {
    expect(sorted(GATES)).toEqual(V147_TOP);
  });

  it('gives every cell the cell keys and every reading the latest keys', () => {
    for (const cell of GATES.cells) {
      expect(sorted(cell)).toEqual(V147_CELL);
      if (cell.latest) expect(sorted(cell.latest)).toEqual(V147_LATEST);
      if (cell.verdict_of_record) expect(sorted(cell.verdict_of_record)).toEqual(V146_RECORD);
    }
  });

  it('gives every detail row the row keys', () => {
    GATES.rows.forEach((row) => expect(sorted(row)).toEqual(V147_ROW));
  });

  it('states win rate as a fraction, as v147 computes it', () => {
    const rates = GATES.rows.flatMap((r) => [r.blocked_win_rate!, r.taken_win_rate!]);
    expect(rates.every((rate) => rate >= 0 && rate <= 1)).toBe(true);
  });
});

describe('envelope helpers', () => {
  it('ok() wraps a result with its own generated_at', () => {
    expect(ok(GATES)).toEqual({ status: 'ok', generated_at: GATES.generated_at, result: GATES });
  });

  it('NOT_RUN is the not_run envelope', () => {
    expect(NOT_RUN).toEqual({ status: 'not_run', generated_at: null, result: null });
  });
});
