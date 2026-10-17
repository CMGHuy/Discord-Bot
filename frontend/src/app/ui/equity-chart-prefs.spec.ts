import { describe, expect, it } from 'vitest';

import {
  EQUITY_BASIS_KEY,
  EQUITY_TF_KEY,
  readEquityChartPrefs,
  writeEquityChartPrefs,
} from './equity-chart-prefs';

describe('equity-chart-prefs', () => {
  it('defaults to daily candles on the open + closed basis', () => {
    expect(readEquityChartPrefs({})).toEqual({ tf: '1D', basis: 'mtm' });
  });

  it('reads a stored timeframe and basis', () => {
    expect(readEquityChartPrefs({ 'dashboard.equity.tf': '4H', 'dashboard.equity.basis': 'realized' }))
      .toEqual({ tf: '4H', basis: 'realized' });
  });

  it('falls back per key when a stored value is unreadable', () => {
    expect(readEquityChartPrefs({ 'dashboard.equity.tf': '1M', 'dashboard.equity.basis': 7 }))
      .toEqual({ tf: '1D', basis: 'mtm' });
    expect(readEquityChartPrefs({ 'dashboard.equity.tf': '1W', 'dashboard.equity.basis': null }))
      .toEqual({ tf: '1W', basis: 'mtm' });
  });

  it('tolerates a missing preferences object', () => {
    expect(readEquityChartPrefs(undefined as never)).toEqual({ tf: '1D', basis: 'mtm' });
  });

  it('writes both keys and leaves every other key alone', () => {
    const next = writeEquityChartPrefs({ 'tape.symbols': ['NVDA'] }, { tf: '1H', basis: 'realized' });
    expect(next[EQUITY_TF_KEY]).toBe('1H');
    expect(next[EQUITY_BASIS_KEY]).toBe('realized');
    expect(next['tape.symbols']).toEqual(['NVDA']);
  });

  it('never writes a value the reader would reject', () => {
    const next = writeEquityChartPrefs({}, { tf: 'bogus' as never, basis: 'mtm' });
    expect(next[EQUITY_TF_KEY]).toBe('1D');
  });
});
