import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Histogram, HistogramBin } from './histogram';

/* SR51 — extracted from the Analytics workspace while adding the grid results,
 * because SR54 needs the same shape twice more (the P&L distribution and the
 * holding-period distribution) and because Analytics' component stylesheet was
 * over its 4 kB budget with it inline.
 *
 * The one behaviour worth pinning is the scaling. Against the TOTAL rather than
 * the tallest bin, a bin holding two observations out of ninety is two percent
 * of the track and invisible — and in a P&L distribution that tail is the
 * finding.
 */

function render(bins: HistogramBin[]) {
  const fixture = TestBed.createComponent(Histogram);
  fixture.componentRef.setInput('bins', bins);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

const widths = (element: HTMLElement) =>
  [...element.querySelectorAll('.fill')].map((fill) =>
    (fill as HTMLElement).style.width,
  );

describe('Histogram', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('scales against the tallest bin, not the total', () => {
    const element = render([
      { label: '0.0R', count: 90 },
      { label: '+2.0R', count: 2 },
    ]);
    // Against the total the second bar would be ~2%. Against the tallest bin
    // it is ~2.2% — still small, but it is drawn, and it is the tail.
    expect(widths(element)[0]).toBe('100%');
    expect(parseFloat(widths(element)[1])).toBeCloseTo(2.22, 1);
  });

  it('draws every bar at full width when all bins are equal', () => {
    expect(widths(render([
      { label: 'a', count: 3 },
      { label: 'b', count: 3 },
    ]))).toEqual(['100%', '100%']);
  });

  it('does not divide by zero on an all-empty set of bins', () => {
    // A bin with a zero count is a real thing to render — it says "nothing
    // landed here", which is different from the bin not existing.
    expect(widths(render([{ label: 'a', count: 0 }]))).toEqual(['0%']);
  });

  it('marks a negative bin by its label sign, by default', () => {
    const element = render([
      { label: '-1.0R', count: 4 },
      { label: '+1.0R', count: 4 },
    ]);
    const fills = element.querySelectorAll('.fill');
    expect(fills[0].classList.contains('negative')).toBe(true);
    expect(fills[1].classList.contains('negative')).toBe(false);
  });

  it('takes the caller own predicate for scales that are not signed', () => {
    const fixture = TestBed.createComponent(Histogram);
    fixture.componentRef.setInput('bins', [{ label: '0-2 days', count: 1 }]);
    fixture.componentRef.setInput('isNegative', () => true);
    fixture.detectChanges();

    const fill = (fixture.nativeElement as HTMLElement).querySelector('.fill');
    expect(fill?.classList.contains('negative')).toBe(true);
  });

  it('renders the label and the count for every bin', () => {
    const text = render([{ label: '+0.5R', count: 7 }]).textContent ?? '';
    expect(text).toContain('+0.5R');
    expect(text).toContain('7');
  });

  it('renders nothing at all for no bins', () => {
    expect(render([]).querySelectorAll('li')).toHaveLength(0);
  });
});
