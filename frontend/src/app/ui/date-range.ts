import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';

import { SB_FIELD } from './field';

/**
 * A reusable opened-at range picker (v85 D32, and R9-04's second consumer).
 *
 * Two native `<input type="date">` elements, not a calendar widget: the plan
 * forbids a third-party dependency, and a hand-rolled popover calendar is a
 * week of accessibility work to reproduce something the browser already gets
 * right on every platform, phones included.
 *
 * Presentational only — `from`/`to` are the two bounds as `YYYY-MM-DD` or
 * `null`, and every change re-emits both together as `changed`, mapping an
 * emptied input to `null` rather than `''` so a caller writing straight into
 * a query object never has to special-case the empty string itself (the
 * `navigate()`/URL convention this app's other filters already follow).
 *
 * v246 §A2: one field. In a bar it sits in `<sb-field label="Opened"
 * size="auto" [fullRow]="true">`: one caption, From and To inline at M
 * width with the dash between, and below 640px the whole row split 50/50.
 * The inputs take their names from the field's label ("Opened from").
 */
@Component({
  selector: 'sb-date-range',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="field">
      <input
        type="date"
        class="from"
        [attr.aria-label]="fromName()"
        [value]="from() ?? ''"
        (change)="emit($any($event.target).value || null, to())"
      />
      <span class="sep" aria-hidden="true">–</span>
      <input
        type="date"
        class="to"
        [attr.aria-label]="toName()"
        [attr.min]="from()"
        [value]="to() ?? ''"
        (change)="emit(from(), $any($event.target).value || null)"
      />
    </span>
  `,
  styles: `
    :host { display: inline-block; max-width: 100%; }
    .field { display: inline-flex; align-items: center; gap: var(--space-6); }
    .sep { color: var(--text-muted); }
    input {
      min-width: 0;
      width: var(--field-m);
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface);
      border: 1px solid var(--control-border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    input:hover { border-color: var(--text-muted); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    @media (max-width: 639px) {
      :host { display: block; width: 100%; }
      .field { display: flex; }
      input { flex: 1 1 0; width: auto; }
    }
  `,
})
export class DateRange {
  readonly from = input<string | null>(null);
  readonly to = input<string | null>(null);
  readonly changed = output<{ from: string | null; to: string | null }>();

  private readonly field = inject(SB_FIELD, { optional: true });
  /** "Opened from" inside a labelled field; "From date" anywhere else. */
  protected readonly fromName = computed(() => this.boundName('from', 'From date'));
  protected readonly toName = computed(() => this.boundName('to', 'To date'));

  protected emit(from: string | null, to: string | null): void {
    this.changed.emit({ from, to });
  }

  private boundName(bound: 'from' | 'to', fallback: string): string {
    const label = this.field?.label();
    return label ? `${label} ${bound}` : fallback;
  }
}
