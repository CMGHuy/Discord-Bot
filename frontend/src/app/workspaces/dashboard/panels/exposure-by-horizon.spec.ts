import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { TradeRow } from '../../../api/models';
import { ExposureByHorizon } from './exposure-by-horizon';

function row(over: Partial<TradeRow> = {}): TradeRow {
  return {
    id: 'p1', origin: 'plan', status: 'ACTIVE', ticker: 'AAPL', direction: 'bullish',
    strategy: null, horizon: '2w', tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 10, open_shares: 10, position_value: null,
    current_price: null, current_price_stale: false, exit_price: null, realized_pnl_amount: null,
    pnl_pct: null, r_multiple: null, held_hours: 1, opened_at: '2026-09-01T00:00:00Z',
    closed_at: null, has_note: false, today: false, created_at: null,
    trigger_price: null, follow_score: null, progress_pct: null, entry_pct: null,
    progress_band: null, blink_seconds: null, status_label: 'ACTIVE',
    target_is_banked_tp1: false, stop_kind: 'risk', bar_kind: 'none',
    floor_r: null, price_r: null, headroom_r: null, distance_to_trigger_r: null,
    bars_to_expiry: null, leg_index: 0, leg_total: 1,
    ...over,
  } as TradeRow;
}

function seed() {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
    ],
  });
  const fixture = TestBed.createComponent(ExposureByHorizon);
  const backend = TestBed.inject(HttpTestingController);
  return { fixture, backend };
}

function flush(backend: HttpTestingController, rows: TradeRow[]): void {
  backend.expectOne((r) => r.url === '/api/v1/trades')
    .flush({ items: rows, total: rows.length, page: 1, per_page: 200 });
}

function slicesOf(fixture: { componentInstance: unknown }) {
  return (fixture.componentInstance as unknown as { slices: () => unknown[] }).slices();
}

describe('exposure by horizon panel', () => {
  it('queries open positions at the server page-size cap', () => {
    const { backend } = seed();
    const req = backend.expectOne((r) => r.url === '/api/v1/trades');
    expect(req.request.params.get('status')).toBe('open');
    expect(req.request.params.get('per_page')).toBe('200');
    req.flush({ items: [], total: 0, page: 1, per_page: 200 });
  });

  it('groups open risk by horizon', () => {
    const { fixture, backend } = seed();
    flush(backend, [
      row({ id: 'a', horizon: '2w', entry: 100, stop_loss: 95, open_shares: 10 }),
      row({ id: 'b', horizon: '2w', entry: 50, stop_loss: 45, open_shares: 4 }),
      row({ id: 'c', horizon: '1m', entry: 200, stop_loss: 190, open_shares: 2 }),
    ]);
    fixture.detectChanges();

    const slices = slicesOf(fixture);
    expect(slices).toEqual([
      { label: '1m', count: 20 },   // (200-190) * 2
      { label: '2w', count: 70 },   // (100-95)*10 + (50-45)*4 = 50 + 20
    ].sort((a, b) => b.count - a.count));
  });

  it('labels a horizon-less row Unknown rather than dropping it', () => {
    const { fixture, backend } = seed();
    flush(backend, [row({ horizon: null, entry: 100, stop_loss: 95, open_shares: 1 })]);
    fixture.detectChanges();
    expect(slicesOf(fixture)).toEqual([{ label: 'Unknown', count: 5 }]);
  });

  it('skips a position with no priced risk instead of drawing a zero slice', () => {
    const { fixture, backend } = seed();
    flush(backend, [row({ entry: null, stop_loss: null })]);
    fixture.detectChanges();
    expect(slicesOf(fixture)).toEqual([]);
  });

  it('shows an empty message rather than a blank donut when there is nothing open', () => {
    const { fixture, backend } = seed();
    flush(backend, []);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.querySelector('sb-donut')).toBeNull();
    expect(el.textContent).toContain('No open exposure yet');
  });
});
