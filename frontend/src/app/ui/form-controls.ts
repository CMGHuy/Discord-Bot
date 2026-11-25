import { ChangeDetectionStrategy, Component, computed, inject, input, model } from '@angular/core';

import { FieldContext, SB_FIELD } from './field';

/* Spec 3's input inventory: select, text input, checkbox.
 *
 * All three use `model()` for two-way binding rather than implementing
 * `ControlValueAccessor`. Nothing in this application uses Angular forms --
 * every filter is a query parameter and every setting is a field on a store --
 * so a CVA would be ceremony in service of an integration that has no call
 * site. If a real form ever appears, adding CVA is additive.
 *
 * Each control renders a real `<label>` wrapping or bound to a real form
 * element, so clicking the text focuses the control and screen readers get the
 * association for free.
 */

/** One option in a `<select>`. */
export interface SelectOption {
  value: string;
  label: string;
}

/** The accessible name of a select or text input (v246 Handoff 2).
 *  Outside an sb-field nothing changes: the visible <label> names the
 *  control, and aria-label is used only when there is no label. Inside a
 *  field the field draws the (aria-hidden) caption, so the control names
 *  itself: its own label, else its ariaLabel, else the field's label;
 *  null removes the attribute rather than printing an empty one. */
function controlName(field: FieldContext | null, label: string | null, ariaLabel: string): string | null {
  if (!field) return label ? null : ariaLabel;
  return label || ariaLabel || field.label() || null;
}

@Component({
  selector: 'sb-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class.in-field]': 'inField' },
  template: `
    <label class="field">
      @if (visibleLabel(); as text) {
        <span class="sb-label">{{ text }}</span>
      }
      <select
        [value]="value()"
        [disabled]="disabled()"
        [attr.aria-label]="accessibleName()"
        (change)="value.set($any($event.target).value)"
      >
        @if (placeholder(); as text) {
          <option value="">{{ text }}</option>
        }
        @for (option of options(); track option.value) {
          <option [value]="option.value" [selected]="option.value === value()">{{ option.label }}</option>
        }
      </select>
    </label>
  `,
  styles: `
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    /* v246: inside an sb-field the control is block-level, so a width of
       100% (below 640px) resolves against the field, not its own content. */
    :host(.in-field) { display: block; min-width: 0; }
    :host(.in-field) .field { display: flex; }
    /* v80 D4: a hairline field; the caption is the global .sb-label.
       --text-control is 16px on touch, the size below which a phone zooms
       into a focused field. v195 Phase 2: the panel is the flat --surface
       now, so the field sits one step down on the --bg well, behind the
       control border (v240, 3:1 in Navy), and its edge brightens on hover. */
    select {
      height: var(--control-h);
      /* The field's size token (ui/field.ts); native width standalone. */
      width: var(--sb-control-w, auto);
      max-width: 100%;
      padding: 0 var(--space-8);
      background: var(--bg);
      border: 1px solid var(--control-border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
      transition: border-color var(--transition);
    }
    select:hover:not(:disabled) { border-color: var(--text-muted); }
    select:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    /* Opacity, not the divider-only grey (contrast.spec.ts). */
    select:disabled { opacity: 0.45; }
  `,
})
export class Select {
  readonly value = model<string>('');
  readonly options = input.required<SelectOption[]>();
  readonly label = input<string | null>(null);
  /** Used only when there is no visible label. */
  readonly ariaLabel = input('');
  /** The empty choice — "Any strategy", "All horizons". */
  readonly placeholder = input<string | null>(null);
  readonly disabled = input(false);

  private readonly field = inject(SB_FIELD, { optional: true });
  /** Inside an sb-field the field draws the one label (v246 Handoff 2). */
  protected readonly inField = this.field !== null;
  protected readonly visibleLabel = computed(() => (this.inField ? null : this.label()));
  protected readonly accessibleName = computed(() => controlName(this.field, this.label(), this.ariaLabel()));
}

@Component({
  selector: 'sb-text-input',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class.in-field]': 'inField' },
  template: `
    <label class="field">
      @if (visibleLabel(); as text) {
        <span class="sb-label">{{ text }}</span>
      }
      <input
        [type]="type()"
        [value]="value()"
        [placeholder]="placeholder()"
        [disabled]="disabled()"
        [attr.min]="min()"
        [attr.max]="max()"
        [attr.step]="step()"
        [attr.name]="name()"
        [attr.autocomplete]="autocomplete()"
        [attr.aria-label]="accessibleName()"
        (input)="value.set($any($event.target).value)"
      />
    </label>
  `,
  styles: `
    :host { min-width: 0; }
    /* max-width + min-width: 0: in a narrow grid cell (the filter bar's two
       columns at 390) the field shrinks to the cell instead of keeping the
       native 20-character input width and running past the panel. */
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); max-width: 100%; }
    /* v246: see sb-select above. */
    :host(.in-field) { display: block; min-width: 0; }
    :host(.in-field) .field { display: flex; }
    /* Same field as sb-select above (v80 D4). */
    input {
      min-width: 0;
      height: var(--control-h);
      /* The field's size token (ui/field.ts); native width standalone. */
      width: var(--sb-control-w, auto);
      padding: 0 var(--space-8);
      background: var(--bg);
      border: 1px solid var(--control-border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
      transition: border-color var(--transition);
    }
    input::placeholder { color: var(--text-muted); }
    input:hover:not(:disabled) { border-color: var(--text-muted); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    input:disabled { opacity: 0.45; }
  `,
})
export class TextInput {
  readonly value = model<string>('');
  readonly label = input<string | null>(null);
  readonly ariaLabel = input('');
  readonly placeholder = input('');
  /**
   * `search` gets the browser's clear affordance.
   *
   * `number` was deliberately excluded here, on the grounds that every
   * numeric field in the app is a price or a percentage that wants its own
   * formatting rather than a spinner. NG50 is the exception that reopened
   * it: the System settings form renders from `config.py`'s schema, where a
   * `number` field arrives with its own `min`, `max` and `step` and the
   * browser's range check is exactly the right one. Adding a second input
   * component for that one case would be worse than widening this one.
   *
   * The value stays a string either way — `<input type="number">` reports
   * one, and the settings API takes one.
   *
   * `date` was added for the Analytics range filter, which had two raw
   * `<input type="date">` because nothing here covered it. The native picker
   * is the right control -- it is keyboard-accessible, localised by the
   * browser, and this app never needs a range calendar.
   */
  readonly type = input<'text' | 'search' | 'number' | 'password' | 'date'>('text');
  readonly disabled = input(false);

  /** Passed through to the element for `number` fields, straight from the
   *  schema. Null on everything else, which removes the attribute. */
  readonly min = input<number | null>(null);
  readonly max = input<number | null>(null);
  readonly step = input<number | null>(null);

  private readonly field = inject(SB_FIELD, { optional: true });
  /** Inside an sb-field the field draws the one label (v246 Handoff 2). */
  protected readonly inField = this.field !== null;
  protected readonly visibleLabel = computed(() => (this.inField ? null : this.label()));
  protected readonly accessibleName = computed(() => controlName(this.field, this.label(), this.ariaLabel()));

  /** `name` and `autocomplete` pass straight through to the native input.
   *  Login is the one call site that needs them -- a password manager
   *  keys off both, and dropping them would be a real regression. */
  readonly name = input<string | null>(null);
  readonly autocomplete = input<string | null>(null);
}

@Component({
  selector: 'sb-checkbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="field" [class.stacked]="topLabel()">
      @if (topLabel(); as text) {
        <span class="top-label sb-label">{{ text }}</span>
      }
      <span class="box">
        <input
          type="checkbox"
          [checked]="checked()"
          [disabled]="disabled()"
          (change)="checked.set($any($event.target).checked)"
        />
        <span>{{ label() }}</span>
      </span>
    </label>
  `,
  styles: `
    .field {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      font-size: var(--text-table);
      color: var(--text);
      cursor: pointer;
    }
    /* Label above, control below -- the same two bands sb-select and
       sb-text-input have, so a checkbox can share a row with them. */
    .stacked { flex-direction: column; align-items: flex-start; gap: var(--space-4); }
    /* .top-label's typography is the global .sb-label (v80 D3). */
    /* The control band. Height matched to every other control so the row
       aligns on the box, not on the caption's text. */
    .box { display: inline-flex; align-items: center; gap: var(--space-6); height: var(--control-h); min-width: var(--hit-min); }
    .field:has(input:disabled) { opacity: 0.45; cursor: default; }
    input { accent-color: var(--accent); }
  `,
})
export class Checkbox {
  readonly checked = model(false);
  readonly label = input.required<string>();
  readonly disabled = input(false);
  /** Rendered above the box, matching sb-select and sb-text-input, so a
   *  checkbox can sit in a control row without breaking its alignment. The
   *  inline `label` stays either way -- it is the checkbox's own name. */
  readonly topLabel = input<string | null>(null);
}
