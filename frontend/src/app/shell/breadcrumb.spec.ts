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
    expect(crumbsFor('/trades', null, 'Trades')).toEqual([
      { label: 'Trades', link: null },
      { label: 'Book', link: null },
    ]);
  });

  it('is the destination alone on a single page', () => {
    expect(crumbsFor('/risk', null, 'Risk')).toEqual([{ label: 'Risk', link: null }]);
  });

  it.each([
    ['/trades/calendar', 'Calendar', ['Trades', 'Calendar']],
    ['/trades/cancels', 'Cancels', ['Trades', 'Cancels']],
    ['/insights/analytics', 'Analytics', ['Insights', 'Analytics']],
    ['/system/versions', 'Versions', ['System', 'Versions']],
    ['/system?tab=logs', 'System', ['System', 'Health']],
  ])('never reads the section of %s as a detail page', (url, title, expected) => {
    expect(crumbsFor(url, null, title)).toEqual(expected.map((label) => ({ label, link: null })));
  });

  it('links the crumb before a detail back to its list', () => {
    expect(crumbsFor('/trades/812', 'NVDA #812', 'Trade detail')).toEqual([
      { label: 'Trades', link: null },
      { label: 'Book', link: '/trades' },
      { label: 'NVDA #812', link: null },
    ]);
    expect(crumbsFor('/watchlist/NVDA', 'NVDA', 'Ticker detail')).toEqual([
      { label: 'Watchlist', link: '/watchlist' },
      { label: 'NVDA', link: null },
    ]);
  });

  it("stands the route title in for a detail that has not loaded yet, below a section's list", () => {
    expect(crumbsFor('/plans/5', null, 'Plan detail').map((crumb) => crumb.label))
      .toEqual(['Trades', 'Book', 'Plan detail']);
    expect(crumbsFor('/trades/calendar/2026-10-01', null, 'Calendar day')).toEqual([
      { label: 'Trades', link: null },
      { label: 'Calendar', link: '/trades/calendar' },
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
          { path: 'trades/calendar', component: Blank, title: 'Calendar' },
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

  it('shows destination and section, the section marked current', async () => {
    await go('/trades');
    expect(labels()).toEqual(['Trades', 'Book']);
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('Book');
    expect(el().querySelector('a')).toBeNull();
  });

  it('shows the detail segment once the detail route supplies it, linking back to the list', async () => {
    await go('/trades/812');
    expect(labels()).toEqual(['Trades', 'Book', 'Trade detail']);
    titles.setDetail('NVDA #812');
    fixture.detectChanges();
    expect(labels()).toEqual(['Trades', 'Book', 'NVDA #812']);
    const back = el().querySelector('a')!;
    expect(back.textContent!.trim()).toBe('Book');
    expect(back.getAttribute('href')).toBe('/trades');
    expect(back.classList).toContain('sb-hit');
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('NVDA #812');
  });

  it('shows a section page as destination and section, with no third crumb', async () => {
    await go('/trades/calendar');
    expect(labels()).toEqual(['Trades', 'Calendar']);
    expect(el().querySelector('a')).toBeNull();
  });

  it('falls back to the route title off the nav', async () => {
    await go('/ui');
    expect(labels()).toEqual(['UI gallery']);
  });

  it('hides its separators from assistive tech', async () => {
    await go('/trades/812');
    const seps = [...el().querySelectorAll('.sep')];
    expect(seps).toHaveLength(2);
    for (const sep of seps) expect(sep.getAttribute('aria-hidden')).toBe('true');
  });

  it('keeps only the current crumb below 640px', () => {
    expect(SOURCE).toMatch(/@media \(max-width: 639px\) \{\s*li:not\(\.current\) \{ display: none; \}/);
  });

  it('draws the separators in the rule colour and the text in the muted one (correction 13)', () => {
    expect(SOURCE).toMatch(/\.sep \{[^}]*color: var\(--text-faint\)/);
    expect(SOURCE).toMatch(/li \{[^}]*color: var\(--text-muted\)/);
  });
});
