import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from '../api/api-error';
import { errorInterceptor } from '../api/interceptors';
import { ToastService } from '../shell/toast.service';
import { FORBIDDEN_TOAST, forbiddenInterceptor } from './forbidden.interceptor';

const FORBIDDEN = { error: { code: 'forbidden', message: 'Read-only account.' } };

describe('forbiddenInterceptor (v207)', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let toasts: ToastService;

  beforeEach(() => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([forbiddenInterceptor, errorInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    toasts = TestBed.inject(ToastService);
  });

  afterEach(() => vi.useRealTimers());

  function call(method: string, url: string, body: object, status: number): unknown {
    let caught: unknown = null;
    http.request(method, url, { body: {} }).subscribe({ error: (error: unknown) => (caught = error) });
    backend.expectOne(url).flush(body, { status, statusText: String(status) });
    return caught;
  }

  it('toasts "Read-only account" once and still hands the caller the ApiError', () => {
    const error = call('POST', '/api/v1/trades/7/close', FORBIDDEN, 403);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('forbidden');
    expect((error as ApiError).status).toBe(403);
    expect(toasts.toasts().map((t) => [t.message, t.kind])).toEqual([[FORBIDDEN_TOAST, 'warn']]);
    expect(FORBIDDEN_TOAST).toBe('Read-only account');
  });

  it.each(['PUT', 'GET'])('stays silent for a %s on /system/preferences', (method) => {
    const error = call(method, '/api/v1/system/preferences', FORBIDDEN, 403);
    expect((error as ApiError).code).toBe('forbidden');
    expect(toasts.toasts()).toEqual([]);
  });

  it('shows one toast for a burst, and toasts again once it has gone', () => {
    call('GET', '/api/v1/jobs', FORBIDDEN, 403);
    call('GET', '/api/v1/versions', FORBIDDEN, 403);
    call('DELETE', '/api/v1/trades/7', FORBIDDEN, 403);
    expect(toasts.toasts()).toHaveLength(1);
    vi.advanceTimersByTime(4000);
    expect(toasts.toasts()).toEqual([]);
    call('POST', '/api/v1/watchlist/tickers', FORBIDDEN, 403);
    expect(toasts.toasts()).toHaveLength(1);
  });

  it.each([
    [401, { error: { code: 'auth', message: 'Authentication required.' } }],
    [404, { error: { code: 'not_found', message: 'No such trade.' } }],
    [500, { error: { code: 'unavailable', message: 'Boom.' } }],
    [403, '<html>proxy says no</html>'],
  ])('ignores a %s that is not a v1 forbidden', (status, body) => {
    call('POST', '/api/v1/trades/7/close', body as object, status as number);
    expect(toasts.toasts()).toEqual([]);
  });

  it('passes a success through untouched', () => {
    let answer: unknown = null;
    http.get('/api/v1/dashboard').subscribe((value) => (answer = value));
    backend.expectOne('/api/v1/dashboard').flush({ ok: true });
    expect(answer).toEqual({ ok: true });
    expect(toasts.toasts()).toEqual([]);
  });
});

describe('app.config interceptor order (v207)', () => {
  it('puts forbiddenInterceptor after loading and before error', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/app.config.ts'), 'utf8');
    const list = /withInterceptors\(\[([^\]]*)\]\)/.exec(source)![1].split(',').map((name) => name.trim()).filter(Boolean);
    expect(list).toEqual([
      'loadingInterceptor', 'forbiddenInterceptor', 'errorInterceptor',
      'authInterceptor', 'routeRefreshInterceptor', 'freshInterceptor',
    ]);
  });
});
