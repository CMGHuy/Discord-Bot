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
import { Collection, TradeQuery, TradeRow } from '../api/models';
import { PageSpec, SortSpec } from '../ui/data-table/data-table.types';

export const DEFAULT_PER_PAGE = 25;

interface TradesSlice {
  data: Collection<TradeRow> | null;
  query: TradeQuery;
  loading: boolean;
  error: string | null;
}

/** The API spells a sort `field` or `-field`. The table speaks `SortSpec`.
 *  Translating in the store is what lets the table stay ignorant of the wire
 *  format — and lets the wire format change without touching the table. */
export function toSortParam(sort: SortSpec | null): string | undefined {
  if (!sort) return undefined;
  return sort.direction === 'desc' ? `-${sort.key}` : sort.key;
}

export function fromSortParam(param: string | null | undefined): SortSpec | null {
  if (!param) return null;
  return param.startsWith('-')
    ? { key: param.slice(1), direction: 'desc' }
    : { key: param, direction: 'asc' };
}

/**
 * The Trades list — `GET /api/v1/trades`, driven entirely by its query.
 *
 * Follows `CockpitStore`'s shape (one server response in, everything else
 * derived) with one addition: it holds the **query** as well, and the query is
 * a projection of the URL rather than a fourth copy of the truth. The
 * workspace reads the route's query parameters, hands them here, and every
 * control navigates instead of mutating — so a filtered, sorted, paged view
 * survives a reload and can be pasted to someone else, which spec v13
 * Decision 5 requires and a store-only filter silently cannot do.
 *
 * That is also why there is no `setFilter`/`setSort`/`setPage` trio. A single
 * `setQuery` means there is exactly one way state arrives, and it comes from
 * the URL.
 *
 * The refetch on a `trades` event **reissues the current query** rather than
 * reconciling individual rows. Events are thin — they say "trades changed",
 * not what changed — and a store that tried to patch a row would be inventing
 * a second, drifting copy of the server's data.
 */
export const TradesStore = signalStore(
  withState<TradesSlice>({
    data: null,
    query: { page: 1, per_page: DEFAULT_PER_PAGE },
    loading: false,
    error: null,
  }),
  withComputed(({ data, query }) => ({
    rows: computed(() => data()?.items ?? []),

    /** True until the first response and never again: a skeleton belongs on
     *  the first load and nothing at all on a refetch. */
    empty: computed(() => data() === null),

    /** Null while nothing has loaded, so the table shows no pager rather than
     *  a pager claiming one page of nothing. */
    pagination: computed<PageSpec | null>(() => {
      const collection = data();
      if (!collection) return null;
      return {
        total: collection.total,
        page: collection.page,
        perPage: collection.per_page,
      };
    }),

    sort: computed(() => fromSortParam(query().sort)),

    /** How many filters are on, for the filter bar's count. Paging and
     *  sorting are not filters — they do not hide anything, so counting them
     *  would report a filtered list that is not filtered. */
    activeFilterCount: computed(() => {
      const { page, per_page, sort, ...filters } = query();
      return Object.values(filters).filter(
        (value) => value !== undefined && value !== null && value !== '',
      ).length;
    }),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    setQuery(query: TradeQuery): void {
      patchState(store, { query });
    },

    load(): void {
      patchState(store, { loading: true });
      api.trades(store.query()).subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            // `data` is deliberately untouched: a list that vanishes because
            // one poll failed is worse than a slightly stale one beside a
            // warning, especially when the stream reconnects seconds later.
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
      effect(() => {
        // Three dependencies, one loader. Reading the counter is the
        // subscription; reading the query makes a navigation refetch. The
        // first run IS the initial load, so the load path and the refetch
        // path cannot drift apart.
        trades();
        store.query();
        store.load();
      });
    },
  }),
);
