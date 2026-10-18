import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { CalendarTrade, SparkSeries } from '../../../api/models';
import { ConnectionStore } from '../../../stores/connection.store';
import { R_TOOLTIP } from './day-copy';
import { DayTradeCard, heldLabel, legLabel, tradeLinkId } from './day-trade-card';

const TRADE: CalendarTrade = {
  trade_id: 'a'.repeat(16),
  ticker: 'AAPL',
  strategy: 'EMA20',
  horizon: '4w',
  direction: 'bullish',
  day: '2026-08-03',
  closed_at: '2026-08-03T20:00:00+00:00',
  outcome: 'win',
  pnl_amount: 50,
  r_multiple: 2,
  mfe_r: 2.4,
  mae_r: -0.3,
  exit_efficiency: 83,
  tags: ['clean-exit'],
  auto_lesson: 'Held to target.',
  plan_id: 'PLAN-9',
  opened_at: '2026-08-01T14:30:00+00:00',
  leg_index: 0,
  leg_total: 1,
  entry_price: 100,
  exit_price: 110,
  stop_price: 95,
  tp1: 120,
  tp2: null,
  shares: 10,
  held_hours: 53.5,
  return_pct: 10,
  exit_reason: 'tp1',
};

const SERIES: SparkSeries = {
  closes: [{ date: '2026-08-01', close: 100 }, { date: '2026-08-03', close: 110 }],
  exit_bar: 1, last_bar: '2026-08-28', stale: false,
  entry: 100, stop: 95, tp1: 120, tp2: null, exit: 110, exit_date: '2026-08-03',
};

describe('day-trade-card helpers', () => {
  it('labels a leg 1-based and a whole trade not at all', () => {
    expect(legLabel(TRADE)).toBeNull();
    expect(legLabel({ ...TRADE, leg_index: 1, leg_total: 3 })).toBe('Leg 2 of 3');
  });

  it('formats held time, with a dash for none', () => {
    expect(heldLabel(53.5)).toBe('2d 5h 30m');
    expect(heldLabel(5.25)).toBe('5h 15m');
    expect(heldLabel(null)).toBe('—');
  });

  it('links to the plan when there is one, else the trade', () => {
    expect(tradeLinkId(TRADE)).toBe('PLAN-9');
    expect(tradeLinkId({ ...TRADE, plan_id: null })).toBe('a'.repeat(16));
  });
});

describe('DayTradeCard', () => {
  let fixture: ComponentFixture<DayTradeCard>;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: ConnectionStore, useValue: { currency: () => '€' } },
      ],
    });
    fixture = TestBed.createComponent(DayTradeCard);
  });

  const render = async (
    trade: CalendarTrade,
    series: SparkSeries | null | undefined = undefined,
  ): Promise<HTMLElement> => {
    fixture.componentRef.setInput('trade', trade);
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };
  const text = (el: HTMLElement, selector: string) =>
    el.querySelector(selector)?.textContent?.replace(/\s+/g, ' ').trim();

  it('shows who, how and how much in the header', async () => {
    const el = await render(TRADE);
    expect(text(el, '.ticker')).toBe('AAPL');
    expect(text(el, '.direction')).toBe('Long');
    expect(text(el, '.setup')).toBe('EMA20 · 4w');
    expect(text(el, 'sb-chip')).toBe('tp1');
    expect(text(el, '.pnl')).toBe('+50.00 €');
    expect(text(el, '.r')).toBe('+2.00R');
    expect(text(el, '.return')).toBe('+10.00%');
    expect(el.querySelector('.leg')).toBeNull();
  });

  it('tints only P&L and R, and explains R', async () => {
    const el = await render({ ...TRADE, pnl_amount: -20, r_multiple: -0.8, return_pct: -4 });
    expect(el.querySelector('.pnl')?.classList.contains('neg')).toBe(true);
    expect(el.querySelector('.r')?.classList.contains('neg')).toBe(true);
    expect(el.querySelector('.return')?.classList.contains('neg')).toBe(false);
    expect(el.querySelector('.r')?.getAttribute('title')).toBe(R_TOOLTIP);
  });

  it('lists the recorded prices, calling the stop the final stop', async () => {
    const el = await render(TRADE);
    expect(text(el, '.prices')).toBe(
      'Entry 100.00 · Exit 110.00 · Final stop 95.00 · TP1 120.00 · TP2 —',
    );
  });

  it('shows held time, shares and MFE/MAE', async () => {
    const el = await render(TRADE);
    expect(text(el, '.stats')).toBe('Held 2d 5h 30m · Shares 10 · MFE +2.40R · MAE -0.30R');
    const leg = await render({ ...TRADE, shares: 3.3333, leg_index: 1, leg_total: 3 });
    expect(text(leg, '.stats')).toContain('Shares 3.33');
    expect(text(leg, '.leg')).toBe('Leg 2 of 3');
  });

  it('renders every missing figure as a dash, never 0', async () => {
    const el = await render({
      ...TRADE, direction: null, pnl_amount: null, r_multiple: null, return_pct: null,
      entry_price: null, exit_price: null, stop_price: null, tp1: null, tp2: null,
      shares: null, held_hours: null, mfe_r: null, mae_r: null,
    });
    expect(text(el, '.direction')).toBe('—');
    expect(text(el, '.pnl')).toBe('—');
    expect(text(el, '.r')).toBe('—');
    expect(text(el, '.return')).toBe('—');
    expect(text(el, '.prices')).toBe('Entry — · Exit — · Final stop — · TP1 — · TP2 —');
    expect(text(el, '.stats')).toBe('Held — · Shares — · MFE — · MAE —');
    expect(el.textContent).not.toContain('0.00');
  });

  it('opens the trade, and the sparkline opens its chart', async () => {
    const el = await render(TRADE, SERIES);
    expect(el.querySelector('a.open')?.getAttribute('href')).toBe('/trades/PLAN-9');
    expect(text(el, 'a.open')).toBe('Open →');
    expect(el.querySelector('sb-trade-sparkline a.spark')?.getAttribute('href'))
      .toBe('/trades/PLAN-9?tab=chart');
    const orphan = await render({ ...TRADE, plan_id: null });
    expect(orphan.querySelector('a.open')?.getAttribute('href')).toBe('/trades/' + 'a'.repeat(16));
  });

  it('shows a dash where there is no sparkline', async () => {
    const el = await render(TRADE, null);
    expect(el.querySelector('sb-trade-sparkline .spark-empty')).not.toBeNull();
  });

  it('mutes an unmapped exit reason', async () => {
    const el = await render({ ...TRADE, exit_reason: 'other' });
    expect(el.querySelector('sb-chip .chip')?.classList.contains('muted')).toBe(true);
  });

  it('keeps the lesson and the tags', async () => {
    const el = await render(TRADE);
    expect(text(el, '.lesson')).toBe('Held to target.');
    expect(text(el, '.tags')).toBe('clean-exit');
  });
});
