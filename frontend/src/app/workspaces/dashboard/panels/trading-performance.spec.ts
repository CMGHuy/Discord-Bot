import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { TradingPerformance } from './trading-performance';

describe('trading performance panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(TradingPerformance);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('shows all eight metrics', () => {
    const el = render({
      openPnlPct: 0.36, winRate: 49.1, expectancyR: -0.16, avgConfidence: 4.0,
      realizedAmount: 0, realizedLabel: 'Realised today', openTrades: 1,
      riskUsedPct: 0, riskCapPct: 6, payoffRatio: 2.34, currency: '€', scope: 'today',
    });
    const labels = [...el.querySelectorAll('sb-metric-card')]
      .map((c) => c.textContent ?? '');
    expect(labels.length).toBe(8);
    expect(el.textContent).toContain('Payoff ratio');
    expect(el.textContent).toContain('2.34');
  });

  it('emits the scope the user picked', () => {
    const f = TestBed.createComponent(TradingPerformance);
    f.componentRef.setInput('scope', 'today');
    f.detectChanges();
    let picked: string | undefined;
    f.componentInstance.scopeChange.subscribe((s: string) => (picked = s));
    (f.nativeElement as HTMLElement)
      .querySelector<HTMLButtonElement>('[data-scope="all"]')!.click();
    expect(picked).toBe('all');
  });

  it('renders a missing payoff ratio as no value, never as zero', () => {
    // null means "not enough outcomes yet". 0 would claim wins are worthless
    // against losses -- a real and very different statement.
    const el = render({ payoffRatio: null, riskCapPct: 6, currency: '€', scope: 'today' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Payoff ratio'))!;
    expect(card.textContent).not.toContain('0.00');
  });

  it('carries no risk gauge -- that is the cut Risk & Exposure content', () => {
    const el = render({ riskUsedPct: 0, riskCapPct: 6, currency: '€', scope: 'today' });
    expect(el.querySelector('sb-donut')).toBeNull();
    expect(el.textContent).not.toContain('Remaining risk');
  });
});
