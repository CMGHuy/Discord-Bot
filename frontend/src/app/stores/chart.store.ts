import { effect, inject } from '@angular/core';
import { patchState, signalStore, withHooks, withMethods, withState } from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import { ChartResponse } from '../api/models';

interface ChartSlice {
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
 * The interactive trade chart's data — `GET /api/v1/market/chart/:tradeId`.
 *
 * **One request, one loading flag, one error.** The bars, the indicator panes,
 * the volume profile, the plan lines and the overlay all arrive together
 * because the panes have to agree: they are slices of one frame computed at
 * one window, by the same Python that draws the PNG posted to Discord. Five
 * requests would let the RSI pane describe a different frame from the candles
 * above it, which renders perfectly happily and is wrong.
 *
 * **Refetches on `trades`, unlike `OhlcvStore`, and the difference is
 * deliberate rather than an inconsistency.** `OhlcvStore` explicitly does not:
 * its levels only move when the plan does, and refetching a year of candles on
 * every trade event to pick up four horizontal lines is the wrong trade. The
 * reasoning does not carry over here. This payload carries `working_stop` --
 * the live breakeven/trail floor, which moves on every trail step while the
 * position is open -- and an overlay derived from the trade's own confirming
 * sources. A stale chart here does not show slightly old candles; it shows the
 * wrong stop, which is the one number a reader acts on.
 *
 * Not on `scan`: the frame is anchored to the trade, and a scan completing
 * says nothing about this position.
 */
export const ChartStore = signalStore(
  withState<ChartSlice>({
    tradeId: null,
    window: null,
    data: null,
    loading: false,
    error: null,
  }),
  withMethods((store, api = inject(ApiClient)) => {
    /** Shared by the event effect and by `retry`, so the failure path and the
     *  happy path cannot drift into two different requests. */
    const load = (): void => {
      const tradeId = store.tradeId();
      // The Chart tab is constructed before the trade has loaded. A request
      // for `/chart/null` is a 404 the user reads as "this chart is broken".
      if (!tradeId) return;

      const window = store.window();
      patchState(store, { loading: true, error: null });
      api.chart(tradeId, window === null ? {} : { window }).subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            // The two degraded states spec Decision 10 names must be
            // distinguishable in the empty state: a trade that is gone is a
            // permanent condition and retrying it is pointless, while an
            // unreachable admin is temporary and retrying is the whole
            // response. Same wording as the other stores use for the latter.
            error:
              error.code === 'not_found'
                ? `No chart data for trade ${tradeId}.`
                : error.code === 'unavailable'
                  ? 'The admin is not responding.'
                  : error.message,
          }),
      });
    };

    return {
      /** Setting the trade IS the load — one way in, so there is no path that
       *  can be forgotten. Re-setting the same id is a no-op, so a re-render
       *  cannot cost a request. */
      setTrade(tradeId: string | null): void {
        if (tradeId === store.tradeId()) return;
        // The previous payload goes NOW, not when the new one lands. A chart
        // of the wrong position sitting under the new trade's header for the
        // length of a round trip is worse than an empty pane: it is legible,
        // and nothing about it says it is stale.
        patchState(store, { tradeId, data: null, error: null });
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
      effect(() => {
        trades();
        store.tradeId();
        store.window();
        store.load();
      });
    },
  }),
);
