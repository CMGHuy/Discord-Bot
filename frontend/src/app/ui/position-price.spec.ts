import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { MarketStatus } from '../api/models';
import { LiveValuesStore } from '../stores/live-values.store';
import { CLOCK } from './clock';
import { PREV_CLOSE_ARIA, NO_PRICE_REASON } from './position-format';
import { PositionFigure, PositionPrice, PositionPriceRow } from './position-price';
import type { PriceKind } from './position-progress';

const FIX = JSON.parse(readFileSync(join(process.cwd(), 'src/app/testing/fixtures/v248-worst-case-row.json'), 'utf8'));
const rowOf = (name: string, o: Record<string, unknown> = {}): PositionPriceRow =>
  ({ ...FIX.base, ...FIX.rows[name], ...o }) as PositionPriceRow;
const NOW = Date.parse(FIX.now);
const regular: MarketStatus = {
  session: 'regular',
  last_close_at: '2026-11-24T21:00:00Z',
  stale_price_s: 120,
  stale_snapshot_s: 600,
  heartbeat: { beat_at: null, cadence_s: 30, stalled: false },
} as MarketStatus;

function setup(status: MarketStatus): void {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: CLOCK, useValue: signal(NOW) },
      { provide: LiveValuesStore, useValue: { status: signal(status) } },
    ],
  });
}

function renderPrice(row: PositionPriceRow, status: MarketStatus = regular): HTMLElement {
  setup(status);
  const fixture = TestBed.createComponent(PositionPrice);
  fixture.componentRef.setInput('row', row);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

function renderFigure(value: number | null, unit: 'pct' | 'r', kind: PriceKind | null): HTMLElement {
  setup(regular);
  const fixture = TestBed.createComponent(PositionFigure);
  fixture.componentRef.setInput('value', value);
  fixture.componentRef.setInput('unit', unit);
  fixture.componentRef.setInput('kind', kind);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('PositionPrice', () => {
  it('a prev-close row shows its value, a dated prev close tag with an accessible name, and no age', () => {
    const el = renderPrice(rowOf('worst_case'));
    expect(el.querySelector('.pp-value')!.textContent!.trim()).toBe('1,234.56');
    const tag = el.querySelector('.pp-tag')!;
    expect(tag.textContent!.trim()).toBe('prev close 11-24');
    expect(tag.getAttribute('aria-label')).toBe(PREV_CLOSE_ARIA);
    expect(el.querySelector('.pp')!.getAttribute('title')).toBe('Previous close, 2026-11-24 -- not a live price');
    expect(el.querySelector('.mv-age')).toBeNull();
  });
  it('the worst case keeps its error in the regular session', () => {
    expect(renderPrice(rowOf('worst_case')).querySelector('.mv-err')?.textContent).toContain('refresh failed');
  });
  it('outside the regular session the same row shows no error', () => {
    const el = renderPrice(rowOf('worst_case'), { ...regular, session: 'extended' } as MarketStatus);
    expect(el.querySelector('.mv-err')).toBeNull();
    expect(el.querySelector('.pp-tag')).not.toBeNull();
  });
  it('a stale live row shows its price through sb-market-value with the error and no prev close tag', () => {
    const el = renderPrice(rowOf('stale_live'));
    expect(el.querySelector('sb-market-value')!.textContent).toContain('131.07');
    expect(el.querySelector('.mv-err')).not.toBeNull();
    expect(el.querySelector('.pp-tag')).toBeNull();
  });
  it('a fresh live row shows price and age only', () => {
    const asOf = new Date(NOW - 12_000).toISOString();
    const el = renderPrice(
      rowOf('stale_live', { price_as_of: asOf, price_error: null, price_error_at: null, current_price_stale: false }),
    );
    expect(el.querySelector('.mv-age')!.textContent!.trim()).toBe('12 s ago');
    expect(el.querySelector('.mv-err')).toBeNull();
  });
  it('a held row with no price at all says so and why, never a bare dash', () => {
    const el = renderPrice(rowOf('no_price'));
    expect(el.querySelector('.pp-none')!.textContent!.trim()).toBe('no price yet');
    expect(el.querySelector('.pp-reason')!.textContent!.trim()).toBe(NO_PRICE_REASON);
    expect(el.textContent).not.toContain('—');
  });
  it('a held row with no live price but a cached close keeps the dated last-close note', () => {
    const el = renderPrice(rowOf('no_price', { last_close: 36.86, last_close_date: '2026-11-09' }));
    expect(el.querySelector('.last-close')!.textContent).toContain('36.86');
    expect(el.querySelector('.last-close')!.textContent).toContain('close 11-09');
    expect(el.querySelector('.pp-none')).toBeNull();
  });
  it('a PENDING row with no price shows no no-price note', () => {
    expect(renderPrice(rowOf('no_price', { status: 'PENDING', price_error: null })).querySelector('.pp-none')).toBeNull();
  });
  it('holds nothing focusable, so a live update cannot move focus', () => {
    for (const name of ['worst_case', 'stale_live', 'no_price']) {
      TestBed.resetTestingModule();
      expect(renderPrice(rowOf(name)).querySelectorAll('button, a, [tabindex]').length).toBe(0);
    }
  });
});

describe('PositionFigure', () => {
  it('sb-position-figure renders the figure and a labelled suffix on prev close only', () => {
    const prev = renderFigure(-11.82, 'pct', 'prev_close');
    expect(prev.querySelector('.fig')!.textContent!.trim()).toBe('−11.82%');
    expect(prev.querySelector('.fig-suffix')!.textContent!.trim()).toBe('at prev close');
    expect(prev.querySelector('.fig-suffix')!.getAttribute('aria-label')).toBe(PREV_CLOSE_ARIA);
    TestBed.resetTestingModule();
    expect(renderFigure(1.38, 'r', 'live').querySelector('.fig-suffix')).toBeNull();
    TestBed.resetTestingModule();
    expect(renderFigure(null, 'r', 'prev_close').querySelector('.fig')!.textContent!.trim()).toBe('—');
  });
});
