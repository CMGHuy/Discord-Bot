import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { SessionStore } from '../../stores/session.store';

/**
 * The login form, rendered *instead of* the shell.
 *
 * Not a route, deliberately (spec v13 Decision 7). If login were a route,
 * the shell would be the thing hosting it, and the router would have to be
 * trusted to keep an unauthenticated visitor away from every workspace
 * route -- a guard, correctly applied, forever, including on routes added
 * later. Rendering it as the alternative to the shell means the workspace
 * code is not merely guarded but never loaded at all.
 */
@Component({
  selector: 'sb-login',
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class Login {
  private readonly session = inject(SessionStore);

  protected readonly username = signal('');
  protected readonly password = signal('');

  protected readonly error = this.session.error;
  protected readonly submitting = this.session.submitting;

  protected submit(): void {
    if (this.submitting()) return;
    void this.session.login(this.username(), this.password());
  }
}
