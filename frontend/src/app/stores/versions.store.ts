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
import { Release, VersionFilter, VersionHistory } from '../api/models';
import { PageSpec } from '../ui/data-table/data-table.types';

export const PAGE_SIZE = 25;

/** One component's run at one version, as a fraction of the strip. */
export interface LaneSegment {
  version: string;
  /** Left edge, 0-1. */
  start: number;
  /** Width, 0-1, never below the pixel floor. */
  width: number;
  firstSeen: string;
  lastSeen: string;
  current: boolean;
}

export interface Lane {
  component: string;
  segments: LaneSegment[];
  /** Width of the leading "did not exist yet" region, 0 when the component was
   *  present at the first release. Deliberately not a segment: it must never
   *  be mistaken for a version, and it carries no version to show. */
  absentWidth: number;
}

/**
 * Raise every width to `floor`, taking the surplus proportionally from those
 * above it. Iterative, not single-pass: raising the small ones shrinks the
 * large ones, which can push a previously-fine segment below the floor.
 *
 * Why a floor at all: `git log --date=short` gives day resolution, and this
 * repo really does ship several times a day (four releases on 2026-08-14).
 * On a six-week axis those are ~0.6% wide each — sub-pixel — and would simply
 * vanish, so the strip would under-report exactly the burst activity it is
 * meant to show.
 *
 * The cost, which is accepted and documented on the page: once segments are
 * floored the lane is honest about ORDER and approximate about DURATION. The
 * date ticks below the strip are the ground truth.
 */
export function applyFloor(widths: number[], floor: number): number[] {
  if (widths.length === 0) return [];
  // Nothing to do, and the fully-saturated case: if even equal shares are
  // below the floor, equal shares are the best available answer.
  if (widths.length * floor >= 1) return widths.map(() => 1 / widths.length);

  const out = [...widths];
  const pinned = new Set<number>();
  for (;;) {
    const newly = out
      .map((w, i) => [w, i] as const)
      .filter(([w, i]) => !pinned.has(i) && w < floor)
      .map(([, i]) => i);
    if (newly.length === 0) return out;

    for (const i of newly) {
      out[i] = floor;
      pinned.add(i);
    }

    const budget = 1 - pinned.size * floor;
    const free = out.reduce((sum, w, i) => (pinned.has(i) ? sum : sum + w), 0);
    if (free <= 0) {
      const share = budget / (out.length - pinned.size || 1);
      out.forEach((_, i) => {
        if (!pinned.has(i)) out[i] = share;
      });
      return out;
    }
    out.forEach((w, i) => {
      if (!pinned.has(i)) out[i] = (w / free) * budget;
    });
  }
}

interface VersionsSlice {
  data: VersionHistory | null;
  loading: boolean;
  error: string | null;
  page: number;
  filter: VersionFilter;
  /** Measured by the component. The floor is a PIXEL rule, so the geometry
   *  cannot be computed without knowing how wide the strip actually is. A
   *  sane default keeps the store usable before the component has measured
   *  itself. */
  stripWidth: number;
}

/**
 * The component release timeline — what the Versions workspace draws.
 *
 * Read-only and loaded once. There is no event wiring and no refetch: the
 * underlying file changes only when someone cuts a release and re-runs
 * `scripts/dev/build_version_matrix.py`, which cannot happen while the page is
 * open in front of them.
 *
 * **The wire is oldest-first** (how the generator walks git); `releases()` is
 * the one place that reverses it, so the strip and the stream draw the same
 * newest-first order without a second convention to disagree.
 */
export const VersionsStore = signalStore(
  withState<VersionsSlice>({
    data: null,
    loading: false,
    error: null,
    page: 1,
    filter: null,
    stripWidth: 800,
  }),
  withComputed(({ data }) => ({
    empty: computed(() => data() === null),

    components: computed<string[]>(() => data()?.components ?? []),
    current: computed<Record<string, string>>(() => data()?.current ?? {}),
    live: computed<Record<string, string>>(() => data()?.live ?? {}),
    /** VERSION.json has moved past the frozen file — the page is behind,
     *  and says so rather than quietly showing an incomplete history. */
    stale: computed(() => data()?.stale ?? false),
    generatedAt: computed(() => data()?.generated_at ?? null),
    /** The server's own wording for what a release does and does not claim.
     *  Rendered verbatim; see `models.ts`. */
    basis: computed(() => data()?.basis ?? null),

    /** Newest first. THE one reversal — the wire is oldest-first because
     *  that is how the generator walks git, and two conventions that can
     *  disagree is one more than this needs. */
    releases: computed<Release[]>(() => [...(data()?.releases ?? [])].reverse()),
  })),
  withComputed(({ releases, filter }) => ({
    /** Releases matching the filter, before paging. An empty-string version
     *  matches nothing: `versions[c]` is `null` when the component did not
     *  exist, and absent must never look like a value. */
    matching: computed<Release[]>(() => {
      const active = filter();
      const all = releases();
      if (!active) return all;
      return all.filter((r) => r.versions[active.component] === active.version);
    }),
  })),
  withComputed(({ matching, page }) => ({
    visible: computed<Release[]>(() => {
      const start = (page() - 1) * PAGE_SIZE;
      return matching().slice(start, start + PAGE_SIZE);
    }),

    pageSpec: computed<PageSpec>(() => ({
      // The count BEFORE slicing. `visible().length` here would silently
      // show a single page however much history is behind it.
      total: matching().length,
      page: page(),
      perPage: PAGE_SIZE,
    })),
  })),
  withComputed(({ data, components, visible, stripWidth }) => ({
    /** Segments per component, on a TIME axis.
     *
     *  Time and not release index, because index would space every release
     *  equally and destroy the signal this strip exists to carry: bot sat at
     *  1.1.2 through ten consecutive ui releases, and that only shows up
     *  when width means duration. */
    lanes: computed<Lane[]>(() => {
      const ordered = [...(data()?.releases ?? [])]; // oldest first
      if (ordered.length === 0) return [];

      const t = (iso: string) => new Date(iso).getTime();
      const t0 = t(ordered[0].date);
      const tEnd = Math.max(t(ordered[ordered.length - 1].last_seen), t0 + 1);
      const span = tEnd - t0; // never 0 — see above
      const floor = 2 / Math.max(1, stripWidth());

      return components().map((component) => {
        // Collapse consecutive releases that leave this component alone: a
        // lane's segments are ITS changes, not every release.
        const runs: { version: string; from: number; to: number }[] = [];
        for (const r of ordered) {
          const version = r.versions[component];
          if (version === null || version === undefined) continue;
          const last = runs[runs.length - 1];
          if (last && last.version === version) last.to = t(r.last_seen);
          else runs.push({ version, from: t(r.date), to: t(r.last_seen) });
        }
        if (runs.length === 0) return { component, segments: [], absentWidth: 1 };

        runs[runs.length - 1].to = tEnd; // the live one runs to now
        const absentWidth = (runs[0].from - t0) / span;
        // Width uses the geometric boundary -- the NEXT run's start, or tEnd
        // for the last run -- rather than `to` (this run's own last_seen).
        // last_seen is typically the calendar day BEFORE the next run's
        // date, so using it for width leaves a one-day gap between every
        // pair of consecutive segments and the lane never sums to 1. `to`
        // itself is untouched: it still carries the true last-seen instant
        // for the segment's tooltip metadata below.
        const bounds = runs.map((run, i) => (i + 1 < runs.length ? runs[i + 1].from : tEnd));
        const raw = runs.map((run, i) => (bounds[i] - run.from) / span);
        const scale = 1 - absentWidth;
        const widths = applyFloor(
          raw.map((w) => w / (scale || 1)),
          floor / (scale || 1),
        ).map((w) => w * scale);

        let cursor = absentWidth;
        const segments = runs.map((run, i) => {
          const segment: LaneSegment = {
            version: run.version,
            start: cursor,
            width: widths[i],
            firstSeen: ordered.find((r) => t(r.date) === run.from)?.date ?? '',
            lastSeen: ordered.find((r) => t(r.last_seen) === run.to)?.last_seen ?? '',
            current: i === runs.length - 1,
          };
          cursor += widths[i];
          return segment;
        });
        return { component, segments, absentWidth };
      });
    }),

    /** Where the visible page sits on the full-history strip. This is the
     *  whole reason the strip can show all of history and still say where
     *  you are — the alternative was a zoom control nobody asked for. */
    bracket: computed<{ start: number; width: number }>(() => {
      const rows = visible();
      const ordered = [...(data()?.releases ?? [])];
      if (rows.length === 0 || ordered.length === 0) return { start: 0, width: 0 };

      const t = (iso: string) => new Date(iso).getTime();
      const t0 = t(ordered[0].date);
      const tEnd = Math.max(t(ordered[ordered.length - 1].last_seen), t0 + 1);
      const span = tEnd - t0;

      // `visible` is newest-first, so its last row is the oldest on screen.
      const from = t(rows[rows.length - 1].date);
      const to = t(rows[0].last_seen);
      const start = (from - t0) / span;
      return { start, width: Math.max((to - from) / span, 2 / Math.max(1, stripWidth())) };
    }),
  })),
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

    setPage(n: number): void {
      patchState(store, { page: Math.max(1, n) });
    },

    /** Measured by the component. The floor is a PIXEL rule, so the geometry
     *  cannot be computed without knowing how wide the strip actually is. */
    setStripWidth(px: number): void {
      patchState(store, { stripWidth: Math.max(1, Math.round(px)) });
    },

    /** Selecting the same chip twice clears — the chip IS the toggle, which
     *  is why there is no separate "clear filter" control. Always returns to
     *  page 1: staying on page 3 of a filter that now has one page shows an
     *  empty list that looks like "no results". */
    toggleFilter(component: string, version: string): void {
      const active = store.filter();
      const same = active?.component === component && active?.version === version;
      patchState(store, {
        filter: same ? null : { component, version },
        page: 1,
      });
    },
  })),
  withHooks({
    onInit(store) {
      store.load();
    },
  }),
);
