import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Dashboard as DashboardData } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { Dashboard } from './dashboard';

/** Dashboard reads only currency() from ConnectionStore and
 *  values()/isLoaded()/update() from PreferencesStore -- stubbed rather than
 *  let their own onInit hooks issue real HTTP requests this spec does not
 *  care about. */
const connectionStub = { currency: signal('$') };
const preferencesStub = {
  values: signal({}),
  isLoaded: signal(true),
  update: () => undefined,
};

function payload(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    account_balance: 10000,
    open_pnl_pct: 1.2,
    risk_used_pct: 3,
    risk_cap_pct: 20,
    open_trades: 2,
    avg_confidence: 3.5,
    win_rate: 55,
    expectancy_r: 0.2,
    equity_30d: { points: [] } as never,
    position_premium: {},
    lifecycle: {},
    scope: 'all',
    ...overrides,
  } as DashboardData;
}

/** The four sb-trade-group panels each provide their own TradesStore and
 *  issue their own request the moment Dashboard's template is created --
 *  content projected via <ng-content> constructs its child components
 *  immediately, regardless of which branch sb-async happens to be showing
 *  at that instant. Not this spec's concern (trade-group.spec.ts covers
 *  it); flushed empty just to unblock the states this spec does care about. */
function flushTradeGroups(backend: HttpTestingController): void {
  for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
    req.flush({ items: [], total: 0, page: 1, per_page: 6 });
  }
}

function seed(): { fixture: ComponentFixture<Dashboard>; backend: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
    ],
  });
  const fixture = TestBed.createComponent(Dashboard);
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

describe('Dashboard states', () => {
  it('shows a skeleton while loading, before the first response', () => {
    const { fixture } = seed();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.skeleton')).toBeTruthy();
  });

  it('shows the error state on a first-load failure', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushTradeGroups(backend);
    backend
      .expectOne('/api/v1/dashboard?mode=today')
      .flush({ error: { code: 'unavailable', message: 'nope' } }, { status: 503, statusText: 'x' });
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.failed')).toBeTruthy();
  });

  it('shows the measured-zero empty state, not a spinner, when open_trades is 0', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushTradeGroups(backend);
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload({ open_trades: 0 }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('No open positions');
    expect(el.querySelector('.skeleton')).toBeNull();
  });
});
