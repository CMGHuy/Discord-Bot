import type { IChartApi, LogicalRange, LogicalRangeChangeEventHandler } from 'lightweight-charts';
import { describe, expect, it, vi } from 'vitest';

import { TimeScaleSync } from './time-scale-sync';

const range = (from: number, to: number) => ({ from, to }) as LogicalRange;

/** A chart reduced to its time scale. Setting the range reports it at once: the worst case for ping-pong. */
function fakeChart() {
  let handlers: LogicalRangeChangeEventHandler[] = [];
  let visible: LogicalRange | null = null;
  const report = () => handlers.forEach((handler) => handler(visible));
  const scale = {
    subscribeVisibleLogicalRangeChange: (handler: LogicalRangeChangeEventHandler) => { handlers.push(handler); },
    unsubscribeVisibleLogicalRangeChange: (handler: LogicalRangeChangeEventHandler) => {
      handlers = handlers.filter((h) => h !== handler);
    },
    getVisibleLogicalRange: () => visible,
    setVisibleLogicalRange: vi.fn((next: LogicalRange) => { visible = next; report(); }),
  };
  return {
    chart: { timeScale: () => scale } as unknown as IChartApi,
    set: scale.setVisibleLogicalRange,
    /** A user gesture: the range moves and the chart reports it. */
    scroll(next: LogicalRange | null) { visible = next; report(); },
    /** The library reporting later, after the call stack has unwound. */
    quietly(next: LogicalRange) { visible = next; },
    listeners: () => handlers.length,
  };
}

describe('TimeScaleSync (v246 §A3 linked scrolling)', () => {
  it('moves every other chart to the scrolled range, once, and never back to the source', () => {
    const sync = new TimeScaleSync();
    const [a, b, c] = [fakeChart(), fakeChart(), fakeChart()];
    for (const fake of [a, b, c]) sync.register(fake.chart);
    a.scroll(range(2, 10));
    expect(b.set).toHaveBeenCalledTimes(1);
    expect(b.set).toHaveBeenCalledWith(range(2, 10));
    expect(c.set).toHaveBeenCalledTimes(1);
    expect(a.set).not.toHaveBeenCalled();
  });

  it('ignores a late echo of a range the source already shows', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    b.set.mockImplementation((next: LogicalRange) => b.quietly(next));
    a.scroll(range(4, 12));
    b.scroll(range(4, 12));
    expect(b.set).toHaveBeenCalledTimes(1);
    expect(a.set).not.toHaveBeenCalled();
  });

  it('follows the other way too', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    b.scroll(range(0, 5));
    expect(a.set).toHaveBeenCalledWith(range(0, 5));
  });

  it('moves nothing for a null range', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    a.scroll(null);
    expect(b.set).not.toHaveBeenCalled();
  });

  it('stops following once released, and a second release is harmless', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    const release = sync.register(a.chart);
    sync.register(b.chart);
    release();
    expect(a.listeners()).toBe(0);
    a.scroll(range(1, 3));
    b.scroll(range(6, 9));
    expect(b.set).not.toHaveBeenCalled();
    expect(a.set).not.toHaveBeenCalled();
    expect(() => release()).not.toThrow();
  });

  it('subscribes a chart once however often it is registered', () => {
    const sync = new TimeScaleSync();
    const a = fakeChart();
    const first = sync.register(a.chart);
    const second = sync.register(a.chart);
    expect(a.listeners()).toBe(1);
    second();
    expect(a.listeners()).toBe(0);
    expect(() => first()).not.toThrow();
  });

  it('drops its guard again when a follower throws', () => {
    const sync = new TimeScaleSync();
    const [a, b] = [fakeChart(), fakeChart()];
    sync.register(a.chart);
    sync.register(b.chart);
    b.set.mockImplementationOnce(() => { throw new Error('disposed'); });
    expect(() => a.scroll(range(1, 2))).toThrow('disposed');
    a.scroll(range(3, 4));
    expect(b.set).toHaveBeenLastCalledWith(range(3, 4));
  });
});
