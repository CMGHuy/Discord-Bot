import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { describe, expect, it } from 'vitest';

import { SessionStore } from '../stores/session.store';
import { DEFAULT_PHONE_TAB_PATHS, NAV_ENTRIES, NavEntry, navEntriesFor } from './nav';
import {
  MAX_TAB_PAGES, TAB_BAR_PREF_KEY, TAB_BAR_STORAGE, TabBarPrefs, TabBarStorage, readTabPaths, sanitizeTabPaths,
} from './tab-bar-prefs';

const ADMIN = navEntriesFor(true);
const VIEWER = navEntriesFor(false);
const DEFAULT = [...DEFAULT_PHONE_TAB_PATHS];
const paths = (entries: readonly NavEntry[]) => entries.map((entry) => entry.path);

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

describe('TabBarPrefs (v240 §6)', () => {
  function setup(stored?: string, role: 'admin' | 'viewer' = 'admin', storage: TabBarStorage = memoryStorage()) {
    if (stored !== undefined) storage.set(TAB_BAR_PREF_KEY, stored);
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: TAB_BAR_STORAGE, useValue: storage }],
    });
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: role, role });
    return { prefs: TestBed.inject(TabBarPrefs), storage };
  }

  const savedIn = (storage: TabBarStorage) => JSON.parse(storage.get(TAB_BAR_PREF_KEY) ?? 'null');

  it('defaults to Home, Watchlist, Trades and Calendar, with Risk, Insights and System under More', () => {
    const { prefs } = setup();
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(prefs.tabs().map((tab) => tab.label)).toEqual(['Home', 'Watchlist', 'Trades', 'Calendar']);
    expect(prefs.underMore().map((entry) => entry.label)).toEqual(['Risk', 'Insights', 'System']);
    expect(prefs.isDefault()).toBe(true);
    expect(prefs.canAdd()).toBe(false);
  });

  it('reads a custom list from storage, without rewriting it', () => {
    const { prefs, storage } = setup('["/risk","/dashboard","/risk"]');
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
    expect(prefs.tabs().map((tab) => tab.label)).toEqual(['Home', 'Risk']);
    expect(prefs.isDefault()).toBe(false);
    expect(prefs.canAdd()).toBe(true);
    expect(storage.get(TAB_BAR_PREF_KEY)).toBe('["/risk","/dashboard","/risk"]');
  });

  it('hides a stored System tab from a viewer and shows it once the login is an admin', () => {
    const { prefs } = setup('["/dashboard","/system","/risk"]', 'viewer');
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
    expect(paths(prefs.underMore())).not.toContain('/system');
    patchState(unprotected(TestBed.inject(SessionStore)), { role: 'admin' });
    expect(prefs.paths()).toEqual(['/dashboard', '/system', '/risk']);
  });

  it('keeps an admin System tab through the moment the session is still loading', () => {
    const storage = memoryStorage(new Map([[TAB_BAR_PREF_KEY, '["/dashboard","/system"]']]));
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: TAB_BAR_STORAGE, useValue: storage }],
    });
    const prefs = TestBed.inject(TabBarPrefs);
    expect(prefs.paths()).toEqual(['/dashboard']);
    patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username: 'admin', role: 'admin' });
    expect(prefs.paths()).toEqual(['/dashboard', '/system']);
  });

  it.each([
    ['admin', undefined],
    ['admin', '["/dashboard","/system"]'],
    ['admin', '["/risk","/insights","/system","/calendar","/trades"]'],
    ['viewer', undefined],
    ['viewer', '["/dashboard","/system","/watchlist"]'],
    ['viewer', 'not json'],
  ] as const)('partitions every page a %s may see between the bar and More (stored %s)', (role, stored) => {
    const { prefs } = setup(stored, role);
    const visible = paths(navEntriesFor(role === 'admin'));
    const bar = [...prefs.paths()];
    const more = paths(prefs.underMore());
    expect(bar.filter((path) => more.includes(path))).toEqual([]);
    expect([...bar, ...more].sort()).toEqual([...visible].sort());
    expect(bar[0]).toBe('/dashboard');
    expect(bar.length).toBeLessThanOrEqual(MAX_TAB_PAGES);
  });

  it('lists More in rail order under rail labels', () => {
    const { prefs } = setup('["/dashboard","/insights"]');
    expect(prefs.underMore().map((entry) => entry.label))
      .toEqual(['Watchlist', 'Trades', 'Calendar', 'Risk', 'System']);
  });

  it('adds a page at the end and saves the list as JSON', () => {
    const { prefs, storage } = setup('["/dashboard","/watchlist"]');
    prefs.add('/risk');
    expect(prefs.paths()).toEqual(['/dashboard', '/watchlist', '/risk']);
    expect(savedIn(storage)).toEqual(['/dashboard', '/watchlist', '/risk']);
  });

  it('ignores an add while the bar is full, of a page already on it, or of one the login cannot open', () => {
    const { prefs, storage } = setup(undefined, 'viewer');
    prefs.add('/risk');
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(storage.get(TAB_BAR_PREF_KEY)).toBeNull();
    prefs.remove('/calendar');
    prefs.add('/watchlist');
    prefs.add('/system');
    prefs.add('/nowhere');
    expect(prefs.paths()).toEqual(['/dashboard', '/watchlist', '/trades']);
    expect(savedIn(storage)).toEqual(['/dashboard', '/watchlist', '/trades']);
  });

  it('removes any page but the Dashboard, down to the Dashboard alone', () => {
    const { prefs } = setup('["/dashboard","/risk"]');
    prefs.remove('/dashboard');
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
    prefs.remove('/risk');
    expect(prefs.paths()).toEqual(['/dashboard']);
    expect(prefs.tabs().map((tab) => tab.label)).toEqual(['Home']);
    prefs.remove('/watchlist');
    expect(prefs.paths()).toEqual(['/dashboard']);
  });

  it('moves a page up or down, never past the pinned Dashboard or off the end', () => {
    const { prefs } = setup();
    prefs.moveUp('/trades');
    expect(prefs.paths()).toEqual(['/dashboard', '/trades', '/watchlist', '/calendar']);
    prefs.moveUp('/trades');
    prefs.moveUp('/dashboard');
    prefs.moveDown('/dashboard');
    prefs.moveDown('/calendar');
    prefs.moveUp('/nowhere');
    expect(prefs.paths()).toEqual(['/dashboard', '/trades', '/watchlist', '/calendar']);
    prefs.moveDown('/trades');
    expect(prefs.paths()).toEqual(['/dashboard', '/watchlist', '/trades', '/calendar']);
  });

  it('resets to the default, saves it and hands back the list it replaced', () => {
    const { prefs, storage } = setup('["/dashboard","/risk"]');
    expect(prefs.reset()).toEqual(['/dashboard', '/risk']);
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(prefs.isDefault()).toBe(true);
    expect(savedIn(storage)).toEqual(DEFAULT);
    prefs.set(['/dashboard', '/risk']);
    expect(prefs.paths()).toEqual(['/dashboard', '/risk']);
  });

  it('validates a set() like a read', () => {
    const { prefs, storage } = setup();
    prefs.set(['/risk', '/trades/calendar', '/risk', '/nowhere']);
    expect(prefs.paths()).toEqual(['/dashboard', '/risk', '/calendar']);
    expect(savedIn(storage)).toEqual(['/dashboard', '/risk', '/calendar']);
  });

  it('survives a throwing storage: the default on read, and edits that last the session', () => {
    const { prefs } = setup(undefined, 'admin', throwingStorage());
    expect(prefs.paths()).toEqual(DEFAULT);
    expect(() => prefs.remove('/watchlist')).not.toThrow();
    expect(prefs.paths()).toEqual(['/dashboard', '/trades', '/calendar']);
    expect(() => prefs.reset()).not.toThrow();
    expect(prefs.paths()).toEqual(DEFAULT);
  });

  it('never relabels the nav model', () => {
    setup().prefs.tabs();
    expect(NAV_ENTRIES[0].label).toBe('Dashboard');
  });
});
