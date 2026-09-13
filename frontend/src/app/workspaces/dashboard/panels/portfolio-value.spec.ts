import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { PortfolioValue } from './portfolio-value';

describe('portfolio value panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(PortfolioValue);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows the balance as the hero figure with its currency', () => {
    const el = render({ balance: 997480.01, changePct: 0.36, points: [1, 2], currency: '€' });
    expect(el.querySelector('.figure')?.textContent).toContain('997,480.01');
    expect(el.querySelector('.figure')?.textContent).toContain('€');
  });

  it('tones the day change by sign', () => {
    expect(render({ balance: 1, changePct: 0.36, points: [], currency: '€' })
      .querySelector('.change')?.classList.contains('pos')).toBe(true);
    expect(render({ balance: 1, changePct: -0.36, points: [], currency: '€' })
      .querySelector('.change')?.classList.contains('neg')).toBe(true);
  });

  it('renders no value rather than a zero when the balance is missing', () => {
    const el = render({ balance: null, changePct: null, points: [], currency: '€' });
    expect(el.querySelector('.figure')?.textContent).not.toContain('0.00');
    expect(el.querySelector('.change')).toBeNull();
  });

  it('omits the sparkline entirely when there are no points', () => {
    expect(render({ balance: 1, changePct: 0, points: [], currency: '€' })
      .querySelector('sb-sparkline')).toBeNull();
    expect(render({ balance: 1, changePct: 0, points: [1, 2, 3], currency: '€' })
      .querySelector('sb-sparkline')).not.toBeNull();
  });

  const THIRTY = Array.from({ length: 30 }, (_, i) => i);

  it('renders the one 30-day series without a range picker', () => {
    const el = render({ balance: 1, changePct: 0, points: THIRTY, currency: '€' });
    expect(el.querySelector('sb-sparkline')).not.toBeNull();
    expect(el.querySelector('.equity-range')).toBeNull();
  });

  it('renders no equity-range controls', () => {
    const el = render({ balance: 1, changePct: 0, points: THIRTY, currency: '€' });
    const labels = [...el.querySelectorAll('button')].map((b) => b.textContent!.trim());
    expect(labels).not.toContain('1W');
    expect(labels).not.toContain('1M');
    expect(labels).not.toContain('ALL');
  });

  it('keeps the complete input series for the sparkline', () => {
    const f = TestBed.createComponent(PortfolioValue);
    f.componentRef.setInput('balance', 1);
    f.componentRef.setInput('changePct', 0);
    f.componentRef.setInput('currency', '€');
    f.componentRef.setInput('points', THIRTY);
    f.detectChanges();
    expect(f.componentInstance.points()).toBe(THIRTY);
    expect((f.nativeElement as HTMLElement).querySelector('sb-sparkline')).not.toBeNull();
  });
});
