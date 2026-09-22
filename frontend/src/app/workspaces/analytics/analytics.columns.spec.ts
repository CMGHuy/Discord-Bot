import { describe, expect, it } from 'vitest';

import { DecileRow, DriftRow, StrategyRow, TierRow } from '../../stores/analytics.store';
import { DECILE_COLUMNS, DRIFT_COLUMNS, soakLabel, STRATEGY_COLUMNS, TIER_COLUMNS } from './analytics.columns';

describe('analytics columns', () => {
  it('renders every plain-text group and label column', () => {
    const strategy: StrategyRow = { strategy: 'RSI', status: 'VALIDATED', n: 10, win_rate: 55, expectancy_r: 0.3, window: 'TRAIN', run_date: null, live_n: 5, live_wr: 50, delta_vs_oos: -5, decayed: false, evidence_decay: 'fresh', gate_description: null, win_rate_series: [] };
    const decile: DecileRow = { decile: 'D3', n: 12, win_rate: 60, expectancy_r: 0.2 };
    const tier: TierRow = { level: 3, n: 4, win_rate: 70, expectancy_r: 0.4 };
    const drift: DriftRow = { strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8, live_wr: 40, delta_wr: -25, drift_alert: true };

    expect(STRATEGY_COLUMNS.find((column) => column.key === 'strategy')?.value?.(strategy)).toBe('RSI');
    expect(DECILE_COLUMNS.find((column) => column.key === 'decile')?.value?.(decile)).toBe('D3');
    expect(TIER_COLUMNS(20).find((column) => column.key === 'level')?.value?.(tier)).toBe('3');
    expect(DRIFT_COLUMNS.find((column) => column.key === 'strategy')?.value?.(drift)).toBe('MACD');
  });

  /* A screenshot pass (v94 V2) once caught the Strategy breakdown table's
   * Soak column rendering the raw `soak_verdict` object -- e.g.
   * `{"clauses":{"entry_parity":false,"n":false,"non_inferior":false},
   * "n_closed":1,"pass":false}` -- straight into a table cell via
   * `JSON.stringify`. `soakLabel` is the fix: a short, human verdict. */
  it('reads the shadow-soak verdict as a short verdict, never the raw object', () => {
    expect(soakLabel({ pass: false, n_closed: 1, clauses: { n: false, non_inferior: false, entry_parity: true } }))
      .toBe('FAIL · n=1');
    expect(soakLabel({ pass: true, n_closed: 34, clauses: { n: true, non_inferior: true, entry_parity: true } }))
      .toBe('PASS · n=34');
    expect(soakLabel(null)).toBeNull();
    expect(soakLabel(undefined)).toBeNull();
  });
});
