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
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { ConnectionStore } from './connection.store';

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

  changes(name: string): Signal<number> {
    return this.counterFor(name).asReadonly();
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

  it('refetches on the scan event, not only on the bot event', () => {
    // The strip's whole resolution depends on this: `scan_progress.json`
    // raises `scan`, and a store that only listened for `bot` would move the
    // bar once per heartbeat instead of once per second.
    tick();
    respond({ ...SCAN, running: false, progress: null });

    events.raise('scan');
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    expect(store.scanRunning()).toBe(true);
    expect(store.scanProgress()?.current_ticker).toBe('AAPL');
  });

  it('clears the record when the scan ends so no bar outlives it', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    events.raise('scan');
    tick();
    respond({ ...SCAN, running: false, progress: null });

    expect(store.scanRunning()).toBe(false);
    expect(store.scanProgress()).toBeNull();
  });

  it('a failed scan read leaves the bar alone rather than freezing it', () => {
    tick();
    respond({ ...SCAN, running: true, progress: PROGRESS });

    events.raise('scan');
    tick();
    backend.expectOne('/api/v1/health').flush(HEALTH);
    backend.expectOne('/api/v1/system/scan')
      .error(new ProgressEvent('error'), { status: 0 });

    // One failed poll is a blip; the next event corrects it. Blanking the
    // strip on it would have the bar flicker through every scan.
    expect(store.scanProgress()?.pct).toBe(66);
  });
});
