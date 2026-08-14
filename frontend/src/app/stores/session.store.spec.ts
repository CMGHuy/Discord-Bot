import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { ApplicationRef, provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  authInterceptor,
  errorInterceptor,
  loadingInterceptor,
} from '../api/interceptors';
import { SessionStore } from './session.store';

/* NG28 — session state.
 *
 * The interceptors are wired in because two of the behaviours under test are
 * *their* behaviours reaching the store: a 401 expiring the session, and a
 * failed login arriving as an ApiError rather than an HttpErrorResponse.
 */

describe('SessionStore', () => {
  let store: InstanceType<typeof SessionStore>;
  let backend: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(
          withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor]),
        ),
        provideHttpClientTesting(),
      ],
    });
    store = TestBed.inject(SessionStore);
    backend = TestBed.inject(HttpTestingController);
  });

  const boot = (authenticated: boolean, username: string | null = 'admin') => {
    const done = store.boot();
    backend.expectOne('/api/v1/session').flush({ authenticated, username });
    return done;
  };

  /* -- boot ------------------------------------------------------------ */

  it('starts in a state that renders neither the shell nor the login form', () => {
    // The whole point of the app initializer: 'unknown' must not be
    // mistakable for 'anonymous', or an authenticated reload flashes the
    // login form before correcting itself.
    expect(store.isResolving()).toBe(true);
    expect(store.isAuthenticated()).toBe(false);
  });

  it('resolves to authenticated when the server says so', async () => {
    await boot(true, 'admin');

    expect(store.isAuthenticated()).toBe(true);
    expect(store.isResolving()).toBe(false);
    expect(store.username()).toBe('admin');
  });

  it('resolves to anonymous when the server says so', async () => {
    await boot(false, null);

    expect(store.isAuthenticated()).toBe(false);
    expect(store.isResolving()).toBe(false);
  });

  it('resolves to anonymous when the admin is unreachable', async () => {
    // GET /session is not auth-guarded, so the only way to fail here is a
    // dead server -- and the right thing to show then is the login form,
    // not a permanently blank page.
    const done = store.boot();
    backend.expectOne('/api/v1/session').error(new ProgressEvent('error'), { status: 0 });
    await done;

    expect(store.isResolving()).toBe(false);
    expect(store.isAuthenticated()).toBe(false);
    expect(store.error()).toBeNull();
  });

  /* -- login ----------------------------------------------------------- */

  it('authenticates on a successful login', async () => {
    await boot(false, null);

    const done = store.login('admin', 'admin');
    backend
      .expectOne('/api/v1/session')
      .flush({ authenticated: true, username: 'admin' });
    await done;

    expect(store.isAuthenticated()).toBe(true);
    expect(store.error()).toBeNull();
  });

  it('reports a rejected password without authenticating', async () => {
    await boot(false, null);

    const done = store.login('admin', 'wrong');
    backend.expectOne('/api/v1/session').flush(
      { error: { code: 'auth', message: 'Invalid username or password.' } },
      { status: 401, statusText: 'Unauthorized' },
    );
    await done;

    expect(store.isAuthenticated()).toBe(false);
    expect(store.error()).toBe('Invalid username or password.');
    expect(store.submitting()).toBe(false);
  });

  it('distinguishes a dead admin from a wrong password', async () => {
    await boot(false, null);

    const done = store.login('admin', 'admin');
    backend.expectOne('/api/v1/session').error(new ProgressEvent('error'), { status: 0 });
    await done;

    // "Invalid username or password" for an unreachable server sends
    // someone hunting for a password that was never wrong.
    expect(store.error()).toContain('Could not reach');
  });

  it('clears a previous error when a login is retried', async () => {
    await boot(false, null);

    const failed = store.login('admin', 'wrong');
    backend.expectOne('/api/v1/session').flush(
      { error: { code: 'auth', message: 'no' } },
      { status: 401, statusText: 'Unauthorized' },
    );
    await failed;
    expect(store.error()).not.toBeNull();

    const retried = store.login('admin', 'admin');
    expect(store.error()).toBeNull(); // cleared as the attempt starts
    backend
      .expectOne('/api/v1/session')
      .flush({ authenticated: true, username: 'admin' });
    await retried;
  });

  /* -- expiry ---------------------------------------------------------- */

  it('treats a 401 from any request as a normal logout', async () => {
    // Rotating ADMIN_PASSWORD invalidates every issued session by design.
    // The person did nothing wrong, so no error banner appears -- an
    // "Invalid username or password" over an empty form, for an event they
    // did not cause, is both wrong and alarming on a tool showing money.
    await boot(true, 'admin');
    // Asserted, not assumed: without this the test would still pass if the
    // session had never become authenticated in the first place.
    expect(store.isAuthenticated()).toBe(true);

    const http = TestBed.inject(HttpClient);
    http.get('/api/v1/dashboard').subscribe({ error: () => {} });
    backend.expectOne((req) => req.url === '/api/v1/dashboard').flush(
      { error: { code: 'auth', message: 'Authentication required.' } },
      { status: 401, statusText: 'Unauthorized' },
    );

    // The store watches the 401 seam through an effect; zoneless means
    // nothing flushes it until change detection runs.
    TestBed.inject(ApplicationRef).tick();

    expect(store.isAuthenticated()).toBe(false);
    expect(store.error()).toBeNull();
  });

  /* -- logout ---------------------------------------------------------- */

  it('reloads the page after logging out', async () => {
    // The reload is how the session's data actually leaves the tab: route
    // stores, the event stream, and the lazily-loaded workspace chunks.
    // Tearing that down by hand would need every future store to remember
    // to participate, and the one that forgets leaks positions and balances
    // into the next login.
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload },
    });

    await boot(true, 'admin');

    const done = store.logout();
    backend
      .expectOne('/api/v1/session')
      .flush({ authenticated: false, username: null });
    await done;

    expect(store.isAuthenticated()).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
  });

  it('logs out locally even when the server call fails', async () => {
    const reload = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload },
    });

    await boot(true, 'admin');

    const done = store.logout();
    backend.expectOne('/api/v1/session').error(new ProgressEvent('error'), { status: 0 });
    await done;

    // DELETE is idempotent and the cookie is cleared regardless; a failure
    // must not strand someone inside a session they asked to leave.
    expect(store.isAuthenticated()).toBe(false);
    expect(reload).toHaveBeenCalledOnce();
  });

  /* -- SR58: the deep link ---------------------------------------------- */

  describe('the deep link a visitor arrived on', () => {
    /** `boot()` takes the arrival URL as a parameter precisely so this is
     *  drivable -- jsdom's `location` does not follow `history.replaceState`,
     *  and a test that pushed history would assert against `/` and pass for
     *  the wrong reason. */
    const bootFrom = (url: string, authenticated = false) => {
      const done = store.boot(url);
      backend.expectOne('/api/v1/session').flush({ authenticated, username: 'admin' });
      return done;
    };

    it('remembers where the visitor was actually trying to go', async () => {
      await bootFrom('/analytics?tab=tuning');

      expect(store.takeRedirect()).toBe('/analytics?tab=tuning');
    });

    it('does not remember the root, which is where sign-in lands anyway', async () => {
      await bootFrom('/');

      expect(store.takeRedirect()).toBeNull();
    });

    it('consumes the redirect, so a second read does not repeat it', async () => {
      // Otherwise a later navigation, or a second sign-in in the same tab,
      // jumps back to a URL the visitor has since moved on from.
      await bootFrom('/trades/abc');

      expect(store.takeRedirect()).toBe('/trades/abc');
      expect(store.takeRedirect()).toBeNull();
    });

    it('captures it even for a visitor who is already signed in', async () => {
      // The capture happens before the identity is known, and it must: a
      // reload of a deep link with a live cookie should stay put too.
      await bootFrom('/risk', true);

      expect(store.takeRedirect()).toBe('/risk');
    });
  });
});
