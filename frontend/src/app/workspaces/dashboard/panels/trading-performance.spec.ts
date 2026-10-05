import { readFileSync } from 'node:fs';
import { join } from 'node:path';

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

  it('phone summary carries win rate, expectancy, payoff and realised', () => {
    // At <=640px the eight-card grid is display:none, so the phone summary is
    // the only place these four figures can appear.
    const el = render({
      winRate: 49.1, winRateN: 12, expectancyR: -0.16, payoffRatio: 2.34,
      realizedAmount: 5, realizedLabel: 'Realised today', currency: '€', scope: 'today',
    });
    const text = el.querySelector('.mobile-summary')!.textContent ?? '';
    expect(text).toContain('Win rate');
    expect(text).toContain('49.1%');
    expect(text).toContain('Expectancy');
    expect(text).toContain('-0.16R');
    expect(text).toContain('Payoff');
    expect(text).toContain('2.34');
    expect(text).toContain('Realised today');
  });

  it('shows the open P&L amount under the percentage', () => {
    const el = render({ openPnlPct: 2.5, openPnlAmount: 1234.5, currency: '€', scope: 'today' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Open P&L'))!;
    expect(card.textContent).toContain('2.50%');
    expect(card.textContent).toContain('1,234.50');
  });

  it('colours the open P&L amount by its sign, like the percentage', () => {
    const subOf = (amountValue: number) => {
      const el = render({ openPnlPct: 1, openPnlAmount: amountValue, currency: '€', scope: 'today' });
      const card = [...el.querySelectorAll('sb-metric-card')]
        .find((c) => c.textContent?.includes('Open P&L'))!;
      return card.querySelector('.sub')!;
    };
    expect(subOf(50).classList.contains('pos')).toBe(true);
    expect(subOf(-50).classList.contains('neg')).toBe(true);
    expect(subOf(0).classList.contains('pos') || subOf(0).classList.contains('neg')).toBe(false);
  });

  it('explains an absent figure in today scope instead of a bare dash', () => {
    const el = render({ payoffRatio: null, realizedAmount: null, currency: '€', scope: 'today' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Payoff ratio'))!;
    expect(card.textContent).toContain('none closed today');
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

describe('trading-performance tablet band', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/dashboard/panels/trading-performance.ts'),
    'utf8',
  );

  it('has a treatment between sm and md, not only below sm', () => {
    // 640 alone leaves iPad portrait on the desktop layout: the 4-up KPI
    // grid's 560px floor starves the equity block to ~40px and the portfolio
    // figure breaks into fragments.
    expect(src).toMatch(/@media\s*\(\s*max-width:\s*1023px\s*\)/);
  });

  it('never leaves a four-track KPI grid below md', () => {
    const tabletBlock = src.match(/@media\s*\(\s*max-width:\s*1023px\s*\)\s*\{[\s\S]*?\n\s{0,4}\}/)?.[0] ?? '';
    expect(tabletBlock).toMatch(/grid-template-columns:\s*repeat\(2,/);
  });

  it('uses only declared breakpoint values', () => {
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
