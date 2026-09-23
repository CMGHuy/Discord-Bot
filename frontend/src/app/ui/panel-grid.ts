import { ChangeDetectionStrategy, Component, ElementRef, computed, effect, inject, input } from '@angular/core';

import { Viewport, ViewportService } from './breakpoints';

export type PanelTrack = 'narrow' | 'wide';
@Component({ selector: 'sb-panel-grid', changeDetection: ChangeDetectionStrategy.OnPush, host: { '[class]': 'track()' }, template: `<ng-content />`, styles: `:host { display: grid; gap: var(--space-14); grid-template-columns: repeat(auto-fill, minmax(min(220px, 100%), 1fr)); } :host(.wide) { grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); } @media (max-width: 639px) { :host, :host(.wide) { grid-template-columns: minmax(0, 1fr); } }` })
export class PanelGrid {
  readonly track = input<PanelTrack>('narrow');

  /** Panel ids, in the order they should appear, per viewport — v95 §4.3.
   *  A band with no entry keeps declaration order. */
  readonly order = input<Partial<Record<Viewport, string[]>> | null>(null);
  /** Test override — jsdom resolves no media query. */
  readonly viewportAt = input<Viewport | null>(null);

  private readonly viewportService = inject(ViewportService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  constructor() {
    /* CSS `order` rather than moving nodes: reordering the DOM would reset
     * scroll position and drop focus every time the viewport crossed a
     * breakpoint, and a panel mid-interaction would jump under the user.
     *
     * Read off the host's own children rather than contentChildren: the
     * panels are projected as plain elements carrying data-panel-id, with no
     * directive or template reference to query them by. */
    effect(() => {
      const declared = this.order()?.[this.viewport()] ?? null;
      const panels = this.host.nativeElement.querySelectorAll<HTMLElement>('[data-panel-id]');
      for (const element of panels) {
        const id = element.dataset['panelId'];
        if (!declared || !id) { element.style.order = ''; continue; }
        const index = declared.indexOf(id);
        // Unnamed panels sort after named ones, in declaration order, rather
        // than vanishing to the front on -1.
        element.style.order = String(index === -1 ? declared.length : index);
      }
    });
  }
}
