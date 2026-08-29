import { describe, expect, it } from 'vitest';

import { BreakdownRow, DecileRow, DriftRow, StrategyRow, TierRow } from '../../stores/analytics.store';
import { breakdownColumns, DECILE_COLUMNS, DRIFT_COLUMNS, STRATEGY_COLUMNS, TIER_COLUMNS } from './analytics.columns';

describe('analytics columns', () => {
  it('renders every plain-text group and label column', () => {
    const breakdown: BreakdownRow = { key: 'AAPL', n: 5, wins: 3, losses: 2, win_rate: 60, expectancy_r: 0.2, avg_r: 0.2, profit_factor: 1.4, total_pnl: 210 };
    const strategy: StrategyRow = { strategy: 'RSI', status: 'VALIDATED', n: 10, win_rate: 55, expectancy_r: 0.3, window: 'TRAIN', run_date: null, live_n: 5, live_wr: 50, delta_vs_oos: -5, decayed: false, evidence_decay: 'fresh', gate_description: null, win_rate_series: [] };
    const decile: DecileRow = { decile: 'D3', n: 12, win_rate: 60, expectancy_r: 0.2 };
    const tier: TierRow = { tier: 'A', n: 4, win_rate: 70, expectancy_r: 0.4, expected_band: '>=80', ok: true };
    const drift: DriftRow = { strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8, live_wr: 40, delta_wr: -25, drift_alert: true };

    expect(breakdownColumns('Ticker').find((column) => column.key === 'key')?.value?.(breakdown)).toBe('AAPL');
    expect(STRATEGY_COLUMNS.find((column) => column.key === 'strategy')?.value?.(strategy)).toBe('RSI');
    expect(DECILE_COLUMNS.find((column) => column.key === 'decile')?.value?.(decile)).toBe('D3');
    expect(TIER_COLUMNS.find((column) => column.key === 'expected_band')?.value?.(tier)).toBe('>=80');
    expect(DRIFT_COLUMNS.find((column) => column.key === 'strategy')?.value?.(drift)).toBe('MACD');
  });
});