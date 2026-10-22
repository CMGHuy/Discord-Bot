import { describe, expect, it } from 'vitest';

import {
  SCOPE_PRESETS, SCOPE_PRESET_KEY, readScopePreset, writeScopePreset,
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

describe('scope preset preference (v181)', () => {
  it('lists the presets in control order', () => {
    expect(SCOPE_PRESETS).toEqual(['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', 'All']);
    expect(SCOPE_PRESET_KEY).toBe('dashboard.scope.preset');
  });

  it('defaults to 1D, reads a stored preset, and falls back on anything else', () => {
    expect(readScopePreset({})).toBe('1D');
    expect(readScopePreset(undefined as never)).toBe('1D');
    expect(readScopePreset({ 'dashboard.scope.preset': '3M' })).toBe('3M');
    expect(readScopePreset({ 'dashboard.scope.preset': '2W' })).toBe('1D');
    expect(readScopePreset({ 'dashboard.scope.preset': 7 })).toBe('1D');
    // Range is never a stored value (spec § 1): it reads as the default.
    expect(readScopePreset({ 'dashboard.scope.preset': 'Range' })).toBe('1D');
  });

  it('writes the key, leaves every other key alone, and never writes a bad value', () => {
    const next = writeScopePreset({ 'dashboard.equity.tf': '4H' }, 'YTD');
    expect(next).toEqual({ 'dashboard.equity.tf': '4H', 'dashboard.scope.preset': 'YTD' });
    expect(writeScopePreset({}, 'bogus' as never)[SCOPE_PRESET_KEY]).toBe('1D');
  });
});
