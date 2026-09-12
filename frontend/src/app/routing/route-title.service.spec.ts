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
});
