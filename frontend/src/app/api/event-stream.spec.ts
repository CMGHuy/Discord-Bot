import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EVENT_NAMES, EventStream, POLL_INTERVAL_MS } from './event-stream';

/* NG31 — the event stream.
 *
 * jsdom has no EventSource, which is convenient: the fake below is the
 * whole browser side of the contract, so a test can raise an event, fail a
 * connection, or fail three, without a server.
 */

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly listeners = new Map<string, ((event: MessageEvent) => void)[]>();
  onerror: (() => void) | null = null;
  closed = false;

  constructor(
    readonly url: string,
    readonly init?: EventSourceInit,
  ) {
    FakeEventSource.instances.push(this);
  }

  addEventListener(name: string, handler: (event: MessageEvent) => void): void {
    const existing = this.listeners.get(name) ?? [];
    this.listeners.set(name, [...existing, handler]);
  }

  close(): void {
    this.closed = true;
  }

  /** Deliver a frame the way the server sends it: named event, thin body. */
  emit(name: string, seq = 1): void {
    const event = new MessageEvent(name, {
      data: JSON.stringify({ seq, at: '2026-08-12T00:00:00+00:00' }),
    });
    for (const handler of this.listeners.get(name) ?? []) handler(event);
  }

  fail(): void {
    this.onerror?.();
  }

  static latest(): FakeEventSource {
    return FakeEventSource.instances[FakeEventSource.instances.length - 1];
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }
}

describe('EventStream', () => {
  let stream: EventStream;

  beforeEach(() => {
    vi.useFakeTimers();
    FakeEventSource.reset();
    vi.stubGlobal('EventSource', FakeEventSource);

    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection()],
    });
    stream = TestBed.inject(EventStream);
    stream.connect();
  });

  afterEach(() => {
    stream.disconnect();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  /* -- connecting ------------------------------------------------------ */

  it('opens one credentialed connection to the events endpoint', () => {
    expect(FakeEventSource.instances).toHaveLength(1);
    expect(FakeEventSource.latest().url).toBe('/api/v1/events');
    // EventSource cannot set headers, so the cookie is the only way it can
    // authenticate at all.
    expect(FakeEventSource.latest().init?.withCredentials).toBe(true);
  });

  it('does not open a second connection', () => {
    // One stream per app: the server caps connections at 8, and a second
    // one here would spend that budget on a single tab.
    stream.connect();
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it('starts in connecting, not live', () => {
    // Claiming to be live before the server has said anything is exactly
    // the "looks live and is not" failure the indicator exists to prevent.
    expect(stream.state()).toBe('connecting');
  });

  /* -- events ---------------------------------------------------------- */

  it('emits every raised event name alongside its counter update', () => {
    const raised: string[] = [];
    stream.raised.subscribe((name) => raised.push(name));
    FakeEventSource.latest().emit('trades');
    expect(raised).toEqual(['trades']);
  });
  it('bumps the counter for the event that arrived', () => {
    const trades = stream.changes('trades');
    const account = stream.changes('account');

    FakeEventSource.latest().emit('trades');

    expect(trades()).toBe(1);
    expect(account()).toBe(0);
  });

  it('counts repeats, so a second event is a second refetch', () => {
    // A boolean would be one change here, and the second event would be
    // silently dropped by any effect watching it.
    const trades = stream.changes('trades');

    FakeEventSource.latest().emit('trades');
    FakeEventSource.latest().emit('trades');

    expect(trades()).toBe(2);
  });

  it('goes live on the first frame', () => {
    FakeEventSource.latest().emit('resync');
    expect(stream.state()).toBe('live');
  });

  it('bumps every counter on a resync', () => {
    // "Refetch everything on screen" -- the client has been away for an
    // unknown time, and thin events mean one refetch fixes any staleness.
    const counters = EVENT_NAMES.map((name) => stream.changes(name));

    FakeEventSource.latest().emit('resync');

    expect(counters.every((c) => c() === 1)).toBe(true);
  });

  it('records the last seq', () => {
    FakeEventSource.latest().emit('trades', 4812);
    expect(stream.lastSeq()).toBe(4812);
  });

  it('survives a frame it cannot parse', () => {
    // The event's meaning is its NAME; the body is a bonus.
    const trades = stream.changes('trades');
    const handlers = FakeEventSource.latest().listeners.get('trades') ?? [];
    handlers[0](new MessageEvent('trades', { data: 'not json' }));

    expect(trades()).toBe(1);
    expect(stream.state()).toBe('live');
  });

  it('does not treat a ping as a change', () => {
    // Its only job is stopping a proxy dropping an idle connection.
    const counters = EVENT_NAMES.map((name) => stream.changes(name));

    FakeEventSource.latest().emit('ping');

    expect(stream.state()).toBe('live');
    expect(counters.every((c) => c() === 0)).toBe(true);
  });

  /* -- degrading ------------------------------------------------------- */

  it('tolerates two failures in a minute', () => {
    // EventSource reconnects on its own; an occasional drop is normal and
    // must not cost the stream.
    FakeEventSource.latest().fail();
    FakeEventSource.latest().fail();

    expect(stream.state()).toBe('connecting');
    expect(FakeEventSource.latest().closed).toBe(false);
  });

  it('degrades on the third failure in a minute', () => {
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();

    expect(stream.state()).toBe('degraded');
    // Closed, not left retrying: its retry is unbounded, and the two
    // failures worth naming -- a 401 and the server's connection cap --
    // are both permanent, with the second made worse by retrying.
    expect(source.closed).toBe(true);
  });

  it('does not degrade on failures spread beyond the window', () => {
    FakeEventSource.latest().fail();
    vi.advanceTimersByTime(61_000);
    FakeEventSource.latest().fail();
    vi.advanceTimersByTime(61_000);
    FakeEventSource.latest().fail();

    expect(stream.state()).toBe('connecting');
  });

  it('forgets earlier failures once a frame arrives', () => {
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.emit('trades'); // the connection is demonstrably working
    source.fail();
    source.fail();

    expect(stream.state()).toBe('live');
  });

  /* -- the polling fallback -------------------------------------------- */

  it('polls every five seconds once degraded', () => {
    const trades = stream.changes('trades');
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    expect(trades()).toBe(1);

    vi.advanceTimersByTime(POLL_INTERVAL_MS);
    expect(trades()).toBe(2);
  });

  it('polls every event type, so no workspace is left stale', () => {
    const counters = EVENT_NAMES.map((name) => stream.changes(name));
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();

    vi.advanceTimersByTime(POLL_INTERVAL_MS);

    // Subscribers never ask which mode they are in: degraded looks exactly
    // like a resync arriving every five seconds, so there is no second code
    // path in any store to keep correct.
    expect(counters.every((c) => c() === 1)).toBe(true);
  });

  it('retries the stream while degraded', () => {
    const first = FakeEventSource.latest();
    first.fail();
    first.fail();
    first.fail();
    expect(FakeEventSource.instances).toHaveLength(1);

    vi.advanceTimersByTime(30_000);

    // Otherwise one bad minute -- an admin restart, a closed laptop lid --
    // leaves the tab polling until someone thinks to reload it.
    expect(FakeEventSource.instances).toHaveLength(2);
  });

  it('stops polling when the stream comes back', () => {
    const trades = stream.changes('trades');
    const first = FakeEventSource.latest();
    first.fail();
    first.fail();
    first.fail();

    vi.advanceTimersByTime(30_000);
    FakeEventSource.latest().emit('resync');
    const afterRecovery = trades();

    vi.advanceTimersByTime(POLL_INTERVAL_MS * 3);

    expect(stream.state()).toBe('live');
    expect(trades()).toBe(afterRecovery); // no poll ticks on top of live events
  });

  it('closes everything on disconnect', () => {
    const trades = stream.changes('trades');
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();

    stream.disconnect();
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 3 + 60_000);

    // A timer surviving teardown would keep refetching against a logged-out
    // session for as long as the tab is open.
    expect(trades()).toBe(0);
    expect(FakeEventSource.instances).toHaveLength(1);
  });
});