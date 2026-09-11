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
 * Order-sensitive array equality for `string[]`.
 *
 * `readTapeSymbols` already normalises order (dedup, trim, uppercase,
 * insertion order preserved), so two reads that flag the same set of symbols
 * the same way always come back in the same order -- an order-sensitive
 * comparison is enough, and cheaper than sorting first.
 */
function sameSymbols(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((symbol, i) => symbol === b[i]);
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
  withComputed((_store, prefs = inject(PreferencesStore)) => ({
    // `equal: sameSymbols` is what keeps this computed's VALUE stable across
    // an unrelated preference write (a column width, a sort order): without
    // it, `readTapeSymbols` returning a fresh array reference on every write
    // to `prefs.values()` would count as a change to any effect that reads
    // `symbols()`, including the refetch effect in `withHooks` below -- the
    // same over-firing bug `untracked()` was once (wrongly) covering for.
    symbols: computed(() => readTapeSymbols(prefs.values()), { equal: sameSymbols }),
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

      /** Flag or unflag a ticker.
       *
       *  Does not call `load()` itself: `prefs.update()` changes
       *  `store.symbols()` (once the new symbol set differs, per
       *  `sameSymbols` above), and the tracked `onInit` effect below re-runs
       *  and refetches as a result. A second explicit call here would fire
       *  the request twice for one toggle. */
      toggle(symbol: string): void {
        prefs.update((current) => toggleTapeSymbol(current, symbol));
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const scan = events.changes('scan');
      // Tracked, deliberately: `load()` reads `store.symbols()` (transitively,
      // through `prefs.values()`), so this effect re-runs on a genuine `scan`
      // AND whenever the flagged-symbol set actually changes -- which is
      // also what makes the tape populate once `PreferencesStore`'s async
      // preferences GET resolves after the shell's synchronous first
      // `tape.load()` call found nothing to load. `sameSymbols` on the
      // `symbols` computed is what stops an unrelated preference write (not
      // touching `tape.symbols`) from re-triggering this.
      effect(() => {
        scan();
        store.load();
      });
    },
  }),
);
