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
// The last open dialog: on a phone the row drawer is open too, and the confirm
// dialog it raised sits after it in the DOM.
const openDialog = () => [...el().querySelectorAll<HTMLDialogElement>('dialog[open]')].at(-1) ?? null;
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
