import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { EventStream } from '../api/event-stream';
import { authInterceptor, errorInterceptor, loadingInterceptor } from '../api/interceptors';
import { REFUSED, RESET } from './trades-clear.fixture';
import { TradesStore } from './trades.store';

/* v189 A6/A7: what the bulk clears now answer. Clear open names the plans it
 * ended; clear history is an archived reset that is refused while the kill
 * switch is tripped unless forced. */

const OPEN_URL = '/api/v1/trades/clear-open';
const HISTORY_URL = '/api/v1/trades/clear-history';

describe('TradesStore bulk clears (v189)', () => {
  let store: InstanceType<typeof TradesStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: { changes: () => signal(0) } },
        TradesStore,
      ],
    });
    store = TestBed.inject(TradesStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const post = (url: string) => backend.expectOne((r) => r.method === 'POST' && r.url === url);
  const fail = (url: string, status: number, code: string, message: string) =>
    post(url).flush({ error: { code, message } }, { status, statusText: 'x' });

  it('shows the clear-open notice naming the positions it ended', () => {
    const notice = 'Ended 1 open position(s): AAPL (`p1`, was PARTIAL). ...';
    store.clearOpen();
    post(OPEN_URL).flush({ removed: 2, ended: [{ plan_id: 'p1', ticker: 'AAPL', status_before: 'PARTIAL', status_after: 'CLOSED' }], notice });
    expect(store.clearResult()).toBe('Cleared 2 open positions.');
    expect(store.clearNotice()).toBe(notice);
  });

  it.each([{ removed: 1, ended: [], notice: '' }, { removed: 1 }])(
    'keeps no notice when nothing ended or the server sends none: %o', (body) => {
      store.clearOpen();
      post(OPEN_URL).flush(body);
      expect(store.clearResult()).toBe('Cleared 1 open position.');
      expect(store.clearNotice()).toBeNull();
    });

  it('sends no force by default and names the archive on success', () => {
    store.clearHistory();
    const req = post(HISTORY_URL);
    expect(req.request.body).toEqual({});
    req.flush(RESET);
    expect(store.clearResult()).toBe(
      'Cleared 4 closed trades and 2 finished plans. Archived as account-reset-20261024T101500Z.json.');
    expect(store.clearNotice()).toBe(RESET.notice);
    expect(store.clearRefusal()).toBeNull();
    expect(store.clearing()).toBeNull();
  });

  it('singularises one trade and one plan', () => {
    store.clearHistory();
    post(HISTORY_URL).flush({ ...RESET, removed: 1, removed_plans: 1 });
    expect(store.clearResult()).toBe(
      'Cleared 1 closed trade and 1 finished plan. Archived as account-reset-20261024T101500Z.json.');
  });

  it('holds a kill-switch refusal apart from an error, and never retries on its own', () => {
    store.clearHistory();
    fail(HISTORY_URL, 409, 'kill_switch_tripped', REFUSED);
    expect(store.clearRefusal()).toBe(REFUSED);
    expect(store.clearError()).toBeNull();
    expect(store.clearResult()).toBeNull();
    expect(store.clearing()).toBeNull();
    backend.expectNone((r) => r.url === HISTORY_URL);
  });

  it('sends force only when asked, and a forced retry clears the refusal at once', () => {
    store.clearHistory();
    fail(HISTORY_URL, 409, 'kill_switch_tripped', REFUSED);
    store.clearHistory(true);
    expect(store.clearRefusal()).toBeNull();
    const req = post(HISTORY_URL);
    expect(req.request.body).toEqual({ force: true });
    req.flush({ ...RESET, kill_switch: true });
    expect(store.clearResult()).toContain('Archived as');
  });

  it('reads an archive failure as its own error, not as a refusal', () => {
    store.clearHistory();
    fail(HISTORY_URL, 500, 'archive_failed', 'archive write failed: disk full');
    expect(store.clearError()).toBe('Nothing was cleared: the archive could not be written (archive write failed: disk full).');
    expect(store.clearRefusal()).toBeNull();
  });

  it('keeps the generic failure for anything else, on both clears', () => {
    store.clearOpen();
    fail(OPEN_URL, 409, 'conflict', 'another change holds the trade; try again');
    expect(store.clearError()).toBe('Nothing was cleared — another change holds the trade; try again');
    store.clearHistory();
    fail(HISTORY_URL, 503, 'unavailable', 'The admin could not be reached.');
    expect(store.clearError()).toBe('Nothing was cleared — The admin could not be reached.');
    expect(store.clearRefusal()).toBeNull();
  });

  it('starts every clear from a blank slate', () => {
    store.clearHistory();
    fail(HISTORY_URL, 409, 'kill_switch_tripped', REFUSED);
    store.clearOpen();
    expect([store.clearResult(), store.clearNotice(), store.clearRefusal(), store.clearError()])
      .toEqual([null, null, null, null]);
    post(OPEN_URL).flush({ removed: 0, ended: [], notice: '' });
  });
});
