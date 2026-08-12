import { Injectable, signal } from '@angular/core';

/** The seam between "a request came back 401" and "show the login view".
 *
 * The auth interceptor cannot inject `SessionStore` directly: the store
 * injects `ApiClient` to log in and out, and `ApiClient` runs through the
 * interceptor -- a cycle. So the interceptor bumps a counter here and the
 * store reacts to it (NG28).
 *
 * A monotonically increasing counter rather than a boolean, because the
 * interesting event is "another 401 just happened", and a boolean already
 * true cannot say that a second time.
 */
@Injectable({ providedIn: 'root' })
export class UnauthorizedService {
  private readonly count = signal(0);

  /** Bumped on every 401 from any request. */
  readonly seen = this.count.asReadonly();

  report(): void {
    this.count.update((n) => n + 1);
  }
}
