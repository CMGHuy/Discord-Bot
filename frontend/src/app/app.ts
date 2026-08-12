import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { Login } from './shell/login/login';
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
  imports: [RouterOutlet, Login],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (session.isAuthenticated()) {
      <router-outlet />
    } @else if (session.isResolving()) {
      <!-- deliberately empty -->
    } @else {
      <sb-login />
    }
  `,
})
export class App {
  protected readonly session = inject(SessionStore);
}
