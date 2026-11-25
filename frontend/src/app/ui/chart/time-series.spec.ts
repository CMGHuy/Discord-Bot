import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import type {
  AreaSeriesOptions, BaselineSeriesOptions, CandlestickSeriesOptions, IChartApi, IPriceLine, ISeriesApi,
  SeriesType, SingleValueData,
} from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { resolveToken } from '../testing/resolve-token';
import { THEME_STORAGE } from '../theme.service';
import {
  TimeSeries, TimeSeriesCandle, TimeSeriesDatum, TimeSeriesFormat, TimeSeriesKind, TimeSeriesPoint, collapseByDay,
} from './time-series';

// A real lightweight-charts chart is created; fancy-canvas needs matchMedia.
installMatchMediaPolyfill();

type Internals = { chart: IChartApi | null; series: ISeriesApi<SeriesType> | null; zeroLine: IPriceLine | null };
const inside = (fixture: ComponentFixture<TimeSeries>) => fixture.componentInstance as unknown as Internals;
const values = (fixture: ComponentFixture<TimeSeries>) =>
  inside(fixture).series!.data().map((row) => (row as SingleValueData).value);

const EQUITY: TimeSeriesPoint[] = [
  { time: '2026-10-01', value: 0 }, { time: '2026-10-02', value: 120.5 }, { time: '2026-10-05', value: -40 },
];
const CANDLES: TimeSeriesCandle[] = [
  { time: '2026-10-01', open: 100, high: 120, low: 90, close: 110 },
  { time: '2026-10-02', open: 110, high: 112, low: 95, close: 98 },
];

function mount(kind: TimeSeriesKind, points: readonly TimeSeriesDatum[], valueFormat?: TimeSeriesFormat) {
  TestBed.configureTestingModule({
    // Black first: Navy is the default since v240, and V246-13b's theme test flips to Navy.
    providers: [provideZonelessChangeDetection(),
      { provide: THEME_STORAGE, useValue: { get: () => 'graphite', set: () => {} } }],
  });
  const fixture = TestBed.createComponent(TimeSeries);
  fixture.componentRef.setInput('kind', kind);
  fixture.componentRef.setInput('points', points);
  fixture.componentRef.setInput('label', 'Equity curve');
  if (valueFormat) fixture.componentRef.setInput('valueFormat', valueFormat);
  fixture.detectChanges();
  return fixture;
}

function set(fixture: ComponentFixture<TimeSeries>, name: string, value: unknown): void {
  fixture.componentRef.setInput(name, value);
  fixture.detectChanges();
}

afterEach(() => vi.restoreAllMocks());

describe('collapseByDay', () => {
  it('keeps the last point of each day, keyed and labelled by the date part, in time order', () => {
    expect(collapseByDay([
      { time: '2026-10-01T10:00:00Z', value: 1 }, { time: '2026-10-01T16:00:00Z', value: 2 }, { time: '2026-09-30', value: 0 },
    ])).toEqual([{ time: '2026-09-30', value: 0 }, { time: '2026-10-01', value: 2 }]);
  });

  it('returns nothing for nothing', () => {
    expect(collapseByDay([])).toEqual([]);
  });
});

describe('sb-time-series (v246 §A3)', () => {
  it('draws an area in the accent over an accent-to-transparent fill, with a zero line', () => {
    const fixture = mount('area', EQUITY);
    const { series, zeroLine } = inside(fixture);
    const options = series!.options() as AreaSeriesOptions;
    expect(series!.seriesType()).toBe('Area');
    expect(options.lineColor).toBe(resolveToken('--accent'));
    expect(options.topColor).toBe(resolveToken('--accent-soft'));
    expect(options.bottomColor).toBe('transparent');
    expect(values(fixture)).toEqual([0, 120.5, -40]);
    expect(zeroLine!.options().price).toBe(0);
    expect(zeroLine!.options().color).toBe(resolveToken('--border-strong'));
  });

  it('draws drawdown as a baseline at zero, shaded in the loss tint below it', () => {
    const fixture = mount('baseline', [{ time: '2026-10-01', value: 0 }, { time: '2026-10-02', value: -1.5 }], 'r');
    const { series, zeroLine } = inside(fixture);
    const options = series!.options() as BaselineSeriesOptions;
    expect(series!.seriesType()).toBe('Baseline');
    expect(options.baseValue).toEqual({ type: 'price', price: 0 });
    expect(options.bottomLineColor).toBe(resolveToken('--neg'));
    expect(options.bottomFillColor1).toBe(resolveToken('--neg-soft'));
    expect(options.bottomFillColor2).toBe(resolveToken('--neg-soft'));
    expect(options.topFillColor1).toBe('transparent');
    expect(zeroLine).not.toBeNull();
  });

  it('draws candles in the up and down inks, without a zero line', () => {
    const fixture = mount('candles', CANDLES);
    const { series, zeroLine } = inside(fixture);
    const options = series!.options() as CandlestickSeriesOptions;
    expect(series!.seriesType()).toBe('Candlestick');
    expect(options.upColor).toBe(resolveToken('--pos'));
    expect(options.downColor).toBe(resolveToken('--neg'));
    expect(series!.data()).toHaveLength(2);
    expect(zeroLine).toBeNull();
  });

  it('themes the chart through applyChartTheme', () => {
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    expect(chart.options().layout.textColor).toBe(resolveToken('--text-secondary'));
    expect(chart.options().autoSize).toBe(false);
  });

  it('formats the price scale per valueFormat', () => {
    const fixture = mount('area', EQUITY);
    const format = (value: number) => inside(fixture).series!.priceFormatter().format(value);
    expect(format(997800)).toBe('997,800.00');
    set(fixture, 'valueFormat', 'r');
    expect(format(-1)).toBe('−1.00R');
    set(fixture, 'valueFormat', 'pct');
    expect(format(3)).toBe('+3.00%');
  });

  it('rebuilds only the series when the kind changes', () => {
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    const removed = vi.spyOn(chart, 'removeSeries');
    set(fixture, 'kind', 'baseline');
    expect(inside(fixture).chart).toBe(chart);
    expect(removed).toHaveBeenCalledTimes(1);
    expect(inside(fixture).series!.seriesType()).toBe('Baseline');
    expect(values(fixture)).toEqual([0, 120.5, -40]);
  });

  it('names the canvas and reserves its height', () => {
    const fixture = mount('area', EQUITY);
    const host = fixture.nativeElement as HTMLElement;
    expect(host.getAttribute('role')).toBe('img');
    expect(host.getAttribute('aria-label')).toBe('Equity curve');
    expect(host.style.height).toBe('220px');
    const resize = vi.spyOn(inside(fixture).chart!, 'resize');
    set(fixture, 'height', 160);
    expect(host.style.height).toBe('160px');
    expect(resize).toHaveBeenLastCalledWith(expect.any(Number), 160);
  });

  it('removes its chart on destroy', () => {
    const fixture = mount('area', EQUITY);
    const remove = vi.spyOn(inside(fixture).chart!, 'remove');
    fixture.destroy();
    expect(remove).toHaveBeenCalledTimes(1);
    expect(inside(fixture).chart).toBeNull();
  });
});
