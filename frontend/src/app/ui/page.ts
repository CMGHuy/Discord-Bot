import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';

import { RouteTitleService } from '../routing/route-title.service';

/**
 * The page template every workspace route renders -- v195 Phase 4.
 *
 * Five slots, in this order, each optional:
 *
 * 1. Header: the page's one `<h1>` and a one-line description on the left,
 *    `[page-actions]` on the right. The actions slot is the only home for a
 *    destructive control (killswitch, restart, stop, clear, discard, delete),
 *    and each opens `sb-confirm-dialog`: the killswitch as `danger`,
 *    everything else as `danger-quiet`.
 * 2. `[page-scope]`: filters and scope only (horizon, side, dates, tabs).
 * 3. `[page-kpis]`: the headline figures, one KPI strip.
 * 4. `[page-primary]`: the main table or chart, full width.
 * 5. `[page-secondary]`: the rest, two columns from lg (1440px), one below.
 *
 * Anything without a slot attribute (a confirm dialog, a drawer) is
 * projected last. An empty slot is `:empty` and hidden, so it takes no space
 * and adds no gap. Give a slot one element carrying its attribute; put a
 * conditional inside that element rather than the attribute inside an
 * `@if`.
 *
 * The `<h1>` is the page's only heading of that rank (correction 9): the
 * shell renders none, and `route-focus.ts` moves focus to `.workspace h1`
 * after each navigation, which is this one. Its words default to the
 * route's `title` and `data.subtitle`, the strings the breadcrumb and
 * `document.title` already use; `heading` / `description` override them.
 *
 * No surface of its own: panels inside it carry the surface and border.
 */
@Component({
  selector: 'sb-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="bar">
      <div class="heading">
        <h1 class="title">{{ headingText() }}</h1>
        @if (descriptionText(); as text) {
          <p class="description">{{ text }}</p>
        }
      </div>
      <div class="actions slot"><ng-content select="[page-actions]" /></div>
    </header>
    <div class="scope slot"><ng-content select="[page-scope]" /></div>
    <div class="kpis slot"><ng-content select="[page-kpis]" /></div>
    <div class="primary slot"><ng-content select="[page-primary]" /></div>
    <div class="secondary slot"><ng-content select="[page-secondary]" /></div>
    <ng-content />
  `,
  styles: `
    :host { display: flex; flex-direction: column; gap: var(--space-14); min-width: 0; }
    .slot:empty { display: none; }
    .bar {
      display: flex;
      flex-wrap: wrap;
      align-items: flex-start;
      justify-content: space-between;
      gap: var(--space-10) var(--space-14);
    }
    .heading { flex: 1 1 280px; min-width: 0; }
    .title { margin: 0; color: var(--text); font-size: var(--text-title); font-weight: 600; line-height: 1.25; }
    .description { margin: var(--space-4) 0 0; max-width: min(65ch, 100%); color: var(--text-muted); font-size: var(--text-body); }
    .actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: var(--space-8); }
    .scope, .kpis, .primary { min-width: 0; }
    .secondary { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); }
    @media (min-width: 1440px) {
      .secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  `,
})
export class Page {
  /** Overrides the route title; empty or null falls back to it. */
  readonly heading = input<string | null>(null);
  /** Overrides the route subtitle; null falls back to it. */
  readonly description = input<string | null>(null);

  private readonly titles = inject(RouteTitleService);

  protected readonly headingText = computed(() => this.heading() || this.titles.title());
  protected readonly descriptionText = computed(() => this.description() ?? this.titles.subtitle());
}
