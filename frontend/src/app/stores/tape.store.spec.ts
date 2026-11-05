import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';

import { Preferences, TapeRow } from '../api/models';
import { PreferencesStore } from './preferences.store';
import { TapeFeed } from './tape-feed';
import { TapeStore } from './tape.store';

const row = (symbol: string, sort_rank: number): TapeRow => (
  { symbol, sort_rank, price: 1, change_pct: 0, context_kind: null, context_label: null });

describe('TapeStore', () => {
  function setup(rows: TapeRow[], symbols: string[] = ['NVDA'], asOf: string | null = null) {
    const prefs = signal<Preferences>({ 'tape.symbols': symbols });
    const feed = {
      register: vi.fn(),
      rows: signal(Object.fromEntries(rows.map((r) => [r.symbol, r]))),
      asOf: signal<string | null>(asOf),
      loading: signal(false),
      refresh: vi.fn(),
    };
    TestBed.configureTestingModule({
      providers: [
        { provide: TapeFeed, useValue: feed },
        { provide: PreferencesStore, useValue: {
            values: () => prefs(),
            update: (fn: (current: Preferences) => Preferences) => prefs.update(fn),
            isLoaded: () => true,
          } },
      ],
    });
    return { feed, prefs, store: TestBed.inject(TapeStore) };
  }

  it('is not visible when nothing is flagged', () => {
    const { store } = setup([], []);
    expect(store.visible()).toBe(false);
  });

  it('registers its symbols with the feed as owner "tape"', () => {
    const { feed, store } = setup([]);
    TestBed.tick();
    expect(feed.register).toHaveBeenCalledWith('tape', store.symbols);
  });

  it('sorts positions before plans before the rest', () => {
    const { store } = setup([row('C', 2), row('A', 0), row('B', 1)], ['A', 'B', 'C']);
    expect(store.rows().map((r) => r.symbol)).toEqual(['A', 'B', 'C']);
  });

  it('shows only the rows of its own flagged symbols', () => {
    const { store } = setup([row('A', 0), row('^GSPC', 2)], ['A']);
    expect(store.rows().map((r) => r.symbol)).toEqual(['A']);
  });

  it('exposes the as-of instant from the feed', () => {
    const { store } = setup([], ['NVDA'], '2026-09-09T14:35:00+00:00');
    expect(store.asOf()).toBe('2026-09-09T14:35:00+00:00');
  });

  it('load() asks the feed to refresh', () => {
    const { feed, store } = setup([]);
    store.load();
    expect(feed.refresh).toHaveBeenCalledTimes(1);
  });

  it('toggle() flags a ticker through preferences and does not refresh itself', () => {
    const { feed, store } = setup([], ['NVDA']);
    store.toggle('AMD');
    expect(store.symbols()).toEqual(['NVDA', 'AMD']);
    expect(feed.refresh).not.toHaveBeenCalled();
  });
});
