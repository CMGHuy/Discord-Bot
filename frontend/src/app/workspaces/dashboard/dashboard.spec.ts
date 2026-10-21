import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { Router, provideRouter } from '@angular/router';
import { Location } from '@angular/common';
import { SpyLocation, provideLocationMocks } from '@angular/common/testing';
import { By } from '@angular/platform-browser';
import { RouterTestingHarness } from '@angular/router/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Dashboard as DashboardData, EquityCandlesResponse, TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { Dashboard, DASHBOARD_COLUMNS, DASHBOARD_PANEL_ORDER } from './dashboard';
import { DashboardStore } from '../../stores/dashboard.store';
import { ToastService } from '../../shell/toast.service';
import { EquityCandlesStore } from '../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { provideMotion } from '../../ui/motion/motion.service';
import { dashboardRoutes } from './dashboard.routes';
import { PositionsTable } from './positions-table';

installMatchMediaPolyfill();

/** Answered, so sb-equity-candles shows its chart and not a loading skeleton
 *  (several tests here assert the page has no skeleton once loaded). */
const CANDLES: EquityCandlesResponse = {
  tf: '1D', basis: 'mtm', currency_symbol: '€', recording_since: '2026-10-20T13:35:00Z',
  as_of: '2026-10-21T14:35:00Z',
  candles: [{ t: '2026-10-20', o: 100, h: 120, l: 90, c: 110, change: 10, change_pct: 10,
              samples: 4, skipped: 0, approx: false }],
};

// The whole Dashboard now mounts a real sb-equity-candles chart. jsdom has no
// canvas, so lightweight-charts' animation-frame draw would throw "Value is
// null" after an awaited test; nothing here asserts on pixels, so frames are
// dropped.
beforeEach(() => {
  vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(0);
});
afterEach(() => vi.restoreAllMocks());

// v85: the explanatory drawers are real <dialog> elements (sb-drawer); jsdom
// has no showModal()/close(). See the polyfill for why <dialog> stays.
installDialogPolyfill();

/** Dashboard reads only currency() from ConnectionStore and
 *  values()/isLoaded()/update() from PreferencesStore -- stubbed rather than
 *  let their own onInit hooks issue real HTTP requests this spec does not
 *  care about. */
const connectionStub = { currency: signal('$'), marketActive: signal<boolean | null>(true) };
const preferencesStub = {
  values: signal({}),
  isLoaded: signal(true),
  update: () => undefined,
};

function payload(overrides: Partial<DashboardData> = {}): DashboardData {
  return {
    account_balance: 10000,
    open_pnl_pct: 1.2,
    open_pnl_amount: 120,
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
      { provide: EquityCandlesStore, useValue: equityCandlesStoreStub(CANDLES) },
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
    current_price: null, current_price_stale: false, exit_price: 110, realized_pnl_amount: 50,
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
    const labels = [...(fixture.nativeElement as HTMLElement).querySelectorAll('[role="tab"] .label')]
      .map((el) => el.textContent?.replace(/\s+/g, ' ').trim());
    expect(labels[0]).toMatch(/^Pending \d+$/);
    expect(labels[1]).toMatch(/^Open \d+$/);
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
    [...el.querySelectorAll<HTMLButtonElement>('sb-trading-performance sb-segmented .segment')]
      .find((s) => s.textContent!.trim() === 'All days')!.click();
    fixture.detectChanges();
    expect(TestBed.inject(DashboardStore).scope()).toBe('all');
  });
});

/* -- v177: the Plan cell's runner forms on the positions table ---------- */

/** `loaded()`, but the positions table's trades request is answered with
 *  `items` instead of empty (the table constructs, and requests, before the
 *  dashboard payload lands). One `#planCell` template serves every tab, so
 *  the tab only changes which rows arrive. */
async function loadedWithRows(items: TradeRow[]): Promise<HTMLElement> {
  const { fixture, backend } = seed();
  fixture.detectChanges();
  for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
    req.flush({ items, total: items.length, page: 1, per_page: 10 });
  }
  backend.expectOne('/api/v1/dashboard?mode=today').flush(payload());
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('Dashboard Plan cell for runners (v177)', () => {
  const runner = tradeRow({
    id: 'p1', status: 'PARTIAL', status_label: 'PARTIAL', direction: 'bearish',
    entry: 60.67, stop_loss: 52.437, target: null, target_is_banked_tp1: true,
    stop_kind: 'trailing', bar_kind: 'trailing', banked_fraction: 0.5,
    banked_exit_price: 58.33, banked_r: 1.98, exit_price: null,
    risk_stop: 61.85, runner_best: 49.94, tp1: 58.33,
    best_pnl_pct: 17.69, stop_pnl_pct: 13.57, leg_index: 1, leg_total: 2,
  });
  const tp1Leg = tradeRow({
    id: 'p1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
    stop_loss: 52.437, target: null, target_is_banked_tp1: true,
    stop_kind: 'trailing', bar_kind: 'trailing', exit_price: 58.33,
    risk_stop: 61.85, runner_best: 49.94, tp1: null, best_pnl_pct: null,
    stop_pnl_pct: null, runner_exit_price: null, leg_index: 0, leg_total: 2,
  });
  const closedRunner = tradeRow({
    id: 'c1', status: 'CLOSED', direction: 'bearish', entry: 60.67,
    stop_loss: 61.85, target: 58.33, exit_price: 52.44, tp1: null,
    runner_exit_price: 52.44, runner_exit_reason: 'giveback', leg_index: 1, leg_total: 2,
  });

  it('reads a PARTIAL trailing runner on two lines', async () => {
    const [cell] = (await loadedWithRows([runner])).querySelectorAll('sb-plan-cell');
    expect(cell.querySelector('.l1')!.textContent!.replace(/\s+/g, ' ').trim())
      .toBe('60.67 → 58.33 / 61.85 (3.9% - 1.9%)');
    expect(cell.querySelector('.l2')!.textContent!.replace(/\s+/g, ' ').trim())
      .toBe('Trail 49.94 → 52.44 (+17.7% / +13.6%)');
  });

  it('keeps today\'s cell on the TP1-leg row of a PARTIAL plan', async () => {
    const [cell] = (await loadedWithRows([tp1Leg])).querySelectorAll('sb-plan-cell');
    expect(cell.querySelector('.runner')).toBeNull();
  });

  it('shows a closed runner\'s exit and names the give-back stop', async () => {
    const [cell] = (await loadedWithRows([closedRunner])).querySelectorAll('sb-plan-cell');
    expect(cell.textContent!.replace(/\s+/g, ' ').trim()).toBe('60.67 → 52.44 / 61.85 (+13.6% - 1.9%)');
    expect(cell.querySelector('[title]')!.getAttribute('title'))
      .toContain('Runner exit (give-back stop): 52.44');
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
  it('draws equity candles with timeframe chips instead of the 30-day sparkline (v172)', async () => {
    const fixture = await loaded({ equity_30d: THIRTY_POINTS });
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-portfolio-value sb-equity-candles')).not.toBeNull();
    expect(el.querySelector('sb-portfolio-value sb-sparkline')).toBeNull();
    const chips = [...el.querySelectorAll('sb-equity-candles [aria-label="Candle timeframe"] button')]
      .map((b) => b.textContent!.trim());
    expect(chips).toEqual(['1H', '4H', '1D', '1W']);
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

describe('dead card-mode contract', () => {
  const read = (p: string) => readFileSync(join(process.cwd(), p), 'utf8');

  it('no longer reads variables nothing sets', () => {
    // v80 D4 removed card mode and with it .card-value; --cell-wrap and
    // --sep-wrap have been set by nothing since. Reading them made the
    // widest cell on the page permanently nowrap behind a comment claiming
    // it was handled.
    const src = read('src/app/workspaces/dashboard/dashboard.ts');
    expect(src).not.toMatch(/--cell-wrap/);
    expect(src).not.toMatch(/--sep-wrap/);
  });

  it('data-table no longer cites the superseded v18 decision', () => {
    expect(read('src/app/ui/data-table/data-table.ts'))
      .not.toMatch(/Cards instead of a table/);
  });
});

/* -- v95 C3 -- panel order ------------------------------------------------- */

describe('Dashboard panel order', () => {
  it('leads with performance at every band', () => {
    // Observed: at 390px positions came first and the portfolio figure was
    // below a 900px table. At 768px performance came first. The phone case
    // was the odd one out, and it was the wrong way round.
    for (const band of ['xs', 'sm', 'md', 'lg', 'xl'] as const) {
      expect(DASHBOARD_PANEL_ORDER[band]?.[0] ?? 'performance').toBe('performance');
    }
  });

  it('no longer carries an undeclared breakpoint', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/dashboard.ts'), 'utf8');
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});

/* -- v95 C4 -- Open Positions column floors -------------------------------- */

describe('DASHBOARD_COLUMNS', () => {
  it('reuses tradeColumns() rather than a second, driftable floor list', () => {
    // Every entry v95 C2 declared a floor on carries it here too, because
    // this is literally that same function's return value.
    expect(DASHBOARD_COLUMNS.length).toBeGreaterThan(0);
    expect(DASHBOARD_COLUMNS.filter((c) => c.inlineFrom === undefined)).toEqual([]);
  });
});

describe('Dashboard v171 price age hint', () => {
  /** Open rows carry a live pnl_pct from the server, so the hint has to sit
   *  on that branch of the P&L cell, not only on the projected one a
   *  PENDING row falls through to (found by the V171-33 Playwright pass). */
  async function withActiveRow(row: Partial<TradeRow>) {
    const { fixture, backend } = seed();
    fixture.detectChanges();
    for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
      const active = req.request.params.get('status') === 'ACTIVE';
      req.flush({ items: active ? [tradeRow({ status: 'ACTIVE', pnl_pct: 0.9, ...row })] : [], total: active ? 1 : 0, page: 1, per_page: 20 });
    }
    backend.expectOne('/api/v1/dashboard?mode=today').flush(payload({ lifecycle: { ACTIVE: 1 } as never }));
    await fixture.whenStable();
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).querySelectorAll('.age-hint');
  }

  it('shows the age beside a live P&L older than the dashboard window', async () => {
    const hints = await withActiveRow({ price_age_s: 75 });
    expect([...hints].map((h) => h.textContent?.trim())).toEqual(['1 min ago']);
  });

  it('stays silent inside the window', async () => {
    expect((await withActiveRow({ price_age_s: 5 })).length).toBe(0);
  });
});

/* v179 §3.2: the trade drawer, driven through a real router so the URL,
 * history and the route's rerun rule are what is tested. The route copies
 * the production rerun rule and counts its resolver runs. */
@Component({ template: '' })
class TradePage {}

let resolverRuns = 0;

const ACTIVITY_ROW = tradeRow({
  id: 't1', ticker: 'AAPL', status: 'ACTIVE', status_label: 'Open', opened_at: '2026-10-20T10:00:00Z',
  pnl_pct: null, realized_pnl_amount: null, exit_price: null, current_price: 105, open_shares: 5,
});

/** Answers the page's own requests: the activity feed's trades query (no
 *  status) gets `recentRows`, the positions table's (status set) nothing. */
async function answer(harness: RouterTestingHarness, backend: HttpTestingController, recentRows: TradeRow[]) {
  for (const req of backend.match((r) => r.url === '/api/v1/trades')) {
    const rows = req.request.params.has('status') ? [] : recentRows;
    req.flush({ items: rows, total: rows.length, page: 1, per_page: 20 });
  }
  for (const req of backend.match('/api/v1/dashboard?mode=today')) req.flush(payload());
  await harness.fixture.whenStable();
  harness.detectChanges();
}

async function routed(url: string) {
  resolverRuns = 0;
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([
        {
          path: 'dashboard', component: Dashboard,
          runGuardsAndResolvers: dashboardRoutes[0].runGuardsAndResolvers,
          resolve: { ready: () => { resolverRuns += 1; return true; } },
        },
        { path: 'trades/:id', component: TradePage },
      ]),
      provideLocationMocks(),
      provideMotion('off'),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      DashboardStore,
      { provide: ConnectionStore, useValue: connectionStub },
      { provide: PreferencesStore, useValue: preferencesStub },
      { provide: EquityCandlesStore, useValue: equityCandlesStoreStub(CANDLES) },
    ],
  });
  const harness = await RouterTestingHarness.create(url);
  // The app's bootstrap listener (initialNavigation) is what subscribes the
  // Router to popstate; the harness never runs it, so Back would be ignored.
  TestBed.inject(Router).setUpLocationChangeListener();
  const backend = TestBed.inject(HttpTestingController);
  const location = TestBed.inject(Location) as SpyLocation;
  return { harness, backend, location };
}

async function settled(harness: RouterTestingHarness) {
  await harness.fixture.whenStable();
  harness.detectChanges();
}

const drawer = (harness: RouterTestingHarness) =>
  harness.routeNativeElement!.querySelector('sb-trade-drawer');

describe('Dashboard trade drawer (v179 §3.2)', () => {
  it('opens an activity row in the drawer and pushes ?trade=', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    const before = location.urlChanges.length;
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    expect(drawer(harness)?.querySelector('header h2')?.textContent?.trim()).toBe('AAPL');
    expect(location.path()).toBe('/dashboard?trade=t1');
    expect(location.urlChanges.slice(before)).toEqual(['/dashboard?trade=t1']);
  });

  it('fetches nothing and re-runs no resolver when only the trade changes', async () => {
    const { harness, backend } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    backend.match(() => true);              // drain anything unrelated to the drawer
    const runs = resolverRuns;
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    expect(drawer(harness)).not.toBeNull();
    expect(backend.match(() => true)).toEqual([]);
    expect(resolverRuns).toBe(runs);
  });

  it('closes on Back', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    location.back();
    // The Router starts a popstate navigation from a setTimeout (Angular's
    // HistoryStateManager), which whenStable() does not wait for.
    await new Promise((resolve) => setTimeout(resolve));
    await settled(harness);
    expect(location.path()).toBe('/dashboard');
    expect(drawer(harness)).toBeNull();
  });

  it('goes back on × after an in-page open, adding no history entry', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    const back = vi.spyOn(location, 'back');
    const before = location.urlChanges.length;
    drawer(harness)!.querySelector<HTMLButtonElement>('.close')!.click();
    // SpyLocation.back() moves path() synchronously; the Router's popstate
    // navigation starts from a setTimeout, so let it run and settle first.
    await new Promise((resolve) => setTimeout(resolve));
    await settled(harness);
    expect(back).toHaveBeenCalledTimes(1);
    expect(location.path()).toBe('/dashboard');
    // Router bookkeeping may re-write the current entry; a push would be a
    // plain URL in urlChanges, a replace is prefixed 'replace: '.
    expect(location.urlChanges.slice(before).filter((url) => !url.startsWith('replace: '))).toEqual([]);
    expect(drawer(harness)).toBeNull();
  });

  it('opens a position row on every device: the table emits, the Dashboard holds the row', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, []);
    const table = harness.routeDebugElement!.query(By.directive(PositionsTable));
    expect((table.componentInstance as { phoneTap: () => string }).phoneTap()).toBe('emit');
    const position = tradeRow({ id: 'p9', ticker: 'HOOD', status: 'ACTIVE', opened_at: '2026-10-20T09:00:00Z' });
    (table.componentInstance as PositionsTable).rowActivate.emit(position);
    await settled(harness);
    expect(drawer(harness)?.querySelector('header h2')?.textContent?.trim()).toBe('HOOD');
    expect(location.path()).toBe('/dashboard?trade=p9');
  });

  it('waits for the activity rows on a cold link, then opens the trade', async () => {
    const { harness, backend, location } = await routed('/dashboard?trade=t1');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate');
    harness.detectChanges();
    expect(drawer(harness)).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
    await answer(harness, backend, [ACTIVITY_ROW]);
    expect(drawer(harness)?.querySelector('header h2')?.textContent?.trim()).toBe('AAPL');
    expect(location.path()).toBe('/dashboard?trade=t1');
  });

  it('removes the parameter with replaceUrl on × after a cold open', async () => {
    const { harness, backend, location } = await routed('/dashboard?trade=t1');
    await answer(harness, backend, [ACTIVITY_ROW]);
    const back = vi.spyOn(location, 'back');
    drawer(harness)!.querySelector<HTMLButtonElement>('.close')!.click();
    await settled(harness);
    expect(back).not.toHaveBeenCalled();
    expect(location.path()).toBe('/dashboard');
    expect(location.urlChanges.at(-1)).toBe('replace: /dashboard');
    expect(drawer(harness)).toBeNull();
  });

  it('sends a link whose trade is not loaded to the full trade page, replacing the entry', async () => {
    const { harness, backend, location } = await routed('/dashboard?trade=gone');
    await answer(harness, backend, [ACTIVITY_ROW]);
    await settled(harness);
    expect(location.path()).toBe('/trades/gone');
    expect(location.urlChanges.at(-1)).toBe('replace: /trades/gone');
  });

  it('opens the full trade page from the drawer link', async () => {
    const { harness, backend, location } = await routed('/dashboard');
    await answer(harness, backend, [ACTIVITY_ROW]);
    harness.routeNativeElement!.querySelector<HTMLButtonElement>('sb-recent-activity button.event-hit')!.click();
    await settled(harness);
    drawer(harness)!.querySelector<HTMLAnchorElement>('a.full-trade')!.click();
    await settled(harness);
    expect(location.path()).toBe('/trades/t1');
  });
});
