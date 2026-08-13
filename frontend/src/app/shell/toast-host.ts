import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { ToastService } from './toast.service';

@Component({
  selector: 'sb-toast-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="host" role="status" aria-live="polite">
      @for (toast of toasts.toasts(); track toast.id) {
        <button class="toast" [class]="toast.kind" (click)="toasts.dismiss(toast.id)">
          {{ toast.message }}
        </button>
      }
    </div>
  `,
  styles: `
    .host {
      position: fixed;
      right: var(--space-20);
      bottom: var(--space-20);
      display: flex;
      flex-direction: column;
      gap: var(--space-8);
      z-index: 10;
    }
    .toast {
      padding: var(--space-8) var(--space-14);
      background: var(--surface-raised);
      border: 1px solid var(--border-strong);
      border-left-width: 2px;
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .warn { border-left-color: var(--warn); }
    .error { border-left-color: var(--neg); }
    .info { border-left-color: var(--border-strong); }
  `,
})
export class ToastHost {
  protected readonly toasts = inject(ToastService);
}
