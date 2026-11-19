import { NgComponentOutlet, NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy, Component, ElementRef, Type, ViewEncapsulation,
  afterRenderEffect, computed, effect, inject, input, signal, untracked, viewChild,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { RouteTitleService } from '../../routing/route-title.service';
import { GuideStore } from '../../stores/guide.store';
import { Async } from '../../ui/async';
import { ViewportService } from '../../ui/breakpoints';
import { Button } from '../../ui/button';
import { Select, SelectOption } from '../../ui/form-controls';
import { Drawer, Panel } from '../../ui/layout';
import { Page } from '../../ui/page';
import { GUIDE_FIGURES } from './guide-figures';
import { applyHeadingAnchors, internalGuideUrl, renderGuideSegments, scrollToAnchor } from './guide-markdown';

/** The one-line notice on every guide page (spec v215 § Risks). */
export const GUIDE_NOTICE = 'Education about a paper-trading tool, not advice: alerts are not tailored to you, '
  + 'a suggested size is a default, and past results do not predict future ones.';

/**
 * Insights → Guide (spec v215): one chapter at a time, rendered from the
 * server's resolved Markdown. Chapter HTML is rendered by `marked` and bound
 * with [innerHTML], so Angular's sanitiser runs on it; the prose styles are
 * unencapsulated (ViewEncapsulation.None, every selector under `sb-guide`)
 * because sanitised HTML carries no component attribute.
 */
@Component({
  selector: 'sb-guide',
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  imports: [Async, Button, Drawer, NgComponentOutlet, NgTemplateOutlet, Page, Panel, RouterLink, Select],
  template: `
    <sb-page [heading]="chapter()?.title ?? null">
      <div page-primary class="guide-layout">
        @if (tocMode() === 'picker') {
          <div class="guide-bar">
            <sb-select class="guide-picker" ariaLabel="Chapter" [options]="chapterOptions()"
                       [value]="activeSlug() ?? ''" (valueChange)="goTo($event)" />
          </div>
        } @else if (tocMode() === 'drawer') {
          <div class="guide-bar">
            <button sb-button type="button" class="guide-contents" (click)="drawerOpen.set(true)">Contents</button>
          </div>
          <sb-drawer [open]="drawerOpen()" heading="Contents" (closed)="drawerOpen.set(false)">
            <ng-container *ngTemplateOutlet="contents" />
          </sb-drawer>
        }
        <div class="guide-body">
          @if (tocMode() === 'rail') {
            <nav class="guide-rail" aria-label="Guide contents">
              <ng-container *ngTemplateOutlet="contents" />
            </nav>
          }
          <div class="guide-main">
            <sb-panel class="guide-panel">
              <sb-async [loading]="loading()" [error]="error()" [empty]="empty()" emptyReason="no-data-yet"
                        [emptyTitle]="emptyTitle()" [staleAsOf]="null" shape="panel" (retry)="retry()">
                <article #article class="guide-chapter" (click)="onContentClick($event)">
                  <p class="guide-stamp">Reviewed for bot v{{ chapter()?.reviewed_for }}</p>
                  @for (segment of segments(); track $index) {
                    @if (segment.kind === 'md') {
                      <div class="md" [innerHTML]="segment.html"></div>
                    } @else {
                      <ng-container *ngComponentOutlet="figure(segment.name)" />
                    }
                  }
                </article>
              </sb-async>
            </sb-panel>
            <p class="guide-notice">{{ notice }}</p>
          </div>
        </div>
      </div>
    </sb-page>

    <ng-template #contents>
      <ol class="guide-toc">
        @for (c of store.chapters(); track c.slug) {
          <li>
            <a class="toc-chapter" [routerLink]="['/insights/guide', c.slug]" (click)="picked()"
               [attr.aria-current]="c.slug === activeSlug() ? 'page' : null">{{ c.title }}</a>
            @if (c.slug === activeSlug() && c.headings.length) {
              <ol class="toc-headings">
                @for (h of c.headings; track h.anchor) {
                  <li><a class="toc-heading" [class.sub]="h.level === 3" [routerLink]="['/insights/guide', c.slug]"
                         [fragment]="h.anchor" (click)="picked()">{{ h.text }}</a></li>
                }
              </ol>
            }
          </li>
        }
      </ol>
    </ng-template>
  `,
  styles: `
    sb-guide .guide-layout { display: flex; flex-direction: column; gap: var(--space-14); min-width: 0; }
    sb-guide .guide-chapter { max-width: 72ch; min-width: 0; overflow-wrap: anywhere; }
    sb-guide .guide-stamp, sb-guide .guide-notice { margin: 0; color: var(--text-muted); font-size: var(--text-table); }
    sb-guide .md h2 { margin: var(--space-20) 0 var(--space-8); font-size: var(--text-subhead); scroll-margin-top: var(--space-20); }
    sb-guide .md h3 { margin: var(--space-14) 0 var(--space-6); font-size: var(--text-body); font-weight: 600; scroll-margin-top: var(--space-20); }
    sb-guide .md p, sb-guide .md ul, sb-guide .md ol { margin: var(--space-8) 0; line-height: 1.55; }
    sb-guide .md a { color: var(--accent); }
    sb-guide .md blockquote { margin: var(--space-10) 0; padding: var(--space-8) var(--space-14); border-left: 2px solid var(--accent); background: var(--surface-raised); }
    sb-guide .md table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
    sb-guide .md th, sb-guide .md td { padding: var(--cell-pad-y) var(--cell-pad-x); border-bottom: 1px solid var(--border); text-align: left; }
    sb-guide .md pre { max-width: 100%; overflow-x: auto; padding: var(--space-8); background: var(--bg); font-family: var(--font-mono); }
    sb-guide .md details { margin: var(--space-10) 0; padding: 0 var(--space-10); border: 1px solid var(--border); border-radius: var(--control-radius); }
    sb-guide .md summary { display: flex; align-items: center; gap: var(--space-6); min-height: var(--hit-min); color: var(--text-muted); cursor: pointer; list-style: none; }
    sb-guide .md summary::before { content: '▸'; }
    sb-guide .md details[open] > summary::before { content: '▾'; }
    sb-guide .md .permalink { margin-left: var(--space-6); color: var(--text-faint); text-decoration: none; }
    sb-guide .guide-bar { display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--space-10); min-width: 0; }
    sb-guide .guide-picker { flex: 1 1 100%; min-width: 0; }
    sb-guide .guide-picker .field, sb-guide .guide-picker select { width: 100%; max-width: 100%; }
    sb-guide .guide-body { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); align-items: start; }
    sb-guide .guide-main { display: flex; flex-direction: column; gap: var(--space-14); min-width: 0; }
    @media (min-width: 1024px) {
      sb-guide .guide-body { grid-template-columns: minmax(14rem, 18rem) minmax(0, 1fr); }
      sb-guide .guide-rail { position: sticky; top: var(--space-14); max-height: calc(100dvh - 8rem); overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-10); }
    }
    sb-guide .guide-toc, sb-guide .toc-headings { list-style: none; margin: 0; padding: 0; }
    sb-guide .toc-headings { padding-left: var(--space-10); }
    sb-guide .toc-chapter, sb-guide .toc-heading { display: flex; align-items: center; min-height: var(--hit-min); color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
    sb-guide .toc-heading { color: var(--text-secondary); font-size: var(--text-table); }
    sb-guide .toc-heading.sub { padding-left: var(--space-10); }
    sb-guide .toc-chapter[aria-current='page'] { color: var(--accent); font-weight: 600; }
  `,
})
export class Guide {
  /** The `:slug` route param; absent on `/insights/guide`. */
  readonly slug = input<string>();

  protected readonly store = inject(GuideStore);
  private readonly router = inject(Router);
  private readonly titles = inject(RouteTitleService);
  private readonly fragment = toSignal(inject(ActivatedRoute).fragment, { initialValue: null });
  private readonly article = viewChild<ElementRef<HTMLElement>>('article');
  private scrolledTo: string | null = null;
  protected readonly notice = GUIDE_NOTICE;
  private readonly viewport = inject(ViewportService);
  /** Contents per width: rail ≥ 1024, drawer 640–1023, picker < 640. */
  protected readonly tocMode = computed<'rail' | 'drawer' | 'picker'>(() =>
    this.viewport.isPhone() ? 'picker' : this.viewport.isNarrow() ? 'drawer' : 'rail');
  protected readonly drawerOpen = signal(false);
  protected readonly chapterOptions = computed<SelectOption[]>(() =>
    this.store.chapters().map((c) => ({ value: c.slug, label: c.title })));

  protected readonly activeSlug = computed(() => this.slug() || this.store.firstSlug());
  protected readonly chapter = computed(() =>
    this.store.chapters().find((c) => c.slug === this.activeSlug()) ?? null);
  private readonly bodyStatus = computed(() => {
    const slug = this.activeSlug();
    return slug ? this.store.chapterStatus()[slug] ?? 'loading' : null;
  });
  protected readonly segments = computed(() => {
    const slug = this.activeSlug();
    const body = slug ? this.store.bodies()[slug] : undefined;
    return body ? renderGuideSegments(body.markdown) : [];
  });
  protected readonly loading = computed(() =>
    ['idle', 'loading'].includes(this.store.status()) || this.bodyStatus() === 'loading');
  protected readonly error = computed(() =>
    this.store.error() ?? (this.bodyStatus() === 'error' ? 'This chapter could not be loaded.' : null));
  protected readonly empty = computed(() =>
    this.store.status() === 'ready' && (this.activeSlug() === null || this.bodyStatus() === 'missing'));
  protected readonly emptyTitle = computed(() => this.activeSlug() === null
    ? 'The guide has no chapters yet' : `No guide chapter called “${this.activeSlug()}”`);

  constructor() {
    effect(() => {
      const slug = this.activeSlug();
      if (slug && this.store.status() === 'ready') untracked(() => this.store.loadChapter(slug));
    });
    // The breadcrumb's detail segment (calendar-day.ts pattern): the chapter
    // on a chapter URL, none on the bare /insights/guide.
    effect(() => {
      const crumb = this.slug() ? this.chapter()?.title ?? null : null;
      this.titles.detail();
      untracked(() => this.titles.setDetail(crumb));
    });
    afterRenderEffect(() => {
      const host = this.article()?.nativeElement;
      const chapter = this.chapter();
      this.segments();
      if (!host || !chapter) return;
      applyHeadingAnchors(host, chapter.headings, `/insights/guide/${chapter.slug}`);
      this.scrollToFragment(host, chapter.slug, this.fragment());
    });
  }

  protected figure(name: string): Type<unknown> | null {
    return GUIDE_FIGURES[name] ?? null;
  }

  protected retry(): void {
    void this.store.ensureLoaded();
    const slug = this.activeSlug();
    if (slug) this.store.loadChapter(slug);
  }

  /** The phone picker: open the chosen chapter. */
  protected goTo(slug: string): void {
    if (slug && slug !== this.activeSlug()) void this.router.navigate(['/insights/guide', slug]);
  }

  /** A contents link was followed: close the drawer so the chapter is what
   *  the reader sees next, and let the fragment scroll again. */
  protected picked(): void {
    this.drawerOpen.set(false);
    this.scrolledTo = null;
  }

  /** Chapter links are plain <a href> in sanitised HTML; send the in-app
   *  ones through the router instead of reloading the app. */
  protected onContentClick(event: MouseEvent): void {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const href = (event.target as Element | null)?.closest('a')?.getAttribute('href');
    const url = href ? internalGuideUrl(href, this.activeSlug()) : null;
    if (url === null) return;
    event.preventDefault();
    this.scrolledTo = null;
    void this.router.navigateByUrl(url);
  }

  /** Once per slug#fragment, and only when the heading is rendered: the
   *  body arrives after the router's own anchor scroll would have run. */
  private scrollToFragment(host: HTMLElement, slug: string, fragment: string | null): void {
    const key = fragment ? `${slug}#${fragment}` : null;
    if (key === null || key === this.scrolledTo) return;
    if (scrollToAnchor(host, fragment!)) this.scrolledTo = key;
  }
}
