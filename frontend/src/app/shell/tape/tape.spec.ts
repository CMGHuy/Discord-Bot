import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { ConnectionStore } from '../../stores/connection.store';
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
        { provide: ConnectionStore, useValue: { marketActive: () => true } },
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

  it('never shows the word "live" ', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.textContent?.toLowerCase()).not.toContain('live');
  });

  it('still shows the indices when nothing is flagged', () => {
    const el = setup([index], []).nativeElement as HTMLElement;
    expect(el.textContent).toContain('S&P 500');
  });

  it('carries the as-of time in a tooltip, not as visible text', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.querySelector('.as-of')).toBeNull();
    expect(el.querySelector('.lane')!.getAttribute('title')).toContain('as of');
  });

  it('shows a placeholder rather than dropping an unpriced symbol', () => {
    const el = setup([index], [{ ...stock, symbol: 'ZZZZ', price: null, change_pct: null }])
      .nativeElement as HTMLElement;
    expect(el.textContent).toContain('ZZZZ');
    expect(el.textContent).toContain('no price');
  });

  const proxy = { symbol: '^GSPC', price: null, change_pct: 0.42, is_proxy: true, proxy_symbol: 'SPY', age_s: 20 };

  it('labels a proxy row and shows its change only, never a level (v171 D7)', () => {
    const el = setup([proxy], []).nativeElement as HTMLElement;
    const tile = el.querySelector('.tile')!;
    expect(tile.querySelector('.sym')?.textContent).toBe('S&P 500');
    expect(tile.querySelector('.ctx.proxy')?.textContent?.trim()).toBe('SPY proxy');
    expect(tile.textContent).toContain('+0.42%');
    expect(tile.querySelector('.px')).toBeNull();
    expect(tile.textContent).not.toContain('no price');
  });

  it('shows the age of a value older than the tape window', () => {
    const el = setup([{ ...index, age_s: 240 }], []).nativeElement as HTMLElement;
    expect(el.querySelector('.tile .age-hint')?.textContent?.trim()).toBe('4 min ago');
  });

  it('shows no age inside the window, nor when the server sends none (flag off)', () => {
    expect((setup([{ ...index, age_s: 30 }], []).nativeElement as HTMLElement).querySelector('.age-hint')).toBeNull();
    TestBed.resetTestingModule();
    expect((setup([index], []).nativeElement as HTMLElement).querySelector('.age-hint')).toBeNull();
  });
});
