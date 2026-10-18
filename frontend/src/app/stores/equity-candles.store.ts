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
  EquityChartPrefs,
  readEquityChartPrefs,
  writeEquityChartPrefs,
} from '../ui/equity-chart-prefs';
import { PreferencesStore } from './preferences.store';

interface EquityCandlesSlice {
  data: EquityCandlesResponse | null;
  loading: boolean;
  error: string | null;
}

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
 */
export const EquityCandlesStore = signalStore(
  { providedIn: 'root' },
  withState<EquityCandlesSlice>({ data: null, loading: false, error: null }),
  withComputed((_store, prefs = inject(PreferencesStore)) => ({
    tf: computed<EquityTimeframe>(() => readEquityChartPrefs(prefs.values()).tf),
    basis: computed<EquityBasis>(() => readEquityChartPrefs(prefs.values()).basis),
  })),
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;

    const load = (): void => {
      const tf = store.tf();
      const basis = store.basis();
      // untracked: `load()` runs inside the onInit effect, and a tracked read
      // of `data` would make every response re-trigger the effect.
      const previous = untracked(() => store.data());
      const sameView = previous !== null && previous.tf === tf && previous.basis === basis;
      const request = ++latestRequest;
      patchState(store, { loading: true, error: null, data: sameView ? previous : null });
      api.equityCandles(tf, basis).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.candles)) {
            patchState(store, { loading: false });
            return;
          }
          patchState(store, { data: response, loading: false, error: null });
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

    // Does not call `load()`: the write changes `tf()`/`basis()`, and the
    // tracked onInit effect refetches once as a result.
    const write = (value: EquityChartPrefs): void =>
      prefs.update((current) => writeEquityChartPrefs(current, value));

    return {
      load,
      setTimeframe(tf: EquityTimeframe): void {
        write({ tf, basis: store.basis() });
      },
      setBasis(basis: EquityBasis): void {
        write({ tf: store.tf(), basis });
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
