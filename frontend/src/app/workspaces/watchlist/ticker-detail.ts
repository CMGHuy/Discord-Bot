import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { ChartStore } from '../../stores/chart.store';
import { TradesStore } from '../../stores/trades.store';
import { ChartContainer } from '../../ui/chart-container';
import { TradeChart } from '../../ui/chart/trade-chart';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext } from '../../ui/data-table/data-table.types';
import { held, num, pct } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';

/** How many of this ticker's trades the table shows.
 *
 *  A cap, not a page. This view answers "what has this symbol done for us",
 *  and the full, filterable, sortable list is one click away in Trades —
 *  where paging belongs. */
export const TICKER_TRADES_CAP = 25;

/**
 * One ticker: its price history and the trades taken on it.
 *
 * **Builds nothing new** (spec v14 Decision 9). The table is
 * `DataTableComponent` over `TradesStore` with the ticker filter set; the
 * chart is `ChartContainer` + `TradeChart` over `ChartStore` with no
 * `trade_id`, so it draws price without any one plan's levels. Both stores
 * are the same ones Trades and the trade detail use — a second loader here
 * would give this screen its own subtly different empty and error states.
 *
 * The chart used to be a different COMPONENT here (`PriceChart`) reading a
 * different endpoint, because the full one could not be asked for a ticker
 * without a trade. It can now, so this screen and the trade detail draw with
 * the same code and cannot drift apart on screen.
 *
 * There is no ticker-level summary endpoint and this view does not invent
 * one: the counts come from the rows it already has.
 */
@Component({
  selector: 'sb-ticker-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, Panel, DataTable, ChartContainer, RowLink, SectionHead, TradeChart],
  providers: [TradesStore, ChartStore],
  template: `
    <!-- The breadcrumb sits above the header rather than inside it: it
         reads first, before the title, and sb-section-head has no slot
         that lands content on that side of the heading -- only
         heading:string and a right-aligned [actions]. -->
    <a class="back" routerLink="/watchlist">← Watchlist</a>
    <sb-section-head [heading]="symbol()">
      <span actions class="counts">
        {{ openCount() }} open · {{ closedCount() }} closed
      </span>
    </sb-section-head>

    <sb-chart-container
      [loading]="chart.loading()"
      [error]="chart.error()"
      [hasData]="!chart.isEmpty()"
      [height]="380"
      [caption]="symbol() + ' — daily'"
    >
      <sb-trade-chart [data]="chart.data()" />
    </sb-chart-container>

    <sb-panel [heading]="'Trades on ' + symbol()" [flush]="true">
      <a panel-actions class="all-link" routerLink="/trades" [queryParams]="{ ticker: symbol() }">
        Open in Trades →
      </a>

      @if (trades.error(); as message) {
        <!-- Without this a failed load renders as the table's empty state,
             and "No trades" would be a claim about this ticker rather than
             about the network. -->
        <p class="table-error" role="status">{{ message }}</p>
      }

      <sb-data-table
        [rows]="trades.rows()"
        [columns]="columns()"
        [visible]="visible"
        [rowKey]="rowKey"
        [loading]="trades.loading() && trades.empty()"
        [emptyState]="emptyState"
      />
    </sb-panel>

    <!-- cells ----------------------------------------------------------- -->

    <ng-template #tickerCell let-row>
      <sb-row-link [link]="['/trades', row.id]">{{ row.ticker }}</sb-row-link>
    </ng-template>

    <!-- pct(), not signed(): every P&L% cell in the app units its own
         figure, for the reason trades.ts's fmtPct note gives (in card mode
         the header is a label beside the value, not a column head above a
         run of them). This one is a single number, but reading the same as
         the other three matters more than the two characters saved. -->
    <ng-template #pnlCell let-row>
      <span [class]="pnlClass(row.pnl_pct)">{{ fmtPct(row.pnl_pct) }}</span>
    </ng-template>
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

    .back { color: var(--text-secondary); font-size: var(--text-table); text-decoration: none; }
    .back:hover { color: var(--text); }
    /* font-family is the one thing sb-section-head's own h1 rule leaves to
       inherit -- setting it on the host reaches the internal h1 through
       normal CSS inheritance, which crosses the encapsulation boundary
       even though selectors cannot. */
    sb-section-head { font-family: var(--font-mono); }
    /* Resets the mono inherited from the host above -- only the ticker
       heading wants it; the count badge stays the app's default sans. */
    .counts { color: var(--text-secondary); font-size: var(--text-table); font-family: var(--font-sans); }

    .all-link { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .all-link:hover { text-decoration: underline; }

    .table-error {
      padding: var(--space-8) var(--space-14);
      color: var(--warn);
      font-size: var(--text-table);
    }

    sb-row-link { color: var(--accent); font-family: var(--font-mono); }
  `,
})
export class TickerDetail {
  /** Arrives through `withComponentInputBinding`, so this component is
   *  testable without standing up a router. */
  readonly symbol = input.required<string>();

  protected readonly trades = inject(TradesStore);
  protected readonly chart = inject(ChartStore);

  protected readonly rowKey = (row: TradeRow) => row.id;

  protected readonly emptyState = {
    title: 'No trades on this ticker',
    hint: 'It is being scanned; nothing has qualified yet.',
  };

  private readonly tickerCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('tickerCell');
  private readonly pnlCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('pnlCell');

  /** Six columns and no picker: the picker persists per table id, and giving
   *  this one the Trades id would let a change here silently rearrange the
   *  Trades list. */
  protected readonly visible = ['ticker', 'status', 'entry', 'now', 'pnl_pct', 'held'];

  protected readonly columns = computed<ColumnDef<TradeRow>[]>(() => [
    { key: 'ticker', header: 'Ticker', cell: this.tickerCell() },
    { key: 'status', header: 'Status', value: (row) => row.status },
    { key: 'entry', header: 'Entry', value: (row) => num(row.entry), numeric: true },
    { key: 'now', header: 'Now', value: (row) => num(row.current_price), numeric: true },
    { key: 'pnl_pct', header: 'P&L %', numeric: true, cell: this.pnlCell() },
    { key: 'held', header: 'Held', value: (row) => held(row.held_hours), numeric: true },
  ]);

  /** From the rows on screen, because there is no ticker summary endpoint
   *  and inventing one for two numbers would be the wrong trade. Both are
   *  therefore counts within the cap, which is why the panel links out. */
  protected readonly openCount = computed(
    () => this.trades.rows().filter((row) => row.status === 'open').length,
  );
  protected readonly closedCount = computed(
    () => this.trades.rows().filter((row) => row.status !== 'open').length,
  );

  constructor() {
    // Both stores follow the route parameter. An effect rather than a
    // constructor call because the symbol can change without the component
    // being recreated -- navigating from one ticker to another reuses it.
    effect(() => {
      this.trades.setQuery({
        ticker: this.symbol(),
        sort: '-opened_at',
        page: 1,
        per_page: TICKER_TRADES_CAP,
      });
    });

    // No trade id: this is the symbol's own chart, and picking one trade's
    // levels to draw would be a claim that plan is the interesting one.
    effect(() => this.chart.setTarget(this.symbol()));
  }

  // The P&L cell units its own percentage -- see trades.ts's fmtPct note.
  protected fmtPct = pct;

  protected pnlClass(value: number | null): string {
    if (value === null) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }
}
