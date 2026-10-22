import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EquityCandle, EquityCandlesResponse } from '../../../api/models';
import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { token } from '../../../ui/chart/chart-theme';
import { EquityCandles } from './equity-candles';

// A real lightweight-charts chart is created; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();

function candle(t: string, overrides: Partial<EquityCandle> = {}): EquityCandle {
  return { t, o: 100, h: 120, l: 90, c: 110, change: 10, change_pct: 10,
           samples: 4, skipped: 0, approx: false, ...overrides };
}

function response(candles: EquityCandle[], overrides: Partial<EquityCandlesResponse> = {}): EquityCandlesResponse {
  return { tf: '1D', basis: 'mtm', currency_symbol: '€', has_more: false, candles,
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

function tones(el: HTMLElement): (string | null)[] {
  return [...el.querySelectorAll('.readout .part')].map((p) => p.getAttribute('data-tone'));
}

function at(fixture: { componentInstance: EquityCandles; detectChanges(): void }, from: number, to: number) {
  fixture.componentInstance['onVisibleRange']({ from, to });
  fixture.detectChanges();
}

/** `count` hourly candles from 2026-10-01 00:00 New York (EDT all month). */
function hourlyCandles(count: number): EquityCandle[] {
  return Array.from({ length: count }, (_, i) => {
    const wall = new Date(Date.UTC(2026, 9, 1) + i * 3_600_000).toISOString().slice(0, 19);
    return candle(`${wall}-04:00`);
  });
}

function dailyCandles(count: number): EquityCandle[] {
  return Array.from({ length: count }, (_, i) =>
    candle(new Date(Date.UTC(2026, 8, 1) + i * 86_400_000).toISOString().slice(0, 10)));
}

type Scale = { fitContent(): void; setVisibleRange(range: unknown): void };
const scaleOf = (fixture: { componentInstance: EquityCandles }) =>
  (fixture.componentInstance as unknown as { chart: { timeScale(): Scale } }).chart.timeScale();

describe('sb-equity-candles', () => {
  it('reads out the hovered candle, its change toned by sign', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['onCrosshair']({ logical: 2 });
    fixture.detectChanges();
    const parts = readout(el);
    expect(parts[0]).toBe('Oct 20, 2026');
    expect(parts).toContain('C 112.00');
    expect(parts).toContain('+7.00 €');
    expect(parts).toContain('+6.67% vs prev close');
    expect(parts).toContain('Open + closed');
    expect(parts).toContain('2 positions not counted');
    expect(tones(el)[parts.indexOf('+7.00 €')]).toBe('pos');
    expect(tones(el)[parts.indexOf('C 112.00')]).toBe('neutral');
  });

  it('summarises the visible range when nothing is hovered', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 0, 2);
    expect(readout(el)).toEqual([
      'Equity change +12.00 € (+12.00%)', 'High 120.00', 'Low 90.00',
      'Max drawdown within range -4.55%',
    ]);
    expect(tones(el)).toEqual(['pos', 'neutral', 'neutral', 'neg']);
  });

  it('falls back to the latest candle with no buckets in view and clears the baseline', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 1, 2);
    expect(fixture.componentInstance['baseline']?.current()?.value).toBe(110);
    at(fixture, 10, 12);
    expect(readout(el)[0]).toBe('Oct 20, 2026');
    expect(readout(el)).toContain('C 112.00');
    expect(fixture.componentInstance['baseline']?.current()).toBeNull();
  });

  it('explains the percentage in a tooltip', () => {
    const { fixture, el } = render(response(MIXED));
    fixture.componentInstance['onCrosshair']({ logical: 2 });
    fixture.detectChanges();
    const pctPart = [...el.querySelectorAll('.readout .part')]
      .find((p) => p.textContent!.includes('vs prev close'))!;
    expect(pctPart.getAttribute('title'))
      .toBe("Change from the previous candle's close, not a return on capital");
  });

  it('follows the crosshair, and returns to the range summary when it leaves', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 0, 2);
    fixture.componentInstance['onCrosshair']({ logical: 1 });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Oct 19, 2026');
    expect(readout(el)).toContain('approx');
    expect(tones(el)[readout(el).indexOf('-5.00 €')]).toBe('neg');

    fixture.componentInstance['onCrosshair']({ logical: undefined });
    fixture.detectChanges();
    expect(readout(el)[0]).toBe('Equity change +12.00 € (+12.00%)');
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

  it('states what the account is, directly under the readout', () => {
    const { fixture, el } = render(response(MIXED));
    at(fixture, 0, 2);
    const account = el.querySelector('.readout')!.nextElementSibling;
    expect(account?.classList.contains('account')).toBe(true);
    expect(account?.textContent?.trim()).toBe('Paper account · before tax and costs');
    expect(el.querySelectorAll('.account').length).toBe(1);
  });

  it('uses the currency it is given, not the API symbol', () => {
    const { fixture, el } = render(response(MIXED, { currency_symbol: '$' }));
    fixture.componentRef.setInput('currency', '£');
    fixture.detectChanges();
    at(fixture, 0, 2);
    expect(readout(el)[0]).toContain('+12.00 £');
  });

  function buttons(el: HTMLElement, group: string): HTMLButtonElement[] {
    return [...el.querySelectorAll<HTMLButtonElement>(`[aria-label="${group}"] button`)];
  }

  it('offers the four timeframes with the stored one pressed', () => {
    const { el } = render(response(MIXED));
    const chips = buttons(el, 'Candle timeframe');
    expect(chips.map((b) => b.textContent!.trim())).toEqual(['1H', '4H', '1D', '1W']);
    expect(chips.find((b) => b.getAttribute('aria-pressed') === 'true')?.textContent?.trim()).toBe('1D');
  });

  it('switches timeframe through the store', () => {
    const { fixture, el, stub } = render(response(MIXED));
    buttons(el, 'Candle timeframe').find((b) => b.textContent!.trim() === '1W')!.click();
    fixture.detectChanges();
    expect(stub.calls.tf).toEqual(['1W']);
    expect(buttons(el, 'Candle timeframe').find((b) => b.getAttribute('aria-pressed') === 'true')
      ?.textContent?.trim()).toBe('1W');
  });

  it('offers the two bases by name and switches through the store', () => {
    const { fixture, el, stub } = render(response(MIXED));
    const toggle = buttons(el, 'Equity basis');
    expect(toggle.map((b) => b.textContent!.trim())).toEqual(['Open + closed', 'Closed trades only']);
    toggle[1].click();
    fixture.detectChanges();
    expect(stub.calls.basis).toEqual(['realized']);
  });

  it('keeps the controls when there is nothing to draw', () => {
    const { el } = render(response([], { tf: '1H' }));
    expect(buttons(el, 'Candle timeframe').length).toBe(4);
    expect(buttons(el, 'Equity basis').length).toBe(2);
  });

  it('fits the view once, only after the host has a width (first load)', () => {
    let notify: () => void = () => {};
    class FakeObserver {
      constructor(cb: () => void) { notify = cb; }
      observe(): void {}
      disconnect(): void {}
    }
    vi.stubGlobal('ResizeObserver', FakeObserver);
    let width = 0;
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
    try {
      const { fixture, stub } = render(response(MIXED));
      const fit = vi.spyOn(
        (fixture.componentInstance as unknown as { chart: { timeScale(): { fitContent(): void } } })
          .chart.timeScale(), 'fitContent');
      stub.data.set(response(MIXED));
      fixture.detectChanges();
      expect(fit).not.toHaveBeenCalled();
      width = 600;
      notify();
      notify();
      expect(fit).toHaveBeenCalledTimes(1);
    } finally {
      widthSpy.mockRestore();
      vi.unstubAllGlobals();
    }
  });
  it('draws the baseline at the first in-window open, washed pos above and neg below', () => {
    const { fixture } = render(response(MIXED));
    at(fixture, 1, 2);
    const base = fixture.componentInstance['baseline']?.current();
    expect(base?.value).toBe(110);
    expect(base?.above).toBe(token('--pos-soft'));
    expect(base?.below).toBe(token('--neg-soft'));
    expect(base?.line).toBe(token('--text-muted'));
  });

  it('asks for older history near the left edge, once, only while there is more', () => {
    const { fixture, stub } = render(response(MIXED));
    const loadOlder = vi.spyOn(stub, 'loadOlder');
    stub.hasMore.set(false);
    at(fixture, 1, 2);
    expect(loadOlder).not.toHaveBeenCalled();

    stub.hasMore.set(true);
    at(fixture, 1, 2);
    expect(loadOlder).toHaveBeenCalledTimes(1);

    stub.pageLoading.set(true);
    at(fixture, 0, 2);
    expect(loadOlder).toHaveBeenCalledTimes(1);
  });

  it('keeps the candles and offers a retry when a history page fails', () => {
    const { fixture, el, stub } = render(response(MIXED));
    const loadOlder = vi.spyOn(stub, 'loadOlder');
    stub.pageError.set(true);
    fixture.detectChanges();
    const note = el.querySelector('.page-error')!;
    expect(note.textContent).toContain("Couldn't load earlier history");
    expect(fixture.componentInstance['state']()).toBe('chart');
    note.querySelector('button')!.click();
    expect(loadOlder).toHaveBeenCalledTimes(1);
    stub.hasMore.set(true);
    at(fixture, 0, 2);
    expect(loadOlder).toHaveBeenCalledTimes(2);
  });

  it('reports leaving the live edge and offers Latest, which scrolls back', () => {
    const { fixture, el, stub } = render(response(MIXED));
    // vi.spyOn calls through, so the stub's atLiveEdge follows what the component reports.
    const setEdge = vi.spyOn(stub, 'setAtLiveEdge');
    at(fixture, 0, 0);
    expect(setEdge).toHaveBeenLastCalledWith(false);
    expect(stub.atLiveEdge()).toBe(false);
    const scroll = vi.spyOn(
      (fixture.componentInstance as unknown as { chart: { timeScale(): { scrollToRealTime(): void } } })
        .chart.timeScale(), 'scrollToRealTime');
    const latest = [...el.querySelectorAll('button')].find((b) => b.textContent!.includes('Latest'))!;
    latest.click();
    expect(scroll).toHaveBeenCalledTimes(1);

    stub.setAtLiveEdge(true);
    fixture.detectChanges();
    expect([...el.querySelectorAll('button')].some((b) => b.textContent!.includes('Latest'))).toBe(false);
  });

  it('never moves the viewport on a scan refresh while the past is in view', () => {
    const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
    try {
      const { fixture, stub } = render(response(MIXED));
      const scale = (fixture.componentInstance as unknown as {
        chart: { timeScale(): { fitContent(): void; scrollToRealTime(): void } } }).chart.timeScale();
      const fit = vi.spyOn(scale, 'fitContent');
      const scroll = vi.spyOn(scale, 'scrollToRealTime');
      stub.setAtLiveEdge(false);
      stub.data.set(response([...MIXED, candle('2026-10-21', { o: 112, c: 115 })]));
      fixture.detectChanges();
      expect(fit).not.toHaveBeenCalled();
      expect(scroll).not.toHaveBeenCalled();
    } finally {
      widthSpy.mockRestore();
    }
  });
  describe('auto timeframe (v181 §3)', () => {
    afterEach(() => vi.useRealTimers());

    it('steps up past 250 visible bars and restores the same span on the new candles', () => {
      const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
      try {
        const { fixture, stub } = render(response(hourlyCandles(300), { tf: '1H' }));
        at(fixture, 0, 299);
        expect(stub.calls.tf).toEqual(['4H']);

        const scale = scaleOf(fixture);
        const restore = vi.spyOn(scale, 'setVisibleRange').mockImplementation(() => {});
        const fit = vi.spyOn(scale, 'fitContent');
        stub.data.set(response(hourlyCandles(80), { tf: '4H' }));
        fixture.detectChanges();
        const from = Date.UTC(2026, 9, 1) / 1000;
        expect(restore).toHaveBeenCalledWith({ from, to: from + 300 * 3600 - 1 });
        expect(fit).not.toHaveBeenCalled();
      } finally {
        widthSpy.mockRestore();
      }
    });

    it('steps down below 15 visible bars', () => {
      const { fixture, stub } = render(
        response(dailyCandles(40), { tf: '1D', recording_since: '2026-08-01T13:30:00Z' }));
      at(fixture, 0, 9);
      expect(stub.calls.tf).toEqual(['4H']);
    });

    it('holds at the edge of history, where no intraday candles exist', () => {
      const { fixture, stub } = render(
        response(dailyCandles(40), { tf: '1D', recording_since: '2026-10-01T13:30:00Z' }));
      at(fixture, 0, 9);
      expect(stub.calls.tf).toEqual([]);
    });

    it('holds between 15 and 250 bars', () => {
      const { fixture, stub } = render(response(dailyCandles(40), { tf: '1D' }));
      at(fixture, 0, 39);
      expect(stub.calls.tf).toEqual([]);
    });

    it('takes one step at a time while the new candles load', () => {
      const { fixture, stub } = render(response(hourlyCandles(300), { tf: '1H' }));
      at(fixture, 0, 299);
      at(fixture, 0, 298);
      expect(stub.calls.tf).toEqual(['4H']);
    });

    it('drops a pending restore when the partner picks a timeframe by hand', () => {
      const { fixture, stub } = render(response(hourlyCandles(300), { tf: '1H' }));
      at(fixture, 0, 299);
      fixture.componentInstance['onTimeframe']('1D');
      expect(fixture.componentInstance['pendingSpan']).toBeNull();
      expect(stub.calls.tf).toEqual(['4H', '1D']);
    });
  });

  describe('programmatic moves (v181 §1, §7)', () => {
    afterEach(() => vi.useRealTimers());

    it('holds the flag through the chart\'s next paint, then releases it', () => {
      // Only the settle timer is under test; jsdom has no canvas paint context.
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
      const { fixture } = render(response(MIXED));
      const component = fixture.componentInstance as unknown as {
        programmatic: boolean; moveProgrammatically(fn: () => void): void };
      let inside = false;
      component.moveProgrammatically(() => (inside = component.programmatic));
      expect(inside).toBe(true);
      expect(component.programmatic).toBe(true);
      vi.advanceTimersByTime(99);
      expect(component.programmatic).toBe(true);
      vi.advanceTimersByTime(1);
      expect(component.programmatic).toBe(false);
    });

    it('fits a new timeframe under the flag', () => {
      const widthSpy = vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => 600);
      try {
        const { fixture, stub } = render(response(MIXED));
        const component = fixture.componentInstance as unknown as { programmatic: boolean };
        let flagged: boolean | null = null;
        vi.spyOn(scaleOf(fixture), 'fitContent').mockImplementation(() => (flagged = component.programmatic));
        stub.data.set(response(MIXED, { tf: '1W' }));
        fixture.detectChanges();
        expect(flagged).toBe(true);
      } finally {
        widthSpy.mockRestore();
      }
    });
  });

});
