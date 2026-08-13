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
import { Risk } from '../api/models';
import { RiskStore } from './risk.store';

/* NG49 — exposure, heat and the killswitch.
 *
 * The read half is the same shape as `DashboardStore` and is covered here only
 * where Risk differs from it. What earns its own tests is the command: the
 * killswitch decides whether the bot opens positions at all, and the two
 * states worth failing over are "the screen says engaged when it is not" and
 * "a failed toggle looks like a successful one".
 */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

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

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

const RESPONSE: Risk = {
  heat: { open_pct: 3, cap_pct: 6, utilisation_pct: 50 },
  positions: [
    {
      trade_id: 'aaaaaaaaaaaaaaaa',
      ticker: 'AAPL',
      strategy: 'RSI Divergence',
      shares: 10,
      entry: 100,
      stop_loss: 95,
      risk_pct: 2,
    },
    {
      trade_id: 'bbbbbbbbbbbbbbbb',
      ticker: 'MSFT',
      strategy: null,
      shares: 5,
      entry: 300,
      stop_loss: 290,
      risk_pct: 1,
    },
  ],
  sector_heat: [{ sector: 'Technology', heat_pct: 3 }],
  clusters: [['AAPL', 'MSFT']],
  throttle: { multiplier: 1, paused: false },
  killswitch: { on: false, reason: null, at: null },
  scan_health: { durations_s: [12, 14], latest_s: 14, slowdown: false },
};

describe('RiskStore', () => {
  let store: InstanceType<typeof RiskStore>;
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
        RiskStore,
      ],
    });
    store = TestBed.inject(RiskStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();
  const respond = (body: Partial<Risk> = {}) =>
    backend.expectOne('/api/v1/risk').flush({ ...RESPONSE, ...body });

  /* -- the read ---------------------------------------------------------- */

  it('loads on creation, with no separate bootstrap call', () => {
    tick();
    respond();

    expect(store.openHeatPct()).toBe(3);
    expect(store.positions()).toHaveLength(2);
    expect(store.empty()).toBe(false);
  });

  it('refetches on a risk event', () => {
    tick();
    respond();

    events.raise('risk');
    tick();
    respond({ heat: { open_pct: 5, cap_pct: 6, utilisation_pct: 83 } });

    expect(store.openHeatPct()).toBe(5);
  });

  it('refetches on a trades event, because exposure moves with positions', () => {
    tick();
    respond();

    events.raise('trades');
    tick();
    respond({ positions: [] });

    expect(store.positions()).toEqual([]);
  });

  it('keeps the previous exposure when a refetch fails', () => {
    // An error panel where the numbers were is worse than stale numbers
    // beside a warning -- this screen is read to decide whether to act.
    tick();
    respond();

    events.raise('risk');
    tick();
    backend
      .expectOne('/api/v1/risk')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.openHeatPct()).toBe(3);
    expect(store.error()).toContain('stale');
  });

  /* -- heat -------------------------------------------------------------- */

  it('does not clamp utilisation over the cap', () => {
    // Over budget is exactly the state the reader must see; a number that
    // stopped at 100 would hide it.
    tick();
    respond({ heat: { open_pct: 8, cap_pct: 6, utilisation_pct: 133 } });

    expect(store.heatUtilisationPct()).toBe(133);
    expect(store.heatOverCap()).toBe(true);
    // Only the bar's width is clamped, so it cannot overflow its track.
    expect(store.heatMeterFraction()).toBe(1);
  });

  it('distinguishes zero heat from unknown heat', () => {
    // A meter at zero and a missing meter look identical and mean opposite
    // things, so the fraction is 0 in one case and null in the other.
    tick();
    respond({ heat: { open_pct: 0, cap_pct: 6, utilisation_pct: 0 } });
    expect(store.heatMeterFraction()).toBe(0);

    events.raise('risk');
    tick();
    respond({ heat: { open_pct: null, cap_pct: 6, utilisation_pct: null } });
    expect(store.heatMeterFraction()).toBeNull();
  });

  it('flags the cap as near from 80% of it', () => {
    tick();
    respond({ heat: { open_pct: 4.8, cap_pct: 6, utilisation_pct: 80 } });

    expect(store.heatNearCap()).toBe(true);
    expect(store.heatOverCap()).toBe(false);
  });

  /* -- the loosely typed fields ------------------------------------------ */

  it('numbers clusters and drops anything that is not a ticker list', () => {
    // `clusters` is `unknown[]` on the wire: the shape belongs to the Python
    // collector, and a template that trusted it would render `[object
    // Object]` the first time it changed.
    tick();
    respond({ clusters: [['AAPL', 'MSFT'], 'NVDA', [], [{ ticker: 'TSLA' }], ['GOOG', 'META']] });

    expect(store.clusters()).toEqual([
      { index: 1, tickers: ['AAPL', 'MSFT'] },
      { index: 2, tickers: ['GOOG', 'META'] },
    ]);
  });

  it('reads the throttle as engaged only below ×1', () => {
    tick();
    respond();
    expect(store.throttled()).toBe(false);

    events.raise('risk');
    tick();
    respond({ throttle: { multiplier: 0.5, paused: true } });

    expect(store.throttled()).toBe(true);
    expect(store.paused()).toBe(true);
  });

  /* -- the command ------------------------------------------------------- */

  it('posts a boolean, never a string, to engage', () => {
    // The endpoint refuses anything that is not a bool precisely so a typo
    // cannot silently release the killswitch.
    tick();
    respond();

    store.toggleKillswitch(true);
    const request = backend.expectOne('/api/v1/risk/killswitch');
    expect(request.request.method).toBe('POST');
    expect(request.request.body.on).toBe(true);
    expect(store.toggling()).toBe(true);

    request.flush({ killswitch: { on: true, reason: 'admin panel', at: '2026-08-13T09:00:00Z' } });
    expect(store.toggling()).toBe(false);
  });

  it('shows the new state immediately, without waiting for the event', () => {
    // The `risk` event comes from a file watcher over killswitch.json, so it
    // is a poll interval behind. A screen that showed "Clear" for that second
    // would answer "is the bot still trading" wrongly, in the dangerous
    // direction.
    tick();
    respond();

    store.toggleKillswitch(true);
    backend
      .expectOne('/api/v1/risk/killswitch')
      .flush({ killswitch: { on: true, reason: 'admin panel', at: null } });

    expect(store.killswitchOn()).toBe(true);
    expect(store.killswitch()?.reason).toBe('admin panel');
  });

  it('leaves the rest of the page alone when the toggle answers', () => {
    // The endpoint returns the killswitch only -- rebuilding the whole risk
    // resource re-clusters open positions, which fetches daily history per
    // ticker. Nothing else may be blanked by the merge.
    tick();
    respond();

    store.toggleKillswitch(true);
    backend
      .expectOne('/api/v1/risk/killswitch')
      .flush({ killswitch: { on: true, reason: null, at: null } });

    expect(store.positions()).toHaveLength(2);
    expect(store.openHeatPct()).toBe(3);
  });

  it('says the killswitch is NOT engaged when the command fails', () => {
    // The failure mode this test exists for: believing the bot stopped
    // taking positions when it did not.
    tick();
    respond();

    store.toggleKillswitch(true);
    backend
      .expectOne('/api/v1/risk/killswitch')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.killswitchOn()).toBe(false);
    expect(store.toggling()).toBe(false);
    expect(store.commandError()).toContain('NOT engaged');
  });

  it('names the direction that failed when releasing', () => {
    tick();
    respond({ killswitch: { on: true, reason: 'drawdown', at: null } });

    store.toggleKillswitch(false);
    backend
      .expectOne('/api/v1/risk/killswitch')
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.killswitchOn()).toBe(true);
    expect(store.commandError()).toContain('NOT released');
  });

  it('holds a command error until the next attempt', () => {
    // Not cleared by a refetch: the user asked for a state change that did
    // not happen, and a poll landing is not an answer to that.
    tick();
    respond();

    store.toggleKillswitch(true);
    backend
      .expectOne('/api/v1/risk/killswitch')
      .error(new ProgressEvent('error'), { status: 0 });

    events.raise('risk');
    tick();
    respond();
    expect(store.commandError()).not.toBeNull();

    store.toggleKillswitch(true);
    expect(store.commandError()).toBeNull();
    backend
      .expectOne('/api/v1/risk/killswitch')
      .flush({ killswitch: { on: true, reason: null, at: null } });
  });
});
