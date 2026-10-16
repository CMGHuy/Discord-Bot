import { describe, expect, it } from 'vitest';

import type { Leg, StatusEvent } from '../../stores/trade-detail.store';
import {
  averageExit, daysUntil, lastHistoryReason, legRsLine, orderWording,
  outcomeTone, pctFrom, sideLabel, statusGroup,
} from './trade-figures';

const leg = (fraction: number | null, exitPrice: number | null, r: number | null = null): Leg =>
  ({ fraction, exitPrice, r, reason: null });

describe('trade figures', () => {
  it.each([
    [null, null], [0, null], [0.099, null], [-0.099, null],
    [0.1, 'pos'], [-0.1, 'neg'], [2.23, 'pos'], [-1, 'neg'],
  ] as const)('uses the neutral band for outcome %s', (value, expected) => {
    expect(outcomeTone(value)).toBe(expected);
  });

  it('weights settled scale-out prices rather than taking the final leg price', () => {
    expect(averageExit([leg(0.5, 147.54), leg(0.5, 145.56)], 145.56))
      .toBeCloseTo(146.55, 10);
  });

  it('renormalizes usable legs and ignores missing or nonpositive weights', () => {
    const legs = [leg(0.25, 100), leg(0.5, 130), leg(null, 900),
      leg(0, 800), leg(-1, 700), leg(0.25, null)];
    expect(averageExit(legs, 90)).toBe(120);
  });

  it('falls back only when no weighted exit is available, preserving zero prices', () => {
    expect(averageExit([], 90)).toBe(90);
    expect(averageExit([leg(null, 100), leg(1, null)], null)).toBeNull();
    expect(averageExit([leg(1, 0)], 90)).toBe(0);
  });

  it.each([
    [' CLOSED ', null, 'closed'], ['active', 100, 'open'],
    [' Partial ', null, 'open'], ['pending', 100, 'pending'],
    ['CANCELLED', null, 'unfilled'], ['expired', 0, 'closed'],
    [null, 100, 'closed'], [null, null, 'unfilled'],
  ] as const)('groups status %s with exit %s', (status, exit, expected) => {
    expect(statusGroup(status, exit)).toBe(expected);
  });

  it.each([
    [' bullish ', 'Long'], ['LONG', 'Long'], [' Bearish', 'Short'],
    ['short ', 'Short'], ['sideways', null], ['', null], [null, null],
  ] as const)('labels direction %s', (direction, expected) => {
    expect(sideLabel(direction)).toBe(expected);
  });

  it.each([
    [null, 'bullish', 100, '—'], ['market', 'bullish', 100, 'Market (long)'],
    ['market', 'short', null, 'Market (short)'], ['market', null, null, 'Market'],
    ['stop_entry', 'long', 101.5, 'Buy stop 101.50'],
    ['stop_entry', 'bearish', 101.5, 'Sell stop 101.50'],
    ['stop_entry', null, 101.5, 'Stop entry 101.50'],
    ['stop_entry', 'bullish', null, 'Buy stop —'],
    ['limit', 'bearish', 1234.5, 'Sell limit 1,234.50'],
    ['limit', 'bullish', 100, 'Buy limit 100.00'],
    ['limit', 'unknown', null, 'Limit entry —'],
    ['stop', 'bullish', 101.5, 'stop 101.50'],
  ] as const)('words order %s / %s / %s', (type, direction, price, expected) => {
    expect(orderWording(type, direction, price)).toBe(expected);
  });

  it.each([
    [100, 110, 10], [100, 90, -10], [100, 0, -100],
    [0, 100, null], [null, 100, null], [100, null, null],
  ] as const)('computes percentage from %s to %s', (from, to, expected) => {
    expect(pctFrom(from, to)).toBe(expected);
  });

  it('renders multiple settled R values including zero, omitting unclosed legs', () => {
    expect(legRsLine([leg(0.5, 147.54, 2.23), leg(0.5, 145.56, 1.43)]))
      .toBe('+2.23R / +1.43R');
    expect(legRsLine([leg(1, null), leg(1, 100, 0), leg(1, 90, -1)]))
      .toBe('0.00R / -1.00R');
  });

  it('omits the leg comparison unless at least two R values are recorded', () => {
    expect(legRsLine([])).toBeNull();
    expect(legRsLine([leg(1, 100, 1), leg(1, null)])).toBeNull();
  });

  it('finds the last nonempty reason without changing history order', () => {
    const history: readonly StatusEvent[] = Object.freeze([
      { status: 'ACTIVE', at: null, reason: 'entry filled' },
      { status: 'CLOSED', at: null, reason: '  target hit  ' },
      { status: 'CLOSED', at: null, reason: '  ' },
      { status: 'CLOSED', at: null, reason: null },
    ]);
    expect(lastHistoryReason(history)).toBe('target hit');
    expect(lastHistoryReason([])).toBeNull();
    expect(lastHistoryReason([{ status: 'ACTIVE', at: null, reason: '  ' }])).toBeNull();
  });

  it.each([
    ['2026-10-20', 4], ['2026-10-20T06:00:00Z', 5],
    ['2026-10-16', 0], ['2026-10-15', 0], ['invalid', null], [null, null],
  ] as const)('counts remaining whole days for %s', (iso, expected) => {
    expect(daysUntil(iso, Date.parse('2026-10-16T00:00:00Z'))).toBe(expected);
  });
});
