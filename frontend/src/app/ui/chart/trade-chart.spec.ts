import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { THEME_STORAGE, ThemeService } from '../theme.service';
import { ChartPrefs } from './chart-prefs';
import { chartPalette } from './chart-theme';
import { applyPricePanePalette } from './price-pane';
import { TradeChart } from './trade-chart';

// TradeChart creates a real lightweight-charts chart, and fancy-canvas asks
// for matchMedia the moment one exists. jsdom has no matchMedia at all — see
// the polyfill for why this is a stand-in rather than a jsdom bug workaround.
installMatchMediaPolyfill();

const PAYLOAD = {
  ticker: 'AAPL',
  ohlcv: [{ t: 1767225600, o: 1, h: 2, l: 0.5, c: 1.5, v: 100 }],
  indicators: { rsi: [50] },
  volume_profile: [],
  levels: null,
  overlays: [{ side: 'target', source: 'EMA20', shape: { kind: 'curve', points: [] } }],
  notes: ['Trendline 2026-06-02 → 2026-08-01'],
} as never;

afterEach(() => {
  delete document.documentElement.dataset['theme'];
});

describe('TradeChart', () => {
  let prefs: ChartPrefs;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: THEME_STORAGE, useValue: { get: () => null, set: () => {} } },
      ],
    });
    prefs = TestBed.inject(ChartPrefs);
  });

  it('drops a pane when its layer is toggled off', () => {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    const before = fixture.componentInstance['activeLayers']();
    expect(before).toContain('rsi');

    prefs.toggle('rsi');
    fixture.detectChanges();
    expect(fixture.componentInstance['activeLayers']()).not.toContain('rsi');
  });

  it('feeds the legend the payload notes and every drawn method', () => {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    const lines = fixture.componentInstance['legendLines']();
    expect(lines).toContain('EMA20');
    expect(lines.some((l: string) => l.includes('Trendline'))).toBe(true);
  });

  it('draws no plan layer when the payload has no levels', () => {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    expect(fixture.componentInstance['activeLayers']()).not.toContain('plan');
  });
});

describe('TradeChart follows the theme (v225)', () => {
  // jsdom resolves token() against the flat Graphite fixture (test-setup.ts),
  // so the Navy ground is layered here the way tokens.css layers it.
  const NAVY_CSS = ':root[data-theme="navy"]{--surface:#0c1424;--text:#e6ecf5;--text-muted:#9fb0c8;--text-faint:#5f6f8a}';
  let style: HTMLStyleElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: THEME_STORAGE, useValue: { get: () => null, set: () => {} } }],
    });
    style = document.createElement('style');
    style.textContent = NAVY_CSS;
    document.head.appendChild(style);
  });

  afterEach(() => {
    style.remove();
    delete document.documentElement.dataset['theme'];
  });

  async function mounted() {
    const fixture = TestBed.createComponent(TradeChart);
    fixture.componentRef.setInput('data', PAYLOAD);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture;
  }

  async function flip(fixture: Awaited<ReturnType<typeof mounted>>, theme: 'graphite' | 'navy') {
    TestBed.inject(ThemeService).set(theme);
    fixture.detectChanges();
    await fixture.whenStable();
  }

  it('re-applies the chart ground, the series colours and the legend palette on a flip', async () => {
    const fixture = await mounted();
    const component = fixture.componentInstance;
    const applied = vi.spyOn(component['chart']!, 'applyOptions');
    const candles = vi.spyOn(component['candles']!, 'applyOptions');
    const volume = vi.spyOn(component['volume']!, 'applyOptions');

    await flip(fixture, 'navy');

    expect(applied.mock.calls.at(-1)![0]).toMatchObject({ layout: { background: { color: '#0c1424' }, textColor: '#9fb0c8' } });
    expect(candles).toHaveBeenCalledWith(expect.objectContaining({ upColor: chartPalette().up, wickDownColor: chartPalette().down }));
    expect(volume).toHaveBeenCalledWith({ color: '#5f6f8a' });
    expect(component['legend']!['currentPalette'].surface).toBe('#0c1424');
  });

  it('repaints the palette-fed layers without moving the viewport', async () => {
    const fixture = await mounted();
    const component = fixture.componentInstance;
    const strategy = vi.spyOn(component['strategy']!, 'render');
    const fit = vi.spyOn(component['chart']!.timeScale(), 'fitContent');

    await flip(fixture, 'navy');

    expect(strategy).toHaveBeenCalledTimes(1);
    expect(strategy.mock.calls[0][1].surface).toBe('#0c1424');
    expect(fit).not.toHaveBeenCalled();
  });

  it('returns to the Graphite ground when flipped back', async () => {
    const fixture = await mounted();
    const graphiteSurface = chartPalette().surface;
    await flip(fixture, 'navy');
    const applied = vi.spyOn(fixture.componentInstance['chart']!, 'applyOptions');
    await flip(fixture, 'graphite');
    expect(graphiteSurface).not.toBe('#0c1424');
    expect(applied.mock.calls.at(-1)![0]).toMatchObject({ layout: { background: { color: graphiteSurface } } });
  });

  it('restyles nothing after the chart is destroyed', async () => {
    const fixture = await mounted();
    fixture.destroy();
    expect(() => TestBed.inject(ThemeService).set('navy')).not.toThrow();
  });
});

describe('applyPricePanePalette (v225)', () => {
  it('gives the candles and the volume the same colours createPricePane does', () => {
    const candles = { applyOptions: vi.fn() };
    const volume = { applyOptions: vi.fn() };
    const palette = { up: '#1', down: '#2', volume: '#3' } as never;
    applyPricePanePalette({ candles, volume } as never, palette);
    expect(candles.applyOptions).toHaveBeenCalledWith({
      upColor: '#1', downColor: '#2', borderUpColor: '#1', borderDownColor: '#2', wickUpColor: '#1', wickDownColor: '#2',
    });
    expect(volume.applyOptions).toHaveBeenCalledWith({ color: '#3' });
  });
});
