import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { ChartPrefs } from './chart-prefs';
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

describe('TradeChart', () => {
  let prefs: ChartPrefs;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
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
