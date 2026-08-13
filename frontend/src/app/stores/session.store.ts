import { computed, effect, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withHooks,
  withMethods,
  withState,
} from '@ngrx/signals';
import { firstValueFrom } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { UnauthorizedService } from '../api/unauthorized.service';

/** `unknown` only exists before the boot check resolves. The shell must
 *  never render in that state -- see the note on `boot()`. */
export type SessionStatus = 'unknown' | 'anonymous' | 'authenticated';

interface SessionState {
  status: SessionStatus;
  username: string | null;
  /** Set only by a rejected *login attempt*. An expired session is not an
   *  error and must not populate this. */
  error: string | null;
  submitting: boolean;
}

const initial: SessionState = {
  status: 'unknown',
  username: null,
  error: null,
  submitting: false,
};

/**
 * Who is logged in, and the two operations that change it.
 *
 * Auth is the existing signed session cookie (spec v11 Decision 5) -- no
 * token, no refresh flow, and a session established through the Jinja
 * `/login` page is valid here and vice versa, which matters because both
 * UIs are live until cutover.
 */
export const SessionStore = signalStore(
  { providedIn: 'root' },
  withState(initial),
  withComputed(({ status, username }) => ({
    isAuthenticated: computed(() => status() === 'authenticated'),
    /** True only while the boot check is outstanding. Render nothing at
     *  all in this state -- not the shell, not the login form. */
    isResolving: computed(() => status() === 'unknown'),
    displayName: computed(() => username() ?? 'admin'),
  })),
  withMethods((store, api = inject(ApiClient)) => ({
    /**
     * Ask the server who we are. Awaited by an app initializer, so the
     * application does not bootstrap until it resolves.
     *
     * This is what stops the "dashboard flash": if the shell rendered
     * first and corrected itself when the answer came back, an
     * unauthenticated visitor would see a frame of the real UI -- empty
     * panels and all -- before being shown the login form. Worse, the
     * workspaces would have started fetching, producing a burst of 401s
     * on every page load.
     *
     * It cannot fail into a broken state: `GET /session` is deliberately
     * not auth-guarded server-side (it answers `authenticated: false`
     * rather than 401), so the only way here is a dead server -- and the
     * right thing to show then is the login form, which is what
     * 'anonymous' renders.
     */
    async boot(): Promise<void> {
      try {
        const identity = await firstValueFrom(api.session());
        patchState(store, {
          status: identity.authenticated ? 'authenticated' : 'anonymous',
          username: identity.username,
        });
      } catch {
        patchState(store, { status: 'anonymous', username: null });
      }
    },

    async login(username: string, password: string): Promise<void> {
      patchState(store, { submitting: true, error: null });
      try {
        const identity = await firstValueFrom(api.login(username, password));
        patchState(store, {
          status: identity.authenticated ? 'authenticated' : 'anonymous',
          username: identity.username,
          submitting: false,
        });
      } catch (error) {
        patchState(store, {
          status: 'anonymous',
          username: null,
          submitting: false,
          error:
            error instanceof ApiError && error.isAuth
              ? 'Invalid username or password.'
              : 'Could not reach the admin. Is it running?',
        });
      }
    },

    /**
     * Clear the server session, then reload the page.
     *
     * The reload is the point, not laziness. Logging out has to leave
     * nothing behind: every route store's cached rows, the event stream's
     * open connection, and the lazily-loaded workspace chunks themselves.
     * Tearing those down by hand means every future store has to remember
     * to participate, and the one that forgets leaks the previous
     * session's data into the next login -- on a tool whose whole content
     * is account balances and positions.
     */
    async logout(): Promise<void> {
      try {
        await firstValueFrom(api.logout());
      } catch {
        // DELETE /session is idempotent and clears the cookie regardless;
        // a failure here must not strand someone in a session they have
        // asked to leave.
      }
      patchState(store, { status: 'anonymous', username: null });
      window.location.reload();
    },

    /**
     * The session went away underneath us -- expired, or ADMIN_PASSWORD
     * was rotated, which invalidates every issued session by design.
     *
     * **This is a normal logout, not an error.** Nothing sets `error`
     * here: the person did nothing wrong, and showing "Invalid username
     * or password" above an empty form for an event they did not cause is
     * both wrong and alarming on a tool that shows money.
     */
    expire(): void {
      patchState(store, { status: 'anonymous', username: null, error: null });
    },
  })),
  withHooks({
    onInit(store, unauthorized = inject(UnauthorizedService)) {
      // Any 401 from any request, via the seam in api/unauthorized.service.
      // The store cannot be injected into the interceptor -- it injects
      // ApiClient, which runs through the interceptor -- so the signal is
      // the direction that does not create a cycle.
      effect(() => {
        if (unauthorized.seen() > 0) {
          store.expire();
        }
      });
    },
  }),
);
