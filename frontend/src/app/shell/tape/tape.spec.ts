import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { MarketIndexStore } from '../../stores/market-index.store';
import { TapeStore } from '../../stores/tape.store';
import { afterEach, vi } from 'vitest';
import { Tape } from './tape';
import { TAPE_PAGE_SECONDS } from './tape-pages';

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

  it('renders each tile once: the strip pages, it no longer scrolls a doubled track', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.querySelectorAll('.tile').length).toBe(2);
    expect(el.querySelector('[aria-hidden="true"].tile')).toBeNull();
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

  describe('pages of whole tiles (v179 layout audit)', () => {
    const stocks = ['NVDA', 'AMD', 'MSFT', 'TSLA'].map((symbol) => ({ ...stock, symbol }));
    let restore: (() => void)[] = [];

    /** jsdom has no layout: give every tile 100px and the viewport 250px, so two tiles fit. */
    function fakeLayout(tileWidth: number, laneWidth: number) {
      const tile = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetWidth');
      const lane = Object.getOwnPropertyDescriptor(Element.prototype, 'clientWidth');
      Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
        configurable: true, get() { return (this as HTMLElement).classList.contains('tile') ? tileWidth : 0; },
      });
      Object.defineProperty(Element.prototype, 'clientWidth', {
        configurable: true, get() { return (this as HTMLElement).classList.contains('viewport') ? laneWidth : 0; },
      });
      restore.push(() => {
        if (tile) Object.defineProperty(HTMLElement.prototype, 'offsetWidth', tile);
        if (lane) Object.defineProperty(Element.prototype, 'clientWidth', lane);
      });
    }

    afterEach(() => {
      restore.forEach((undo) => undo());
      restore = [];
      vi.useRealTimers();
    });

    const shown = (el: HTMLElement) => [...el.querySelectorAll('.tile:not(.off) .sym')].map((n) => n.textContent);

    it('shows only the tiles that fit whole, the rest are off the strip but still in the DOM', async () => {
      fakeLayout(100, 250);
      const fixture = setup([index], stocks);
      await fixture.whenStable();
      fixture.detectChanges();
      const el = fixture.nativeElement as HTMLElement;
      expect(shown(el)).toEqual(['S&P 500', 'NVDA']);
      expect(el.querySelectorAll('.tile').length).toBe(5);
      expect(el.querySelector('.tile.off')!.getAttribute('tabindex')).toBe('-1');
    });

    it('turns to the next page on a timer so every symbol is reached, and wraps round', async () => {
      vi.useFakeTimers();
      fakeLayout(100, 250);
      const fixture = setup([index], stocks);
      await fixture.whenStable();
      fixture.detectChanges();
      const el = fixture.nativeElement as HTMLElement;
      vi.advanceTimersByTime(TAPE_PAGE_SECONDS * 1000);
      fixture.detectChanges();
      expect(shown(el)).toEqual(['AMD', 'MSFT']);
      vi.advanceTimersByTime(TAPE_PAGE_SECONDS * 1000);
      fixture.detectChanges();
      expect(shown(el)).toEqual(['TSLA']);
      vi.advanceTimersByTime(TAPE_PAGE_SECONDS * 1000);
      fixture.detectChanges();
      expect(shown(el)).toEqual(['S&P 500', 'NVDA']);
    });

    it('hides the strip when not even one whole tile fits the lane, instead of showing a sliver (768px leaves ~60px)', async () => {
      fakeLayout(195, 60);
      const fixture = setup([index], stocks);
      await fixture.whenStable();
      fixture.detectChanges();
      const el = fixture.nativeElement as HTMLElement;
      expect(el.querySelector('.lane')!.classList).toContain('nothing-fits');
      expect(shown(el)).toEqual([]);
    });

    it('keeps the strip showing while the tiles fit', async () => {
      fakeLayout(100, 250);
      const fixture = setup([index], stocks);
      await fixture.whenStable();
      fixture.detectChanges();
      expect((fixture.nativeElement as HTMLElement).querySelector('.lane')!.classList).not.toContain('nothing-fits');
    });

    it('holds the page while the pointer is over the strip', async () => {
      vi.useFakeTimers();
      fakeLayout(100, 250);
      const fixture = setup([index], stocks);
      await fixture.whenStable();
      fixture.detectChanges();
      const el = fixture.nativeElement as HTMLElement;
      el.querySelector('.viewport')!.dispatchEvent(new Event('mouseenter'));
      vi.advanceTimersByTime(TAPE_PAGE_SECONDS * 3000);
      fixture.detectChanges();
      expect(shown(el)).toEqual(['S&P 500', 'NVDA']);
    });
  });
});

describe('tape.css: nothing is cut at the lane edge (v179 layout audit)', () => {
  const css = readFileSync(join(process.cwd(), 'src/app/shell/tape/tape.css'), 'utf8');
  const rule = (selector: string) => css.match(
    new RegExp(`^${selector.replaceAll('.', '\\.')} \\{[^}]*\\}`, 'm'),
  )?.[0] ?? '';

  it('has no sliding marquee: no animation on the track', () => {
    expect(css).not.toMatch(/animation-name|@keyframes|sb-tape-slide/);
  });

  it('hides a lane too narrow for one whole tile, keeping its layout so it can be measured again on resize', () => {
    expect(rule('.lane.nothing-fits')).toMatch(/visibility:\s*hidden/);
  });

  it('takes an off-page tile out of flow and out of sight (and out of reach) without changing its width', () => {
    const off = rule('.tile.off');
    expect(off).toMatch(/position:\s*absolute/);
    expect(off).toMatch(/visibility:\s*hidden/);
  });

  it('gives a tile a 44px hit area on touch widths: the lane is as tall as the control', () => {
    expect(css).toMatch(/\.lane\s*\{[^}]*height:\s*max\(32px,\s*var\(--control-h\)\)/s);
    const tape = readFileSync(join(process.cwd(), 'src/app/shell/tape/tape.ts'), 'utf8');
    expect(tape).toMatch(/class="tile sb-hit"/);
  });
});
