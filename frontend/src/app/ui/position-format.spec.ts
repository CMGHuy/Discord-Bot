import { describe, expect, it } from 'vitest';

import {
  HELD_STATUSES, NO_PRICE_REASON, NO_PRICE_TEXT, PREV_CLOSE_ARIA, PREV_CLOSE_SUFFIX, PREV_CLOSE_TAG,
  closeDateTag, figureText, figureTone, positionFigure, positionPriceText,
} from './position-format';

const held = (o: Record<string, unknown>) => ({ status: 'ACTIVE', current_price: null, last_close: null, ...o });

describe('positionFigure', () => {
  it('formats P&L % signed with its unit and R signed without one', () => {
    expect(positionFigure(3.14159, 'pct')).toEqual({ text: '+3.14%', suffix: null });
    expect(positionFigure(1.38, 'r', 'live')).toEqual({ text: '+1.38', suffix: null });
  });
  it('suffixes a prev-close figure, with the true minus', () => {
    expect(positionFigure(-11.82, 'pct', 'prev_close')).toEqual({ text: '−11.82%', suffix: 'at prev close' });
    expect(positionFigure(-1.65, 'r', 'prev_close')).toEqual({ text: '−1.65', suffix: PREV_CLOSE_SUFFIX });
  });
  it('a missing value is an em dash and never carries the suffix', () => {
    expect(positionFigure(null, 'pct', 'prev_close')).toEqual({ text: '—', suffix: null });
    expect(positionFigure(undefined, 'r')).toEqual({ text: '—', suffix: null });
  });
  it('a loss that rounds to zero prints unsigned', () => {
    expect(positionFigure(-0.001, 'pct').text).toBe('0.00%');
  });
  it('figureText joins the suffix for text-only renderings', () => {
    expect(figureText(-1.65, 'r', 'prev_close')).toBe('−1.65 at prev close');
    expect(figureText(2, 'pct', 'live')).toBe('+2.00%');
  });
});

describe('figureTone', () => {
  it('is the sign on a live row and muted on a prev-close one', () => {
    expect(figureTone(5, 'live')).toBe('pos');
    expect(figureTone(-1, null)).toBe('neg');
    expect(figureTone(0)).toBe('');
    expect(figureTone(null, 'prev_close')).toBe('');
    expect(figureTone(-1, 'prev_close')).toBe('muted');
    expect(figureTone(4, 'prev_close')).toBe('muted');
  });
});

describe('position constants and text', () => {
  it('held means ACTIVE and PARTIAL only', () => {
    expect([...HELD_STATUSES].sort()).toEqual(['ACTIVE', 'PARTIAL']);
  });
  it('pins the copy the spec fixes', () => {
    expect(PREV_CLOSE_TAG).toBe('prev close');
    expect(NO_PRICE_TEXT).toBe('no price yet');
    expect(NO_PRICE_REASON).toBe('no trade and no daily close cached');
    expect(PREV_CLOSE_ARIA).toBe('price is previous close, not live');
  });
  it('closeDateTag keeps month-day', () => {
    expect(closeDateTag('2026-11-24')).toBe('11-24');
    expect(closeDateTag(null)).toBe('');
  });
  it('positionPriceText says what the price is', () => {
    expect(positionPriceText(held({ current_price: 131.07, price_kind: 'live' }))).toBe('131.07');
    expect(positionPriceText(held({ current_price: 1234.56, price_kind: 'prev_close', last_close: 1234.56 })))
      .toBe('1,234.56 prev close');
    expect(positionPriceText(held({}))).toBe('no price yet');
    expect(positionPriceText(held({ last_close: 36.86, last_close_date: '2026-11-09' }))).toBe('36.86 close 11-09');
    expect(positionPriceText({ status: 'PENDING', current_price: null, last_close: null })).toBe('—');
  });
});
