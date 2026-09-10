import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { PreferencesStore } from './preferences.store';
import { TapeStore } from './tape.store';

describe('TapeStore', () => {
  function setup(rows: unknown[], symbols: string[] = ['NVDA']) {
    const api = { tape: vi.fn().mockReturnValue(
      of({ as_of: '2026-09-09T14:35:00+00:00', rows })) };
    TestBed.configureTestingModule({
      providers: [
        { provide: ApiClient, useValue: api },
        { provide: PreferencesStore, useValue: {
            values: () => ({ 'tape.symbols': symbols }),
            update: () => undefined,
            isLoaded: () => true,
          } },
      ],
    });
    return { api, store: TestBed.inject(TapeStore) };
  }

  it('is not visible when nothing is flagged', () => {
    const { store } = setup([], []);
    store.load();
    expect(store.visible()).toBe(false);
  });

  it('sorts positions before plans before the rest', () => {
    const { store } = setup([
      { symbol: 'C', sort_rank: 2, price: 1, change_pct: 0, context_kind: null, context_label: null },
      { symbol: 'A', sort_rank: 0, price: 1, change_pct: 0, context_kind: 'position', context_label: '+1R' },
      { symbol: 'B', sort_rank: 1, price: 1, change_pct: 0, context_kind: 'plan', context_label: '2w 1% to entry' },
    ]);
    store.load();
    expect(store.rows().map((r) => r.symbol)).toEqual(['A', 'B', 'C']);
  });

  it('keeps the previous rows when a refetch fails', () => {
    const { api, store } = setup([
      { symbol: 'A', sort_rank: 0, price: 1, change_pct: 0, context_kind: null, context_label: null },
    ]);
    store.load();
    api.tape.mockReturnValue(of(null as never));
    store.load();
    expect(store.rows().length).toBe(1);
  });

  it('exposes the as-of instant', () => {
    const { store } = setup([]);
    store.load();
    expect(store.asOf()).toBe('2026-09-09T14:35:00+00:00');
  });
});
