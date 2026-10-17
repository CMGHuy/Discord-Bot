import { describe, expect, it } from 'vitest';

import { LiveLossRow } from '../../api/models';
import { DecileRow, DriftRow, StrategyRow, TierRow } from '../../stores/analytics.store';
import { ABSENT } from '../../ui/format';
import {
  DECILE_COLUMNS,
  DRIFT_COLUMNS,
  LIVE_LOSS_COLUMNS,
  LIVE_LOSS_LOOKS_CAVEAT,
  LIVE_LOSS_MEANING,
  liveLossCountsLine,
  liveLossLabel,
  REGISTRY_CONTEXT_LABEL,
  soakLabel,
  STRATEGY_COLUMNS,
  TIER_COLUMNS,
} from './analytics.columns';

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

describe('live loss watch columns (v164)', () => {
  const row: LiveLossRow = {
    source: 'confluence', strategy: 'ALL', horizon: null, live_n: 24, live_wr: 41.7,
    live_expr: -0.25, bound_upper: -0.04, alert: true, registry_status: 'WEAK',
    registry_window_kind: 'VALIDATION', registry_run_date: '2026-05-01', registry_expr: -0.05,
  };
  const value = (key: string, r: LiveLossRow = row) =>
    LIVE_LOSS_COLUMNS.find((column) => column.key === key)?.value?.(r);

  it('labels a row by source, strategy and horizon, pooled when the horizon is null', () => {
    expect(liveLossLabel(row)).toBe('confluence / ALL / pooled');
    expect(liveLossLabel({ ...row, horizon: '4w' })).toBe('confluence / ALL / 4w');
    expect(value('row')).toBe('confluence / ALL / pooled');
  });

  it('formats the live figures and flags only an alert row', () => {
    expect(value('live_n')).toBe('24');
    expect(value('live_wr')).toBe('41.7%');
    expect(String(value('live_expr')).startsWith('\u2212')).toBe(true);
    expect(String(value('bound_upper'))).toContain('0.040');
    expect(value('alert')).toBe('BELOW ZERO');
    expect(value('alert', { ...row, alert: false })).toBe(ABSENT);
    expect(value('live_wr', { ...row, live_wr: null })).toBe(ABSENT);
    expect(value('bound_upper', { ...row, bound_upper: null })).toBe(ABSENT);
  });

  it('heads every registry column as registry context', () => {
    const registry = LIVE_LOSS_COLUMNS.filter((column) => column.key.startsWith('registry_'));
    expect(registry.map((column) => column.key)).toEqual(
      ['registry_status', 'registry_window_kind', 'registry_run_date', 'registry_expr']);
    expect(registry.every((column) => column.header.startsWith('Registry'))).toBe(true);
    expect(value('registry_window_kind')).toBe('VALIDATION');
    expect(value('registry_window_kind', { ...row, registry_window_kind: null })).toBe(ABSENT);
  });

  it('carries the pre-registered wording verbatim', () => {
    expect(LIVE_LOSS_MEANING).toBe(
      'live ExpR for this row is below zero with ~90% one-sided confidence — not "the edge decayed versus its backtest"');
    expect(LIVE_LOSS_LOOKS_CAVEAT).toBe(
      '11 correlated looks per week; flags are prompts to investigate, not verdicts');
    expect(REGISTRY_CONTEXT_LABEL).toBe('backtest context — not comparable');
  });

  it('states every exclusion count, zeros included, and manual closes as included', () => {
    expect(liveLossCountsLine({ no_source: 2, unknown_strategy: 0, no_r: 1, manual_close: 3, no_entry_date: 0 }))
      .toBe('Excluded, counted: no source 2 · unknown strategy 0 · no R 1 · no entry date 0. Manual closes included: 3.');
    expect(liveLossCountsLine({}))
      .toBe('Excluded, counted: no source 0 · unknown strategy 0 · no R 0 · no entry date 0. Manual closes included: 0.');
  });

  it('gives the drift decay column a plain-text value now that a table renders it', () => {
    const drift: DriftRow = { strategy: 'MACD', oos_n: 20, oos_wr: 65, live_n: 8, live_wr: 40, delta_wr: -25, drift_alert: true };
    const decay = DRIFT_COLUMNS.find((column) => column.key === 'drift_alert');
    expect(decay?.value?.(drift)).toBe('DECAY');
    expect(decay?.value?.({ ...drift, drift_alert: false })).toBe(ABSENT);
  });
});
