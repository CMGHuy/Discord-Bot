import { effect, inject } from '@angular/core';
import { patchState, signalStore, withHooks, withMethods, withState } from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { TapeRow } from '../api/models';

/** Lane A's fixed symbols, in the exact order the tape shows them.
 *
 * Yahoo's own index formats (`swingbot/core/marketdata/ticker_utils.py`),
 * not the friendlier aliases ("SPX", "VIX", ...) that alias table resolves
 * FROM -- `/market/tape` prices the literal symbol it is given with no
 * alias lookup of its own (`_tape_symbols` just upper-cases each part). */
const INDEX_SYMBOLS = ['^GSPC', '^NDX', '^DJI', '^VIX'];

interface MarketIndexSlice {
  rows: TapeRow[];
  asOf: string | null;
}

/**
 * Lane A of the shell tape — first-party replacement for the earlier
 * TradingView `ticker-tape` iframe.
 *
 * That widget was cross-origin: its scroll speed, its color theme and even
 * whether a given symbol (VIX included) painted at all were entirely up to
 * TradingView, not this app. This store prices the same four indices through
 * `/market/tape` — the same batched yfinance path Lane B already uses — so
 * Lane A renders through the exact same markup and CSS as Lane B (`tape.css`):
 * one scroll speed, one dark-theme palette, one place a missing price can be
 * fixed instead of two.
 *
 * Rows are NOT re-sorted (contrast `TapeStore`, which sorts by `sort_rank`):
 * `/market/tape` returns rows in the order its `symbols` query param listed
 * them, and Lane A's fixed display order (S&P, Nasdaq, Dow, VIX) IS that
 * request order.
 */
export const MarketIndexStore = signalStore(
  { providedIn: 'root' },
  withState<MarketIndexSlice>({ rows: [], asOf: null }),
  withMethods((store, api = inject(ApiClient)) => {
    let latestRequest = 0;
    const load = (): void => {
      const request = ++latestRequest;
      api.tape(INDEX_SYMBOLS).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.rows)) return;
          patchState(store, { rows: response.rows, asOf: response.as_of ?? null });
        },
        // Deliberately silent and non-destructive, matching TapeStore: a
        // toast over the workspace someone is reading is not worth this
        // strip going one refresh cycle stale.
        error: () => undefined,
      });
    };
    return { load };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const scan = events.changes('scan');
      effect(() => {
        scan();
        store.load();
      });
    },
  }),
);
