import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

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

@Component({
  selector: 'sb-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="field">
      @if (label(); as text) {
        <span class="label">{{ text }}</span>
      }
      <select
        [value]="value()"
        [disabled]="disabled()"
        [attr.aria-label]="label() ? null : ariaLabel()"
        (change)="value.set($any($event.target).value)"
      >
        @if (placeholder(); as text) {
          <option value="">{{ text }}</option>
        }
        @for (option of options(); track option.value) {
          <option [value]="option.value">{{ option.label }}</option>
        }
      </select>
    </label>
  `,
  styles: `
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    select {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
    }
    select:hover:not(:disabled) { border-color: var(--border-strong); }
    select:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    select:disabled { color: var(--text-faint); }
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
}

@Component({
  selector: 'sb-text-input',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="field">
      @if (label(); as text) {
        <span class="label">{{ text }}</span>
      }
      <input
        [type]="type()"
        [value]="value()"
        [placeholder]="placeholder()"
        [disabled]="disabled()"
        [attr.min]="min()"
        [attr.max]="max()"
        [attr.step]="step()"
        [attr.aria-label]="label() ? null : ariaLabel()"
        (input)="value.set($any($event.target).value)"
      />
    </label>
  `,
  styles: `
    .field { display: inline-flex; flex-direction: column; gap: var(--space-4); }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    input {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
    }
    input::placeholder { color: var(--text-faint); }
    input:hover:not(:disabled) { border-color: var(--border-strong); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
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
}

@Component({
  selector: 'sb-checkbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <label class="field" [class.stacked]="topLabel()">
      @if (topLabel(); as text) {
        <span class="top-label">{{ text }}</span>
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
    .top-label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    /* The control band. Height matched to every other control so the row
       aligns on the box, not on the caption's text. */
    .box { display: inline-flex; align-items: center; gap: var(--space-6); height: var(--control-h); }
    .field:has(input:disabled) { color: var(--text-faint); cursor: default; }
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
