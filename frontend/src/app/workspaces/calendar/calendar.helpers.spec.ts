import { describe, expect, it } from 'vitest';

import { cellValue, monthLabel, monthMatrix } from './calendar.helpers';

describe('monthMatrix', () => {
  it('lays out Monday-first weeks of seven', () => {
    const weeks = monthMatrix('2026-08');
    expect(weeks.every((week) => week.length === 7)).toBe(true);
    // 2026-08-01 is a Saturday, so the first row starts on Mon 2026-07-27.
    expect(weeks[0][0].date).toBe('2026-07-27');
    expect(weeks[0][0].inMonth).toBe(false);
  });

  it('marks the days that belong to the requested month', () => {
    const inMonth = monthMatrix('2026-08')
      .flat()
      .filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(31);
    expect(inMonth[0].date).toBe('2026-08-01');
    expect(inMonth[30].date).toBe('2026-08-31');
  });

  it('marks weekends, which never carry a close', () => {
    const cells = monthMatrix('2026-08').flat();
    const saturday = cells.find((cell) => cell.date === '2026-08-01');
    const monday = cells.find((cell) => cell.date === '2026-08-03');
    expect(saturday?.weekend).toBe(true);
    expect(monday?.weekend).toBe(false);
  });

  it('handles February in a leap year', () => {
    const inMonth = monthMatrix('2024-02')
      .flat()
      .filter((cell) => cell.inMonth);
    expect(inMonth).toHaveLength(29);
    expect(inMonth[28].date).toBe('2024-02-29');
  });

  it('handles a month that starts on a Monday without a blank leading week', () => {
    // 2026-06-01 is a Monday.
    const weeks = monthMatrix('2026-06');
    expect(weeks[0][0].date).toBe('2026-06-01');
    expect(weeks[0][0].inMonth).toBe(true);
  });

  it('pads the trailing week rather than emitting a short row', () => {
    const weeks = monthMatrix('2026-08');
    const last = weeks[weeks.length - 1];
    expect(last).toHaveLength(7);
    expect(last[6].inMonth).toBe(false);
  });

  it('zero-pads dates so they match the API day keys exactly', () => {
    // A `2026-8-3` here would silently miss every dayIndex lookup.
    const cells = monthMatrix('2026-08').flat();
    expect(cells.every((cell) => /^\d{4}-\d{2}-\d{2}$/.test(cell.date))).toBe(true);
  });
});

describe('monthLabel', () => {
  it('renders a human month and year', () => {
    expect(monthLabel('2026-08')).toBe('August 2026');
    expect(monthLabel('2026-01')).toBe('January 2026');
  });
});

describe('cellValue', () => {
  const DAY = { date: '2026-04-24', net_r: 1.2, net_pnl_amount: 480, trade_count: 12, win_rate: 75 };

  it('formats R, currency, count and win-rate with their own semantic tones', () => {
    expect(cellValue(DAY, 'r')).toEqual({ value: 1.2, text: '+1.20R', tone: 'pos' });
    expect(cellValue(DAY, 'currency').text).toContain('480');
    expect(cellValue(DAY, 'trades')).toEqual({ value: 12, text: '12', tone: 'neutral' });
    expect(cellValue(DAY, 'win_rate')).toEqual({ value: 75, text: '75%', tone: 'neutral' });
  });

  it('shows "0" for a no-trade day rather than leaving the cell blank (2026-09-14)', () => {
    // The 'empty' tone is kept (no pos/neg colour for a day with nothing to
    // colour), but the text is now the honest, measured "0" -- a blank
    // trading-day cell reads as a rendering fault, not as "nothing to see".
    for (const metric of ['r', 'currency', 'trades', 'win_rate'] as const) {
      const result = cellValue({ ...DAY, trade_count: 0, win_rate: null }, metric);
      expect(result.tone).toBe('empty');
      expect(result.text).toBe('0');
      expect(result.value).toBe(0);
    }
  });
});
