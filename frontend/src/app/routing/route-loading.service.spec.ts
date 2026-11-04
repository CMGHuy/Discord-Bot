import { Component, provideZonelessChangeDetection } from '@angular/core';
import { NavigationCancel, Router, RouterStateSnapshot, ResolveEnd, ResolveStart, provideRouter } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { NEVER, Subject, of } from 'rxjs';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PreferencesStore } from '../stores/preferences.store';
import { SessionStore } from '../stores/session.store';
import { onEvents, routeData } from './route-metadata';
import { BACKGROUND_REFRESH_INFO, ROUTE_LOADING_DELAY_MS, RouteLoadingService } from './route-loading.service';
import { startRoute } from './route-resolver';

@Component({ template: '' })
class StubPage {}

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

  it('never veils the page for a live background refresh, but still reports it pending', () => {
    vi.useFakeTimers();
    const events = new Subject<unknown>();
    const currentNavigation = () => ({ extras: { info: BACKGROUND_REFRESH_INFO } });
    TestBed.configureTestingModule({ providers: [{ provide: Router, useValue: { events, currentNavigation } }] });
    const service = TestBed.inject(RouteLoadingService);
    const state = routeState('Risk');
    events.next(new ResolveStart(1, '/risk', '/risk', state));
    vi.advanceTimersByTime(5000);
    expect(service.pending()).toBe(true);
    expect(service.visible()).toBe(false);
    events.next(new ResolveEnd(1, '/risk', '/risk', state));
    expect(service.pending()).toBe(false);
  });

  it('never shows the veil for a route whose data is still loading', async () => {
    vi.useFakeTimers();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{
          path: 'x',
          data: routeData('X', onEvents()),
          resolve: { ready: startRoute(() => NEVER) },
          component: StubPage,
        }]),
        { provide: PreferencesStore, useValue: { resolve: () => of(undefined) } },
        { provide: SessionStore, useValue: { expire: vi.fn() } },
      ],
    });
    const service = TestBed.inject(RouteLoadingService);
    const navigation = TestBed.inject(Router).navigateByUrl('/x');
    await vi.advanceTimersByTimeAsync(ROUTE_LOADING_DELAY_MS + 500);
    await navigation;
    expect(service.visible()).toBe(false);
    expect(service.pending()).toBe(false);
  });
});
