import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { VersionHistory } from '../api/models';
import { VersionsStore } from './versions.store';

/* The Versions workspace's data.
 *
 * What earns tests here is the GEOMETRY, not the fetch. The matrix draws a bar
 * from a start column across a span and puts dots on specific columns; every
 * one of those is an index into `bot_versions`, and an off-by-one produces a
 * page that looks entirely plausible and is wrong. The fetch itself is the same
 * shape as every other store and is covered only where it fails.
 */

const RESPONSE: VersionHistory = {
  generated_at: '2026-08-15 07:00:00 UTC',
  basis: 'Versions observed together in VERSION.json.',
  live: { ui: '1.2.0', bot: '1.1.2' },
  stale: false,
  ui_versions: ['1.0.4', '1.1.0', '1.2.0'],
  bot_versions: ['1.0.5', '1.0.6', '1.0.10', '1.1.0', '1.1.2'],
  pairs: [
    // 1.0.4 skips 1.0.6 deliberately: the span covers it, no pair shipped on
    // it, and the dots are what tell those two situations apart.
    { ui: '1.0.4', bot: '1.0.5', first_seen: '2026-07-08', last_seen: '2026-07-08' },
    { ui: '1.0.4', bot: '1.0.10', first_seen: '2026-07-09', last_seen: '2026-07-09' },
    { ui: '1.1.0', bot: '1.1.0', first_seen: '2026-07-18', last_seen: '2026-07-18' },
    { ui: '1.2.0', bot: '1.1.2', first_seen: '2026-08-14', last_seen: '2026-08-14' },
  ],
  ranges: [
    { ui: '1.0.4', bot_min: '1.0.5', bot_max: '1.0.10', bot_count: 2,
      first_seen: '2026-07-08', last_seen: '2026-07-09' },
    { ui: '1.1.0', bot_min: '1.1.0', bot_max: '1.1.0', bot_count: 1,
      first_seen: '2026-07-18', last_seen: '2026-07-18' },
    { ui: '1.2.0', bot_min: '1.1.2', bot_max: '1.1.2', bot_count: 1,
      first_seen: '2026-08-14', last_seen: '2026-08-14' },
  ],
};

function setup(response: VersionHistory | null = RESPONSE) {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(
        withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor]),
      ),
      provideHttpClientTesting(),
      VersionsStore,
    ],
  });

  const store = TestBed.inject(VersionsStore);
  const http = TestBed.inject(HttpTestingController);
  const request = http.expectOne('/api/v1/versions');
  if (response) request.flush(response);
  return { store, http, request };
}

describe('VersionsStore', () => {
  it('loads on init', () => {
    const { store } = setup();
    expect(store.pairCount()).toBe(4);
    expect(store.empty()).toBe(false);
  });

  it('orders rows newest ui first', () => {
    const { store } = setup();
    expect(store.rows().map((r) => r.ui)).toEqual(['1.2.0', '1.1.0', '1.0.4']);
  });

  it('resolves the bar to 1-based grid columns', () => {
    const { store } = setup();
    const row = store.rows().find((r) => r.ui === '1.0.4')!;
    // bot_versions[0] is 1.0.5 -> column 1; 1.0.10 is index 2 -> column 3.
    expect(row.start).toBe(1);
    expect(row.span).toBe(3);
  });

  it('a single-version range still spans one column', () => {
    const { store } = setup();
    const row = store.rows().find((r) => r.ui === '1.2.0')!;
    expect(row.start).toBe(5);
    expect(row.span).toBe(1);
  });

  it('dots mark only the pairs that actually shipped', () => {
    const { store } = setup();
    const row = store.rows().find((r) => r.ui === '1.0.4')!;
    // Columns 1 and 3, NOT 2 -- 1.0.6 falls inside the span with no pair.
    expect(row.shipped).toEqual([1, 3]);
  });

  it('every dot falls inside its own row span', () => {
    const { store } = setup();
    for (const row of store.rows()) {
      for (const column of row.shipped) {
        expect(column).toBeGreaterThanOrEqual(row.start);
        expect(column).toBeLessThan(row.start + row.span);
      }
    }
  });

  it('marks the row matching the live ui version', () => {
    const { store } = setup();
    expect(store.rows().filter((r) => r.current).map((r) => r.ui)).toEqual(['1.2.0']);
  });

  it('exposes the server basis verbatim rather than restating it', () => {
    const { store } = setup();
    expect(store.basis()).toBe(RESPONSE.basis);
  });

  it('surfaces the stale flag', () => {
    const { store } = setup({ ...RESPONSE, stale: true });
    expect(store.stale()).toBe(true);
  });

  it('renders nothing rather than throwing when history is empty', () => {
    const { store } = setup({
      ...RESPONSE, ui_versions: [], bot_versions: [], pairs: [], ranges: [],
    });
    expect(store.rows()).toEqual([]);
    expect(store.botAxis()).toEqual([]);
  });

  it('keeps an error message and stays renderable', () => {
    const { store, request } = setup(null);
    request.flush({ error: { code: 'unavailable', message: 'down' } },
                  { status: 503, statusText: 'Service Unavailable' });
    expect(store.error()).toBeTruthy();
    expect(store.rows()).toEqual([]);
  });
});
