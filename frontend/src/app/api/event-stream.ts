import { Injectable, Signal, WritableSignal, signal } from '@angular/core';
import { Subject } from 'rxjs';

import { ScanEventProgress } from './models';
import { parseScanEventProgress } from './scan-event-progress';

/** The event types the server can raise, plus the two it synthesises.
 *  Mirrors spec v12's taxonomy table -- one type per *concern*, so several
 *  files raise the same event and the client never learns the storage
 *  layout. `feed` (v227) is the simple-channel post log the voice notifier
 *  reads. */
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
  | 'settings'
  | 'market'
  | 'feed';

export const EVENT_NAMES: readonly EventName[] = [
  'trades', 'account', 'analytics', 'journal', 'scan',
  'bot', 'risk', 'watchlist', 'jobs', 'settings', 'market', 'feed',
] as const;

export type StreamState = 'connecting' | 'live' | 'degraded';

/** Reconnects inside {@link FAILURE_WINDOW_MS} before giving up on the
 *  stream. Spec v13 Decision 4: three in a minute. */
const FAILURE_LIMIT = 3;
const FAILURE_WINDOW_MS = 60_000;

/** The interval the old Jinja UI polled at, and what this falls back to. */
export const POLL_INTERVAL_MS = 5_000;

/** How often a store that hits market data may react to `scan` (v132).
 *  `scan` fires about once a second while a scan runs (every
 *  `scan_progress` write raises it), and each reaction used to cost the
 *  server a Yahoo download -- which is how the admin ran out of sockets on
 *  2026-10-05. */
export const MARKET_DATA_MIN_INTERVAL_MS = 30_000;

/** One rate-limited view of an event counter, shared by every subscriber
 *  asking for the same event at the same interval. */
interface Throttle {
  readonly name: EventName;
  readonly out: WritableSignal<number>;
  readonly interval: number;
  last: number;
  timer: ReturnType<typeof setTimeout> | null;
}

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
 * **The reaction to an event is a refetch, never a patch -- except `scan`.**
 * The events are thin by design (`{seq, at}`, no payload), so there is
 * nothing here to merge into anything. That is the property that stops a
 * store becoming a second, slowly diverging copy of the server's data.
 *
 * `scan` is the one exception (v206 P1-c). It fires about once a second
 * while a scan runs, and refetching `/system/scan` on each one, from every
 * open tab, was most of the admin's load. So a `scan` frame carries the two
 * fields the progress strip reads, and {@link payload} exposes them,
 * validated, as a signal separate from the counter. A thin or malformed
 * frame sets it to null, and so does every path that refetches everything
 * (resync, the polling fallback, a reconnect), so a store never patches
 * from a payload older than its last refetch.
 *
 * `market` is answered by a catch-up fetch (`/market/updates`), still never a
 * patch from the event itself.
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
  private readonly raisedSubject = new Subject<EventName>();
  readonly raised = this.raisedSubject.asObservable();
  private readonly counters = new Map<EventName, ReturnType<typeof signal<number>>>();
  private readonly throttles = new Map<string, Throttle>();
  /** v206: the last validated `scan` payload; null whenever the store must fetch. */
  private readonly scanPayload = signal<ScanEventProgress | null>(null);
  private readonly scanPayloadView = this.scanPayload.asReadonly();
  private visibilityBound = false;
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
  changes(name: EventName, options?: { minIntervalMs: number }): Signal<number> {
    if (!options) return this.counterFor(name).asReadonly();
    // Throttled view (v132): the first bump passes at once, the rest of a
    // burst collapses into one trailing bump. The signal itself is returned
    // (not `asReadonly()`, a new object per call) so subscribers share it;
    // the return type is what keeps callers read-only.
    const key = `${name}:${options.minIntervalMs}`;
    let throttle = this.throttles.get(key);
    if (!throttle) {
      throttle = { name, out: signal(0), interval: options.minIntervalMs, last: -Infinity, timer: null };
      this.throttles.set(key, throttle);
    }
    return throttle.out;
  }

  /**
   * The last validated payload of a `scan` frame, or null (v206 P1-c).
   *
   * Unthrottled: it moves on every `scan` frame, before the counters do. A
   * thin frame (the server's read failed, or an older server) and anything
   * malformed read as null -- the store's cue to fetch `/system/scan`
   * through its throttled fallback instead.
   */
  payload(name: 'scan'): Signal<ScanEventProgress | null>;
  payload(): Signal<ScanEventProgress | null> {
    return this.scanPayloadView;
  }

  connect(): void {
    if (this.source || typeof EventSource === 'undefined') return;

    const source = new EventSource('/api/v1/events', { withCredentials: true });
    this.source = source;
    // A reconnect starts from nothing: the resync that follows refetches.
    this.scanPayload.set(null);

    for (const name of EVENT_NAMES) {
      source.addEventListener(name, (event) => this.receive(name, event as MessageEvent));
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
    for (const throttle of this.throttles.values()) {
      if (throttle.timer !== null) clearTimeout(throttle.timer);
      throttle.timer = null;
    }
    if (this.recoveryTimer !== null) {
      clearInterval(this.recoveryTimer);
      this.recoveryTimer = null;
    }
  }

  /* -- internals ------------------------------------------------------- */

  private receive(name: EventName, event: MessageEvent): void {
    const frame = this.markLive(event);
    // Set before the bump: a reaction to the counter reads the payload that
    // arrived with it, never the one before.
    if (name === 'scan') this.scanPayload.set(parseScanEventProgress(frame));
    this.bump(name);
  }

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
    this.raisedSubject.next(name);
    for (const throttle of this.throttles.values()) {
      if (throttle.name === name) this.pass(throttle);
    }
  }

  /** Leading edge at once, everything else inside the interval as one
   *  trailing bump -- so the last event of a burst is never lost. */
  private pass(throttle: Throttle): void {
    const wait = throttle.last + throttle.interval - Date.now();
    if (wait <= 0) {
      if (throttle.timer !== null) clearTimeout(throttle.timer);
      this.release(throttle);
    } else if (throttle.timer === null) {
      throttle.timer = setTimeout(() => this.release(throttle), wait);
    }
  }

  private release(throttle: Throttle): void {
    throttle.timer = null;
    if (this.pollTimer !== null && typeof document !== 'undefined' && document.hidden) return;
    throttle.last = Date.now();
    throttle.out.update((n) => n + 1);
  }

  private bumpAll(): void {
    // Everything is refetched, so no store may patch from an older payload.
    this.scanPayload.set(null);
    for (const name of EVENT_NAMES) this.bump(name);
  }

  private markLive(event: MessageEvent): unknown {
    // A message arriving is proof the connection works, so the failure
    // window resets here rather than on `onopen`: EventSource reports open
    // before the server has necessarily said anything.
    this.failures = [];
    this.state.set('live');
    this.stopPolling();
    try {
      const data = JSON.parse(event.data) as { seq?: number } | null;
      if (typeof data?.seq === 'number') this.lastSeq.set(data.seq);
      return data;
    } catch {
      // A frame we cannot parse is not worth failing over: the event's
      // meaning is its NAME, which we already have.
      return null;
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
    this.scanPayload.set(null);
    this.source?.close();
    this.source = null;
    this.startPolling();
    this.startRecovery();
  }

  private startPolling(): void {
    if (this.pollTimer !== null) return;
    this.pollTimer = setInterval(() => {
      // A tab nobody is looking at must not cost the server a refetch (v132).
      if (typeof document !== 'undefined' && document.hidden) return;
      this.bumpAll();
    }, POLL_INTERVAL_MS);
    if (!this.visibilityBound && typeof document !== 'undefined') {
      this.visibilityBound = true;
      // One catch-up refetch when the tab is looked at again.
      document.addEventListener('visibilitychange', () => {
        if (!document.hidden && this.pollTimer !== null) this.bumpAll();
      });
    }
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
