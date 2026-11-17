import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { CalendarTrade, SparkSeries } from '../../../api/models';
import { ConnectionStore } from '../../../stores/connection.store';
import { R_TOOLTIP } from './day-copy';
import { DayTradeCard, heldLabel, rowIsEstimate, tradeLinkId } from './day-trade-card';
import { LEG_HINT_TEXT, legLabel } from '../../trades/leg-label';

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
    // The shared helper appends a calendar row's exit reason (v194 B3).
    expect(legLabel({ ...TRADE, leg_index: 1, leg_total: 3 })).toBe('Leg 2 of 3 · TP1');
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

  it.each([
    ['daily', 5.5, true],
    ['daily', 47.9, true],
    ['daily', 48, false],
    ['daily', 53.5, false],
    ['daily', null, true],          // unknown hold on daily bars counts as short (V228-9)
    ['5min', 5.5, false],
    ['hourly', 30, false],
    [null, 5.5, false],
    [undefined, 5.5, false],        // a server older than v228 sends no field
  ] as const)('rowIsEstimate: source %s held %s h -> %s', (source, hours, expected) => {
    expect(rowIsEstimate({ ...TRADE, excursion_source: source, held_hours: hours })).toBe(expected);
  });

  it('never marks a row that shows no excursion figure', () => {
    expect(rowIsEstimate({ ...TRADE, excursion_source: 'daily', held_hours: 3, mfe_r: null, mae_r: null }))
      .toBe(false);
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
    expect(el.querySelector('.r')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('.r + sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(R_TOOLTIP);
  });

  it('lists the recorded prices, calling the stop the final stop', async () => {
    const el = await render(TRADE);
    expect(text(el, '.prices')).toBe(
      'Entry 100.00 · Exit 110.00 · Final stop 95.00 · TP1 120.00 · TP2 —',
    );
  });

  it('shows held time, shares and MFE/MAE', async () => {
    const el = await render(TRADE);
    expect(text(el, '.stats')).toBe('Held 2d 5h 30m · Shares 10 · MFE +2.40R · MAE −0.30R');
    const leg = await render({ ...TRADE, shares: 3.3333, leg_index: 1, leg_total: 3 });
    expect(text(leg, '.stats')).toContain('Shares 3.33');
    expect(text(leg, '.leg .name')).toBe('Leg 2 of 3');
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

  it('puts the marker inside the MFE · MAE line for a short hold on daily bars', async () => {
    const el = await render({ ...TRADE, excursion_source: 'daily', held_hours: 5.5 });
    const marker = el.querySelector('.stats sb-excursion-est');
    expect(marker).not.toBeNull();
    expect(marker!.querySelector('.est')?.textContent?.trim()).toBe('est. (daily bars)');
    // The line still reads in order; the marker follows MAE.
    expect(text(el, '.stats')).toMatch(/^Held 5h 30m · Shares 10 · MFE \+2\.40R · MAE −0\.30R ?est\. \(daily bars\)/);
    // Its explanation is a hint reachable by tap and keyboard.
    expect(el.querySelector('.stats sb-excursion-est sb-hint button')?.getAttribute('aria-label'))
      .toBe('About this estimate');
  });

  it('marks a daily row whose held time is unknown', async () => {
    const el = await render({ ...TRADE, excursion_source: 'daily', held_hours: null });
    expect(el.querySelector('.stats sb-excursion-est')).not.toBeNull();
  });

  it('leaves the line unmarked on intraday bars or a hold of two days or more', async () => {
    const intraday = await render({ ...TRADE, excursion_source: '5min', held_hours: 5.5 });
    expect(intraday.querySelector('sb-excursion-est')).toBeNull();
    expect(text(intraday, '.stats')).toBe('Held 5h 30m · Shares 10 · MFE +2.40R · MAE −0.30R');
    const long = await render({ ...TRADE, excursion_source: 'daily', held_hours: 53.5 });
    expect(long.querySelector('sb-excursion-est')).toBeNull();
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

describe('DayTradeCard leg label (v194 B3)', () => {
  function card(trade: CalendarTrade): HTMLElement {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: ConnectionStore, useValue: { currency: () => '€' } },
      ],
    });
    const fixture = TestBed.createComponent(DayTradeCard);
    fixture.componentRef.setInput('trade', trade);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('names the leg once, leaving the reason to the chip beside it', () => {
    const el = card({ ...TRADE, leg_index: 1, leg_total: 2 });
    expect(el.querySelector('.leg .name')!.textContent!.trim()).toBe('Leg 2 of 2');
  });

  it('explains the leg in a tooltip on its name, saying how this page counts legs (A4 audit)', () => {
    const el = card({ ...TRADE, leg_index: 0, leg_total: 2 });
    expect(el.querySelector('.leg button')).toBeNull();   // no separate info icon
    const tip = el.querySelector('.leg [role="tooltip"]')!.textContent!;
    expect(tip).toContain('Leg 1 of 2 is the first part of the plan to close');
    expect(tip).toContain(LEG_HINT_TEXT);
    expect(tip).toContain('count each realised leg as its own trade');
  });

  it('shows neither label nor leg tooltip for a trade that never scaled out', () => {
    const el = card(TRADE);
    expect(el.querySelector('.leg')).toBeNull();
    expect(el.querySelector('sb-leg-name')).toBeNull();
  });
});
