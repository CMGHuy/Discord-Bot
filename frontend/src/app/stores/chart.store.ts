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
import { ChartResponse } from '../api/models';

interface ChartSlice {
  ticker: string | null;
  /** Optional. The chart's subject is the ticker; a trade adds its plan. */
  tradeId: string | null;
  /** Bars to load. Null means "whatever the endpoint defaults to" (120) --
   *  the default is deliberately NOT copied here, because a copy is a second
   *  place to change it and the two would disagree silently. */
  window: number | null;
  data: ChartResponse | null;
  loading: boolean;
  error: string | null;
}

/**
 * Every chart's data — `GET /api/v1/market/chart/:ticker?trade_id=`.
 *
 * One store, because there is one chart. This absorbed `OhlcvStore`, whose
 * only reason to exist was that the chart endpoint could not be asked for a
 * ticker without a trade. It can now, so the watchlist's ticker detail and
 * the trade detail's Chart tab load through this same path and cannot drift
 * into two subtly different loaders.
 *
 * **One request, one loading flag, one error.** The bars, the indicator panes,
 * the volume profile, the plan lines and the overlays all arrive together
 * because the panes have to agree: they are slices of one frame computed at
 * one window, by the same Python that draws the PNG posted to Discord. Five
 * requests would let the RSI pane describe a different frame from the candles
 * above it, which renders perfectly happily and is wrong.
 *
 * **Refetches on `trades`.** This payload carries `working_stop` -- the live
 * breakeven/trail floor, which moves on every trail step while the position is
 * open -- and overlays derived from the trade's own confirming sources. A stale
 * chart here does not show slightly old candles; it shows the wrong stop, which
 * is the one number a reader acts on.
 *
 * **And on `scan`, which the trade-only store did not do.** A completed scan is
 * exactly when the OHLCV cache behind this endpoint has new bars in it, and a
 * plain ticker chart has no trade events to ride on -- without this, the
 * watchlist's chart would never refresh at all. The cost the old `OhlcvStore`
 * weighed (a year of candles refetched for four horizontal lines) is the same
 * request this store already makes for its own reasons.
 */
export const ChartStore = signalStore(
  withState<ChartSlice>({
    ticker: null,
    tradeId: null,
    window: null,
    data: null,
    loading: false,
    error: null,
  }),
  withComputed(({ data }) => ({
    /** Distinct from an error and from loading: the request came back and this
     *  ticker simply has no history in the window.
     *
     *  Null `data` is NOT empty. It is the state before the first response and
     *  between two targets — the store drops the payload the moment the target
     *  changes — and reporting that as "no price history" would be a claim
     *  about the data rather than about the wait. */
    isEmpty: computed(() => data() !== null && data()!.ohlcv.length === 0),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    let latestRequest = 0;
    /** Shared by the event effect and by `retry`, so the failure path and the
     *  happy path cannot drift into two different requests. */
    const load = (): void => {
      const ticker = store.ticker();
      // The Chart tab is constructed before the trade has loaded. A request
      // for `/chart/null` is a 404 the user reads as "this chart is broken".
      if (!ticker) return;

      const tradeId = store.tradeId();
      const window = store.window();
      const request = ++latestRequest;
      patchState(store, { loading: true, error: null });
      api.chart(ticker, {
        ...(tradeId === null ? {} : { trade_id: tradeId }),
        ...(window === null ? {} : { window }),
      }).subscribe({
        next: (data) => {
          if (request !== latestRequest || data.ticker !== ticker) return;
          patchState(store, { data, loading: false, error: null });
        },
        error: (error: ApiError) => {
          if (request !== latestRequest) return;
          patchState(store, {
            loading: false,
            // The two degraded states spec Decision 10 names must be
            // distinguishable in the empty state: a trade that is gone is a
            // permanent condition and retrying it is pointless, while an
            // unreachable admin is temporary and retrying is the whole
            // response. Same wording as the other stores use for the latter.
            error:
              error.code === 'not_found'
                ? `No chart data for ${tradeId ? `trade ${tradeId}` : ticker}.`
                : error.code === 'unavailable'
                  ? 'The admin is not responding.'
                  : error.message,
          });
        },
      });
    };

    return {
      /** Setting the target IS the load — one way in, so there is no path
       *  that can be forgotten. Re-setting the same pair is a no-op, so a
       *  re-render cannot cost a request.
       *
       *  `tradeId` is optional: a watchlist ticker has no plan, and passing
       *  null is how you ask for the chart without one. */
      setTarget(ticker: string | null, tradeId: string | null = null): void {
        if (ticker === store.ticker() && tradeId === store.tradeId()) return;
        // The previous payload goes NOW, not when the new one lands. A chart
        // of the wrong position sitting under the new trade's header for the
        // length of a round trip is worse than an empty pane: it is legible,
        // and nothing about it says it is stale.
        patchState(store, { ticker, tradeId, data: null, error: null });
      },

      /** Bars to load. Also a load, for the same reason `setTrade` is: the
       *  window changes the frame every pane is sliced from, so there is no
       *  "change the window without refetching". */
      setWindow(window: number | null): void {
        if (window === store.window()) return;
        // `data` deliberately survives this one. It is the same position, and
        // the old frame is a truthful — merely differently-scoped — picture of
        // it, so the chart re-scales rather than blanking while the wider
        // request is out.
        patchState(store, { window, error: null });
      },

      /** The retry the failed empty state offers. Re-issues rather than
       *  nudging a signal the effect watches: the state has not changed, and
       *  inventing a nonce to make an effect fire again would make the retry
       *  path depend on effect scheduling. */
      retry(): void {
        load();
      },

      load,
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const trades = events.changes('trades');
      const scan = events.changes('scan');
      effect(() => {
        trades();
        scan();
        store.ticker();
        store.tradeId();
        store.window();
        store.load();
      });
    },
  }),
);
