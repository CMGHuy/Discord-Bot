import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';

import { AdminUser } from '../../api/models';
import { UsersStore } from '../../stores/users.store';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState, RowContext } from '../../ui/data-table/data-table.types';
import { date, dateTime } from '../../ui/format';
import { Icon } from '../../ui/icon';
import { FocusTrap } from '../../ui/focus-trap';
import { TextInput } from '../../ui/form-controls';
import { ControlRow, Panel } from '../../ui/layout';

/**
 * System → Users (spec v207 § SPA "Users page"): the viewer accounts, one
 * row each. Admin-only twice over (the `adminGuard` on `/system` and the
 * server's admin-only `/api/v1/users` prefix). The `.env` admin is never
 * listed and cannot be changed here. The bin is a per-row command with its
 * own confirm, so it stays in its row, not in the page header.
 */
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

export type UserForm = { kind: 'create' } | { kind: 'reset'; user: AdminUser };

@Component({
  selector: 'sb-user-form-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow, FocusTrap, TextInput],
  template: `
    <dialog #dialog class="elev-overlay" (close)="form() && cancelled.emit()">
      @if (form(); as f) {
        <form sbFocusTrap (submit)="$event.preventDefault(); send()">
          <h2>{{ f.kind === 'create' ? 'New viewer' : 'Reset password for ' + f.user.username }}</h2>
          @if (f.kind === 'create') {
            <sb-text-input label="Username" name="username" autocomplete="off" [(value)]="username" />
          }
          <sb-text-input
            [label]="f.kind === 'create' ? 'Password' : 'New password'"
            type="password"
            name="password"
            autocomplete="new-password"
            [(value)]="password"
          />
          <p class="rule">At least 12 characters.{{ f.kind === 'reset' ? ' Saving signs this viewer out everywhere.' : '' }}</p>
          @if (problem(); as text) {
            <p class="problem" role="alert">{{ text }}</p>
          }
          <sb-control-row class="actions">
            <button sb-button variant="ghost" type="button" (click)="cancelled.emit()">Cancel</button>
            <button sb-button variant="primary" type="submit" data-action="submit-user" [loading]="working()">
              {{ f.kind === 'create' ? 'Create viewer' : 'Reset password' }}
            </button>
          </sb-control-row>
        </form>
      }
    </dialog>
  `,
  styles: `
    dialog {
      width: min(420px, calc(100vw - 2 * var(--space-20)));
      padding: var(--space-20);
      color: var(--text);
    }
    dialog::backdrop {
      background: var(--scrim);
    }
    form {
      display: grid;
      gap: var(--space-10);
    }
    sb-text-input {
      display: block;
    }
    .rule {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .problem {
      color: var(--neg);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
  `,
})
export class UserFormDialog {
  readonly form = input<UserForm | null>(null);
  readonly problem = input<string | null>(null);
  readonly working = input(false);
  readonly submitted = output<{ username: string; password: string }>();
  readonly cancelled = output<void>();
  protected readonly username = signal('');
  protected readonly password = signal('');
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      const open = this.form() !== null;
      if (open && !element.open) {
        untracked(() => {
          this.username.set('');
          this.password.set('');
        });
        element.showModal();
      } else if (!open && element.open) element.close();
    });
  }

  protected send(): void {
    this.submitted.emit({ username: this.username(), password: this.password() });
  }
}

@Component({
  selector: 'sb-users-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [UsersStore],
  imports: [Panel, DataTable, Button, Icon, ConfirmDialog, UserFormDialog],
  template: `
    <sb-panel
      heading="Viewer accounts"
      description="Read-only sign-ins. A viewer sees Dashboard, Trades, Watchlist, Risk and Insights, never System, and can change nothing. The .env admin is not listed and cannot be changed here."
    >
      <button panel-actions sb-button variant="primary" type="button" data-action="new-viewer" (click)="openCreate()">
        New viewer
      </button>
      @if (store.notice(); as text) {
        <p class="notice" role="status">{{ text }}</p>
      }
      @if (!form() && store.actionError(); as text) {
        <p class="problem" role="alert">{{ text }}</p>
      }
      @if (store.status() === 'error') {
        <p class="problem" role="alert">
          {{ store.error() }}
          <button sb-button variant="ghost" type="button" data-action="retry" (click)="store.load()">Retry</button>
        </p>
      }
      <sb-data-table
        [rows]="store.users()"
        [columns]="columns()"
        [visible]="visible"
        [rowKey]="rowKey"
        [loading]="store.status() === 'loading'"
        [emptyState]="empty"
        clientPaging="system-users"
      />
    </sb-panel>

    <ng-template #nameCell let-user>
      <span class="name">{{ user.username }}</span>
    </ng-template>

    <ng-template #actionsCell let-user>
      <span class="row-actions">
        <button
          sb-button
          variant="ghost"
          type="button"
          data-action="reset-password"
          [attr.aria-label]="'Reset password for ' + user.username"
          (click)="openReset(user)"
        >
          Reset password
        </button>
        <button
          sb-button
          variant="ghost"
          type="button"
          data-action="toggle-disabled"
          [loading]="store.busy() === user.id"
          [attr.aria-label]="(user.disabled ? 'Enable ' : 'Disable ') + user.username"
          (click)="toggle(user)"
        >
          {{ user.disabled ? 'Enable' : 'Disable' }}
        </button>
        <button
          sb-button
          variant="danger-icon"
          type="button"
          class="sb-hit"
          data-action="delete"
          [attr.aria-label]="'Delete ' + user.username"
          (click)="deleting.set(user)"
        >
          <sb-icon name="trash" />
        </button>
      </span>
    </ng-template>

    <sb-confirm-dialog
      [open]="deleting() !== null"
      [title]="'Delete ' + (deleting()?.username ?? '')"
      [consequence]="deleteText()"
      confirmLabel="Delete"
      [working]="store.busy() !== null"
      (confirmed)="confirmDelete()"
      (cancelled)="deleting.set(null)"
    />
    <sb-user-form-dialog
      [form]="form()"
      [problem]="store.actionError()"
      [working]="store.busy() !== null"
      (submitted)="submit($event)"
      (cancelled)="closeForm()"
    />
  `,
  styles: `
    :host {
      display: block;
    }
    .name {
      overflow-wrap: anywhere;
    }
    .row-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-8);
    }
    .row-actions button {
      min-height: var(--control-h);
      flex: none;
      white-space: nowrap;
    }
    @media (min-width: 640px) {
      /* In the table the actions stay on one line; the name column gives way. */
      .row-actions {
        flex-wrap: nowrap;
      }
    }
    .notice {
      color: var(--text-secondary);
    }
    .problem {
      color: var(--neg);
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      gap: var(--space-8);
    }
  `,
})
export class UsersTab {
  protected readonly store = inject(UsersStore);
  protected readonly visible = USER_COLUMNS.map((c) => c.key);
  protected readonly rowKey = (u: AdminUser): string => String(u.id);
  protected readonly empty: EmptyState = {
    title: 'No viewer accounts yet',
    hint: 'New viewer creates a read-only sign-in for someone who should see the book but change nothing.',
  };
  readonly deleting = signal<AdminUser | null>(null);
  protected readonly form = signal<UserForm | null>(null);
  protected readonly deleteText = computed(() => {
    const u = this.deleting();
    return u ? deleteConsequence(u.username) : '';
  });
  private readonly nameCell = viewChild.required<TemplateRef<RowContext<AdminUser>>>('nameCell');
  private readonly actionsCell = viewChild.required<TemplateRef<RowContext<AdminUser>>>('actionsCell');
  protected readonly columns = computed(() => {
    const cells: Record<string, TemplateRef<RowContext<AdminUser>>> = {
      username: this.nameCell(),
      actions: this.actionsCell(),
    };
    return USER_COLUMNS.map((c) => (cells[c.key] ? { ...c, cell: cells[c.key] } : c));
  });

  constructor() {
    this.store.load();
  }

  protected openCreate(): void {
    this.store.clearMessages();
    this.form.set({ kind: 'create' });
  }

  protected openReset(user: AdminUser): void {
    this.store.clearMessages();
    this.form.set({ kind: 'reset', user });
  }

  protected closeForm(): void {
    this.form.set(null);
    this.store.clearMessages();
  }

  protected async submit({ username, password }: { username: string; password: string }): Promise<void> {
    const f = this.form();
    if (f === null) return;
    const ok =
      f.kind === 'create'
        ? await this.store.create(username, password)
        : await this.store.resetPassword(f.user, password);
    if (ok) this.form.set(null);
  }

  protected toggle(user: AdminUser): void {
    void this.store.setDisabled(user, !user.disabled);
  }

  protected async confirmDelete(): Promise<void> {
    const user = this.deleting();
    if (user === null) return;
    await this.store.remove(user);
    this.deleting.set(null);
  }
}
