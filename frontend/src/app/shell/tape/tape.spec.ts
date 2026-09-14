import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { TapeStore } from '../../stores/tape.store';
import { Tape } from './tape';

describe('Tape', () => {
  function setup(
    indexRows: unknown[],
    stockRows: unknown[],
    asOf: string | null = '2026-09-09T14:35:00+00:00',
  ) {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: MarketIndexStore, useValue: { rows: () => indexRows, asOf: () => null, load: () => undefined } },
        { provide: TapeStore, useValue: {
          rows: () => stockRows, asOf: () => asOf,
          visible: () => stockRows.length > 0, load: () => undefined,
        } },
      ],
    });
    const fixture = TestBed.createComponent(Tape);
    fixture.detectChanges();
    return fixture;
  }

  const index = { symbol: '^GSPC', price: 6500, change_pct: 0.5 };
  const stock = { symbol: 'NVDA', price: 1, change_pct: 1, context_kind: null, context_label: null, sort_rank: 2 };

  it('lists the market indices before any watchlist symbol', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    const symbols = [...el.querySelectorAll('.tile .sym')].map((n) => n.textContent);
    expect(symbols[0]).toBe('S&P 500');
    expect(symbols).toContain('NVDA');
    expect(symbols.indexOf('S&P 500')).toBeLessThan(symbols.indexOf('NVDA'));
  });

  it('renders the track twice so the loop is seamless', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    // One pass renders 2 tiles (1 index + 1 stock); doubled is 4.
    expect(el.querySelectorAll('.tile').length).toBe(4);
  });

  it('never shows the word "live" -- only the as-of clock', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.textContent?.toLowerCase()).not.toContain('live');
  });

  it('still shows the indices when nothing is flagged', () => {
    const el = setup([index], []).nativeElement as HTMLElement;
    expect(el.textContent).toContain('S&P 500');
  });

  it('keeps the as-of badge outside the animated track', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    const badge = el.querySelector('.as-of')!;
    expect(badge.closest('.track')).toBeNull();
  });

  it('shows a placeholder rather than dropping an unpriced symbol', () => {
    const el = setup([index], [{ ...stock, symbol: 'ZZZZ', price: null, change_pct: null }])
      .nativeElement as HTMLElement;
    expect(el.textContent).toContain('ZZZZ');
    expect(el.textContent).toContain('no price');
  });
});
