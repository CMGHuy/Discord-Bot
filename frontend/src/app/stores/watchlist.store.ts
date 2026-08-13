import { computed, effect, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Subject, debounceTime, switchMap } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { EventStream } from '../api/event-stream';
import { Ticker, TickerSuggestion } from '../api/models';

interface WatchlistSlice {
  tickers: Ticker[];
  loaded: boolean;
  loading: boolean;
  error: string | null;

  adding: boolean;
  /** The last add's outcome, per symbol. Held until the next add: a batch
   *  that added twenty-nine of thirty has one thing worth reading, and it is
   *  the thirtieth. */
  addResult: string | null;
  addError: string | null;

  removing: string | null;
  removeError: string | null;

  suggestions: TickerSuggestion[];
}

/** Split a typed or pasted blob into candidate symbols.
 *
 *  Done here rather than left to the server (which tolerates a raw string)
 *  so that one add and thirty take exactly the same path — the endpoint
 *  absorbs both, and a client with a "single" path would grow its own
 *  validation and then disagree with the bulk one. */
export function parseSymbols(text: string): string[] {
  return text
    .split(/[,\s]+/)
    .map((symbol) => symbol.trim().toUpperCase())
    .filter((symbol) => symbol.length > 0);
}

/**
 * The watchlist — list, add, remove, suggest.
 *
 * Deliberately the thinnest workspace store (spec v14 Decision 9). The list
 * is not paginated, not sorted server-side and not filtered: it is the set
 * of symbols the bot scans, and everything interesting about a symbol lives
 * on its detail view or in Trades.
 *
 * **Add is always a list.** One endpoint absorbs single and bulk, and it
 * reports per-symbol outcomes rather than failing the batch — so pasting
 * thirty symbols with one typo adds twenty-nine and names the one. The
 * message this store builds keeps all three groups for that reason;
 * "added 29" alone hides the only part worth reading.
 *
 * Suggestions are debounced through one RxJS pipeline with `switchMap`, so
 * a fast typist cannot have an early response overwrite a later one — the
 * out-of-order failure that makes a suggestion list flicker between two
 * queries.
 */
export const WatchlistStore = signalStore(
  withState<WatchlistSlice>({
    tickers: [],
    loaded: false,
    loading: false,
    error: null,
    adding: false,
    addResult: null,
    addError: null,
    removing: null,
    removeError: null,
    suggestions: [],
  }),
  withComputed(({ tickers, loaded }) => ({
    /** True until the first response, and never again — distinct from "the
     *  watchlist is empty", which is a real and different state. */
    empty: computed(() => !loaded()),
    count: computed(() => tickers().length),
    /** Symbols already watched, so the add box can say so before a round
     *  trip. The server is still the authority; this only saves the user a
     *  request to be told something the screen already shows. */
    symbols: computed(() => new Set(tickers().map((row) => row.symbol))),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    const load = (): void => {
      patchState(store, { loading: true });
      api.tickers().subscribe({
        next: ({ tickers }) =>
          patchState(store, { tickers, loading: false, loaded: true, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            error:
              error.code === 'unavailable'
                ? 'The admin is not responding.'
                : error.message,
          }),
      });
    };

    /** One pipeline for every keystroke. `switchMap` cancels the in-flight
     *  request, which is what stops an early response landing after a later
     *  one and showing suggestions for a query the box no longer holds. */
    const queries = new Subject<string>();
    queries
      .pipe(
        debounceTime(180),
        switchMap((q) => api.suggestTickers(q)),
        // The store outlives no route, but the pipeline would outlive the
        // store: this is the only subscription here that is not tied to a
        // single request, so it is the only one that needs tearing down.
        takeUntilDestroyed(),
      )
      .subscribe({
        next: ({ results }) => patchState(store, { suggestions: results }),
        // Silent: suggestions are an accelerator, and an error banner for a
        // failed autocomplete would be louder than the feature.
        error: () => patchState(store, { suggestions: [] }),
      });

    return {
      load,

      addTickers(text: string): void {
        const symbols = parseSymbols(text);
        if (!symbols.length) return;

        patchState(store, { adding: true, addResult: null, addError: null });
        api.addTickers(symbols).subscribe({
          next: ({ added, already_present, invalid }) => {
            const parts: string[] = [];
            if (added.length) parts.push(`Added ${added.join(', ')}`);
            // Both of these are the reason the endpoint reports per symbol.
            // Dropping either would turn a partial success into a silent one.
            if (already_present.length) {
              parts.push(`already watched: ${already_present.join(', ')}`);
            }
            if (invalid.length) parts.push(`not valid: ${invalid.join(', ')}`);
            patchState(store, {
              adding: false,
              addResult: parts.join(' · ') || 'Nothing to add.',
              suggestions: [],
            });
            // The server emits `watchlist`, but only outside tests and only
            // once the watcher notices. Reloading here means the row appears
            // with the click rather than a poll later.
            load();
          },
          error: (error: ApiError) =>
            patchState(store, {
              adding: false,
              addError:
                error.code === 'unavailable'
                  ? 'The admin is not responding — nothing was added.'
                  : error.message,
            }),
        });
      },

      removeTicker(symbol: string): void {
        patchState(store, { removing: symbol, removeError: null });
        api.removeTicker(symbol).subscribe({
          next: () => {
            patchState(store, { removing: null });
            load();
          },
          error: (error: ApiError) =>
            patchState(store, {
              removing: null,
              // Named, because the row is still on screen and the user has
              // to know THIS symbol is the one that did not go.
              removeError: `Could not remove ${symbol} — ${error.message}`,
            }),
        });
      },

      suggest(query: string): void {
        const q = query.trim();
        if (!q) {
          patchState(store, { suggestions: [] });
          return;
        }
        queries.next(q);
      },

      clearSuggestions(): void {
        patchState(store, { suggestions: [] });
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const watchlist = events.changes('watchlist');
      effect(() => {
        watchlist();
        store.load();
      });
    },
  }),
);
