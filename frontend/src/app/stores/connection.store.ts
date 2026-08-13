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

/** What the shell's indicator shows. `dead` is not an EventStream state:
 *  it means the fallback itself is failing, i.e. the admin is unreachable
 *  by any route. */
export type ConnectionState = 'connecting' | 'live' | 'degraded' | 'dead';

interface ConnectionStateSlice {
  botAlive: boolean | null;
  botLastSeen: string | null;
  /** True when the most recent poll for bot liveness failed. */
  unreachable: boolean;
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
    unreachable: false,
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
  withMethods((store, api = inject(ApiClient)) => ({
    refresh(): void {
      api.scanStatus().subscribe({
        next: (scan) =>
          patchState(store, {
            botAlive: scan.bot_alive,
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
