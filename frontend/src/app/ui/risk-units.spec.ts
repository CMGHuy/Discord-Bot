import { describe, expect, it } from 'vitest';

import { ABSENT, MINUS } from './format';
import { riskUnits } from './risk-units';

/* v195 section 5.2: open risk and cap headroom show money and % of account side by
 * side, against the dollar-risk cap. Never one unit alone, never an
 * invented figure. */
describe('riskUnits', () => {
  it('renders money and % of account together, money first', () => {
    expect(riskUnits(1.42, 100_000, '$')).toBe('1,420 $ · 1.42%');
    expect(riskUnits(2, 123_456.78, '€')).toBe('2,469 € · 2.00%');
  });

  it('rounds the money to whole units and keeps two decimals on the percentage', () => {
    expect(riskUnits(1.25, 10_000, '$')).toBe('125 $ · 1.25%');
    expect(riskUnits(0.333, 10_000, '$')).toBe('33 $ · 0.33%');
  });

  it('keeps the percentage and marks the money absent when the balance is unknown', () => {
    expect(riskUnits(1.42, null, '$')).toBe(`${ABSENT} · 1.42%`);
    expect(riskUnits(1.42, undefined, '$')).toBe(`${ABSENT} · 1.42%`);
    expect(riskUnits(1.42, Number.NaN, '$')).toBe(`${ABSENT} · 1.42%`);
  });

  it('is absent as a whole when the percentage is unknown', () => {
    expect(riskUnits(null, 100_000, '$')).toBe(ABSENT);
    expect(riskUnits(undefined, 100_000, '$')).toBe(ABSENT);
    expect(riskUnits(Number.POSITIVE_INFINITY, 100_000, '$')).toBe(ABSENT);
  });

  it('renders zero risk as zero in both units, unsigned', () => {
    expect(riskUnits(0, 50_000, '$')).toBe('0 $ · 0.00%');
    expect(riskUnits(-0, 50_000, '$')).toBe('0 $ · 0.00%');
  });

  it("keeps riskPct's floor for a sliver of risk", () => {
    expect(riskUnits(0.004, 100_000, '$')).toBe('4 $ · <0.01%');
  });

  it('puts one true minus on each part of a negative figure (headroom past the cap)', () => {
    expect(riskUnits(-0.5, 100_000, '$')).toBe(`${MINUS}500 $ · ${MINUS}0.50%`);
    expect(riskUnits(-0.5, 100_000, '$')).not.toContain('-');
    expect(riskUnits(-0.5, null, '$')).toBe(`${ABSENT} · ${MINUS}0.50%`);
  });
});
