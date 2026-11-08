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
    const order = [...el.querySelectorAll('.today, .paper, .range, .chips')].map((n) => n.classList[0]);
    expect(order).toEqual(['today', 'paper', 'range', 'chips']);
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
    const chips = [...el.querySelectorAll<HTMLButtonElement>('.chips button')];
    expect(chips.map((b) => text(b.querySelector('.label')))).toEqual(SERIES_ORDER.map((k) => CHIP_LABELS[k]));
    expect(chips.filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.dataset['key']))
      .toEqual([...DEFAULT_VISIBLE]);
    expect(text(chips[1])).toContain('on capital in trades — not account return');
    expect(chips[1].querySelector('.swatch.dashed')).not.toBeNull();
  });
  it('toggles a chip on and off', () => {
    const { fixture, el } = renderTab(stubStore(BENCHMARK_FIXTURE));
    const dow = el.querySelector<HTMLButtonElement>('.chips button[data-key="^DJI"]')!;
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