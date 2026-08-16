import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { TradesStore } from '../../stores/trades.store';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState } from '../../ui/data-table/data-table.types';

/**
 * How many rows one category's summary table shows.
 *
 * A cap, not a page. The Dashboard answers "what is happening right now" at a
 * glance, and a glance does not scroll; the full list is one click away in
 * Trades, which is where paging, filtering and sorting belong. This is also
 * why no pager is passed to the table -- a pager here would invite paging
 * through a summary, which is the Trades workspace wearing a disguise.
 */
export const OPEN_POSITIONS_CAP = 6;

/**
 * One lifecycle status's capped slice of the Dashboard's open-positions panel
 * — PENDING, ACTIVE and PARTIAL each get their own instance of this.
 *
 * `status=open` (the endpoint's own alias) bundles ACTIVE and PARTIAL, and
 * neither it nor any other existing alias includes PENDING at all — the
 * three categories the panel now shows require three distinct exact-match
 * queries, not one. `TradesStore` already does exact, case-insensitive
 * status matching for anything other than `open` (NG54), so no backend
 * change is needed; this component just gives each status its own store
 * instance (`providers: [TradesStore]`, same isolation trick the Dashboard
 * workspace already uses to keep its table independent of the Trades
 * workspace's) so the three groups load, error and refetch-on-event
 * independently rather than racing each other over one shared query.
 */
@Component({
  selector: 'sb-trade-group',
  imports: [RouterLink, DataTable],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [TradesStore],
  template: `
    <div class="group">
      <div class="group-head">
        <h3>{{ heading() }}</h3>
        <a class="all-link" routerLink="/trades" [queryParams]="{ status: status() }">
          {{ allLinkLabel() }}
        </a>
      </div>

      @if (trades.error(); as message) {
        <p class="table-error" role="status">{{ message }}</p>
      }

      <sb-data-table
        [rows]="rows()"
        [columns]="columns()"
        [visible]="visible()"
        [pinned]="pinned()"
        [rowKey]="rowKey()"
        [loading]="trades.loading()"
        [emptyState]="emptyState()"
        (rowActivate)="rowActivate.emit($event)"
        (reorder)="reorder.emit($event)"
      />
    </div>
  `,
  styles: `
    .group + .group { margin-top: var(--space-14); border-top: 1px solid var(--border);
                       padding-top: var(--space-14); }
    .group-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-10);
      padding: 0 var(--space-14);
      margin-bottom: var(--space-8);
    }
    h3 {
      margin: 0;
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .all-link {
      color: var(--accent);
      font-size: var(--text-chip);
      text-decoration: none;
      white-space: nowrap;
    }
    .all-link:hover { text-decoration: underline; }
    .table-error {
      padding: 0 var(--space-14) var(--space-8);
      color: var(--warn);
      font-size: var(--text-table);
    }
  `,
})
export class TradeGroup {
  protected readonly trades = inject(TradesStore);

  /** The exact-match lifecycle status this group queries: `PENDING`,
   *  `ACTIVE` or `PARTIAL`. */
  readonly status = input.required<string>();
  readonly heading = input.required<string>();
  readonly cap = input(OPEN_POSITIONS_CAP);
  readonly columns = input.required<ColumnDef<TradeRow>[]>();
  readonly visible = input.required<string[]>();
  readonly pinned = input<string[]>([]);
  readonly rowKey = input.required<(row: TradeRow) => string>();
  readonly emptyState = input<EmptyState | null>(null);

  readonly rowActivate = output<TradeRow>();
  readonly reorder = output<string[]>();

  protected readonly rows = computed(() => this.trades.rows().slice(0, this.cap()));

  /** Counts come from this group's own request, not `rows.length`: the table
   *  is capped, and `pagination().total` is the pre-slice count the
   *  Collection convention already guarantees is correct. */
  protected readonly allLinkLabel = computed(() => {
    const total = this.trades.pagination()?.total ?? 0;
    return total > this.cap()
      ? `All ${total} →`
      : `${this.heading()} in Trades →`;
  });

  constructor() {
    // An effect, not a direct read in the constructor body: a required
    // signal input is not guaranteed set yet at that point. `status` and
    // `cap` never actually change after creation -- each instance is
    // mounted once per category, in the template, and unmounted with the
    // panel -- so this effect fires exactly once in practice, but stays
    // correct if that ever stops being true.
    effect(() => {
      this.trades.setQuery({
        status: this.status(),
        sort: '-opened_at',
        page: 1,
        per_page: this.cap(),
      });
    });
  }
}
