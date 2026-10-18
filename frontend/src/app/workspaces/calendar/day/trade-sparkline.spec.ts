import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { SparkSeries } from '../../../api/models';
import { TradeSparkline, sparkGeometry } from './trade-sparkline';

/** Six bars, exit on the fourth (index 3), two dimmed context bars after it.
 *  Levels: stop 9 is the domain floor, close 13 the ceiling, so
 *  y(v) = 30 - (v - 9) / 4 * 28 and x steps by 120 / 5 = 24. */
const SERIES: SparkSeries = {
  closes: [
    { date: '2026-07-29', close: 10 },
    { date: '2026-07-30', close: 11 },
    { date: '2026-07-31', close: 12 },
    { date: '2026-08-03', close: 13 },
    { date: '2026-08-04', close: 12 },
    { date: '2026-08-05', close: 11 },
  ],
  exit_bar: 3,
  last_bar: '2026-08-28',
  stale: false,
  entry: 10,
  stop: 9,
  tp1: 13,
  tp2: null,
  exit: 12.5,
  exit_date: '2026-08-03',
};

describe('sparkGeometry', () => {
  it('draws the bars up to the exit solid and the context bars after it dimmed', () => {
    const g = sparkGeometry(SERIES);
    expect(g.path).toBe('M 0.00 23.00 L 24.00 16.00 L 48.00 9.00 L 72.00 2.00');
    expect(g.dimmedPath).toBe('M 72.00 2.00 L 96.00 9.00 L 120.00 16.00');
  });

  it('puts a tick at every recorded level, in entry, stop, tp1, tp2 order, skipping nulls', () => {
    expect(sparkGeometry(SERIES).ticks).toEqual([
      { kind: 'entry', y: 23 },
      { kind: 'stop', y: 30 },
      { kind: 'tp1', y: 2 },
    ]);
  });

  it('puts the exit dot at the recorded fill, not at the exit bar close', () => {
    // The bar closed at 13 (y 2); the fill was 12.5 (y 5.5).
    expect(sparkGeometry(SERIES).exitDot).toEqual({ x: 72, y: 5.5 });
  });

  it('draws only the close line when every tick was nulled (entry off the bars)', () => {
    const g = sparkGeometry({ ...SERIES, entry: null, stop: null, tp1: null, tp2: null, exit: null });
    expect(g.ticks).toEqual([]);
    expect(g.exitDot).toBeNull();
    // Domain is now the closes alone: 10 is the floor.
    expect(g.path.startsWith('M 0.00 30.00')).toBe(true);
  });

  it('has no exit dot on a stale series: its last bar is not the exit day', () => {
    expect(sparkGeometry({ ...SERIES, stale: true }).exitDot).toBeNull();
  });

  it('has no dimmed part when the exit bar is the last bar', () => {
    const g = sparkGeometry({ ...SERIES, closes: SERIES.closes.slice(0, 4) });
    expect(g.dimmedPath).toBe('');
    expect(g.path.endsWith('L 120.00 2.00')).toBe(true);
  });

  it('draws a single bar as a flat line down the middle', () => {
    const g = sparkGeometry({
      ...SERIES,
      closes: [{ date: '2026-08-03', close: 50 }],
      exit_bar: 0, entry: 50, stop: null, tp1: null, tp2: null, exit: 50,
    });
    expect(g.path).toBe('M 0.00 16.00 L 120.00 16.00');
    expect(g.dimmedPath).toBe('');
    expect(g.exitDot).toEqual({ x: 60, y: 16 });
  });

  it('draws everything solid and no dot when exit_bar is outside the closes', () => {
    const g = sparkGeometry({ ...SERIES, exit_bar: 9 });
    expect(g.dimmedPath).toBe('');
    expect(g.exitDot).toBeNull();
    expect(g.path.endsWith('L 120.00 16.00')).toBe(true);
  });

  it('is empty for an empty close list', () => {
    expect(sparkGeometry({ ...SERIES, closes: [] })).toEqual({
      path: '', dimmedPath: '', ticks: [], exitDot: null,
    });
  });
});

describe('TradeSparkline', () => {
  let fixture: ComponentFixture<TradeSparkline>;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
    fixture = TestBed.createComponent(TradeSparkline);
    fixture.componentRef.setInput('tradeId', 'PLAN-1');
  });

  const render = async (series: SparkSeries | null | undefined): Promise<HTMLElement> => {
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  };

  it('links the whole sparkline to the trade Chart tab', async () => {
    const el = await render(SERIES);
    expect(el.querySelector('a.spark')?.getAttribute('href')).toBe('/trades/PLAN-1?tab=chart');
  });

  it('draws the ticks, the dimmed context and the exit dot, with the stop called the final stop', async () => {
    const el = await render(SERIES);
    expect(el.querySelectorAll('line.tick')).toHaveLength(3);
    const stop = el.querySelector('line.tick[data-kind=stop]');
    expect(stop?.querySelector('title')?.textContent).toBe('final stop');
    expect(el.querySelector('path.dimmed')).not.toBeNull();
    expect(el.querySelector('circle.exit')).not.toBeNull();
    expect(el.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 120 32');
  });

  it('says where a stale cache ends', async () => {
    const el = await render({ ...SERIES, stale: true, last_bar: '2026-08-04' });
    expect(el.querySelector('.stale-note')?.textContent?.trim()).toBe('cache ends 2026-08-04');
    expect(el.querySelector('circle.exit')).toBeNull();
  });

  it('renders a dash, not an empty box, with no series or no answer', async () => {
    for (const series of [null, undefined]) {
      const el = await render(series);
      expect(el.querySelector('svg')).toBeNull();
      expect(el.querySelector('.spark-empty')?.textContent?.trim()).toBe('—');
    }
  });
});
