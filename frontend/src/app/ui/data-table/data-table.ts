import { NgTemplateOutlet } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  input,
  output,
  signal,
} from '@angular/core';

import {
  ColumnDef,
  EmptyState,
  PageSpec,
  RowContext,
  SortSpec,
} from './data-table.types';

/**
 * The load-bearing table — spec `2026-08-08-angular-workspaces-design-v14.md`
 * Decision 1. Trades, Analytics/Strategies, Risk and Universe all render
 * through this one component, which is why it was built and settled before any
 * of them started: discovering the API is wrong afterwards means rewriting
 * four workspaces.
 *
 * Five properties the contract enforces, none of which are conveniences:
 *
 *  1. **Server-side everything.** Sorting and paging emit events; this
 *     component never reorders or slices `rows`. The API already works this
 *     way, and a table that sorts only the page it can see is the specific bug
 *     that convention exists to prevent.
 *  2. **`visible` is a set of keys and its order is ignored.** Render order
 *     comes from `columns`. There is no ordering input, so the drag-to-reorder
 *     behaviour that was removed cannot creep back in through a call site.
 *  3. **Row expansion is the caller's template**, not a config object — every
 *     workspace expands into something different, and the alternative slowly
 *     reinvents templates as JSON.
 *  4. **`pagination.total` is post-filter, pre-slice.** See `PageSpec`.
 *  5. **No data access.** This component cannot fetch and does not know a
 *     store exists.
 *
 * The pager markup below is deliberately minimal; NG39 extracts it into
 * `PaginationComponent` along with the column picker and the empty state. What
 * matters here is that `pageChange` is wired to something real, so the
 * contract is exercised rather than merely declared.
 */
@Component({
  selector: 'sb-data-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  template: `
    <div class="wrap" [attr.aria-busy]="loading()">
      <table>
        <thead>
          <tr>
            @if (expansion()) {
              <th class="expander-cell"><span class="sr-only">Expand row</span></th>
            }
            @for (col of renderedColumns(); track col.key) {
              <th
                [style.width]="col.width"
                [class.num]="col.numeric"
                [attr.aria-sort]="ariaSort(col)"
              >
                @if (col.sortable) {
                  <button type="button" class="sort" (click)="toggleSort(col)">
                    <span>{{ col.header }}</span>
                    <span class="arrow" aria-hidden="true">{{ arrow(col) }}</span>
                  </button>
                } @else {
                  {{ col.header }}
                }
              </th>
            }
          </tr>
        </thead>

        <tbody>
          @for (row of rows(); track rowKey()(row)) {
            <tr class="row" (click)="activate(row, $event)">
              @if (expansion()) {
                <td class="expander-cell">
                  <button
                    type="button"
                    class="expander"
                    [attr.aria-expanded]="isExpanded(row)"
                    [attr.aria-label]="isExpanded(row) ? 'Collapse row' : 'Expand row'"
                    (click)="toggleExpanded(row)"
                  >
                    {{ isExpanded(row) ? '▾' : '▸' }}
                  </button>
                </td>
              }
              @for (col of renderedColumns(); track col.key) {
                <td [class.num]="col.numeric">
                  @if (col.cell; as cellTemplate) {
                    <ng-container
                      [ngTemplateOutlet]="cellTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  } @else {
                    {{ text(col, row) }}
                  }
                </td>
              }
            </tr>

            @if (expansion(); as expansionTemplate) {
              @if (isExpanded(row)) {
                <tr class="expansion">
                  <td [attr.colspan]="colspan()">
                    <ng-container
                      [ngTemplateOutlet]="expansionTemplate"
                      [ngTemplateOutletContext]="{ $implicit: row }"
                    />
                  </td>
                </tr>
              }
            }
          }
        </tbody>
      </table>

      @if (showEmptyState()) {
        <div class="empty">
          <p class="empty-title">{{ emptyState()!.title }}</p>
          @if (emptyState()!.hint; as hint) {
            <p class="empty-hint">{{ hint }}</p>
          }
        </div>
      }

      @if (pagination(); as page) {
        @if (pageCount() > 1) {
          <div class="pager">
            <span class="range num">{{ rangeLabel() }}</span>
            <button type="button" [disabled]="page.page <= 1" (click)="goTo(page.page - 1)">
              Previous
            </button>
            <span class="of num">{{ page.page }} / {{ pageCount() }}</span>
            <button
              type="button"
              [disabled]="page.page >= pageCount()"
              (click)="goTo(page.page + 1)"
            >
              Next
            </button>
          </div>
        }
      }
    </div>
  `,
  styles: `
    .wrap { position: relative; }
    .wrap[aria-busy='true'] { opacity: 0.6; transition: opacity var(--transition); }

    table {
      width: 100%;
      border-collapse: collapse;
      font-size: var(--text-table);
    }
    th, td {
      padding: var(--space-6) var(--space-10);
      text-align: left;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    /* Digits line up down the column, so a magnitude is readable without
       reading the number. */
    .num { text-align: right; font-family: var(--font-mono); }
    .num.sort, th.num .sort { justify-content: flex-end; }

    .sort {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      width: 100%;
      padding: 0;
      background: none;
      border: 0;
      color: inherit;
      font: inherit;
      letter-spacing: inherit;
      text-transform: inherit;
      cursor: pointer;
    }
    .sort:hover { color: var(--text); }
    .sort:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* Reserved width, so cycling the sort does not shift the header row. */
    .arrow { display: inline-block; min-width: 0.7em; color: var(--accent); }

    .row:hover { background: var(--surface-raised); }
    .expansion > td { background: var(--surface); white-space: normal; }

    .expander-cell { width: 1px; padding-right: 0; }
    .expander {
      padding: 0 var(--space-4);
      background: none;
      border: 0;
      color: var(--text-muted);
      cursor: pointer;
      font-size: var(--text-body);
    }
    .expander:hover { color: var(--text); }
    .expander:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }

    .empty { padding: var(--space-28) var(--space-20); text-align: center; }
    .empty-title { color: var(--text-secondary); font-size: var(--text-body); }
    .empty-hint { margin-top: var(--space-6); color: var(--text-muted); font-size: var(--text-table); }

    .pager {
      display: flex;
      align-items: center;
      gap: var(--space-10);
      padding: var(--space-10);
      font-size: var(--text-table);
      color: var(--text-secondary);
    }
    .range { margin-right: auto; }
    .pager button {
      padding: var(--space-4) var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      cursor: pointer;
    }
    .pager button:disabled { color: var(--text-faint); cursor: default; }
    .pager button:not(:disabled):hover { border-color: var(--border-strong); }

    .sr-only {
      position: absolute;
      width: 1px; height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `,
})
export class DataTable<T> {
  readonly rows = input.required<T[]>();
  /** The full set, in the order they are meant to render. */
  readonly columns = input.required<ColumnDef<T>[]>();
  /** Column keys. A set, not a sequence — see property 2. */
  readonly visible = input.required<string[]>();
  /** Stable identity per row: the `@for` track and the expansion key. */
  readonly rowKey = input.required<(row: T) => string>();

  readonly sort = input<SortSpec | null>(null);
  /** `null` means this data is not paginated: render every row, show no
   *  pager. See `PageSpec` for why this is one input rather than three. */
  readonly pagination = input<PageSpec | null>(null);
  readonly loading = input(false);
  readonly expansion = input<TemplateRef<RowContext<T>> | null>(null);
  readonly emptyState = input<EmptyState | null>(null);

  readonly sortChange = output<SortSpec>();
  readonly pageChange = output<number>();
  readonly visibleChange = output<string[]>();
  readonly rowActivate = output<T>();

  /** Expanded rows, by `rowKey`. Keyed rather than indexed so a refetch that
   *  reorders or repages the rows does not leave a different row expanded. */
  private readonly expanded = signal<ReadonlySet<string>>(new Set());

  /** Order comes from `columns`; `visible` only decides membership. */
  protected readonly renderedColumns = computed(() => {
    const keys = new Set(this.visible());
    return this.columns().filter((column) => keys.has(column.key));
  });

  protected readonly colspan = computed(
    () => this.renderedColumns().length + (this.expansion() ? 1 : 0),
  );

  /** Not while loading: "No trades match this filter" under a spinner is a
   *  claim the table cannot yet make. */
  protected readonly showEmptyState = computed(
    () => !this.loading() && this.rows().length === 0 && this.emptyState() !== null,
  );

  protected readonly pageCount = computed(() => {
    const page = this.pagination();
    if (!page || page.perPage <= 0) return 1;
    return Math.max(1, Math.ceil(page.total / page.perPage));
  });

  protected readonly rangeLabel = computed(() => {
    const page = this.pagination();
    if (!page) return '';
    const first = (page.page - 1) * page.perPage + 1;
    const last = Math.min(page.page * page.perPage, page.total);
    return `${first}–${last} of ${page.total}`;
  });

  /** An em dash, not an empty cell: a value that has not been computed reads
   *  as missing, where blank reads as a rendering fault. */
  protected text(column: ColumnDef<T>, row: T): string {
    const value = column.value?.(row);
    return value === null || value === undefined || value === '' ? '—' : String(value);
  }

  protected ariaSort(column: ColumnDef<T>): 'ascending' | 'descending' | null {
    const sort = this.sort();
    if (!column.sortable || sort?.key !== column.key) return null;
    return sort.direction === 'asc' ? 'ascending' : 'descending';
  }

  protected arrow(column: ColumnDef<T>): string {
    const sort = this.sort();
    if (sort?.key !== column.key) return '';
    return sort.direction === 'asc' ? '↑' : '↓';
  }

  /** A new column starts ascending and repeat clicks toggle. There is no
   *  third "unsorted" state — the API always sorts by something, so a cycle
   *  back to none would emit a sort the server cannot express. */
  protected toggleSort(column: ColumnDef<T>): void {
    const sort = this.sort();
    const direction =
      sort?.key === column.key && sort.direction === 'asc' ? 'desc' : 'asc';
    this.sortChange.emit({ key: column.key, direction });
  }

  protected goTo(page: number): void {
    if (page < 1 || page > this.pageCount()) return;
    this.pageChange.emit(page);
  }

  protected isExpanded(row: T): boolean {
    return this.expanded().has(this.rowKey()(row));
  }

  protected toggleExpanded(row: T): void {
    const key = this.rowKey()(row);
    this.expanded.update((current) => {
      const next = new Set(current);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  }

  /**
   * Row clicks activate the row, except when the click landed on something
   * that handles its own click — an action button, a link to the detail page.
   * Without this a workspace could not put a "close trade" button in a cell
   * without it also navigating away.
   *
   * Activation is mouse-only by design. A call site that needs the row
   * reachable by keyboard puts a real `<a>` or `<button>` in a cell (Trades
   * uses the `#` column); making every row focusable would put Risk's and
   * Universe's read-only rows into the tab order for nothing.
   */
  protected activate(row: T, event: Event): void {
    const target = event.target as HTMLElement | null;
    if (target?.closest('button, a, input, select, textarea, label')) return;
    this.rowActivate.emit(row);
  }
}
