import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { SEARCH_INDEX_TTL_MS, SearchIndexStore } from './search-index.store';

const TICKERS_URL = '/api/v1/watchlist/tickers';
const TRADES_URL = '/api/v1/trades';
const T0 = Date.parse('2026-10-27T12:00:00Z');

const tickersBody = (...symbols: string[]) => ({
  tickers: symbols.map((symbol) => ({ symbol, company_name: null, open_trades: 0, closed_trades: 0 })),
});
const tradesBody = (...ids: string[]) => ({
  items: ids.map((id) => ({ id, ticker: 'NVDA', status: 'ACTIVE', strategy: null, created_at: null, opened_at: null })),
  total: ids.length, page: 1, per_page: 200,
});
const FAIL_BODY = { error: { code: 'unavailable', message: 'down' } };
const FAIL_STATUS = { status: 503, statusText: 'Unavailable' };

describe('SearchIndexStore (v195 §3.1)', () => {
  let store: InstanceType<typeof SearchIndexStore>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(SearchIndexStore);
    http = TestBed.inject(HttpTestingController);
  });

  const answer = (symbols: string[], ids: string[]) => {
    http.expectOne((r) => r.url === TICKERS_URL).flush(tickersBody(...symbols));
    http.expectOne((r) => r.url === TRADES_URL).flush(tradesBody(...ids));
  };

  it('fetches nothing until the palette asks', () => {
    http.expectNone(() => true);
    expect(store.loadedAt()).toBeNull();
    expect(store.failed()).toBe(false);
  });

  it('reads the watchlist and the 200 most recently created trades on the first open', () => {
    store.ensure(T0);
    const trades = http.expectOne((r) => r.url === TRADES_URL);
    expect(trades.request.method).toBe('GET');
    expect(trades.request.params.get('per_page')).toBe('200');
    expect(trades.request.params.get('sort')).toBe('-created_at');
    http.expectOne((r) => r.url === TICKERS_URL).flush(tickersBody('NVDA', 'AMD'));
    trades.flush(tradesBody('812'));
    expect(store.tickers().map((t) => t.symbol)).toEqual(['NVDA', 'AMD']);
    expect(store.trades().map((t) => t.id)).toEqual(['812']);
    expect(store.loadedAt()).toBe(T0);
    expect(store.failed()).toBe(false);
  });

  it('serves the cache for 60s and refreshes on the first open after that', () => {
    store.ensure(T0);
    answer(['NVDA'], ['812']);

    store.ensure(T0 + SEARCH_INDEX_TTL_MS);
    http.expectNone(() => true);

    store.ensure(T0 + SEARCH_INDEX_TTL_MS + 1);
    answer(['NVDA', 'TSLA'], ['812', '813']);
    expect(store.tickers()).toHaveLength(2);
    expect(store.loadedAt()).toBe(T0 + SEARCH_INDEX_TTL_MS + 1);
  });

  it('never starts a second read while one is in flight', () => {
    store.ensure(T0);
    store.ensure(T0 + 1);
    expect(http.match((r) => r.url === TICKERS_URL)).toHaveLength(1);
    expect(http.match((r) => r.url === TRADES_URL)).toHaveLength(1);
  });

  it('flags a failed read, keeps the earlier rows and retries on the next open', () => {
    store.ensure(T0);
    answer(['NVDA'], ['812']);

    const later = T0 + SEARCH_INDEX_TTL_MS + 1;
    store.ensure(later);
    http.expectOne((r) => r.url === TICKERS_URL).flush(FAIL_BODY, FAIL_STATUS);
    http.expectOne((r) => r.url === TRADES_URL).flush(tradesBody('812', '813'));
    expect(store.failed()).toBe(true);
    expect(store.tickers().map((t) => t.symbol)).toEqual(['NVDA']);
    // The list that did answer is still taken.
    expect(store.trades()).toHaveLength(2);
    // Not stamped: the next open tries again rather than waiting 60s.
    expect(store.loadedAt()).toBe(T0);

    store.ensure(later + 1);
    answer(['NVDA', 'AMD'], ['812', '813']);
    expect(store.failed()).toBe(false);
    expect(store.loadedAt()).toBe(later + 1);
  });

  it('starts empty and flagged when the very first read fails, so pages still serve', () => {
    store.ensure(T0);
    http.expectOne((r) => r.url === TICKERS_URL).flush(FAIL_BODY, FAIL_STATUS);
    http.expectOne((r) => r.url === TRADES_URL).flush(FAIL_BODY, FAIL_STATUS);
    expect(store.tickers()).toEqual([]);
    expect(store.trades()).toEqual([]);
    expect(store.failed()).toBe(true);
    expect(store.loadedAt()).toBeNull();
  });

  it('treats a body without its list as empty, not as a crash', () => {
    store.ensure(T0);
    http.expectOne((r) => r.url === TICKERS_URL).flush({});
    http.expectOne((r) => r.url === TRADES_URL).flush({});
    expect(store.tickers()).toEqual([]);
    expect(store.trades()).toEqual([]);
    expect(store.failed()).toBe(false);
  });
});
