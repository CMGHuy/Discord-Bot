import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { By } from '@angular/platform-browser';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { TradeRow } from '../../api/models';
import { ConnectionStore } from '../../stores/connection.store';
import { CLOCK } from '../../ui/clock';
import { RowActions } from './row-actions';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { provideMotion } from '../../ui/motion/motion.service';
import { PAPER_MARKER, TradeDrawer, drawerPnl, tradeDrawerFields } from './trade-drawer';

const NOW = Date.parse('2026-10-20T12:00:00Z');

function tradeRow(overrides: Partial<TradeRow> = {}): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'ACTIVE', ticker: 'AAPL',
    direction: 'bullish', strategy: 'RSI', horizon: '2w', tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 100, stop_loss: 95, target: 110, target2: 120,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: 2, shares: 10, open_shares: 10, position_value: 1000,
    current_price: 105, current_price_stale: false, exit_price: null, realized_pnl_amount: null,
    pnl_pct: null, r_multiple: null, held_hours: null, opened_at: '2026-10-19T12:00:00Z', closed_at: null,
    has_note: false, today: false, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'Open', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  } as TradeRow;
}

describe('tradeDrawerFields (v179 §3.2)', () => {
  it('lists the summary in reading order', () => {
    expect(tradeDrawerFields(tradeRow(), '€', NOW).map((f) => f.key)).toEqual([
      'direction', 'status', 'pnl', 'entry', 'stop', 'tp1', 'tp2', 'rr', 'opened', 'held', 'strategy', 'horizon',
    ]);
  });

  it('shows the live P&L of an open position as a percentage and an amount', () => {
    expect(drawerPnl(tradeRow())).toEqual({ pct: 5, amount: 50 });
    const pnl = tradeDrawerFields(tradeRow(), '€', NOW).find((f) => f.key === 'pnl')!;
    expect(pnl.value).toBe('+5.00% (+50.00 €)');
    expect(pnl.tone).toBe('pos');
    expect(pnl.numeric).toBe(true);
  });

  it('shows the realised P&L of a closed leg, signed and toned by its sign', () => {
    const row = tradeRow({ status: 'CLOSED', pnl_pct: -4, realized_pnl_amount: -40, current_price: null });
    const pnl = tradeDrawerFields(row, '€', NOW).find((f) => f.key === 'pnl')!;
    expect(pnl.value).toBe('-4.00% (-40.00 €)');
    expect(pnl.tone).toBe('neg');
  });

  it('labels the level a pending plan waits on as its trigger', () => {
    const row = tradeRow({ status: 'PENDING', entry: null, trigger_price: 101, open_shares: null, opened_at: null });
    const fields = tradeDrawerFields(row, '€', NOW);
    expect(fields.find((f) => f.key === 'trigger')).toMatchObject({ label: 'Trigger', value: '101.00', numeric: true });
    expect(fields.find((f) => f.key === 'entry')).toBeUndefined();
  });

  it('measures held time from the open while the server has not computed it', () => {
    const held = tradeDrawerFields(tradeRow(), '€', NOW).find((f) => f.key === 'held')!;
    expect(held.value).toBe('1d 0h 0m');
    const closed = tradeRow({ status: 'CLOSED', held_hours: 2.5, pnl_pct: 1, realized_pnl_amount: 10 });
    expect(tradeDrawerFields(closed, '€', NOW).find((f) => f.key === 'held')!.value).toBe('2h 30m');
  });

  it('renders every absent value as an em dash, never NaN or undefined', () => {
    const bare = tradeRow({
      direction: '', status_label: '', strategy: null, horizon: null, entry: null, trigger_price: null,
      stop_loss: null, target: null, target2: null, risk_reward: null, current_price: null,
      open_shares: null, opened_at: null, held_hours: null,
    });
    for (const field of tradeDrawerFields(bare, '€', NOW)) {
      expect(field.value, field.key).not.toMatch(/NaN|undefined|null/);
      expect(field.value.trim(), field.key).not.toBe('');
    }
    expect(tradeDrawerFields(bare, '€', NOW).find((f) => f.key === 'pnl')!.value).toBe('—');
  });
});

describe('sb-trade-drawer (v179 §3.2)', () => {
  let fixture: ComponentFixture<TradeDrawer>;

  beforeEach(() => {
    installDialogPolyfill();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        provideMotion('off'),
        { provide: CLOCK, useValue: signal(NOW) },
        { provide: ConnectionStore, useValue: { currency: signal('€') } },
      ],
    });
  });

  function mount(row: TradeRow = tradeRow()): HTMLElement {
    fixture = TestBed.createComponent(TradeDrawer);
    fixture.componentRef.setInput('row', row);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('opens a drawer headed by the ticker, marked as a paper trade', () => {
    const el = mount();
    const dialog = el.querySelector<HTMLDialogElement>('sb-drawer dialog')!;
    expect(dialog.open).toBe(true);
    expect(el.querySelector('sb-drawer header h2')!.textContent!.trim()).toBe('AAPL');
    const marker = el.querySelector('sb-drawer header .paper-marker')!;
    expect(marker.textContent!.trim()).toBe(PAPER_MARKER);
    expect(PAPER_MARKER).toBe('Paper trade');
  });

  it('renders each field as a label/value pair, numbers in the numeric face', () => {
    const el = mount();
    const rows = [...el.querySelectorAll('dl.fields > div.field')];
    expect(rows.map((r) => r.getAttribute('data-field'))).toContain('pnl');
    const stop = el.querySelector('[data-field="stop"]')!;
    expect(stop.querySelector('dt')!.textContent!.trim()).toBe('Stop');
    expect(stop.querySelector('dd')!.textContent!.trim()).toBe('95.00');
    expect(stop.querySelector('dd')!.classList).toContain('num');
    expect(el.querySelector('[data-field="strategy"] dd')!.classList).not.toContain('num');
    expect(el.querySelector('[data-field="pnl"] dd')!.classList).toContain('pos');
  });

  it('offers the row actions and the full trade page', () => {
    const el = mount();
    expect(el.querySelector('.drawer-actions sb-row-actions')).not.toBeNull();
    const link = el.querySelector<HTMLAnchorElement>('.drawer-actions a.full-trade')!;
    expect(link.textContent!.trim()).toBe('Open full trade →');
    expect(link.getAttribute('href')).toBe('/trades/t1');
    expect(link.classList).toContain('sb-hit');
  });

  it('summarises the loaded row without requesting data', () => {
    mount();
    TestBed.inject(HttpTestingController).expectNone(() => true);
  });

  it('forwards completion from the existing row actions', () => {
    mount();
    let completed = 0;
    fixture.componentInstance.actionDone.subscribe(() => (completed += 1));
    fixture.debugElement.query(By.directive(RowActions)).componentInstance.done.emit();
    expect(completed).toBe(1);
  });

  it('reports the close the drawer makes', () => {
    const el = mount();
    let closed = 0;
    fixture.componentInstance.closed.subscribe(() => (closed += 1));
    el.querySelector<HTMLButtonElement>('sb-drawer .close')!.click();
    fixture.detectChanges();
    expect(closed).toBe(1);
  });

  it('aligns each field and the action line on the text baseline', () => {
    const css = readFileSync(join(process.cwd(), 'src/app/workspaces/dashboard/trade-drawer.ts'), 'utf8');
    expect(css).toMatch(/\.field \{[^}]*align-items: baseline/);
    expect(css).toMatch(/\.drawer-actions \{[^}]*align-items: baseline/);
    // No workspace media query (spec §4 anti-goal): the drawer's phone,
    // tablet and desktop geometry is sb-drawer's own.
    expect(css).not.toMatch(/@media/);
  });
});
