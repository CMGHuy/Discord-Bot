import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
} from '@angular/core';

import { PageSpec } from './data-table/data-table.types';

/**
 * The pager under a paginated table.
 *
 * Every number it shows is derived from `PageSpec.total` — the post-filter,
 * pre-slice count the API returns — and never from how many rows happen to be
 * on screen. That is the whole reason `total` is part of the contract: a pager
 * that counts the rows it can see always reads "1 of 1".
 *
 * Renders nothing at all when everything fits on one page. A pager with one
 * page is chrome that tells you nothing, and Trades is frequently a short list
 * once a status filter is on.
 */
@Component({
  selector: 'sb-pagination',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (pageCount() > 1) {
      <div class="pager">
        <span class="range num">{{ rangeLabel() }}</span>
        <button type="button" [disabled]="pagination().page <= 1" (click)="goTo(-1)">
          Previous
        </button>
        <span class="of num">{{ pagination().page }} / {{ pageCount() }}</span>
        <button
          type="button"
          [disabled]="pagination().page >= pageCount()"
          (click)="goTo(1)"
        >
          Next
        </button>
      </div>
    }
  `,
  styles: `
    .pager {
      display: flex;
      align-items: center;
      gap: var(--space-10);
      padding: var(--space-10);
      font-size: var(--text-table);
      color: var(--text-secondary);
    }
    .range { margin-right: auto; }
    button {
      padding: var(--space-4) var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      cursor: pointer;
      transition: border-color var(--transition);
    }
    button:disabled { color: var(--text-faint); cursor: default; }
    button:not(:disabled):hover { border-color: var(--border-strong); }
    button:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
  `,
})
export class PaginationComponent {
  readonly pagination = input.required<PageSpec>();
  readonly pageChange = output<number>();

  protected readonly pageCount = computed(() => {
    const { total, perPage } = this.pagination();
    if (perPage <= 0) return 1;
    return Math.max(1, Math.ceil(total / perPage));
  });

  /** "26–50 of 90". The range is computed from the page, not measured from
   *  the rows, so it stays correct while a refetch is in flight. */
  protected readonly rangeLabel = computed(() => {
    const { total, page, perPage } = this.pagination();
    const first = (page - 1) * perPage + 1;
    const last = Math.min(page * perPage, total);
    return `${first}–${last} of ${total}`;
  });

  protected goTo(delta: number): void {
    const target = this.pagination().page + delta;
    if (target < 1 || target > this.pageCount()) return;
    this.pageChange.emit(target);
  }
}
