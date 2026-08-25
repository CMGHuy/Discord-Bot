import { DOCUMENT } from '@angular/common';
import {
  EnvironmentProviders,
  Injector,
  afterNextRender,
  inject,
  makeEnvironmentProviders,
  provideEnvironmentInitializer,
} from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

/**
 * Move focus to the new workspace's heading after a route change.
 *
 * In an SPA nothing moves focus on navigation: it stays on the nav link that
 * was just activated, so a screen-reader user is told nothing about the page
 * that replaced the one they were on, and a keyboard user's next Tab
 * continues through the sidebar rather than into the content.
 *
 * `tabindex="-1"` makes the heading focusable programmatically WITHOUT
 * putting it in the tab order — a heading that became a tab stop would be a
 * new obstacle on every page.
 */
export function focusWorkspaceHeading(doc: Document): void {
  const heading = doc.querySelector<HTMLElement>('.workspace h1');
  if (!heading) return;
  heading.setAttribute('tabindex', '-1');
  heading.focus({ preventScroll: true });
}

/**
 * Wires `focusWorkspaceHeading` to every route change.
 *
 * The heading does not exist yet at `NavigationEnd` itself -- the new
 * workspace has not rendered. `afterNextRender` waits for that render before
 * looking for it, one call at a time via an explicit `injector` since the
 * router event arrives outside any component's injection context.
 */
export function provideRouteFocus(): EnvironmentProviders {
  return makeEnvironmentProviders([
    provideEnvironmentInitializer(() => {
      const router = inject(Router);
      const doc = inject(DOCUMENT);
      const injector = inject(Injector);
      router.events
        .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
        .subscribe(() => {
          afterNextRender(() => focusWorkspaceHeading(doc), { injector });
        });
    }),
  ]);
}
