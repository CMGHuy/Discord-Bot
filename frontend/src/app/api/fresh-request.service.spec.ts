import { HttpClient, HttpContext, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BOOT_FRESH_WINDOW_MS, FRESH_HEADER, FRESH_REQUEST, FreshRequestService } from './fresh-request.service';
import { freshInterceptor } from './interceptors';

@Component({ template: '' })
class Blank {}

describe('FreshRequestService (v171 D2: reload means fresh, navigation means reuse)', () => {
  let http: HttpClient;
  let backend: HttpTestingController;
  let router: Router;
  let fresh: FreshRequestService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'a', component: Blank }, { path: 'b', component: Blank }]),
        provideHttpClient(withInterceptors([freshInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    backend = TestBed.inject(HttpTestingController);
    router = TestBed.inject(Router);
    fresh = TestBed.inject(FreshRequestService);
  });

  const header = (url: string) => {
    const req = backend.expectOne(url);
    const value = req.request.headers.get(FRESH_HEADER);
    req.flush({});
    return value;
  };

  it('marks every GET of a full page load', () => {
    http.get('/api/v1/dashboard').subscribe();
    expect(header('/api/v1/dashboard')).toBe('1');
  });

  it('still marks after the initial navigation (one NavigationStart)', async () => {
    await router.navigateByUrl('/a');
    expect(fresh.isBootPhase()).toBe(true);
    http.get('/api/v1/trades').subscribe();
    expect(header('/api/v1/trades')).toBe('1');
  });

  it('stops marking at the first in-app navigation', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    expect(fresh.isBootPhase()).toBe(false);
    http.get('/api/v1/watchlist/tickers').subscribe();
    expect(header('/api/v1/watchlist/tickers')).toBeNull();
  });

  it('ends the boot phase 10 s after the first NavigationEnd on the same route', async () => {
    vi.useFakeTimers({ toFake: ['Date'] });   // zoneless app, no zone.js: vitest clock, not fakeAsync
    try {
      await router.navigateByUrl('/a');
      vi.setSystemTime(Date.now() + BOOT_FRESH_WINDOW_MS - 1);
      expect(fresh.isBootPhase()).toBe(true);
      vi.setSystemTime(Date.now() + 2);
      expect(fresh.isBootPhase()).toBe(false);
      http.get('/api/v1/market/tape').subscribe();
      expect(header('/api/v1/market/tape')).toBeNull();
    } finally { vi.useRealTimers(); }
  });

  it('marks requests issued inside markFresh after the boot phase', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    fresh.markFresh(() => http.get('/api/v1/trades').subscribe());
    expect(header('/api/v1/trades')).toBe('1');
    http.get('/api/v1/trades?x=1').subscribe();
    expect(header('/api/v1/trades?x=1')).toBeNull();
  });

  it('marks a request carrying the FRESH_REQUEST context token', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    http.get('/api/v1/risk', { context: new HttpContext().set(FRESH_REQUEST, true) }).subscribe();
    expect(header('/api/v1/risk')).toBe('1');
  });

  it('never marks a mutation, even in the boot phase', () => {
    http.post('/api/v1/trades/x/close', {}).subscribe();
    expect(header('/api/v1/trades/x/close')).toBeNull();
  });

  it('returns the callback value, nests, and restores the depth when the callback throws', () => {
    expect(fresh.markFresh(() => fresh.markFresh(() => fresh.isMarking()))).toBe(true);
    expect(fresh.isMarking()).toBe(false);
    expect(() => fresh.markFresh(() => { throw new Error('boom'); })).toThrow('boom');
    expect(fresh.isMarking()).toBe(false);
  });
});
