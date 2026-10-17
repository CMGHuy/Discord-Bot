import { Signal, computed, inject } from '@angular/core';

import { PreferencesStore } from '../stores/preferences.store';
import { ViewportService } from './breakpoints';
import { readTablePerPage, writeTablePerPage } from './table-prefs';

export interface TablePerPage {
  /** Rows per page now: the saved choice for this table and device class,
   *  else the device default. Re-evaluates when the viewport crosses `md`. */
  value: Signal<number>;
  set(perPage: number): void;
}

/** One table's rows-per-page, wired to the saved preferences and the
 *  viewport. Call from an injection context. */
export function tablePerPage(tableId: string): TablePerPage {
  const preferences = inject(PreferencesStore);
  const viewport = inject(ViewportService);
  return {
    value: computed(() => readTablePerPage(preferences.values(), tableId, viewport.isNarrow())),
    set: (perPage) => preferences.update((prefs) => writeTablePerPage(prefs, tableId, viewport.isNarrow(), perPage)),
  };
}
