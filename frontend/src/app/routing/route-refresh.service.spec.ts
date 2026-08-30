import { Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { RouteLoadingService } from './route-loading.service';
import { routeData } from './route-metadata';
import { RouteRefreshService } from './route-refresh.service';

describe('RouteRefreshService', () => {
  it('coalesces relevant events and reloads the current URL once', () => {
    vi.useFakeTimers();
    const raised = new Subject<'trades' | 'account' | 'jobs'>();
    const navigateByUrl = vi.fn();
    const router = { url: '/dashboard', events: new Subject(), navigateByUrl,
      routerState: { snapshot: { root: { data: {}, firstChild: { data: routeData('Dashboard', (event) => event === 'trades' || event === 'account'), firstChild: null } } } } };
    TestBed.configureTestingModule({ providers: [
      { provide: Router, useValue: router },
      { provide: EventStream, useValue: { raised } },
      { provide: RouteLoadingService, useValue: { pending: () => false } },
    ] });
    TestBed.inject(RouteRefreshService);
    raised.next('trades'); raised.next('account');
    vi.advanceTimersByTime(299);
    expect(navigateByUrl).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(navigateByUrl).toHaveBeenCalledWith('/dashboard', { onSameUrlNavigation: 'reload', replaceUrl: true });
    vi.useRealTimers();
  });
});