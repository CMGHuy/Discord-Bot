import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { AnalyticsBenchmark, BookScope } from '../../../api/models';
import { AnalyticsStore, DEFAULT_SCOPE } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { PreferencesStore } from '../../../stores/preferences.store';
import { BenchmarkTab, DEFAULT_VISIBLE, POLL_MS } from './benchmark';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BENCHMARK_FIXTURE, benchmarkWith } from './benchmark.fixture';
import {
  dailyColumns, dailyVisible, captureTiles, beatLine, CAPTURE_FORMULA, TAX_LINE, FOOTNOTE,
  statGroups, chartSeries, chartDates, pointFlag, markerNotes, stripLine, ALPHA_CELLS_HINT,
  CHIP_LABELS, PAPER_LINE, SERIES_ORDER, etClock, isMixedCurrency, signedPct, stateStamp, statusNote, todayCells,
} from './benchmark';

describe('benchmark helpers (v208)', () => {
  it('fixes the chip labels, the price indexes labelled in the label itself', () => {
    expect(SERIES_ORDER.map((k) => CHIP_LABELS[k])).toEqual(
      ['Bot · account', 'Bot · deployed', 'SPY', 'QQQ', 'Nasdaq Comp. (price)', 'Dow (price)']);
    expect(PAPER_LINE).toBe('Paper trades only. Returns are pre-tax and exclude fees and slippage; '
      + 'indexes are buy-and-hold. Not a recommendation or forecast.');
  });
  it('formats signed percentages and never turns null into 0%', () => {
    expect([signedPct(1.02), signedPct(-0.12), signedPct(0), signedPct(null), signedPct(6.1, 1)])
      .toEqual(['+1.02%', '−0.12%', '0.00%', '—', '+6.1%']);
  });
  it('stamps the time in New York on both sides of the DST change', () => {
    expect(etClock('2026-11-05T15:35:00+00:00')).toBe('10:35');
    expect(etClock('2026-10-14T19:05:00+00:00')).toBe('15:05');
  });
  it('stamps open, closed, pre-open and no-session differently', () => {
    expect(stateStamp(BENCHMARK_FIXTURE)).toBe('as of 10:35 ET');
    expect(stateStamp(benchmarkWith({ session_state: 'closed', today: { ...BENCHMARK_FIXTURE.today!, final: true } })))
      .toBe('2026-11-05 · final');
    expect(stateStamp(benchmarkWith({ session_state: 'pre', today: { session: '2026-11-04', final: true, lines: {} } })))
      .toBe('2026-11-04 · final');
    expect(stateStamp(benchmarkWith({ today: { session: null as never, final: false, lines: {} } }))).toBe('no session yet');
    expect(stateStamp(benchmarkWith({ today: null }))).toBe('no session yet');
  });
  it('gives every line a Today cell, bot cells unrealised while open, null as —', () => {
    expect(todayCells(BENCHMARK_FIXTURE).map((c) => [c.label, c.value, c.caption])).toEqual([
      ['Bot · account', '+0.31%', 'unrealised · paper'], ['Bot · deployed', '+0.82%', 'unrealised · paper'],
      ['SPY', '+1.02%', null], ['QQQ', '+1.40%', null], ['Nasdaq Comp. (price)', '—', null], ['Dow (price)', '−0.55%', null]]);
    // Open session with no live sample yet: the bot cell is —, never 0%.
    const noSample = todayCells(benchmarkWith({ today: { session: '2026-11-05', final: false,
      lines: { bot_account: { pct: null, final: false }, SPY: { pct: 0.2, final: false } } } }));
    expect(noSample.map((c) => c.value)).toEqual(['—', '+0.20%']);
    const closed = todayCells(benchmarkWith({ session_state: 'closed',
      today: { session: '2026-11-05', final: true, lines: { bot_account: { pct: 0.1, final: true } } } }));
    expect(closed).toEqual([{ key: 'bot_account', label: 'Bot · account', value: '+0.10%', caption: null }]);
    expect(todayCells(benchmarkWith({ today: null }))).toEqual([]);
  });
  it('names the two empty states, and nothing when bars are fine', () => {
    expect(statusNote(BENCHMARK_FIXTURE)).toBeNull();
    expect(statusNote(benchmarkWith({ benchmarks_status: 'empty' }))).toBe('No benchmark data yet');
    expect(statusNote(benchmarkWith({ benchmarks_status: 'stale' }))).toBe('Benchmarks not updating — refresher is off');
  });
  it('flags a non-USD account or any non-USD ticker', () => {
    expect(isMixedCurrency(BENCHMARK_FIXTURE)).toBe(false);
    expect(isMixedCurrency(benchmarkWith({ account_currency: 'EUR' }))).toBe(true);
    expect(isMixedCurrency(benchmarkWith({ mixed_tickers: ['SAP.DE'] }))).toBe(true);
  });
});

export function stubStore(payload: AnalyticsBenchmark | null, over: Record<string, unknown> = {}) {
  return {
    benchmark: signal(payload), benchmarkError: signal<string | null>(null), benchmarkRange: signal('3M'),
    benchmarkCapture: signal('SPY'), benchmarkLoadingMore: signal(false), scope: signal<BookScope>({ ...DEFAULT_SCOPE }),
    setBenchmarkRange: vi.fn(), setBenchmarkCapture: vi.fn(), refreshBenchmark: vi.fn(),
    loadMoreBenchmarkDaily: vi.fn(), reload: vi.fn(), setScope: vi.fn(), ...over,
  };
}
export function renderTab(store: ReturnType<typeof stubStore>) {
  TestBed.configureTestingModule({ providers: [
    provideZonelessChangeDetection(), provideRouter([]),
    { provide: AnalyticsStore, useValue: store },
    { provide: ConnectionStore, useValue: { currency: signal('$') } },
    { provide: PreferencesStore, useValue: { values: () => ({}), update: () => {} } },
  ] });
  const fixture = TestBed.createComponent(BenchmarkTab);
  fixture.detectChanges();
  return { fixture, el: fixture.nativeElement as HTMLElement };
}
export const text = (el: Element | null) => (el?.textContent ?? '').replace(/\s+/g, ' ').trim();

describe('BenchmarkTab frame (v208)', () => {
  beforeEach(() => TestBed.resetTestingModule());
  afterEach(() => vi.useRealTimers());

  it('renders the Today card, the paper line under it, then range and chips', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const order = [...el.querySelectorAll('.today, .paper, .range, .series-chips')].map((n) => n.classList[0]);
    expect(order).toEqual(['today', 'paper', 'range', 'series-chips']);
    expect(text(el.querySelector('.today'))).toContain('as of 10:35 ET');
    expect(text(el.querySelector('.today'))).toContain('unrealised · paper');
    expect(text(el.querySelector('.paper'))).toBe(PAPER_LINE);
    expect(el.querySelector('.banner')).toBeNull();
  });
  it('shows the mixed-currency banner with its exact copy', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ account_currency: 'EUR' })));
    expect(text(el.querySelector('.banner'))).toBe(
      'Benchmark assumes a USD account trading USD stocks — figures may be mixed-currency');
  });
  it('labels the chips exactly, four on by default, the deployed chip carrying its caveat', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const chips = [...el.querySelectorAll<HTMLButtonElement>('.series-chips button')];
    expect(chips.map((b) => text(b.querySelector('.label')))).toEqual(SERIES_ORDER.map((k) => CHIP_LABELS[k]));
    expect(chips.filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset['key']))
      .toEqual([...DEFAULT_VISIBLE]);
    expect(text(chips[1])).toContain('on capital in trades — not account return');
    expect(chips[1].querySelector('.swatch.dashed')).not.toBeNull();
  });
  it('toggles a chip on and off', () => {
    const { fixture, el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const dow = el.querySelector<HTMLButtonElement>('.series-chips button[data-key="^DJI"]')!;
    dow.click(); fixture.detectChanges();
    expect(dow.getAttribute('aria-pressed')).toBe('true');
    dow.click(); fixture.detectChanges();
    expect(dow.getAttribute('aria-pressed')).toBe('false');
  });
  it('picks a preset, and shows none selected while a custom scope date is set', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    const { fixture, el } = renderTab(store);
    expect(text(el.querySelector('.range button[aria-pressed="true"]'))).toBe('3M');
    store.scope.set({ ...DEFAULT_SCOPE, from: '2026-09-01' });
    fixture.detectChanges();
    expect(el.querySelector('.range button[aria-pressed="true"]')).toBeNull();
    fixture.componentInstance.pickRange('1M');
    expect(store.setScope).toHaveBeenCalledWith({ from: null, to: null });
    expect(store.setBenchmarkRange).toHaveBeenCalledWith('1M');
  });
  it('picks a preset without touching the scope when no custom date is set', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    renderTab(store).fixture.componentInstance.pickRange('All');
    expect(store.setScope).not.toHaveBeenCalled();
    expect(store.setBenchmarkRange).toHaveBeenCalledWith('All');
  });
  it('says when the range was clamped to the live book', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ range: { ...BENCHMARK_FIXTURE.range, clamped: true } })));
    expect(text(el.querySelector('.range'))).toContain('Live book since 2026-08-07');
  });
  it('shows "No benchmark data yet" when there are no bars', () => {
    expect(text(renderTab(stubStore(benchmarkWith({ benchmarks_status: 'empty' }))).el)).toContain('No benchmark data yet');
  });
  it('shows the refresher-off note with the last stored session', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ benchmarks_status: 'stale' })));
    expect(text(el.querySelector('.stale'))).toBe('Benchmarks not updating — refresher is off · last stored session 2026-11-04');
  });
  it('shows a retryable error above the last data', () => {
    const store = stubStore(BENCHMARK_FIXTURE, { benchmarkError: signal('Server error') });
    const { el } = renderTab(store);
    expect(el.querySelector('sb-panel-error')).not.toBeNull();
    expect(el.querySelector('.today')).not.toBeNull();
  });
  it('polls every five minutes only while the session is open and the page visible', () => {
    vi.useFakeTimers();
    const store = stubStore(BENCHMARK_FIXTURE);
    const { fixture } = renderTab(store);
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
    const hidden = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
    hidden.mockRestore();
    store.benchmark.set(benchmarkWith({ session_state: 'closed' }));
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
    store.benchmark.set(BENCHMARK_FIXTURE);
    fixture.destroy();
    vi.advanceTimersByTime(POLL_MS);
    expect(store.refreshBenchmark).toHaveBeenCalledTimes(1);
  });
});
describe('benchmark stat strip (v208)', () => {
  const ALL = new Set(['bot_account', 'bot_deployed', 'SPY', 'QQQ']);
  const groups = statGroups(BENCHMARK_FIXTURE, ALL, '$');
  const tile = (key: string, label: string) => groups.find((g) => g.key === key)!.tiles.find((t) => t.label === label)!;

  it('builds one group per visible line, in chip order, with its caveat', () => {
    expect(groups.map((g) => [g.label, g.note])).toEqual([
      ['Bot · account', null], ['Bot · deployed', 'on capital in trades — not account return · 38% approx.'],
      ['SPY', 'total return'], ['QQQ', 'total return']]);
    expect(statGroups(BENCHMARK_FIXTURE, new Set(['^DJI']), '$').map((g) => [g.label, g.note]))
      .toEqual([['Dow (price)', 'price only']]);
  });
  it('formats every tile with its N, drawdowns negative, money in the account symbol', () => {
    expect([tile('bot_account', 'Total').value, tile('bot_account', 'Total').sample, tile('bot_account', 'Total').tone])
      .toEqual(['+0.58%', 4, 'pos']);
    expect(tile('bot_account', 'Max drawdown').value).toBe('−0.32%');
    expect(tile('bot_account', 'Drawdown ($)').value).toBe('−$41.50');
    expect(tile('bot_account', 'Losing streak').value).toBe('2 sessions');
    expect(tile('SPY', 'Lead vs SPY').value).toBe('−0.82 pp');
  });
  it('shows — and the reason verbatim below every guard, never 0', () => {
    expect([tile('bot_account', 'Sharpe (rf = 0)').value, tile('bot_account', 'Sharpe (rf = 0)').secondary])
      .toEqual(['—', 'needs ≥ 20 sessions']);
    expect(tile('QQQ', 'Sharpe (rf = 0)').secondary).toBe('no variance');
    expect([tile('bot_deployed', 'Drawdown ($)').value, tile('bot_deployed', 'Drawdown ($)').secondary])
      .toEqual(['—', 'account line only']);
    expect([tile('SPY', 'Alpha (rf = 0)').value, tile('SPY', 'Alpha (rf = 0)').secondary])
      .toEqual(['—', 'needs ≥ 60 sessions']);
  });
  it('gives beta its SE and alpha its t-stat, plain with "1 of 24 cells" unless it is the headline', () => {
    expect(tile('QQQ', 'Beta').value).toBe('β 0.42 ± 0.18');
    const alpha = tile('QQQ', 'Alpha (rf = 0)');
    expect([alpha.value, alpha.bold, alpha.sample]).toEqual(['α +6.1% (t 0.9)', false, 61]);
    expect(alpha.hint).toContain(ALPHA_CELLS_HINT);
    expect(ALPHA_CELLS_HINT).toBe('1 of 24 cells');
    const headline = statGroups(benchmarkWith({ vs: { ...BENCHMARK_FIXTURE.vs, SPY: { ...BENCHMARK_FIXTURE.vs.SPY!,
      alpha: { value: 4.2, t: 1.1, n: 80, reason: null, headline: true } } } }), ALL, '$');
    const spyAlpha = headline.find((g) => g.key === 'SPY')!.tiles.find((t) => t.label === 'Alpha (rf = 0)')!;
    expect([spyAlpha.value, spyAlpha.bold]).toEqual(['α +4.2% (t 1.1)', true]);
    expect(spyAlpha.hint).not.toContain(ALPHA_CELLS_HINT);
  });
  it('says how many sessions and that beta/alpha are not evidence of edge', () => {
    expect(stripLine(BENCHMARK_FIXTURE)).toBe('5 sessions, paper book — beta/alpha are indicative, not evidence of edge.');
  });
});

describe('benchmark chart (v208)', () => {
  it('draws only the visible lines, tokens and dash from the line, a missing session as a gap', () => {
    const series = chartSeries(BENCHMARK_FIXTURE, new Set(['bot_account', 'bot_deployed', 'SPY']));
    expect(series.map((s) => [s.name, s.color, !!s.dashed])).toEqual([
      ['Bot · account', '--accent', false], ['Bot · deployed', '--accent', true], ['SPY', '--chart-2', false]]);
    const acct = series[0].points;
    expect(acct[0]).toEqual({ date: '2026-10-28', value: 0, day: null, flag: undefined });
    expect(acct[2].value).toBeNull();
    expect(acct[2].flag).toBe('missing session');
    expect(acct[3].flag).toBe('covers 2 sessions');
  });
  it('flags proxy, approximate exposure and clipped days in the tooltip', () => {
    const base = BENCHMARK_FIXTURE.series[0].points[1];
    expect(pointFlag({ ...base, proxy: true })).toBe('proxy ETF');
    expect(pointFlag({ ...base, approx: true, clipped: true })).toBe('exposure approximate · clipped at −100%');
    expect(pointFlag(base)).toBeUndefined();
  });
  it('gives the exposure strip the chart’s own sorted, de-duplicated dates', () => {
    const dates = chartDates(chartSeries(BENCHMARK_FIXTURE, new Set(['SPY', 'QQQ'])));
    expect(dates).toEqual(['2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04']);
    expect(chartDates([])).toEqual([]);
  });
  it('names each base_balance break under the chart', () => {
    expect(markerNotes(BENCHMARK_FIXTURE)).toEqual([
      'Base balance changed on 2026-11-03: that session is left out of every stat and the account line carries flat.']);
  });
});

describe('BenchmarkTab strip and chart (v208)', () => {
  beforeEach(() => TestBed.resetTestingModule());
  it('puts the strip and the chart after the chips, the headline alpha bold', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const order = [...el.querySelectorAll('.today, .range, .series-chips, .stats, .chart')].map((n) => n.classList[0]);
    expect(order).toEqual(['today', 'range', 'series-chips', 'stats', 'chart']);
    expect(text(el.querySelector('.stats .strip-line'))).toContain('not evidence of edge');
    expect(el.querySelectorAll('.chart sb-line-chart')).toHaveLength(1);
    expect(el.querySelector('.chart sb-exposure-strip')).not.toBeNull();
    expect(text(el.querySelector('.chart .markers'))).toContain('2026-11-03');
  });
  it('increases the figure weight only for the headline alpha tile', () => {
    const payload = benchmarkWith({ vs: { ...BENCHMARK_FIXTURE.vs,
      SPY: { ...BENCHMARK_FIXTURE.vs.SPY!,
        alpha: { value: 4.2, t: 1.1, n: 80, reason: null, headline: true } } } });
    const { el } = renderTab(stubStore(payload));
    const tiles = [...el.querySelectorAll<HTMLElement>('.stats .tile')];
    const emphasized = tiles.filter((tile) => getComputedStyle(tile).getPropertyValue('--figure-weight').trim() === '700');
    expect(emphasized).toHaveLength(1);
    expect(text(emphasized[0])).toContain('Alpha (rf = 0)');
    expect(text(emphasized[0].closest('.group')!.querySelector('h3'))).toBe('SPY total return');
    expect(emphasized[0].classList.contains('bold')).toBe(true);
  });
  it('follows the chips: hiding SPY drops its stat group and its line', () => {
    const { fixture, el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    el.querySelector<HTMLButtonElement>('.series-chips button[data-key="SPY"]')!.click();
    fixture.detectChanges();
    expect([...el.querySelectorAll('.stats .group h3')].map((h) => text(h))).not.toContain('SPY');
    expect(fixture.componentInstance.chart().map((s) => s.name)).not.toContain('SPY');
  });
  it('renders no strip or chart when there are no bars', () => {
    const { el } = renderTab(stubStore(benchmarkWith({ benchmarks_status: 'empty' })));
    expect(el.querySelector('.stats')).toBeNull();
    expect(el.querySelector('.chart')).toBeNull();
    expect(el.querySelector('.daily')).toBeNull();
    expect(el.querySelector('.capture')).toBeNull();
    expect(el.querySelector('.footnote')).toBeNull();
  });
});

describe('benchmark daily table and capture (v208)', () => {
  const cols = dailyColumns('SPY');
  const cell = (key: string, i: number) => cols.find((c) => c.key === key)!.value!(BENCHMARK_FIXTURE.daily[i]);

  it('shows a missing session as — and a spanning row as covering N sessions', () => {
    expect([cell('date', 0), cell('bot_account', 0), cell('SPY', 0), cell('exposure', 0), cell('open', 0), cell('beat', 0)])
      .toEqual(['2026-11-04', '−0.12%', '+0.40%', '38.0%', 2, 'No']);
    expect([cell('date', 3), cell('bot_account', 3), cell('SPY', 3), cell('exposure', 3), cell('beat', 3)])
      .toEqual(['2026-10-30 · no bot sample', '—', '+0.30%', '—', '—']);
    expect([cell('date', 2), cell('beat', 2)]).toEqual(['2026-11-02 · covers 2 sessions', '—']);
    expect(cell('bot_deployed', 1)).toBe('—');
  });
  it('names the Beat? column after the capture index and follows the chips', () => {
    expect(cols.find((c) => c.key === 'beat')!.header).toBe('Beat? (vs SPY)');
    expect(dailyColumns('^DJI').find((c) => c.key === 'beat')!.header).toBe('Beat? (vs Dow (price))');
    expect(cols[0].key).toBe('date');
    expect(dailyVisible(new Set(['bot_account', 'SPY']))).toEqual(['date', 'bot_account', 'SPY', 'exposure', 'open', 'beat']);
  });
  it('shows capture as — with the 10+10 reason below the guard, and the formula in the tooltip', () => {
    const [up, down, ratio] = captureTiles(BENCHMARK_FIXTURE);
    expect([up.label, up.value, up.sample, up.secondary]).toEqual(
      ['Up capture', '—', 2, 'needs ≥ 10 index-up and ≥ 10 index-down sessions']);
    expect(up.hint).toBe(CAPTURE_FORMULA);
    expect(CAPTURE_FORMULA).toBe('Σ bot return on index-up days ÷ Σ index return on those days (sum ratio, not the geometric form)');
    expect([down.sample, ratio.sample]).toEqual([1, 3]);
  });
  it('formats computed capture and keeps "index flat" verbatim', () => {
    const p = benchmarkWith({ capture: { ...BENCHMARK_FIXTURE.capture,
      up_pct: { value: 85.24, n: 12, reason: null }, down_pct: { value: 61.0, n: 11, reason: null },
      ratio: { value: 1.3974, n: 23, reason: null } } });
    expect(captureTiles(p).map((t) => t.value)).toEqual(['85.2%', '61.0%', '1.40×']);
    const flat = benchmarkWith({ capture: { ...BENCHMARK_FIXTURE.capture,
      down_pct: { value: null, n: 0, reason: 'index flat' } } });
    expect(captureTiles(flat)[1].secondary).toBe('index flat');
  });
  it('counts beats as description, not edge', () => {
    expect(beatLine(BENCHMARK_FIXTURE)).toBe(
      'Bot · account beat SPY on 1 of 2 up days and 1 of 1 down days — descriptive, not evidence of edge.');
  });
  it('carries the tax sentence and the price-only note in the footnote', () => {
    expect(TAX_LINE).toBe('Swing turnover is taxed as short-term gains, so after-tax results would differ from this chart.');
    expect(FOOTNOTE).toContain(TAX_LINE);
    expect(FOOTNOTE[0]).toContain('price indexes');
  });
});

describe('BenchmarkTab table, capture and layout (v208)', () => {
  beforeEach(() => TestBed.resetTestingModule());
  afterEach(() => vi.restoreAllMocks());

  for (const width of [390, 820, 1440]) {
    it(`keeps the approved order and pins the date column at ${width}px`, () => {
      vi.spyOn(window, 'innerWidth', 'get').mockReturnValue(width);
      const { el } = renderTab(stubStore(BENCHMARK_FIXTURE));
      const order = [...el.querySelectorAll('.today, .range, .series-chips, .stats, .chart, .daily, .capture, .footnote')]
        .map((n) => n.classList[0]);
      expect(order).toEqual(['today', 'range', 'series-chips', 'stats', 'chart', 'daily', 'capture', 'footnote']);
      expect(el.querySelector('.daily sb-data-table .compact-list')).toBeNull();
      expect(text(el.querySelector('.daily sb-data-table th.pin'))).toContain('Date');
      expect(el.querySelector('.daily sb-data-table .wrap')!.classList.contains('phone')).toBe(width < 640);
    });
  }
  it('loads older sessions from the server, and says nothing when there are none', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    const { el } = renderTab(store);
    el.querySelector<HTMLButtonElement>('.daily button.more')!.click();
    expect(store.loadMoreBenchmarkDaily).toHaveBeenCalledTimes(1);
    TestBed.resetTestingModule();
    expect(renderTab(stubStore(benchmarkWith({ daily_has_more: false }))).el.querySelector('.daily button.more')).toBeNull();
  });
  it('disables the button while a page is loading', () => {
    const { el } = renderTab(stubStore(BENCHMARK_FIXTURE, { benchmarkLoadingMore: signal(true) }));
    expect(el.querySelector<HTMLButtonElement>('.daily button.more')!.disabled).toBe(true);
  });
  it('switches the capture index through the store', () => {
    const store = stubStore(BENCHMARK_FIXTURE);
    const { fixture, el } = renderTab(store);
    const qqq = [...el.querySelectorAll<HTMLButtonElement>('.capture button')].find((b) => text(b) === 'QQQ')!;
    qqq.click();
    fixture.detectChanges();
    expect(store.setBenchmarkCapture).toHaveBeenCalledWith('QQQ');
    expect(text(el.querySelector('.capture .beat'))).toContain('not evidence of edge');
  });
  it('sizes the controls for touch and stacks the tiles in two columns on phone', () => {
    const src = readFileSync(join(process.cwd(), 'src/app/workspaces/analytics/tabs/benchmark.ts'), 'utf8');
    expect(src).toMatch(/\.more\{[^}]*min-height:44px/);
    expect(src).toMatch(/@media \(max-width:639px\)\{[^@]*\.tiles\{grid-template-columns:repeat\(2,minmax\(0,1fr\)\)\}/);
  });
});
