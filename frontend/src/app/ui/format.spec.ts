import { describe, expect, it } from 'vitest';

import { amount, held, money, signed, timeInZone } from './format';

/* No prior spec file existed for format.ts; timeInZone is new (Watchlist
 * Earnings calendar) and carries real cross-timezone/DST behaviour worth
 * pinning directly rather than only through the component that uses it. */

describe('timeInZone', () => {
  it('renders the same instant differently in two timezones', () => {
    // 20:00 UTC on a summer date is 22:00 in Berlin (CEST, UTC+2).
    const iso = '2026-09-03T20:00:00+00:00';
    expect(timeInZone(iso, 'UTC')).toBe('20:00');
    expect(timeInZone(iso, 'Europe/Berlin')).toBe('22:00');
  });

  it('shifts the Berlin offset correctly across the DST boundary', () => {
    // Winter: CET is UTC+1, not the summer's UTC+2.
    const winter = '2026-01-15T20:00:00+00:00';
    expect(timeInZone(winter, 'Europe/Berlin')).toBe('21:00');
  });

  it('always renders 24-hour HH:MM regardless of viewer locale', () => {
    // en-GB is pinned explicitly so this never flips to a 12-hour clock.
    expect(timeInZone('2026-09-03T00:30:00+00:00', 'UTC')).toBe('00:30');
    expect(timeInZone('2026-09-03T13:05:00+00:00', 'UTC')).toBe('13:05');
  });

  it('renders an em dash for null, undefined or an unparseable string', () => {
    expect(timeInZone(null, 'UTC')).toBe('—');
    expect(timeInZone(undefined, 'UTC')).toBe('—');
    expect(timeInZone('not a date', 'UTC')).toBe('—');
  });
});

describe('held (v80 cell contract: minutes always present)', () => {
  it('renders minutes alone under an hour', () => {
    expect(held(0.75)).toBe('45m');
    expect(held(0.5)).toBe('30m');
  });

  it('keeps zero minutes under a day', () => {
    expect(held(3)).toBe('3h 0m');
    expect(held(5.2)).toBe('5h 12m');
  });

  it('keeps zero parts past a day', () => {
    expect(held(98.25)).toBe('4d 2h 15m');
    expect(held(96 + 5 / 60)).toBe('4d 0h 5m');
    expect(held(48)).toBe('2d 0h 0m');
    expect(held(24.25)).toBe('1d 0h 15m');
  });

  it('renders "0m" rather than blank for a duration under a minute', () => {
    expect(held(0)).toBe('0m');
  });

  it('carries a rounded minute into the hour', () => {
    expect(held(59.999 / 60)).toBe('1h 0m');
  });

  it('renders an em dash for null or undefined', () => {
    expect(held(null)).toBe('—');
    expect(held(undefined)).toBe('—');
  });
});

describe('signed', () => {
  it('prefixes a plus so gain is legible without colour', () => {
    expect(signed(1.5)).toBe('+1.50');
  });

  it('uses a real minus sign, not a hyphen', () => {
    // U+2212. A hyphen is narrower than a digit and breaks tabular alignment
    // down a column, which is the entire reason numerics are mono here.
    expect(signed(-1.5)).toBe('−2.00'.replace('2.00', '1.50'));
  });

  it('renders zero without a sign, because zero has none', () => {
    expect(signed(0)).toBe('0.00');
  });

  it('renders absence as the em dash, not as zero', () => {
    expect(signed(null)).toBe('—');
    expect(signed(undefined)).toBe('—');
  });

  it('honours a decimals override', () => {
    expect(signed(1.5, 1)).toBe('+1.5');
  });
});

describe('amount (v85: the hero balance figure needs grouped thousands)', () => {
  it('groups thousands so a six-figure balance is legible', () => {
    expect(amount(997480.01, '€')).toBe('997,480.01 €');
  });

  it('carries no sign -- it names a level, not a movement', () => {
    expect(amount(-5, '€')).toBe('-5.00 €');
  });

  it('renders absence as the em dash, not as zero', () => {
    expect(amount(null, '€')).toBe('—');
  });
});

describe('money', () => {
  it('groups thousands and signs a gain', () => {
    expect(money(12345.6, '€')).toBe('+12,345.60 €');
  });

  it('signs a loss with its native minus, not a doubled one', () => {
    expect(money(-1234.5, '€')).toBe('-1,234.50 €');
  });

  it('renders absence as the em dash, not as zero', () => {
    expect(money(null, '€')).toBe('—');
  });
});
