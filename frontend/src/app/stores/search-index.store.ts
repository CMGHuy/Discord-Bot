import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, forkJoin, map, of } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { Ticker, TradeRow } from '../api/models';

/** An open more than this long after the last good read refreshes it. */
export const SEARCH_INDEX_TTL_MS = 60_000;

/**
 * The trades read. Newest *created* first, not newest opened: an unfilled
 * plan has no `opened_at` and the server sorts valueless rows last, so
 * `-opened_at` would push every pending plan behind 200 filled trades. 200
 * is the server's `per_page` cap.
 */
export const SEARCH_INDEX_TRADES_QUERY = { per_page: 200, sort: '-created_at' } as const;

interface SearchIndexSlice {
  tickers: Ticker[];
  trades: TradeRow[];
  /** When the last read that fully answered arrived; null before one has. */
  loadedAt: number | null;
  /** The last read lost at least one list; the palette says so in one line. */
  failed: boolean;
}

/**
 * The command palette's tickers and trades -- v195 §3.1.
 *
 * Root-provided because the palette lives in the shell, and the stores that
 * hold these rows (`TradesStore`, `WatchlistStore`, `TradeDetailStore`) are
 * route-scoped. It reads the same two existing endpoints itself; no new
 * backend surface.
 *
 * Lazy: nothing is fetched until the palette first opens (`ensure`), so a
 * session that never opens it costs nothing. Cached for the session and
 * refreshed on an open more than `SEARCH_INDEX_TTL_MS` after the last good
 * read. A list that fails keeps its earlier rows, sets `failed`, and leaves
 * `loadedAt` alone so the next open tries again; the palette still serves
 * pages and preferences meanwhile.
 *
 * Errors are swallowed per list, with no toast: a search box that cannot
 * list tickers is not worth interrupting whatever page is open.
 */
export const SearchIndexStore = signalStore(
  { providedIn: 'root' },
  withState<SearchIndexSlice>({ tickers: [], trades: [], loadedAt: null, failed: false }),
  withMethods((store, api = inject(ApiClient)) => {
    let inFlight = false;

    const isFresh = (now: number): boolean => {
      const at = store.loadedAt();
      return at !== null && now - at <= SEARCH_INDEX_TTL_MS;
    };

    /** One list, or null when its read failed. */
    const orNull = <T>(source: Observable<T[]>): Observable<T[] | null> =>
      source.pipe(catchError(() => of(null)));

    const ensure = (now: number = Date.now()): void => {
      if (inFlight || isFresh(now)) return;
      inFlight = true;
      forkJoin({
        tickers: orNull(api.tickers().pipe(map((body) => body?.tickers ?? []))),
        trades: orNull(api.trades({ ...SEARCH_INDEX_TRADES_QUERY }).pipe(map((body) => body?.items ?? []))),
      }).subscribe(({ tickers, trades }) => {
        inFlight = false;
        const failed = tickers === null || trades === null;
        patchState(store, {
          tickers: tickers ?? store.tickers(),
          trades: trades ?? store.trades(),
          failed,
          loadedAt: failed ? store.loadedAt() : now,
        });
      });
    };

    return { ensure };
  }),
);
