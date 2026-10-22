import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { ACCOUNT_LABEL } from './equity-candles.model';
import { TradingPerformance } from './trading-performance';

installMatchMediaPolyfill();

describe('trading performance panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
      ],
    });
  });

  function render(inputs: Record<string, unknown>) {
    const f = TestBed.createComponent(TradingPerformance);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  function card(el: HTMLElement, label: string): HTMLElement {
    return [...el.querySelectorAll<HTMLElement>('sb-metric-card')]
      .find((c) => c.querySelector('.label')?.textContent?.trim() === label)!;
  }

  function tint(c: HTMLElement): 'pos' | 'neg' | null {
    if (c.classList.contains('tint-pos')) return 'pos';
    return c.classList.contains('tint-neg') ? 'neg' : null;
  }

  function row(el: HTMLElement, label: string): HTMLElement {
    return [...el.querySelectorAll<HTMLElement>('.mobile-summary > div')]
      .find((d) => d.querySelector('span')?.textContent?.trim() === label)!;
  }

  it('judges win rate and payoff together against break-even', () => {
    // payoff 1.0 -> break-even 50%; the band is +/-0.5 pp.
    const pair = (winRate: number, winRateN = 12) => {
      const el = render({ winRate, winRateN, payoffRatio: 1, currency: '€', scope: 'today' });
      return [tint(card(el, 'Win rate')), tint(card(el, 'Payoff ratio'))];
    };
    expect(pair(60)).toEqual(['pos', 'pos']);
    expect(pair(40)).toEqual(['neg', 'neg']);
    expect(pair(50.3)).toEqual([null, null]);
    expect(pair(60, 4)).toEqual([null, null]);
  });

  it('tints open P&L, expectancy and realised by sign, and never a dash', () => {
    const el = render({ openPnlPct: 1.2, expectancyR: -0.16, realizedAmount: null,
                        currency: '€', scope: 'today' });
    expect(tint(card(el, 'Open P&L'))).toBe('pos');
    expect(tint(card(el, 'Expectancy'))).toBe('neg');
    const realised = card(el, 'Realised today');
    expect(tint(realised)).toBeNull();
    expect(realised.querySelector('.value')!.classList.contains('absent')).toBe(true);
  });

  it('warns on risk used near the cap and marks it bad at the cap', () => {
    const risk = (riskUsedPct: number) => card(
      render({ riskUsedPct, riskCapPct: 6, currency: '€', scope: 'today' }), 'Risk used');
    expect(risk(3).querySelector('.value')!.className).not.toMatch(/\b(pos|neg|warn)\b/);
    expect(risk(5).querySelector('.value')!.classList.contains('warn')).toBe(true);
    expect(tint(risk(5))).toBeNull();
    expect(tint(risk(6))).toBe('neg');
  });

  it('never judges open trades or average confidence', () => {
    const el = render({ openTrades: 3, avgConfidence: 4.5, currency: '€', scope: 'today' });
    for (const label of ['Open trades', 'Avg confidence']) {
      expect(tint(card(el, label))).toBeNull();
      expect(card(el, label).querySelector('.value')!.className).not.toMatch(/\b(pos|neg|warn)\b/);
    }
  });

  it('gives the phone summary rows the same tones', () => {
    const el = render({ changePct: -0.4, winRate: 60, winRateN: 12, payoffRatio: 1, expectancyR: 0.2,
                        realizedAmount: 15, riskUsedPct: 5, riskCapPct: 6, openTrades: 2,
                        realizedLabel: 'Realised today', currency: '€', scope: 'today' });
    expect(row(el, 'Today').getAttribute('data-tone')).toBe('neg');
    expect(row(el, 'Win rate').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Payoff').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Expectancy').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Realised today').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Risk').getAttribute('data-tone')).toBe('warn');
    expect(row(el, 'Open').getAttribute('data-tone')).toBeNull();
  });

  it('states what the account is under the KPI grid, in the chart caption\'s words', () => {
    const el = render({ currency: '€', scope: 'today' });
    const captions = [...el.querySelectorAll('.account')]
      .map((p) => p.textContent?.trim());
    expect(captions.filter((text) => text === ACCOUNT_LABEL).length).toBe(2);
    expect(el.querySelector('.mobile-summary + .account')).not.toBeNull();
  });

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

  it('puts Today / All days in one segmented control on the header line (v179 §3.3)', () => {
    const el = render({ scope: 'today' });
    const control = el.querySelector('sb-panel header sb-segmented')!;
    expect(control).not.toBeNull();
    const segments = [...control.querySelectorAll<HTMLButtonElement>('.segment')];
    expect(segments.map((s) => s.textContent!.trim())).toEqual(['Today', 'All days']);
    expect(segments.map((s) => s.getAttribute('aria-pressed'))).toEqual(['true', 'false']);
    expect(el.querySelector('sb-panel header sb-control-row')).toBeNull();
    expect(el.querySelector('[data-scope]')).toBeNull();
  });

  it('emits the scope the user picked', () => {
    const f = TestBed.createComponent(TradingPerformance);
    f.componentRef.setInput('scope', 'today');
    f.detectChanges();
    let picked: string | undefined;
    f.componentInstance.scopeChange.subscribe((s: string) => (picked = s));
    [...(f.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>('sb-segmented .segment')]
      .find((s) => s.textContent!.trim() === 'All days')!.click();
    expect(picked).toBe('all');
  });

  it('presses no segment for a scope the toggle never sets', () => {
    const el = render({ scope: 'active' });
    const pressed = [...el.querySelectorAll('sb-panel header sb-segmented .segment')].map((s) => s.getAttribute('aria-pressed'));
    expect(pressed).toEqual(['false', 'false']);
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

  it('gives the portfolio block the full panel width at every width (v172 candles)', () => {
    // A `minmax(0, 1fr) auto` split left the chart a ~240px column beside the KPI grid.
    const combined = src.match(/\.combined\s*\{[^}]*\}/)?.[0] ?? '';
    expect(combined).toMatch(/grid-template-columns:\s*minmax\(0,\s*1fr\);/);
    expect(src).not.toMatch(/\.combined\s*\{\s*display:\s*none/);
  });

  it('uses only declared breakpoint values', () => {
    const allowed = new Set(['639', '1023', '1439', '1919', '640', '1024', '1440', '1920']);
    const widths = [...src.matchAll(/\(\s*(?:max|min)-width:\s*(\d+)px\s*\)/g)].map((m) => m[1]);
    expect(widths.filter((w) => !allowed.has(w))).toEqual([]);
  });
});
