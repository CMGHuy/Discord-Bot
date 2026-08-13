import { TemplateRef } from '@angular/core';

/* The data table's contract — spec `2026-08-08-v14-angular-workspaces-design.md`
 * Decision 1, with one amendment recorded at `PageSpec` below.
 *
 * These types live apart from the component because all four call sites
 * (Trades, Analytics/Strategies, Risk, Universe) import `ColumnDef` to declare
 * their columns, and importing the component to get a type would drag the
 * whole table into files that only describe data.
 */

/** Which way a column is sorted. Structured rather than the API's `-field`
 *  string: the table must not know how the wire format spells a sort, and a
 *  store that translates one to the other is the only place that should. */
export interface SortSpec {
  key: string;
  direction: 'asc' | 'desc';
}

/**
 * Pagination state, supplied as a unit or not at all.
 *
 * **Amends spec v14 Decision 1**, which made `total`, `page` and `perPage`
 * three separate required inputs. Only one of the four call sites paginates
 * (`GET /api/v1/trades`, the `Collection<T>` envelope); Analytics/Strategies,
 * Risk and Universe all return plain lists. Under the original contract each
 * of those three would have had to pass `total = rows.length`, which is
 * precisely what the spec's own Property 4 forbids — so the contract as
 * written pushed its worst anti-pattern into three of its four consumers.
 *
 * Passing `null` (the default) says "this data is not paginated": every row
 * given is rendered and no pager appears. Grouping the three together also
 * means `total` cannot drift out of step with `page` and `perPage`.
 */
export interface PageSpec {
  /** The count after filtering but BEFORE slicing — the pager's denominator.
   *  **Never `rows.length`.** A table handed `rows.length` silently shows a
   *  single page no matter how much data is behind it. */
  total: number;
  /** 1-based, matching the API's `page` parameter. */
  page: number;
  perPage: number;
}

/** What to show when there is nothing to show. */
export interface EmptyState {
  title: string;
  hint?: string;
}

/** The context a cell or row-expansion template is rendered against. */
export interface RowContext<T> {
  $implicit: T;
}

/**
 * One column. `key` is the identity used by `visible` and by sorting, and it
 * must match the API's sort field name when `sortable` is set.
 *
 * There is deliberately **no ordering property**. Render order comes from the
 * position of the entry in the `columns` array and nothing else — that is what
 * physically retires the drag-to-reorder machinery, since no call site can
 * express an order the component would honour.
 */
export interface ColumnDef<T> {
  key: string;
  header: string;

  /** Plain-text cell content. Ignored when `cell` is given. `null` renders as
   *  an em dash, because a value that has not been computed is not zero and
   *  not an empty string. */
  value?: (row: T) => string | number | null;

  /** Rich cell content — a status dot, a chip, an action button. Overrides
   *  `value`. Interactive content inside must be a real `<button>` or `<a>`;
   *  the table suppresses `rowActivate` for clicks that land on one. */
  cell?: TemplateRef<RowContext<T>>;

  /** Marks the column as a sort trigger. The table only emits `sortChange` —
   *  it never reorders `rows` itself. */
  sortable?: boolean;

  /** Right-aligned and set in the mono face. For money, percentages and
   *  counts, so digits line up down the column. */
  numeric?: boolean;

  /** Any CSS width. Left unset the column takes its content's width. */
  width?: string;
}
