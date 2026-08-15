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
});
