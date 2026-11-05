import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  signal,
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
import { Panel } from '../../ui/layout';

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

@Component({
  selector: 'sb-users-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [UsersStore],
  imports: [Panel, DataTable, Button, Icon, ConfirmDialog],
  template: `
    <sb-panel
      heading="Viewer accounts"
      description="Read-only sign-ins. A viewer sees Dashboard, Trades, Watchlist, Risk and Insights, never System, and can change nothing. The .env admin is not listed and cannot be changed here."
    >
      @if (store.notice(); as text) {
        <p class="notice" role="status">{{ text }}</p>
      }
      @if (store.actionError(); as text) {
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

    <ng-template #actionsCell let-user>
      <span class="row-actions">
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
  `,
  styles: `
    :host {
      display: block;
    }
    .row-actions {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-8);
    }
    .row-actions button {
      min-height: var(--control-h);
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
  protected readonly deleteText = computed(() => {
    const u = this.deleting();
    return u ? deleteConsequence(u.username) : '';
  });
  private readonly actionsCell = viewChild.required<TemplateRef<RowContext<AdminUser>>>('actionsCell');
  protected readonly columns = computed(() =>
    USER_COLUMNS.map((c) => (c.key === 'actions' ? { ...c, cell: this.actionsCell() } : c)),
  );

  constructor() {
    this.store.load();
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
