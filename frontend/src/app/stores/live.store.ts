import { computed, effect, inject, untracked } from '@angular/core';
import { patchState, signalStore, withComputed, withHooks, withMethods, withState } from '@ngrx/signals';
import { Subscription } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { LiveEvent, LiveSnapshot } from '../api/models';

/** The events that can move a dock figure: a trade or plan row, a scan, the
 *  bot heartbeat and the killswitch (which raises `risk`). */
export const LIVE_REFRESH_EVENTS = ['trades', 'scan', 'bot', 'risk'] as const;

/** At most one `/live` request per window (spec v202 §4). */
export const LIVE_REFRESH_DEBOUNCE_MS = 2000;

const NO_EVENTS: readonly LiveEvent[] = [];

interface LiveSlice {
  snapshot: LiveSnapshot | null;
  /** True until the first answer, and while a request is in flight. */
  loading: boolean;
  /** The last request failed. The last good snapshot is kept: each section
   *  carries its own `as_of`, so its age shows the data getting old. */
  failed: boolean;
}

/**
 * The Live dock data -- v203 (spec v202 §4 "Data source"). Root-scoped,
 * read only by the shell dock, edge tab and strip. It never touches
 * `RiskStore` or `/risk`; heat comes only from `/live`.
 *
 * Refresh: one load on init, then one request LIVE_REFRESH_DEBOUNCE_MS after
 * the FIRST event of a burst. It is a fixed window, not a resetting
 * debounce: a running scan raises `scan` about once a second, and a timer
 * that restarted on each one would never fire.
 */
export const LiveStore = signalStore(
  { providedIn: 'root' },
  withState<LiveSlice>({ snapshot: null, loading: true, failed: false }),
  withComputed(({ snapshot }) => ({
    heat: computed(() => snapshot()?.heat ?? null),
    awaiting: computed(() => snapshot()?.awaiting ?? null),
    killswitch: computed(() => snapshot()?.killswitch ?? null),
    events: computed<readonly LiveEvent[]>(() => snapshot()?.events ?? NO_EVENTS),
    eventsMeta: computed(() => snapshot()?.events_meta ?? null),
  })),
  withMethods((store, api = inject(ApiClient)) => {
    let inflight: Subscription | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const cancelTimer = (): void => {
      if (timer !== null) clearTimeout(timer);
      timer = null;
    };

    const load = (): void => {
      cancelTimer();
      inflight?.unsubscribe();
      patchState(store, { loading: true });
      inflight = api.live().subscribe({
        next: (snapshot) => patchState(store, { snapshot, loading: false, failed: false }),
        error: () => patchState(store, { loading: false, failed: true }),
      });
    };

    return {
      load,
      /** The panel-error retry: at once, dropping any pending refresh. */
      retry: load,
      /** One request at the end of the current window; later events join it. */
      _scheduleRefresh(): void {
        if (timer === null) timer = setTimeout(load, LIVE_REFRESH_DEBOUNCE_MS);
      },
      _stop(): void {
        cancelTimer();
        inflight?.unsubscribe();
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      const counters = LIVE_REFRESH_EVENTS.map((name) => events.changes(name));
      let first = true;
      // Reading the counters subscribes; the first run is the initial load.
      effect(() => {
        counters.forEach((counter) => counter());
        untracked(() => {
          if (first) store.load();
          else store._scheduleRefresh();
          first = false;
        });
      });
    },
    onDestroy(store) {
      store._stop();
    },
  }),
);
