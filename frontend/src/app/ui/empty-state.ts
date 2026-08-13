import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * What a table shows when it has no rows.
 *
 * Always a sentence about this table's situation, never a generic "No data":
 * "no trades yet" and "no trades match this filter" look identical to a
 * component and mean opposite things to a person, and only the caller knows
 * which one it is. The `hint` carries the way out — clear the filters, add a
 * ticker — because an empty state that does not say what to do next is a dead
 * end.
 */
@Component({
  selector: 'sb-empty-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="empty">
      <p class="empty-title">{{ title() }}</p>
      @if (hint(); as hintText) {
        <p class="empty-hint">{{ hintText }}</p>
      }
    </div>
  `,
  styles: `
    .empty { padding: var(--space-20) var(--space-20); text-align: center; }
    .empty-title { color: var(--text-secondary); font-size: var(--text-body); }
    .empty-hint {
      margin-top: var(--space-6);
      color: var(--text-muted);
      font-size: var(--text-table);
    }
  `,
})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly hint = input<string | undefined>(undefined);
}
