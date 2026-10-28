import { describe, expect, it } from 'vitest';

import { MINUS, amount, held, money, pct, quantity, rMultiple, riskPct, shareCount, signed, timeInZone } from './format';

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

  it('signs a loss with one true minus, not a hyphen and not a doubled sign (v195 correction 5)', () => {
    expect(money(-1234.5, '€')).toBe('−1,234.50 €');
  });

  it('renders absence as the em dash, not as zero', () => {
    expect(money(null, '€')).toBe('—');
  });
});

describe('quantity (v183: a share count, decimals are a ceiling)', () => {
  it('drops trailing zeros and groups thousands', () => {
    expect(quantity(25)).toBe('25');
    expect(quantity(1234.567)).toBe('1,234.57');
    expect(quantity(12.5)).toBe('12.5');
  });

  it('honours a custom ceiling and shows the placeholder for an absent value', () => {
    expect(quantity(1.23456, 4)).toBe('1.2346');
    expect(quantity(null)).toBe('—');
    expect(quantity(undefined)).toBe('—');
  });
});

describe('shareCount (v194 B4: fractional shares are not rounded to whole)', () => {
  it('renders integers bare and keeps one or two decimals, trailing zeros dropped', () => {
    expect(shareCount(3)).toBe('3');
    expect(shareCount(0.5)).toBe('0.5');
    expect(shareCount(2.7)).toBe('2.7');
    expect(shareCount(2.72)).toBe('2.72');
    expect(shareCount(1234.4)).toBe('1,234.4');
  });

  it('rounds at the third decimal', () => {
    expect(shareCount(1.236)).toBe('1.24');
    expect(shareCount(1.234)).toBe('1.23');
    expect(shareCount(2.999)).toBe('3');
  });

  it('renders a real zero as 0 and absence as the em dash', () => {
    expect(shareCount(0)).toBe('0');
    expect(shareCount(null)).toBe('—');
    expect(shareCount(undefined)).toBe('—');
  });
});

describe('riskPct (v194 B5: a tiny risk never reads as zero)', () => {
  it('renders an exact zero, and -0, as 0.00%', () => {
    expect(riskPct(0)).toBe('0.00%');
    expect(riskPct(-0)).toBe('0.00%');
  });

  it('renders a non-zero value below 0.01 as <0.01%, and 0.01 itself at two decimals', () => {
    expect(riskPct(0.002)).toBe('<0.01%');
    expect(riskPct(0.0099)).toBe('<0.01%');
    expect(riskPct(0.01)).toBe('0.01%');
  });

  it('renders two grouped decimals with the unit, unsigned when positive', () => {
    expect(riskPct(1.234)).toBe('1.23%');
    expect(riskPct(3)).toBe('3.00%');
    expect(riskPct(1234.5)).toBe('1,234.50%');
  });

  it('keeps the sign of a negative value, tiny or not', () => {
    expect(riskPct(-1.234)).toBe('-1.23%');
    expect(riskPct(-0.002)).toBe('-<0.01%');
  });

  it('renders absence as the em dash', () => {
    expect(riskPct(null)).toBe('—');
    expect(riskPct(undefined)).toBe('—');
  });
});

/* v195 section 1.1, correction 5: colour is never the only cue. Every P&L, R and
 * return figure carries an explicit sign, and a loss carries U+2212, the
 * same glyph signed() has always used: a hyphen is narrower than a digit
 * even in a mono face, so a column of hyphen-negatives does not align. */
describe('v195: a true minus on every signed figure', () => {
  const HYPHEN = '-';

  it('exports the minus sign once, as U+2212', () => {
    expect(MINUS).toBe('−');
    expect(MINUS).not.toBe(HYPHEN);
  });

  it('signs pct both ways and keeps its decimals', () => {
    expect(pct(1.5)).toBe('+1.50%');
    expect(pct(-1.5)).toBe('−1.50%');
    expect(pct(-12.34, 1)).toBe('−12.3%');
    expect(pct(0)).toBe('0.00%');
    expect(pct(-0)).toBe('0.00%');
    expect(pct(null)).toBe('—');
    expect(pct(undefined)).toBe('—');
  });

  it('signs money both ways, groups the magnitude and keeps the unit suffix', () => {
    expect(money(12345.6, '€')).toBe('+12,345.60 €');
    expect(money(-212, '$', 0)).toBe('−212 $');
    expect(money(-1234567.891, '$')).toBe('−1,234,567.89 $');
    expect(money(0, '€')).toBe('0.00 €');
    expect(money(-0, '€')).toBe('0.00 €');
    expect(money(null, '€')).toBe('—');
  });

  it('signs an R multiple both ways', () => {
    expect(rMultiple(1.84)).toBe('+1.84R');
    expect(rMultiple(-0.3)).toBe('−0.30R');
    expect(rMultiple(0)).toBe('0.00R');
    expect(rMultiple(null)).toBe('—');
  });

  it('prints no hyphen-minus from any signed helper', () => {
    for (const value of [-0.004, -1, -2.5, -1234.567]) {
      for (const text of [pct(value), pct(value, 0), money(value, '$'), money(value, '€', 0), rMultiple(value), signed(value)]) {
        expect(text, `${value} -> ${text}`).not.toContain(HYPHEN);
        expect(text.startsWith(MINUS), `${value} -> ${text}`).toBe(true);
      }
    }
  });

  it('leaves the unsigned level formatter unsigned and zero unsigned', () => {
    expect(amount(1420, '$', 0)).toBe('1,420 $');
    expect(signed(0)).toBe('0.00');
  });
});
