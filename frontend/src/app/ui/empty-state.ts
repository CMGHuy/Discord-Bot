import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import type { AsyncEmptyReason } from './async';

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
      @if (reason(); as why) {
        <span class="reason sb-label" [class.awaiting]="why === 'no-data-yet'">{{ why === 'measured-zero' ? 'Result: 0' : 'Awaiting data' }}</span>
      }
      <p class="empty-title">{{ title() }}</p>
      @if (hint(); as hintText) {
        <p class="empty-hint">{{ hintText }}</p>
      }
    </div>
  `,
  styles: `
    /* v195 Phase 2: the one empty style, inside the panel body. No box of
       its own -- the panel is the frame -- centred and quiet. */
    .empty { display: grid; justify-items: center; gap: var(--space-6); padding: var(--space-20) var(--panel-pad); text-align: center; }
    .empty-title { margin: 0; color: var(--text-secondary); font-size: var(--text-body); }
    .empty-hint { margin: 0; color: var(--text-muted); font-size: var(--text-table); }
    /* A measured zero is a neutral fact (the muted label); missing data is
       a caution. The words carry the difference, the colour repeats it. */
    .reason.awaiting { color: var(--warn); }
  `,

})
export class EmptyStateComponent {
  readonly title = input.required<string>();
  readonly hint = input<string | undefined>(undefined);
  readonly reason = input<AsyncEmptyReason | null>(null);
}
