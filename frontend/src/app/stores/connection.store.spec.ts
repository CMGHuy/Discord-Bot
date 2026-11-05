import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  ApplicationRef,
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { MockInstance } from 'vitest';

import { EventStream } from '../api/event-stream';
import { ScanEventProgress } from '../api/models';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import {
  ConnectionStore,
  HEALTH_INTERVAL_MS,
  SCAN_FALLBACK_MIN_INTERVAL_MS,
} from './connection.store';

/* SR58 — the shell's own facts: the version tag and the market session.
 *
 * `ApiClient.health()` had existed with no caller since NG4, so the version
 * footer and "Last updated" the Jinja sidebar showed were simply absent. Both
 * ride this store because it is the one the shell already refetches on the
 * `bot` event, and because `market_active` answers the same question the
 * connection state does from the other side: "these prices have not moved" is
 * a failure during the session and correct behaviour outside it.
 */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();
  readonly lastSeq = signal(0);

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  readonly scanPayload = signal<ScanEventProgress | null>(null);
  readonly requested: [string, unknown][] = [];

  changes(name: string, options?: { minIntervalMs: number }): Signal<number> {
    this.requested.push([name, options]);
    return this.counterFor(name).asReadonly();
  }

  payload(_name: 'scan'): Signal<ScanEventProgress | null> {
    return this.scanPayload.asReadonly();
  }

  /** A `scan` frame as V206-8 delivers it: payload first, then the counter. */
  send(payload: ScanEventProgress | null): void {
    this.scanPayload.set(payload);
    this.raise('scan');
  }

  state(): 'connecting' | 'live' | 'degraded' {
    return 'live';
  }

  connect(): void {
    /* no-op */
  }

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

const HEALTH = {
  ok: true,
  versions: { ui: '1.2.0', bot: '1.3.1', last_updated: '2026-08-14T06:00:00Z' },
  market_active: true,
  currency: '€',
};

const SCAN = {
  pending: false,
  pending_at: null,
  paused: false,
  paused_at: null,
  running: false,
  bot_alive: true,
  bot_last_seen: '2026-08-14T09:00:00Z',
  bot_healthy: true,
  bot_last_success: '2026-08-14T09:00:00Z',
  bot_consecutive_failures: 0,
};

describe('ConnectionStore', () => {
  let store: InstanceType<typeof ConnectionStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;

  beforeEach(() => {
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
      ],
    });
    store = TestBed.inject(ConnectionStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  /** The store fires TWO requests per refresh: health and scan status. */
  const respond = (health: object | null = HEALTH) => {
    const request = backend.expectOne('/api/v1/health');
    if (health === null) request.error(new ProgressEvent('error'), { status: 0 });
    else request.flush(health);
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
  };

  it('reads the ui and bot versions for the shell footer', () => {
    tick();
    respond();

    expect(store.versions()?.ui).toBe('1.2.0');
    expect(store.versions()?.bot).toBe('1.3.1');
  });

  it('reads when the image was last updated', () => {
    tick();
    respond();

    expect(store.lastUpdated()).toBe('2026-08-14T06:00:00Z');
  });

  it('reports no versions before the first answer', () => {
    // Rendering "0.0.0" while the request is in flight would look like a
    // real version rather than an absent one.
    expect(store.versions()).toBeNull();
    expect(store.lastUpdated()).toBeNull();
  });

  it('reports the market session', () => {
    tick();
    respond();

    expect(store.marketActive()).toBe(true);
  });

  it('reports an unknown market session as null, not as closed', () => {
    // Three-valued deliberately: an indicator that says CLOSED before it
    // knows is worse than one that says nothing.
    expect(store.marketActive()).toBeNull();
  });

  it('a failed health read does not flip the connection indicator', () => {
    // The two answer different questions and have their own signals; a
    // health blip must not make the shell claim the admin is unreachable.
    tick();
    respond(null);

    expect(store.marketActive()).toBeNull();
    expect(store.unreachable()).toBe(false);
    expect(store.botAlive()).toBe(true);
  });

  it('refetches health on a bot event, so a deploy updates the footer', () => {
    tick();
    respond();

    events.raise('bot');
    tick();
    respond({ ...HEALTH, versions: { ...HEALTH.versions, ui: '1.2.1' } });

    expect(store.versions()?.ui).toBe('1.2.1');
  });

  it('carries bot_healthy through from scan status', () => {
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend
      .expectOne('/api/v1/system/scan')
      .flush({ ...SCAN, bot_alive: true, bot_healthy: false });

    expect(store.botAlive()).toBe(true);
    expect(store.botHealthy()).toBe(false);
  });

  it('leaves bot health null when the bot has never completed a tick', () => {
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend
      .expectOne('/api/v1/system/scan')
      .flush({ ...SCAN, bot_alive: true, bot_healthy: null });

    expect(store.botHealthy()).toBeNull();
  });

  it('keeps the last successful tick for the freshness chip (v195)', () => {
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend
      .expectOne('/api/v1/system/scan')
      .flush({ ...SCAN, bot_last_success: '2026-08-14T08:55:00Z' });

    expect(store.botLastSuccess()).toBe('2026-08-14T08:55:00Z');
  });

  it('starts with no last successful tick, which is not the same as an old one', () => {
    expect(store.botLastSuccess()).toBeNull();
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush({ ...SCAN, bot_last_success: null });
    expect(store.botLastSuccess()).toBeNull();
  });
});

/* --- scan progress (the shell strip) ------------------------------------ */

describe('ConnectionStore scan progress', () => {
  let store: InstanceType<typeof ConnectionStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;

  beforeEach(() => {
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
      ],
    });
    store = TestBed.inject(ConnectionStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  const respond = (scan: object) => {
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush(scan);
  };

  const PROGRESS = {
    at: '2026-08-14T09:00:00Z', pct: 66, stage: 'analyzing',
    current_ticker: 'AAPL', done: 50, total: 100, qualifying_found: 3,
  };

  it('reports no scan running before the first answer', () => {
    expect(store.scanRunning()).toBe(false);
    expect(store.scanProgress()).toBeNull();
  });

  it('carries the running flag and the published record to the shell', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    expect(store.scanRunning()).toBe(true);
    expect(store.scanProgress()?.pct).toBe(66);
  });

  it('asks for the scan counter throttled to 5 s', () => {
    expect(SCAN_FALLBACK_MIN_INTERVAL_MS).toBe(5000);
    expect(events.requested).toContainEqual(['scan', { minIntervalMs: 5000 }]);
  });

  it('patches the strip from the scan payload and sends no request (v206)', () => {
    tick();
    respond({ ...SCAN, running: false, progress: null });

    events.send({ running: true, progress: PROGRESS });
    tick();

    backend.expectNone('/api/v1/system/scan');
    backend.expectNone('/api/v1/health');
    expect(store.scanRunning()).toBe(true);
    expect(store.scanProgress()?.current_ticker).toBe('AAPL');
  });

  it('a scan tick with no payload falls back to /system/scan, never /health', () => {
    // An older server, a failed broker read or degraded mode: fetch instead.
    tick();
    respond({ ...SCAN, running: false, progress: null });

    events.send(null);
    tick();

    backend.expectNone('/api/v1/health');
    backend.expectOne('/api/v1/system/scan').flush({ ...SCAN, running: true, progress: PROGRESS });
    expect(store.scanProgress()?.pct).toBe(66);
  });

  it('clears the record when the scan ends so no bar outlives it', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    events.send({ running: false, progress: null });
    tick();

    expect(store.scanRunning()).toBe(false);
    expect(store.scanProgress()).toBeNull();
  });

  it('a failed fallback read leaves the bar alone rather than freezing it', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    events.send(null);
    tick();
    backend.expectOne('/api/v1/system/scan').error(new ProgressEvent('error'), { status: 0 });

    // One failed poll is a blip; the next event corrects it.
    expect(store.scanProgress()?.pct).toBe(66);
  });

  it('a bot event still refetches both, so the heartbeat facts move', () => {
    tick();
    respond({ ...SCAN, bot_last_seen: '2026-08-14T09:00:00Z' });

    events.raise('bot');
    tick();
    respond({ ...SCAN, bot_last_seen: '2026-08-14T09:05:00Z' });

    expect(store.botLastSeen()).toBe('2026-08-14T09:05:00Z');
  });
});

/* --- the 5-minute /health timer (v206) ----------------------------------- */

describe('ConnectionStore health timer', () => {
  let backend: HttpTestingController;
  let hidden: MockInstance<() => boolean> | null = null;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
      ],
    });
    TestBed.inject(ConnectionStore);
    backend = TestBed.inject(HttpTestingController);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
  });

  afterEach(() => {
    hidden?.mockRestore();
    hidden = null;
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  const setHidden = (value: boolean) => {
    hidden ??= vi.spyOn(document, 'hidden', 'get');
    hidden.mockReturnValue(value);
    document.dispatchEvent(new Event('visibilitychange'));
  };

  it('refreshes /health every 5 minutes while visible, and nothing else', () => {
    expect(HEALTH_INTERVAL_MS).toBe(300_000);
    vi.advanceTimersByTime(HEALTH_INTERVAL_MS - 1);
    backend.expectNone('/api/v1/health');
    vi.advanceTimersByTime(1);
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectNone('/api/v1/system/scan');
  });

  it('skips the timer while hidden and catches up once when the tab is visible again', () => {
    setHidden(true);
    vi.advanceTimersByTime(HEALTH_INTERVAL_MS * 2);
    backend.expectNone('/api/v1/health');

    setHidden(false);
    backend.expectOne('/api/v1/health').flush(HEALTH);
    setHidden(false);
    backend.expectNone('/api/v1/health');
  });

  it('does not catch up on visible when the last fetch is recent', () => {
    vi.advanceTimersByTime(60_000);
    setHidden(true);
    setHidden(false);
    backend.expectNone('/api/v1/health');
  });

  it('stops the timer and the visibility listener when the store is destroyed', () => {
    const clear = vi.spyOn(globalThis, 'clearInterval');
    const remove = vi.spyOn(document, 'removeEventListener');
    TestBed.resetTestingModule();
    expect(clear).toHaveBeenCalled();
    expect(remove.mock.calls.some(([type]) => type === 'visibilitychange')).toBe(true);
    clear.mockRestore();
    remove.mockRestore();
  });
});

/* --- against the real EventStream: the throttle is real (v206) ----------- */

class FakeEventSource {
  static latest: FakeEventSource | null = null;
  readonly listeners = new Map<string, ((event: MessageEvent) => void)[]>();
  onerror: (() => void) | null = null;
  constructor(readonly url: string) { FakeEventSource.latest = this; }
  addEventListener(name: string, handler: (event: MessageEvent) => void): void {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), handler]);
  }
  close(): void { /* no-op */ }
  emit(name: string, body: object = {}): void {
    const event = new MessageEvent(name, { data: JSON.stringify({ seq: 1, at: '2026-11-05T15:40:00+00:00', ...body }) });
    for (const handler of this.listeners.get(name) ?? []) handler(event);
  }
}

describe('ConnectionStore on the real EventStream', () => {
  let store: InstanceType<typeof ConnectionStore>;
  let backend: HttpTestingController;
  const PROGRESS = {
    at: '2026-11-05T15:40:00+00:00', pct: 40, stage: 'analyzing',
    current_ticker: 'MSFT', done: 4, total: 10, qualifying_found: 1,
  };

  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('EventSource', FakeEventSource);
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(ConnectionStore);
    backend = TestBed.inject(HttpTestingController);
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan').flush(SCAN);
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const scans = () => backend.match('/api/v1/system/scan');

  it('thin scan frames every 500 ms make at most one fallback call per 5 s, and no /health', () => {
    FakeEventSource.latest!.emit('scan');
    tick();
    expect(scans()).toHaveLength(1);
    for (let ms = 500; ms < 5000; ms += 500) {
      vi.advanceTimersByTime(500);
      FakeEventSource.latest!.emit('scan');
      tick();
    }
    expect(scans()).toHaveLength(0);
    vi.advanceTimersByTime(500); // t = 5 s: the trailing bump
    tick();
    expect(scans()).toHaveLength(1);
    backend.expectNone('/api/v1/health');
  });

  it('scan frames that carry progress send no request at all', () => {
    for (let i = 0; i < 10; i++) {
      FakeEventSource.latest!.emit('scan', { progress: { running: true, progress: { ...PROGRESS, done: i } } });
      tick();
      vi.advanceTimersByTime(1000);
      tick();
    }
    backend.verify();
    expect(store.scanProgress()?.done).toBe(9);
  });

  it('a resync refetches health and scan status once each, not twice', () => {
    FakeEventSource.latest!.emit('resync');
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    expect(scans()).toHaveLength(1);
  });
});
