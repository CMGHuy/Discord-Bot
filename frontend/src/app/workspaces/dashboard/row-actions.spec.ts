import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { TradeRow } from '../../api/models';
import { RowActions } from './row-actions';

function row(over: Partial<TradeRow> = {}): TradeRow {
  return {
    id: 'p1', origin: 'plan', status: 'ACTIVE', ticker: 'AAPL', direction: 'bullish',
    strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 10, open_shares: 10, position_value: null,
    current_price: null, exit_price: null, realized_pnl_amount: null,
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

let httpMock: HttpTestingController;

function mount(inputs: { row: TradeRow }): ComponentFixture<RowActions> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideRouter([]),
      provideHttpClient(),
      provideHttpClientTesting(),
    ],
  });
  const f = TestBed.createComponent(RowActions);
  f.componentRef.setInput('row', inputs.row);
  f.detectChanges();
  httpMock = TestBed.inject(HttpTestingController);
  return f;
}

function openMenu(f: ComponentFixture<RowActions>): void {
  (f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.trigger')!.click();
  f.detectChanges();
}

function items(f: ComponentFixture<RowActions>): string[] {
  openMenu(f);
  return [...(f.nativeElement as HTMLElement).querySelectorAll('[role="menuitem"]')]
    .map((b) => b.textContent!.trim());
}

function clickItem(f: ComponentFixture<RowActions>, label: string): void {
  const button = [...(f.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('[role="menuitem"]')]
    .find((b) => b.textContent!.trim() === label)!;
  button.click();
  f.detectChanges();
}

describe('row actions menu (v85 D13)', () => {
  it('offers close only on an open position', () => {
    expect(items(mount({ row: row({ status: 'ACTIVE' }) }))).toContain('Close position');
    expect(items(mount({ row: row({ status: 'PARTIAL' }) }))).toContain('Close position');
    expect(items(mount({ row: row({ status: 'PENDING' }) }))).not.toContain('Close position');
  });

  it('offers cancel only on a plan that has not filled', () => {
    expect(items(mount({ row: row({ status: 'PENDING' }) }))).toContain('Cancel plan');
    expect(items(mount({ row: row({ status: 'ACTIVE' }) }))).not.toContain('Cancel plan');
  });

  it('never offers delete, because the backend refuses it for plans', () => {
    for (const status of ['ACTIVE', 'PENDING', 'PARTIAL', 'CLOSED', 'CANCELLED']) {
      expect(items(mount({ row: row({ status }) })).join(' ')).not.toContain('Delete');
    }
  });

  it('always offers the note, whatever the status', () => {
    for (const status of ['ACTIVE', 'PENDING', 'CLOSED']) {
      expect(items(mount({ row: row({ status }) }))).toContain('Add note');
    }
  });

  it('posts a close and tells the page to refetch', () => {
    const f = mount({ row: row({ status: 'ACTIVE', id: 'p1' }) });
    let done = 0;
    f.componentInstance.done.subscribe(() => (done += 1));
    openMenu(f);
    clickItem(f, 'Close position');

    const req = httpMock.expectOne('/api/v1/trades/p1/close');
    expect(req.request.method).toBe('POST');
    req.flush({});
    expect(done).toBe(1);
  });
});
