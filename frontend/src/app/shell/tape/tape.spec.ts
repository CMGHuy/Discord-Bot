import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { LiveValuesStore } from '../../stores/live-values.store';
import { FakeLiveValues } from '../../testing/fake-live-values';
import { ConnectionStore } from '../../stores/connection.store';
import { TapeStore } from '../../stores/tape.store';
import { TAPE_PROXY_HINT, Tape } from './tape';

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
        { provide: LiveValuesStore, useClass: FakeLiveValues },
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

  it('explains proxy figures once, beside the lane caption, never inside a tile link (v194 A3)', () => {
    const el = setup([proxy], []).nativeElement as HTMLElement;
    expect(el.querySelector('.proxy')!.hasAttribute('title')).toBe(false);
    expect(el.querySelector('a sb-hint')).toBeNull();
    expect(el.querySelector('.cap-row sb-hint [role="tooltip"]')!.textContent!.trim()).toBe(TAPE_PROXY_HINT);
  });

  it('shows no proxy hint when no tile is a proxy', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.querySelector('.cap-row sb-hint')).toBeNull();
  });

  it('tiles carry the price age through sb-market-value', () => {
    const asOf = new Date(Date.now() - 4 * 60_000).toISOString();
    const el = setup([{ ...index, price_as_of: asOf }], [{ ...stock, price_as_of: asOf }]).nativeElement as HTMLElement;
    const ages = [...el.querySelectorAll('.tile sb-market-value .mv-age')].map((n) => n.textContent?.trim());
    expect(ages).toContain('4 min ago');
    expect(el.querySelector('.tile sb-age-hint')).toBeNull();
  });

  it('a refreshing price shows the spinner, and one with no as-of shows no age', () => {
    const el = setup([{ ...index, price_refreshing: true }], []).nativeElement as HTMLElement;
    expect(el.querySelector('.tile sb-market-value sb-spinner')).not.toBeNull();
    expect(el.querySelector('.tile sb-market-value .mv-age')).toBeNull();
  });
});
