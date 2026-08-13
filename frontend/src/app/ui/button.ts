import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost' | 'icon';

/**
 * The five button variants spec 3's inventory names, and no others.
 *
 * Applied to a NATIVE `<button>` through an attribute selector rather than
 * wrapping one in a custom element. A wrapper has to re-implement `disabled`,
 * `type="submit"`, focus, the Enter/Space keys and the accessibility tree, and
 * usually re-implements three of the five. This way the element in the DOM is
 * the button the browser already knows how to operate, and this component only
 * supplies the paint.
 *
 * `danger` is not merely a red `primary`: it is the variant every irreversible
 * action uses (close, cancel, delete, killswitch), and pairing it with
 * `ConfirmDialog` is what makes those actions hard to trigger by accident.
 */
@Component({
  selector: 'button[sb-button]',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<ng-content />`,
  host: {
    '[class]': 'classes()',
    '[attr.aria-busy]': 'loading() || null',
    '[disabled]': 'disabled() || loading() || null',
  },
  styles: `
    :host {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: var(--space-6);
      padding: var(--space-6) var(--space-14);
      border: 1px solid transparent;
      border-radius: var(--radius);
      font-family: var(--font-sans);
      font-size: var(--text-table);
      font-weight: 600;
      cursor: pointer;
      transition: background var(--transition), border-color var(--transition),
        color var(--transition);
    }
    :host(:focus-visible) { outline: 1px solid var(--accent); outline-offset: 2px; }
    :host([disabled]) { opacity: 0.45; cursor: default; }

    /* Blue is interactive-only, which is exactly what a primary button is --
       the one place the accent is allowed to carry weight. */
    :host(.primary) { background: var(--accent); color: #001428; }
    :host(.primary:not([disabled]):hover) { background: color-mix(in srgb, var(--accent) 85%, white); }

    :host(.secondary) {
      background: var(--surface-raised);
      border-color: var(--border-strong);
      color: var(--text);
    }
    :host(.secondary:not([disabled]):hover) { border-color: var(--text-muted); }

    /* Red here is not P&L -- it is the one sanctioned exception, because an
       irreversible control that does not look dangerous is worse than a
       colour rule kept perfectly. */
    :host(.danger) {
      background: transparent;
      border-color: var(--neg);
      color: var(--neg);
    }
    :host(.danger:not([disabled]):hover) { background: color-mix(in srgb, var(--neg) 14%, transparent); }

    :host(.ghost) { background: transparent; color: var(--text-secondary); }
    :host(.ghost:not([disabled]):hover) { color: var(--text); background: var(--surface-raised); }

    :host(.icon) {
      padding: var(--space-4);
      background: transparent;
      color: var(--text-muted);
      line-height: 1;
    }
    :host(.icon:not([disabled]):hover) { color: var(--text); background: var(--surface-raised); }
  `,
})
export class Button {
  readonly variant = input<ButtonVariant>('secondary');
  readonly disabled = input(false);
  /** Disables the button and marks it busy, so a slow command cannot be sent
   *  twice by an impatient second click. */
  readonly loading = input(false);

  protected readonly classes = computed(() => this.variant());
}
