import { computed, effect, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { Health } from '../api/models';

/** What the shell's indicator shows. `dead` is not an EventStream state:
 *  it means the fallback itself is failing, i.e. the admin is unreachable
 *  by any route. */
export type ConnectionState = 'connecting' | 'live' | 'degraded' | 'dead';

interface ConnectionStateSlice {
  botAlive: boolean | null;
  botLastSeen: string | null;
  /** Null when the bot has never completed a tick -- distinct from false. */
  botHealthy: boolean | null;
  /** True when the most recent poll for bot liveness failed. */
  unreachable: boolean;
  /**
   * SR58 — `GET /health`: the version tag, its build time, and whether the
   * US market is open.
   *
   * Read HERE rather than by a new store because it answers the same
   * question the two facts above do -- "is what I am looking at real" -- and
   * the shell already refetches this store on the `bot` event. `market_active`
   * in particular is why "these prices have not moved" is not always a
   * failure: outside session hours it is the correct behaviour.
   *
   * Null until the first answer. `ApiClient.health()` had existed with no
   * caller since NG4.
   */
  health: Health | null;
}

/**
 * "Am I hearing about changes, and is the bot alive?" — for the shell.
 *
 * Two facts that look unrelated and are not: both answer "is what I am
 * looking at real", and the shell shows them together because a user
 * noticing stale numbers needs to know whether the browser stopped
 * listening or the bot stopped writing. They have different fixes.
 */
export const ConnectionStore = signalStore(
  { providedIn: 'root' },
  withState<ConnectionStateSlice>({
    botAlive: null,
    botLastSeen: null,
    botHealthy: null,
    unreachable: false,
    health: null,
  }),
  withComputed((store, events = inject(EventStream)) => ({
    state: computed<ConnectionState>(() =>
      // Only "degraded and the fallback is also failing" is dead. A failed
      // poll while the stream is live is a blip worth ignoring: the next
      // event will correct it, and flashing "offline" on one bad request
      // trains people to distrust the indicator.
      store.unreachable() && events.state() === 'degraded' ? 'dead' : events.state(),
    ),
    lastSeq: events.lastSeq,
  })),
  withComputed(({ health }) => ({
    /** The `ui`/`bot` pair for the shell footer, or null before the first
     *  answer -- rendering "0.0.0" while the request is in flight would look
     *  like a real version rather than an absent one. */
    versions: computed(() => health()?.versions ?? null),
    /** When VERSION.json was last written, which doubles as when this image
     *  last actually changed. */
    lastUpdated: computed(() => health()?.versions.last_updated ?? null),
    /**
     * Three-valued deliberately. `null` means "not asked yet", which is a
     * different statement from "the market is closed" -- and an indicator
     * that says CLOSED before it knows is worse than one that says nothing.
     */
    marketActive: computed<boolean | null>(() => health()?.market_active ?? null),
    /**
     * The account's currency symbol, for every card that renders a money
     * amount.
     *
     * Falls back to `€` rather than to `null`, unlike the three-valued
     * signals above, because a metric card cannot render "currency unknown":
     * it would have to drop the unit entirely and show a bare number, which
     * is the ambiguity the unit exists to remove. `€` is what
     * `CURRENCY_SYMBOL` defaults to on the server, so the fallback and the
     * default agree -- the brief window before the first `/health` lands
     * shows the same symbol it will settle on.
     */
    currency: computed(() => health()?.currency ?? '€'),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    refresh(): void {
      // Its own request and its own silence on failure: a failed health read
      // must not flip the connection indicator, which is answering a
      // different question and has its own signal for it.
      api.health().subscribe({
        next: (health) => patchState(store, { health }),
        error: () => undefined,
      });

      api.scanStatus().subscribe({
        next: (scan) =>
          patchState(store, {
            botAlive: scan.bot_alive,
            botHealthy: scan.bot_healthy,
            botLastSeen: scan.bot_last_seen,
            unreachable: false,
          }),
        error: () => patchState(store, { unreachable: true }),
      });
    },
  })),
  withHooks({
    onInit(store, events = inject(EventStream)) {
      events.connect();

      // The `bot` event is the heartbeat file moving. Reading the counter
      // inside the effect is what subscribes to it; the effect's first run
      // is also the initial load, so there is no separate bootstrap call
      // that could drift from the refetch path.
      const bot = events.changes('bot');
      effect(() => {
        bot();
        store.refresh();
      });
    },
  }),
);
