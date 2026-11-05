import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { errorInterceptor } from '../api/interceptors';
import { AdminUser } from '../api/models';
import { PASSWORD_RULE, USERNAME_RULE, UsersStore, passwordProblem, usernameProblem } from './users.store';

const URL = '/api/v1/users';
const PW = 'long-enough-pw';
const user = (over: Partial<AdminUser> = {}): AdminUser => ({
  id: 1, username: 'alice', role: 'viewer', disabled: false,
  created_at: '2026-11-05T10:00:00+00:00', last_login_at: null, ...over,
});
const failure = (code: string, status: number, message: string) =>
  [{ error: { code, message } }, { status, statusText: 'Error' }] as const;
const NO_CONTENT = { status: 204, statusText: 'No Content' };

let store: InstanceType<typeof UsersStore>;
let backend: HttpTestingController;

beforeEach(() => {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(withInterceptors([errorInterceptor])),
      provideHttpClientTesting(),
      UsersStore,
    ],
  });
  store = TestBed.inject(UsersStore);
  backend = TestBed.inject(HttpTestingController);
});
afterEach(() => backend.verify());

function loaded(users: AdminUser[]): void {
  store.load();
  backend.expectOne(URL).flush({ users });
}

describe('client-side rules mirror principals.py (v207)', () => {
  it.each(['ab', 'a'.repeat(65), 'has space', 'émile', 'semi;colon', ''])('refuses username %j', (name) => {
    expect(usernameProblem(name)).toBe(USERNAME_RULE);
  });
  it.each(['abc', 'a.b_c-d', 'A'.repeat(64)])('accepts username %j', (name) => {
    expect(usernameProblem(name)).toBeNull();
  });
  it('wants 12 password characters, not 11', () => {
    expect(passwordProblem('x'.repeat(11))).toBe(PASSWORD_RULE);
    expect(passwordProblem('x'.repeat(12))).toBeNull();
    expect(PASSWORD_RULE).toBe('password must be at least 12 characters.');
  });
});

describe('UsersStore.load', () => {
  it('loads the list in id order', () => {
    expect(store.status()).toBe('idle');
    store.load();
    expect(store.status()).toBe('loading');
    backend.expectOne(URL).flush({ users: [user({ id: 3, username: 'carol' }), user()] });
    expect(store.users().map((u) => u.id)).toEqual([1, 3]);
    expect(store.status()).toBe('ready');
    expect(store.error()).toBeNull();
  });

  it('keeps the last list when a reload fails, and says why', () => {
    loaded([user()]);
    store.load();
    backend.expectOne(URL).flush(...failure('unavailable', 503, 'down'));
    expect(store.status()).toBe('error');
    expect(store.error()).toBe('The admin is not responding.');
    expect(store.users()).toHaveLength(1);
  });

  it('shows the server message for any other load failure', () => {
    store.load();
    backend.expectOne(URL).flush(...failure('internal', 500, 'Internal error.'));
    expect(store.error()).toBe('Internal error.');
  });
});

describe('UsersStore.create', () => {
  it('refuses a short password without a request', async () => {
    expect(await store.create('bob', 'short')).toBe(false);
    expect(store.actionError()).toBe(PASSWORD_RULE);
    backend.expectNone({ method: 'POST', url: URL });
  });

  it('refuses a bad username without a request', async () => {
    expect(await store.create('b b', PW)).toBe(false);
    expect(store.actionError()).toBe(USERNAME_RULE);
    backend.expectNone({ method: 'POST', url: URL });
  });

  it('posts the trimmed name and adds the row', async () => {
    loaded([user()]);
    const done = store.create('  bob ', PW);
    const req = backend.expectOne({ method: 'POST', url: URL });
    expect(req.request.body).toEqual({ username: 'bob', password: PW });
    expect(store.busy()).toBe('create');
    req.flush(user({ id: 2, username: 'bob' }), { status: 201, statusText: 'Created' });
    expect(await done).toBe(true);
    expect(store.users().map((u) => u.username)).toEqual(['alice', 'bob']);
    expect(store.notice()).toBe('Created viewer bob.');
    expect(store.busy()).toBeNull();
  });

  it('explains a 409 and leaves the list alone', async () => {
    loaded([user()]);
    const done = store.create('Alice', PW);
    backend.expectOne({ method: 'POST', url: URL }).flush(...failure('conflict', 409, 'username is already taken.'));
    expect(await done).toBe(false);
    expect(store.actionError()).toBe('"Alice" is taken: names are case-insensitive, and the admin\'s own name is reserved.');
    expect(store.users()).toHaveLength(1);
    expect(store.busy()).toBeNull();
  });

  it('shows the server message for a 400', async () => {
    const done = store.create('bob', PW);
    backend.expectOne({ method: 'POST', url: URL })
      .flush(...failure('invalid', 400, "username must be 3-64 characters: letters, digits, '.', '_' or '-'."));
    expect(await done).toBe(false);
    expect(store.actionError()).toBe(USERNAME_RULE);
  });
});

describe('UsersStore row commands', () => {
  it('disables through PATCH, swaps the row and says sessions ended', async () => {
    loaded([user()]);
    const done = store.setDisabled(user(), true);
    const req = backend.expectOne({ method: 'PATCH', url: `${URL}/1` });
    expect(req.request.body).toEqual({ disabled: true });
    expect(store.busy()).toBe(1);
    req.flush(user({ disabled: true }));
    expect(await done).toBe(true);
    expect(store.users()[0].disabled).toBe(true);
    expect(store.notice()).toBe('Disabled alice. Any session they had open has ended.');
  });

  it('re-enables without the session note', async () => {
    loaded([user({ disabled: true })]);
    const done = store.setDisabled(user({ disabled: true }), false);
    backend.expectOne({ method: 'PATCH', url: `${URL}/1` }).flush(user());
    expect(await done).toBe(true);
    expect(store.notice()).toBe('Enabled alice.');
  });

  it('checks the new password first, then resets with a 204', async () => {
    loaded([user()]);
    expect(await store.resetPassword(user(), 'x'.repeat(11))).toBe(false);
    expect(store.actionError()).toBe(PASSWORD_RULE);
    backend.expectNone({ method: 'POST', url: `${URL}/1/password` });
    const done = store.resetPassword(user(), PW);
    const req = backend.expectOne({ method: 'POST', url: `${URL}/1/password` });
    expect(req.request.body).toEqual({ password: PW });
    req.flush(null, NO_CONTENT);
    expect(await done).toBe(true);
    expect(store.actionError()).toBeNull();
    expect(store.notice()).toBe('Password reset for alice. Any session they had open has ended.');
  });

  it('deletes and drops the row', async () => {
    loaded([user(), user({ id: 2, username: 'bob' })]);
    const done = store.remove(user());
    backend.expectOne({ method: 'DELETE', url: `${URL}/1` }).flush(null, NO_CONTENT);
    expect(await done).toBe(true);
    expect(store.users().map((u) => u.id)).toEqual([2]);
    expect(store.notice()).toBe('Deleted alice.');
  });

  it('drops a row that is already gone, and names it', async () => {
    loaded([user()]);
    const done = store.setDisabled(user(), true);
    backend.expectOne({ method: 'PATCH', url: `${URL}/1` }).flush(...failure('not_found', 404, 'No user with id 1.'));
    expect(await done).toBe(false);
    expect(store.users()).toEqual([]);
    expect(store.actionError()).toBe('alice no longer exists; it was removed from the list.');
    expect(store.busy()).toBeNull();
  });

  it('says nothing was changed when the admin is down', async () => {
    loaded([user()]);
    const done = store.remove(user());
    backend.expectOne({ method: 'DELETE', url: `${URL}/1` }).flush(...failure('unavailable', 503, 'down'));
    expect(await done).toBe(false);
    expect(store.actionError()).toBe('The admin is not responding — nothing was changed.');
    expect(store.users()).toHaveLength(1);
  });

  it('clears both messages, and a new command clears the old ones', async () => {
    loaded([user()]);
    await store.create('b b', PW);
    store.clearMessages();
    expect(store.actionError()).toBeNull();
    expect(store.notice()).toBeNull();
    await store.create('b b', PW);
    const done = store.remove(user());
    expect(store.actionError()).toBeNull();
    backend.expectOne({ method: 'DELETE', url: `${URL}/1` }).flush(null, NO_CONTENT);
    await done;
  });
});
