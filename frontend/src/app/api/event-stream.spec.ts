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

  /** Deliver a frame the way the server sends it: named event, thin body,
   *  plus any extra keys (v206: `progress` on `scan`). */
  emit(name: string, seq = 1, body: object = {}): void {
    this.emitRaw(name, JSON.stringify({ seq, at: '2026-08-12T00:00:00+00:00', ...body }));
  }

  /** Deliver a frame whose data is exactly `data`, parseable or not. */
  emitRaw(name: string, data: string): void {
    const event = new MessageEvent(name, { data });
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

  /* -- the scan payload (v206 P1-c) ------------------------------------- */

  const RECORD = {
    at: '2026-11-05T15:40:00+00:00', pct: 66, stage: 'analyzing',
    current_ticker: 'AAPL', done: 50, total: 100, qualifying_found: 3,
  };
  const PAYLOAD = { running: true, progress: RECORD };
  const scanFrame = (seq = 1) => FakeEventSource.latest().emit('scan', seq, { progress: PAYLOAD });
  const degradeNow = () => {
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();
  };

  it('holds nothing before the first scan frame', () => {
    expect(stream.payload('scan')()).toBeNull();
  });

  it('holds the last validated payload of a scan frame', () => {
    scanFrame(1);
    FakeEventSource.latest().emit('scan', 2, { progress: { running: true, progress: { ...RECORD, pct: 70 } } });
    expect(stream.payload('scan')()).toEqual({ running: true, progress: { ...RECORD, pct: 70 } });
  });

  it('a thin scan frame sets it back to null, so the store falls back to fetching', () => {
    scanFrame(1);
    FakeEventSource.latest().emit('scan', 2);
    expect(stream.payload('scan')()).toBeNull();
  });

  it('a malformed payload is null, and the counter still bumps', () => {
    const scan = stream.changes('scan');
    scanFrame(1);
    FakeEventSource.latest().emit('scan', 2, { progress: { running: 'yes', progress: RECORD } });
    expect(stream.payload('scan')()).toBeNull();
    expect(scan()).toBe(2);
  });

  it('an unparseable frame is null, and the counter still bumps', () => {
    const scan = stream.changes('scan');
    scanFrame(1);
    FakeEventSource.latest().emitRaw('scan', '{not json');
    expect(stream.payload('scan')()).toBeNull();
    expect(scan()).toBe(2);
  });

  it('is set before the counters move, so a reaction reads the payload it came with', () => {
    const seen: unknown[] = [];
    stream.raised.subscribe(() => seen.push(stream.payload('scan')()));
    scanFrame(1);
    expect(seen).toEqual([PAYLOAD]);
  });

  it('is cleared on resync: the client refetches everything', () => {
    scanFrame(1);
    FakeEventSource.latest().emit('resync');
    expect(stream.payload('scan')()).toBeNull();
  });

  it('is cleared on degrade, and a 5 s poll tick never brings it back', () => {
    const scan = stream.changes('scan');
    scanFrame(1);
    degradeNow();
    expect(stream.payload('scan')()).toBeNull();
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 2);
    expect(scan()).toBe(3); // the frame, then two poll ticks
    expect(stream.payload('scan')()).toBeNull();
  });

  it('is cleared when the stream reconnects', () => {
    scanFrame(1);
    stream.disconnect();
    stream.connect();
    expect(FakeEventSource.instances).toHaveLength(2);
    expect(stream.payload('scan')()).toBeNull();
  });

  it('is left alone by every other event, and no other counter moves on a scan frame', () => {
    const trades = stream.changes('trades');
    const bot = stream.changes('bot');
    const scan = stream.changes('scan');
    scanFrame(1);
    FakeEventSource.latest().emit('trades', 2);
    FakeEventSource.latest().emit('ping', 3);
    expect(stream.payload('scan')()).toEqual(PAYLOAD);
    expect([trades(), bot(), scan()]).toEqual([1, 0, 1]);
  });

  it('feeds the throttled scan view exactly as before', () => {
    const slow = stream.changes('scan', { minIntervalMs: 5_000 });
    for (let i = 0; i < 5; i++) scanFrame(i + 1);
    expect(slow()).toBe(1);
    vi.advanceTimersByTime(5_000);
    expect(slow()).toBe(2);
    expect(stream.payload('scan')()).toEqual(PAYLOAD);
  });

  /* -- throttled subscription (v132) ------------------------------------ */

  it('collapses a burst into one immediate and one trailing bump', () => {
    const raw = stream.changes('scan');
    const slow = stream.changes('scan', { minIntervalMs: 30_000 });
    for (let i = 0; i < 10; i++) FakeEventSource.latest().emit('scan', i + 1);
    expect(raw()).toBe(10);
    expect(slow()).toBe(1);
    vi.advanceTimersByTime(30_000);
    expect(slow()).toBe(2);
    vi.advanceTimersByTime(60_000);
    expect(slow()).toBe(2);
  });

  it('passes a lone event straight through after a quiet interval', () => {
    const slow = stream.changes('scan', { minIntervalMs: 30_000 });
    FakeEventSource.latest().emit('scan', 1);
    vi.advanceTimersByTime(31_000);
    FakeEventSource.latest().emit('scan', 2);
    expect(slow()).toBe(2);
  });

  it('shares one throttle between subscribers of the same event and interval', () => {
    expect(stream.changes('scan', { minIntervalMs: 30_000 }))
      .toBe(stream.changes('scan', { minIntervalMs: 30_000 }));
  });

  it('cancels an overdue trailing timer when a new event releases immediately', () => {
    const slow = stream.changes('scan', { minIntervalMs: 30_000 });
    vi.setSystemTime(0);
    FakeEventSource.latest().emit('scan', 1);
    vi.setSystemTime(5_000);
    FakeEventSource.latest().emit('scan', 2);
    vi.setSystemTime(31_000);
    FakeEventSource.latest().emit('scan', 3);
    expect(slow()).toBe(2);
    vi.runOnlyPendingTimers();
    expect(slow()).toBe(2);
  });

  it('defers a pending fallback refresh while hidden until the tab returns', () => {
    const slow = stream.changes('scan', { minIntervalMs: 30_000 });
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 2);
    expect(slow()).toBe(1);

    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    vi.advanceTimersByTime(30_000);
    expect(slow()).toBe(1);
    hidden.mockReturnValue(false);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(slow()).toBe(2);
    hidden.mockRestore();
  });

  it('does not poll while the document is hidden, and catches up once on return', () => {
    const source = FakeEventSource.latest();
    source.fail();
    source.fail();
    source.fail();
    const trades = stream.changes('trades');
    const before = trades();
    const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true);
    vi.advanceTimersByTime(POLL_INTERVAL_MS * 3);
    expect(trades()).toBe(before);
    hidden.mockReturnValue(false);
    document.dispatchEvent(new Event('visibilitychange'));
    expect(trades()).toBe(before + 1);
    hidden.mockRestore();
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

describe('market event (v201)', () => {
  it('sits just before feed, the last name EVENT_NAMES subscribes to', () => {
    expect(EVENT_NAMES[EVENT_NAMES.length - 2]).toBe('market');
  });

  it('a market SSE message bumps changes(market)', () => {
    FakeEventSource.reset();
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const stream = TestBed.inject(EventStream);
    stream.connect();
    const market = stream.changes('market');
    FakeEventSource.latest().emit('market');
    expect(market()).toBe(1);
    stream.disconnect();
    vi.unstubAllGlobals();
  });
});

describe('feed event (v227)', () => {
  it('is the last name EVENT_NAMES subscribes to', () => {
    expect(EVENT_NAMES[EVENT_NAMES.length - 1]).toBe('feed');
  });

  it('a feed SSE message bumps changes(feed) and nothing else', () => {
    FakeEventSource.reset();
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const stream = TestBed.inject(EventStream);
    stream.connect();
    const feed = stream.changes('feed');
    const market = stream.changes('market');
    FakeEventSource.latest().emit('feed');
    expect(feed()).toBe(1);
    expect(market()).toBe(0);
    stream.disconnect();
    vi.unstubAllGlobals();
  });
});
