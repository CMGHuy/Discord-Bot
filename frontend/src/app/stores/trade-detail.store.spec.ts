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

/* NG46 — the Notes and Strategy tabs' half of the detail store.
 *
 * The note is the only writable field in the whole SPA, so the states that
 * matter are the ones where text the user typed is NOT on the server:
 * unsaved, failed, and "this position cannot take a note at all".
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

  raise(name: string): void {
    this.counterFor(name).update((n) => n + 1);
  }
}

const ID = 'dddddddddddddddd';

/** Only the fields these tests read. The full row is pinned server-side by
 *  `test_detail_row_fields_match_the_list_exactly`. */
function detailResponse(note: string | null = null, strategy = 'RSI Divergence') {
  return {
    id: ID,
    ticker: 'AAPL',
    strategy,
    entry: 100,
    stop_loss: 95,
    target: 110,
    has_note: note !== null,
    detail: { trade_id: ID, note },
  };
}

const STRATEGY_ROW = {
  strategy: 'RSI Divergence',
  status: 'VALIDATED',
  n: 40,
  win_rate: 55,
  expectancy_r: 0.3,
  window: '2024',
  run_date: null,
  live_n: 25,
  live_wr: 40,
  delta_vs_oos: -15,
  decayed: true,
  evidence_decay: 'unknown',
  gate_description: null,
  win_rate_series: [],
};

describe('TradeDetailStore — notes and strategy', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;
  let events: FakeEventStream;

  beforeEach(() => {
    events = new FakeEventStream();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: events },
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const tick = () => TestBed.inject(ApplicationRef).tick();

  /**
   * Load a trade and settle BOTH of its requests.
   *
   * SR55 added `GET /trades/:id/journal` beside the detail fetch — the
   * excursions explain the note, and they are read separately so a journal
   * failure cannot empty the position itself. Settled here so the
   * `backend.verify()` assertions below still mean "nothing ELSE went out".
   *
   * It answers `journaled: false` by default, which is the ordinary state of
   * an open position. Tests that need an entry pass one.
   */
  const open = (note: string | null = null, strategy = 'RSI Divergence',
                journal: unknown = null) => {
    store.setId(ID);
    tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(detailResponse(note, strategy));
    backend
      .expectOne(`/api/v1/trades/${ID}/journal`)
      .flush({ journaled: journal !== null, entry: journal });
  };

  it('shows the stored note before anything is typed', () => {
    open('bought the retest');
    expect(store.noteText()).toBe('bought the retest');
    expect(store.noteStatus()).toBe('saved');
  });

  it('shows an empty box, not the word null, when there is no note', () => {
    open(null);
    expect(store.noteText()).toBe('');
  });

  it('goes unsaved as soon as the text differs', () => {
    open('first');
    store.editNote('second');

    expect(store.noteText()).toBe('second');
    expect(store.noteDirty()).toBe(true);
    expect(store.noteStatus()).toBe('unsaved');
  });

  it('settles back to saved when the edit is undone', () => {
    // Typing a character and deleting it must not leave the tab claiming
    // there is unsaved work, nor autosave a no-op.
    open('first');
    store.editNote('firstx');
    store.editNote('first');

    expect(store.noteDirty()).toBe(false);
    expect(store.noteStatus()).toBe('saved');
  });

  it('PUTs the draft and reports saving while in flight', () => {
    open('first');
    store.editNote('second');
    store.saveNote();

    const request = backend.expectOne(`/api/v1/trades/${ID}/note`);
    expect(request.request.method).toBe('PUT');
    expect(request.request.body).toEqual({ note: 'second' });
    expect(store.noteStatus()).toBe('saving');

    request.flush({ id: ID, note: 'second' });
    expect(store.noteStatus()).toBe('saved');
  });

  it('keeps the typed text on screen until the refetch carries it', () => {
    // Clearing the draft on success would blank the textarea for the length
    // of the round trip.
    open('first');
    store.editNote('second');
    store.saveNote();
    backend.expectOne(`/api/v1/trades/${ID}/note`).flush({ id: ID, note: 'second' });

    expect(store.noteText()).toBe('second');
  });

  it('reads as saved before the journal refetch arrives', () => {
    // The acknowledged text, not `detail.note`, is what "saved" is measured
    // against. Otherwise the tab claims unsaved work for the length of the
    // round trip -- and for ever if the event stream is disconnected and the
    // refetch never comes.
    open('first');
    store.editNote('second');
    store.saveNote();
    backend.expectOne(`/api/v1/trades/${ID}/note`).flush({ id: ID, note: 'second' });

    expect(store.trade()?.detail?.note).toBe('first');
    expect(store.noteStatus()).toBe('saved');
  });

  it('goes unsaved again when typing continues after a save', () => {
    open('first');
    store.editNote('second');
    store.saveNote();
    backend.expectOne(`/api/v1/trades/${ID}/note`).flush({ id: ID, note: 'second' });

    store.editNote('third');
    expect(store.noteStatus()).toBe('unsaved');
  });

  /* -- SR55: the journal entry behind the note ------------------------ */

  const ENTRY = {
    trade_id: ID, ticker: 'AAPL', strategy: 'RSI Divergence', horizon_key: '1m',
    direction: 'bullish', tier: 'A', badge: 'VALIDATED', quality_score: 72,
    outcome: 'loss', r_realized: -1.0, mfe_r: 1.4, mae_r: 0.2,
    exit_efficiency: 0.31, holding_days: 3.2, tags: ['gave-it-back'],
    auto_lesson: 'Went 1.4R in favour before stopping out.', note: '',
    opened_at: null, closed_at: null, created_at: null,
  };

  it('shows the three excursion figures, with efficiency as a percentage', () => {
    open(null, 'RSI Divergence', ENTRY);

    const rows = store.excursions();
    expect(rows.map((r) => r.label)).toEqual(['MFE', 'MAE', 'Exit efficiency']);
    expect(rows[0].value).toBe(1.4);
    // Stored 0-1, shown as a percentage: "captured 31% of the favourable
    // move" is the sentence a reader is trying to form.
    expect(rows[2].value).toBeCloseTo(31);
  });

  it('carries the tags and the auto-lesson through', () => {
    open(null, 'RSI Divergence', ENTRY);
    expect(store.journalTags()).toEqual(['gave-it-back']);
    expect(store.autoLesson()).toContain('1.4R');
  });

  it('reports no excursions rather than dashes when a trade is unjournaled', () => {
    // An open position has no excursions to report. Three em dashes would
    // imply it does and that they could not be measured.
    open('a note');
    expect(store.excursions()).toEqual([]);
    expect(store.journalAbsent()).toBe(true);
  });

  it('does not claim "unjournaled" before the endpoint has answered', () => {
    // No open(): nothing has come back yet. Rendering this the same as a
    // real "no entry" would flash the empty state on every navigation.
    store.setId(ID);
    expect(store.journalAbsent()).toBe(false);
  });

  it('does not save when nothing was typed', () => {
    open('first');
    store.saveNote();
    backend.verify();
  });

  it('reads a 404 as "not journaled yet" rather than as a failure', () => {
    // Journal entries are written at close, so this is the ordinary state of
    // an open position -- and an error message would tell the user to fix
    // something that is not broken.
    open(null);
    store.editNote('too early');
    store.saveNote();
    backend
      .expectOne(`/api/v1/trades/${ID}/note`)
      .flush(
        { error: { code: 'not_found', message: 'no journal entry' } },
        { status: 404, statusText: 'Not Found' },
      );

    expect(store.noteStatus()).toBe('unjournaled');
    expect(store.noteError()).toBeNull();
  });

  it('says so loudly when a save actually fails', () => {
    open('first');
    store.editNote('second');
    store.saveNote();
    backend
      .expectOne(`/api/v1/trades/${ID}/note`)
      .error(new ProgressEvent('error'), { status: 0 });

    expect(store.noteStatus()).toBe('error');
    expect(store.noteError()).toContain('not saved');
  });

  it('drops an unsaved draft when the trade changes', () => {
    // Carrying it across would autosave one trade's note onto another.
    open('first');
    store.editNote('unsaved words');

    store.setId('eeeeeeeeeeeeeeee');
    expect(store.noteDraft()).toBeNull();
    expect(store.noteStatus()).toBe('saved');
  });

  it('refetches on a journal event, which is how a save comes back', () => {
    open('first');

    store.load();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(detailResponse('second'));

    expect(store.noteText()).toBe('second');
  });

  it('picks this trade\'s row out of the registry', () => {
    open(null, 'RSI Divergence');
    store.loadStrategies();
    backend.expectOne('/api/v1/analytics/strategies').flush({
      strategies: [{ ...STRATEGY_ROW, strategy: 'Other' }, STRATEGY_ROW],
      heatmap: {},
    });

    expect(store.strategyRow()?.strategy).toBe('RSI Divergence');
    expect(store.strategyRow()?.decayed).toBe(true);
  });

  it('reports no row rather than the wrong one when the registry lacks it', () => {
    open(null, 'Nowhere To Be Found');
    store.loadStrategies();
    backend
      .expectOne('/api/v1/analytics/strategies')
      .flush({ strategies: [STRATEGY_ROW], heatmap: {} });

    expect(store.strategyRow()).toBeNull();
  });

  it('has no strategy row when the trade has no strategy', () => {
    open(null, '');
    expect(store.strategyRow()).toBeNull();
  });
});

describe('TradeDetailStore — original risk and plan figures', () => {
  let store: InstanceType<typeof TradeDetailStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(),
        provideHttpClientTesting(),
        TradeDetailStore,
      ],
    });
    store = TestBed.inject(TradeDetailStore);
    backend = TestBed.inject(HttpTestingController);
  });

  function open(row: Record<string, unknown> = {}, detail: Record<string, unknown> = {}) {
    store.setId(ID);
    TestBed.inject(ApplicationRef).tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush({
      ...detailResponse(), status: 'ACTIVE', shares: 10, ...row,
      detail: { ...detailResponse().detail, ...detail },
    });
    backend.expectOne(`/api/v1/trades/${ID}/journal`).flush({ journaled: false, entry: null });
    backend.verify();
  }

  it('keeps original per-share risk after a PARTIAL stop moves to breakeven', () => {
    open({ status: 'PARTIAL', risk_stop: 95, stop_loss: 100, shares: 4 });
    expect(store.riskPerShare()).toBe(5);
    expect(store.rewardPerShare()).toBe(10);
  });

  it('measures ACTIVE risk and plan figures from their recorded values', () => {
    open({ risk_stop: 95 }, {
      working_stop: 97, trail_atr_mult: 2.5, sizing_mode: 'risk', entry_type: 'stop',
    });
    expect(store.riskStop()).toBe(95);
    expect(store.riskPerShare()).toBe(5);
    expect(store.dollarAtRisk()).toBe(50);
    expect(store.workingStop()).toBe(97);
    expect(store.trailAtrMult()).toBe(2.5);
    expect(store.sizingMode()).toBe('risk');
    expect(store.entryType()).toBe('stop');
  });

  it('uses remaining open shares and original risk for a PARTIAL position', () => {
    open({ status: 'PARTIAL', risk_stop: 95, stop_loss: 100, shares: 4 });
    expect(store.dollarAtRisk()).toBe(20);
  });

  it.each([
    { row: {}, stop: null, risk: 5, dollars: 50 },
    { row: { risk_stop: null }, stop: null, risk: 5, dollars: 50 },
    { row: { risk_stop: 105 }, stop: 105, risk: 5, dollars: 50 },
    { row: { risk_stop: 95, stop_loss: null }, stop: 95, risk: 5, dollars: 50 },
    { row: { risk_stop: 100, shares: 0 }, stop: 100, risk: 0, dollars: 0 },
    { row: { risk_stop: '95' }, stop: null, risk: 5, dollars: 50 },
    { row: { risk_stop: NaN }, stop: null, risk: 5, dollars: 50 },
    { row: { risk_stop: Infinity }, stop: null, risk: 5, dollars: 50 },
    { row: { stop_loss: null }, stop: null, risk: null, dollars: null },
    { row: { stop_loss: undefined }, stop: null, risk: null, dollars: null },
    { row: { stop_loss: '95' }, stop: null, risk: null, dollars: null },
    { row: { entry: null }, stop: null, risk: null, dollars: null },
    { row: { entry: undefined }, stop: null, risk: null, dollars: null },
    { row: { entry: Infinity }, stop: null, risk: null, dollars: null },
    { row: { entry: '100' }, stop: null, risk: null, dollars: null },
    { row: { shares: null }, stop: null, risk: 5, dollars: null },
    { row: { shares: undefined }, stop: null, risk: 5, dollars: null },
    { row: { shares: NaN }, stop: null, risk: 5, dollars: null },
    { row: { shares: '10' }, stop: null, risk: 5, dollars: null },
  ])('narrows original risk and open shares: $row', ({ row, stop, risk, dollars }) => {
    open(row);
    expect(store.riskStop()).toBe(stop);
    expect(store.riskPerShare()).toBe(risk);
    expect(store.dollarAtRisk()).toBe(dollars);
  });

  it('keeps figures unknown before a response arrives', () => {
    expect(store.riskStop()).toBeNull();
    expect(store.riskPerShare()).toBeNull();
    expect(store.dollarAtRisk()).toBeNull();
    expect(store.workingStop()).toBeNull();
    expect(store.trailAtrMult()).toBeNull();
    expect(store.sizingMode()).toBeNull();
    expect(store.entryType()).toBeNull();
    expect(store.earningsDays()).toBeNull();
  });

  it.each([undefined, null, NaN, Infinity, '3', {}, true])(
    'rejects absent or malformed numeric detail fields: %s', (value) => {
      open({}, { working_stop: value, trail_atr_mult: value });
      expect(store.workingStop()).toBeNull();
      expect(store.trailAtrMult()).toBeNull();
    },
  );

  it('preserves recorded zero values in detail fields', () => {
    open({}, { working_stop: 0, trail_atr_mult: 0 });
    expect(store.workingStop()).toBe(0);
    expect(store.trailAtrMult()).toBe(0);
  });

  it.each([undefined, null, '', '  ', {}, true])(
    'keeps unreadable or blank plan text unknown: %s', (value) => {
      open({}, { sizing_mode: value, entry_type: value });
      expect(store.sizingMode()).toBeNull();
      expect(store.entryType()).toBeNull();
    },
  );

  it.each([
    { gates: undefined, days: null },
    { gates: null, days: null },
    { gates: {}, days: null },
    { gates: [], days: null },
    { gates: [{ key: 'rs', label: 'RS', value: 90 }], days: null },
    { gates: [{ key: 'earnings', label: 'Earnings', value: 7 }], days: 7 },
    { gates: [{ key: 'earnings', label: 'Earnings', value: 0 }], days: 0 },
    { gates: [{ key: 'earnings', label: 'Earnings', value: -2 }], days: -2 },
    { gates: [{ key: 'earnings', label: 'Earnings', value: '7' }], days: null },
    { gates: [{ key: 'earnings', label: 'Earnings', value: Infinity }], days: null },
    { gates: [{ key: 'earnings', label: 'Earnings', value: null }], days: null },
    { gates: [{ key: 'earnings', label: '', value: 7 }], days: null },
  ])('reads earnings days only from a readable numeric earnings gate: $gates', ({ gates, days }) => {
    open({}, { gates });
    expect(store.earningsDays()).toBe(days);
  });
});
