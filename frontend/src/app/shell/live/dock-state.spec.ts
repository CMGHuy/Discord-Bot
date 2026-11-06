import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, Routes, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { Preferences } from '../../api/models';
import { PreferencesStore } from '../../stores/preferences.store';
import { ViewportService } from '../../ui/breakpoints';
import { DockState, pathOf } from './dock-state';
import { DOCK_PREF_KEY } from './live-state';

@Component({ template: '' })
class Blank {}

const ROUTES: Routes = [
  ...['dashboard', 'risk', 'trades', 'trades/calendar', 'insights/analytics', 'ui'].map((path) => ({ path, component: Blank })),
  { path: 'calendar', redirectTo: 'trades/calendar' },
];

describe('DockState (v203)', () => {
  const data = signal<Preferences>({});
  const loaded = signal(false);
  const narrow = signal(false);
  const prefs = { values: () => data(), isLoaded: () => loaded(), update: vi.fn((m: (p: Preferences) => Preferences) => data.set(m(data()))) };
  let dock: DockState;
  const go = (url: string) => TestBed.inject(Router).navigateByUrl(url);

  beforeEach(() => {
    data.set({});
    loaded.set(true);
    narrow.set(false);
    prefs.update.mockClear();
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter(ROUTES),
        { provide: PreferencesStore, useValue: prefs },
        { provide: ViewportService, useValue: { isNarrow: narrow, isPhone: signal(false) } },
      ],
    });
    dock = TestBed.inject(DockState);
  });

  it.each([['/trades/calendar', '/trades'], ['/insights/analytics?tab=tuning#x', '/insights'], ['/calendar', '/trades'], ['/ui', null]])(
    'keys %s by destination %s', async (url, destination) => {
      await go(url);
      expect(dock.destination()).toBe(destination);
    });

  it('opens by default on Dashboard and Risk, and is collapsed elsewhere', async () => {
    await go('/dashboard');
    expect(dock.open()).toBe(true);
    await go('/risk');
    expect(dock.open()).toBe(true);
    await go('/trades');
    expect(dock.open()).toBe(false);
  });

  it('uses the default before preferences load, and after a failed read', async () => {
    data.set({ [DOCK_PREF_KEY]: { '/dashboard': false } });
    loaded.set(false);
    await go('/dashboard');
    expect(dock.open()).toBe(true);
    data.set({});                   // a failed read: loaded, empty
    loaded.set(true);
    expect(dock.open()).toBe(true);
  });

  it('remembers a toggle per destination, through PreferencesStore', async () => {
    await go('/trades/calendar');
    dock.toggle();
    expect(dock.open()).toBe(true);
    expect(data()[DOCK_PREF_KEY]).toEqual({ '/trades': true });
    await go('/risk');
    expect(dock.open()).toBe(true);
    dock.toggle();
    expect(dock.open()).toBe(false);
    await go('/calendar');          // an old path keys the same destination
    expect(dock.open()).toBe(true);
    expect(data()[DOCK_PREF_KEY]).toEqual({ '/trades': true, '/risk': false });
  });

  it('writes nothing off the nav model', async () => {
    await go('/ui');
    dock.toggle();
    expect(prefs.update).not.toHaveBeenCalled();
    expect(dock.open()).toBe(false);
  });

  it('docks only at 1024 px and wider', () => {
    expect(dock.docked()).toBe(true);
    narrow.set(true);
    expect(dock.docked()).toBe(false);
  });

  it('reveals by opening a collapsed docked dock, or the sheet below 1024 px', async () => {
    await go('/trades');
    dock.reveal();
    expect(dock.open()).toBe(true);
    dock.reveal();                  // already open: no second write
    expect(prefs.update).toHaveBeenCalledTimes(1);
    expect(dock.sheetOpen()).toBe(false);
    narrow.set(true);
    dock.reveal();
    expect(dock.sheetOpen()).toBe(true);
    expect(prefs.update).toHaveBeenCalledTimes(1);
  });

  it('closes the sheet on navigation, on closeSheet and when the window docks', async () => {
    narrow.set(true);
    await go('/trades');
    dock.openSheet();
    await go('/risk');
    expect(dock.sheetOpen()).toBe(false);
    dock.openSheet();
    dock.closeSheet();
    expect(dock.sheetOpen()).toBe(false);
    dock.openSheet();
    narrow.set(false);
    TestBed.tick();
    expect(dock.sheetOpen()).toBe(false);
  });

  it('keeps the sheet open through a background same-URL refresh', async () => {
    narrow.set(true);
    await go('/insights/analytics?tab=tuning');
    dock.openSheet();
    // RouteRefreshService's background refresh: the same URL, reloaded.
    await TestBed.inject(Router).navigateByUrl('/insights/analytics?tab=tuning', { onSameUrlNavigation: 'reload', replaceUrl: true });
    expect(dock.sheetOpen()).toBe(true);
  });

  it('keeps the sheet open when only query params or the fragment change', async () => {
    narrow.set(true);
    await go('/trades/calendar');
    dock.openSheet();
    await go('/trades/calendar?month=2026-11');
    await go('/trades/calendar?month=2026-11#day');
    expect(dock.sheetOpen()).toBe(true);
    await go('/trades');            // a different page still closes it
    expect(dock.sheetOpen()).toBe(false);
  });

  it.each([['/a?b=1#c', '/a'], ['/a#c', '/a'], ['/a', '/a'], ['', '']])('pathOf(%s) is %s', (url, path) => {
    expect(pathOf(url)).toBe(path);
  });
});
