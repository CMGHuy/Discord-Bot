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
import { EventStream } from '../api/event-stream';
import { TapeRow } from '../api/models';
import { readTapeSymbols, toggleTapeSymbol } from '../ui/tape-prefs';
import { PreferencesStore } from './preferences.store';

interface TapeSlice {
  rows: TapeRow[];
  asOf: string | null;
}

/**
 * Lane B of the shell tape — spec v77.
 *
 * **Refetch, never push.** The SSE layer is a `stat()` watcher that carries a
 * concern name and no payload, so this store subscribes to the `scan` event
 * (`EventStream.changes('scan')`, the reference pattern in `chart.store.ts`)
 * and refetches, exactly as every other workspace does. There is no
 * independent polling timer: an open tab must not add recurring network
 * load, and the `onInit` effect's first run doubles as the initial load —
 * there is no separate bootstrap path to drift out of sync with the refetch
 * path.
 *
 * **A failed refetch keeps the previous rows.** Blanking the tape on a
 * transient error would read as "every position closed", which is the
 * dangerous direction to be wrong in. The as-of badge is what tells the reader
 * the answer is ageing.
 */
export const TapeStore = signalStore(
  { providedIn: 'root' },
  withState<TapeSlice>({ rows: [], asOf: null }),
  withComputed((store, prefs = inject(PreferencesStore)) => ({
    symbols: computed(() => readTapeSymbols(prefs.values())),
  })),
  withComputed((store) => ({
    visible: computed(() => store.symbols().length > 0),
  })),
  withMethods((store, api = inject(ApiClient), prefs = inject(PreferencesStore)) => {
    let latestRequest = 0;
    // A local binding, not `this.load()` from inside the returned object:
    // `toggle` must be able to call it however the store is destructured at
    // the call site, and `this` there is not guaranteed to be the store.
    const load = (): void => {
      const symbols = store.symbols();
      if (!symbols.length) {
        patchState(store, { rows: [], asOf: null });
        return;
      }
      // A quick `toggle()` overlapping a `scan`-triggered refetch can have
      // their HTTP responses resolve out of order. `latestRequest` -- the
      // same counter `ChartStore` uses -- makes the STALE one a no-op rather
      // than whichever happens to land last.
      const request = ++latestRequest;
      api.tape(symbols).subscribe({
        next: (response) => {
          if (request !== latestRequest) return;
          if (!response || !Array.isArray(response.rows)) return;
          const rows = [...response.rows].sort(
            (a, b) => a.sort_rank - b.sort_rank || a.symbol.localeCompare(b.symbol),
          );
          patchState(store, { rows, asOf: response.as_of ?? null });
        },
        // Deliberately silent, and deliberately non-destructive: see the class
        // comment. A toast over the workspace someone is reading is not worth
        // a ticker strip going one cycle stale.
        error: () => undefined,
      });
    };

    return {
      load,

      /** Flag or unflag a ticker, then refetch so the tape reflects it at once. */
      toggle(symbol: string): void {
        prefs.update((current) => toggleTapeSymbol(current, symbol));
        load();
      },
    };
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
