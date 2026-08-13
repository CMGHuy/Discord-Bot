import { computed, effect, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import { Candle, TradeLevels } from '../api/models';

interface OhlcvSlice {
  ticker: string | null;
  tradeId: string | null;
  bars: Candle[];
  levels: TradeLevels | null;
  loading: boolean;
  /** Whether a request for the CURRENT target has come back. Reset by
   *  `setTarget`, so it never reports the previous ticker's completion. */
  loaded: boolean;
  error: string | null;
}

/**
 * Price history for one ticker — `GET /api/v1/market/ohlcv/:ticker`.
 *
 * Shared by the trade detail's Chart tab and (NG51) the ticker detail, which
 * is why it is a store rather than a fetch inside the chart component: both
 * want the same request with a different `trade_id`, and a component that
 * fetched its own data would give the chart two subtly different loaders.
 *
 * Refetches on `scan`. There is no `prices` event -- spec v12's taxonomy has
 * ten and none of them is a price tick -- and `scan` is the honest stand-in:
 * a completed scan is exactly when the OHLCV cache behind this endpoint has
 * new bars in it.
 *
 * Deliberately NOT on `trades`. The levels do come from the trade, but they
 * only change when the plan does, and refetching a year of candles on every
 * trade event to pick up four horizontal lines is the wrong trade. If plan
 * edits ever become frequent, the fix is a narrower event, not a wider
 * refetch.
 */
export const OhlcvStore = signalStore(
  withState<OhlcvSlice>({
    ticker: null,
    tradeId: null,
    bars: [],
    levels: null,
    loading: false,
    loaded: false,
    error: null,
  }),
  withComputed(({ bars, loading, loaded, error }) => ({
    /** Distinct from an error and from loading: the request succeeded and
     *  this ticker simply has no history in the window.
     *
     *  Gated on `loaded` because the three not-ready states are otherwise
     *  indistinguishable at rest. The Chart tab builds this store before the
     *  trade has loaded -- there is no ticker yet, so nothing is in flight
     *  and `loading` is false -- and without the gate that idle moment reads
     *  as "no price history for this ticker", which is a claim about the
     *  data rather than about the wait. */
    isEmpty: computed(
      () => loaded() && !loading() && error() === null && bars().length === 0,
    ),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    /** Setting the target is the load. Passing the same pair twice is a
     *  no-op, so a re-render cannot cost a request. */
    setTarget(ticker: string | null, tradeId: string | null = null): void {
      if (ticker === store.ticker() && tradeId === store.tradeId()) return;
      patchState(store, {
        ticker,
        tradeId,
        bars: [],
        levels: null,
        loaded: false,
        error: null,
      });
    },

    load(): void {
      const ticker = store.ticker();
      if (!ticker) return;

      const tradeId = store.tradeId();
      patchState(store, { loading: true });
      api.ohlcv(ticker, tradeId ? { trade_id: tradeId } : {}).subscribe({
        next: (response) =>
          patchState(store, {
            bars: response.bars,
            levels: response.levels ?? null,
            loading: false,
            loaded: true,
            error: null,
          }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            loaded: true,
            error:
              error.code === 'not_found'
                ? `No price history for ${ticker}.`
                : error.code === 'unavailable'
                  ? 'The admin is not responding.'
                  : error.message,
          }),
      });
    },
  })),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const scan = events.changes('scan');
      effect(() => {
        scan();
        store.ticker();
        store.tradeId();
        store.load();
      });
    },
  }),
);
