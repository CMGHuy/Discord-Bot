import { Injectable, Signal, signal } from '@angular/core';

/** The ten event types the server can raise, plus the two it synthesises.
 *  Mirrors spec v12's taxonomy table -- one type per *concern*, so several
 *  files raise the same event and the client never learns the storage
 *  layout. */
export type EventName =
  | 'trades'
  | 'account'
  | 'analytics'
  | 'journal'
  | 'scan'
  | 'bot'
  | 'risk'
  | 'watchlist'
  | 'jobs'
  | 'settings';

export const EVENT_NAMES: readonly EventName[] = [
  'trades', 'account', 'analytics', 'journal', 'scan',
  'bot', 'risk', 'watchlist', 'jobs', 'settings',
] as const;

export type StreamState = 'connecting' | 'live' | 'degraded';

/** Reconnects inside {@link FAILURE_WINDOW_MS} before giving up on the
 *  stream. Spec v13 Decision 4: three in a minute. */
const FAILURE_LIMIT = 3;
const FAILURE_WINDOW_MS = 60_000;

/** The interval the old Jinja UI polled at, and what this falls back to. */
export const POLL_INTERVAL_MS = 5_000;

/** How often a degraded client tries the stream again. */
const RECOVERY_INTERVAL_MS = 30_000;

/**
 * One `EventSource` for the application, exposed as signals.
 *
 * **This service knows nothing about stores.** It publishes a counter per
 * event type; a store watches the counter it cares about. The inverse --
 * the stream calling into stores -- would make every new workspace a change
 * to this file, and would put the list of stores inside the transport.
 *
 * **The reaction to an event is always a refetch, never a patch.** The
 * events are thin by design (`{seq, at}`, no payload), so there is nothing
 * here to merge into anything. That is the property that stops a store
 * becoming a second, slowly diverging copy of the server's data.
 *
 * **Degraded mode is invisible to subscribers.** When the stream fails, the
 * same counters get bumped by a 5-second timer instead. A store never asks
 * which mode it is in, so there is no second code path to keep correct --
 * and the UI stays correct with the stream entirely dead, which spec v12
 * names as the acceptance criterion.
 */
@Injectable({ providedIn: 'root' })
export class EventStream {
  readonly state = signal<StreamState>('connecting');
  /** The `id:` of the last event received. Diagnostics only -- recovery is
   *  a resync, never a replay, so nothing acts on the number. */
  readonly lastSeq = signal<number | null>(null);

  private source: EventSource | null = null;
  private readonly counters = new Map<EventName, ReturnType<typeof signal<number>>>();
  /** Timestamps of recent connection failures, inside the rolling window. */
  private failures: number[] = [];
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private recoveryTimer: ReturnType<typeof setInterval> | null = null;

  /**
   * A counter that increases every time `name` is raised.
   *
   * Counters, not booleans or the event object: a store reacts with an
   * effect, and an effect only re-runs when the value it read changes. A
   * boolean set true twice is one change; two events must be two.
   */
  changes(name: EventName): Signal<number> {
    return this.counterFor(name).asReadonly();
  }

  connect(): void {
    if (this.source || typeof EventSource === 'undefined') return;

    const source = new EventSource('/api/v1/events', { withCredentials: true });
    this.source = source;

    for (const name of EVENT_NAMES) {
      source.addEventListener(name, (event) => {
        this.markLive(event as MessageEvent);
        this.bump(name);
      });
    }

    // The stream opens with one of these, and sends one on every reconnect
    // the browser makes on its own. "Refetch everything on screen": the
    // client has been away for an unknown length of time, and because the
    // events are thin, one refetch fixes any amount of staleness.
    source.addEventListener('resync', (event) => {
      this.markLive(event as MessageEvent);
      this.bumpAll();
    });

    // Nothing to do -- its entire purpose is to stop an idle connection
    // being dropped by a proxy. Registered anyway so it is visibly handled
    // rather than looking like an event someone forgot.
    source.addEventListener('ping', (event) => this.markLive(event as MessageEvent));

    source.onerror = () => this.onFailure();
  }

  disconnect(): void {
    this.source?.close();
    this.source = null;
    this.stopPolling();
    if (this.recoveryTimer !== null) {
      clearInterval(this.recoveryTimer);
      this.recoveryTimer = null;
    }
  }

  /* -- internals ------------------------------------------------------- */

  private counterFor(name: EventName) {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  private bump(name: EventName): void {
    this.counterFor(name).update((n) => n + 1);
  }

  private bumpAll(): void {
    for (const name of EVENT_NAMES) this.bump(name);
  }

  private markLive(event: MessageEvent): void {
    // A message arriving is proof the connection works, so the failure
    // window resets here rather than on `onopen`: EventSource reports open
    // before the server has necessarily said anything.
    this.failures = [];
    this.state.set('live');
    this.stopPolling();
    try {
      const data = JSON.parse(event.data) as { seq?: number };
      if (typeof data.seq === 'number') this.lastSeq.set(data.seq);
    } catch {
      // A frame we cannot parse is not worth failing over: the event's
      // meaning is its NAME, which we already have.
    }
  }

  private onFailure(): void {
    const now = Date.now();
    this.failures = this.failures.filter((at) => now - at < FAILURE_WINDOW_MS);
    this.failures.push(now);

    if (this.failures.length >= FAILURE_LIMIT) {
      this.degrade();
    }
  }

  /**
   * Give up on the stream and poll instead.
   *
   * The EventSource is closed rather than left to keep retrying. Its
   * built-in retry is unbounded, and the two failures worth naming here are
   * both permanent: a 401 (retry forever, never succeed) and the server's
   * 8-connection cap (retry forever, and be the reason it is full).
   */
  private degrade(): void {
    this.state.set('degraded');
    this.source?.close();
    this.source = null;
    this.startPolling();
    this.startRecovery();
  }

  private startPolling(): void {
    if (this.pollTimer !== null) return;
    this.pollTimer = setInterval(() => this.bumpAll(), POLL_INTERVAL_MS);
  }

  private stopPolling(): void {
    if (this.pollTimer === null) return;
    clearInterval(this.pollTimer);
    this.pollTimer = null;
  }

  /**
   * Keep trying the stream while degraded.
   *
   * Without this, one bad minute -- an admin restart, a laptop lid --
   * leaves the tab polling until someone reloads it, and the indicator
   * telling them so is easy to stop noticing. The failure window is cleared
   * first so a recovery attempt starts from a clean slate rather than
   * immediately re-tripping the limit.
   */
  private startRecovery(): void {
    if (this.recoveryTimer !== null) return;
    this.recoveryTimer = setInterval(() => {
      if (this.source) return;
      this.failures = [];
      this.connect();
    }, RECOVERY_INTERVAL_MS);
  }
}
