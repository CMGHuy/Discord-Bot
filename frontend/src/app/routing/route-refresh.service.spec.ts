import { Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EventName, EventStream } from '../api/event-stream';
import { RouteLoadingService, BACKGROUND_REFRESH_INFO } from './route-loading.service';
import { RefreshPredicate, routeData } from './route-metadata';
import { EVENT_MIN_INTERVAL_MS, RouteRefreshService } from './route-refresh.service';

describe('RouteRefreshService', () => {
  let raised: Subject<EventName>;
  let navigateByUrl: ReturnType<typeof vi.fn>;

  const start = (refreshOn: RefreshPredicate, url = '/dashboard') => {
    raised = new Subject<EventName>();
    navigateByUrl = vi.fn();
    const router = { url, events: new Subject(), navigateByUrl,
      routerState: { snapshot: { root: { data: {}, firstChild: { data: routeData('Page', refreshOn), firstChild: null } } } } };
    TestBed.configureTestingModule({ providers: [
      { provide: Router, useValue: router },
      { provide: EventStream, useValue: { raised } },
      { provide: RouteLoadingService, useValue: { pending: () => false } },
    ] });
    TestBed.inject(RouteRefreshService);
  };

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    TestBed.resetTestingModule();
    vi.useRealTimers();
  });

  it('coalesces relevant events and reloads the current URL once', () => {
    start((event) => event === 'trades' || event === 'account');
    raised.next('trades'); raised.next('account');
    vi.advanceTimersByTime(299);
    expect(navigateByUrl).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(navigateByUrl).toHaveBeenCalledWith('/dashboard', { onSameUrlNavigation: 'reload', replaceUrl: true, info: BACKGROUND_REFRESH_INFO });
  });

  it('limits only scan, to 5 s (v206)', () => {
    expect(EVENT_MIN_INTERVAL_MS).toEqual({ scan: 5000 });
  });

  it('reloads a scan-driven route at most once per 5 s while a scan raises scan every second', () => {
    start((event) => event === 'scan', '/system/scan');
    const at: number[] = [];
    navigateByUrl.mockImplementation(() => at.push(Date.now()));
    const t0 = Date.now();
    for (let second = 0; second < 10; second++) {
      raised.next('scan');
      vi.advanceTimersByTime(1000);
    }
    vi.advanceTimersByTime(10_000);
    // Leading at 0 s, then one trailing reload per 5 s window: 0.3, 5.3, 10.3 s.
    expect(at.map((t) => t - t0)).toEqual([300, 5300, 10_300]);
  });

  it('never drops the last scan of a burst: it lands at the end of the window', () => {
    start((event) => event === 'scan', '/system/scan');
    raised.next('scan');
    vi.advanceTimersByTime(1000);
    raised.next('scan');
    vi.advanceTimersByTime(4299);
    expect(navigateByUrl).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(1);
    expect(navigateByUrl).toHaveBeenCalledTimes(2);
  });

  it('keeps the plain 300 ms debounce for every other event', () => {
    start((event) => event === 'trades', '/trades');
    raised.next('trades');
    vi.advanceTimersByTime(1000);
    raised.next('trades');
    vi.advanceTimersByTime(300);
    expect(navigateByUrl).toHaveBeenCalledTimes(2);
  });

  it('a held-back scan does not hold back another event', () => {
    start((event) => event === 'scan' || event === 'bot', '/system/providers');
    raised.next('scan');
    vi.advanceTimersByTime(1000);
    raised.next('scan'); // held until 5 s
    raised.next('bot');
    vi.advanceTimersByTime(300);
    expect(navigateByUrl).toHaveBeenCalledTimes(2); // 0.3 s (scan) and 1.3 s (bot)
  });

  it('cancels a pending scan when the service is destroyed', () => {
    start((event) => event === 'scan', '/system/scan');
    raised.next('scan');
    vi.advanceTimersByTime(1000);
    raised.next('scan');
    TestBed.resetTestingModule();
    vi.advanceTimersByTime(10_000);
    expect(navigateByUrl).toHaveBeenCalledTimes(1);
  });
});
