import { inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { Preferences } from '../api/models';

/** How long a burst of changes settles before it is written. */
export const WRITE_DEBOUNCE_MS = 750;

interface PreferencesSlice {
  values: Preferences;
  loaded: boolean;
}

/**
 * Per-user UI state, persisted server-side.
 *
 * **Not localStorage** (spec v13): the same person on a laptop and a desktop
 * should see the same columns, and localStorage fails that silently -- it
 * looks like it works right up until you sit at the other machine.
 *
 * Read once, at shell construction. There is no refetch on an event and no
 * `settings` subscription: this is the one piece of state whose only writer
 * is this browser, so re-reading it could only ever overwrite what the user
 * just did with what they did a moment earlier.
 */
export const PreferencesStore = signalStore(
  { providedIn: 'root' },
  withState<PreferencesSlice>({ values: {}, loaded: false }),
  withMethods((store, api = inject(ApiClient)) => {
    let timer: ReturnType<typeof setTimeout> | null = null;

    /**
     * Write after the burst settles.
     *
     * A column picker produces one change per checkbox, so an un-debounced
     * save would PUT four times while someone chooses four columns. The
     * write is a whole-object replace, so only the last one carries
     * anything the others did not.
     */
    const scheduleWrite = () => {
      if (timer !== null) clearTimeout(timer);
      timer = setTimeout(() => {
        timer = null;
        api.savePreferences(store.values()).subscribe({
          // Silent on failure, deliberately. Losing a column preference is
          // not worth a toast over the workspace someone is reading, and
          // the local state stays correct for this session either way.
          error: () => undefined,
        });
      }, WRITE_DEBOUNCE_MS);
    };

    return {
      load(): void {
        if (store.loaded()) return;
        api.preferences().subscribe({
          next: ({ preferences }) =>
            patchState(store, { values: preferences ?? {}, loaded: true }),
          // A failed read leaves defaults in place and marks it loaded, so
          // one bad request does not retry on every navigation.
          error: () => patchState(store, { loaded: true }),
        });
      },

      /** The whole preferences map, for the pure readers in `ui/table-prefs`.
       *
       *  Exposed rather than adding a store method per preference: the
       *  readers are pure functions over this object precisely so they can be
       *  tested without a store, and a method per key would be a second place
       *  to keep the key names correct. */
      values(): Preferences {
        return store.values();
      },

      /** Whether the server's preferences have arrived.
       *
       *  Exposed because reading `values()` before this is true yields the
       *  empty defaults, and a workspace that reads once in its constructor
       *  would silently show the default layout to everyone -- the write
       *  path works, so the preference is saved and then ignored, which is
       *  the hardest version of this bug to notice. */
      isLoaded(): boolean {
        return store.loaded();
      },

      /** Apply a pure updater from `ui/table-prefs` and schedule the write.
       *
       *  Takes a function rather than a key and a value so the caller cannot
       *  invent a key spelling — the updaters own the key format, and this
       *  only owns when the result is persisted. */
      update(mutate: (prefs: Preferences) => Preferences): void {
        patchState(store, (state) => ({ values: mutate(state.values) }));
        scheduleWrite();
      },

      /** Visible column ids for a table, or null for "the table's default".
       *
       *  Null rather than an empty array: a table the user has never
       *  touched and a table with every column hidden are different states,
       *  and conflating them would make the second unrepresentable. */
      columns(tableId: string): string[] | null {
        return store.values().tables?.[tableId] ?? null;
      },

      setColumns(tableId: string, columns: string[]): void {
        patchState(store, (state) => ({
          values: {
            ...state.values,
            tables: { ...state.values.tables, [tableId]: columns },
          },
        }));
        scheduleWrite();
      },

      /** Forget a table's preference and fall back to its default. */
      resetColumns(tableId: string): void {
        patchState(store, (state) => {
          const tables = { ...state.values.tables };
          delete tables[tableId];
          return { values: { ...state.values, tables } };
        });
        scheduleWrite();
      },

      /** Write immediately instead of waiting out the debounce. */
      flush(): void {
        if (timer === null) return;
        clearTimeout(timer);
        timer = null;
        api.savePreferences(store.values()).subscribe({ error: () => undefined });
      },
    };
  }),
);
