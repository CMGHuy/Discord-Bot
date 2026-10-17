import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { convertToParamMap } from '@angular/router';
import { describe, expect, it } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { GateCell } from '../api/models';
import { ATTRIBUTION, GATES, NOT_RUN, ok } from '../testing/report-fixtures';
import {
  HOLDOUT_NOTE,
  PORTFOLIO_NOTE,
  ReportsStore,
  attributionView,
  gatesView,
  tabFromParams,
} from './reports.store';

/* The rules these tests pin are the quant panel's, and each one is a way the
 * page could mislead: a latest reading shown as the verdict, a verdict shown
 * below the floor, a thin bucket flagged as a candidate, two populations
 * blended into one figure. */

const ATTRIBUTION_URL = '/api/v1/reports/expectancy-attribution';
const GATES_URL = '/api/v1/reports/gate-counterfactual';

function create(): { store: InstanceType<typeof ReportsStore>; http: HttpTestingController } {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
      provideHttpClientTesting(),
      ReportsStore,
    ],
  });
  return { store: TestBed.inject(ReportsStore), http: TestBed.inject(HttpTestingController) };
}

describe('tabFromParams', () => {
  it('defaults to attribution, and for anything it does not know', () => {
    expect(tabFromParams(convertToParamMap({}))).toBe('attribution');
    expect(tabFromParams(convertToParamMap({ tab: 'nonsense' }))).toBe('attribution');
    expect(tabFromParams(convertToParamMap({ tab: 'gates' }))).toBe('gates');
  });
});

describe('attributionView', () => {
  const view = attributionView(ATTRIBUTION);

  it('takes THE verdict from the verdict of record, not from the latest reading', () => {
    // The fixture's latest reading says PREDICTIVE; the record says WEAK.
    expect(view.verdict).toEqual({ label: 'WEAK', tone: 'warn', date: '2026-10-12', n: 214, inverted: false });
  });

  it('keeps live and TRAIN as two readings, never one', () => {
    expect(view.readings.map((r) => [r.population, r.present, r.n])).toEqual([['Live', true, 214], ['TRAIN', true, 3120]]);
    expect(view.readings[0].spread).toBe(0.22);
    expect(view.readings[1].spread).toBe(0.04);
  });

  it('formats each population window as first_week..last_week', () => {
    expect(view.readings.map((r) => r.window)).toEqual(['2026-07-06..2026-10-05', '2019-01-07..2023-12-25']);
  });

  it('marks a factor as a screen candidate only below q 0.10', () => {
    const byKey = Object.fromEntries(view.factors.map((f) => [f.key, f.candidate]));
    expect(byKey).toEqual({ 'RSI trend alignment': true, 'MACD momentum': false });
  });

  it('draws a thin bucket withheld, with its N, and never marks it', () => {
    const earnings = view.dimensions.find((d) => d.key === 'earnings')!;
    const thin = earnings.live!.find((b) => b.label === '0-5')!;
    expect(thin).toMatchObject({ withheld: true, n: 12 });
    // q is 0.01 in the fixture, well under the threshold, and it is thin.
    expect(earnings.candidates).toEqual([]);
  });

  it('marks a non-thin bucket below q 0.10, naming its population', () => {
    const regime = view.dimensions.find((d) => d.key === 'regime2_state')!;
    expect(regime.candidates).toEqual(['bull_quiet (Live)']);
  });

  it('keeps the dimensions in the result order, with their labels', () => {
    expect(view.dimensions.map((d) => [d.key, d.label])).toEqual([
      ['regime2_state', 'Regime'], ['earnings', 'Earnings proximity']]);
  });

  it('lists the direction and horizon splits, each with both populations', () => {
    expect(view.splits.map((s) => `${s.axis}:${s.name}`)).toEqual([
      'Direction:bullish', 'Direction:bearish', 'Horizon:2w', 'Horizon:3m']);
    expect(view.splits[1].live?.spread).toBe(-0.05);
    expect(view.splits[1].train?.n).toBe(620);
  });

  it('reads an absent population as not in this run, never as zeros', () => {
    const liveOnly = attributionView({ ...ATTRIBUTION, populations: { live: ATTRIBUTION.populations.live, train: null } });
    expect(liveOnly.readings[1]).toMatchObject({ population: 'TRAIN', present: false, n: null, spread: null, window: null });
    expect(liveOnly.dimensions[0].train).toBeNull();
    expect(liveOnly.factors[0].train).toBeNull();
    expect(liveOnly.splits[0].train).toBeNull();
  });

  it('notes "inverted" when a population reports it', () => {
    const live = ATTRIBUTION.populations.live!;
    const inverted = attributionView({
      ...ATTRIBUTION,
      verdict_of_record: { verdict: 'NOT PREDICTIVE', date: '2026-10-12', n: 214 },
      populations: { live: { ...live, monotonicity: { ...live.monotonicity, inverted: true } }, train: null },
    });
    expect(inverted.verdict).toMatchObject({ label: 'NOT PREDICTIVE', tone: 'neutral', inverted: true });
  });

  it('carries the looks count and the seed for the footer', () => {
    expect([view.looks, view.seed]).toEqual([37, 42]);
  });
});

describe('gatesView', () => {
  const cells = gatesView(GATES);
  const cell = (gate: string, population: string) => cells.find((c) => c.gate === gate && c.population === population)!;

  it('yields one view per cell, in the result order', () => {
    expect(cells.map((c) => c.id)).toEqual([
      'rs:live', 'rs:train', 'risk_cap:live', 'risk_cap:train', 'compression:live', 'compression:train']);
  });

  it('shows WAITING with its N and nothing else below the floor', () => {
    const waiting = cell('rs', 'Live');
    expect(waiting.state).toBe('waiting');
    expect(waiting.n).toBe(29);
    expect(waiting.verdict).toBeNull();
    // The fixture carries a latest reading for this cell; it must not surface.
    expect(waiting.latest).toBeNull();
    expect(waiting.labels).toEqual([]);
  });

  it('keeps the verdict of record apart from a different latest reading', () => {
    const riskCap = cell('risk_cap', 'Live');
    expect(riskCap.state).toBe('verdict');
    expect(riskCap.verdict).toMatchObject({ label: 'GATE EARNS', tone: 'good', date: '2026-10-14', n: 31 });
    expect(riskCap.latest).toEqual({ difference: -0.08, ciLow: -0.31, ciHigh: 0.12, q: 0.44 });
  });

  it('words a verdict as a historical measurement', () => {
    expect(cell('risk_cap', 'Live').verdict!.sentence)
      .toBe('Over these trades, the gate’s blocked setups returned less than its taken ones.');
    expect(cell('compression', 'TRAIN').verdict!.sentence)
      .toBe('Over these trades, the gate’s blocked setups returned more than its taken ones.');
  });

  it('puts the portfolio-state and holdout notes beside every live verdict', () => {
    expect(cell('risk_cap', 'Live').labels).toEqual([PORTFOLIO_NOTE, HOLDOUT_NOTE]);
    expect(cell('compression', 'Live').labels).toEqual([PORTFOLIO_NOTE, HOLDOUT_NOTE]);
    expect(cell('risk_cap', 'TRAIN').labels).toEqual([]);
  });

  it('labels TRAIN compression in-sample', () => {
    expect(cell('compression', 'TRAIN').labels).toEqual(['in-sample']);
  });

  it('shows a fixed note in place of a verdict where there is no population', () => {
    const rsTrain = cell('rs', 'TRAIN');
    expect(rsTrain.state).toBe('note');
    expect(rsTrain.note).toBe('no TRAIN population');
    expect(rsTrain.verdict).toBeNull();
    expect(rsTrain.latest).toBeNull();
  });

  it('shows the persisted no-plan note on a no_qualifying_target cell, deriving nothing from the gate', () => {
    const noPlan: GateCell = {
      gate: 'no_qualifying_target', population: 'live', verdict: 'WAITING', n: 0, taken_n: 0,
      verdict_of_record: null, latest: null, in_sample: false, note: 'no verdict — no-plan',
    };
    const [view] = gatesView({ ...GATES, cells: [noPlan], rows: [] });
    expect(view).toMatchObject({ id: 'no_qualifying_target:live', state: 'note', note: 'no verdict — no-plan',
                                 verdict: null, latest: null, labels: [] });
  });

  it('shows a run-time note above the floor in place of any reading', () => {
    const noTakenArm: GateCell = {
      gate: 'compression', population: 'train', verdict: 'WAITING', n: 260, taken_n: 0,
      verdict_of_record: null, latest: { difference: 0.17, ci_low: 0.04, ci_high: 0.3, q: 0.03, p: 0.01 },
      in_sample: true, note: 'no TRAIN taken arm — no as-of earnings archive',
    };
    const [view] = gatesView({ ...GATES, cells: [noTakenArm] });
    expect(view).toMatchObject({ state: 'note', verdict: null, latest: null, labels: [], n: 260 });
  });

  it('attaches each cell its own gate x reason rows, with the over-cap figure', () => {
    const rows = cell('risk_cap', 'Live').rows;
    expect(rows.map((r) => r.reason)).toEqual(['risk_cap_exceeded']);
    expect(rows[0]).toMatchObject({ overCap: true, dollarRisk: 412.5, blockedN: 46 });
    expect(cell('risk_cap', 'TRAIN').rows).toEqual([]);
  });

  it('keeps the v147 row figures in their own units, with the booked R apart', () => {
    const [row] = cell('rs', 'Live').rows;
    expect(row).toMatchObject({ fillRate: 0.72, blockedWinRate: 0.4, takenWinRate: 0.52, takenN: 40,
                                takenExpR: 0.1, takenRealisedExpR: 0.08 });
  });
});

describe('ReportsStore', () => {
  it('fetches only the active tab', () => {
    const { store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(ATTRIBUTION_URL).flush(ok(ATTRIBUTION));
    http.expectNone(GATES_URL);
    expect(store.tab()).toBe('attribution');
    expect(store.attribution()?.verdict.label).toBe('WEAK');
    expect(store.gates()).toBeNull();
    expect(store.generatedAt()).toBe('2026-10-20T21:30:00+00:00');
  });

  it('switches tab and fetches the other report', () => {
    const { store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(ATTRIBUTION_URL).flush(ok(ATTRIBUTION));
    store.resolveTab('gates').subscribe();
    http.expectOne(GATES_URL).flush(ok(GATES));
    expect(store.tab()).toBe('gates');
    expect(store.gates()?.length).toBe(6);
    expect(store.generatedAt()).toBe('2026-10-20T21:45:00+00:00');
  });

  it('reports not_run as a state, with no view and no error', () => {
    const { store, http } = create();
    store.resolveTab('gates').subscribe();
    http.expectOne(GATES_URL).flush(NOT_RUN);
    expect(store.notRun()).toBe(true);
    expect(store.gates()).toBeNull();
    expect(store.error()).toBeNull();
    expect(store.generatedAt()).toBeNull();
  });

  it('records a 500 as an error, not as not_run', () => {
    const { store, http } = create();
    store.resolveTab('attribution').subscribe();
    http.expectOne(ATTRIBUTION_URL).flush(
      { error: { code: 'report_unreadable', message: 'ValueError: Expecting value' } },
      { status: 500, statusText: 'Server Error' });
    expect(store.notRun()).toBe(false);
    expect(store.error()).toBeTruthy();
    expect(store.data()).toBeNull();
  });
});
