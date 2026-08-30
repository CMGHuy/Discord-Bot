import { Signal, computed, signal } from '@angular/core';
import { PageSpec } from './data-table.types';

export interface ClientPage<T> {
  /** The active (clamped) page number. Read-only: nothing outside this
   *  factory ever needs to set it directly -- `setPage` is the only
   *  mutator, so this is a plain `Signal`, not a `WritableSignal`. */
  page: Signal<number>;
  visible: Signal<T[]>;
  pageSpec: Signal<PageSpec>;
  setPage(n: number): void;
}

/** Client-side pagination over an already-fetched array — Analytics data
 *  isn't page-shaped at the API level the way Trades' collection endpoint
 *  is, so slicing what's already in hand is simpler and needs no backend
 *  change. `rows` is a function (not a plain array) so this stays correct
 *  when the underlying store re-fetches and the array identity changes. */
export function createClientPage<T>(
  rows: () => readonly T[],
  perPage: number | (() => number) = 25,
): ClientPage<T> {
  const size = typeof perPage === 'function' ? perPage : () => perPage;
  const requestedPage = signal(1);
  const effective = computed(() => (size() > 0 ? size() : Math.max(1, rows().length)));
  const totalPages = computed(() => Math.max(1, Math.ceil(rows().length / effective())));
  const page = computed(() => Math.min(requestedPage(), totalPages()));
  const visible = computed(() => {
    const start = (page() - 1) * effective();
    return rows().slice(start, start + effective());
  });
  const pageSpec = computed<PageSpec>(() => ({ total: rows().length, page: page(), perPage: size() }));
  return { page, visible, pageSpec, setPage: (n: number) => requestedPage.set(Math.max(1, n)) };
}