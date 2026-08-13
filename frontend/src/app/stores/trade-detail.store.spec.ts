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
  rr_override: null,
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

  /** Load a trade and settle. */
  const open = (note: string | null = null, strategy = 'RSI Divergence') => {
    store.setId(ID);
    tick();
    backend.expectOne(`/api/v1/trades/${ID}`).flush(detailResponse(note, strategy));
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

    events.raise('journal');
    tick();
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
