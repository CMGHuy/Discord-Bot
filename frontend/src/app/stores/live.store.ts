import { computed, effect, inject, untracked } from '@angular/core';
import { patchState, signalStore, withComputed, withHooks, withMethods, withState } from '@ngrx/signals';
import { Subscription } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { LiveEvent, LiveSnapshot } from '../api/models';

/**
 * The events that can move a dock figure (v206 P1-d: `scan` is not one).
 *
 * `scan` fires about once a second while a scan runs and used to cost a
 * `/live` request every 2 s per tab. Nothing `/live` returns is written by
 * the scan progress itself: what a scan adds that the dock shows is new
 * plans, and the `plans` table raises `trades`. Every field, its source
 * and the event that announces it:
 *
 * | `/live` field                                  | Source (table / input)                     | Trigger                        |
 * |------------------------------------------------|--------------------------------------------|--------------------------------|
 * | heat.open_pct, open_amount, utilisation_pct,   | open trades and resting plans              | `trades` (trades, plans)       |
 * |   headroom_pct, headroom_amount                |   (`open_heat_state`)                      |                                |
 * | heat.balance                                   | account config                             | `account`; a close moves it    |
 * |                                                |                                            |   with `trades`; no scan write |
 * | heat.cap_pct, cap_amount                       | the heat-cap setting                       | `settings`; no scan write      |
 * | heat.includes_resting, availability, reason    | the same read                              | as above                       |
 * | awaiting.count, next_expiry                    | PENDING plans                              | `trades` (plans)               |
 * | killswitch.engaged, since, detail              | killswitch row                             | `risk` (killswitch)            |
 * | events[]: plan_alerted, paper_filled, tp1_hit  | plans                                      | `trades` (plans)               |
 * | events[]: trade_closed                         | trades                                     | `trades` (trades)              |
 * | events[]: killswitch                           | killswitch                                 | `risk` (killswitch)            |
 * | events_meta.availability, missing              | the same reads as events[]                 | as events[]                    |
 * | every `as_of`                                  | the request's clock                        | none (any refresh)             |
 *
 * `bot` (the heartbeat) moves no field itself; it stays from v203 as the
 * once-per-heartbeat catch-up that keeps every `as_of` current. `account` and
 * `settings` are not listed because neither changes during a scan and
 * neither was listed before v206. A field that starts changing during a scan
 * through another table gets that table's own event here -- never `scan`.
 */
export const LIVE_REFRESH_EVENTS = ['trades', 'bot', 'risk'] as const;

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
 * debounce: a busy book raises `trades` in bursts, and a timer that
 * restarted on each one would never fire.
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
