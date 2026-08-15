import { describe, expect, it } from 'vitest';

import { ChartPrefs } from './chart-prefs';

describe('ChartPrefs', () => {
  it('shows every layer by default', () => {
    const prefs = new ChartPrefs(new Map());
    expect(prefs.visible()['macd']).toBe(true);
    expect(prefs.visible()['plan']).toBe(true);
  });

  it('remembers a hidden layer', () => {
    const store = new Map<string, string>();
    new ChartPrefs(store).toggle('rsi');
    expect(new ChartPrefs(store).visible()['rsi']).toBe(false);
  });

  it('ignores a corrupt stored value rather than throwing', () => {
    const store = new Map([['sb.chart.layers', '{oops']]);
    expect(new ChartPrefs(store).visible()['macd']).toBe(true);
  });
});
