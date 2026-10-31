import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, TitleStrategy, provideRouter } from '@angular/router';
import { describe, expect, it, beforeEach } from 'vitest';

import { RouteTitleService, SubtitleTitleStrategy } from './route-title.service';

class Blank {}

describe('route title service', () => {
  let router: Router;
  let titles: RouteTitleService;

  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([
          { path: 'dashboard', component: Blank, title: 'Dashboard',
            data: { subtitle: "What's happening right now" } },
          { path: 'versions', component: Blank, title: 'Versions',
            data: { subtitle: "What's deployed, and when it changed" } },
          { path: 'bare', component: Blank, title: 'Bare' },
          { path: 'trades/:id', component: Blank, title: 'Trade detail',
            data: { subtitle: 'One position, end to end' } },
        ]),
        { provide: TitleStrategy, useClass: SubtitleTitleStrategy },
      ],
    });
    router = TestBed.inject(Router);
    titles = TestBed.inject(RouteTitleService);
  });

  it('publishes the active route title and subtitle', async () => {
    await router.navigateByUrl('/dashboard');
    expect(titles.title()).toBe('Dashboard');
    expect(titles.subtitle()).toBe("What's happening right now");
  });

  it('updates both on navigation', async () => {
    await router.navigateByUrl('/dashboard');
    await router.navigateByUrl('/versions');
    expect(titles.title()).toBe('Versions');
    expect(titles.subtitle()).toBe("What's deployed, and when it changed");
  });

  it('clears the subtitle on a route that has none, rather than keeping the last', async () => {
    await router.navigateByUrl('/dashboard');
    await router.navigateByUrl('/bare');
    expect(titles.title()).toBe('Bare');
    expect(titles.subtitle()).toBeNull();
  });

  describe('the breadcrumb detail segment (v195 Phase 3)', () => {
    it('starts empty', async () => {
      await router.navigateByUrl('/trades/812');
      expect(titles.detail()).toBeNull();
    });

    it('publishes what a detail route sets, and stores an empty string as none', async () => {
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      expect(titles.detail()).toBe('NVDA #812');
      titles.setDetail('');
      expect(titles.detail()).toBeNull();
    });

    it('clears it on a move to another page', async () => {
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      await router.navigateByUrl('/dashboard');
      expect(titles.detail()).toBeNull();
    });

    it('clears it on a move to another record of the same route', async () => {
      // /trades/812 -> /trades/813: the old ticker must not label the new trade
      // while its data loads.
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      await router.navigateByUrl('/trades/813');
      expect(titles.detail()).toBeNull();
    });

    it('keeps it across a query-only navigation on the same page', async () => {
      // A tab switch (?tab=...) re-runs the title strategy; the page, and so
      // its detail, did not change.
      await router.navigateByUrl('/trades/812');
      titles.setDetail('NVDA #812');
      await router.navigateByUrl('/trades/812?tab=plan');
      expect(titles.title()).toBe('Trade detail');
      expect(titles.detail()).toBe('NVDA #812');
    });

    it('clears it on a direct set() that names no path', () => {
      titles.setDetail('NVDA #812');
      titles.set('Somewhere', null);
      expect(titles.detail()).toBeNull();
    });
  });
});
