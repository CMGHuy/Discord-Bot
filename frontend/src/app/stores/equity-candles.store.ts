import { computed, effect, inject, untracked } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { EventStream, MARKET_DATA_MIN_INTERVAL_MS } from '../api/event-stream';
import { EquityBasis, EquityCandlesResponse, EquityTimeframe } from '../api/models';
import {
  HISTORY_PAGE_LIMIT,
  mergeLatest,
  prependPage,
} from '../workspaces/dashboard/panels/equity-range.model';
import {
  EquityChartPrefs,
  readEquityChartPrefs,
  writeEquityChartPrefs,
} from '../ui/equity-chart-prefs';
import { PreferencesStore } from './preferences.store';

interface EquityCandlesSlice {
  data: EquityCandlesResponse | null;
  loading: boolean;
  error: string | null;
  /** v181: the last answer that set the oldest candle said more exist. */
  hasMore: boolean;
  /** v181: an older page is in flight. */
  pageLoading: boolean;
  /** v181: the last older page failed; the chart shows a retry note. */
  pageError: boolean;
  /** v181: the chart shows the newest candle (drives "↦ Latest"). */
  atLiveEdge: boolean;
}

const INITIAL: EquityCandlesSlice = {
  data: null, loading: false, error: null,
  hasMore: false, pageLoading: false, pageError: false, atLiveEdge: true,
};

/** What a timeframe or basis change resets: the old view's paging state. */
const FRESH_VIEW = { hasMore: false, pageLoading: false, pageError: false, atLiveEdge: true };

export const EQUITY_CANDLES_ERROR = 'Equity candles could not be loaded.';

/**
 * The Dashboard's equity candles — spec v172 § 5.
 *
 * **Refetch, never push**, like `TapeStore`: the onInit effect runs on the
 * throttled `scan` event and whenever the chosen timeframe or basis changes,
 * and its first run is the initial load. The trade monitor's samples raise no
 * SSE event of their own, so the newest candle grows with the scan cadence.
 *
 * `tf`/`basis` are two string computeds over the server-backed preferences,
 * so an unrelated preference write (a column width) compares equal and does
 * not refetch.
 *
 * **A failed refetch keeps the candles already shown**; only a failed first
 * load (nothing to show) surfaces `error` for `sb-async`'s retry. Switching
 * timeframe or basis drops the other view's candles at once, so a 1H request
 * in flight never sits under daily candles.
 *
 * **Pages (v181 § 2).** `loadOlder()` prepends `HISTORY_PAGE_LIMIT` older
 * candles; a scan refresh merges the newest candles over them
 * (`mergeLatest`), so paged history survives the scan cadence. A page that
 * answers after a view change is dropped by the `view` counter. A failed
 * page keeps every candle and sets `pageError`; the next call retries.
 */
export const EquityCandlesStore = signalStore(
  { providedIn: 'root' },
  withState<EquityCandlesSlice>(INITIAL),
  withComputed((_store, prefs = inject(PreferencesStore)) => ({
    tf: computed<EquityTimeframe>(() => readEquityChartPrefs(prefs.values()).tf),
    basis: computed<EquityBasis>(() => readEquityChartPrefs(prefs.values()).basis),
  })),
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;
    // Bumped on every view change; a page answering for an older view is dropped.
    let view = 0;

    // untracked throughout: load() runs inside the onInit effect, and a
    // tracked read of `data`/`hasMore` would make every response re-trigger it.
    const applyLatest = (response: EquityCandlesResponse): void => {
      const shown = untracked(() => store.data());
      const sameView = shown !== null && shown.tf === response.tf && shown.basis === response.basis;
      const candles = sameView ? mergeLatest(shown.candles, response.candles) : response.candles;
      const keptOlder = candles.length > response.candles.length;
      patchState(store, {
        data: { ...response, candles },
        hasMore: keptOlder ? untracked(() => store.hasMore()) : response.has_more === true,
        loading: false,
        error: null,
      });
    };

    const load = (): void => {
      const tf = store.tf();
      const basis = store.basis();
      const previous = untracked(() => store.data());
      const sameView = previous !== null && previous.tf === tf && previous.basis === basis;
      const request = ++latestRequest;
      if (!sameView) view += 1;
      patchState(store, {
        loading: true, error: null, data: sameView ? previous : null,
        ...(sameView ? {} : FRESH_VIEW),
      });
      api.equityCandles(tf, basis).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.candles)) {
            patchState(store, { loading: false });
            return;
          }
          applyLatest(response);
        },
        error: () => {
          if (request !== latestRequest) return;
          // untracked for the same reason: a synchronous error (a test's
          // throwError) lands inside the effect's run.
          const shown = untracked(() => store.data());
          patchState(store, { loading: false, error: shown ? null : EQUITY_CANDLES_ERROR });
        },
      });
    };

    const loadOlder = (): void => {
      const shown = untracked(() => store.data());
      const busy = untracked(() => store.pageLoading());
      const more = untracked(() => store.hasMore());
      if (!shown || shown.candles.length === 0 || busy || !more) return;
      const pageView = view;
      patchState(store, { pageLoading: true, pageError: false });
      api.equityCandles(shown.tf, shown.basis, HISTORY_PAGE_LIMIT, shown.candles[0].t).subscribe({
        next: (page) => {
          if (pageView !== view) return;
          const current = untracked(() => store.data());
          if (!current || !page || !Array.isArray(page.candles)) {
            patchState(store, { pageLoading: false });
            return;
          }
          patchState(store, {
            data: { ...current, candles: prependPage(current.candles, page.candles) },
            hasMore: page.has_more === true,
            pageLoading: false,
          });
        },
        error: () => {
          if (pageView !== view) return;
          patchState(store, { pageLoading: false, pageError: true });
        },
      });
    };

    // Does not call `load()`: the write changes `tf()`/`basis()`, and the
    // tracked onInit effect refetches once as a result.
    const write = (value: EquityChartPrefs): void =>
      prefs.update((current) => writeEquityChartPrefs(current, value));

    return {
      load,
      loadOlder,
      setTimeframe(tf: EquityTimeframe): void {
        write({ tf, basis: store.basis() });
      },
      setBasis(basis: EquityBasis): void {
        write({ tf: store.tf(), basis });
      },
      setAtLiveEdge(atEdge: boolean): void {
        patchState(store, { atLiveEdge: atEdge });
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const scan = events.changes('scan', { minIntervalMs: MARKET_DATA_MIN_INTERVAL_MS });
      effect(() => {
        scan();
        store.load();
      });
    },
  }),
);
