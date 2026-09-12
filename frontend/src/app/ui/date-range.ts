import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

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
 */
@Component({
  selector: 'sb-date-range',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="field">
      <input
        type="date"
        class="from"
        aria-label="From date"
        [value]="from() ?? ''"
        (change)="emit($any($event.target).value || null, to())"
      />
      <span class="sep">–</span>
      <input
        type="date"
        class="to"
        aria-label="To date"
        [attr.min]="from()"
        [value]="to() ?? ''"
        (change)="emit(from(), $any($event.target).value || null)"
      />
    </span>
  `,
  styles: `
    .field { display: inline-flex; align-items: center; gap: var(--space-6); }
    .sep { color: var(--text-muted); }
    input {
      height: var(--control-h);
      padding: 0 var(--space-8);
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    input:hover { border-color: var(--text-muted); }
    input:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
  `,
})
export class DateRange {
  readonly from = input<string | null>(null);
  readonly to = input<string | null>(null);
  readonly changed = output<{ from: string | null; to: string | null }>();

  protected emit(from: string | null, to: string | null): void {
    this.changed.emit({ from, to });
  }
}
