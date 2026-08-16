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
export function createClientPage<T>(rows: () => readonly T[], perPage = 25): ClientPage<T> {
  const requestedPage = signal(1);

  const totalPages = computed(() => Math.max(1, Math.ceil(rows().length / perPage)));

  // Clamp on read rather than in a separate effect: a `setPage` call can
  // race a rows() shrink from either direction, and clamping wherever the
  // value is actually consumed is the one place that can't be out of date.
  // Exposed AS `page` (rather than the raw requested value) so a caller
  // reading `page()` right after a shrink sees the same clamped number the
  // table is actually showing, not a stale request that no longer exists.
  const page = computed(() => Math.min(requestedPage(), totalPages()));

  const visible = computed(() => {
    const start = (page() - 1) * perPage;
    return rows().slice(start, start + perPage);
  });

  const pageSpec = computed<PageSpec>(() => ({
    total: rows().length,
    page: page(),
    perPage,
  }));

  return {
    page,
    visible,
    pageSpec,
    setPage: (n: number) => requestedPage.set(Math.max(1, n)),
  };
}
