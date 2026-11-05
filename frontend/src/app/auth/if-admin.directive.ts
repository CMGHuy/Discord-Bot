import { Directive, TemplateRef, ViewContainerRef, effect, inject } from '@angular/core';

import { SessionStore } from '../stores/session.store';

/**
 * v207: `<button *ifAdmin>` renders only for an admin session. It hides,
 * never disables, and is presentation only (the server is the boundary).
 * There is no `else` branch: a control with a read-only stand-in uses
 * `@if (session.isAdmin()) { ... } @else { ... }` in its own template.
 */
@Directive({ selector: '[ifAdmin]' })
export class IfAdminDirective {
  constructor() {
    const session = inject(SessionStore);
    const template = inject(TemplateRef<unknown>);
    const container = inject(ViewContainerRef);
    effect(() => {
      if (session.isAdmin()) {
        if (container.length === 0) container.createEmbeddedView(template);
      } else {
        container.clear();
      }
    });
  }
}
