import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { LiveValuesStore } from '../../stores/live-values.store';
import { FakeLiveValues } from '../../testing/fake-live-values';
import { ConnectionStore } from '../../stores/connection.store';
import { TapeStore } from '../../stores/tape.store';
import { TapeFeed } from '../../stores/tape-feed';
import { TAPE_PROXY_HINT, Tape, shockSummary } from './tape';

describe('Tape', () => {
  function setup(
    indexRows: unknown[],
    stockRows: unknown[],
    asOf: string | null = '2026-09-09T14:35:00+00:00',
    shock: unknown = null,
  ) {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([]),
        { provide: LiveValuesStore, useClass: FakeLiveValues },
        { provide: ConnectionStore, useValue: { marketActive: () => true } },
        { provide: MarketIndexStore, useValue: { rows: () => indexRows, asOf: () => null, load: () => undefined } },
        { provide: TapeFeed, useValue: { shock: () => shock } },
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

  it('declares its viewport a marquee so edge-crossing tiles are not audited as clipped', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    const viewport = el.querySelector('.viewport');
    expect(viewport?.hasAttribute('data-marquee')).toBe(true);
    expect(viewport?.querySelectorAll('.tile').length).toBe(4);
  });

  it('gives every tile the 44px touch hit area, while the strip stays compact', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    const tiles = [...el.querySelectorAll('.tile')];
    expect(tiles.length).toBe(4);
    expect(tiles.every((tile) => tile.classList.contains('sb-hit'))).toBe(true);
  });

  it('marks no tile and keeps the marquee when both sources are empty', () => {
    const el = setup([], []).nativeElement as HTMLElement;
    expect(el.querySelectorAll('.tile').length).toBe(0);
    expect(el.querySelector('.viewport')?.hasAttribute('data-marquee')).toBe(true);
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

  const shockState = {
    label: 'SHOCK', since: '2026-11-05T14:45:00+00:00', as_of: '2026-11-05T15:00:00+00:00',
    breadth_pct: 42, sectors_down: 5, sectors_total: 8, spy_atr_move: -1.8, qqq_atr_move: -2.3,
    vix_level: 21.13, vix_chg_pct: 27.2, vix_missing: false,
  };

  it('shows no badge without a shock object (detector off)', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.querySelector('.shock-badge')).toBeNull();
  });

  it.each(['NORMAL', 'SHOCK', 'RECOVERY'])('labels the badge %s', (label) => {
    const el = setup([index], [stock], undefined, { ...shockState, label }).nativeElement as HTMLElement;
    const badge = el.querySelector('.shock-badge')!;
    expect(badge.getAttribute('data-label')).toBe(label);
    expect(badge.querySelector('.shock-label')!.textContent!.trim()).toBe(label);
    expect(badge.textContent).not.toContain('VIX missing');
  });

  it('says VIX missing when the reading has no VIX', () => {
    const missing = { ...shockState, vix_level: null, vix_chg_pct: null, vix_missing: true };
    const el = setup([index], [], undefined, missing).nativeElement as HTMLElement;
    expect(el.querySelector('.shock-badge .shock-vix')!.textContent!.trim()).toBe('VIX missing');
  });

  it('sits after the tape lane, never inside its clipped viewport', () => {
    const el = setup([index], [stock], undefined, shockState).nativeElement as HTMLElement;
    expect(el.querySelector('.lane .shock-badge')).toBeNull();
    expect(el.querySelector('.lane')!.nextElementSibling!.classList).toContain('shock-badge');
    expect(el.querySelectorAll('.cap-row').length).toBe(1);
    expect(el.textContent!.toLowerCase()).not.toContain('live');
  });

  it('carries the headline numbers in its title', () => {
    const el = setup([index], [stock], undefined, shockState).nativeElement as HTMLElement;
    expect(el.querySelector('.shock-badge')!.getAttribute('title')).toBe(
      'Market state SHOCK since 14:45 UTC · breadth 42% · sectors 5/8 · SPY -1.80 ATR · QQQ -2.30 ATR · VIX 21.13 (+27.2%)');
  });

  it('summarises a reading with no numbers as n/a', () => {
    expect(shockSummary({
      label: 'NORMAL', since: null, as_of: null, breadth_pct: null, sectors_down: null,
      sectors_total: null, spy_atr_move: null, qqq_atr_move: null, vix_level: null,
      vix_chg_pct: null, vix_missing: true,
    })).toBe('Market state NORMAL · breadth n/a · sectors n/a · SPY n/a · QQQ n/a · VIX missing');
  });
});
