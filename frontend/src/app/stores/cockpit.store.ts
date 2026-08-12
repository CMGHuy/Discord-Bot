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
import { Cockpit } from '../api/models';

interface CockpitSlice {
  data: Cockpit | null;
  loading: boolean;
  error: string | null;
}

/**
 * The Cockpit's nine metrics.
 *
 * **This is the reference shape.** Every workspace store in Phase 4 copies
 * it: `withState` for what the server said, `withComputed` for anything
 * derived, `withMethods` for the one `load()`, and a `withHooks` effect that
 * turns the relevant events into refetches. Read this one before writing
 * another.
 *
 * Three properties are the point, and each is easy to lose:
 *
 * **It holds one server response and derives everything else.** No merging,
 * no accumulating, no local edits. An event means refetch, so a store that
 * merged would be a second copy of the server's data, slowly diverging --
 * the failure mode spec v13 Decision 3 exists to prevent.
 *
 * **The first effect run IS the initial load.** There is no separate
 * bootstrap call, so the load path and the refetch path cannot drift apart
 * -- a class of bug where the screen is right on arrival and wrong after an
 * update, or vice versa.
 *
 * **A refetch failure keeps the previous data on screen.** Replacing nine
 * live numbers with an error panel because one poll failed is worse than
 * showing slightly stale numbers next to a warning, especially when the
 * event stream reconnects seconds later.
 */
export const CockpitStore = signalStore(
  withState<CockpitSlice>({ data: null, loading: false, error: null }),
  withComputed(({ data }) => ({
    /** True until the first response, and never again. Distinguishes "no
     *  data yet" from "a refetch is in flight", which want different UI:
     *  a skeleton once, and nothing at all thereafter. */
    empty: computed(() => data() === null),

    balance: computed(() => data()?.account_balance ?? null),
    openPnlPct: computed(() => data()?.open_pnl_pct ?? null),
    riskUsedPct: computed(() => data()?.risk_used_pct ?? null),
    riskCapPct: computed(() => data()?.risk_cap_pct ?? null),

    openTrades: computed(() => data()?.open_trades ?? 0),
    avgConfidence: computed(() => data()?.avg_confidence ?? null),
    winRate: computed(() => data()?.win_rate ?? null),
    expectancyR: computed(() => data()?.expectancy_r ?? null),
    equity30d: computed(() => data()?.equity_30d ?? null),

    /** Risk used as a fraction of the cap, for a meter. Null rather than 0
     *  when either side is missing: an empty meter and a meter at zero look
     *  identical and mean opposite things. */
    riskUtilisation: computed(() => {
      const used = data()?.risk_used_pct;
      const cap = data()?.risk_cap_pct;
      if (used == null || cap == null || cap === 0) return null;
      return used / cap;
    }),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    load(): void {
      patchState(store, { loading: true });
      api.cockpit().subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            // `data` is deliberately untouched.
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
      // Reading these inside the effect is the subscription. `account`
      // covers the balance and equity curve; `trades` covers open P&L, open
      // count and risk used, all of which move when a position does.
      const account = events.changes('account');
      const trades = events.changes('trades');
      effect(() => {
        account();
        trades();
        store.load();
      });
    },
  }),
);
