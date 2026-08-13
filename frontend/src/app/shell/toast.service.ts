import { Injectable, signal } from '@angular/core';

export type ToastKind = 'info' | 'warn' | 'error';

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

/**
 * Transient feedback for commands: "Scan triggered", "Could not close trade".
 *
 * Root-level and shell-rendered so a toast raised by a workspace survives
 * navigating away from it -- a confirmation that disappears because the user
 * moved on is a confirmation they never got.
 */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private next = 1;
  private readonly items = signal<Toast[]>([]);

  readonly toasts = this.items.asReadonly();

  show(message: string, kind: ToastKind = 'info', ms = 4000): number {
    const id = this.next++;
    this.items.update((list) => [...list, { id, kind, message }]);
    // Errors stay until dismissed. An error that vanishes on its own is one
    // the user can neither read twice nor act on, and the actions here move
    // money-shaped state.
    if (kind !== 'error') {
      setTimeout(() => this.dismiss(id), ms);
    }
    return id;
  }

  dismiss(id: number): void {
    this.items.update((list) => list.filter((t) => t.id !== id));
  }
}
