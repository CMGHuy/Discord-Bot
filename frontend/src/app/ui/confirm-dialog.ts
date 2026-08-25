import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';

import { Button } from './button';
import { ControlRow } from './layout';

/**
 * The gate in front of every destructive action — close, cancel, delete,
 * clear-open, the killswitch.
 *
 * **`consequence` is required, and it is the point of the component.** Spec
 * v14: the dialog must name what is being destroyed, not ask "are you sure?".
 * These act on paper-trade history that has no undo and no backup, and "Are
 * you sure?" is answered yes reflexively by anyone who has seen it twice. A
 * sentence naming the specific trade, and what will not come back, is the only
 * part of this component doing any work. Making it a required input means a
 * call site cannot omit it and get a generic dialog.
 *
 * Built on `<dialog>`: the browser supplies the top layer, the backdrop, focus
 * trapping, the Escape key and the inert background. A div-plus-overlay
 * re-implements all five and typically gets focus trapping wrong.
 */
@Component({
  selector: 'sb-confirm-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow],
  template: `
    <dialog #dialog class="elev-overlay" (close)="cancelled.emit()" (cancel)="cancelled.emit()">
      <h2>{{ title() }}</h2>
      <p class="consequence">{{ consequence() }}</p>

      <sb-control-row class="actions">
        <button sb-button variant="ghost" type="button" (click)="close()">
          {{ cancelLabel() }}
        </button>
        <button
          sb-button
          [variant]="destructive() ? 'danger' : 'primary'"
          type="button"
          [loading]="working()"
          (click)="confirmed.emit()"
        >
          {{ confirmLabel() }}
        </button>
      </sb-control-row>
    </dialog>
  `,
  styles: `
    dialog {
      max-width: 380px;
      padding: var(--space-20);
      color: var(--text);
    }
    dialog::backdrop { background: var(--scrim); }

    h2 { font-size: var(--text-subhead); font-weight: 600; }
    .consequence {
      margin-top: var(--space-8);
      color: var(--text-secondary);
      font-size: var(--text-body);
      line-height: 1.5;
    }
    /* sb-control-row supplies alignment, wrap and gap; only the right-hand
       justification and the standoff from the consequence line are this
       dialog's own. display:flex stays because sb-control-row's host is an
       inline element -- an inline box ignores justify-content outright, and
       the buttons would sit left. */
    .actions {
      display: flex;
      justify-content: flex-end;
      margin-top: var(--space-20);
    }
  `,
})
export class ConfirmDialog {
  readonly open = input(false);
  readonly title = input.required<string>();
  /** What this will do, named specifically. Not "Are you sure?" — see above. */
  readonly consequence = input.required<string>();
  readonly confirmLabel = input('Confirm');
  readonly cancelLabel = input('Cancel');
  /** Paints the confirm button `danger`. Default true: everything routed
   *  through this dialog is destructive, and a caller that wants the softer
   *  variant should have to say so. */
  readonly destructive = input(true);
  /** The command is in flight — the confirm button locks so it cannot be
   *  sent twice. */
  readonly working = input(false);

  readonly confirmed = output<void>();
  readonly cancelled = output<void>();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      // showModal() twice throws, and close() on a closed dialog fires a
      // spurious `close` event that would look like a cancellation.
      if (this.open() && !element.open) element.showModal();
      else if (!this.open() && element.open) element.close();
    });
  }

  protected close(): void {
    // Emits `cancelled` through the dialog's own close event, so dismissing
    // with Escape and pressing Cancel take exactly one path.
    this.dialog().nativeElement.close();
  }
}
