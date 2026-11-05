import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi } from 'vitest';

import { TapeRow } from '../api/models';
import { MarketIndexStore } from './market-index.store';
import { TapeFeed } from './tape-feed';

const row = (symbol: string): TapeRow => (
  { symbol, sort_rank: 2, price: 1, change_pct: 0, context_kind: null, context_label: null });

function setup(rows: TapeRow[]) {
  const feed = {
    register: vi.fn(),
    rows: signal(Object.fromEntries(rows.map((r) => [r.symbol, r]))),
    asOf: signal<string | null>('2026-10-29T14:00:00Z'),
    loading: signal(false),
    refresh: vi.fn(),
  };
  TestBed.configureTestingModule({ providers: [{ provide: TapeFeed, useValue: feed }] });
  return { feed, store: TestBed.inject(MarketIndexStore) };
}

describe('MarketIndexStore', () => {
  it('registers INDEX_SYMBOLS as owner "index"', () => {
    const { feed } = setup([]);
    TestBed.tick();
    expect(feed.register).toHaveBeenCalledTimes(1);
    const [owner, symbols] = feed.register.mock.calls[0];
    expect(owner).toBe('index');
    expect(symbols()).toEqual(['^GSPC', '^NDX', '^DJI', '^VIX']);
  });

  it('rows follow INDEX_SYMBOLS order, skipping a symbol the feed lacks', () => {
    const { store } = setup([row('^VIX'), row('^GSPC'), row('^DJI'), row('NVDA')]);
    expect(store.rows().map((r) => r.symbol)).toEqual(['^GSPC', '^DJI', '^VIX']);
  });

  it('asOf comes from the feed and load() refreshes it', () => {
    const { feed, store } = setup([]);
    expect(store.asOf()).toBe('2026-10-29T14:00:00Z');
    store.load();
    expect(feed.refresh).toHaveBeenCalledTimes(1);
  });
});
