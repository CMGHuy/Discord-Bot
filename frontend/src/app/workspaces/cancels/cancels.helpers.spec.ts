import { describe, expect, it } from 'vitest';

import { CancelPlanRow } from '../../api/models';
import { CancelFilter, NO_FILTER } from '../../stores/cancels.store';
import { CANCEL_PAYLOAD, fig } from '../../testing/cancel-fixtures';
import { ciText, figureText, filterRows, rText, verdictLabel } from './cancels.helpers';

const ROWS = CANCEL_PAYLOAD.rows;
const ids = (rows: CancelPlanRow[]): string[] => rows.map((r) => `${r.ticker}:${r.entry_model}`);
const only = (over: Partial<CancelFilter>): CancelFilter => ({ ...NO_FILTER, ...over });
const row = (i: number, over: Partial<CancelPlanRow> = {}): CancelPlanRow => ({ ...ROWS[i], ...over });

describe('figureText', () => {
  it('prints precision as a whole percent of N', () => {
    expect(figureText(fig({ n: 37, precision: 0.6216 }))).toBe('62% of 37');
    expect(figureText(fig({ n: 3, precision: 1 }))).toBe('100% of 3');
  });
  it('prints a dash when there is no precision, never 0%', () => {
    expect(figureText(fig())).toBe('— of 0');
  });
});

describe('ciText', () => {
  it('prints the 95% interval in whole percent', () => {
    expect(ciText([0.45, 0.78])).toBe('95% CI 45–78%');
  });
  it('prints a dash without an interval', () => {
    expect(ciText(null)).toBe('95% CI —');
  });
});

describe('rText', () => {
  it('signs and fixes R to two places', () => {
    expect(rText(1.85)).toBe('+1.85R');
    expect(rText(-3.4)).toBe('-3.40R');
    expect(rText(0)).toBe('0.00R');
  });
  it('prints a dash for a missing R', () => {
    expect(rText(null)).toBe('—');
  });
});

describe('verdictLabel', () => {
  it('names an invalidated or expired verdict a right or wrong cancel', () => {
    expect(verdictLabel(row(2))).toBe('Wrong cancel');
    expect(verdictLabel(row(2, { outcome: 'right' }))).toBe('Right cancel');
    expect(verdictLabel(row(3))).toBe('Unresolved');
    expect(verdictLabel(row(4))).toBe('Untriggered after cancel');
  });
  it('never calls a risk_cap verdict a wrong cancel', () => {
    expect(verdictLabel(row(1))).toBe('Setup reached TP1');
    expect(verdictLabel(row(0, { tie: false }))).toBe('Setup lost');
    expect(verdictLabel(row(1))).not.toContain('cancel');
  });
  it('marks a verdict decided by a same-bar tie', () => {
    expect(verdictLabel(row(0))).toBe('Setup lost (tie)');
  });
  it('names the exclusion on an excluded row', () => {
    expect(verdictLabel(row(5))).toBe('Excluded: split in window');
    expect(verdictLabel(row(5, { excluded: 'no_cancel_entry' }))).toBe('Excluded: no cancel-day bar');
    expect(verdictLabel(row(5, { excluded: 'something_new' }))).toBe('Excluded: something_new');
  });
});

describe('filterRows', () => {
  it('returns every row, in order, with no filter', () => {
    expect(ids(filterRows(ROWS, NO_FILTER))).toEqual([
      'AAPL:trigger', 'AAPL:cancel_fill', 'MSFT:trigger', 'NVDA:trigger', 'TSLA:trigger', 'XOM:trigger',
    ]);
  });
  it('keeps the two risk_cap entry models apart', () => {
    expect(ids(filterRows(ROWS, only({ card: 'risk_cap' })))).toEqual(['AAPL:trigger']);
    expect(ids(filterRows(ROWS, only({ card: 'risk_cap_fill' })))).toEqual(['AAPL:cancel_fill']);
    expect(ids(filterRows(ROWS, only({ card: 'other' })))).toEqual(['XOM:trigger']);
  });
  it('narrows an outcome or split with no card to the headline population', () => {
    // AAPL's crossing-price row is wrong too, but it is not in the headline.
    expect(ids(filterRows(ROWS, only({ outcome: 'wrong' })))).toEqual(['MSFT:trigger']);
    expect(ids(filterRows(ROWS, only({ split: { dim: 'origin', value: 'next_session' } })))).toEqual(['TSLA:trigger']);
    expect(ids(filterRows(ROWS, only({ split: { dim: 'horizon', value: '2m' } })))).toEqual(['MSFT:trigger']);
  });
  it('combines card, outcome and split', () => {
    expect(ids(filterRows(ROWS, only({ card: 'invalidated', outcome: 'wrong' })))).toEqual(['MSFT:trigger']);
    expect(ids(filterRows(ROWS, only({ outcome: 'right', split: { dim: 'direction', value: 'long' } }))))
      .toEqual(['AAPL:trigger']);
    expect(filterRows(ROWS, only({ card: 'expired', outcome: 'wrong' }))).toEqual([]);
  });
  it('never mutates its input', () => {
    const copy = [...ROWS];
    filterRows(ROWS, only({ card: 'risk_cap' }));
    expect(ROWS).toEqual(copy);
  });
  it('handles an empty book', () => {
    expect(filterRows([], only({ outcome: 'right' }))).toEqual([]);
  });
});
