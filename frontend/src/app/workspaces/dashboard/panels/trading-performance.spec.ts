import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { By } from '@angular/platform-browser';
import { describe, expect, it, beforeEach } from 'vitest';

import { EquityCandlesStore } from '../../../stores/equity-candles.store';
import { equityCandlesStoreStub } from '../../../testing/equity-candles-store.stub';
import { installMatchMediaPolyfill } from '../../../testing/match-media-polyfill';
import { ViewportService } from '../../../ui/breakpoints';
import { SCOPE_PRESETS, ScopePreset, ScopeSelection, TimeWindow, rangeChipLabel } from './equity-range.model';
import { KPI_HELP, PANEL_HELP } from './panel-help';
import { PortfolioValue } from './portfolio-value';
import { TradingPerformance, presetLabel } from './trading-performance';

installMatchMediaPolyfill();

const preset = (value: ScopePreset): ScopeSelection => ({ kind: 'preset', preset: value });
/** 3 Sep – 18 Oct on the New York clock: `to` is the exclusive 19 Oct midnight. */
const RANGE_WINDOW: TimeWindow = { from: '2026-09-03T04:00:00.000Z', to: '2026-10-19T04:00:00.000Z' };
const RANGE: ScopeSelection = { kind: 'range', window: RANGE_WINDOW };
const TODAY_BLOCK = { amount: 15, pct: 0.4, n: 3, wins: 2, losses: 1 };

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

  it('has no Risk used card or row (dropped 2026-10-23)', () => {
    const el = render({ currency: '€' });
    expect(card(el, 'Risk used')).toBeUndefined();
    expect(row(el, 'Risk')).toBeUndefined();
    expect(el.textContent).not.toContain('Risk used');
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
                        todayRealized: TODAY_BLOCK, openTrades: 2, currency: '€' });
    expect(row(el, 'Today').getAttribute('data-tone')).toBe('neg');
    expect(row(el, 'Win rate').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Payoff').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Expectancy').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Realised today').getAttribute('data-tone')).toBe('pos');
    expect(row(el, 'Open').getAttribute('data-tone')).toBeNull();
  });

  it('carries no "Paper account" caption under the KPI grid (dropped 2026-10-23)', () => {
    const el = render({ currency: '€' });
    expect(el.querySelector('.account')).toBeNull();
    expect(el.textContent).not.toContain('Paper account');
  });

  it('shows all seven metrics in Today mode', () => {
    const el = render({
      openPnlPct: 0.36, winRate: 49.1, expectancyR: -0.16, avgConfidence: 4.0,
      todayRealized: TODAY_BLOCK, openTrades: 1,
      payoffRatio: 2.34, currency: '€',
    });
    const labels = [...el.querySelectorAll('sb-metric-card')]
      .map((c) => c.textContent ?? '');
    expect(labels.length).toBe(7);
    expect(el.textContent).toContain('Payoff ratio');
    expect(el.textContent).toContain('2.34');
  });

  it('phone summary carries win rate, expectancy, payoff and realised', () => {
    // At <=640px the seven-card grid is display:none, so the phone summary is
    // the only place these four figures can appear.
    const el = render({
      winRate: 49.1, winRateN: 12, expectancyR: -0.16, payoffRatio: 2.34,
      todayRealized: TODAY_BLOCK, currency: '€',
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
    expect(chips.map((c) => c.textContent!.trim())).toEqual(SCOPE_PRESETS.map(presetLabel));
    expect(chips[0].textContent!.trim()).toBe('Today');
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
      const el = render({ selection, openTrades: 2, openPnlPct: 1, openPnlAmount: 10, currency: '€' });
      return ['Open P&L', 'Open trades']
        .map((label) => card(el, label).querySelector('.sub')?.textContent?.trim() ?? null);
    };
    const day = subs(preset('1D'));
    expect(day[1]).toBeNull();
    expect(subs(preset('1M'))).toEqual([`now · ${day[0]}`, 'now']);
    expect(subs(RANGE)[1]).toBe('now');
    expect(subs(preset('All'))[1]).toBe('now');
  });

  it('marks the phone summary\'s Open row "now" outside 1D', () => {
    const labels = (selection: ScopeSelection) =>
      [...render({ selection, currency: '€' }).querySelectorAll('.mobile-summary > div > span')]
        .map((s) => s.textContent!.replace(/\s+/g, ' ').trim());
    expect(labels(preset('5D'))).toEqual(expect.arrayContaining(['Open · now']));
    expect(labels(preset('1D'))).toEqual(expect.arrayContaining(['Open']));
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
    const el = render({ payoffRatio: null, currency: '€' });
    const card = [...el.querySelectorAll('sb-metric-card')]
      .find((c) => c.textContent?.includes('Payoff ratio'))!;
    expect(card.textContent).not.toContain('0.00');
  });

  it('carries no risk gauge -- that is the cut Risk & Exposure content', () => {
    const el = render({ currency: '€' });
    expect(el.querySelector('sb-donut')).toBeNull();
    expect(el.textContent).not.toContain('Remaining risk');
  });

  describe('loading rings', () => {
    const busyLabels = (el: HTMLElement) =>
      [...el.querySelectorAll('sb-metric-card.loading .label')].map((l) => l.textContent!.trim());

    it('ring the five window-scoped cards while a refetch is in flight, and not the "now" cards', () => {
      const el = render({ loading: true, currency: '€' });
      expect(busyLabels(el)).toEqual(
        ['Win rate', 'Expectancy', 'Payoff ratio', 'Realised today', 'Avg confidence']);
      expect(card(el, 'Win rate').querySelector('sb-spinner')).not.toBeNull();
      expect(card(el, 'Open P&L').querySelector('sb-spinner')).toBeNull();
      expect(card(el, 'Open trades').querySelector('sb-spinner')).toBeNull();
    });

    it('show nothing when idle', () => {
      const el = render({ currency: '€' });
      expect(busyLabels(el)).toEqual([]);
      expect(el.querySelector('sb-spinner')).toBeNull();
    });

    it('also ring the phone summary rows, dimming their figures, but not Portfolio, Today or Open', () => {
      const el = render({ loading: true, currency: '€' });
      const busyRows = [...el.querySelectorAll('.mobile-summary > div.busy > span')]
        .map((s) => s.textContent!.replace(/\s+/g, ' ').trim());
      expect(busyRows).toEqual(['Win rate', 'Expectancy', 'Payoff', 'Realised today']);
      expect(el.querySelectorAll('.mobile-summary sb-spinner')).toHaveLength(4);
      expect(row(el, 'Open').classList.contains('busy')).toBe(false);
      expect(row(el, 'Portfolio').classList.contains('busy')).toBe(false);
    });
  });

  describe('Today and Period modes', () => {
    const labels = (el: HTMLElement) =>
      [...el.querySelectorAll('sb-metric-card .label')].map((l) => l.textContent!.trim());
    const sub = (c: HTMLElement) => c.querySelector('.sub')?.textContent?.trim() ?? null;

    it("Today: one realised card, today's amount with % and counts beneath", () => {
      const el = render({ todayRealized: TODAY_BLOCK, realizedAmount: 999, currency: '€' });
      expect(labels(el).filter((l) => l.startsWith('Realised'))).toEqual(['Realised today']);
      const today = card(el, 'Realised today');
      expect(today.textContent).toContain('15.00');
      expect(sub(today)).toBe('+0.40% · 3 closed · 2W 1L');
      expect(tint(today)).toBe('pos');
    });

    it('Period: eight cards, Realised today still today and Realised in period naming its window', () => {
      const el = render({ selection: preset('1M'), todayRealized: TODAY_BLOCK, realizedAmount: -40, currency: '€' });
      expect(labels(el)).toHaveLength(8);
      expect(card(el, 'Realised today').textContent).toContain('15.00');
      const period = card(el, 'Realised in period');
      expect(period.textContent).toContain('40.00');
      expect(sub(period)).toBe('1M');
      expect(tint(period)).toBe('neg');
    });

    it('names a range, All days, and an empty period in the period card', () => {
      const periodSub = (selection: ScopeSelection, realizedAmount: number | null) =>
        sub(card(render({ selection, realizedAmount, currency: '€' }), 'Realised in period'));
      expect(periodSub(RANGE, 5)).toBe(rangeChipLabel(RANGE_WINDOW));
      expect(periodSub(preset('All'), 5)).toBe('All days');
      expect(periodSub(preset('All'), null)).toBe('All days');
      expect(periodSub(preset('3M'), null)).toBe('3M · none closed in range');
    });

    it("says none closed today, leaves out a missing %, and shows no sub before today's figures land", () => {
      expect(sub(card(render({ todayRealized: { ...TODAY_BLOCK, amount: null, n: 0, wins: 0, losses: 0 }, currency: '€' }), 'Realised today')))
        .toBe('none closed today');
      expect(sub(card(render({ todayRealized: { ...TODAY_BLOCK, pct: null }, currency: '€' }), 'Realised today')))
        .toBe('3 closed · 2W 1L');
      expect(sub(card(render({ currency: '€' }), 'Realised today'))).toBeNull();
    });

    it("rings Realised today on today's own fetch in Period, and on the scoped fetch in Today", () => {
      const busy = (inputs: Record<string, unknown>) =>
        card(render({ ...inputs, currency: '€' }), 'Realised today').classList.contains('loading');
      expect(busy({ selection: preset('1M'), loading: true })).toBe(false);
      expect(busy({ selection: preset('1M'), todayLoading: true })).toBe(true);
      expect(busy({ loading: true })).toBe(true);
      expect(busy({ todayLoading: true })).toBe(false);
    });

    it('phone summary: Realised today always, Realised in period only in Period', () => {
      const rows = (selection: ScopeSelection) =>
        [...render({ selection, todayRealized: TODAY_BLOCK, realizedAmount: 3, currency: '€' })
          .querySelectorAll('.mobile-summary > div > span')].map((s) => s.textContent!.trim());
      expect(rows(preset('1D'))).toContain('Realised today');
      expect(rows(preset('1D'))).not.toContain('Realised in period');
      expect(rows(RANGE)).toEqual(expect.arrayContaining(['Realised today', 'Realised in period']));
    });
  });

  describe('tooltips', () => {
    it('describe the panel and every KPI card', () => {
      const el = render({ currency: '€' });
      expect(el.querySelector('sb-panel')!.getAttribute('title')).toBe(PANEL_HELP.tradingPerformance);
      const titles = new Map([...el.querySelectorAll('sb-metric-card')].map((c) => [
        c.querySelector('.label')!.textContent!.trim(), c.getAttribute('title')]));
      expect(titles.get('Open P&L')).toBe(KPI_HELP.openPnl);
      expect(titles.get('Win rate')).toBe(KPI_HELP.winRate);
      expect(titles.get('Expectancy')).toBe(KPI_HELP.expectancy);
      expect(titles.get('Payoff ratio')).toBe(KPI_HELP.payoffRatio);
      expect(titles.get('Realised today')).toBe(KPI_HELP.realizedToday);
      expect(titles.get('Open trades')).toBe(KPI_HELP.openTrades);
      expect(titles.get('Avg confidence')).toBe(KPI_HELP.avgConfidence);
    });
  });

  it('passes the chart Latest press up to the scope owner', () => {
    const f = TestBed.createComponent(TradingPerformance);
    f.detectChanges();
    let presses = 0;
    f.componentInstance.viewReset.subscribe(() => (presses += 1));
    f.debugElement.query(By.directive(PortfolioValue)).componentInstance.viewReset.emit();
    expect(presses).toBe(1);
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

  it('widens the seventh card to fill its row, so seven cards leave no hole', () => {
    expect(src).toMatch(/\.grid > :last-child:nth-child\(4n \+ 3\)\s*\{\s*grid-column:\s*span 2;\s*\}/);
  });

  it('lets the odd last phone summary row span both columns', () => {
    expect(src).toMatch(/\.mobile-summary > div:last-child:nth-child\(odd\)\s*\{\s*grid-column:\s*1 \/ -1;\s*\}/);
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
    expect(select.options[0].textContent!.trim()).toBe('Today');
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
