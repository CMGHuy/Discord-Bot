import { computed, inject } from '@angular/core';
import { ParamMap, Params } from '@angular/router';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { Observable, forkJoin, of } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { LedgerRow, ResearchLedger, StrategyRow } from '../api/models';
import { routeRequest } from '../routing/route-request';
import { PageSpec, SortSpec } from '../ui/data-table/data-table.types';

export const LEDGER_PAGE_SIZE = 25;

/** What the toolbar can narrow by. All three live in the query string, so a
 *  filtered view is a link. An empty value means "no filter on this axis". */
export interface LedgerFilters {
  verdicts: string[];
  instrument: string;
  search: string;
}

const NO_FILTERS: LedgerFilters = { verdicts: [], instrument: '', search: '' };
const NEWEST_FIRST: SortSpec = { key: 'date', direction: 'desc' };

export function filtersFromParams(params: ParamMap): LedgerFilters {
  return {
    verdicts: (params.get('verdict') ?? '').split(',').filter((v) => v !== ''),
    instrument: params.get('instrument') ?? '',
    search: params.get('q') ?? '',
  };
}

/** Nulls, not empty strings: `queryParamsHandling: 'merge'` drops a null key,
 *  so a default never lingers in the URL. */
export function filtersToParams(filters: LedgerFilters): Params {
  return {
    verdict: filters.verdicts.length ? filters.verdicts.join(',') : null,
    instrument: filters.instrument || null,
    q: filters.search || null,
  };
}

function matchesSearch(row: LedgerRow, search: string): boolean {
  const needle = search.trim().toLowerCase();
  return needle === '' || row.id.toLowerCase().includes(needle)
    || row.hypothesis.toLowerCase().includes(needle);
}

/** `anyVerdict` skips the verdict axis: the chip counts need every row the
 *  OTHER filters allow, or selecting one verdict would zero the rest. */
export function filterLedger(
  rows: readonly LedgerRow[],
  filters: LedgerFilters,
  opts: { anyVerdict?: boolean } = {},
): LedgerRow[] {
  return rows.filter((row) =>
    (opts.anyVerdict || filters.verdicts.length === 0 || filters.verdicts.includes(row.verdict))
    && (filters.instrument === '' || row.instrument === filters.instrument)
    && matchesSearch(row, filters.search));
}

type SortValue = string | number | null;

/** A null figure is "not recorded", so it sorts last whichever way the
 *  column runs: it is not the smallest value and not the largest. */
export function sortLedger(rows: readonly LedgerRow[], sort: SortSpec): LedgerRow[] {
  const sign = sort.direction === 'asc' ? 1 : -1;
  const value = (row: LedgerRow) => (row as unknown as Record<string, SortValue>)[sort.key] ?? null;
  return [...rows].sort((a, b) => {
    const x = value(a);
    const y = value(b);
    if (x === null || y === null) return (x === null ? 1 : 0) - (y === null ? 1 : 0);
    if (x === y) return 0;
    return (x < y ? -1 : 1) * sign;
  });
}

interface ResearchData {
  ledger: ResearchLedger;
  registry: StrategyRow[];
}

interface ResearchSlice {
  data: ResearchData | null;
  loading: boolean;
  error: string | null;
  filters: LedgerFilters;
  sort: SortSpec;
  page: number;
  selectedId: string | null;
}

/**
 * The Research workspace's data: the pre-registration ledger and the
 * strategy registry, fetched together and never refetched on an event.
 *
 * Both change only when a commit lands and deploys, which cannot happen
 * while the page is open, so there is no event wiring. The ledger is small
 * (a few dozen rows), so filtering, sorting and paging all happen here.
 */
export const ResearchStore = signalStore(
  withState<ResearchSlice>({
    data: null,
    loading: false,
    error: null,
    filters: NO_FILTERS,
    sort: NEWEST_FIRST,
    page: 1,
    selectedId: null,
  }),
  withComputed(({ data, filters, sort }) => ({
    registry: computed<StrategyRow[]>(() => data()?.registry ?? []),
    verdicts: computed<string[]>(() => data()?.ledger.verdicts ?? []),
    instruments: computed<string[]>(() => data()?.ledger.instruments ?? []),
    /** How many ledger rows have a p-value: the BH family behind every q. */
    familySize: computed(() => data()?.ledger.q_family_m ?? 0),
    matching: computed<LedgerRow[]>(() =>
      sortLedger(filterLedger(data()?.ledger.rows ?? [], filters()), sort())),
    verdictCounts: computed<Record<string, number>>(() => {
      const pool = filterLedger(data()?.ledger.rows ?? [], filters(), { anyVerdict: true });
      const counts: Record<string, number> = {};
      for (const verdict of data()?.ledger.verdicts ?? []) counts[verdict] = 0;
      for (const row of pool) counts[row.verdict] = (counts[row.verdict] ?? 0) + 1;
      return counts;
    }),
    activeFilterCount: computed(() => {
      const f = filters();
      return (f.verdicts.length ? 1 : 0) + (f.instrument ? 1 : 0) + (f.search ? 1 : 0);
    }),
  })),
  withComputed(({ data, matching, page, selectedId }) => {
    const current = computed(() =>
      Math.min(page(), Math.max(1, Math.ceil(matching().length / LEDGER_PAGE_SIZE))));
    return {
      visible: computed<LedgerRow[]>(() => {
        const start = (current() - 1) * LEDGER_PAGE_SIZE;
        return matching().slice(start, start + LEDGER_PAGE_SIZE);
      }),
      // The count BEFORE slicing; `visible().length` would show one page forever.
      pageSpec: computed<PageSpec>(() => ({
        total: matching().length, page: current(), perPage: LEDGER_PAGE_SIZE,
      })),
      /** Looked up in the whole ledger, so a drawer survives a filter change. */
      selected: computed<LedgerRow | null>(() =>
        data()?.ledger.rows.find((row) => row.id === selectedId()) ?? null),
    };
  }),
  withMethods((store, api = inject(ApiClient)) => {
    const resolve = (): Observable<void> => routeRequest(
      forkJoin({ ledger: api.researchLedger(), registry: api.analyticsRegistry() }),
      {
        start: () => patchState(store, { loading: true }),
        next: ({ ledger, registry }) => patchState(store, {
          data: { ledger, registry: registry.registry }, loading: false, error: null,
        }),
        error: (error) => patchState(store, {
          loading: false,
          error: error.code === 'unavailable'
            ? 'The admin is not responding — the ledger is unavailable.'
            : error.message,
        }),
      },
    );
    return {
      resolve,
      /** For the route resolver. Every filter change is a navigation, and the
       *  resolver runs on each one; the ledger is fetched once per visit. */
      ensureLoaded(): Observable<void> { return store.data() ? of(undefined) : resolve(); },
      load(): void { resolve().subscribe({ error: () => undefined }); },
      /** Sets the filters from the URL. A filter change always returns to page 1. */
      hydrate(filters: LedgerFilters): void { patchState(store, { filters, page: 1 }); },
      setSort(sort: SortSpec): void { patchState(store, { sort, page: 1 }); },
      setPage(n: number): void { patchState(store, { page: Math.max(1, n) }); },
      select(id: string | null): void { patchState(store, { selectedId: id }); },
    };
  }),
);
