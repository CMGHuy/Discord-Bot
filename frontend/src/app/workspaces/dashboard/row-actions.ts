import {
  ChangeDetectionStrategy, Component, ElementRef, computed, inject, input, output, signal,
} from '@angular/core';
import { Router } from '@angular/router';

import { ApiClient } from '../../api/api-client';
import { TradeRow } from '../../api/models';
import { Button } from '../../ui/button';
import { Icon } from '../../ui/icon';

const CLOSEABLE = new Set(['ACTIVE', 'PARTIAL']);

/**
 * Per-row actions — v85 D13.
 *
 * Each item's precondition mirrors its endpoint's, so the menu cannot offer a
 * command the server will refuse: close is ACTIVE/PARTIAL only, cancel is
 * PENDING only. Delete is absent entirely — `delete_trade` rejects plan-backed
 * rows with a 422, and every row on this page is plan-backed.
 */
@Component({
  selector: 'sb-row-actions',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Icon],
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown.escape)': 'close()',
  },
  template: `
    <button sb-button variant="icon" type="button" class="trigger"
            [attr.aria-expanded]="open()" aria-haspopup="menu"
            aria-label="Row actions" (click)="toggle($event)">
      <sb-icon name="more" />
    </button>

    @if (open()) {
      <div class="menu elev-overlay" role="menu">
        @if (canClose()) {
          <button sb-button variant="ghost" role="menuitem" type="button"
                  (click)="run('close')">Close position</button>
        }
        @if (canCancel()) {
          <button sb-button variant="ghost" role="menuitem" type="button"
                  (click)="run('cancel')">Cancel plan</button>
        }
        <button sb-button variant="ghost" role="menuitem" type="button"
                (click)="run('note')">Add note</button>
      </div>
    }
  `,
  styles: `
    :host { position: relative; display: inline-flex; }
    .menu {
      position: absolute; top: calc(100% + var(--space-4)); right: 0; z-index: 20;
      min-width: 160px; display: flex; flex-direction: column; gap: var(--space-4);
      padding: var(--space-6);
    }
    .menu button { justify-content: flex-start; font-size: var(--text-table); }
  `,
})
export class RowActions {
  private readonly api = inject(ApiClient);
  private readonly router = inject(Router);
  private readonly host: ElementRef<HTMLElement> = inject(ElementRef);

  readonly row = input.required<TradeRow>();
  readonly done = output<void>();

  protected readonly open = signal(false);
  protected readonly canClose = computed(() =>
    CLOSEABLE.has((this.row().status ?? '').toUpperCase()));
  protected readonly canCancel = computed(() =>
    (this.row().status ?? '').toUpperCase() === 'PENDING');

  protected toggle(event: MouseEvent): void {
    event.stopPropagation();
    this.open.update((v) => !v);
  }

  protected close(): void {
    if (!this.open()) return;
    this.open.set(false);
    this.host.nativeElement.querySelector<HTMLElement>('.trigger')?.focus();
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) this.close();
  }

  protected run(action: 'close' | 'cancel' | 'note'): void {
    const id = this.row().id;
    this.close();
    if (action === 'note') {
      // The note editor already exists on Trade detail (a plain always-shown
      // textarea, no separate "open editor" state) -- this navigates there
      // rather than growing a second editor with its own save path.
      void this.router.navigate(['/trades', id]);
      return;
    }
    const call = action === 'close' ? this.api.closeTrade(id) : this.api.cancelTrade(id);
    call.subscribe({ next: () => this.done.emit(), error: () => this.done.emit() });
  }
}
