import { ApplicationRef, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject, of, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import {
  EquityBasis,
  EquityCandle,
  EquityCandlesResponse,
  EquityTimeframe,
  Preferences,
} from '../api/models';
import { EQUITY_CANDLES_ERROR, EquityCandlesStore } from './equity-candles.store';
import { PreferencesStore } from './preferences.store';

const CANDLE: EquityCandle = {
  t: '2026-10-16', o: 10120.5, h: 10210, l: 10090.2, c: 10180.4,
  change: 59.9, change_pct: 0.59, samples: 78, skipped: 0, approx: false,
};

function response(tf: EquityTimeframe = '1D', basis: EquityBasis = 'mtm',
                  candles: EquityCandle[] = [CANDLE]): EquityCandlesResponse {
  return { tf, basis, currency_symbol: '€', candles, recording_since: null,
           as_of: '2026-10-17T14:00:00+00:00' };
}

function okApi() {
  return {
    equityCandles: vi.fn().mockImplementation(
      (tf: EquityTimeframe, basis: EquityBasis) => of(response(tf, basis))),
  };
}

function pendingApi(pending: Subject<EquityCandlesResponse>[]) {
  return {
    equityCandles: vi.fn().mockImplementation(() => {
      const subject = new Subject<EquityCandlesResponse>();
      pending.push(subject);
      return subject;
    }),
  };
}

/** A signal-backed PreferencesStore fake: `update` really changes `values()`,
 *  so the store's tf/basis computeds and the onInit effect react to a write
 *  exactly as they do against the real store. */
function setup(stored: Preferences = {}, api: { equityCandles: ReturnType<typeof vi.fn> } = okApi()) {
  const prefs = signal<Preferences>(stored);
  const scan = signal(0);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: ApiClient, useValue: api },
      { provide: EventStream, useValue: { changes: () => scan.asReadonly() } },
      { provide: PreferencesStore, useValue: {
          values: () => prefs(),
          update: (mutate: (p: Preferences) => Preferences) => prefs.update(mutate),
          isLoaded: () => true,
        } },
    ],
  });
  const store = TestBed.inject(EquityCandlesStore);
  const tick = () => TestBed.inject(ApplicationRef).tick();
  tick();
  return { api, store, prefs, scan, tick };
}

describe('EquityCandlesStore', () => {
  it('loads daily mark-to-market candles when nothing is stored', () => {
    const { api, store } = setup();
    expect(api.equityCandles).toHaveBeenCalledTimes(1);
    expect(api.equityCandles).toHaveBeenCalledWith('1D', 'mtm');
    expect(store.data()?.candles).toEqual([CANDLE]);
    expect(store.loading()).toBe(false);
    expect(store.error()).toBeNull();
  });

  it('loads the stored timeframe and basis', () => {
    const { api, store } = setup({ 'dashboard.equity.tf': '4H', 'dashboard.equity.basis': 'realized' });
    expect(api.equityCandles).toHaveBeenCalledWith('4H', 'realized');
    expect(store.tf()).toBe('4H');
    expect(store.basis()).toBe('realized');
  });

  it('writes the timeframe through PreferencesStore and refetches once', () => {
    const { api, store, prefs, tick } = setup();
    store.setTimeframe('1W');
    tick();
    expect(prefs()['dashboard.equity.tf']).toBe('1W');
    expect(prefs()['dashboard.equity.basis']).toBe('mtm');
    expect(api.equityCandles).toHaveBeenCalledTimes(2);
    expect(api.equityCandles).toHaveBeenLastCalledWith('1W', 'mtm');
  });

  it('writes the basis through PreferencesStore and refetches once', () => {
    const { api, store, prefs, tick } = setup();
    store.setBasis('realized');
    tick();
    expect(prefs()['dashboard.equity.basis']).toBe('realized');
    expect(api.equityCandles).toHaveBeenCalledTimes(2);
    expect(api.equityCandles).toHaveBeenLastCalledWith('1D', 'realized');
  });

  it('does not refetch on an unrelated preference write', () => {
    const { api, prefs, tick } = setup();
    prefs.update((p) => ({ ...p, 'tape.symbols': ['NVDA'] }));
    tick();
    expect(api.equityCandles).toHaveBeenCalledTimes(1);
  });

  it('refetches when a scan event arrives', () => {
    const { api, scan, tick } = setup();
    scan.update((n) => n + 1);
    tick();
    expect(api.equityCandles).toHaveBeenCalledTimes(2);
  });

  it('keeps the candles it has when a refetch fails', () => {
    const { api, store } = setup();
    api.equityCandles.mockReturnValue(throwError(() => new Error('boom')));
    store.load();
    expect(store.data()?.candles).toEqual([CANDLE]);
    expect(store.error()).toBeNull();
  });

  it('reports an error when the first load fails', () => {
    const api = { equityCandles: vi.fn().mockReturnValue(throwError(() => new Error('boom'))) };
    const { store } = setup({}, api);
    expect(store.data()).toBeNull();
    expect(store.error()).toBe(EQUITY_CANDLES_ERROR);
  });

  it('drops the previous view candles while a new timeframe loads', () => {
    const pending: Subject<EquityCandlesResponse>[] = [];
    const { store, tick } = setup({}, pendingApi(pending));
    pending[0].next(response('1D'));
    expect(store.data()?.tf).toBe('1D');

    store.setTimeframe('1H');
    tick();
    expect(store.data()).toBeNull();
    expect(store.loading()).toBe(true);
    pending[1].next(response('1H'));
    expect(store.data()?.tf).toBe('1H');
  });

  it('applies only the later of two overlapping loads', () => {
    const pending: Subject<EquityCandlesResponse>[] = [];
    const { store } = setup({}, pendingApi(pending));
    store.load();
    const stale = pending[0];
    const fresh = pending[1];
    fresh.next(response('1D', 'mtm', [{ ...CANDLE, c: 2 }]));
    stale.next(response('1D', 'mtm', [{ ...CANDLE, c: 1 }]));
    expect(store.data()?.candles[0].c).toBe(2);
  });
});
