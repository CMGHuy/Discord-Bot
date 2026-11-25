import {
  ChangeDetectionStrategy, Component, InjectionToken, Signal, forwardRef, input,
} from '@angular/core';

/** S a short select (Horizon, Direction), M a date or Strategy, L a free-text
 *  search; `auto` for month arrows and segmented groups, which size themselves. */
export type FieldSize = 's' | 'm' | 'l' | 'auto';

/** What a control inside a field reads: the field's label, so the control can
 *  drop its own visible label and keep the accessible name (v246 Handoff 2). */
export interface FieldContext {
  readonly label: Signal<string>;
}

export const SB_FIELD = new InjectionToken<FieldContext>('SB_FIELD');

/**
 * One control in a filter bar, with its label line above it (v246 §A2).
 *
 * The label line is always there: with no label it is an aria-hidden filler
 * one caption line tall, so every field in a bar is the same height and the
 * bars (flex-end, V246-6) line the controls up along their bottom edge. The
 * visible label is aria-hidden because the wrapped control carries the
 * accessible name: `sb-select` and `sb-text-input` read `SB_FIELD` and name
 * themselves from it (V246-4). One label path per bar.
 *
 * Width: the field sets `--sb-control-w` from the size token, and the
 * controls size themselves from it. Below 640px the field fills its row or
 * grid cell instead; a `fullRow` field (month arrows, a segmented group)
 * takes the whole row there and drops an empty filler line.
 *
 * In `sb-toolbar` the field, not the control, carries `slot="<id>"`.
 */
@Component({
  selector: 'sb-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [{ provide: SB_FIELD, useExisting: forwardRef(() => Field) }],
  host: {
    '[attr.data-size]': 'size()',
    '[class.no-label]': '!label()',
    '[class.full-row]': 'fullRow()',
  },
  template: `
    @if (label(); as text) {
      <span class="sb-label field-label" aria-hidden="true">{{ text }}</span>
    } @else {
      <span class="sb-label field-label filler" aria-hidden="true">&nbsp;</span>
    }
    <ng-content />
  `,
  styles: `
    :host {
      display: inline-flex;
      flex-direction: column;
      gap: var(--space-4);
      min-width: 0;
      max-width: 100%;
    }
    :host([data-size='s']) { --sb-control-w: var(--field-s); }
    :host([data-size='m']) { --sb-control-w: var(--field-m); }
    :host([data-size='l']) { --sb-control-w: var(--field-l); }
    /* Guaranteed-invalid: a control's var(--sb-control-w, auto) falls back. */
    :host([data-size='auto']) { --sb-control-w: initial; }
    @media (max-width: 639px) {
      :host { display: flex; }
      :host(:not([data-size='auto'])) { --sb-control-w: 100%; }
      :host(.full-row) { flex: 1 1 100%; width: 100%; }
      :host(.full-row.no-label) .field-label { display: none; }
    }
  `,
})
export class Field implements FieldContext {
  readonly label = input<string>('');
  readonly size = input<FieldSize>('m');
  readonly fullRow = input<boolean>(false);
}
