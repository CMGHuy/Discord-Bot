import { inject } from '@angular/core';
import { CanMatchFn } from '@angular/router';

import { SessionStore } from '../stores/session.store';

/**
 * Protects all six workspace routes.
 *
 * A `CanMatchFn`, not a `CanActivateFn`: `canMatch` runs *before* the
 * router resolves the route's `loadComponent`, so an unauthenticated
 * request never downloads the workspace chunk. `canActivate` runs after,
 * which would fetch the code and then refuse to show it.
 *
 * This is the second of two defences and the weaker one. The first is
 * structural: the root component renders the login form instead of the
 * shell, so there is no router-outlet to navigate into while logged out.
 * This guard exists for the case that structure cannot cover -- a session
 * expiring mid-visit, where the outlet already exists and a navigation is
 * already in flight.
 */
export const authGuard: CanMatchFn = () => inject(SessionStore).isAuthenticated();
