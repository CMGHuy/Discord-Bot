import { describe, expect, it } from 'vitest';

import { Preferences } from '../api/models';
import {
  PER_PAGE_OPTIONS,
  readTableColumns,
  readTableDensity,
  readTablePerPage,
  writeTableColumns,
  writeTableDensity,
  writeTablePerPage,
} from './table-prefs';

/* SR12. These are pure functions over a plain object, so they are tested
 * directly rather than through a store — the tolerance below is the whole
 * reason the "columns carry an order" reversal is safe, and it deserves to be
 * pinned somewhere a store's plumbing cannot obscure it. */

describe('readTableColumns', () => {
  const baseline = ['num', 'status', 'ticker'];

  it('returns the baseline when nothing is stored', () => {
    expect(readTableColumns({}, 'trades', 'compact', baseline)).toEqual(baseline);
  });

  it('honours a stored order', () => {
    const prefs = { 'tables.trades.compact.columns': ['ticker', 'num', 'status'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline))
      .toEqual(['ticker', 'num', 'status']);
  });

  it('drops a stored key that is no longer a column', () => {
    // The plan's version of this case expects ['ticker', 'num'] — which
    // contradicts the very next test AND the plan's own implementation
    // snippet. Both cannot hold: 'status' is a baseline column missing from
    // the stored order, so the append rule that stops a new column being
    // hidden must also apply here. Dropping 'deleted_col' is what this test
    // is actually about, and that still holds.
    const prefs = { 'tables.trades.compact.columns': ['ticker', 'deleted_col', 'num'] };
    const result = readTableColumns(prefs, 'trades', 'compact', baseline);
    expect(result).not.toContain('deleted_col');
    expect(result).toEqual(['ticker', 'num', 'status']);
  });

  it('appends a baseline column absent from the stored order, never hides it', () => {
    // A layout saved before a column existed must not make that column
    // undiscoverable — it appears at the end instead.
    const prefs = { 'tables.trades.compact.columns': ['ticker'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline))
      .toEqual(['ticker', 'num', 'status']);
  });

  it('survives a stored value of the wrong type', () => {
    expect(readTableColumns({ 'tables.trades.compact.columns': 'nonsense' } as Preferences,
                            'trades', 'compact', baseline)).toEqual(baseline);
  });

  it('survives non-string entries inside the stored array', () => {
    const prefs = { 'tables.trades.compact.columns': ['ticker', 42, null] } as Preferences;
    expect(readTableColumns(prefs, 'trades', 'compact', baseline))
      .toEqual(['ticker', 'num', 'status']);
  });

  it('keeps the two densities independent', () => {
    const prefs = { 'tables.trades.full.columns': ['ticker'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline)).toEqual(baseline);
  });

  it('keeps two tables independent', () => {
    const prefs = { 'tables.dashboard.compact.columns': ['ticker'] };
    expect(readTableColumns(prefs, 'trades', 'compact', baseline)).toEqual(baseline);
  });

  it('does not alias the baseline it was given', () => {
    // Returning the caller's array would let a later sort mutate the default.
    const result = readTableColumns({}, 'trades', 'compact', baseline);
    result.reverse();
    expect(baseline).toEqual(['num', 'status', 'ticker']);
  });
});

describe('readTableDensity', () => {
  it('defaults to compact', () => {
    expect(readTableDensity({}, 'trades')).toBe('compact');
  });

  it('reads a stored density', () => {
    expect(readTableDensity({ 'tables.trades.density': 'full' }, 'trades')).toBe('full');
  });

  it('rejects a value that is not a density', () => {
    expect(readTableDensity({ 'tables.trades.density': 'enormous' }, 'trades')).toBe('compact');
  });
});

describe('readTablePerPage', () => {
  it('defaults to 25', () => {
    expect(readTablePerPage({}, 'trades')).toBe(25);
  });

  it('reads a stored value that the UI actually offers', () => {
    expect(readTablePerPage({ 'tables.trades.per_page': 50 }, 'trades')).toBe(50);
  });

  it('rejects a value outside the offered set', () => {
    // Otherwise a hand-edited preference asks the server for an unbounded page.
    expect(readTablePerPage({ 'tables.trades.per_page': 5000 }, 'trades')).toBe(25);
  });

  it('rejects a non-number', () => {
    expect(readTablePerPage({ 'tables.trades.per_page': '50' } as Preferences, 'trades')).toBe(25);
  });

  it('offers a sane set of options', () => {
    expect([...PER_PAGE_OPTIONS]).toEqual([10, 25, 50, 100]);
  });
});

describe('the writers', () => {
  it('round-trip through their readers', () => {
    let prefs: Preferences = {};
    prefs = writeTableDensity(prefs, 'trades', 'full');
    prefs = writeTableColumns(prefs, 'trades', 'full', ['ticker', 'num']);
    prefs = writeTablePerPage(prefs, 'trades', 50);

    expect(readTableDensity(prefs, 'trades')).toBe('full');
    expect(readTableColumns(prefs, 'trades', 'full', ['num', 'ticker'])).toEqual(['ticker', 'num']);
    expect(readTablePerPage(prefs, 'trades')).toBe(50);
  });

  it('do not mutate the preferences they are given', () => {
    // The store holds these in signal state; mutating in place would change
    // it without anything noticing that it changed.
    const original: Preferences = {};
    writeTableDensity(original, 'trades', 'full');
    expect(original).toEqual({});
  });

  it('leave other keys alone', () => {
    const prefs: Preferences = { 'tables.dashboard.density': 'full' };
    const next = writeTableDensity(prefs, 'trades', 'compact');
    expect(next['tables.dashboard.density']).toBe('full');
  });
});
