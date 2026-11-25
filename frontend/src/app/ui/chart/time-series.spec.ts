import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import type {
  AreaSeriesOptions, BaselineSeriesOptions, CandlestickSeriesOptions, IChartApi, IPriceLine, ISeriesApi,
  SeriesType, SingleValueData,
} from 'lightweight-charts';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installMatchMediaPolyfill } from '../../testing/match-media-polyfill';
import { resolveToken } from '../testing/resolve-token';
import { resolveTokenIn } from '../testing/theme-tokens';
import { THEME_STORAGE, ThemeService } from '../theme.service';
import {
  TimeSeries, TimeSeriesCandle, TimeSeriesDatum, TimeSeriesFormat, TimeSeriesKind, TimeSeriesPoint, collapseByDay,
} from './time-series';
import { TimeScaleSync } from './time-scale-sync';

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

/** A ResizeObserver stand-in: `notify()` fires the last observer's callback. */
function fakeResizeObserver() {
  const state = { notify: () => {}, disconnect: vi.fn() };
  class FakeObserver {
    constructor(callback: () => void) { state.notify = callback; }
    observe(): void {}
    disconnect(): void { state.disconnect(); }
  }
  vi.stubGlobal('ResizeObserver', FakeObserver);
  return state;
}

describe('sb-time-series edge states and lifecycle (v246 §A3)', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('collapses same-day points and drops a non-finite value', () => {
    const fixture = mount('area', [
      { time: '2026-10-01T09:00:00Z', value: 1 }, { time: '2026-10-01T17:00:00Z', value: 2 },
      { time: '2026-10-02', value: Number.NaN }, { time: '2026-10-03', value: 4 },
    ]);
    expect(values(fixture)).toEqual([2, 4]);
  });

  it('drops a candle with a non-finite price', () => {
    const fixture = mount('candles', [
      { time: '2026-10-01', open: 100, high: 120, low: 90, close: 110 },
      { time: '2026-10-02', open: 110, high: Number.POSITIVE_INFINITY, low: 95, close: 98 },
    ]);
    expect(inside(fixture).series!.data()).toHaveLength(1);
  });

  it('keeps an empty series for no points, and fills it when points arrive', () => {
    const fixture = mount('area', []);
    expect(inside(fixture).series!.data()).toHaveLength(0);
    set(fixture, 'points', EQUITY);
    expect(values(fixture)).toEqual([0, 120.5, -40]);
  });

  it('draws one point as a marker without a line, and the line again from two', () => {
    const fixture = mount('area', [{ time: '2026-10-01', value: 5 }]);
    const options = () => inside(fixture).series!.options() as AreaSeriesOptions;
    expect(options().lineVisible).toBe(false);
    expect(options().pointMarkersVisible).toBe(true);
    set(fixture, 'points', EQUITY);
    expect(options().lineVisible).toBe(true);
    expect(options().pointMarkersVisible).toBe(false);
  });

  it('marks a single drawdown point too', () => {
    const fixture = mount('baseline', [{ time: '2026-10-01', value: -0.4 }], 'r');
    const options = inside(fixture).series!.options() as BaselineSeriesOptions;
    expect(options.lineVisible).toBe(false);
    expect(options.pointMarkersVisible).toBe(true);
  });

  it('fits new data once the plot has a width', () => {
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockReturnValue(600);
    const fixture = mount('area', []);
    const fit = vi.spyOn(inside(fixture).chart!.timeScale(), 'fitContent');
    set(fixture, 'points', EQUITY);
    set(fixture, 'height', 180);
    expect(fit).toHaveBeenCalledTimes(1);
  });

  it('resizes to the host width on an observer tick, and fits once a width arrives', () => {
    const observer = fakeResizeObserver();
    let width = 0;
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    const resize = vi.spyOn(chart, 'resize');
    const fit = vi.spyOn(chart.timeScale(), 'fitContent');
    width = 600;
    observer.notify();
    observer.notify();
    expect(resize).toHaveBeenLastCalledWith(600, 220);
    expect(fit).toHaveBeenCalledTimes(1);
  });

  it('repaints on a theme switch, without a reload', async () => {
    const fixture = mount('area', EQUITY);
    const names = ['--accent', '--accent-soft', '--surface', '--text-secondary'];
    const style = document.createElement('style');
    style.textContent = `:root[data-theme="navy"]{${names.map((n) => `${n}:${resolveTokenIn('navy', n)}`).join(';')}}`;
    document.head.appendChild(style);
    try {
      TestBed.inject(ThemeService).set('navy');
      fixture.detectChanges();
      await fixture.whenStable();
      const { chart, series } = inside(fixture);
      expect(resolveTokenIn('navy', '--accent')).not.toBe(resolveToken('--accent'));
      expect((series!.options() as AreaSeriesOptions).lineColor).toBe(resolveTokenIn('navy', '--accent'));
      expect((series!.options() as AreaSeriesOptions).topColor).toBe(resolveTokenIn('navy', '--accent-soft'));
      expect(chart!.options().layout.textColor).toBe(resolveTokenIn('navy', '--text-secondary'));
      expect((chart!.options().layout.background as { color: string }).color).toBe(resolveTokenIn('navy', '--surface'));
    } finally {
      style.remove();
    }
  });

  it('releases its ResizeObserver, its chart and its theme subscription on destroy', async () => {
    const observer = fakeResizeObserver();
    const fixture = mount('area', EQUITY);
    const chart = inside(fixture).chart!;
    const remove = vi.spyOn(chart, 'remove');
    const applied = vi.spyOn(chart, 'applyOptions');
    fixture.destroy();
    expect(observer.disconnect).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledTimes(1);
    expect(inside(fixture).chart).toBeNull();
    TestBed.inject(ThemeService).set('navy');
    await fixture.whenStable();
    expect(applied).not.toHaveBeenCalled();
  });
});

describe('sb-time-series linked scrolling (v246 §A3)', () => {
  function spiedSync() {
    const sync = new TimeScaleSync();
    const release = vi.fn();
    const register = vi.spyOn(sync, 'register').mockReturnValue(release);
    return { sync, register, release };
  }

  /** `sync` set before the first change detection, the way a template binds it. */
  function mountSynced(sync: TimeScaleSync) {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(),
        { provide: THEME_STORAGE, useValue: { get: () => 'graphite', set: () => {} } }],
    });
    const fixture = TestBed.createComponent(TimeSeries);
    fixture.componentRef.setInput('kind', 'area');
    fixture.componentRef.setInput('points', EQUITY);
    fixture.componentRef.setInput('label', 'Equity curve');
    fixture.componentRef.setInput('sync', sync);
    fixture.detectChanges();
    return fixture;
  }

  it('registers its chart once with the sync it is given', () => {
    const { sync, register } = spiedSync();
    const fixture = mountSynced(sync);
    expect(register).toHaveBeenCalledTimes(1);
    expect(register).toHaveBeenCalledWith(inside(fixture).chart);
  });

  it('keeps its registration across a kind change: the chart is the same', () => {
    const { sync, register, release } = spiedSync();
    const fixture = mountSynced(sync);
    set(fixture, 'kind', 'baseline');
    expect(register).toHaveBeenCalledTimes(1);
    expect(release).not.toHaveBeenCalled();
  });

  it('leaves the old sync for a new one, and any sync for null', () => {
    const first = spiedSync();
    const second = spiedSync();
    const fixture = mountSynced(first.sync);
    set(fixture, 'sync', second.sync);
    expect(first.release).toHaveBeenCalledTimes(1);
    expect(second.register).toHaveBeenCalledWith(inside(fixture).chart);
    set(fixture, 'sync', null);
    expect(second.release).toHaveBeenCalledTimes(1);
  });

  it('joins a sync set after it was created', () => {
    const { sync, register } = spiedSync();
    const fixture = mount('area', EQUITY);
    expect(register).not.toHaveBeenCalled();
    set(fixture, 'sync', sync);
    expect(register).toHaveBeenCalledWith(inside(fixture).chart);
  });

  it('releases its sync on destroy, before the chart is removed', () => {
    const { sync, release } = spiedSync();
    const fixture = mountSynced(sync);
    const chart = inside(fixture).chart!;
    const order: string[] = [];
    const remove = chart.remove.bind(chart);
    release.mockImplementation(() => order.push('sync'));
    vi.spyOn(chart, 'remove').mockImplementation(() => { order.push('chart'); remove(); });
    fixture.destroy();
    expect(order).toEqual(['sync', 'chart']);
  });
});
