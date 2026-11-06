# v207 part 5 — Users page and release: client + `UsersStore`, the System → Users tab, deploy doc

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md) (§ Users API, § SPA "Users page", § Rollout, § Testing "Frontend")
**Index:** [`2026-11-05-v207-viewer-accounts_0-index.md`](2026-11-05-v207-viewer-accounts_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V207-16, V207-17, V207-17b (index groups G and H). They run in order; V207-17b ends with the deploy section, after every other v207 task is committed on the branch. The version bump is `/close-out`'s, not a task. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v207-viewer-accounts`; every command names that path, never the main tree. Frontend specs run narrow: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include <spec>` (the path after `--include` is relative to `<wt>/frontend`). No task runs the full suite: CI does after the push.

**Contracts this part consumes, fixed elsewhere:**
- Users API (V207-6): `GET /api/v1/users` → `{"users": [UserOut]}`; `POST /api/v1/users` `{username, password}` → 201 UserOut; `PATCH /api/v1/users/<id>` `{disabled}` → 200 UserOut; `POST /api/v1/users/<id>/password` `{password}` → 204; `DELETE /api/v1/users/<id>` → 204. Errors: 404 `not_found`, 409 `conflict` (duplicate, case-insensitive, or the `.env` admin's name; message `username is already taken.`), 400 `invalid` (message starts `username ` or `password `). UserOut = `{id, username, role: "viewer", disabled, created_at, last_login_at | null}`.
- Server-side rules mirrored client-side for instant feedback (the server stays the authority): username `^[A-Za-z0-9._-]{3,64}$`, message `username must be 3-64 characters: letters, digits, '.', '_' or '-'.`; password at least 12 characters, message `password must be at least 12 characters.` (V207-3 `USERNAME_RULE` / `PASSWORD_RULE`).
- `write-calls.ts` (V207-12): `GATED_CALLERS['admin-route']` already lists `stores/users.store.ts` and `workspaces/system/`. V207-16 only adds its four mutating methods as `'admin-route'` rows; they are never called outside those paths (the spec's stray check fails otherwise).
- Role idiom (part 3 header): specs that render a role-aware component set `patchState(unprotected(TestBed.inject(SessionStore)), { status: 'authenticated', username, role })`. The Users tab lives behind `adminGuard` (V207-9) and reads no role itself, so its specs need no session state.

## Review focus (this part)

1. **A 409 on create** (a name that differs only in case from an existing viewer, or the `.env` admin's own name): the dialog stays open with the typed values, says the name is taken and why (names are case-insensitive, the admin's name is reserved), and the list is unchanged. Test in V207-16 (store) and V207-17 (dialog).
2. **A row that vanished under the admin** (deleted in another tab, then Disable / Reset / Delete pressed here): the 404 drops the row and names it, never a raw "No user with id 7." and never a stuck spinner. Test in V207-16.
3. **A 64-character username on a 390 px phone**: the compact row and the row drawer wrap it (`overflow-wrap: anywhere`), no horizontal page scroll. Checked by the layout audit in V207-17 with a long-name fixture account.
4. **Delete pressed by mistake**: nothing is sent until the confirm dialog's Delete; Cancel and Escape send nothing. On a phone, the row drawer of a deleted account closes rather than offering actions on a row that no longer exists. Tests in V207-17.
5. **The admin offline or the table not migrated yet**: a 503 / 500 on load shows a retry, keeps any list already shown, and a failed mutation reads "nothing was changed", never a silent no-op. Test in V207-16.

# Phase G — Users page

### Task V207-16: Users API client, models, `UsersStore`

**Model:** sonnet — four thin client wrappers and one store whose every message and branch is fixed below; no design judgement left.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (session section, after `Identity` :84)
- Modify: `frontend/src/app/api/api-client.ts` (import block :1-78; new section after the session section's `logout`)
- Modify: `frontend/src/app/auth/write-calls.ts` (created by V207-12: four rows)
- Create: `frontend/src/app/stores/users.store.ts`
- Create: `frontend/src/app/stores/users.store.spec.ts`

**Interfaces:**
- Consumes: the Users API contract (part header); `ApiError` (`api/api-error.ts`: `code`, `status`, `message`); `errorInterceptor` (`api/interceptors.ts`) turns every v1 error body into an `ApiError`; `WRITE_CALLS` / `GATED_CALLERS` from V207-12.
- Produces (V207-17 consumes all of it):
  - `models.ts`: `export interface AdminUser { id: number; username: string; role: 'viewer'; disabled: boolean; created_at: string; last_login_at: string | null; }`
  - `ApiClient.listUsers(): Observable<AdminUser[]>`, `.createUser(body: { username: string; password: string }): Observable<AdminUser>`, `.setUserDisabled(id: number, disabled: boolean): Observable<AdminUser>`, `.resetUserPassword(id: number, password: string): Observable<void>`, `.deleteUser(id: number): Observable<void>`
  - `users.store.ts`: `USERNAME_PATTERN: RegExp`, `PASSWORD_MIN = 12`, `USERNAME_RULE`, `PASSWORD_RULE` (strings), `usernameProblem(name: string): string | null`, `passwordProblem(password: string): string | null`, `failureText(error: ApiError, username: string): string`, `type UsersStatus = 'idle' | 'loading' | 'ready' | 'error'`, `type UsersBusy = 'create' | number | null`, and `UsersStore` (a `signalStore` **not** provided in root: the Users tab provides it) with state `users: AdminUser[]`, `status: UsersStatus`, `error: string | null`, `busy: UsersBusy`, `notice: string | null`, `actionError: string | null`, and methods `load(): void`, `create(username: string, password: string): Promise<boolean>`, `setDisabled(user: AdminUser, disabled: boolean): Promise<boolean>`, `resetPassword(user: AdminUser, password: string): Promise<boolean>`, `remove(user: AdminUser): Promise<boolean>`, `clearMessages(): void`. Each mutation resolves `true` on success and `false` on any refusal or failure, so a dialog closes only on `true`.

`listUsers` is a GET, so it gets **no** `WRITE_CALLS` row: V207-12's first assertion requires the keys to equal the mutating methods exactly. The four mutating methods are `'admin-route'`.

- [ ] **Step 1: Write the failing spec** — `frontend/src/app/stores/users.store.spec.ts`

```ts
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/users.store.spec.ts`
Expected: FAIL — cannot resolve `./users.store`.

- [ ] **Step 3: Add `AdminUser` to `models.ts`**

Directly below `Identity` in the `/* -- session -- */` section, the interface from Interfaces above, with a doc comment: one viewer account as every `/api/v1/users` endpoint returns it (V207-6); the server never sends the password hash or `credential_version`, so neither exists here.

- [ ] **Step 4: Add the five `ApiClient` methods**

Add `AdminUser` to the `./models` import list and `map` to the rxjs import (`import { Observable, map, of } from 'rxjs';`). Then, after `logout()`, a new section:

```ts
  /* -- users (v207, admin-only) ---------------------------------------- */

  /** Unwrapped here: the envelope carries nothing but the list, and the
   *  store should not have to know it exists. */
  listUsers(): Observable<AdminUser[]> {
    return this.http.get<{ users: AdminUser[] }>(`${this.base}/users`).pipe(map((body) => body.users));
  }

  /** 409 `conflict` for a taken name (case-insensitive) or the `.env`
   *  admin's own; 400 `invalid` names the field. */
  createUser(body: { username: string; password: string }): Observable<AdminUser> {
    return this.http.post<AdminUser>(`${this.base}/users`, body, this.skipRouteRefresh);
  }

  /** Disabling ends the viewer's live sessions server-side (V207-6). */
  setUserDisabled(id: number, disabled: boolean): Observable<AdminUser> {
    return this.http.patch<AdminUser>(`${this.base}/users/${id}`, { disabled }, this.skipRouteRefresh);
  }

  /** 204, no body. Ends the viewer's live sessions. */
  resetUserPassword(id: number, password: string): Observable<void> {
    return this.http.post<void>(`${this.base}/users/${id}/password`, { password }, this.skipRouteRefresh);
  }

  deleteUser(id: number): Observable<void> {
    return this.http.delete<void>(`${this.base}/users/${id}`, this.skipRouteRefresh);
  }
```

`skipRouteRefresh` on all four writes: the store patches its own list, and a route refresh would only re-run the System resolver for nothing.

- [ ] **Step 5: Write `frontend/src/app/stores/users.store.ts`**

Module doc comment: the Users tab's store (spec v207 § SPA); admin-only by route (`adminGuard`) and by server (`/api/v1/users` is an admin-only prefix); the client-side rules only save a round trip, the server stays the authority; mutations return a `Promise<boolean>` so a dialog closes only on success and keeps what was typed otherwise.

```ts
export const USERNAME_PATTERN = /^[A-Za-z0-9._-]{3,64}$/;
export const PASSWORD_MIN = 12;
export const USERNAME_RULE = "username must be 3-64 characters: letters, digits, '.', '_' or '-'.";
export const PASSWORD_RULE = `password must be at least ${PASSWORD_MIN} characters.`;

export const usernameProblem = (name: string): string | null => (USERNAME_PATTERN.test(name) ? null : USERNAME_RULE);
export const passwordProblem = (password: string): string | null => (password.length >= PASSWORD_MIN ? null : PASSWORD_RULE);

/** What a failed command tells the admin. A table, not a branch chain:
 *  each code reads one way whatever the command was. */
export function failureText(error: ApiError, username: string): string {
  const text: Record<string, string> = {
    conflict: `"${username}" is taken: names are case-insensitive, and the admin's own name is reserved.`,
    not_found: `${username} no longer exists; it was removed from the list.`,
    unavailable: 'The admin is not responding — nothing was changed.',
  };
  return text[error.code] ?? error.message;
}

const SESSIONS_ENDED = 'Any session they had open has ended.';
const byId = (a: AdminUser, b: AdminUser): number => a.id - b.id;
```

`UsersSlice` holds the six state fields from Interfaces; initial state `users: []`, `status: 'idle'`, everything else `null`. `withMethods((store, api = inject(ApiClient)) => { ... })` builds these private helpers and returns the six methods:

```ts
    const swap = (row: AdminUser): void =>
      patchState(store, { users: store.users().map((u) => (u.id === row.id ? row : u)) });
    const drop = (id: number): void =>
      patchState(store, { users: store.users().filter((u) => u.id !== id) });
    const refuse = (problem: string): Promise<boolean> => {
      patchState(store, { notice: null, actionError: problem });
      return Promise.resolve(false);
    };
    /** One path for every command: busy on, messages cleared, busy off.
     *  A 404 drops the row it named, so the list never offers a ghost. */
    const run = <T>(busy: UsersBusy, user: { id?: number; username: string }, request: Observable<T>,
                    ok: (value: T) => void): Promise<boolean> => {
      patchState(store, { busy, notice: null, actionError: null });
      return lastValueFrom(request.pipe(
        map((value) => { patchState(store, { busy: null }); ok(value); return true; }),
        catchError((error: ApiError) => {
          if (error.code === 'not_found' && user.id !== undefined) drop(user.id);
          patchState(store, { busy: null, actionError: failureText(error, user.username) });
          return of(false);
        }),
      ));
    };
```

- `load()`: `patchState(store, { status: 'loading' })`, then `api.listUsers().subscribe({ next: (users) => patchState(store, { users: [...users].sort(byId), status: 'ready', error: null }), error: (e: ApiError) => patchState(store, { status: 'error', error: e.code === 'unavailable' ? 'The admin is not responding.' : e.message }) })`. On failure the list stays as it was.
- `create(username, password)`: `const name = username.trim()`; `const problem = usernameProblem(name) ?? passwordProblem(password)`; refused → `refuse(problem)`; else `run('create', { username: name }, api.createUser({ username: name, password }), (made) => patchState(store, { users: [...store.users(), made].sort(byId), notice: 'Created viewer ' + made.username + '.' }))`.
- `setDisabled(user, disabled)`: `run(user.id, user, api.setUserDisabled(user.id, disabled), (row) => { swap(row); patchState(store, { notice: disabled ? 'Disabled ' + user.username + '. ' + SESSIONS_ENDED : 'Enabled ' + user.username + '.' }); })`.
- `resetPassword(user, password)`: `passwordProblem(password)` refused first; else `run(user.id, user, api.resetUserPassword(user.id, password), () => patchState(store, { notice: 'Password reset for ' + user.username + '. ' + SESSIONS_ENDED }))`.
- `remove(user)`: `run(user.id, user, api.deleteUser(user.id), () => { drop(user.id); patchState(store, { notice: 'Deleted ' + user.username + '.' }); })`.
- `clearMessages()`: `patchState(store, { notice: null, actionError: null })`.

(Template literals are fine in the source; the plan spells the strings with `+` only so they read unambiguously here.) Imports: `inject` from `@angular/core`; `patchState, signalStore, withMethods, withState` from `@ngrx/signals`; `Observable, catchError, lastValueFrom, map, of` from `rxjs`; `ApiClient`, `ApiError`, `AdminUser`. No `providedIn`: V207-17's `UsersTab` provides it, so its list lives exactly as long as the tab.

- [ ] **Step 6: Add the four inventory rows to `frontend/src/app/auth/write-calls.ts`**

Below `savePreferences`, in `WRITE_CALLS`:

```ts
  createUser: 'admin-route',        // users.store <- System -> Users tab (V207-17)
  setUserDisabled: 'admin-route',   // users.store <- System -> Users tab
  resetUserPassword: 'admin-route', // users.store <- System -> Users tab
  deleteUser: 'admin-route',        // users.store <- System -> Users tab
```

`GATED_CALLERS['admin-route']` already lists `stores/users.store.ts` and `workspaces/system/` (V207-12): leave it as it is.

- [ ] **Step 7: Run both specs to see them pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/stores/users.store.spec.ts --include src/app/auth/write-calls.spec.ts`
Expected: PASS, `0 failed`. A `write-calls` failure naming `listUsers` means it got a row it must not have; one naming `<method> <- <path>` means a Users method is called outside the store: move the call, never widen `GATED_CALLERS`.

- [ ] **Step 8: Commit**

```bash
cd "<wt>" && git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/auth/write-calls.ts frontend/src/app/stores/users.store.ts frontend/src/app/stores/users.store.spec.ts
git commit -m "feat(v207): Users API client, AdminUser model and UsersStore with client-side rules (V207-16)"
```

### Task V207-17: Users tab: table / cards, dialogs, empty state, three widths

**Model:** sonnet — one page built from existing primitives (`sb-panel`, `sb-data-table`, `sb-confirm-dialog`) with its layout and copy fixed below.

Split for size: this task builds the page, its row commands (Disable/Enable, Delete behind a confirm) and the System wiring. **V207-17b** adds New viewer, Reset password, their form dialog and the layout audit at three widths.

**Files:**
- Create: `frontend/src/app/workspaces/system/users-tab.ts`
- Create: `frontend/src/app/workspaces/system/users-tab.spec.ts`
- Modify: `frontend/src/app/stores/system.store.ts` (`SYSTEM_TABS` :35; `resolveTab` :565-571); `frontend/src/app/stores/system.store.spec.ts` (:837-839)
- Modify: `frontend/src/app/workspaces/system/system.ts` (`TABS` :23-28, `TAB_ACTION` :35-40, `imports`, the `@switch`); `frontend/src/app/workspaces/system/system.spec.ts` (:49-52 plus one test)
- Modify: `frontend/src/app/ui/data-table/data-table.ts` (constructor :655); `frontend/src/app/ui/data-table/data-table.spec.ts` (`DataTable row drawer` describe :1129)
- Modify: `frontend/scripts/layout-audit-lib.mjs` (`ROUTES` :24); `frontend/scripts/layout-audit-lib.test.mjs` (:26-27, count 29 → 30)

The last two pairs are outside the ledger row on purpose: `ui-design.md` requires a new tab in the audit's `ROUTES` in the same commit, and on a phone the row drawer must neither keep offering commands for a just-deleted account nor show a stale status after Disable (Review focus 4). The data-table change is generic (the drawer follows its row by `rowKey`) and touches no part-4 file.

**Interfaces:**
- Consumes (V207-16): `AdminUser`; `UsersStore` (`users`, `status`, `error`, `busy`, `notice`, `actionError`, `load()`, `setDisabled()`, `remove()`, `clearMessages()`). `adminGuard` (V207-9) already guards every `/system` URL, so the tab reads no role.
- Produces (V207-17b extends both files): `UsersTab` (selector `sb-users-tab`, `providers: [UsersStore]`) with the `#actionsCell` template, the `.row-actions` span and the `deleting` signal; `deleteConsequence(name: string): string`; `lastSignIn(iso: string | null): string`; the spec helpers `mount`, `settle`, `press`, `openDialog`, `dialogButton`, `user`, `failure`; `SystemTab` gains `'users'`.

**Layout, per device class** (`ui-design.md` § Device classes):
- Desktop ≥ 1024 and tablet 640–1023: one `sb-panel` "Viewer accounts", then an `sb-data-table` with Username · Status · Last sign-in · Created · Actions. Actions is a wrapping flex row: **Disable/Enable** (ghost) and a `danger-icon` bin (`sb-hit`, aria-label `Delete <name>`); every button `min-height: var(--control-h)` (44 px under coarse pointer or ≤ 1023 px).
- Phone < 640: the same table declared with compact slots, so `sb-data-table` draws one card per account (line 1 Username + Status, line 2 Last sign-in); a tap opens its row drawer with Created and the commands. Never hand-built cards (`workspace-consistency.spec.ts`).
- `clientPaging="system-users"`: 10 rows on desktop, 5 on tablet/phone, no pager at ≤ 5 rows (§ Tables and pagers).
- Empty state: title "No viewer accounts yet", hint "New viewer creates a read-only sign-in for someone who should see the book but change nothing."
- The bin is a per-row command with its own confirm, like the Watchlist row bin, so it stays in its row, not in the page header; `TAB_ACTION.users` is `null`.

- [ ] **Step 1: Write the failing specs**

`frontend/src/app/workspaces/system/users-tab.spec.ts`:

```ts
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeAll, describe, expect, it } from 'vitest';

import { errorInterceptor } from '../../api/interceptors';
import { AdminUser } from '../../api/models';
import { installDialogPolyfill } from '../../testing/dialog-polyfill';
import { compactKeys, drawerKeys, openRowDrawer, phoneViewport } from '../../ui/data-table/testing/reachability';
import { UsersTab, deleteConsequence, lastSignIn } from './users-tab';

const URL = '/api/v1/users';
const NO_CONTENT = { status: 204, statusText: 'No Content' };
const user = (over: Partial<AdminUser> = {}): AdminUser => ({
  id: 1, username: 'alice', role: 'viewer', disabled: false,
  created_at: '2026-11-01T10:00:00+00:00', last_login_at: null, ...over,
});
const failure = (code: string, status: number, message: string) =>
  [{ error: { code, message } }, { status, statusText: 'Error' }] as const;

let fixture: ComponentFixture<UsersTab>;
let backend: HttpTestingController;
const el = () => fixture.nativeElement as HTMLElement;
const q = <T extends Element = HTMLElement>(selector: string) => el().querySelector<T>(selector);
const openDialog = () => q<HTMLDialogElement>('dialog[open]');
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
async function settle(): Promise<void> {
  fixture.detectChanges();
  await tick();
  await fixture.whenStable();
  fixture.detectChanges();
}
async function press(selector: string): Promise<void> {
  q<HTMLButtonElement>(selector)!.click();
  await settle();
}
const dialogButton = (label: string) => [...openDialog()!.querySelectorAll<HTMLButtonElement>('button')]
  .find((button) => button.textContent!.trim() === label)!;

async function mount(answer: AdminUser[] | 'down', phone = false): Promise<void> {
  TestBed.resetTestingModule();
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(), provideRouter([]),
      provideHttpClient(withInterceptors([errorInterceptor])), provideHttpClientTesting(),
      ...(phone ? [phoneViewport()] : []),
    ],
  });
  fixture = TestBed.createComponent(UsersTab);
  backend = TestBed.inject(HttpTestingController);
  fixture.detectChanges();
  const req = backend.expectOne(URL);
  if (answer === 'down') req.flush(...failure('unavailable', 503, 'down'));
  else req.flush({ users: answer });
  await settle();
}

describe('System → Users tab (v207)', () => {
  beforeAll(() => installDialogPolyfill());

  it('shows the empty state when there are no accounts', async () => {
    await mount([]);
    expect(el().textContent).toContain('No viewer accounts yet');
    expect(el().querySelectorAll('tbody tr [data-action]')).toHaveLength(0);
  });

  it('lists each account with its status, last sign-in and the matching toggle', async () => {
    await mount([user(), user({ id: 2, username: 'bob', disabled: true, last_login_at: '2026-11-04T09:00:00+00:00' })]);
    const rows = [...el().querySelectorAll('tbody tr')];
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain('alice');
    expect(rows[0].textContent).toContain('Active');
    expect(rows[0].textContent).toContain('Never');
    expect(rows[1].textContent).toContain('Disabled');
    expect(rows[1].textContent).toContain(lastSignIn('2026-11-04T09:00:00+00:00'));
    expect(rows[1].querySelector('[data-action="toggle-disabled"]')!.textContent!.trim()).toBe('Enable');
    expect(rows[0].querySelector('[data-action="delete"]')!.getAttribute('aria-label')).toBe('Delete alice');
  });

  it('asks before deleting: Cancel sends nothing, Delete removes the row', async () => {
    await mount([user()]);
    await press('[data-action="delete"]');
    expect(openDialog()!.textContent).toContain(deleteConsequence('alice'));
    dialogButton('Cancel').click();
    await settle();
    backend.expectNone({ method: 'DELETE', url: `${URL}/1` });

    await press('[data-action="delete"]');
    dialogButton('Delete').click();
    await settle();
    backend.expectOne({ method: 'DELETE', url: `${URL}/1` }).flush(null, NO_CONTENT);
    await settle();
    expect(openDialog()).toBeNull();
    expect(el().textContent).toContain('No viewer accounts yet');
    expect(q('[role="status"]')!.textContent).toContain('Deleted alice.');
  });

  it('names the account and keeps the row when a delete fails', async () => {
    await mount([user()]);
    await press('[data-action="delete"]');
    dialogButton('Delete').click();
    await settle();
    backend.expectOne({ method: 'DELETE', url: `${URL}/1` }).flush(...failure('unavailable', 503, 'down'));
    await settle();
    expect(openDialog()).toBeNull();
    expect(q('[role="alert"]')!.textContent).toContain('nothing was changed');
    expect(q('tbody')!.textContent).toContain('alice');
  });

  it('disables from the row and flips the button to Enable', async () => {
    await mount([user()]);
    await press('[data-action="toggle-disabled"]');
    const req = backend.expectOne({ method: 'PATCH', url: `${URL}/1` });
    expect(req.request.body).toEqual({ disabled: true });
    req.flush(user({ disabled: true }));
    await settle();
    expect(q('[data-action="toggle-disabled"]')!.textContent!.trim()).toBe('Enable');
    expect(q('tbody')!.textContent).toContain('Disabled');
  });

  it('offers a retry when the list cannot load', async () => {
    await mount('down');
    expect(q('[role="alert"]')!.textContent).toContain('The admin is not responding.');
    await press('[data-action="retry"]');
    backend.expectOne(URL).flush({ users: [user()] });
    await settle();
    expect(q('[role="alert"]')).toBeNull();
    expect(q('tbody')!.textContent).toContain('alice');
  });

  it('draws a phone card per account, with the commands in its drawer', async () => {
    await mount([user()], true);
    const table = q('sb-data-table')!;
    expect(compactKeys(table)).toEqual(['username', 'status', 'last_login_at']);
    openRowDrawer(table);
    await settle();
    expect(drawerKeys(table)).toEqual(['created_at', 'actions']);
    expect(table.querySelector('sb-drawer.row-drawer [data-action="toggle-disabled"]')).toBeTruthy();
  });

  it('closes the phone drawer of an account that was just deleted', async () => {
    await mount([user()], true);
    openRowDrawer(q('sb-data-table')!);
    await settle();
    await press('sb-drawer.row-drawer [data-action="delete"]');
    dialogButton('Delete').click();
    await settle();
    backend.expectOne({ method: 'DELETE', url: `${URL}/1` }).flush(null, NO_CONTENT);
    await settle();
    expect(q<HTMLDialogElement>('sb-drawer.row-drawer dialog')?.open ?? false).toBe(false);
  });
});
```

In `data-table.spec.ts`, inside `describe('DataTable row drawer (v179 §3.1, §6a.4)', ...)` (its `host.rows` is a signal over `TRADES`):

```ts
  it('closes the drawer when its row leaves the table (v207)', async () => {
    open(1);
    host.rows.set(host.rows().filter((_, index) => index !== 1));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(dialog()?.open ?? false).toBe(false);
  });

  it('follows its row when the row object is replaced (v207)', async () => {
    open(1);
    host.rows.set(host.rows().map((row, index) => (index === 1 ? { ...row, strategy: 'Fibonacci' } : row)));
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(dialog()!.open).toBe(true);
    expect(el().querySelector('sb-drawer.row-drawer [data-col="strategy"] dd')!.textContent!.trim()).toBe('Fibonacci');
  });
```

In `system.spec.ts`, rename the first test to `'orders the bar Scan, Providers, Settings, Logs, Users'` with `toEqual(['Scan', 'Providers', 'Settings', 'Logs', 'Users'])`, and add (the tab's own GET stays pending; this spec never calls `verify()`):

```ts
  it('opens the Users tab from ?tab=users, with no header command', async () => {
    const { el } = await mount('users');
    expect(selected(el)).toBe('Users');
    expect(el.querySelector('sb-users-tab')).toBeTruthy();
    expect(el.querySelectorAll('sb-page header.bar .actions button')).toHaveLength(0);
  });
```

In `system.store.spec.ts:837-839` the order test becomes `'orders the bar Scan, Providers, Settings, Logs, Users'` with `['scan', 'providers', 'settings', 'logs', 'users']`.

- [ ] **Step 2: Run them to see them fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/system/users-tab.spec.ts --include src/app/workspaces/system/system.spec.ts --include src/app/stores/system.store.spec.ts --include src/app/ui/data-table/data-table.spec.ts`
Expected: FAIL — `./users-tab` does not resolve; the order tests miss `Users`; the two drawer tests fail (the drawer stays open on the removed row, and shows the old `strategy`).

- [ ] **Step 3: Make the row drawer follow its row** — `ui/data-table/data-table.ts`

In the constructor, after the `NavigationStart` subscription:

```ts
    // v207: the drawer follows its row by key. A replaced row (a status
    // change) shows its new values; a row that left `rows` (a deleted
    // account) closes the drawer instead of offering commands on it.
    effect(() => {
      const open = this.drawerRow();
      if (open === null) return;
      const key = this.rowKey()(open);
      const fresh = this.rows().find((row) => this.rowKey()(row) === key) ?? null;
      if (fresh !== open) this.drawerRow.set(fresh);
    });
```

- [ ] **Step 4: Add the tab to System**

- `system.store.ts`: `SYSTEM_TABS = ['scan', 'providers', 'settings', 'logs', 'users'] as const` (doc comment: v207 adds Users last; Settings stays the landing tab); in `resolveTab` add `users: () => of(undefined)` with the comment "the Users tab owns its store and loads on mount (V207-17)".
- `system.ts`: `{ id: 'users', label: 'Users' }` last in `TABS`; `users: null` in `TAB_ACTION` (its commands are per row); `UsersTab` in `imports`; `@case ('users') { <sb-users-tab /> }` in the `@switch`. `refreshOnSystem` needs no change: no event moves the Users list.
- `frontend/scripts/layout-audit-lib.mjs`: `'/system?tab=users'` after `'/system?tab=providers'`; in `layout-audit-lib.test.mjs` the title's `(29)` and `assert.equal(ROUTES.length, 29)` become 30.

- [ ] **Step 5: Write `frontend/src/app/workspaces/system/users-tab.ts`**

Module doc comment: spec v207 § SPA "Users page"; admin-only (route guard + server prefix); the `.env` admin is never listed and cannot be changed here; the bin is a per-row command with its own confirm, so it stays in its row.

```ts
export const deleteConsequence = (name: string): string =>
  `${name} can no longer sign in, and any session they have open ends now. The account cannot be restored: create it again to give them access back.`;

export const lastSignIn = (iso: string | null): string => (iso ? dateTime(iso) : 'Never');

const USER_COLUMNS: ColumnDef<AdminUser>[] = [
  { key: 'username', header: 'Username', value: (u) => u.username, compact: { line: 1, order: 1 } },
  { key: 'status', header: 'Status', value: (u) => (u.disabled ? 'Disabled' : 'Active'), compact: { line: 1, order: 2 } },
  { key: 'last_login_at', header: 'Last sign-in', value: (u) => lastSignIn(u.last_login_at), compact: { line: 2, order: 1 } },
  { key: 'created_at', header: 'Created', value: (u) => date(u.created_at) },
  { key: 'actions', header: 'Actions' },
];
```

`UsersTab`: `sb-users-tab`, OnPush, `providers: [UsersStore]`, imports `Panel, DataTable, Button, Icon, ConfirmDialog` (`date`, `dateTime` from `ui/format`; `ColumnDef`, `EmptyState`, `RowContext` from `ui/data-table/data-table.types`). Template:

```html
<sb-panel heading="Viewer accounts"
          description="Read-only sign-ins. A viewer sees Dashboard, Trades, Watchlist, Risk and Insights, never System, and can change nothing. The .env admin is not listed and cannot be changed here.">
  @if (store.notice(); as text) { <p class="notice" role="status">{{ text }}</p> }
  @if (store.actionError(); as text) { <p class="problem" role="alert">{{ text }}</p> }
  @if (store.status() === 'error') {
    <p class="problem" role="alert">
      {{ store.error() }}
      <button sb-button variant="ghost" type="button" data-action="retry" (click)="store.load()">Retry</button>
    </p>
  }
  <sb-data-table [rows]="store.users()" [columns]="columns()" [visible]="visible" [rowKey]="rowKey"
                 [loading]="store.status() === 'loading'" [emptyState]="empty" clientPaging="system-users" />
</sb-panel>

<ng-template #actionsCell let-user>
  <span class="row-actions">
    <button sb-button variant="ghost" type="button" data-action="toggle-disabled" [loading]="store.busy() === user.id"
            [attr.aria-label]="(user.disabled ? 'Enable ' : 'Disable ') + user.username" (click)="toggle(user)">
      {{ user.disabled ? 'Enable' : 'Disable' }}
    </button>
    <button sb-button variant="danger-icon" type="button" class="sb-hit" data-action="delete"
            [attr.aria-label]="'Delete ' + user.username" (click)="deleting.set(user)"><sb-icon name="trash" /></button>
  </span>
</ng-template>

<sb-confirm-dialog [open]="deleting() !== null" [title]="'Delete ' + (deleting()?.username ?? '')"
                   [consequence]="deleteText()" confirmLabel="Delete" [working]="store.busy() !== null"
                   (confirmed)="confirmDelete()" (cancelled)="deleting.set(null)" />
```

Class members: `store = inject(UsersStore)`; `visible = USER_COLUMNS.map((c) => c.key)`; `rowKey = (u: AdminUser) => String(u.id)`; `empty: EmptyState` (title and hint from Layout above); `deleting = signal<AdminUser | null>(null)`; `deleteText = computed(() => { const u = this.deleting(); return u ? deleteConsequence(u.username) : ''; })`; `actionsCell = viewChild.required<TemplateRef<RowContext<AdminUser>>>('actionsCell')`; `columns = computed(() => USER_COLUMNS.map((c) => (c.key === 'actions' ? { ...c, cell: this.actionsCell() } : c)))`; the constructor calls `this.store.load()`. Methods:
- `toggle(user)`: `void this.store.setDisabled(user, !user.disabled)`.
- `async confirmDelete()`: read `deleting()` (null → return); `await this.store.remove(user)`; `this.deleting.set(null)` whatever the result (a failure shows in the panel's alert line).

Styles: `:host { display: block; }`, `.row-actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8); }`, `.row-actions button { min-height: var(--control-h); }`, `.notice { color: var(--text-secondary); }`, `.problem { color: var(--neg); display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }`. Never write `compact-row`, `compact-hit` or `drawer-fields` in this file, not even in a comment: `workspace-consistency.spec.ts` reads those as a hand-built card.

- [ ] **Step 6: Run the specs to see them pass**

Run: the Step 2 command plus `--include src/app/workspaces/workspace-consistency.spec.ts --include src/app/auth/write-calls.spec.ts`, then `node --test "<wt>/frontend/scripts/layout-audit-lib.test.mjs"`.
Expected: PASS, `0 failed` in both. A `workspace-consistency` failure on the bin means its variant drifted from `danger-icon`. The three-width layout audit runs in V207-17b, once the page is complete.

- [ ] **Step 7: Commit**

```bash
cd "<wt>" && git add frontend/src/app/workspaces/system/users-tab.ts frontend/src/app/workspaces/system/users-tab.spec.ts frontend/src/app/stores/system.store.ts frontend/src/app/stores/system.store.spec.ts frontend/src/app/workspaces/system/system.ts frontend/src/app/workspaces/system/system.spec.ts frontend/src/app/ui/data-table/data-table.ts frontend/src/app/ui/data-table/data-table.spec.ts frontend/scripts/layout-audit-lib.mjs frontend/scripts/layout-audit-lib.test.mjs
git commit -m "feat(v207): System -> Users tab: table and phone cards, disable and delete with confirm (V207-17)"
```

### Task V207-17b: Users tab: New viewer and Reset password dialogs, layout audit at three widths, v207 deploy section

**Model:** sonnet — one native-dialog form beside the existing `ConfirmDialog` pattern, every label and branch fixed below; the audit is mechanical.

Split from V207-17 for size; runs straight after it, same two files, then writes the deploy section as the last v207 work (Steps 8-9).

**Files:**
- Modify: `frontend/src/app/workspaces/system/users-tab.ts` (from V207-17)
- Modify: `frontend/src/app/workspaces/system/users-tab.spec.ts` (from V207-17)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (new section after `### v205: daily FX rates` :320-357, before `## Accessing the admin UI` :359)

**Interfaces:**
- Consumes: V207-17's `UsersTab` (its `#actionsCell` `.row-actions` span, `store`, the panel's alert line) and spec helpers (`mount`, `settle`, `press`, `openDialog`, `user`, `failure`, `URL`, `NO_CONTENT`); V207-16's `UsersStore.create()`, `.resetPassword()`, `.clearMessages()`, `.actionError`, `.busy`, and `PASSWORD_RULE`; for Steps 8-9, every task V207-1..V207-17 committed on the branch, revision `v207_001` and its `down_revision` (V207-1), and the repository's missing-table warning text `admin_users table missing; viewer logins are refused until alembic upgrade head` (V207-2).
- Produces: `type UserForm = { kind: 'create' } | { kind: 'reset'; user: AdminUser }`; `UserFormDialog` (selector `sb-user-form-dialog`, in `users-tab.ts`) with inputs `form: UserForm | null`, `problem: string | null`, `working: boolean` and outputs `submitted: { username: string; password: string }`, `cancelled: void`.

**Layout:** **New viewer** (primary) sits in the panel header's `panel-actions` slot on every width. **Reset password** (ghost) is the first button in each row's `.row-actions` (and so in the phone row drawer). Both open one native `<dialog>` form, `width: min(420px, calc(100vw - 2 * var(--space-20)))` so it fits 390 px, with full-width fields, the rule line under the password, the server's or the client's message in a `role="alert"` line, and Cancel / submit right-aligned and wrapping. While the dialog is open its alert line carries `actionError`, so the panel's own alert line hides (`!form()`).

- [ ] **Step 1: Write the failing tests**

Append to `users-tab.spec.ts`: import `PASSWORD_RULE` from `'../../stores/users.store'`, add `const PW = 'long-enough-pw';` beside the other constants, these two helpers below `dialogButton`, and a new `describe` after the existing one:

```ts
function type(name: string, value: string): void {
  const input = openDialog()!.querySelector<HTMLInputElement>(`input[name="${name}"]`)!;
  input.value = value;
  input.dispatchEvent(new Event('input'));
}
async function submitForm(): Promise<void> {
  openDialog()!.querySelector('form')!.dispatchEvent(new Event('submit', { cancelable: true }));
  await settle();
}

describe('System → Users dialogs (v207)', () => {
  beforeAll(() => installDialogPolyfill());

  it('creates a viewer from the dialog and closes it', async () => {
    await mount([]);
    await press('[data-action="new-viewer"]');
    expect(openDialog()!.querySelector('h2')!.textContent!.trim()).toBe('New viewer');
    type('username', 'bob');
    type('password', PW);
    await submitForm();
    const req = backend.expectOne({ method: 'POST', url: URL });
    expect(req.request.body).toEqual({ username: 'bob', password: PW });
    req.flush(user({ id: 2, username: 'bob' }), { status: 201, statusText: 'Created' });
    await settle();
    expect(openDialog()).toBeNull();
    expect(q('tbody')!.textContent).toContain('bob');
    expect(q('[role="status"]')!.textContent).toContain('Created viewer bob.');
  });

  it('keeps the dialog and the typed name on a 409, and says why', async () => {
    await mount([user()]);
    await press('[data-action="new-viewer"]');
    type('username', 'Alice');
    type('password', PW);
    await submitForm();
    backend.expectOne({ method: 'POST', url: URL }).flush(...failure('conflict', 409, 'username is already taken.'));
    await settle();
    expect(openDialog()).toBeTruthy();
    expect(openDialog()!.querySelector('[role="alert"]')!.textContent).toContain('names are case-insensitive');
    expect(openDialog()!.querySelector<HTMLInputElement>('input[name="username"]')!.value).toBe('Alice');
    expect(el().querySelectorAll('[role="alert"]')).toHaveLength(1);
  });

  it('refuses a short password in the dialog without a request', async () => {
    await mount([]);
    await press('[data-action="new-viewer"]');
    type('username', 'bob');
    type('password', 'short');
    await submitForm();
    backend.expectNone({ method: 'POST', url: URL });
    expect(openDialog()!.querySelector('[role="alert"]')!.textContent!.trim()).toBe(PASSWORD_RULE);
  });

  it('opens empty again after Cancel, with no stale error', async () => {
    await mount([]);
    await press('[data-action="new-viewer"]');
    type('username', 'b b');
    type('password', PW);
    await submitForm();
    dialogButton('Cancel').click();
    await settle();
    expect(openDialog()).toBeNull();
    await press('[data-action="new-viewer"]');
    expect(openDialog()!.querySelector<HTMLInputElement>('input[name="username"]')!.value).toBe('');
    expect(openDialog()!.querySelector('[role="alert"]')).toBeNull();
  });

  it('resets a password from the row, naming the account, with no username field', async () => {
    await mount([user()]);
    await press('[data-action="reset-password"]');
    expect(openDialog()!.querySelector('h2')!.textContent!.trim()).toBe('Reset password for alice');
    expect(openDialog()!.querySelector('input[name="username"]')).toBeNull();
    expect(openDialog()!.textContent).toContain('Saving signs this viewer out everywhere.');
    type('password', PW);
    await submitForm();
    const req = backend.expectOne({ method: 'POST', url: `${URL}/1/password` });
    expect(req.request.body).toEqual({ password: PW });
    req.flush(null, NO_CONTENT);
    await settle();
    expect(openDialog()).toBeNull();
    expect(q('[role="status"]')!.textContent).toContain('Password reset for alice.');
  });

  it('offers Reset password in the phone row drawer too', async () => {
    await mount([user()], true);
    openRowDrawer(q('sb-data-table')!);
    await settle();
    expect(q('sb-drawer.row-drawer [data-action="reset-password"]')).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/system/users-tab.spec.ts`
Expected: FAIL — the new tests find no `[data-action="new-viewer"]` / `[data-action="reset-password"]`; V207-17's tests still pass.

- [ ] **Step 3: Add `UserFormDialog` to `users-tab.ts`**

`sb-user-form-dialog`, OnPush, imports `Button, ControlRow, FocusTrap, TextInput` (`ControlRow` from `ui/layout`, `FocusTrap` from `ui/focus-trap`, `TextInput` from `ui/form-controls`). Members: the inputs and outputs from Interfaces, `protected readonly username = signal('')`, `protected readonly password = signal('')`, `private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog')`. Template:

```html
<dialog #dialog class="elev-overlay" (close)="form() && cancelled.emit()">
  @if (form(); as f) {
    <form sbFocusTrap (submit)="$event.preventDefault(); send()">
      <h2>{{ f.kind === 'create' ? 'New viewer' : 'Reset password for ' + f.user.username }}</h2>
      @if (f.kind === 'create') {
        <sb-text-input label="Username" name="username" autocomplete="off" [(value)]="username" />
      }
      <sb-text-input [label]="f.kind === 'create' ? 'Password' : 'New password'" type="password"
                     name="password" autocomplete="new-password" [(value)]="password" />
      <p class="rule">At least 12 characters.{{ f.kind === 'reset' ? ' Saving signs this viewer out everywhere.' : '' }}</p>
      @if (problem(); as text) { <p class="problem" role="alert">{{ text }}</p> }
      <sb-control-row class="actions">
        <button sb-button variant="ghost" type="button" (click)="cancelled.emit()">Cancel</button>
        <button sb-button variant="primary" type="submit" data-action="submit-user" [loading]="working()">
          {{ f.kind === 'create' ? 'Create viewer' : 'Reset password' }}
        </button>
      </sb-control-row>
    </form>
  }
</dialog>
```

The constructor's `effect` mirrors `ConfirmDialog`'s: when `form()` is non-null and the element is closed, clear both fields inside `untracked` and call `showModal()`; when `form()` is null and the element is open, `close()`. The fields clear only on opening, so a failed submit keeps what was typed. `send()` emits `{ username: this.username(), password: this.password() }`. Escape fires the native `close` while `form()` is still set, so it emits `cancelled`; the parent's own close comes after `form` is null and emits nothing. Styles: the width above, `padding: var(--space-20)`, `color: var(--text)`, `dialog::backdrop { background: var(--scrim); }`, `form { display: grid; gap: var(--space-10); }`, `sb-text-input { display: block; }`, `.rule { color: var(--text-secondary); font-size: var(--text-table); }`, `.problem { color: var(--neg); }`, `.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; }`.

- [ ] **Step 4: Wire it into `UsersTab`**

- Add `UserFormDialog` to `imports`; add `protected readonly form = signal<UserForm | null>(null)`.
- In `<sb-panel>`, first child: `<button panel-actions sb-button variant="primary" type="button" data-action="new-viewer" (click)="openCreate()">New viewer</button>`.
- The panel's alert line becomes `@if (!form() && store.actionError(); as text)`.
- First in `.row-actions`: `<button sb-button variant="ghost" type="button" data-action="reset-password" [attr.aria-label]="'Reset password for ' + user.username" (click)="openReset(user)">Reset password</button>`.
- After the `<ng-template>`: `<sb-user-form-dialog [form]="form()" [problem]="store.actionError()" [working]="store.busy() !== null" (submitted)="submit($event)" (cancelled)="closeForm()" />`.
- Methods:
  - `openCreate()` / `openReset(user)`: `this.store.clearMessages()`, then `this.form.set({ kind: 'create' })` / `this.form.set({ kind: 'reset', user })`.
  - `closeForm()`: `this.form.set(null)` and `this.store.clearMessages()`, so a refusal shown in the dialog does not reappear in the panel.
  - `async submit({ username, password })`: read `this.form()` (null → return); `const ok = f.kind === 'create' ? await this.store.create(username, password) : await this.store.resetPassword(f.user, password)`; `if (ok) this.form.set(null)` (the success notice stays).

- [ ] **Step 5: Run the specs to see them pass**

Run: `node "<wt>/frontend/scripts/ng-test.mjs" "<wt>/frontend" --include src/app/workspaces/system/users-tab.spec.ts --include src/app/workspaces/system/system.spec.ts --include src/app/workspaces/workspace-consistency.spec.ts --include src/app/auth/write-calls.spec.ts`
Expected: PASS, `0 failed`.

- [ ] **Step 6: Audit the page at 390, 768 and 1440**

Run `/replicate-prod-db` first if no task in this session has, then `cd "<wt>" && python -m alembic upgrade head` (local replica only: it creates `admin_users`). Then `cd "<wt>/frontend" && npm run build`, start `python "<wt>/admin_ui.py"` in the background, and sign in once with `node "<wt>/frontend/scripts/browse.mjs" login --base http://localhost:1234` (it reads `.env`; never print it). At `/system?tab=users`, create two throwaway viewers through New viewer: `audit-viewer-1` and a 64-character name (`a` × 64); disable one. Then:

```bash
node "<wt>/frontend/scripts/layout-audit.mjs" --base http://localhost:1234
```

Expected: exit 0 at 390, 768 and 1440, `/system?tab=users` included. Fix a finding in `users-tab.ts`, never in `layout-audit.allow.json`. Read at most 4 clipped shots, e.g. `node "<wt>/frontend/scripts/browse.mjs" shots --path "/system?tab=users" --widths 390 --clip "sb-users-tab"` and the same at 768 and 1440, plus one of the open dialog at 390 (`--clip "sb-user-form-dialog dialog"` after opening it): one card per account at 390, the table at 768 and 1440, no horizontal page scroll, the long name wrapped, the dialog inside the viewport with 44 px buttons. Delete both throwaway viewers from the page, then stop the server.

- [ ] **Step 7: Commit**

```bash
cd "<wt>" && git add frontend/src/app/workspaces/system/users-tab.ts frontend/src/app/workspaces/system/users-tab.spec.ts
git commit -m "feat(v207): Users tab: New viewer and Reset password dialogs, audited at 390/768/1440 (V207-17b)"
```

# Phase H — release


Steps 8-9 were V207-18's deploy-doc steps, folded in to keep the plan at 20 tasks. The version bump and `version_history.json` regeneration are **not** a plan task: `/close-out` Steps 3-4 do both from the index `Bump:` line (ui minor, bot minor). This task does not merge, push or deploy, and runs no full suite.

- [ ] **Step 8: Check the preconditions for the deploy section**

```bash
git -C "<wt>" log --oneline main..HEAD
git -C "<wt>" status --short
cd "<wt>" && python scripts/dev/complexity_gate.py
grep -n "^down_revision" "<wt>/swingbot/core/db/migrations/versions/v207_001_admin_users.py"
```

Expected: commits for V207-1, 2, 3, 4, 4b, 5, 5b, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17 and 17b; a clean status; the complexity gate passes; `down_revision = "<rev>"` (`v205_001` when this plan was written). Keep `<rev>` for Step 9. A missing task: stop and report which one.

- [ ] **Step 9: Write the v207 section in `docs/deploy/DEPLOY_HETZNER.md`**

Insert this block after the v205 section's closing "Rollback, in this order" paragraph and before `## Accessing the admin UI`, with `<rev>` from Step 8 in place of `v205_001` if it differs:

````markdown
### v207: viewer accounts (`admin_users`)

Read-only sign-ins, for people who may look at the book but change nothing,
are rows in `admin_users` (revision `v207_001`). The `.env` admin is
unchanged and never stored, so it cannot be locked out. No `.env` change and
no flag: an empty table is exactly the behaviour before v207.

1. Deploy as usual. `deploy.sh` runs `alembic upgrade head` after
   `up --wait`; until it has, a viewer sign-in answers "Invalid username or
   password.", the admin logs `admin_users table missing; viewer logins are
   refused until alembic upgrade head` once, the Users tab lists nobody and
   creating a viewer fails. The `.env` admin signs in normally throughout.
2. Check the revision:
   `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot alembic current"`
   prints `v207_001 (head)` or a later head.
3. Create the first viewer: sign in at bomeo-capital.com as the `.env`
   admin, open System → Users (`/system?tab=users`), choose **New viewer**,
   and enter a username (3-64 characters: letters, digits, `.`, `_`, `-`;
   never the admin's own name) and a password of at least 12 characters.
   Hand both over a private channel. Viewers are managed only on this page:
   there is no CLI and no `.env` list.
4. Check it in a private browser window: sign in with the new account. The
   header shows `Read-only · <name>`, the rail has no System entry, no write
   control is shown, and opening `/system` lands on the Dashboard. Sign out.
5. To revoke access, use **Disable** (reversible) or **Delete** on the same
   tab. Either one, like a password reset, ends the viewer's sessions on
   their next request and their live event stream within one heartbeat
   (20 s). Re-enabling a disabled viewer does not revive old sessions: they
   sign in again.

Rollback, in this order: (1) redeploy the previous image (§ Rolling back).
The old code never reads `admin_users`, so the table can stay and viewer
accounts survive a later roll-forward; until then only the `.env` admin can
sign in. (2) Only to remove it, run
`docker compose exec -T bot alembic downgrade <the revision v207_001 revises>`
(`v205_001` when v207 was written). This **drops `admin_users` and every
viewer account**, and also rolls back every later revision stacked on top of
`v207_001`, so check `alembic history` first.
````

Then:

```bash
git -C "<wt>" diff --stat
git -C "<wt>" add docs/deploy/DEPLOY_HETZNER.md
git -C "<wt>" commit -m "docs(v207): DEPLOY_HETZNER v207 section -- migration, first viewer, revoke, rollback (V207-17b)"
```

Expected: the diff touches only `docs/deploy/DEPLOY_HETZNER.md`, and the new heading sits between `### v205: daily FX rates` and `## Accessing the admin UI` (`grep -n "^### v20[57]\|^## Accessing" "<wt>/docs/deploy/DEPLOY_HETZNER.md"` prints them in that order).
