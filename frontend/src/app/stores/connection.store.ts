import { DestroyRef, computed, effect, inject, untracked } from '@angular/core';
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
import { Health, ScanEventProgress, ScanProgressRecord } from '../api/models';

/** What the shell's indicator shows. `dead` is not an EventStream state:
 *  it means the fallback itself is failing, i.e. the admin is unreachable
 *  by any route. */
export type ConnectionState = 'connecting' | 'live' | 'degraded' | 'dead';

/** v206: a `scan` tick with no payload (older server, failed broker read,
 *  degraded mode) fetches `/system/scan` at most once per this window. */
export const SCAN_FALLBACK_MIN_INTERVAL_MS = 5000;

/** v206: `/health` is read at boot, on `bot`, and on this timer -- never on
 *  `scan`, which fires about once a second while a scan runs. */
export const HEALTH_INTERVAL_MS = 300_000;

/** The 5-minute `/health` timer: skipped while the tab is hidden, plus one
 *  catch-up when it becomes visible and the last fetch is older than that. */
function startHealthTimer(
  store: { refreshHealth(): void; _healthDue(): boolean },
  destroyRef: DestroyRef,
): void {
  if (typeof document === 'undefined') return;
  const timer = setInterval(() => {
    if (!document.hidden) store.refreshHealth();
  }, HEALTH_INTERVAL_MS);
  const onVisibility = () => {
    if (!document.hidden && store._healthDue()) store.refreshHealth();
  };
  document.addEventListener('visibilitychange', onVisibility);
  destroyRef.onDestroy(() => {
    clearInterval(timer);
    document.removeEventListener('visibilitychange', onVisibility);
  });
}

interface ConnectionStateSlice {
  botAlive: boolean | null;
  botLastSeen: string | null;
  /**
   * When the bot last completed a tick successfully -- v195's top-bar
   * freshness chip. Already in the `/system/scan` payload this store reads;
   * kept now because Scan health leaves the Risk page (spec §5.1) and the
   * chip is what keeps it in view everywhere. Null until the bot has ever
   * completed one, distinct from an old time.
   */
  botLastSuccess: string | null;
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
   * the shell already refetches this store on the `bot` event (and, since v206, on a 5-minute timer; never on `scan`). `market_active`
   * in particular is why "these prices have not moved" is not always a
   * failure: outside session hours it is the correct behaviour.
   *
   * Null until the first answer. `ApiClient.health()` had existed with no
   * caller since NG4.
   */
  health: Health | null;
  /**
   * The scan progress strip's two facts, read from the same `/system/scan`
   * payload the bot-liveness fields above come from.
   *
   * They live in THIS store rather than `system.store` because the strip is
   * shell chrome: `system.store` only exists while the System workspace is
   * open, so a bar wired to it would appear on one page out of a dozen.
   *
   * `scanProgress` is null whenever the bot is publishing nothing -- which
   * the strip must render as "no bar", never as 0%.
   */
  scanRunning: boolean;
  scanProgress: ScanProgressRecord | null;
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
    botLastSuccess: null,
    botHealthy: null,
    unreachable: false,
    health: null,
    scanRunning: false,
    scanProgress: null,
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
  withMethods((store, api = inject(ApiClient), events = inject(EventStream)) => {
    let seenBot: number | null = null;
    let lastHealthAt = Number.NEGATIVE_INFINITY;

    // Its own request and its own silence on failure: a failed health read
    // must not flip the connection indicator, which is answering a
    // different question and has its own signal for it.
    const refreshHealth = (): void => {
      lastHealthAt = Date.now();
      api.health().subscribe({
        next: (health) => patchState(store, { health }),
        error: () => undefined,
      });
    };

    const refreshScan = (): void => {
      api.scanStatus().subscribe({
        next: (scan) =>
          patchState(store, {
            botAlive: scan.bot_alive,
            botHealthy: scan.bot_healthy,
            botLastSeen: scan.bot_last_seen,
            botLastSuccess: scan.bot_last_success,
            scanRunning: scan.running,
            scanProgress: scan.progress,
            unreachable: false,
          }),
        // The strip is deliberately left as it was: one failed poll while the
        // stream is live is a blip the next event corrects, and blanking the
        // bar on it would make it flicker through every scan.
        error: () => patchState(store, { unreachable: true }),
      });
    };

    const refresh = (): void => {
      refreshHealth();
      refreshScan();
    };

    return {
      refresh,
      refreshHealth,
      _healthDue: (): boolean => Date.now() - lastHealthAt > HEALTH_INTERVAL_MS,
      /** One run of the event effect. A moved `bot` counter (boot, a
       *  heartbeat, a resync) refreshes everything; otherwise it was a
       *  throttled `scan` tick, which fetches only when no payload came. */
      _onEventTick(botTick: number): void {
        if (botTick !== seenBot) {
          seenBot = botTick;
          refresh();
          return;
        }
        if (events.payload('scan')() === null) refreshScan();
      },
      /** The strip's two facts straight from a `scan` frame (v206 P1-c). */
      _patchProgress(payload: ScanEventProgress | null): void {
        if (payload) patchState(store, { scanRunning: payload.running, scanProgress: payload.progress });
      },
    };
  }),
  withHooks({
    onInit(store, events = inject(EventStream), destroyRef = inject(DestroyRef)) {
      events.connect();

      // `bot` is the heartbeat moving; the throttled `scan` view is the
      // fallback for a `scan` frame that carried no payload. They share ONE
      // effect, as before v206: its first run is the boot load, and a resync
      // (which bumps both at once) fetches `/system/scan` once, not twice.
      const bot = events.changes('bot');
      const scanTick = events.changes('scan', { minIntervalMs: SCAN_FALLBACK_MIN_INTERVAL_MS });
      effect(() => {
        const botTick = bot();
        scanTick();
        untracked(() => store._onEventTick(botTick));
      });

      // v206: the progress strip moves with every `scan` frame, from the
      // frame itself -- no request. This is what used to cost ~2 requests a
      // second per open tab.
      const payload = events.payload('scan');
      effect(() => {
        const value = payload();
        untracked(() => store._patchProgress(value));
      });

      startHealthTimer(store, destroyRef);
    },
  }),
);
