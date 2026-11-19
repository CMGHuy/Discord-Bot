import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ChangeDetectionStrategy, Component, provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { GuideIndex } from '../../api/models';
import { RouteTitleService } from '../../routing/route-title.service';
import { GuideStore } from '../../stores/guide.store';
import { GUIDE_NOTICE, Guide } from './guide';
import { GUIDE_FIGURES } from './guide-figures';
import { guideRoutes } from './guide.routes';

const INDEX: GuideIndex = { chapters: [
  { slug: 'what-it-is', title: 'What the bot is (and isn’t)', order: 1, reviewed_for: '2.19.2',
    headings: [{ level: 2, text: 'Swing horizons', anchor: 'swing-horizons' }, { level: 3, text: 'Masked', anchor: 'masked' }] },
  { slug: 'glossary', title: 'Glossary', order: 12, reviewed_for: '2.19.1',
    headings: [{ level: 3, text: 'R multiple', anchor: 'r-multiple' }] },
] };

const BODY = [
  '> **In plain words** paper trades only.', '', '## Swing horizons', '', 'See the [glossary](/insights/guide/glossary#r-multiple).',
  '', '<!-- figure:test-figure -->', '', '### Masked', '',
  '<details><summary>Under the hood</summary>', '', '`strategy_types.py`', '', '</details>',
].join('\n');

@Component({ selector: 'sb-test-figure', changeDetection: ChangeDetectionStrategy.OnPush, template: '<p class="test-figure">figure</p>' })
class TestFigure {}

async function openGuide(slug: string | undefined, opts: { fragment?: string | null; status?: number } = {}) {
  TestBed.resetTestingModule();
  const fragment = new BehaviorSubject<string | null>(opts.fragment ?? null);
  TestBed.configureTestingModule({ providers: [
    provideZonelessChangeDetection(), provideRouter([]),
    provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
    provideHttpClientTesting(), GuideStore,
    { provide: ActivatedRoute, useValue: { fragment } },
  ] });
  const http = TestBed.inject(HttpTestingController);
  const fixture: ComponentFixture<Guide> = TestBed.createComponent(Guide);
  if (slug !== undefined) fixture.componentRef.setInput('slug', slug);
  const loaded = TestBed.inject(GuideStore).ensureLoaded();
  http.expectOne('/api/v1/guide').flush(INDEX);
  await loaded;
  await settle(fixture);
  const want = slug ?? 'what-it-is';
  const request = http.expectOne(`/api/v1/guide/${want}`);
  if (opts.status) request.flush({ error: { code: 'not_found', message: 'none' } }, { status: opts.status, statusText: 'x' });
  else request.flush({ slug: want, title: 'T', reviewed_for: '2.19.2', markdown: BODY });
  await settle(fixture);
  return { fixture, el: fixture.nativeElement as HTMLElement, http, fragment };
}

async function settle(fixture: ComponentFixture<unknown>): Promise<void> {
  fixture.detectChanges();
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('Guide page: one chapter', () => {
  GUIDE_FIGURES['test-figure'] = TestFigure;
  afterEach(() => vi.restoreAllMocks());

  it('heads the page with the chapter, stamps its review and ends with the notice', async () => {
    const { el } = await openGuide('what-it-is');
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('What the bot is (and isn’t)');
    expect(el.querySelector('.guide-stamp')!.textContent!.trim()).toBe('Reviewed for bot v2.19.2');
    expect(el.querySelector('.guide-notice')!.textContent!.trim()).toBe(GUIDE_NOTICE);
  });

  it('opens the first chapter when the URL names none', async () => {
    const { el } = await openGuide(undefined);
    expect(el.querySelector('h1')!.textContent!.trim()).toBe('What the bot is (and isn’t)');
  });

  it('renders Markdown through the sanitiser with details intact', async () => {
    const { el } = await openGuide('what-it-is');
    expect(el.querySelector('.md blockquote')).not.toBeNull();
    expect(el.querySelector('.md details > summary')!.textContent).toBe('Under the hood');
  });

  it('places a registered figure between the prose segments', async () => {
    const { el } = await openGuide('what-it-is');
    expect(el.querySelectorAll('.md')).toHaveLength(2);
    expect(el.querySelector('.test-figure')).not.toBeNull();
  });

  it('gives every heading its server anchor and a permalink', async () => {
    const { el } = await openGuide('what-it-is');
    expect([...el.querySelectorAll('.md > h2, .md > h3')].map((h) => h.id)).toEqual(['swing-horizons', 'masked']);
    expect(el.querySelector('#masked a.permalink')!.getAttribute('href')).toBe('/insights/guide/what-it-is#masked');
  });

  it('scrolls a deep link to its heading', async () => {
    const spy = vi.fn();
    Element.prototype.scrollIntoView = spy;
    await openGuide('what-it-is', { fragment: 'masked' });
    expect(spy).toHaveBeenCalledTimes(1);
    expect((spy.mock.contexts[0] as HTMLElement).id).toBe('masked');
  });

  it('routes an in-guide link through the router', async () => {
    const { el } = await openGuide('what-it-is');
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    el.querySelector<HTMLAnchorElement>('.md p a[href^="/insights"]')!.click();
    expect(navigate).toHaveBeenCalledWith('/insights/guide/glossary#r-multiple');
  });

  it('names the chapter in the breadcrumb on a chapter URL', async () => {
    await openGuide('glossary');
    expect(TestBed.inject(RouteTitleService).detail()).toBe('Glossary');
  });

  it('says so when the chapter does not exist', async () => {
    const { el } = await openGuide('nope', { status: 404 });
    expect(el.textContent).toContain('No guide chapter called “nope”');
  });
});

describe('guideRoutes', () => {
  it('scopes GuideStore and the resolver to one parent with two children', () => {
    const [parent] = guideRoutes;
    expect(parent.providers).toContain(GuideStore);
    expect(parent.runGuardsAndResolvers).toBe('always');
    expect(parent.resolve?.['ready']).toBeTypeOf('function');
    expect(parent.children?.map((c) => c.path)).toEqual(['', ':slug']);
  });

  it('loads the Guide component for both children', async () => {
    for (const child of guideRoutes[0].children ?? []) expect(await child.loadComponent!()).toBe(Guide);
  });
});
