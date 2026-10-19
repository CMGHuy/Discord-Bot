import { describe, expect, it } from 'vitest';

import { formatFigureText, parseFigureText } from './figure-text';

describe('parseFigureText', () => {
  it('splits prefix, number and suffix', () => {
    expect(parseFigureText('+$1,240.50 today')).toEqual({
      prefix: '+$', value: 1240.5, decimals: 2, suffix: ' today', grouped: true,
    });
  });

  it('reads a bare percentage and an R multiple', () => {
    expect(parseFigureText('68%')).toEqual({ prefix: '', value: 68, decimals: 0, suffix: '%', grouped: false });
    expect(parseFigureText('-0.42R')).toEqual({ prefix: '-', value: 0.42, decimals: 2, suffix: 'R', grouped: false });
  });

  it('takes only the first number; the rest is suffix', () => {
    expect(parseFigureText('12 / 20')).toEqual({ prefix: '', value: 12, decimals: 0, suffix: ' / 20', grouped: false });
  });

  it('returns null when there is nothing to count', () => {
    expect(parseFigureText(null)).toBeNull();
    expect(parseFigureText('')).toBeNull();
    expect(parseFigureText('—')).toBeNull();
    expect(parseFigureText('n/a')).toBeNull();
  });
});

describe('formatFigureText', () => {
  it('round-trips every shape a stat tile is given', () => {
    for (const text of ['68%', '+1.23R', '+$1,240', '-$12.50', '1.80', '12 / 20', '−0.42R', '1,234,567.8 €']) {
      const parts = parseFigureText(text)!;
      expect(formatFigureText(parts, parts.value)).toBe(text);
    }
  });

  it('formats an intermediate value in the same shape', () => {
    const parts = parseFigureText('+$1,240.50')!;
    expect(formatFigureText(parts, 0)).toBe('+$0.00');
    expect(formatFigureText(parts, 1085.4375)).toBe('+$1,085.44');
  });

  it('keeps an ungrouped number ungrouped', () => {
    expect(formatFigureText(parseFigureText('12345')!, 2000)).toBe('2000');
  });
});
