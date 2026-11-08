import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { ExposureStrip, exposureBars } from './exposure-strip';

const DATES = ['2026-01-01', '2026-01-11', '2026-01-21'];

describe('exposureBars', () => {
  it('centres each bar on the chart x scale and skips a missing day', () => {
    const rects = exposureBars(DATES, [
      { date: '2026-01-01', pct: 50, approx: false },
      { date: '2026-01-11', pct: null, approx: false },
      { date: '2026-01-21', pct: 100, approx: true },
    ]);
    expect(rects.map((r) => r.date)).toEqual(['2026-01-01', '2026-01-21']);
    expect(rects[0].width).toBeCloseTo(160, 5);            // 600 / 3 × 0.8
    expect(rects[0].x).toBe(0);                            // clamped at the left edge
    expect(rects[1].x).toBeCloseTo(440, 5);                // clamped at the right edge
    expect(rects[0].height).toBeCloseTo(20, 5);            // 50 % of 40
    expect(rects[1].height).toBeCloseTo(40, 5);
    expect(rects[1].approx).toBe(true);
  });
  it('places a middle bar on its date and caps the height at 100 %', () => {
    const [mid] = exposureBars(DATES, [{ date: '2026-01-11', pct: 140, approx: false }]);
    expect(mid.x + mid.width / 2).toBeCloseTo(300, 5);
    expect(mid.height).toBeCloseTo(40, 5);
    expect(mid.pct).toBe(140);
  });
  it('returns nothing without dates, and ignores a bar on a date the chart lacks', () => {
    expect(exposureBars([], [{ date: '2026-01-01', pct: 10, approx: false }])).toEqual([]);
    expect(exposureBars(DATES, [{ date: '2026-02-01', pct: 10, approx: false }])).toEqual([]);
  });
});

describe('ExposureStrip', () => {
  function render(dates: string[], bars: { date: string; pct: number | null; approx: boolean }[]) {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const fixture = TestBed.createComponent(ExposureStrip);
    fixture.componentRef.setInput('dates', dates);
    fixture.componentRef.setInput('bars', bars);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }
  it('draws one labelled bar per real day, approximated ones marked', () => {
    const el = render(DATES, [{ date: '2026-01-01', pct: 41.24, approx: true }, { date: '2026-01-11', pct: null, approx: false }]);
    expect(el.querySelector('svg')?.getAttribute('aria-label')).toBe('Exposure: share of equity in open trades per session');
    const rects = el.querySelectorAll('rect.bar');
    expect(rects).toHaveLength(1);
    expect(rects[0].classList.contains('approx')).toBe(true);
    expect(rects[0].querySelector('title')?.textContent).toBe('2026-01-01: 41.2% (approx.)');
  });
  it('renders nothing when there are no dates', () => {
    expect(render([], []).querySelector('svg')).toBeNull();
  });
});
