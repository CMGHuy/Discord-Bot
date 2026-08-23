import { describe, expect, it } from 'vitest';

import { monthLabel, monthMatrix } from './calendar.helpers';

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
