import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map } from 'rxjs';

import { RouteTitleService } from '../routing/route-title.service';
import { breadcrumbFor, navEntryFor } from './nav';

export interface Crumb {
  label: string;
  /** Set on the page crumb when a detail follows it: the way back to the list. */
  link: string | null;
}

/** '/trades' is 1 deep, '/trades/812' is 2: anything past the workspace is a detail page. */
function depth(url: string): number {
  return url.split(/[?#]/)[0].split('/').filter((part) => part !== '').length;
}

/**
 * The crumbs for a URL -- v195 Phase 3. `Group / Page`, plus the detail
 * segment on a detail route: the one the route supplied, or its title while
 * the record loads ('Trade detail'). Off the nav (the /ui gallery) the route
 * title alone. Pure, so the spec can hold every case without a router.
 */
export function crumbsFor(url: string, detail: string | null, title: string): Crumb[] {
  const shownDetail = detail || (depth(url) > 1 && title ? title : null);
  const labels = breadcrumbFor(url, shownDetail);
  if (labels.length === 0) return title ? [{ label: title, link: null }] : [];
  const listPath = labels.length === 3 ? navEntryFor(url)!.entry.path : null;
  return labels.map((label, index) => ({ label, link: index === 1 ? listPath : null }));
}

/**
 * The top bar's breadcrumb -- v195 Phase 3, spec correction 9. A labelled
 * list, never a heading: the page's single <h1> belongs to sb-page. On a
 * phone only the current crumb shows (the top bar collapses to the page
 * title there).
 */
@Component({
  selector: 'sb-breadcrumb',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    <nav class="crumbs" aria-label="Breadcrumb">
      <ol>
        @for (crumb of crumbs(); track $index; let last = $last) {
          <li [class.current]="last">
            @if (crumb.link) {
              <a class="sb-hit" [routerLink]="crumb.link">{{ crumb.label }}</a>
            } @else {
              <span class="crumb" [attr.aria-current]="last ? 'page' : null">{{ crumb.label }}</span>
            }
            @if (!last) {
              <span class="sep" aria-hidden="true">/</span>
            }
          </li>
        }
      </ol>
    </nav>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    ol {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      min-width: 0;
      margin: 0;
      padding: 0;
      list-style: none;
      font-size: var(--text-table);
    }
    li { display: inline-flex; align-items: center; gap: var(--space-6); min-width: 0; white-space: nowrap; color: var(--text-muted); }
    /* The current page reads as the title: the strongest text in the bar,
       and the one crumb that gives way (ellipsis) when the bar is short. */
    li.current { overflow: hidden; color: var(--text); font-weight: 600; }
    li.current .crumb { overflow: hidden; text-overflow: ellipsis; }
    a { color: inherit; text-decoration: none; border-radius: var(--radius-sm); }
    a:hover { color: var(--text); }
    a:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* A divider, not text (correction 13): the rule colour is right here. */
    .sep { color: var(--text-faint); }
    @media (max-width: 639px) {
      li:not(.current) { display: none; }
    }
  `,
})
export class Breadcrumb {
  private readonly router = inject(Router);
  private readonly titles = inject(RouteTitleService);

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  protected readonly crumbs = computed(() => crumbsFor(this.url(), this.titles.detail(), this.titles.title()));
}
