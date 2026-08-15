import { computed, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { VersionHistory } from '../api/models';

/** One ui version's row in the matrix, pre-resolved to grid geometry.
 *
 * `start`/`span` are 1-based CSS grid column values rather than array
 * indices, because that is what the template needs and computing it in two
 * places is how the bar and the dots drift apart by one column. */
export interface MatrixRow {
  ui: string;
  botMin: string;
  botMax: string;
  /** 1-based grid column of `botMin`. */
  start: number;
  /** Columns the span covers, inclusive of both ends. */
  span: number;
  /** Column indices (1-based) where this exact pair actually shipped.
   *  A subset of the span: the span is min..max, and nothing guarantees
   *  every intermediate bot version shipped with this ui. */
  shipped: number[];
  firstSeen: string;
  lastSeen: string;
  /** This is the ui version running right now. */
  current: boolean;
}

interface VersionsSlice {
  data: VersionHistory | null;
  loading: boolean;
  error: string | null;
}

/**
 * The ui/bot pairing history — what the Versions workspace draws.
 *
 * Read-only and loaded once. There is no event wiring and no refetch: the
 * underlying file changes only when someone cuts a release and re-runs
 * `scripts/dev/build_version_matrix.py`, which cannot happen while the page is
 * open in front of them.
 *
 * **The geometry is computed here, not in the template.** A matrix row needs
 * its bar's start column, its width, and the columns carrying a dot; deriving
 * those inline would mean three passes over `bot_versions` per row inside a
 * change-detection cycle, and — worse — three places for an off-by-one to
 * disagree about whether columns are 0- or 1-based.
 */
export const VersionsStore = signalStore(
  withState<VersionsSlice>({ data: null, loading: false, error: null }),
  withComputed(({ data }) => {
    /** Column lookup, built once per payload rather than per row. */
    const botIndex = computed(() => {
      const index = new Map<string, number>();
      (data()?.bot_versions ?? []).forEach((v, i) => index.set(v, i + 1));
      return index;
    });

    return {
      empty: computed(() => data() === null),

      /** The column axis, oldest bot version first — time runs left to right,
       *  which is the only direction a version axis reads naturally. */
      botAxis: computed<string[]>(() => data()?.bot_versions ?? []),

      /** Rows newest ui first: the version you are on, or thinking about
       *  upgrading from, is at the top where it needs no scrolling. */
      rows: computed<MatrixRow[]>(() => {
        const payload = data();
        if (!payload) return [];
        const index = botIndex();
        const liveUi = payload.live?.ui;

        return [...payload.ranges]
          .reverse()
          .map((range) => {
            const start = index.get(range.bot_min) ?? 1;
            const end = index.get(range.bot_max) ?? start;
            return {
              ui: range.ui,
              botMin: range.bot_min,
              botMax: range.bot_max,
              start,
              span: Math.max(1, end - start + 1),
              shipped: payload.pairs
                .filter((pair) => pair.ui === range.ui)
                .map((pair) => index.get(pair.bot))
                .filter((column): column is number => column !== undefined),
              firstSeen: range.first_seen,
              lastSeen: range.last_seen,
              current: range.ui === liveUi,
            };
          });
      }),

      live: computed(() => data()?.live ?? null),
      /** VERSION.json has moved past the frozen file — the page is behind,
       *  and says so rather than quietly showing an incomplete matrix. */
      stale: computed(() => data()?.stale ?? false),
      generatedAt: computed(() => data()?.generated_at ?? null),
      /** The server's own wording for what a pair does and does not claim.
       *  Rendered verbatim; see `models.ts`. */
      basis: computed(() => data()?.basis ?? null),
      pairCount: computed(() => data()?.pairs?.length ?? 0),
    };
  }),
  withMethods((store, api = inject(ApiClient)) => ({
    load(): void {
      patchState(store, { loading: true });
      api.versionHistory().subscribe({
        next: (data) => patchState(store, { data, loading: false, error: null }),
        error: (error: ApiError) =>
          patchState(store, {
            loading: false,
            error:
              error.code === 'unavailable'
                ? 'The admin is not responding — the version history is unavailable.'
                : error.message,
          }),
      });
    },
  })),
  withHooks({
    onInit(store) {
      store.load();
    },
  }),
);
