import { computed, inject } from '@angular/core';
import { signalStore, withComputed, withHooks, withMethods, withState } from '@ngrx/signals';

import { TapeRow } from '../api/models';
import { readTapeSymbols, toggleTapeSymbol } from '../ui/tape-prefs';
import { PreferencesStore } from './preferences.store';
import { TapeFeed } from './tape-feed';

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
 * **Refetch, never push, and never here.** The request is the `TapeFeed`'s
 * (v201): this store registers its flagged symbols with the feed as owner
 * `tape`, and the feed polls the union with lane A on the `scan` event and
 * whenever a symbol set changes. There is no independent polling timer.
 *
 * **A failed refetch keeps the previous rows** (the feed's reasoning): the
 * as-of badge is what tells the reader the answer is ageing.
 */
export const TapeStore = signalStore(
  { providedIn: 'root' },
  withState<{ error: string | null }>({ error: null }),
  withComputed((_store, prefs = inject(PreferencesStore), feed = inject(TapeFeed)) => {
    // `equal: sameSymbols` keeps this computed's VALUE stable across an
    // unrelated preference write (a column width, a sort order): without it,
    // `readTapeSymbols` returning a fresh array on every write to
    // `prefs.values()` would re-trigger the feed's refetch effect.
    const symbols = computed(() => readTapeSymbols(prefs.values()), { equal: sameSymbols });
    return {
      symbols,
      visible: computed(() => symbols().length > 0),
      rows: computed(() => symbols()
        .map((symbol) => feed.rows()[symbol])
        .filter((row): row is TapeRow => !!row)
        .sort((a, b) => a.sort_rank - b.sort_rank || a.symbol.localeCompare(b.symbol))),
      asOf: feed.asOf,
      loading: feed.loading,
    };
  }),
  withMethods((_store, feed = inject(TapeFeed), prefs = inject(PreferencesStore)) => ({
    load: (): void => feed.refresh(),

    /** Flag or unflag a ticker. Does not refresh itself: `prefs.update()`
     *  changes `symbols()` and the feed's tracked effect refetches the new
     *  union, so an explicit call here would fire the request twice. */
    toggle(symbol: string): void {
      prefs.update((current) => toggleTapeSymbol(current, symbol));
    },
  })),
  withHooks({
    onInit(store, feed = inject(TapeFeed)) {
      feed.register('tape', store.symbols);
    },
  }),
);
