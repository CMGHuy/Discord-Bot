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

describe('crumbsFor (v195 Phase 3)', () => {
  it('is group and page on a workspace, neither a link', () => {
    expect(crumbsFor('/trades', null, 'Trades')).toEqual([
      { label: 'Review', link: null },
      { label: 'Trades', link: null },
    ]);
  });

  it('links the page crumb back to its list when a detail follows it', () => {
    expect(crumbsFor('/trades/812', 'NVDA #812', 'Trade detail')).toEqual([
      { label: 'Review', link: null },
      { label: 'Trades', link: '/trades' },
      { label: 'NVDA #812', link: null },
    ]);
  });

  it('stands the route title in for a detail that has not loaded yet', () => {
    expect(crumbsFor('/plans/5', null, 'Plan detail').map((crumb) => crumb.label))
      .toEqual(['Review', 'Trades', 'Plan detail']);
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

  it('shows group and page on a workspace, the page marked current', async () => {
    await go('/trades');
    expect(labels()).toEqual(['Review', 'Trades']);
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('Trades');
    expect(el().querySelector('a')).toBeNull();
  });

  it('shows the detail segment once the detail route supplies it, linking back to the list', async () => {
    await go('/trades/812');
    expect(labels()).toEqual(['Review', 'Trades', 'Trade detail']);
    titles.setDetail('NVDA #812');
    fixture.detectChanges();
    expect(labels()).toEqual(['Review', 'Trades', 'NVDA #812']);
    const back = el().querySelector('a')!;
    expect(back.textContent!.trim()).toBe('Trades');
    expect(back.getAttribute('href')).toBe('/trades');
    expect(back.classList).toContain('sb-hit');
    expect(el().querySelector('[aria-current="page"]')!.textContent!.trim()).toBe('NVDA #812');
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
