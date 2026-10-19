import { Component, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter, withRouterConfig } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { BACKGROUND_REFRESH_INFO } from '../../routing/route-loading.service';
import { RouteEntryService, pathOf } from './route-entry.service';

@Component({ template: '' })
class Blank {}

describe('pathOf', () => {
  it('drops the query string and the fragment', () => {
    expect(pathOf('/trades?tab=open')).toBe('/trades');
    expect(pathOf('/trades#top')).toBe('/trades');
    expect(pathOf('/trades/42?x=1#y')).toBe('/trades/42');
  });

  it('reads an empty URL as the root path', () => {
    expect(pathOf('')).toBe('/');
  });
});

describe('RouteEntryService (spec v168 §3)', () => {
  let router: Router;
  let entry: RouteEntryService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter(
          [
            { path: 'a', component: Blank },
            { path: 'b', component: Blank },
            { path: 'old', redirectTo: 'b' },
          ],
          withRouterConfig({ onSameUrlNavigation: 'reload' }),
        ),
      ],
    });
    router = TestBed.inject(Router);
    entry = TestBed.inject(RouteEntryService);
  });

  it('starts at 0 and moves on the first navigation', async () => {
    expect(entry.activation()).toBe(0);
    await router.navigateByUrl('/a');
    expect(entry.activation()).toBe(1);
  });

  it('moves on a path change', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/b');
    expect(entry.activation()).toBe(2);
  });

  it('does not move on a same-URL reload', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload' });
    expect(entry.activation()).toBe(1);
  });

  it('does not move on a query-only or a fragment-only change', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a?tab=open');
    await router.navigateByUrl('/a#top');
    expect(entry.activation()).toBe(1);
  });

  it('does not move on a background refresh', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a', {
      onSameUrlNavigation: 'reload',
      replaceUrl: true,
      info: BACKGROUND_REFRESH_INFO,
    });
    expect(entry.activation()).toBe(1);
  });

  it('compares the path after redirects', async () => {
    await router.navigateByUrl('/b');
    await router.navigateByUrl('/old');
    expect(entry.activation()).toBe(1);
  });

  it('a navigation after a background refresh is judged on its own info', async () => {
    await router.navigateByUrl('/a');
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload', info: BACKGROUND_REFRESH_INFO });
    await router.navigateByUrl('/b');
    expect(entry.activation()).toBe(2);
  });

  it('claim() is true once per key per activation', async () => {
    await router.navigateByUrl('/a');
    expect(entry.claim('figure:Expectancy')).toBe(true);
    expect(entry.claim('figure:Expectancy')).toBe(false);
    expect(entry.claim('figure:Win rate')).toBe(true);
  });

  it('a background refresh keeps spent claims spent', async () => {
    await router.navigateByUrl('/a');
    entry.claim('route');
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload', info: BACKGROUND_REFRESH_INFO });
    expect(entry.claim('route')).toBe(false);
  });

  it('a path change frees every claim again', async () => {
    await router.navigateByUrl('/a');
    entry.claim('route');
    await router.navigateByUrl('/b');
    expect(entry.claim('route')).toBe(true);
  });
});

describe('RouteEntryService created after the first navigation', () => {
  it('takes the current path as committed, so the same path does not count as new', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([{ path: 'a', component: Blank }, { path: 'b', component: Blank }],
          withRouterConfig({ onSameUrlNavigation: 'reload' })),
      ],
    });
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/a');
    const entry = TestBed.inject(RouteEntryService);
    await router.navigateByUrl('/a', { onSameUrlNavigation: 'reload' });
    expect(entry.activation()).toBe(0);
    await router.navigateByUrl('/b');
    expect(entry.activation()).toBe(1);
  });
});
