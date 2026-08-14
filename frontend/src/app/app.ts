import {
  ChangeDetectionStrategy,
  Component,
  effect,
  inject,
  untracked,
} from '@angular/core';
import { Router } from '@angular/router';

import { Login } from './shell/login/login';
import { Shell } from './shell/shell';
import { SessionStore } from './stores/session.store';

/**
 * The auth gate, and nothing else.
 *
 * One of two things renders: the login form, or the application. Never both
 * and never neither -- and never the application "optimistically" while the
 * session check is outstanding, which is what would produce a frame of empty
 * dashboard before the login form appears.
 *
 * In practice the `unknown` branch is unreachable: an app initializer awaits
 * `boot()` before Angular bootstraps this component, so the status is
 * already settled by the time anything renders. It is written out anyway
 * because "unreachable" here depends on a provider in a different file, and
 * the failure mode if that provider is ever dropped should be a blank frame
 * rather than a flash of the real UI.
 */
@Component({
  selector: 'sb-root',
  imports: [Shell, Login],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (session.isAuthenticated()) {
      <sb-shell />
    } @else if (session.isResolving()) {
      <!-- deliberately empty -->
    } @else {
      <sb-login />
    }
  `,
})
export class App {
  protected readonly session = inject(SessionStore);

  private readonly router = inject(Router);

  constructor() {
    /**
     * SR58 — return to the deep link once authenticated.
     *
     * Here rather than in the login form: a session can also become
     * authenticated without anyone typing a password (an existing cookie,
     * or a session established through the Jinja UI), and the visitor
     * should land where they asked either way.
     *
     * The effect runs on every status change but the redirect is consumed,
     * so it fires at most once per page load.
     */
    effect(() => {
      if (!this.session.isAuthenticated()) return;
      const target = untracked(() => this.session.takeRedirect());
      if (target) void this.router.navigateByUrl(target);
    });
  }
}
