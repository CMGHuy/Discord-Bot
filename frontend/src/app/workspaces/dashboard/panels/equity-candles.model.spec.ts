import { describe, expect, it } from 'vitest';

import { EquityCandle } from '../../../api/models';
import {
  ACCOUNT_LABEL,
  approxCaption,
  candleLabel,
  emptyMessage,
  readoutParts,
  seamIndex,
  toChartTime,
  toSeriesData,
} from './equity-candles.model';

function candle(overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t: '2026-10-16', o: 10120.5, h: 10210, l: 10090.2, c: 10180.4,
           change: 59.9, change_pct: 0.59, samples: 78, skipped: 0, approx: false, ...overrides };
}

const COLORS = { up: 'UP', down: 'DOWN', faint: 'FAINT' };

describe('equity candles model', () => {
  it('keeps daily and weekly times as business-day strings', () => {
    expect(toChartTime('2026-10-16', '1D')).toBe('2026-10-16');
    expect(toChartTime('2026-10-12', '1W')).toBe('2026-10-12');
  });

  it('reads intraday times as New York wall clock', () => {
    // 09:00 New York, whatever the offset, is 09:00 on the axis.
    expect(toChartTime('2026-10-16T09:00:00-04:00', '1H')).toBe(Date.UTC(2026, 9, 16, 9) / 1000);
    expect(toChartTime('2026-12-01T12:00:00-05:00', '4H')).toBe(Date.UTC(2026, 11, 1, 12) / 1000);
  });

  it('keeps the series strictly ascending across the fall-back hour', () => {
    const data = toSeriesData([
      candle({ t: '2026-11-01T01:00:00-04:00' }),
      candle({ t: '2026-11-01T01:00:00-05:00' }),
      candle({ t: '2026-11-01T02:00:00-05:00' }),
    ], '1H', COLORS);
    const times = data.map((p) => p.time as number);
    expect(times[1]).toBe(times[0] + 1);
    expect(times[2]).toBeGreaterThan(times[1]);
  });

  it('draws an approx candle hollow and a measured one with the series colours', () => {
    const [up, down, measured] = toSeriesData([
      candle({ o: 100, c: 110, approx: true }),
      candle({ t: '2026-10-19', o: 110, c: 90, approx: true }),
      candle({ t: '2026-10-20', approx: false }),
    ], '1D', COLORS);
    expect(up).toMatchObject({ color: 'transparent', borderColor: 'UP', wickColor: 'FAINT' });
    expect(down).toMatchObject({ color: 'transparent', borderColor: 'DOWN', wickColor: 'FAINT' });
    expect(measured.color).toBeUndefined();
    expect(measured).toMatchObject({ time: '2026-10-20', open: 10120.5, high: 10210, low: 10090.2, close: 10180.4 });
  });

  it('labels candles by timeframe', () => {
    expect(candleLabel('2026-10-16', '1D')).toBe('Oct 16, 2026');
    expect(candleLabel('2026-10-12', '1W')).toBe('Week of Oct 12, 2026');
    expect(candleLabel('2026-10-16T13:00:00-04:00', '4H')).toBe('Oct 16, 2026 13:00 ET');
  });

  it('builds the readout: when, O H L C, change, % vs prev close, basis', () => {
    expect(readoutParts(candle(), 'mtm', '€', '1D')).toEqual([
      'Oct 16, 2026', 'O 10,120.50', 'H 10,210.00', 'L 10,090.20', 'C 10,180.40',
      '+59.90 €', '+0.59% vs prev close', 'Open + closed',
    ]);
  });

  it('names the closed-trades basis and flags approx and skipped positions', () => {
    const parts = readoutParts(candle({ approx: true, skipped: 2, change: -5, change_pct: -0.05 }),
                               'realized', '$', '1D');
    expect(parts).toContain('Closed trades only');
    expect(parts).toContain('approx');
    expect(parts).toContain('2 positions not counted');
    expect(parts).toContain('-5.00 $');
    expect(readoutParts(candle({ skipped: 1 }), 'mtm', '€', '1D')).toContain('1 position not counted');
  });

  it('shows a dash when the percentage has no base', () => {
    expect(readoutParts(candle({ change_pct: null }), 'mtm', '€', '1D')).toContain('— vs prev close');
  });

  it('words the empty state by timeframe', () => {
    expect(emptyMessage('1H', '2026-10-20T13:35:00Z'))
      .toBe('No hourly samples yet — recording started Oct 20, 2026');
    expect(emptyMessage('4H', '2026-10-20T13:35:00Z'))
      .toBe('No hourly samples yet — recording started Oct 20, 2026');
    expect(emptyMessage('1H', null)).toBe('No equity samples yet');
    expect(emptyMessage('1D', null)).toBe('No equity samples yet');
  });

  it('dates the approx caption in New York', () => {
    // 02:00 UTC on the 21st is still the 20th in New York.
    expect(approxCaption('2026-10-21T02:00:00Z'))
      .toBe('Before Oct 20, 2026: rebuilt from daily bars — ranges are outer bounds');
    expect(approxCaption(null))
      .toBe('Before recording started: rebuilt from daily bars — ranges are outer bounds');
  });

  it('puts the seam on the first measured candle after a rebuilt one', () => {
    expect(seamIndex([candle({ approx: true }), candle({ approx: true }), candle(), candle()])).toBe(2);
    expect(seamIndex([candle(), candle()])).toBe(-1);
    expect(seamIndex([candle({ approx: true })])).toBe(-1);
    expect(seamIndex([])).toBe(-1);
  });

  it('states the account label exactly', () => {
    expect(ACCOUNT_LABEL).toBe('Paper account · before tax and costs');
  });
});
