import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from './api-client';
import { ApiError } from './api-error';
import { authInterceptor, errorInterceptor, loadingInterceptor, routeRefreshInterceptor } from './interceptors';
import { RouteRefreshService } from '../routing/route-refresh.service';
import { LoadingService } from './loading.service';
import { UnauthorizedService } from './unauthorized.service';

/* NG27 — the HTTP layer.
 *
 * The interceptors are registered here in the SAME order as app.config.ts,
 * because that order is load-bearing: auth has to see a raw
 * HttpErrorResponse to recognise a 401, and it only does when it sits
 * innermost. A test that registered them differently would pass while the
 * application was broken.
 */

describe('http interceptors', () => {
  let http: HttpClient;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: RouteRefreshService, useValue: { requestMutationRefresh: () => undefined } },
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
  });

  const fail = (
    body: string | Object,
    status: number,
    statusText = 'Error',
    url = '/api/v1/dashboard',
  ) =>
    new Promise<ApiError>((resolve) => {
      http.get(url).subscribe({ error: (e: ApiError) => resolve(e) });
      backend.expectOne(url).flush(body, { status, statusText });
    });

  /* -- auth ------------------------------------------------------------ */

  it('sends the session cookie', () => {
    http.get('/api/v1/dashboard').subscribe();
    expect(backend.expectOne((req) => req.url === '/api/v1/dashboard').request.withCredentials).toBe(true);
  });

  it('reports a 401 to the unauthorized seam', async () => {
    const unauthorized = TestBed.inject(UnauthorizedService);
    const before = unauthorized.seen();

    await fail({ error: { code: 'auth', message: 'Authentication required.' } }, 401);

    expect(unauthorized.seen()).toBe(before + 1);
  });

  it('does not report a 401 for other failures', async () => {
    const unauthorized = TestBed.inject(UnauthorizedService);
    const before = unauthorized.seen();

    await fail({ error: { code: 'not_found', message: 'nope' } }, 404);

    expect(unauthorized.seen()).toBe(before);
  });

  it('does NOT retry a 401', async () => {
    // The instinct is to refresh and retry. There is nothing to refresh --
    // auth is a signed session cookie -- so a retry would just fail twice,
    // and on a password change it would do that for every request forever.
    await fail({ error: { code: 'auth', message: 'gone' } }, 401);
    backend.verify(); // a retry would leave a second outstanding request
  });

  /* -- errors ---------------------------------------------------------- */

  it('turns a v1 error body into a typed ApiError', async () => {
    const error = await fail(
      { error: { code: 'invalid', message: 'unknown parameter' } },
      400,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe('invalid');
    expect(error.status).toBe(400);
    expect(error.message).toBe('unknown parameter');
  });

  it('calls a non-JSON failure unavailable', async () => {
    // A proxy error page, or Flask's own HTML 500. From the client's point
    // of view an API that answers in HTML is an API that is not answering.
    const error = await fail('<html>502 Bad Gateway</html>', 502);

    expect(error.code).toBe('unavailable');
    expect(error.status).toBe(502);
  });

  it('calls a JSON body without the v1 error shape unavailable', async () => {
    const error = await fail({ detail: 'something else entirely' }, 500);

    expect(error.code).toBe('unavailable');
  });

  it('calls an unreachable server unavailable, with status 0', async () => {
    const error = await new Promise<ApiError>((resolve) => {
      http.get('/api/v1/dashboard').subscribe({ error: (e: ApiError) => resolve(e) });
      backend
        .expectOne((req) => req.url === '/api/v1/dashboard')
        .error(new ProgressEvent('error'), { status: 0, statusText: '' });
    });

    expect(error.code).toBe('unavailable');
    expect(error.status).toBe(0);
    expect(error.message).toContain('could not be reached');
  });

  it('marks auth failures as such however they arrive', () => {
    expect(new ApiError('auth', 401, 'x').isAuth).toBe(true);
    expect(new ApiError('unavailable', 401, 'x').isAuth).toBe(true);
    expect(new ApiError('invalid', 400, 'x').isAuth).toBe(false);
  });

  /* -- loading --------------------------------------------------------- */

  it('counts a request while it is in flight', () => {
    const loading = TestBed.inject(LoadingService);
    expect(loading.isLoading()).toBe(false);

    http.get('/api/v1/dashboard').subscribe();
    expect(loading.inFlight()).toBe(1);

    backend.expectOne((req) => req.url === '/api/v1/dashboard').flush({});
    expect(loading.inFlight()).toBe(0);
    expect(loading.isLoading()).toBe(false);
  });

  it('counts overlapping requests', () => {
    const loading = TestBed.inject(LoadingService);

    http.get('/api/v1/dashboard').subscribe();
    http.get('/api/v1/risk').subscribe();
    expect(loading.inFlight()).toBe(2);

    // A boolean flag would clear here, while one request is still open.
    backend.expectOne((req) => req.url === '/api/v1/dashboard').flush({});
    expect(loading.isLoading()).toBe(true);

    backend.expectOne('/api/v1/risk').flush({});
    expect(loading.isLoading()).toBe(false);
  });

  it('stops counting a failed request', async () => {
    const loading = TestBed.inject(LoadingService);

    await fail({ error: { code: 'not_found', message: 'nope' } }, 404);

    expect(loading.inFlight()).toBe(0);
  });

  it('stops counting a cancelled request', () => {
    // The common case: switchMap cancels the previous request every time a
    // filter changes. tap() would miss this; finalize() does not.
    const loading = TestBed.inject(LoadingService);

    const subscription = http.get('/api/v1/trades').subscribe();
    expect(loading.inFlight()).toBe(1);

    subscription.unsubscribe();
    expect(loading.inFlight()).toBe(0);
  });

  it('requests a route refresh after a successful mutation', () => {
    const refresh = TestBed.inject(RouteRefreshService);
    const requestMutationRefresh = vi.spyOn(refresh, 'requestMutationRefresh');
    http.post('/api/v1/trades', {}).subscribe();
    backend.expectOne('/api/v1/trades').flush({});
    expect(requestMutationRefresh).toHaveBeenCalledOnce();
  });

  it('never counts below zero', () => {
    const loading = TestBed.inject(LoadingService);
    loading.finished();
    loading.finished();

    http.get('/api/v1/dashboard').subscribe();

    // Without the clamp the counter would be -1 here, and isLoading() would
    // stay false through this request and the next one.
    expect(loading.isLoading()).toBe(true);
    backend.expectOne((req) => req.url === '/api/v1/dashboard').flush({});
  });
});

describe('ApiClient', () => {
  let api: ApiClient;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor, routeRefreshInterceptor]),
        ),
        provideHttpClientTesting(),
        { provide: RouteRefreshService, useValue: { requestMutationRefresh: () => undefined } },
      ],
    });
    api = TestBed.inject(ApiClient);
    backend = TestBed.inject(HttpTestingController);
  });

  it('addresses the v1 namespace with relative URLs', () => {
    // Relative so the same bundle works behind ng serve's proxy, behind
    // Flask, and behind any reverse proxy in front of either.
    api.dashboard().subscribe();
    expect(backend.expectOne((req) => req.url === '/api/v1/dashboard').request.method).toBe('GET');
  });

  it('drops empty query parameters instead of sending them', () => {
    api.trades({ page: 2, ticker: '', status: undefined }).subscribe();

    const request = backend.expectOne((r) => r.url === '/api/v1/trades');
    expect(request.request.params.get('page')).toBe('2');
    expect(request.request.params.has('ticker')).toBe(false);
    expect(request.request.params.has('status')).toBe(false);
  });

  it('sends a boolean filter as a value the API parses', () => {
    api.trades({ has_note: true }).subscribe();

    const request = backend.expectOne((r) => r.url === '/api/v1/trades');
    expect(request.request.params.get('has_note')).toBe('true');
  });

  it('escapes ids that would otherwise change the path', () => {
    api.trade('a/b').subscribe();
    backend.expectOne('/api/v1/trades/a%2Fb');
  });

  it('returns download URLs rather than fetching them', () => {
    // An XHR would discard the Save dialog and the server's filename.
    //
    // NG54: the trades export takes NO query. It used to accept one and pass
    // it along, and the endpoint ignored every parameter — so a filtered view
    // exported the whole book while the link implied otherwise. The endpoint
    // exports the trade log, which is not the set the collection shows, so
    // there is no query it could honour.
    expect(api.tradesExportUrl()).toBe('/api/v1/trades/export.csv');
    expect(api.settingsExportUrl()).toBe('/api/v1/system/settings/export');
    backend.verify();
  });
});
