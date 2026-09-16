import { describe, expect, it } from 'vitest';

import { monthBars, rateBars, zeroFilledBars } from './analytics.store';

describe('analytics bar rows (v89 spec §3.1)', () => {
  it('keeps a month\'s return signed -- the bar list draws the sign', () => {
    expect(monthBars([
      { month: '2026-07', return_pct: -0.08, n: 300 },
      { month: '2026-09', return_pct: 0.01, n: 48 },
    ])).toEqual([
      { label: '2026-07', value: -0.08, n: 300 },
      { label: '2026-09', value: 0.01, n: 48 },
    ]);
  });

  it('maps a rate bucket to label, value and n, withholding a null rate', () => {
    expect(rateBars([
      { bucket: '0h-2h', n: 357, win_rate: 64.705882, avg_return_pct: null },
      { bucket: '<1.5', n: 0, win_rate: null, avg_return_pct: null },
    ])).toEqual([
      { label: '0h-2h', value: 64.705882, n: 357, withheld: false },
      { label: '<1.5', value: null, n: 0, withheld: true },
    ]);
  });

  it('zero-fills a segment and keeps n out of the label', () => {
    const rows = zeroFilledBars(
      [{ key: 'bullish', n: 30, wins: 16, losses: 14, win_rate: 53.3, expectancy_r: 0.1, avg_r: 0.1, profit_factor: 1.1, total_pnl: 10 }] as never,
      [['bullish', 'Long'], ['bearish', 'Short']],
      20,
    );
    expect(rows).toEqual([
      { label: 'Long', value: 53.3, n: 30, withheld: false },
      { label: 'Short', value: null, n: 0, withheld: true },
    ]);
  });
});
