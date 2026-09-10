import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type ButtonVariant =
  | 'primary'
  | 'secondary'
  | 'danger'
  | 'ghost'
  | 'icon'
  | 'chip'
  | 'segment'
  | 'link'
  | 'danger-icon';

/**
 * The button variants spec 3's inventory names, and no others (see
 * `ButtonVariant` above for the current list).
 *
 * Applied to a NATIVE `<button>` through an attribute selector rather than
 * wrapping one in a custom element. A wrapper has to re-implement `disabled`,
 * `type="submit"`, focus, the Enter/Space keys and the accessibility tree, and
 * usually re-implements most of them. This way the element in the DOM is
 * the button the browser already knows how to operate, and this component only
 * supplies the paint.
 *
 * `danger` is not merely a red `primary`: it is the variant every irreversible
 * action uses (close, cancel, delete, killswitch), and pairing it with
 * `ConfirmDialog` is what makes those actions hard to trigger by accident.
 * `danger-icon` is a v77 addition for destructive icon-only controls, and pairs
 * with `ConfirmDialog` exactly as `danger` does.
 *
 * v80 D4 restyles every variant through tokens. `segment` and `chip` are
 * deprecated in favour of `sb-segmented`; Migration moves their call sites.
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
       the one place the accent is allowed to carry weight. v80 D1 split the
       accent: --accent (#5593ff) is the text-safe blue and too light to carry
       white ink, so a filled button paints --accent-fill (#2962ff) with
       --on-accent on top, 4.90:1. */
    :host(.primary) { background: var(--accent-fill); color: var(--on-accent); }
    :host(.primary:not([disabled]):hover) { background: color-mix(in srgb, var(--accent-fill) 85%, white); }

    /* A hairline on whatever ground it sits on. Panels separate by hairlines
       now (v80 D3), and a raised fill made every secondary look pressed. */
    :host(.secondary) {
      background: transparent;
      border-color: var(--border-strong);
      color: var(--text);
    }
    :host(.secondary:not([disabled]):hover) { border-color: var(--text-muted); background: var(--surface-raised); }

    /* Red here is not P&L -- it is the one sanctioned exception, because an
       irreversible control that does not look dangerous is worse than a
       colour rule kept perfectly. */
    :host(.danger) {
      background: transparent;
      border-color: var(--neg);
      color: var(--neg);
    }
    /* Fills on hover (v80 D4): the moment before an irreversible click is the
       one place this control should shout. --bg ink on --neg clears 6:1. */
    :host(.danger:not([disabled]):hover) { background: var(--neg); color: var(--bg); }

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

    /* A destructive icon control. Not expressible as \`icon\` plus \`danger\`:
       \`classes\` emits exactly one variant class, deliberately. Geometry is
       \`icon\`'s; the colour is \`danger\`'s. Every call site must supply an
       aria-label -- the icon inside is aria-hidden, so without one the
       control announces nothing at all. */
    :host(.danger-icon) {
      padding: var(--space-4);
      min-width: 0;
      border-color: transparent;
      background: transparent;
      color: var(--neg);
      line-height: 1;
    }
    :host(.danger-icon:not([disabled]):hover) {
      background: color-mix(in srgb, var(--neg) 14%, transparent);
    }

    /* Deprecated (v80 D4): a toggle is sb-segmented now. Kept working until
       Migration moves the call sites.

       A filter toggle. Reads as a chip, behaves as a button: versions/ had
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

    /* Deprecated (v80 D4) with chip above, for the same sb-segmented.

       One cell of a segmented control. The group owns the outer border and
       the radius; a segment owns only its divider, so segments sit flush. */
    :host(.segment) {
      border-color: transparent;
      border-radius: 0;
      background: transparent;
      color: var(--text-secondary);
      font-weight: 500;
    }
    :host(.segment:not([disabled]):hover) { color: var(--text); }
    :host(.segment.current) { background: var(--accent-soft); color: var(--text); }

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

    /* v80 D4 -- a finger needs a square target. The same condition as the
       tokens.css touch block, where --control-h is already 44px. */
    @media (pointer: coarse), (max-width: 639px) {
      :host(.icon), :host(.danger-icon) { min-width: var(--control-h); min-height: var(--control-h); }
    }
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
