import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, TitleStrategy, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { RouteTitleService, SubtitleTitleStrategy } from '../routing/route-title.service';
import { Breadcrumb, crumbsFor } from './breadcrumb';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/shell/breadcrumb.ts'), 'utf8');

class Blank {}

describe('crumbsFor (v202: Destination / Section)', () => {
  it('is destination and section on a sectioned page, neither a link', () => {
    expect(crumbsFor('/insights/research', null, 'Research')).toEqual([
      { label: 'Insights', link: null },
      { label: 'Research', link: null },
    ]);
  });

  it('is the destination alone on a single page, Trades and Calendar included (v247)', () => {
    expect(crumbsFor('/risk', null, 'Risk')).toEqual([{ label: 'Risk', link: null }]);
    expect(crumbsFor('/trades', null, 'Trades')).toEqual([{ label: 'Trades', link: null }]);
    expect(crumbsFor('/calendar?month=2026-11', null, 'Calendar')).toEqual([{ label: 'Calendar', link: null }]);
  });

  it.each([
    ['/insights/reports', 'Reports', ['Insights', 'Reports']],
    ['/insights/analytics', 'Analytics', ['Insights', 'Analytics']],
    ['/insights/guide', 'Guide', ['Insights', 'Guide']],
    ['/system/versions', 'Versions', ['System', 'Versions']],
    ['/system?tab=logs', 'System', ['System', 'Health']],
  ])('never reads the section of %s as a detail page', (url, title, expected) => {
    expect(crumbsFor(url, null, title)).toEqual(expected.map((label) => ({ label, link: null })));
  });

  it('links the crumb before a detail back to its list', () => {
    expect(crumbsFor('/trades/812', 'NVDA #812', 'Trade detail')).toEqual([
      { label: 'Trades', link: '/trades' },
      { label: 'NVDA #812', link: null },
    ]);
    expect(crumbsFor('/watchlist/NVDA', 'NVDA', 'Ticker detail')).toEqual([
      { label: 'Watchlist', link: '/watchlist' },
      { label: 'NVDA', link: null },
    ]);
  });

  it('reads a guide chapter as a detail of the Guide section, linking back to it (v236)', () => {
    expect(crumbsFor('/insights/guide/glossary', 'Glossary', 'Guide')).toEqual([
      { label: 'Insights', link: null },
      { label: 'Guide', link: '/insights/guide' },
      { label: 'Glossary', link: null },
    ]);
  });

  it('stands the route title in for a detail that has not loaded yet', () => {
    expect(crumbsFor('/plans/5', null, 'Plan detail').map((crumb) => crumb.label))
      .toEqual(['Trades', 'Plan detail']);
    expect(crumbsFor('/calendar/2026-10-01', null, 'Calendar day')).toEqual([
      { label: 'Calendar', link: '/calendar' },
      { label: 'Calendar day', link: null },
    ]);
  });

  it('is the route title alone off the nav', () => {
    expect(crumbsFor('/ui', null, 'UI gallery')).toEqual([{ label: 'UI gallery', link: null }]);
  });

  it('is empty before any route has a title', () => {
    expect(crumbsFor('/', null, '')).toEqual([]);
  });
});

describe('Breadcrumb (sb-breadcrumb)', () => {
  let fixture: ComponentFixture<Breadcrumb>;
  let router: Router;
  let titles: RouteTitleService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideRouter([
          { path: 'trades', component: Blank, title: 'Trades' },
          { path: 'calendar', component: Blank, title: 'Calendar' },
          { path: 'trades/:id', component: Blank, title: 'Trade detail' },
          { path: 'ui', component: Blank, title: 'UI gallery' },
        ]),
        { provide: TitleStrategy, useClass: SubtitleTitleStrategy },
      ],
    });
    router = TestBed.inject(Router);
    titles = TestBed.inject(RouteTitleService);
    fixture = TestBed.createComponent(Breadcrumb);
    fixture.detectChanges();
  });

  const el = () => fixture.nativeElement as HTMLElement;
  const go = async (url: string) => {
    await router.navigateByUrl(url);
    fixture.detectChanges();
    await fixture.whenStable();
  };
  const labels = () => [...el().querySelectorAll('li')]
    .map((li) => li.querySelector('a, span:not(.sep)')!.textContent!.trim());

  it('is a labelled nav list, never a heading', async () => {
    await go('/trades');
    expect(el().querySelector('nav[aria-label="Breadcrumb"] > ol')).not.toBeNull();
    expect(el().querySelector('h1, h2, h3, h4, h5, h6')).toBeNull();
  });

  it('shows a single page as one crumb, marked current', async () => {
    await go('/trades');
    expect(labels()).toEqual(['Trades']);
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('Trades');
    expect(el().querySelector('a')).toBeNull();
  });

  it('shows the detail segment once the detail route supplies it, linking back to the list', async () => {
    await go('/trades/812');
    expect(labels()).toEqual(['Trades', 'Trade detail']);
    titles.setDetail('NVDA #812');
    fixture.detectChanges();
    expect(labels()).toEqual(['Trades', 'NVDA #812']);
    const back = el().querySelector('a')!;
    expect(back.textContent!.trim()).toBe('Trades');
    expect(back.getAttribute('href')).toBe('/trades');
    expect(back.classList).toContain('sb-hit');
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('NVDA #812');
  });

  it('shows Calendar as a destination of its own (v247)', async () => {
    await go('/calendar');
    expect(labels()).toEqual(['Calendar']);
    expect(el().querySelector('a')).toBeNull();
  });

  it('falls back to the route title off the nav', async () => {
    await go('/ui');
    expect(labels()).toEqual(['UI gallery']);
  });

  it('hides its separators from assistive tech', async () => {
    await go('/trades/812');
    const seps = [...el().querySelectorAll('.sep')];
    expect(seps).toHaveLength(1);
    for (const sep of seps) expect(sep.getAttribute('aria-hidden')).toBe('true');
  });

  it('keeps only the current crumb below 1024px (v203: moved from 640px)', () => {
    expect(SOURCE).toMatch(/@media \(max-width: 1023px\) \{\s*li:not\(\.current\) \{ display: none; \}/);
  });

  it('draws the separators and the crumbs in the muted colour (v240: --text-faint is never text)', () => {
    expect(SOURCE).toMatch(/\.sep \{[^}]*color: var\(--text-muted\)/);
    expect(SOURCE).toMatch(/li \{[^}]*color: var\(--text-muted\)/);
    expect(SOURCE).not.toContain('--text-faint');
  });
});
