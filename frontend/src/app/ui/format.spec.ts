import { describe, expect, it } from 'vitest';

import { timeInZone } from './format';

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
