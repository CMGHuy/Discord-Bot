import { describe, expect, it } from 'vitest';

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
