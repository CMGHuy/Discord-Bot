import { Injectable, computed, signal } from '@angular/core';

/**
 * The four breakpoints — spec v18 Decision 9.
 *
 * Each value is a FLOOR: 1024 is the first width that is `md`. That is
 * `min-width` semantics, and reading them as ceilings instead shifts every
 * range by one pixel — a defect nobody sees until they resize to exactly a
 * boundary and a layout picks the wrong branch.
 *
 * Not CSS custom properties, for the reason SR2 records: `@media` cannot
 * evaluate `var()`, so a token would have to be duplicated as a literal in
 * every query and the two would drift. The literals live here and in the
 * stylesheet, and the test below is what keeps them honest.
 */
export const BREAKPOINTS = { sm: 640, md: 1024, lg: 1440, xl: 1920 } as const;

export type Viewport = 'xs' | keyof typeof BREAKPOINTS;

/** Pure, so the boundary arithmetic can be tested without a browser. */
export function viewportFor(width: number): Viewport {
  if (width >= BREAKPOINTS.xl) return 'xl';
  if (width >= BREAKPOINTS.lg) return 'lg';
  if (width >= BREAKPOINTS.md) return 'md';
  if (width >= BREAKPOINTS.sm) return 'sm';
  return 'xs';
}

/**
 * The current viewport, as a signal.
 *
 * Driven by one `matchMedia` listener per breakpoint rather than a `resize`
 * handler. A resize handler fires continuously through a drag — dozens of
 * times a second, each one a change-detection pass — where these fire once,
 * when a boundary is actually crossed, which is the only moment anything
 * downstream cares about.
 */
@Injectable({ providedIn: 'root' })
export class ViewportService {
  private readonly width = signal(
    typeof window === 'undefined' ? BREAKPOINTS.lg : window.innerWidth,
  );

  readonly viewport = computed<Viewport>(() => viewportFor(this.width()));

  /** True below `sm` — where the sidebar becomes an overlay. */
  readonly isPhone = computed(() => this.viewport() === 'xs');
  /** True below `md` — where the sidebar is forced to its rail. */
  readonly isNarrow = computed(() => ['xs', 'sm'].includes(this.viewport()));

  constructor() {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    for (const value of Object.values(BREAKPOINTS)) {
      const query = window.matchMedia(`(min-width: ${value}px)`);
      // `change` only — reading innerWidth at the moment of the crossing is
      // what keeps this a single source of truth rather than two.
      query.addEventListener('change', () => this.width.set(window.innerWidth));
    }
  }
}
