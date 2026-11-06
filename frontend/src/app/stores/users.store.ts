/**
 * The Users tab's store (spec v207 § SPA). Admin-only by route (`adminGuard`)
 * and by server (`/api/v1/users` is an admin-only prefix). The client-side
 * rules only save a round trip; the server stays the authority. Mutations
 * return a `Promise<boolean>` so a dialog closes only on success and keeps
 * what was typed otherwise.
 *
 * Not provided in root: the Users tab provides it, so its list lives exactly
 * as long as the tab.
 */
import { inject } from '@angular/core';
import { patchState, signalStore, withMethods, withState } from '@ngrx/signals';
import { Observable, catchError, lastValueFrom, map, of } from 'rxjs';

import { ApiClient } from '../api/api-client';
import { ApiError } from '../api/api-error';
import { AdminUser } from '../api/models';

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

export type UsersStatus = 'idle' | 'loading' | 'ready' | 'error';
export type UsersBusy = 'create' | number | null;

interface UsersSlice {
  users: AdminUser[];
  status: UsersStatus;
  error: string | null;
  busy: UsersBusy;
  notice: string | null;
  actionError: string | null;
}

const initial: UsersSlice = { users: [], status: 'idle', error: null, busy: null, notice: null, actionError: null };

export const UsersStore = signalStore(
  withState(initial),
  withMethods((store, api = inject(ApiClient)) => {
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

    return {
      load(): void {
        patchState(store, { status: 'loading' });
        api.listUsers().subscribe({
          next: (users) => patchState(store, { users: [...users].sort(byId), status: 'ready', error: null }),
          error: (e: ApiError) => patchState(store, {
            status: 'error',
            error: e.code === 'unavailable' ? 'The admin is not responding.' : e.message,
          }),
        });
      },
      create(username: string, password: string): Promise<boolean> {
        const name = username.trim();
        const problem = usernameProblem(name) ?? passwordProblem(password);
        if (problem) return refuse(problem);
        return run('create', { username: name }, api.createUser({ username: name, password }), (made) =>
          patchState(store, { users: [...store.users(), made].sort(byId), notice: `Created viewer ${made.username}.` }));
      },
      setDisabled(user: AdminUser, disabled: boolean): Promise<boolean> {
        return run(user.id, user, api.setUserDisabled(user.id, disabled), (row) => {
          swap(row);
          patchState(store, {
            notice: disabled ? `Disabled ${user.username}. ${SESSIONS_ENDED}` : `Enabled ${user.username}.`,
          });
        });
      },
      resetPassword(user: AdminUser, password: string): Promise<boolean> {
        const problem = passwordProblem(password);
        if (problem) return refuse(problem);
        return run(user.id, user, api.resetUserPassword(user.id, password), () =>
          patchState(store, { notice: `Password reset for ${user.username}. ${SESSIONS_ENDED}` }));
      },
      remove(user: AdminUser): Promise<boolean> {
        return run(user.id, user, api.deleteUser(user.id), () => {
          drop(user.id);
          patchState(store, { notice: `Deleted ${user.username}.` });
        });
      },
      clearMessages(): void {
        patchState(store, { notice: null, actionError: null });
      },
    };
  }),
);
