import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'danger'
  | 'ghost'
  | 'icon'
  | 'chip'
  | 'segment'
  | 'link';

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
      min-height: var(--control-h);
      padding: 0 var(--space-14);
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
    /* Dark ink on the bright accent, not white: --bg against --accent clears
       4.4:1, and the same pairing survives an accent change because both
       sides are tokens. */
    :host(.primary) { background: var(--accent); color: var(--bg); }
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
      min-height: 0;
      padding: var(--space-4);
      background: transparent;
      color: var(--text-muted);
      line-height: 1;
    }
    :host(.icon:not([disabled]):hover) { color: var(--text); background: var(--surface-raised); }

    /* A filter toggle. Reads as a chip, behaves as a button: versions/ had
       four of these hand-rolled because no variant covered a control that is
       a chip in appearance and a toggle in function. \`.on\` is the pressed
       state and pairs with aria-pressed at the call site. */
    :host(.chip) {
      min-height: 0;
      padding: var(--space-4) var(--space-8);
      border-color: var(--border);
      border-radius: var(--radius-chip);
      background: var(--surface-raised);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      font-weight: 500;
    }
    :host(.chip:not([disabled]):hover) { border-color: var(--border-strong); color: var(--text); }
    :host(.chip.on) {
      border-color: var(--accent);
      background: var(--accent-soft);
      color: var(--text);
    }

    /* One cell of a segmented control. The group owns the outer border and
       the radius; a segment owns only its divider, so segments sit flush. */
    :host(.segment) {
      border-color: transparent;
      border-radius: 0;
      background: transparent;
      color: var(--text-secondary);
      font-weight: 500;
    }
    :host(.segment:not([disabled]):hover) { color: var(--text); }
    :host(.segment.current) { background: var(--surface-overlay); color: var(--text); }

    /* A button that must look like a link because it sits in running text.
       Still a button: it performs an action rather than navigating, and an
       <a> without an href is not focusable. */
    :host(.link) {
      min-height: 0;
      padding: 0;
      background: transparent;
      color: var(--accent);
      font-size: var(--text-table);
      font-weight: 500;
    }
    :host(.link:not([disabled]):hover) { text-decoration: underline; }
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
