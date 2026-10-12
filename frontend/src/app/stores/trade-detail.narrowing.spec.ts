import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import {
  ApplicationRef,
  Signal,
  WritableSignal,
  provideZonelessChangeDetection,
  signal,
} from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { TradeDetailStore } from './trade-detail.store';

/* SR49 — the nine detail fields that arrived and rendered nowhere.
 *
 * Every one was typed on `TradeDetailFields`, fetched on every detail load,
 * and read by nothing: grep found each exactly once in `frontend/src`, in
 * `models.ts` itself. No endpoint work was needed for any of them.
 *
 * These tests are mostly about the SHAPES, because several of the fields are
 * `unknown[]` on purpose — the Python side owns them — and because two of the
 * shapes are not what a reader would guess:
 *
 *   * `quality_breakdown` is a list of two-element LISTS, not objects
 *     (`plan_engine.py:141` converts the scoring tuples so JSON round-trips).
 *   * `confirmed_by` carries `{strategy, horizon_key}` objects, while
 *     `models.ts` types it `string[]`. The type is wrong; both forms are
 *     accepted rather than trusting either.
 */

class FakeEventStream {
  private readonly counters = new Map<string, WritableSignal<number>>();

  private counterFor(name: string): WritableSignal<number> {
    let counter = this.counters.get(name);
    if (!counter) {
      counter = signal(0);
      this.counters.set(name, counter);
    }
    return counter;
  }

  changes(name: string): Signal<number> {
    return this.counterFor(name).asReadonly();
  }
}

const ID = 'eeeeeeeeeeeeeeee';

/** A plan-backed trade with every one of the nine fields populated. */
const FULL_DETAIL = {
  trade_id: ID,
  note: null,
  created_at: '2026-08-01T09:30:00Z',
  plan_source: 'scan',
  entry_type: 'stop',
  trigger_price: 101.5,
  tp1_fraction: 0.5,
  breakeven_trigger_fraction: 0.6,
  explanation: 'Price reclaimed the 50-day after a three-week base.',
  confirmed_by: [
    { strategy: 'RSI Divergence', horizon_key: '4w' },
    { strategy: 'VWAP', horizon_key: '2w' },
  ],
  target_sources: ['Fib 1.618', 'Prior high', 'Fib 1.618'],
  stop_sources: ['Swing low'],
  target2_sources: [],
  confidence_breakdown: {
    'Trend alignment': '+12 — above the 200-day',
    'Volume': '+6 — above average on the breakout',
  },
  quality_breakdown: [
    ['Badge', 15],
    ['Confluence', 20],
    ['R:R', 10],
  ],
  status_history: [
    { status: 'PENDING', reason: null, at: '2026-08-01T09:30:00Z' },
    { status: 'ACTIVE', reason: 'trigger filled', at: '2026-08-02T14:05:00Z' },
  ],
  legs: [
    { fraction: 0.5, exit_price: 110, r: 1.2, reason: 'TP1' },
    { fraction: 0.5, exit_price: null, r: null, reason: null },
  ],
  legs_realized: [],
  sizing_mode: 'risk_pct',
  working_stop: 99,
};

/** A legacy row: no plan ever existed, so none of the nine will ever arrive.
 *  The server fills them with the empty forms rather than omitting them
 *  (`api_v1/trades.py:326-341`). */
const LEGACY_DETAIL = {
  trade_id: ID,
  note: null,
  created_at: null,
  plan_source: null,
  entry_type: null,
  trigger_price: null,
  tp1_fraction: null,
  breakeven_trigger_fraction: null,
  explanation: null,
  confirmed_by: [],
  target_sources: [],
  stop_sources: [],
  target2_sources: [],
  confidence_breakdown: null,
  quality_breakdown: [],
  status_history: [],
  legs: [],
  legs_realized: [],
  sizing_mode: null,
  working_stop: null,
};

function response(detail: object) {
  return {
    id: ID,
    ticker: 'AAPL',
    strategy: 'RSI Divergence',
    entry: 100,
    stop_loss: 95,
    target: 110,
    has_note: false,
    detail,
  };
}

describe('TradeDetailStore — the fields that rendered nowhere', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const open = (detail: object) => {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(response(detail));
  };

  it('reads the explanation', () => {
    open(FULL_DETAIL);
    expect(store.explanation()).toBe(
      'Price reclaimed the 50-day after a three-week base.',
    );
  });

  it('reads the recorded Why context and lifecycle without coercing numbers', () => {
    open({ ...FULL_DETAIL, entry_context: { gap_p90_pct: 1.8, gap_fragile: false },
      risk_features: { liquidity: 'thin' }, confidence_points: { trend: 12, volume: 0 },
      confidence_unevaluated: ['earnings', 42, '', '  ', null, {}],
      sessions_since_created: 0, expires_on: '2026-08-07', time_exit_on: '2026-08-14',
      hold_cap_bars: 10, acceptance_level: 101.2 });
    expect(store.entryContext()).toEqual({ gap_p90_pct: 1.8, gap_fragile: false });
    expect(store.riskFeatures()).toEqual({ liquidity: 'thin' });
    expect(store.confidencePoints()).toEqual({ trend: 12, volume: 0 });
    expect(store.confidenceUnevaluated()).toEqual(['earnings', '42']);
    expect(store.sessionsSinceCreated()).toBe(0);
    expect(store.expiresOn()).toBe('2026-08-07');
    expect(store.timeExitOn()).toBe('2026-08-14');
    expect(store.holdCapBars()).toBe(10);
    expect(store.acceptanceLevel()).toBe(101.2);
    expect(store.gapP90Pct()).toBe(1.8);
    expect(store.gapFragile()).toBe(false);
  });

  it.each([FULL_DETAIL, LEGACY_DETAIL])('defaults pre-v146 and legacy missing keys', (detail) => {
    open(detail);
    expect(store.entryContext()).toEqual({});
    expect(store.riskFeatures()).toEqual({});
    expect(store.confidencePoints()).toBeNull();
    expect(store.confidenceUnevaluated()).toEqual([]);
    expect(store.gates()).toEqual([]);
    expect(store.calendar()).toEqual([]);
    expect(store.sessionsSinceCreated()).toBeNull();
    expect(store.expiresOn()).toBeNull();
    expect(store.timeExitOn()).toBeNull();
    expect(store.holdCapBars()).toBeNull();
    expect(store.acceptanceLevel()).toBeNull();
    expect(store.gapP90Pct()).toBeNull();
    expect(store.gapFragile()).toBeNull();
    expect(store.detailAbsent()).toBe(detail === LEGACY_DETAIL);
  });

  it.each([null, [], 'wrong', {}, { trend: '12', bad: NaN }])(
    'keeps confidence points absent when no numeric entries exist: %j', (points) => {
      open({ ...FULL_DETAIL, confidence_points: points });
      expect(store.confidencePoints()).toBeNull();
    },
  );

  it('drops invalid confidence points and keeps finite numeric zero', () => {
    open({ ...FULL_DETAIL, confidence_points: { trend: 0, volume: -2, bad: Infinity,
      text: '3', absent: null, flag: false } });
    expect(store.confidencePoints()).toEqual({ trend: 0, volume: -2 });
  });

  it('narrows known gates and their scalar values and readable parts', () => {
    open({ ...FULL_DETAIL, gates: [null, [], 'junk', { key: 'future' },
      { key: 'rs', label: 'Relative strength', value: 2, threshold: 1, margin: 1,
        applies: true, parts: [{ label: 'Stock', value: 3 }, { label: 'SPY', value: 'flat' },
          null, {}, { label: 'Missing', value: {} }], note: 'Above threshold' },
      { key: 'rs', label: {} }, { key: 'earnings' },
      { key: 'regime', label: 'Regime', value: {}, threshold: '1', margin: NaN,
        applies: 'true', parts: {}, note: {} },
      { key: 'earnings', label: 'Earnings', value: 'clear', applies: false },
    ] });
    expect(store.gates()).toEqual([
      { key: 'rs', label: 'Relative strength', value: 2, threshold: 1, margin: 1,
        applies: true, parts: [{ label: 'Stock', value: 3 }, { label: 'SPY', value: 'flat' },
          { label: 'Missing', value: null }], note: 'Above threshold' },
      { key: 'regime', label: 'Regime', value: null, threshold: null, margin: null,
        applies: false, parts: [], note: null },
      { key: 'earnings', label: 'Earnings', value: 'clear', threshold: null, margin: null,
        applies: false, parts: [], note: null },
    ]);
  });

  it('keeps only dated monthly OPEX calendar rows with a readable label', () => {
    open({ ...FULL_DETAIL, calendar: [null, [], {},
      { kind: 'other', date: '2026-08-21' }, { kind: 'opex_monthly', date: '' },
      { kind: 'opex_monthly', date: '2026-08-21', label: 'August OPEX' },
      { kind: 'opex_monthly', date: '2026-09-18', label: {} },
    ] });
    expect(store.calendar()).toEqual([
      { kind: 'opex_monthly', date: '2026-08-21', label: 'August OPEX' },
      { kind: 'opex_monthly', date: '2026-09-18', label: 'Monthly OPEX' },
    ]);
  });

  it('tolerates wrong wire types without presenting coerced risk numbers', () => {
    open({ ...FULL_DETAIL, entry_context: [], risk_features: 'wrong',
      confidence_unevaluated: {}, gates: {}, calendar: 'wrong',
      sessions_since_created: '2', expires_on: {}, time_exit_on: '',
      hold_cap_bars: Infinity, acceptance_level: false });
    expect(store.entryContext()).toEqual({});
    expect(store.riskFeatures()).toEqual({});
    expect(store.confidenceUnevaluated()).toEqual([]);
    expect(store.gates()).toEqual([]);
    expect(store.calendar()).toEqual([]);
    expect(store.sessionsSinceCreated()).toBeNull();
    expect(store.expiresOn()).toBeNull();
    expect(store.timeExitOn()).toBeNull();
    expect(store.holdCapBars()).toBeNull();
    expect(store.acceptanceLevel()).toBeNull();
  });

  it.each(['true', 1, null])('accepts only real gap booleans: %j', (fragile) => {
    open({ ...LEGACY_DETAIL, entry_context: { gap_fragile: fragile, gap_p90_pct: '2' },
      risk_features: { recorded: true } });
    expect(store.gapFragile()).toBeNull();
    expect(store.gapP90Pct()).toBeNull();
    expect(store.detailAbsent()).toBe(true);
  });

  it('keeps a true gap flag and leaves detailAbsent based on the original fields', () => {
    open({ ...LEGACY_DETAIL, entry_context: { gap_fragile: true } });
    expect(store.gapFragile()).toBe(true);
    expect(store.detailAbsent()).toBe(true);
  });

  it('reads confirmed_by as strategy and horizon pairs', () => {
    open(FULL_DETAIL);
    expect(store.confirmedBy()).toEqual([
      { strategy: 'RSI Divergence', horizon: '4w' },
      { strategy: 'VWAP', horizon: '2w' },
    ]);
  });

  it('accepts confirmed_by as bare strings too', () => {
    // models.ts types this string[]. The type is wrong for today's records,
    // but an older trade on disk is not something this store can vouch for.
    open({ ...FULL_DETAIL, confirmed_by: ['MACD', ''] });
    expect(store.confirmedBy()).toEqual([{ strategy: 'MACD', horizon: null }]);
  });

  it('keeps target and stop sources apart, and de-duplicates each', () => {
    open(FULL_DETAIL);
    // 'Fib 1.618' is listed twice in the fixture. The Jinja tooltip piped the
    // merged list through `unique` for the same reason.
    expect(store.targetSources()).toEqual(['Fib 1.618', 'Prior high']);
    expect(store.stopSources()).toEqual(['Swing low']);
  });

  it('reads the confidence breakdown in the order it was scored', () => {
    open(FULL_DETAIL);
    expect(store.confidenceFactors()).toEqual([
      { factor: 'Trend alignment', note: '+12 — above the 200-day' },
      { factor: 'Volume', note: '+6 — above average on the breakout' },
    ]);
  });

  it('reads quality_breakdown out of two-element lists', () => {
    open(FULL_DETAIL);
    expect(store.qualityFactors()).toEqual([
      { label: 'Badge', points: 15 },
      { label: 'Confluence', points: 20 },
      { label: 'R:R', points: 10 },
    ]);
  });

  it('drops a quality row it cannot read rather than scoring it zero', () => {
    // A factor with no points is not a factor worth 0 — printing 0 would be a
    // claim about the plan that nothing in the data supports.
    open({ ...FULL_DETAIL, quality_breakdown: [['Badge', 15], ['Broken'], 'nope'] });
    expect(store.qualityFactors()).toEqual([{ label: 'Badge', points: 15 }]);
  });

  it('prepends creation to the timeline, since history does not contain it', () => {
    open(FULL_DETAIL);
    const timeline = store.timeline();
    expect(timeline[0]).toEqual({
      status: 'CREATED',
      reason: 'scan',
      at: '2026-08-01T09:30:00Z',
    });
    expect(timeline.map((e) => e.status)).toEqual(['CREATED', 'PENDING', 'ACTIVE']);
  });

  it('keeps a transition that has no reason or time', () => {
    // Only the status is required. Dropping an entry for a missing reason
    // would put a hole in an audit trail.
    open({ ...FULL_DETAIL, created_at: null, status_history: [{ status: 'CLOSED' }] });
    expect(store.timeline()).toEqual([{ status: 'CLOSED', reason: null, at: null }]);
  });

  it('reads the legs, including the runner that has not closed', () => {
    open(FULL_DETAIL);
    expect(store.legs()).toEqual([
      { fraction: 0.5, exitPrice: 110, r: 1.2, reason: 'TP1' },
      { fraction: 0.5, exitPrice: null, r: null, reason: null },
    ]);
  });

  it('prefers the settled legs over the live ones', () => {
    open({
      ...FULL_DETAIL,
      legs_realized: [{ fraction: 1, exit_price: 112, r: 1.5, reason: 'TP2' }],
    });
    expect(store.legs()).toEqual([
      { fraction: 1, exitPrice: 112, r: 1.5, reason: 'TP2' },
    ]);
  });

  it('reads the trigger price and the two fractions as percentages', () => {
    open(FULL_DETAIL);
    expect(store.triggerPrice()).toBe(101.5);
    expect(store.breakevenTriggerPct()).toBe(60);
    expect(store.tp1Pct()).toBe(50);
  });

  it('says a legacy record has no detail, rather than showing nine blanks', () => {
    open(LEGACY_DETAIL);
    expect(store.detailAbsent()).toBe(true);
    expect(store.explanation()).toBeNull();
    expect(store.confirmedBy()).toEqual([]);
    expect(store.qualityFactors()).toEqual([]);
    expect(store.timeline()).toEqual([]);
    expect(store.legs()).toEqual([]);
  });

  it('does not call a plan-backed trade absent just because one field is', () => {
    // One missing explanation is an absent field. A legacy row is an absent
    // RECORD. Conflating them would hide a real plan's reasoning behind a
    // notice saying there is none.
    open({ ...FULL_DETAIL, explanation: null });
    expect(store.detailAbsent()).toBe(false);
  });

  it('is not "absent" before the first response has arrived', () => {
    // Nothing loaded is not the same as nothing recorded, and the notice must
    // not flash during the load.
    expect(store.detailAbsent()).toBe(false);
  });
});

describe('TradeDetailStore — banked leg stats (v58)', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: new FakeEventStream() },
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  function openPartial(overrides: {
    entry?: number | null; shares?: number | null;
    direction?: string; legsRealized?: unknown[];
  } = {}) {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID,
      ticker: 'AAPL',
      strategy: 'RSI Divergence',
      status: 'PARTIAL',
      direction: overrides.direction ?? 'bullish',
      entry: overrides.entry === undefined ? 100 : overrides.entry,
      stop_loss: 101.33,
      target: 105,
      shares: overrides.shares === undefined ? 100 : overrides.shares,
      has_note: false,
      detail: {
        ...LEGACY_DETAIL,
        legs_realized: overrides.legsRealized
          ?? [{ fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' }],
      },
    });
  }

  it('reads the banked leg once PARTIAL', () => {
    openPartial();
    expect(store.bankedLeg()).toEqual({
      fraction: 0.5, exitPrice: 110, r: 2.0, reason: 'tp1',
    });
  });

  it('is null before anything has banked', () => {
    openPartial({ legsRealized: [] });
    expect(store.bankedLeg()).toBeNull();
  });

  it('computes pct and dollar amount from the ORIGINAL entry', () => {
    openPartial();
    expect(store.bankedStats()).toEqual({ pct: 10, amount: 500 });
  });

  it('signs the pct and amount correctly for a short', () => {
    openPartial({
      direction: 'bearish', entry: 100,
      legsRealized: [{ fraction: 0.5, exit_price: 90, r: 2.0, reason: 'tp1' }],
    });
    expect(store.bankedStats()).toEqual({ pct: 10, amount: 500 });
  });

  it('omits the dollar amount when shares are unknown', () => {
    openPartial({ shares: null });
    expect(store.bankedStats()).toEqual({ pct: 10, amount: null });
  });

  it('is null once the position is no longer PARTIAL', () => {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      id: ID, ticker: 'AAPL', strategy: 'RSI Divergence', status: 'CLOSED',
      direction: 'bullish', entry: 100, stop_loss: 101.33, target: 105,
      shares: 100, has_note: false,
      detail: {
        ...LEGACY_DETAIL,
        legs_realized: [{ fraction: 0.5, exit_price: 110, r: 2.0, reason: 'tp1' }],
      },
    });
    expect(store.bankedLeg()).toBeNull();
    expect(store.bankedStats()).toBeNull();
  });
});
