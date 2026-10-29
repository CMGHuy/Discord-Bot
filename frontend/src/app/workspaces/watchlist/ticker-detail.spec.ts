import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { patchState } from '@ngrx/signals';
import { unprotected } from '@ngrx/signals/testing';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';

import { TradeRow } from '../../api/models';
import { ChartStore } from '../../stores/chart.store';
import { TradesStore } from '../../stores/trades.store';
import { TickerDetail } from './ticker-detail';
import { TradeChart } from '../../ui/chart/trade-chart';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { RouteTitleService } from '../../routing/route-title.service';

// The canvas chart needs browser APIs absent in jsdom; these cases exercise
// the real table and drawer, so replace only that unrelated rendering leaf.
@Component({ selector: 'sb-trade-chart', template: '' })
class ChartStub { readonly data = input<unknown>(null); }

function row(overrides: Partial<TradeRow>): TradeRow {
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

describe('TickerDetail rowKey', () => {
  it('is unique for two leg-rows sharing one id', () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore, ChartStore,
      ],
    });
    const f = TestBed.createComponent(TickerDetail);
    const rowKey = (f.componentInstance as unknown as {
      rowKey: (r: TradeRow) => string;
    }).rowKey;

    // This view renders rows from the same leg-expanding /api/v1/trades the
    // Trades table reads, so a scaled-out position arrives as two rows that
    // share one plan id -- `row.id` alone is not a key.
    const tp1 = row({ leg_index: 0, leg_total: 2 });
    const runner = row({ leg_index: 1, leg_total: 2 });
    expect(rowKey(tp1)).not.toBe(rowKey(runner));
  });
});

describe('TickerDetail trades on a phone (v179 §3.1)', () => {
  function renderPhone(): ComponentFixture<TickerDetail> {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore, ChartStore, phoneViewport(),
      ],
    });
    TestBed.overrideComponent(TickerDetail, {
      remove: { imports: [TradeChart] }, add: { imports: [ChartStub] },
    });
    const fixture = TestBed.createComponent(TickerDetail);
    fixture.componentRef.setInput('symbol', 'AAPL');
    fixture.detectChanges();
    patchState(unprotected(TestBed.inject(TradesStore)), {
      data: { items: [row({ id: 't7' })], total: 1, page: 1, per_page: 25 },
    });
    fixture.detectChanges();
    return fixture;
  }
  const table = (fixture: ComponentFixture<TickerDetail>) =>
    (fixture.nativeElement as HTMLElement).querySelector('sb-data-table') as HTMLElement;

  it('shows ticker and P&L on line 1, status and held on line 2', () => {
    expect(compactKeys(table(renderPhone()))).toEqual(['ticker', 'pnl_pct', 'status', 'held']);
  });

  it('reaches all six columns and links the drawer to the trade', () => {
    const fixture = renderPhone();
    openRowDrawer(table(fixture));
    fixture.detectChanges();
    expect([...compactKeys(table(fixture)), ...drawerKeys(table(fixture))].sort())
      .toEqual(['entry', 'held', 'now', 'pnl_pct', 'status', 'ticker']);
    expect(table(fixture).querySelector('a.drawer-detail-link')!.getAttribute('href')).toBe('/trades/t7');
  });
});

/* -- v195 Phase 4, §5.2 and §1.4 -- ticker detail on sb-page ---------------- */

describe('TickerDetail on sb-page (v195 Phase 4, §5.2, §1.4)', () => {
  function mountDetail(symbol = 'NVDA'): ComponentFixture<TickerDetail> {
    installDialogPolyfill();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(), provideRouter([]),
        provideHttpClient(), provideHttpClientTesting(),
        TradesStore, ChartStore,
      ],
    });
    TestBed.overrideComponent(TickerDetail, {
      remove: { imports: [TradeChart] }, add: { imports: [ChartStub] },
    });
    const fixture = TestBed.createComponent(TickerDetail);
    TestBed.inject(RouteTitleService).set('Ticker detail', 'One symbol, in depth');
    fixture.componentRef.setInput('symbol', symbol);
    fixture.detectChanges();
    patchState(unprotected(TestBed.inject(TradesStore)), {
      data: {
        items: [row({ id: 't7', ticker: symbol, status: 'open' }), row({ id: 't8', ticker: symbol })],
        total: 2, page: 1, per_page: 25,
      },
    });
    fixture.detectChanges();
    return fixture;
  }
  const el = (fixture: ComponentFixture<TickerDetail>) => fixture.nativeElement as HTMLElement;

  it('titles the page with the symbol, as its one h1', () => {
    const page = el(mountDetail());
    expect(page.querySelectorAll('h1')).toHaveLength(1);
    expect(page.querySelector('sb-page h1.title')!.textContent!.trim()).toBe('NVDA');
    expect(page.querySelector('sb-page .description')!.textContent!.trim()).toBe('One symbol, in depth');
  });

  it('names the symbol as the breadcrumb detail segment', () => {
    mountDetail();
    expect(TestBed.inject(RouteTitleService).detail()).toBe('NVDA');
  });

  it('puts the symbol back after a title update clears it while the page is open', () => {
    const fixture = mountDetail();
    const titles = TestBed.inject(RouteTitleService);
    titles.set('Ticker detail', 'One symbol, in depth', '/somewhere-else');
    expect(titles.detail()).toBeNull();
    fixture.detectChanges();
    expect(titles.detail()).toBe('NVDA');
  });

  it('follows the symbol when the route reuses the page for another ticker', () => {
    const fixture = mountDetail();
    fixture.componentRef.setInput('symbol', 'MSFT');
    fixture.detectChanges();
    expect(TestBed.inject(RouteTitleService).detail()).toBe('MSFT');
    expect(el(fixture).querySelector('sb-page h1.title')!.textContent!.trim()).toBe('MSFT');
  });

  it('has no scope bar and no in-page back link: the breadcrumb is the way back', () => {
    const page = el(mountDetail());
    expect(page.querySelector('[page-scope]')).toBeNull();
    expect(page.querySelector('a.back')).toBeNull();
    expect(page.querySelector('sb-section-head')).toBeNull();
  });

  it('puts the counts at the header right, the chart primary and the trades panel secondary', () => {
    const page = el(mountDetail());
    expect(page.querySelector('sb-page [page-actions]')!.textContent!.replace(/\s+/g, ' ').trim()).toBe('1 open · 1 closed');
    expect(page.querySelector('sb-page [page-primary]')!.tagName.toLowerCase()).toBe('sb-chart-container');
    const secondary = page.querySelectorAll('sb-page [page-secondary]');
    expect(secondary).toHaveLength(1);
    expect(secondary[0].querySelector('sb-data-table')).toBeTruthy();
    expect(secondary[0].querySelector('a.all-link')!.getAttribute('href')).toBe('/trades?ticker=NVDA');
  });

  it('sets its order figures on the 14px body step, in both densities', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/watchlist/ticker-detail.ts'), 'utf8');
    expect(src).toMatch(/:host \{[^}]*--text-table: var\(--text-body\);/);
  });
});
