import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

import { NavEntry, NavSection } from './nav';

/**
 * A destination's sections as a segmented row of links -- v202 §1.
 *
 * The shell draws it at the top of the workspace, above the page's sb-page
 * header, from the nav model; a workspace never does (section-tabs.spec
 * holds that). Each segment is a page, so they are plain links in the tab
 * order with `aria-current="page"` on the active one, not sb-segmented's
 * roving toggle. The look is sb-segmented's, with the same tokens: Phase 1
 * adds no styling of its own. Renders nothing on a single page.
 */
@Component({
  selector: 'sb-section-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (sections().length > 0) {
      <nav class="track" [attr.aria-label]="label()">
        @for (section of sections(); track section.path) {
          <a
            class="segment"
            [routerLink]="section.path"
            [class.current]="section.path === active()?.path"
            [attr.aria-current]="section.path === active()?.path ? 'page' : null"
          >{{ section.label }}</a>
        }
      </nav>
    }
  `,
  styles: `
    :host { display: block; min-width: 0; max-width: 100%; }
    .track { display: inline-flex; max-width: 100%; margin: 0 0 var(--space-14); overflow-x: auto; scrollbar-width: thin; border: 1px solid var(--border-strong); border-radius: var(--control-radius); }
    .segment { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; min-height: var(--control-h); min-width: var(--hit-min); padding: 0 var(--space-10); border-left: 1px solid var(--border); color: var(--text-secondary); font-size: var(--text-table); font-weight: 500; white-space: nowrap; text-decoration: none; transition: color var(--transition), background var(--transition); }
    .segment:first-child { border-left: 0; }
    .segment:not(.current):hover { color: var(--text); background: var(--surface-raised); }
    .segment:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .current { background: var(--accent-soft); color: var(--text); }
  `,
})
export class SectionTabs {
  readonly entry = input<NavEntry | null>(null);
  readonly active = input<NavSection | null>(null);

  protected readonly sections = computed(() => this.entry()?.sections ?? []);
  protected readonly label = computed(() => `${this.entry()?.label ?? ''} sections`);
}
