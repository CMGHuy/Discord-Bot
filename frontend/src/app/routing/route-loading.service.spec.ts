import { NavigationCancel, Router, RouterStateSnapshot, ResolveEnd, ResolveStart } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { routeData } from './route-metadata';
import { RouteLoadingService } from './route-loading.service';

function routeState(label: string): RouterStateSnapshot {
  return { root: { data: {}, firstChild: { data: routeData(label, () => true), firstChild: null } } } as unknown as RouterStateSnapshot;
}

describe('RouteLoadingService', () => {
  afterEach(() => vi.useRealTimers());

  it('suppresses fast resolution and exposes slow resolution after one second', () => {
    vi.useFakeTimers();
    const events = new Subject<unknown>();
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { events } }] });
    const service = TestBed.inject(RouteLoadingService);
    const state = routeState('Trades');
    events.next(new ResolveStart(1, '/trades', '/trades', state));
    vi.advanceTimersByTime(999);
    expect(service.visible()).toBe(false);
    vi.advanceTimersByTime(1);
    expect(service.visible()).toBe(true);
    expect(service.label()).toBe('Loading Trades');
    events.next(new ResolveEnd(1, '/trades', '/trades', state));
    expect(service.visible()).toBe(false);
  });

  it('clears delayed progress when navigation is cancelled', () => {
    vi.useFakeTimers();
    const events = new Subject<unknown>();
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { events } }] });
    const service = TestBed.inject(RouteLoadingService);
    const state = routeState('Risk');
    events.next(new ResolveStart(1, '/risk', '/risk', state));
    vi.advanceTimersByTime(1000);
    events.next(new NavigationCancel(1, '/risk', 'superseded'));
    expect(service.pending()).toBe(false);
    expect(service.visible()).toBe(false);
  });
});