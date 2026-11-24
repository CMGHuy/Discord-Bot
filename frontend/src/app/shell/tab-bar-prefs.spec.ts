import { describe, expect, it } from 'vitest';

import { DEFAULT_PHONE_TAB_PATHS, navEntriesFor } from './nav';
import { MAX_TAB_PAGES, TAB_BAR_PREF_KEY, TabBarStorage, readTabPaths, sanitizeTabPaths } from './tab-bar-prefs';

const ADMIN = navEntriesFor(true);
const VIEWER = navEntriesFor(false);
const DEFAULT = [...DEFAULT_PHONE_TAB_PATHS];

/** An in-memory ui.tabbar store, as shell.spec.ts does for ui.theme. */
function memoryStorage(map = new Map<string, string>()): TabBarStorage {
  return { get: (key) => map.get(key) ?? null, set: (key, value) => void map.set(key, value) };
}

function throwingStorage(): TabBarStorage {
  return {
    get: () => { throw new Error('SecurityError'); },
    set: () => { throw new Error('QuotaExceededError'); },
  };
}

describe('TAB_BAR_PREF_KEY and MAX_TAB_PAGES', () => {
  it('stores under ui.tabbar and holds four pages', () => {
    expect(TAB_BAR_PREF_KEY).toBe('ui.tabbar');
    expect(MAX_TAB_PAGES).toBe(4);
  });
});

describe('sanitizeTabPaths (v240 §6, §8)', () => {
  it.each([
    ['missing', null],
    ['an object', { paths: ['/risk'] }],
    ['a string', '/risk'],
    ['a number', 4],
    ['an empty array', []],
    ['only unknown paths', ['/nowhere', '/ui']],
    ['only non-strings', [1, null, { path: '/risk' }]],
  ])('gives the default for %s', (_label, raw) => {
    expect(sanitizeTabPaths(raw, ADMIN)).toEqual(DEFAULT);
  });

  it('keeps a valid custom list as it is', () => {
    expect(sanitizeTabPaths(['/dashboard', '/risk', '/insights'], ADMIN)).toEqual(['/dashboard', '/risk', '/insights']);
  });

  it('keeps the Dashboard alone (the editor minimum)', () => {
    expect(sanitizeTabPaths(['/dashboard'], ADMIN)).toEqual(['/dashboard']);
  });

  it('forces the Dashboard first, moving it or adding it', () => {
    expect(sanitizeTabPaths(['/risk', '/dashboard', '/trades'], ADMIN)).toEqual(['/dashboard', '/risk', '/trades']);
    expect(sanitizeTabPaths(['/risk'], ADMIN)).toEqual(['/dashboard', '/risk']);
  });

  it('drops duplicates, unknown paths and non-strings, keeping the first of each', () => {
    expect(sanitizeTabPaths(['/dashboard', '/risk', '/risk', '/nowhere', 7, '/trades'], ADMIN))
      .toEqual(['/dashboard', '/risk', '/trades']);
  });

  it('truncates an over-long list to four pages', () => {
    expect(sanitizeTabPaths(['/dashboard', '/watchlist', '/trades', '/calendar', '/risk', '/insights'], ADMIN))
      .toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
  });

  it('counts the forced Dashboard inside the four', () => {
    expect(sanitizeTabPaths(['/watchlist', '/trades', '/calendar', '/risk'], ADMIN))
      .toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
  });

  it('maps a stored /trades/calendar to /calendar, and dedupes it against /calendar', () => {
    expect(sanitizeTabPaths(['/dashboard', '/trades/calendar'], ADMIN)).toEqual(['/dashboard', '/calendar']);
    expect(sanitizeTabPaths(['/dashboard', '/calendar', '/trades/calendar'], ADMIN)).toEqual(['/dashboard', '/calendar']);
  });

  it('drops System for a viewer and keeps it for an admin', () => {
    expect(sanitizeTabPaths(['/dashboard', '/system', '/risk'], VIEWER)).toEqual(['/dashboard', '/risk']);
    expect(sanitizeTabPaths(['/dashboard', '/system', '/risk'], ADMIN)).toEqual(['/dashboard', '/system', '/risk']);
    expect(sanitizeTabPaths(['/system'], VIEWER)).toEqual(DEFAULT);
  });

  it('gives an empty list for an empty model, never a page it cannot open', () => {
    expect(sanitizeTabPaths(['/dashboard'], [])).toEqual([]);
    expect(sanitizeTabPaths(null, [])).toEqual([]);
  });

  it('never mutates the array it is given', () => {
    const raw = ['/risk', '/dashboard', '/risk'];
    sanitizeTabPaths(raw, ADMIN);
    expect(raw).toEqual(['/risk', '/dashboard', '/risk']);
  });
});

describe('readTabPaths', () => {
  it('reads and validates the stored JSON', () => {
    const storage = memoryStorage(new Map([[TAB_BAR_PREF_KEY, '["/risk","/dashboard"]']]));
    expect(readTabPaths(storage, ADMIN)).toEqual(['/dashboard', '/risk']);
  });

  it.each([
    ['no value', undefined],
    ['malformed JSON', '["/risk",'],
    ['an empty string', ''],
    ['an empty array', '[]'],
    ['JSON null', 'null'],
  ])('gives the default for %s', (_label, stored) => {
    const storage = memoryStorage(stored === undefined ? new Map() : new Map([[TAB_BAR_PREF_KEY, stored]]));
    expect(readTabPaths(storage, ADMIN)).toEqual(DEFAULT);
  });

  it('gives the default when the storage throws', () => {
    expect(readTabPaths(throwingStorage(), ADMIN)).toEqual(DEFAULT);
  });
});
