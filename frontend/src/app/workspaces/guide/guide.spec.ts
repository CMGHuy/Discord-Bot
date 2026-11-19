import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ChangeDetectionStrategy, Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, provideRouter } from '@angular/router';
import { BehaviorSubject } from 'rxjs';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { authInterceptor, errorInterceptor, loadingInterceptor } from '../../api/interceptors';
import { GuideIndex } from '../../api/models';
import { RouteTitleService } from '../../routing/route-title.service';
import { GuideStore } from '../../stores/guide.store';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { ViewportService } from '../../ui/breakpoints';
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

type Width = 'phone' | 'tablet' | 'desktop';
const VIEWPORT = { phone: 'xs', tablet: 'sm', desktop: 'lg' } as const;
/** ViewportService pinned to one width: sb-drawer and sb-panel read `viewport()`, the page reads the two flags. */
const fakeViewport = (width: Width) => ({
  viewport: signal(VIEWPORT[width]), isPhone: signal(width === 'phone'), isNarrow: signal(width !== 'desktop'),
});

async function openGuide(slug: string | undefined, opts: { fragment?: string | null; status?: number; width?: Width } = {}) {
  TestBed.resetTestingModule();
  const fragment = new BehaviorSubject<string | null>(opts.fragment ?? null);
  TestBed.configureTestingModule({ providers: [
    provideZonelessChangeDetection(), provideRouter([]),
    provideHttpClient(withInterceptors([authInterceptor, errorInterceptor, loadingInterceptor])),
    provideHttpClientTesting(), GuideStore,
    { provide: ActivatedRoute, useValue: { fragment } },
    { provide: ViewportService, useValue: fakeViewport(opts.width ?? 'desktop') },
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

describe('Guide page: contents at three widths', () => {
  afterEach(() => vi.restoreAllMocks());

  it('desktop: a rail lists every chapter and the open chapter’s headings', async () => {
    const { el } = await openGuide('what-it-is');
    const rail = el.querySelector('nav.guide-rail')!;
    expect([...rail.querySelectorAll('a.toc-chapter')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/what-it-is', '/insights/guide/glossary']);
    expect(rail.querySelector('a[aria-current="page"]')!.textContent!.trim()).toBe('What the bot is (and isn’t)');
    expect([...rail.querySelectorAll('a.toc-heading')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/what-it-is#swing-horizons', '/insights/guide/what-it-is#masked']);
    expect(el.querySelector('button.guide-contents')).toBeNull();
    expect(el.querySelector('sb-select.guide-picker')).toBeNull();
  });

  it('desktop: lists headings only for the open chapter', async () => {
    const { el } = await openGuide('glossary');
    expect([...el.querySelectorAll('nav.guide-rail a.toc-heading')].map((a) => a.getAttribute('href')))
      .toEqual(['/insights/guide/glossary#r-multiple']);
  });

  it('tablet: a Contents button opens the drawer with the same list', async () => {
    installDialogPolyfill();
    const { el, fixture } = await openGuide('what-it-is', { width: 'tablet' });
    expect(el.querySelector('nav.guide-rail')).toBeNull();
    expect(el.querySelector('sb-select.guide-picker')).toBeNull();
    expect(el.querySelectorAll('sb-drawer a.toc-chapter')).toHaveLength(0);
    el.querySelector<HTMLButtonElement>('button.guide-contents')!.click();
    await settle(fixture);
    expect(el.querySelectorAll('sb-drawer a.toc-chapter')).toHaveLength(2);
  });

  it('tablet: following a contents link closes the drawer', async () => {
    installDialogPolyfill();
    const { el, fixture } = await openGuide('what-it-is', { width: 'tablet' });
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    el.querySelector<HTMLButtonElement>('button.guide-contents')!.click();
    await settle(fixture);
    el.querySelectorAll<HTMLAnchorElement>('sb-drawer a.toc-chapter')[1].click();
    await settle(fixture);
    expect(el.querySelectorAll('sb-drawer a.toc-chapter')).toHaveLength(0);
  });

  it('phone: a labelled chapter picker above the article navigates to the chosen chapter', async () => {
    const { el, fixture } = await openGuide('what-it-is', { width: 'phone' });
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    expect(el.querySelector('nav.guide-rail')).toBeNull();
    expect(el.querySelector('button.guide-contents')).toBeNull();
    const select = el.querySelector<HTMLSelectElement>('.guide-bar sb-select.guide-picker select')!;
    expect(select.getAttribute('aria-label')).toBe('Chapter');
    expect(select.value).toBe('what-it-is');
    expect([...select.options].map((o) => o.value)).toEqual(['what-it-is', 'glossary']);
    select.value = 'glossary';
    select.dispatchEvent(new Event('change'));
    await settle(fixture);
    expect(navigate).toHaveBeenCalledWith(['/insights/guide', 'glossary']);
  });
});
