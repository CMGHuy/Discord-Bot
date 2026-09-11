import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/**
 * The one control bar — spec v85 D22.
 *
 * Filters and chips go in the `filters` slot, scope controls (range pickers,
 * unit selectors) in the `scope` slot. The bar owns the wrap behaviour and the
 * Clear affordance so that no page has to solve either, and so that the two
 * never disagree between pages.
 *
 * It does not own any state. `activeCount` is computed by the page from its own
 * query parameters — this component must not become a second copy of the truth
 * about what is filtered.
 */
@Component({
  selector: 'sb-control-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="bar" role="group" aria-label="Page controls">
      <div class="filters"><ng-content select="[filters]" /></div>
      <div class="scope">
        <ng-content select="[scope]" />
        @if (activeCount() > 0) {
          <button type="button" class="clear" (click)="cleared.emit()">
            Clear {{ activeCount() }}
          </button>
        }
      </div>
    </div>
  `,
  styles: `
    .bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
      padding: var(--space-10) 0;
    }
    .filters,
    .scope {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-10);
      min-width: 0;
    }
    .clear {
      font-size: var(--text-micro);
      color: var(--accent);
      background: none;
      border: 0;
      cursor: pointer;
    }
    /* At phone width the two groups stack rather than compete for one row.
       Nothing is hidden — the plan forbids a control that vanishes silently. */
    @media (max-width: 640px) {
      .bar { flex-direction: column; align-items: stretch; }
      .scope { justify-content: flex-start; }
    }
  `,
})
export class ControlBar {
  readonly activeCount = input<number>(0);
  readonly cleared = output<void>();
}
