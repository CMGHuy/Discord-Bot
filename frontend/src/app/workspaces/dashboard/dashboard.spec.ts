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
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { Dashboard } from './dashboard';
import { DashboardStore } from '../../stores/dashboard.store';
import { ToastService } from '../../shell/toast.service';

// v85: the explanatory drawers are real <dialog> elements (sb-drawer); jsdom
// has no showModal()/close(). See the polyfill for why <dialog> stays.
installDialogPolyfill();

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
    expect(el.textContent).toContain('No active positions');
    expect(el.querySelector('.skeleton')).toBeNull();
  });

  it('keeps portfolio, performance, activity and movers when open_trades is 0', async () => {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    flushTradeGroups(backend);
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload({ open_trades: 0 }));
    await fixture.whenStable();
    fixture.detectChanges();

    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-portfolio-value')).not.toBeNull();
    expect(el.querySelector('sb-trading-performance')).not.toBeNull();
    expect(el.querySelector('sb-recent-activity')).not.toBeNull();
    expect(el.querySelector('sb-market-movers')).not.toBeNull();
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
  it('keeps the dashboard focused on portfolio, performance, activity and movers', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;

    expect(el.querySelector('sb-portfolio-value')).not.toBeNull();
    expect(el.querySelector('sb-trading-performance')).not.toBeNull();
    expect(el.querySelector('sb-recent-activity')).not.toBeNull();
    expect(el.querySelector('sb-market-movers')).not.toBeNull();
    expect(el.querySelector('sb-watchlist-panel')).toBeNull();
    expect(el.querySelector('sb-exposure-by-horizon')).toBeNull();
  });

  it('renders one tabbed positions table, not four stacked groups', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelectorAll('sb-positions-table')).toHaveLength(1);
    expect(el.querySelector('sb-trade-group')).toBeNull();
  });

  it('feeds the tab counts from the lifecycle payload', async () => {
    const fixture = await loaded();
    const labels = [...(fixture.nativeElement as HTMLElement).querySelectorAll('[role="tab"]')]
      .map((t) => t.textContent?.replace(/\s+/g, ' ').trim());
    expect(labels[0]).toMatch(/^Open \d+$/);
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

describe('Dashboard explanatory help', () => {
  it('merges the Open positions help into one tooltip', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    const hint = el.querySelector<HTMLElement>('sb-hint.lifecycle-hint')!;
    expect(hint).not.toBeNull();
    hint.dispatchEvent(new MouseEvent('mouseenter'));
    fixture.detectChanges();
    expect(el.querySelector<HTMLElement>('sb-hint.lifecycle-hint [role="tooltip"]')!.hidden).toBe(false);
    expect(el.textContent).toContain('Only trades that meet');
    expect(el.querySelector('sb-hint.lifecycle-hint sb-plan-lifecycle-diagram')).not.toBeNull();
    expect(el.textContent).toContain('Share counts are snapshotted');
    expect(el.querySelectorAll('sb-panel.positions-panel sb-hint')).toHaveLength(1);
  });

  it('does not render a second sizing help trigger', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-info="sizing"]')).toBeNull();
  });

  it('drops the prices footnote button and its drawer', async () => {
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('[data-info="prices"]')).toBeNull();
    expect(el.textContent).not.toContain('About prices');
  });
});

const THIRTY_POINTS = { points: Array.from({ length: 30 }, (_, i) => i) } as never;

describe('Dashboard portfolio value', () => {
  it('shows its one honest 30-day series without a range picker', async () => {
    const fixture = await loaded({ equity_30d: THIRTY_POINTS });
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-portfolio-value sb-sparkline')).not.toBeNull();
    expect(el.textContent).not.toContain('1W');
    expect(el.textContent).not.toContain('1M');
    expect(el.textContent).not.toContain('ALL');
  });
});

describe('Dashboard v85 close-all', () => {
  // ConfirmDialog exposes no [role="dialog"]/[data-confirm] of its own --
  // every existing consumer (controls.spec.ts) reads the native `dialog`
  // element and its `.open` property, and picks the confirm button by
  // position (the last button inside sb-confirm-dialog). Matched here rather
  // than inventing a second selection convention.
  const dialogText = (el: HTMLElement) => el.querySelector('sb-confirm-dialog dialog')!.textContent!;
  const isDialogOpen = (el: HTMLElement) =>
    el.querySelector<HTMLDialogElement>('sb-confirm-dialog dialog')!.open;
  const clickConfirm = (el: HTMLElement) =>
    [...el.querySelectorAll<HTMLButtonElement>('sb-confirm-dialog button')].at(-1)!.click();

  /** Opens the dropdown and picks one of its three menu items by label
   *  ("Close all open", "Close all partial", "Close all open/partial"). */
  function pickCloseAllScope(fixture: ComponentFixture<Dashboard>, label: string): void {
    const el = fixture.nativeElement as HTMLElement;
    el.querySelector<HTMLButtonElement>('[data-action="close-all"]')!.click();
    fixture.detectChanges();
    const item = [...el.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')]
      .find((b) => b.textContent!.trim() === label)!;
    item.click();
    fixture.detectChanges();
  }

  it('opens a menu of three scopes rather than closing everything on one click', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const el = fixture.nativeElement as HTMLElement;

    el.querySelector<HTMLButtonElement>('[data-action="close-all"]')!.click();
    fixture.detectChanges();

    const items = [...el.querySelectorAll<HTMLButtonElement>('[role="menuitem"]')]
      .map((b) => b.textContent!.trim());
    expect(items).toEqual(['Close all open', 'Close all partial', 'Close all open/partial']);
    // Picking a scope is what opens the confirm dialog, not the trigger click.
    expect(isDialogOpen(el)).toBe(false);
  });

  it('asks before closing, and says what closing means', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const backend = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;

    pickCloseAllScope(fixture, 'Close all open/partial');

    expect(isDialogOpen(el)).toBe(true);
    expect(dialogText(el)).toContain('realis');   // realise/realised
    expect(dialogText(el)).not.toContain('delete');
    // Nothing has been sent yet.
    backend.expectNone((r) => r.url.startsWith('/api/v1/trades/close-open'));
  });

  it('posts once confirmed and refetches the page', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const backend = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    pickCloseAllScope(fixture, 'Close all open/partial');
    clickConfirm(el);

    const req = backend.expectOne('/api/v1/trades/close-open?scope=open_partial');
    expect(req.request.method).toBe('POST');
    req.flush({ closed: 2, failed: 0, tickers: ['ASTS', 'HOOD'] });
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload());
  });

  it('closes only the picked scope', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const backend = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;

    pickCloseAllScope(fixture, 'Close all open');
    expect(dialogText(el)).toContain('Close all open positions?');
    clickConfirm(el);

    backend.expectOne('/api/v1/trades/close-open?scope=open')
      .flush({ closed: 2, failed: 0, tickers: ['ASTS', 'HOOD'] });
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload());
  });

  it('reports a partial failure rather than claiming success', async () => {
    const fixture = await loaded({ lifecycle: { ACTIVE: 2, PARTIAL: 1 } as never });
    const backend = TestBed.inject(HttpTestingController);
    const el = fixture.nativeElement as HTMLElement;
    pickCloseAllScope(fixture, 'Close all open/partial');
    clickConfirm(el);

    backend.expectOne('/api/v1/trades/close-open?scope=open_partial')
      .flush({ closed: 1, failed: 1, tickers: ['ASTS'] });
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload());

    const toast = TestBed.inject(ToastService);
    expect(toast.toasts().at(-1)?.message).toContain('1 failed');
  });

  it('offers nothing to close when the book is empty', async () => {
    // Default payload's lifecycle is {} -- zero ACTIVE/PARTIAL. A confirm
    // dialog for a no-op is a question with one answer.
    const fixture = await loaded();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector<HTMLButtonElement>('[data-action="close-all"]')!.disabled).toBe(true);
  });

  it('puts no destructive bulk operations on this panel -- D14', async () => {
    // clear-open and clear-history DELETE records. They stay where they live
    // today; one click from a close-the-book action is how the wrong one
    // gets pressed.
    const fixture = await loaded();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).not.toContain('Clear open');
    expect(text).not.toContain('Clear history');
  });
});
