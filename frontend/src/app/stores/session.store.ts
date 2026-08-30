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
  /**
   * SR58 — where the visitor was actually trying to go.
   *
   * Captured in `boot()`, which runs as an app initializer BEFORE Angular
   * bootstraps and therefore before the router has had a chance to rewrite
   * the URL. That timing is the whole trick: `authGuard` is a `CanMatchFn`,
   * so while logged out no workspace route matches and the `**` fallback
   * redirects to `/dashboard` -- destroying the deep link before any login
   * form is on screen.
   *
   * Null once consumed, and null for a visitor who arrived at the root.
   */
  redirectTo: string | null;
}

const initial: SessionState = {
  status: 'unknown',
  username: null,
  error: null,
  submitting: false,
  redirectTo: null,
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
    /**
     * @param url The URL the visitor arrived on, defaulting to the real one.
     *   A parameter rather than a bare `location` read because that global
     *   cannot be driven from a test -- jsdom's `location` does not follow
     *   `history.replaceState`, so a test that tried would silently assert
     *   against `/` and pass for the wrong reason. Production calls it with
     *   no argument.
     */
    async boot(url = `${location.pathname}${location.search}`): Promise<void> {
      // Capture the deep link FIRST -- see `redirectTo`. Anything that is
      // already the root or the login-equivalent is not worth remembering,
      // and remembering it would send every ordinary sign-in through a
      // redundant navigation.
      if (url && url !== '/' && !url.startsWith('/?')) {
        patchState(store, { redirectTo: url });
      }

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
     * SR58 — the deep link to return to after signing in, consumed once.
     *
     * Consumed rather than merely read: leaving it set would make a later
     * navigation, or a second sign-in in the same tab, jump back to a URL
     * the visitor has since moved on from.
     */
    takeRedirect(): string | null {
      const target = store.redirectTo();
      if (target !== null) patchState(store, { redirectTo: null });
      return target;
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
    expire(redirectTo?: string): void {
      const fallback = `${location.pathname}${location.search}`;
      const requested = redirectTo ?? fallback;
      const remembered = requested && requested !== '/' ? requested : null;
      patchState(store, {
        status: 'anonymous', username: null,
        redirectTo: redirectTo !== undefined
          ? remembered
          : store.redirectTo() ?? remembered,
        error: store.status() === 'authenticated' ? null : store.error(),
      });
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