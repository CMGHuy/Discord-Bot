import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';
import { token } from './chart/chart-frame';
import { LineChart, lineChartXScale, lineChartYScale, seriesPath } from './line-chart';

describe('lineChartXScale', () => {
  it('maps the earliest date to 0 and the latest to 1', () => {
    const scale = lineChartXScale(['2026-01-01', '2026-01-11', '2026-01-21']);
    expect(scale('2026-01-01')).toBeCloseTo(0, 5);
    expect(scale('2026-01-21')).toBeCloseTo(1, 5);
    expect(scale('2026-01-11')).toBeCloseTo(0.5, 5);
  });

  it('is a real time scale, not an index scale', () => {
    // Three dates, unevenly spaced -- an index scale would put the middle
    // one at 0.5. Jan 3 is 2/20 of the way from Jan 1 to Jan 21.
    const scale = lineChartXScale(['2026-01-01', '2026-01-03', '2026-01-21']);
    expect(scale('2026-01-03')).toBeCloseTo(0.1, 5);
  });

  it('a single date does not divide by zero', () => {
    const scale = lineChartXScale(['2026-01-01']);
    expect(scale('2026-01-01')).toBe(0);
    expect(Number.isNaN(scale('2026-01-01'))).toBe(false);
  });
});

describe('lineChartYScale', () => {
  it('maps the lowest value to 0 and the highest to 1', () => {
    const scale = lineChartYScale([10, 30, 20]);
    expect(scale(10)).toBeCloseTo(0, 5);
    expect(scale(30)).toBeCloseTo(1, 5);
  });

  it('a flat series (one distinct value) does not divide by zero', () => {
    const scale = lineChartYScale([5, 5, 5]);
    expect(scale(5)).toBeCloseTo(0.5, 5);
    expect(Number.isNaN(scale(5))).toBe(false);
  });

  it('respects a fixed [min, max] domain when one is given', () => {
    // The Calibration decile chart needs an absolute 0-100 win-rate axis,
    // not one auto-scaled to whichever decile happens to be tallest --
    // see Task 8's own note on why Histogram needed the same fix.
    const scale = lineChartYScale([60, 85], { min: 0, max: 100 });
    expect(scale(0)).toBeCloseTo(0, 5);
    expect(scale(100)).toBeCloseTo(1, 5);
    expect(scale(85)).toBeCloseTo(0.85, 5);
  });
});

describe('seriesPath', () => {
  it('builds one SVG line command per point after the first', () => {
    const series = {
      name: 'ui',
      points: [
        { date: '2026-01-01', value: 0 },
        { date: '2026-01-11', value: 10 },
      ],
    };
    const x = lineChartXScale(['2026-01-01', '2026-01-11']);
    const y = lineChartYScale([0, 10]);
    const path = seriesPath(series, x, y);
    expect(path.startsWith('M ')).toBe(true);
    expect(path.match(/L /g)).toHaveLength(1);
  });

  it('a single point draws nothing rather than throwing', () => {
    const series = { name: 'ui', points: [{ date: '2026-01-01', value: 0 }] };
    const x = lineChartXScale(['2026-01-01']);
    const y = lineChartYScale([0]);
    expect(() => seriesPath(series, x, y)).not.toThrow();
  });
});

describe('LineChart', () => {
  function render(series: { name: string; points: { date: string; value: number }[] }[]) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(LineChart);
    fixture.componentRef.setInput('series', series);
    fixture.detectChanges();
    return fixture;
  }

  it('draws one path per series', () => {
    const fixture = render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 1 }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 2 }, { date: '2026-01-02', value: 3 }] },
    ]);
    expect(fixture.nativeElement.querySelectorAll('path.series')).toHaveLength(2);
  });

  it('shows no legend for a single series -- the panel heading already names it', () => {
    const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 0 }] }]);
    expect(fixture.nativeElement.querySelector('.legend')).toBeNull();
  });

  it('shows a legend entry per series once there is more than one', () => {
    const fixture = render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 0 }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 1 }] },
    ]);
    const entries = fixture.nativeElement.querySelectorAll('.legend .entry');
    expect(entries).toHaveLength(2);
    expect(entries[0].textContent).toContain('ui');
    expect(entries[1].textContent).toContain('bot');
  });

  it('draws the reference line when one is given', () => {
    const fixture = render([{ name: 'wr', points: [{ date: '2026-01-01', value: 60 }] }]);
    expect(fixture.nativeElement.querySelector('line.reference')).toBeNull();
    fixture.componentRef.setInput('referenceLine', 80);
    fixture.componentRef.setInput('yDomain', { min: 0, max: 100 });
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('line.reference')).not.toBeNull();
  });

  it('renders nothing rather than throwing when every series is empty', () => {
    expect(() => render([{ name: 'ui', points: [] }])).not.toThrow();
  });

  it('shows a tooltip with every series value at the hovered date', () => {
    const fixture = render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 10 }, { date: '2026-01-11', value: 20 }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 1 }, { date: '2026-01-11', value: 2 }] },
    ]);
    const svg = fixture.nativeElement.querySelector('svg');
    svg.dispatchEvent(new MouseEvent('pointermove', { clientX: 0, bubbles: true }));
    fixture.detectChanges();
    const tooltip = fixture.nativeElement.querySelector('.tooltip');
    expect(tooltip).not.toBeNull();
    expect(tooltip.textContent).toContain('ui');
    expect(tooltip.textContent).toContain('bot');
  });

  it('hides the tooltip on pointer leave', () => {
    const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 10 }] }]);
    const svg = fixture.nativeElement.querySelector('svg');
    svg.dispatchEvent(new MouseEvent('pointermove', { clientX: 0, bubbles: true }));
    fixture.detectChanges();
    svg.dispatchEvent(new MouseEvent('pointerleave', { bubbles: true }));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.tooltip')).toBeNull();
  });
});

describe('seriesPath gaps (v208)', () => {
  const x = (d: string) => ({ a: 0, b: 0.25, c: 0.5, d: 1 } as Record<string, number>)[d];
  const y = (v: number) => v / 10;
  it('lifts the pen at a null and never draws it as zero', () => {
    const path = seriesPath({ name: 's', points: [
      { date: 'a', value: 1 }, { date: 'b', value: null }, { date: 'c', value: 2 }, { date: 'd', value: 3 }] }, x, y);
    expect(path).toBe('M 0.0000 0.9000 M 0.5000 0.8000 L 1.0000 0.7000');
  });
  it('starts at the first real point and returns nothing for an all-null series', () => {
    expect(seriesPath({ name: 's', points: [{ date: 'a', value: null }, { date: 'b', value: 5 }] }, x, y))
      .toBe('M 0.2500 0.5000');
    expect(seriesPath({ name: 's', points: [{ date: 'a', value: null }] }, x, y)).toBe('');
  });
  it('draws a gap-free series exactly as before', () => {
    expect(seriesPath({ name: 's', points: [{ date: 'a', value: 0 }, { date: 'd', value: 10 }] }, x, y))
      .toBe('M 0.0000 1.0000 L 1.0000 0.0000');
  });
});

describe('LineChart v208 options', () => {
  type S = { name: string; points: { date: string; value: number | null; day?: number | null; flag?: string }[];
             color?: string; dashed?: boolean };
  function render(series: S[], detail = false) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(LineChart);
    fixture.componentRef.setInput('series', series);
    fixture.componentRef.setInput('valueFormat', (v: number) => `${v.toFixed(2)}%`);
    if (detail) fixture.componentRef.setInput('hoverDetail', true);
    fixture.detectChanges();
    return fixture;
  }
  const hover = (fixture: ReturnType<typeof render>, type = 'pointermove') => {
    fixture.nativeElement.querySelector('svg').dispatchEvent(new MouseEvent(type, { clientX: 0, bubbles: true }));
    fixture.detectChanges();
    const rows = fixture.nativeElement.querySelectorAll('.tooltip strong, .tooltip > div');
    return Array.from(rows, (row) => (row as HTMLElement).textContent?.trim()).join(' ');
  };
  beforeEach(() => TestBed.resetTestingModule());

  it('takes a colour token per series and dashes on request, legend included', () => {
    const fixture = render([
      { name: 'acct', color: '--chart-3', points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 1 }] },
      { name: 'dep', color: '--chart-3', dashed: true, points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: 2 }] },
    ]);
    const paths = fixture.nativeElement.querySelectorAll('path.series');
    expect(paths[0].getAttribute('stroke')).toBe(token('--chart-3'));
    expect(paths[0].getAttribute('stroke-dasharray')).toBeNull();
    expect(paths[1].getAttribute('stroke-dasharray')).toBe('6 4');
    expect(fixture.nativeElement.querySelectorAll('.legend .entry i.dashed')).toHaveLength(1);
  });

  it('keeps the palette colour by index when no colour is given', () => {
    const fixture = render([{ name: 'a', points: [{ date: '2026-01-01', value: 1 }] },
                            { name: 'b', points: [{ date: '2026-01-01', value: 2 }] }]);
    expect(fixture.nativeElement.querySelectorAll('path.series')[1].getAttribute('stroke')).toBe(token('--chart-2'));
  });

  it('ignores nulls when scaling and never writes NaN', () => {
    const fixture = render([{ name: 'a', points: [
      { date: '2026-01-01', value: 1 }, { date: '2026-01-02', value: null }, { date: '2026-01-03', value: 3 }] }]);
    expect(fixture.nativeElement.querySelector('path.series').getAttribute('d')).not.toContain('NaN');
  });

  it('shows "No data to chart." when every value is null', () => {
    const fixture = render([{ name: 'a', points: [{ date: '2026-01-01', value: null }] }]);
    expect(fixture.nativeElement.querySelector('svg')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('No data to chart.');
  });

  it('keeps the plain tooltip when hoverDetail is off, leaving a null point out', () => {
    const text = hover(render([
      { name: 'ui', points: [{ date: '2026-01-01', value: 10, day: 1 }] },
      { name: 'gap', points: [{ date: '2026-01-01', value: null }] },
      { name: 'bot', points: [{ date: '2026-01-01', value: 1 }] },
    ]));
    expect(text).toBe('2026-01-01 ui: 10.00% bot: 1.00%');
  });

  it('gives cumulative, day % and flag per series when hoverDetail is on, and — for a gap', () => {
    const text = hover(render([
      { name: 'Bot · account', points: [{ date: '2026-01-01', value: 1.5, day: 0.25 }] },
      { name: 'SPY', points: [{ date: '2026-01-01', value: 2, day: -0.5, flag: 'proxy' }] },
      { name: 'Bot · deployed', points: [{ date: '2026-01-01', value: null, flag: 'gap' }] },
    ], true));
    expect(text).toBe('2026-01-01 Bot · account: 1.50% (day 0.25%) SPY: 2.00% (day -0.50%) · proxy Bot · deployed: — · gap');
  });

  it('keeps touch inspection after release and leave, while mouse leave dismisses it', () => {
    const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 10 }] }]);
    const svg = fixture.nativeElement.querySelector('svg');
    const dispatch = (type: string, pointerType: string) => {
      const event = new MouseEvent(type, { clientX: 0, bubbles: true });
      Object.defineProperty(event, 'pointerType', { value: pointerType });
      svg.dispatchEvent(event);
      fixture.detectChanges();
    };
    dispatch('pointerdown', 'touch');
    expect(fixture.nativeElement.querySelector('.tooltip')?.textContent ?? '').toContain('ui: 10.00%');
    dispatch('pointerup', 'touch');
    dispatch('pointerleave', 'touch');
    expect(fixture.nativeElement.querySelector('.tooltip')?.textContent ?? '').toContain('ui: 10.00%');
    dispatch('pointermove', 'mouse');
    dispatch('pointerleave', 'mouse');
    expect(fixture.nativeElement.querySelector('.tooltip')).toBeNull();
  });

  it('opens the tooltip on a tap', () => {
    const fixture = render([{ name: 'ui', points: [{ date: '2026-01-01', value: 10 }] }]);
    expect(hover(fixture, 'pointerdown')).toContain('ui: 10.00%');
  });
  it('draws a 0 baseline only when zeroLine is set', () => {
    const off = render([{ name: 'a', points: [{ date: '2026-01-01', value: -1 }, { date: '2026-01-02', value: 2 }] }]);
    expect(off.nativeElement.querySelector('line.zero')).toBeNull();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const on = TestBed.createComponent(LineChart);
    on.componentRef.setInput('series', [{ name: 'a', points: [{ date: '2026-01-01', value: -1 }, { date: '2026-01-02', value: 2 }] }]);
    on.componentRef.setInput('zeroLine', true);
    on.detectChanges();
    expect(on.nativeElement.querySelector('line.zero')).not.toBeNull();
  });

});
