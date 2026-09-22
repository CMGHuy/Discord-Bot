import { describe, expect, it } from 'vitest';

import { monthBars } from './analytics.store';

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
});
