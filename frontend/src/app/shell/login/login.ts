import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { SessionStore } from '../../stores/session.store';
import { Button } from '../../ui/button';
import { TextInput } from '../../ui/form-controls';

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
  imports: [Button, TextInput],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class Login implements AfterViewInit {
  private readonly session = inject(SessionStore);

  /** Replaces the raw `autofocus` attribute, which had nothing to attach to
   *  once the field became `sb-text-input`: `{ read: ElementRef }` reaches
   *  past the component instance to its host element, whose actual
   *  focusable target is the native input element one level inside. */
  private readonly usernameField = viewChild('usernameField', { read: ElementRef<HTMLElement> });

  protected readonly username = signal('');
  protected readonly password = signal('');

  protected readonly error = this.session.error;
  protected readonly submitting = this.session.submitting;

  /** SR63 -- both fields were `required` in the Jinja form. Checked here as
   *  well as marked in the markup, so the button is actually disabled rather
   *  than relying on native validation the submit handler bypasses. */
  protected readonly incomplete = computed(
    () => this.username().trim() === '' || this.password() === '',
  );

  ngAfterViewInit(): void {
    this.usernameField()?.nativeElement.querySelector('input')?.focus();
  }

  /** The `<form>` no longer has NgForm around to preventDefault a real
   *  submit and re-emit it as `ngSubmit` -- dropping FormsModule means
   *  handling the native `submit` event, and preventing it, directly. */
  protected submit(event: SubmitEvent): void {
    event.preventDefault();
    if (this.submitting() || this.incomplete()) return;
    void this.session.login(this.username(), this.password());
  }
}
