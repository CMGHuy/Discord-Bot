import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it, beforeEach } from 'vitest';

import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { ACCOUNT_LABEL } from './equity-candles.model';
import { ViewportService } from '../../../ui/breakpoints';
import { SCOPE_PRESETS, ScopePreset, ScopeSelection, TimeWindow, rangeChipLabel } from './equity-range.model';
import { TradingPerformance } from './trading-performance';

installMatchMediaPolyfill();

const preset = (value: ScopePreset): ScopeSelection => ({ kind: 'preset', preset: value });
/** 3 Sep – 18 Oct on the New York clock: `to` is the exclusive 19 Oct midnight. */
const RANGE_WINDOW: TimeWindow = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
const RANGE: ScopeSelection = { kind: 'range', window: RANGE_WINDOW };

describe('trading performance panel', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
        { provide: ViewportService, useValue: { isPhone: signal(false) } },
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
      const el = render({ winRate, winRateN, payoffRatio: 1, currency: '€' });
      return [tint(card(el, 'Win rate')), tint(card(el, 'Payoff ratio'))];
    };
    expect(pair(60)).toEqual(['pos', 'pos']);
    expect(pair(40)).toEqual(['neg', 'neg']);
    expect(pair(50.3)).toEqual([null, null]);
    expect(pair(60, 4)).toEqual([null, null]);
  });

  it('tints open P&L, expectancy and realised by sign, and never a dash', () => {
    const el = render({ openPnlPct: 1.2, expectancyR: -0.16, realizedAmount: null,
                        currency: '€' });
    expect(tint(card(el, 'Open P&L'))).toBe('pos');
    expect(tint(card(el, 'Expectancy'))).toBe('neg');
    const realised = card(el, 'Realised today');
    expect(tint(realised)).toBeNull();
    expect(realised.querySelector('.value')!.classList.contains('absent')).toBe(true);
  });

  it('warns on risk used near the cap and marks it bad at the cap', () => {
    const risk = (riskUsedPct: number) => card(
      render({ riskUsedPct, riskCapPct: 6, currency: '€' }), 'Risk used');
    expect(risk(3).querySelector('.value')!.className).not.toMatch(/\b(pos|neg|warn)\b/);
    expect(risk(5).querySelector('.value')!.classList.contains('warn')).toBe(true);
    expect(tint(risk(5))).toBeNull();
    expect(tint(risk(6))).toBe('neg');
  });

  it('never judges open trades or average confidence', () => {
    const el = render({ openTrades: 3, avgConfidence: 4.5, currency: '€' });
    for (const label of ['Open trades', 'Avg confidence']) {
      expect(tint(card(el, label))).toBeNull();
      expect(card(el, label).querySelector('.value')!.className).not.toMatch(/\b(pos|neg|warn)\b/);
    }
  });

  it('gives the phone summary rows the same tones', () => {
    const el = render({ changePct: -0.4, winRate: 60, winRateN: 12, payoffRatio: 1, expectancyR: 0.2,
                        realizedAmount: 15, riskUsedPct: 5, riskCapPct: 6, openTrades: 2,
                        realizedLabel: 'Realised today', currency: '€' });
    expect(row(el, 'Today').getAttribute('data-tone')).toBe('neg');
    expect(row(el, 'Win rate').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Payoff').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Expectancy').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Realised today').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Risk').getAttribute('data-tone')).toBe('warn');
    expect(row(el, 'Open').getAttribute('data-tone')).toBeNull();
  });

  it('states what the account is under the KPI grid, in the chart caption\'s words', () => {
    const el = render({ currency: '€' });
    const captions = [...el.querySelectorAll('.account')]
      .map((p) => p.textContent?.trim());
    expect(captions.filter((text) => text === ACCOUNT_LABEL).length).toBe(2);
    expect(el.querySelector('.mobile-summary + .account')).not.toBeNull();
  });

  it('shows all eight metrics', () => {
    const el = render({
      openPnlPct: 0.36, winRate: 49.1, expectancyR: -0.16, avgConfidence: 4.0,
      realizedAmount: 0, realizedLabel: 'Realised today', openTrades: 1,
      riskUsedPct: 0, riskCapPct: 6, payoffRatio: 2.34, currency: '€',
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
      realizedAmount: 5, realizedLabel: 'Realised today', currency: '€',
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
    const el = render({ openPnlPct: 2.5, openPnlAmount: 1234.5, currency: '€' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Open P&L'))!;
    expect(card.textContent).toContain('2.50%');
    expect(card.textContent).toContain('1,234.50');
  });

  it('colours the open P&L amount by its sign, like the percentage', () => {
    const subOf = (amountValue: number) => {
      const el = render({ openPnlPct: 1, openPnlAmount: amountValue, currency: '€' });
      const card = [...el.querySelectorAll('sb-metric-card')]
        .find((c) => c.textContent?.includes('Open P&L'))!;
      return card.querySelector('.sub')!;
    };
    expect(subOf(50).classList.contains('pos')).toBe(true);
    expect(subOf(-50).classList.contains('neg')).toBe(true);
    expect(subOf(0).classList.contains('pos') || subOf(0).classList.contains('neg')).toBe(false);
  });

  it('explains an absent figure in today scope instead of a bare dash', () => {
    const el = render({ payoffRatio: null, realizedAmount: null, currency: '€' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Payoff ratio'))!;
    expect(card.textContent).toContain('none closed today');
  });

  it('offers the eight presets as chips above phone width, the active one pressed', () => {
    const el = render({ selection: preset('3M'), currency: '€' });
    const chips = [...el.querySelectorAll<HTMLButtonElement>('[data-preset]')];
    expect(chips.map((c) => c.textContent!.trim())).toEqual([...SCOPE_PRESETS]);
    expect(chips.filter((c) => c.getAttribute('aria-pressed') === 'true')
      .map((c) => c.getAttribute('data-preset'))).toEqual(['3M']);
    expect(el.querySelector('sb-select')).toBeNull();
    expect(el.querySelector('.range-chip')).toBeNull();
  });

  it('emits the preset the partner picked', () => {
    const f = TestBed.createComponent(TradingPerformance);
    f.detectChanges();
    let picked: ScopePreset | undefined;
    f.componentInstance.presetChange.subscribe((value: ScopePreset) => (picked = value));
    (f.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('[data-preset="YTD"]')!.click();
    expect(picked).toBe('YTD');
  });

  it('shows a Range chip with the visible dates while the scope is a hand-picked range', () => {
    const el = render({ selection: RANGE, currency: '€' });
    const chip = el.querySelector('.range-chip')!;
    expect(chip.textContent!.replace(/\s+/g, ' ').trim()).toBe(`Range ${rangeChipLabel(RANGE_WINDOW)}`);
    expect(chip.getAttribute('aria-current')).toBe('true');
    expect(el.querySelectorAll('[data-preset][aria-pressed="true"]')).toHaveLength(0);
  });

  it('marks the point-in-time cards "now" outside 1D', () => {
    const subs = (selection: ScopeSelection) => {
      const el = render({ selection, openTrades: 2, openPnlPct: 1, openPnlAmount: 10,
                          riskUsedPct: 1, riskCapPct: 6, currency: '€' });
      return ['Open P&L', 'Open trades', 'Risk used']
        .map((label) => card(el, label).querySelector('.sub')?.textContent?.trim() ?? null);
    };
    const day = subs(preset('1D'));
    expect(day[1]).toBeNull();
    expect(subs(preset('1M'))).toEqual([`now · ${day[0]}`, 'now', `now · ${day[2]}`]);
    expect(subs(RANGE)[1]).toBe('now');
    expect(subs(preset('All'))[1]).toBe('now');
  });

  it('marks the phone summary\'s Open and Risk rows "now" outside 1D', () => {
    const labels = (selection: ScopeSelection) =>
      [...render({ selection, currency: '€' }).querySelectorAll('.mobile-summary > div > span')]
        .map((s) => s.textContent!.replace(/\s+/g, ' ').trim());
    expect(labels(preset('5D'))).toEqual(expect.arrayContaining(['Open · now', 'Risk · now']));
    expect(labels(preset('1D'))).toEqual(expect.arrayContaining(['Open', 'Risk']));
  });

  it('says why a figure is absent, in the scope\'s own words', () => {
    const hint = (selection: ScopeSelection) =>
      card(render({ selection, payoffRatio: null, currency: '€' }), 'Payoff ratio')
        .querySelector('.sub')?.textContent?.trim() ?? null;
    expect(hint(preset('1D'))).toBe('none closed today');
    expect(hint(preset('3M'))).toBe('none closed in range');
    expect(hint(RANGE)).toBe('none closed in range');
    expect(hint(preset('All'))).toBeNull();
  });

  it('dims the last figures with a hint while a range refetch has failed, keeping the Range chip', () => {
    const el = render({ selection: RANGE, stale: true, currency: '€' });
    expect(el.querySelector('.grid')!.classList.contains('stale')).toBe(true);
    expect(el.querySelector('.mobile-summary')!.classList.contains('stale')).toBe(true);
    expect(el.querySelector('.stale-hint')!.textContent).toContain('showing the last figures');
    expect(el.querySelector('.range-chip')).not.toBeNull();
    expect(render({ currency: '€' }).querySelector('.stale-hint')).toBeNull();
  });

  it('renders a missing payoff ratio as no value, never as zero', () => {
    // null means "not enough outcomes yet". 0 would claim wins are worthless
    // against losses -- a real and very different statement.
    const el = render({ payoffRatio: null, riskCapPct: 6, currency: '€' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Payoff ratio'))!;
    expect(card.textContent).not.toContain('0.00');
  });

  it('carries no risk gauge -- that is the cut Risk & Exposure content', () => {
    const el = render({ riskUsedPct: 0, riskCapPct: 6, currency: '€' });
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
    // v186: colsMd carries the tablet band through the strip's shared grid.
    expect(src).toMatch(/<sb-stat-strip class="grid"[^>]*\[colsMd\]="2"/);
  });

  it('never leaves a four-track KPI grid below md', () => {
    expect(src).toMatch(/<sb-stat-strip class="grid"[^>]*\[cols\]="4"/);
    // The strip owns the columns; the panel declares no grid of its own.
    expect(src).not.toMatch(/\.grid\s*\{[^}]*grid-template-columns/);
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

describe('trading performance scope on a phone (v181 §1)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
        { provide: ViewportService, useValue: { isPhone: signal(true) } },
      ],
    });
  });

  function mount(selection: ScopeSelection) {
    const f = TestBed.createComponent(TradingPerformance);
    f.componentRef.setInput('selection', selection);
    f.detectChanges();
    return f;
  }

  it('is one native dropdown below 640px, never the chip row', () => {
    const el = mount(preset('1D')).nativeElement as HTMLElement;
    const select = el.querySelector<HTMLSelectElement>('sb-select.preset-select select')!;
    expect([...select.options].map((o) => o.value)).toEqual([...SCOPE_PRESETS]);
    expect(el.querySelector('[data-preset]')).toBeNull();
  });

  it('selects a newly added Range entry when a chart drag replaces the phone preset', () => {
    const f = mount(preset('1D'));
    const select = (f.nativeElement as HTMLElement)
      .querySelector<HTMLSelectElement>('sb-select.preset-select select')!;
    expect(select.value).toBe('1D');

    f.componentRef.setInput('selection', RANGE);
    f.detectChanges();

    expect(select.value).toBe('Range');
    expect(select.selectedOptions[0].textContent!.trim())
      .toBe(`Range · ${rangeChipLabel(RANGE_WINDOW)}`);

    f.componentRef.setInput('selection', preset('1Y'));
    f.detectChanges();
    expect(select.value).toBe('1Y');
    expect([...select.options].some((option) => option.value === 'Range')).toBe(false);
  });

  it('lists the hand-picked range as its own entry and emits a preset picked from the list', () => {
    const f = mount(RANGE);
    const select = (f.nativeElement as HTMLElement)
      .querySelector<HTMLSelectElement>('sb-select.preset-select select')!;
    const last = select.options[select.options.length - 1];
    expect([last.value, last.textContent!.trim()])
      .toEqual(['Range', `Range · ${rangeChipLabel(RANGE_WINDOW)}`]);
    let picked: ScopePreset | undefined;
    f.componentInstance.presetChange.subscribe((value: ScopePreset) => (picked = value));
    select.value = '6M';
    select.dispatchEvent(new Event('change'));
    expect(picked).toBe('6M');
  });
});

describe('trading performance KPI strip (v186 D3)', () => {
  const src = readFileSync(
    join(process.cwd(), 'src/app/workspaces/dashboard/panels/trading-performance.ts'),
    'utf8',
  );

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: EquityCandlesStore, useValue: equityCandlesStoreStub() },
        { provide: ViewportService, useValue: { isPhone: signal(false) } },
      ],
    });
  });

  function render(inputs: Record<string, unknown>): HTMLElement {
    const f = TestBed.createComponent(TradingPerformance);
    for (const [key, value] of Object.entries(inputs)) f.componentRef.setInput(key, value);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('puts every KPI card in one stat strip: four columns from md, two on a tablet', () => {
    const el = render({ currency: '€' });
    const strip = el.querySelector<HTMLElement>('sb-stat-strip.grid');
    expect(strip).not.toBeNull();
    expect(strip!.style.getPropertyValue('--strip-cols')).toBe('4');
    expect(strip!.style.getPropertyValue('--strip-cols-md')).toBe('2');
    expect(strip!.querySelector('.sb-strip-grid')!.classList).toContain('sb-strip-fixed');
    const cards = el.querySelectorAll('sb-metric-card');
    expect(cards.length).toBeGreaterThanOrEqual(7);
    expect(strip!.querySelectorAll('sb-metric-card')).toHaveLength(cards.length);
  });

  it('dims the strip host when the figures are stale, and only then', () => {
    expect(render({ stale: true, currency: '€' }).querySelector('sb-stat-strip')!.classList)
      .toContain('stale');
    expect(render({ currency: '€' }).querySelector('sb-stat-strip')!.classList)
      .not.toContain('stale');
  });

  it('keeps the stale dim and the phone hand-off to the summary on the strip host', () => {
    expect(src).toMatch(/\.grid\.stale, \.mobile-summary\.stale \{ opacity: 0\.55; \}/);
    const phone = src.match(/@media \(max-width: 639px\) \{[\s\S]*?\.mobile-summary \{/)?.[0] ?? '';
    expect(phone).toMatch(/\.grid \{ display: none; \}/);
  });

  it('draws no frame or gap of its own around the cards', () => {
    expect(src).not.toMatch(/\.grid\s*\{[^}]*gap:/);
    // The projected cards are grandchildren of the strip host.
    expect(src).not.toMatch(/\.grid\s*>/);
    if (/nth-child\(4n \+ 3\)/.test(src)) {
      expect(src).toMatch(/\.grid sb-metric-card:last-child:nth-child\(4n \+ 3\) \{ grid-column: span 2; \}/);
    }
  });
});
