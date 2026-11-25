import { WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { RegimeDay, RegimeResponse } from '../api/models';
import { RegimeStore, regimeBanner } from './regime.store';

const NUMBERS = 'SPY −5.7% vs SMA200 · −9.3% vs SMA50 · VIX 37.6';

function regimeDay(over: Partial<RegimeDay> = {}): RegimeDay {
  return {
    session_date: '2026-11-19', last_bar_date: '2026-11-18', state: 'CORRECTION', stress: true,
    pullback_trigger: false, pullback_reason: null, spy_close: 650, sma50: 716, sma200: 690,
    sma50_lag5: 720, sma200_lag20: 680, spy_high_prev: 655, vix_close: 37.6, vix_max5: 40.1,
    spy_provider: 'alpaca', vix_provider: 'yfinance', computed_at: '2026-11-18T21:05:00+00:00',
    display: { label: 'Correction · Stress', words: 'dip in an uptrend, high volatility', numbers: NUMBERS },
    ...over,
  };
}

function regimeResponse(over: Partial<RegimeResponse> = {}): RegimeResponse {
  return { mode: 'shadow', today: regimeDay(), history: [regimeDay()],
           episode: { label: 'Correction · Stress', since_sessions: 6 }, ...over };
}

const pullbackDay = regimeDay({
  stress: false, pullback_trigger: true,
  display: { label: 'Pullback watch', words: 'panic easing inside a correction', numbers: NUMBERS },
});

describe('regimeBanner', () => {
  it('reads a stress correction with its confirmed count and the number form', () => {
    expect(regimeBanner(regimeResponse())).toEqual({
      kind: 'reading', tone: 'correction', label: 'Correction · Stress', since: 6, numbers: NUMBERS,
      words: 'Dip in an uptrend, high volatility.', pullback: false,
      accessibleName: `Regime Correction, stress, 6 sessions; ${NUMBERS}`,
    });
  });

  it.each([
    ['no response', null],
    ['mode off', regimeResponse({ mode: 'off', today: null, history: [], episode: null })],
    ['no stored row for D', regimeResponse({ today: null })],
    ['NORMAL', regimeResponse({ today: regimeDay({ state: 'NORMAL', stress: false,
      display: { label: 'Normal', words: 'no correction or bear trend', numbers: NUMBERS } }) })],
  ])('is hidden on %s', (_name, res) => {
    expect(regimeBanner(res)).toBeNull();
  });

  it('shows a muted no-reading line on UNKNOWN and never the episode label', () => {
    const unknown = regimeDay({ state: 'UNKNOWN', stress: null, spy_close: null, sma50: null, sma200: null,
      vix_close: null, display: { label: 'No reading', words: '—', numbers: null } });
    expect(regimeBanner(regimeResponse({ today: unknown }))).toEqual({
      kind: 'none', tone: 'muted', label: 'No reading', since: null, numbers: null, words: null,
      pullback: false, accessibleName: 'Regime: no reading',
    });
  });

  it('keeps the correction title and adds the pullback chip on a pullback day', () => {
    const b = regimeBanner(regimeResponse({ today: pullbackDay, episode: { label: 'Correction', since_sessions: 3 } }))!;
    expect([b.label, b.pullback, b.since]).toEqual(['Correction', true, 3]);
    expect(b.words).toBe('Panic easing inside a correction.');
    expect(b.accessibleName).toBe(`Regime Correction, 3 sessions, pullback watch; ${NUMBERS}`);
  });

  it.each([null, { label: 'Normal', since_sessions: 9 }, { label: 'No reading', since_sessions: 2 }])(
    'titles a pullback day "Pullback watch" without a repeated chip when the episode is %o', (episode) => {
      const b = regimeBanner(regimeResponse({ today: pullbackDay, episode }))!;
      expect([b.label, b.pullback, b.since]).toEqual(['Pullback watch', false, null]);
    });

  it('drops the count when the confirmed episode carries another label (a one-day flicker)', () => {
    const b = regimeBanner(regimeResponse({ episode: { label: 'Correction', since_sessions: 4 } }))!;
    expect(b.since).toBeNull();
    expect(b.accessibleName).toBe(`Regime Correction, stress; ${NUMBERS}`);
  });

  it('gives BEAR the bear tone, a singular count and no numbers clause when numbers are null', () => {
    const bear = regimeDay({ state: 'BEAR', stress: null,
      display: { label: 'Bear', words: 'trend has turned down', numbers: null } });
    const b = regimeBanner(regimeResponse({ today: bear, episode: { label: 'Bear', since_sessions: 1 } }))!;
    expect([b.tone, b.label, b.numbers, b.accessibleName]).toEqual(['bear', 'Bear', null, 'Regime Bear, 1 session']);
  });
});

describe('RegimeStore', () => {
  let calls: Subject<RegimeResponse>[];
  let scan: WritableSignal<number>;

  beforeEach(() => {
    calls = [];
    scan = signal(0);
    const marketRegime = vi.fn(() => {
      const s = new Subject<RegimeResponse>();
      calls.push(s);
      return s;
    });
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        { provide: ApiClient, useValue: { marketRegime } },
        { provide: EventStream, useValue: { changes: () => scan } },
      ],
    });
  });
  afterEach(() => vi.restoreAllMocks());

  function start(): RegimeStore {
    const store = TestBed.inject(RegimeStore);
    TestBed.tick();
    return store;
  }

  it('is loading and hidden until the first answer, then shows it', () => {
    const store = start();
    expect([store.status(), store.banner()]).toEqual(['loading', null]);
    calls[0].next(regimeResponse());
    expect(store.status()).toBe('ready');
    expect(store.banner()?.label).toBe('Correction · Stress');
  });

  it('clears the banner and logs on a fetch error, never keeping a stale label', () => {
    const log = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const store = start();
    calls[0].next(regimeResponse());
    store.refresh();
    calls[1].error(new Error('502'));
    expect([store.status(), store.banner()]).toEqual(['error', null]);
    expect(log).toHaveBeenCalledTimes(1);
  });

  it('keeps the shown banner while a refetch is in flight, and ignores a superseded answer', () => {
    const store = start();
    calls[0].next(regimeResponse());
    store.refresh();
    store.refresh();
    expect(store.banner()?.label).toBe('Correction · Stress');
    calls[1].next(regimeResponse({ today: null }));
    expect(store.banner()?.label).toBe('Correction · Stress');
    calls[2].next(regimeResponse({ mode: 'off', today: null, history: [], episode: null }));
    expect(store.banner()).toBeNull();
  });

  it('refetches when a scan event lands (the pass writes the row)', () => {
    start();
    scan.set(1);
    TestBed.tick();
    expect(calls.length).toBe(2);
  });
});
