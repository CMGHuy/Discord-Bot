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
import { TradeDetail } from '../api/models';

interface TradeDetailSlice {
  id: string | null;
  data: TradeDetail | null;
  loading: boolean;
  error: string | null;
}

/**
 * One trade, for the detail view — `GET /api/v1/trades/:id`.
 *
 * Same shape as `CockpitStore` and `TradesStore`: one server response in,
 * everything derived, and an effect that turns events into refetches. The
 * `id` lives in state rather than being passed to `load()` so that setting it
 * IS the load, exactly as setting the query is the load in `TradesStore` —
 * one way in, and no path that can be forgotten.
 *
 * Refetches on `trades` (price, status, sizing all move when a position does)
 * and on `journal` (the note is part of this response, and the Notes tab
 * writes it). Not on `account`: a balance change does not alter one trade.
 */
export const TradeDetailStore = signalStore(
  withState<TradeDetailSlice>({ id: null, data: null, loading: false, error: null }),
  withComputed(({ data }) => ({
    empty: computed(() => data() === null),
    trade: computed(() => data()),
    /** The heavy half. Null before the first response rather than an empty
     *  object, so a template cannot read a plan field that has not arrived
     *  and render a confident em dash for it. */
    detail: computed(() => data()?.detail ?? null),

    /** Risk and reward per share, from the plan's own levels. Null unless
     *  both sides are known — half an R:R is not an R:R. */
    riskPerShare: computed(() => {
      const trade = data();
      if (!trade || trade.entry === null || trade.stop_loss === null) return null;
      return Math.abs(trade.entry - trade.stop_loss);
    }),
    rewardPerShare: computed(() => {
      const trade = data();
      if (!trade || trade.entry === null || trade.target === null) return null;
      return Math.abs(trade.target - trade.entry);
    }),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    /** Setting the id is what triggers the load. */
    setId(id: string): void {
      if (id === store.id()) return;
      // Clearing `data` is right here and wrong on a refetch: this is a
      // different trade, and showing the previous one's numbers under the new
      // one's heading would be worse than a skeleton.
      patchState(store, { id, data: null, error: null });
    },

    load(): void {
      const id = store.id();
      if (!id) return;

      patchState(store, { loading: true });
      api.trade(id).subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            error:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    },
  })),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const trades = events.changes('trades');
      const journal = events.changes('journal');
      effect(() => {
        trades();
        journal();
        store.id();
        store.load();
      });
    },
  }),
);
