import { HttpClient } from '@angular/common/http';
import { computed, inject } from '@angular/core';
import { patchState, signalStore, withComputed, withMethods, withState } from '@ngrx/signals';
import { defer, Observable, tap } from 'rxjs';

import { ApiError } from '../api/api-error';
import { CancelOutcome, CancelPrecision } from '../api/models';
import { filterRows } from '../workspaces/cancels/cancels.helpers';

export const CANCELS_URL = '/api/v1/cancel-precision';
export type CancelCardKey = 'risk_cap' | 'risk_cap_fill' | 'invalidated' | 'expired' | 'other';
export interface CancelSplit { dim: 'origin' | 'direction' | 'horizon'; value: string }
export interface CancelFilter {
  card: CancelCardKey | null;
  outcome: CancelOutcome | null;
  split: CancelSplit | null;
}
export const NO_FILTER: CancelFilter = Object.freeze({ card: null, outcome: null, split: null });

interface CancelsSlice {
  data: CancelPrecision | null;
  loading: boolean;
  error: string | null;
  filter: CancelFilter;
}

function messageOf(e: unknown): string {
  if (e instanceof ApiError) {
    return e.code === 'unavailable'
      ? 'The admin is not responding -- these figures may be stale.'
      : e.message;
  }
  return 'The cancel replay could not be loaded.';
}

const toggle = <T>(current: T | null, next: T | null): T | null => (current === next ? null : next);

/**
 * The cancelled-plan precision payload and the screen's one filter.
 *
 * Root-provided on purpose: the server memoises the payload for an hour, and
 * keeping it across visits gives stale-while-revalidate (a revisit shows the
 * last figures while the reload runs). A failed reload never clears `data`.
 */
export const CancelsStore = signalStore(
  { providedIn: 'root' },
  withState<CancelsSlice>({ data: null, loading: false, error: null, filter: NO_FILTER }),
  withComputed(({ data, filter }) => ({
    rows: computed(() => filterRows(data()?.rows ?? [], filter())),
  })),
  withMethods((store, http = inject(HttpClient)) => ({
    load(): Observable<CancelPrecision> {
      return defer(() => {
        patchState(store, { loading: true, error: null });
        return http.get<CancelPrecision>(CANCELS_URL);
      }).pipe(tap({
        next: (data) => patchState(store, { data, loading: false }),
        error: (e: unknown) => patchState(store, { loading: false, error: messageOf(e) }),
      }));
    },
    pickCard(card: CancelCardKey | null): void {
      patchState(store, { filter: { ...store.filter(), card: toggle(store.filter().card, card) } });
    },
    pickOutcome(outcome: CancelOutcome | null): void {
      patchState(store, { filter: { ...store.filter(), outcome: toggle(store.filter().outcome, outcome) } });
    },
    pickSplit(split: CancelSplit | null): void {
      const cur = store.filter().split;
      const same = split !== null && cur !== null && cur.dim === split.dim && cur.value === split.value;
      patchState(store, { filter: { ...store.filter(), split: same ? null : split } });
    },
    clearFilter(): void {
      patchState(store, { filter: NO_FILTER });
    },
  })),
);
