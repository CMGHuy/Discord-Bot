import { provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  ResolveFn,
  RouterStateSnapshot,
  convertToParamMap,
} from '@angular/router';
import { Observable, of } from 'rxjs';
import { describe, expect, it } from 'vitest';

import { EventStream } from '../../api/event-stream';
import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../../api/interceptors';
import { Preferences } from '../../api/models';
import { PreferencesStore } from '../../stores/preferences.store';
import { SessionStore } from '../../stores/session.store';
import { TradesStore } from '../../stores/trades.store';
import { ViewportService } from '../../ui/breakpoints';
import { ALL_PER_PAGE, API_MAX_PER_PAGE } from '../../ui/table-prefs';
import { queryFor, tradesRoutes } from './trades.routes';

/* v194 B2 -- "All" rows asks the API for its 200-row cap, whether the
 * choice arrives in the URL or is restored from the saved preference. */

const snapshot = (params: Record<string, string>) =>
  ({ queryParamMap: convertToParamMap(params) }) as ActivatedRouteSnapshot;

describe('queryFor', () => {
  it('turns "All" in the URL into the API cap, not the default 10', () => {
    expect(queryFor(snapshot({ per_page: String(ALL_PER_PAGE) }), 10).per_page).toBe(API_MAX_PER_PAGE);
  });

  it('uses the saved choice when the URL names none', () => {
    expect(queryFor(snapshot({}), ALL_PER_PAGE).per_page).toBe(API_MAX_PER_PAGE);
    expect(queryFor(snapshot({}), 50).per_page).toBe(50);
  });

  it('lets an offered URL choice win over the saved one', () => {
    expect(queryFor(snapshot({ per_page: '50' }), ALL_PER_PAGE).per_page).toBe(50);
    expect(queryFor(snapshot({ per_page: '0' }), 20).per_page).toBe(API_MAX_PER_PAGE);
  });

  it('ignores a URL value that is not an offered choice', () => {
    for (const raw of ['', ' ', 'abc', '7', '-1', '1e2', '500']) {
      expect(queryFor(snapshot({ per_page: raw }), 20).per_page).toBe(20);
    }
  });

  it('still reads page, sort and the filters as before', () => {
    const query = queryFor(snapshot({ page: '3', sort: '-pnl_pct', status: 'open', ticker: 'AAPL' }), 10);
    expect(query).toEqual({ page: 3, per_page: 10, sort: '-pnl_pct', status: 'open', ticker: 'AAPL' });
    expect(queryFor(snapshot({ page: 'x' }), 10).page).toBe(1);
  });
});

describe('the Trades route resolver', () => {
  /** Runs the real resolver with the given saved preferences, URL params and
   *  device class; returns the one /api/v1/trades request it made. */
  function resolveWith(prefs: Preferences, params: Record<string, string>, narrow = false) {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
        { provide: EventStream, useValue: { changes: () => signal(0) } },
        { provide: PreferencesStore, useValue: { resolve: () => of(undefined), values: () => prefs } },
        { provide: SessionStore, useValue: { expire: () => undefined } },
        { provide: ViewportService, useValue: { isNarrow: signal(narrow) } },
        TradesStore,
      ],
    });
    const resolver = tradesRoutes[0].resolve!['ready'] as ResolveFn<boolean>;
    const state = { url: '/trades' } as RouterStateSnapshot;
    (TestBed.runInInjectionContext(() => resolver(snapshot(params), state)) as Observable<boolean>).subscribe();
    return TestBed.inject(HttpTestingController).expectOne((r) => r.url === '/api/v1/trades');
  }

  it('requests per_page=200 when "All" is chosen (it lands in the URL as 0)', () => {
    const request = resolveWith({} as Preferences, { per_page: String(ALL_PER_PAGE) });
    expect(request.request.params.get('per_page')).toBe(String(API_MAX_PER_PAGE));
  });

  it('requests per_page=200 for a saved "All" with no per_page in the URL', () => {
    const request = resolveWith({ 'tables.trades.desktop.per_page': ALL_PER_PAGE } as Preferences, {});
    expect(request.request.params.get('per_page')).toBe(String(API_MAX_PER_PAGE));
  });

  it('restores a saved "All" on a phone or tablet from that device class\'s key', () => {
    const request = resolveWith({ 'tables.trades.compact.per_page': ALL_PER_PAGE } as Preferences, {}, true);
    expect(request.request.params.get('per_page')).toBe(String(API_MAX_PER_PAGE));
  });

  it('asks for the desktop default when nothing is saved', () => {
    expect(resolveWith({} as Preferences, {}).request.params.get('per_page')).toBe('10');
  });

  it('asks for the compact default on a phone or tablet when nothing is saved', () => {
    expect(resolveWith({} as Preferences, {}, true).request.params.get('per_page')).toBe('5');
  });
});
