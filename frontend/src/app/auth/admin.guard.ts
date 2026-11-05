import { inject } from '@angular/core';
import { CanMatchFn, Router } from '@angular/router';

import { SessionStore } from '../stores/session.store';

/**
 * v207: System is admin-only. Returns a `UrlTree`, not `false`, because a
 * `false` falls through to the `**` route, which is `/dashboard` only by
 * accident. Listed after `authGuard`, so an anonymous visitor still gets
 * `authGuard`'s answer first. Presentation only: the server is the boundary.
 */
export const adminGuard: CanMatchFn = () =>
  inject(SessionStore).isAdmin() ? true : inject(Router).createUrlTree(['/dashboard']);
