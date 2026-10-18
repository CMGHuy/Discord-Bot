import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';

import { EquityCandle, EquityCandlesResponse } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { EquityCandles } from './equity-candles';

// A real lightweight-charts chart is created; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();

function candle(t: string, overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t, o: 100, h: 120, l: 90, c: 110, change: 10, change_pct: 10,
           samples: 4, skipped: 0, approx: false, ...overrides };
}

function response(candles: EquityCandle[], overrides: Partial<EquityCandlesResponse> = {}): EquityCandlesResponse {
  return { tf: '1D', basis: 'mtm', currency_symbol: '€', candles,
           recording_since: '2026-10-20T13:35:00Z', as_of: '2026-10-21T14:35:00Z', ...overrides };
}

const MIXED = [
  candle('2026-10-16', { approx: true }),
  candle('2026-10-19', { approx: true, o: 110, c: 105, change: -5, change_pct: -4.55 }),
  candle('2026-10-20', { o: 105, c: 112, change: 7, change_pct: 6.67, skipped: 2 }),
];

function render(data: EquityCandlesResponse | null, error: string | null = null) {
  const stub = equityCandlesStoreStub(data);
  stub.error.set(error);
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: EquityCandlesStore, useValue: stub }],
  });
  const fixture = TestBed.createComponent(EquityCandles);
  fixture.componentRef.setInput('currency', '€');
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement, stub };
}

function readout(el: HTMLElement): string[] {
  return [...el.querySelectorAll('.readout .part')].map((p) => p.textContent!.trim());
}

describe('sb-equity-candles', () => {
  it('reads out the latest candle when nothing is hovered', () => {
    const { el } = render(response(MIXED));
    const parts = readout(el);
    expect(parts[0]).toBe('Oct 20, 2026');
    expect(parts).toContain('C 112.00');
    expect(parts).toContain('+7.00 €');
    expect(parts).toContain('+6.67% vs prev close');
    expect(parts).toContain('Open + closed');
    expect(parts).toContain('2 positions not counted');
  });

  it('explains the percentage in a tooltip', () => {
    const { el } = render(response(MIXED));
    const pctPart = [...el.querySelectorAll('.readout .part')]
      .find((p) => p.textContent!.includes('vs prev close'))!;
    expect(pctPart.getAttribute('title'))
      .toBe("Change from the previous candle's close, not a return on capital");
  });

  it('follows the crosshair, and returns to the latest candle when it leaves', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['onCrosshair']({ logical: 1 });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Oct 19, 2026');
    expect(readout(el)).toContain('approx');

    fixture.componentInstance['onCrosshair']({ logical: undefined });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Oct 20, 2026');
  });

  it('draws rebuilt candles hollow, with the outer-bounds caption and the seam', () => {
    const { fixture, el } = render(response(MIXED));
    // jsdom lays the chart out at 0px, so whatever range it reports is not a
    // real viewport: clear it, as before the first range event.
    fixture.componentInstance['visible'].set(null);
    fixture.detectChanges();
    const data = fixture.componentInstance['seriesData']();
    expect(data[0].color).toBe('transparent');
    expect(data[1].color).toBe('transparent');
    expect(data[2].color).toBeUndefined();
    expect(el.querySelector('.caption')?.textContent?.trim())
      .toBe('Before Oct 20, 2026: rebuilt from daily bars — ranges are outer bounds');
    const seam = fixture.componentInstance['seam']?.current();
    expect(seam?.label).toBe('Recording started');
    expect(seam?.time).toBe('2026-10-20');
  });

  it('hides the caption once the rebuilt candles scroll out of view', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['visible'].set({ from: 2, to: 2 });
    fixture.detectChanges();
    expect(el.querySelector('.caption')).toBeNull();
  });

  it('shows no caption and no seam when every candle was recorded', () => {
    const { fixture, el } = render(response([candle('2026-10-20'), candle('2026-10-21')]));
    expect(el.querySelector('.caption')).toBeNull();
    expect(fixture.componentInstance['seam']?.current()).toBeNull();
  });

  it('shows the hourly empty state with the recording date, never an empty axis', () => {
    const { fixture, el } = render(response([], { tf: '1H' }));
    expect(fixture.componentInstance['state']()).toBe('empty');
    expect(el.querySelector('sb-async')?.textContent)
      .toContain('No hourly samples yet — recording started Oct 20, 2026');
    expect(el.querySelector('.chart')?.classList.contains('hidden')).toBe(true);
  });

  it('shows the loading skeleton before the first answer', () => {
    const { fixture, el } = render(null);
    expect(fixture.componentInstance['state']()).toBe('loading');
    expect(el.querySelector('sb-async')?.getAttribute('aria-busy')).toBe('true');
  });

  it('offers a retry on error that reloads the store', () => {
    const { el, stub } = render(null, 'Equity candles could not be loaded.');
    const retry = [...el.querySelectorAll('button')].find((b) => b.textContent!.trim() === 'Retry')!;
    retry.click();
    expect(stub.calls.load).toBe(1);
  });

  it('always states what the account is', () => {
    const { el } = render(response(MIXED));
    expect(el.querySelector('.account')?.textContent?.trim())
      .toBe('Paper account · before tax and costs');
  });

  it('uses the currency it is given, not the API symbol', () => {
    const { fixture, el } = render(response(MIXED, { currency_symbol: '$' }));
    fixture.componentRef.setInput('currency', '£');
    fixture.detectChanges();
    expect(readout(el)).toContain('+7.00 £');
  });
});
