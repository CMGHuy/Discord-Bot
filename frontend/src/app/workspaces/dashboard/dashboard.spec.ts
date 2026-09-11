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
import { Dashboard as DashboardData, TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { Dashboard } from './dashboard';
import { DashboardStore } from '../../stores/dashboard.store';

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
      DashboardStore,
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
    ],
  });
  const fixture = TestBed.createComponent(Dashboard);
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

function tradeRow(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', ticker: 'AAPL',
    direction: 'bullish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 5, open_shares: null, position_value: null,
    current_price: null, exit_price: 110, realized_pnl_amount: 50,
    pnl_pct: 10, r_multiple: 2, held_hours: 1, opened_at: null, closed_at: null,
    has_note: false, today: true, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'CLOSED', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  } as TradeRow;
}

describe('Dashboard rowKey', () => {
  it('is unique for two leg-rows sharing one id', () => {
    const { fixture } = seed();
    const rowKey = (fixture.componentInstance as unknown as {
      rowKey: (r: TradeRow) => string;
    }).rowKey;

    // v79 splits a scaled-out position into one row per leg, and both legs
    // keep the plan's id -- so a key of `row.id` alone collides and the
    // table's trackBy drops one of the two rows.
    const tp1 = tradeRow({ leg_index: 0, leg_total: 2 });
    const runner = tradeRow({ leg_index: 1, leg_total: 2 });
    expect(rowKey(tp1)).not.toBe(rowKey(runner));
  });
});

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

  it('renders no in-page heading, because the top bar owns the title', () => {
    const { fixture } = seed();
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).not.toContain('Dashboard');
  });
});

/** sb-async only projects its content (the panels, the positions table) in
 *  its success branch -- loading shows a skeleton instead -- so every test
 *  here has to seed and flush a real payload before it can find any of them. */
async function loaded(overrides: Partial<DashboardData> = {}) {
  const { fixture, backend } = seed();
  fixture.detectChanges();
  flushTradeGroups(backend);
  backend.expectOne('/api/v1/dashboard?mode=today').flush(payload(overrides));
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture;
}

describe('Dashboard v85 layout', () => {
  it('lays the page out as the five panels plus the positions table', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('sb-portfolio-value')).not.toBeNull();
    expect(el.querySelector('sb-trading-performance')).not.toBeNull();
    expect(el.querySelector('sb-recent-activity')).not.toBeNull();
    expect(el.querySelector('sb-watchlist-panel')).not.toBeNull();
    expect(el.querySelector('sb-market-movers')).not.toBeNull();
  });

  it('drops the old metric rows the panels replaced', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('.primary')).toBeNull();
    expect(el.querySelector('sb-chip-row.chips')).toBeNull();
    expect(el.querySelector('.lifecycle')).toBeNull();
  });

  it('has no Risk & Exposure or Account Info panel', async () => {
    const fixture = await loaded();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('Risk & Exposure');
    expect(text).not.toContain('Account Info');
  });

  it('routes the panel scope control back into the store', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('[data-scope="all"]')!.click();
    fixture.detectChanges();
    expect(TestBed.inject(DashboardStore).scope()).toBe('all');
  });
});
