import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { CockpitStore } from '../../stores/cockpit.store';
import { TradesStore } from '../../stores/trades.store';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext } from '../../ui/data-table/data-table.types';
import { held, num, pct } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { MetricCard } from '../../ui/metric-card';
import { MetricChip } from '../../ui/metric-chip';
import { Sparkline } from '../../ui/sparkline';

/**
 * How many open positions the summary table shows.
 *
 * A cap, not a page. The Cockpit answers "what is happening right now" at a
 * glance, and a glance does not scroll; the full list is one click away in
 * Trades, which is where paging, filtering and sorting belong. This is also
 * why no pager is passed to the table -- a pager here would invite paging
 * through a summary, which is the Trades workspace wearing a disguise.
 */
export const OPEN_POSITIONS_CAP = 6;

/**
 * The Cockpit — spec v14 Decision 5's two-tier header plus a capped view of
 * what is currently open.
 *
 * Three large cards and six compact chips, and the split is the point:
 * hierarchy comes from size rather than from culling (design system Decision
 * 2), because fourteen equal-weight stat cards is what made the old dashboard
 * unreadable. The six metrics that moved to Analytics -- wins, losses, avg
 * realised P&L, best/worst trade, avg holding period -- are deliberately
 * absent. Re-adding one here is a design change, not a convenience.
 *
 * Two things live in the shell rather than here: scan status and bot status.
 * They are global facts, and duplicating them into a workspace is how the
 * "one thing in four places" problem started.
 *
 * **No card-flash on refresh, and no transition on any number.** Spec 3
 * removed it: with push, "something changed" is continuous rather than a
 * discrete event, so a flash would fire more or less permanently, and an
 * animating figure is unreadable at exactly the glance this screen exists to
 * serve.
 *
 * The data path is NG36's tracer bullet, unchanged: the stores are provided on
 * the component, this component reads signals and never fetches, and there is
 * no subscription or refresh call anywhere in this file -- each store's own
 * effect owns both the first load and every refetch.
 */
@Component({
  selector: 'sb-cockpit',
  imports: [RouterLink, MetricCard, MetricChip, Sparkline, Panel, DataTable],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Provided here rather than in root: the stores are created on entry and
  // destroyed on exit, so a workspace does not hold stale state while you
  // are looking at another one. `TradesStore` is a second, independent
  // instance -- the Trades workspace's own copy is unaffected by the query
  // this screen sets on its own.
  providers: [CockpitStore, TradesStore],
  template: `
    <header class="head">
      <h1>Cockpit</h1>
      @if (store.error(); as message) {
        <!-- Beside the numbers, not instead of them: the previous values
             are still the best information available, and replacing nine
             live figures with an error panel because one poll failed is
             worse than showing them slightly stale. -->
        <span class="stale" role="status">{{ message }}</span>
      }
    </header>

    <div class="primary">
      <sb-metric-card
        label="Account balance"
        [value]="store.balance()"
        unit=" USD"
      />
      <sb-metric-card
        label="Open P&L"
        [value]="store.openPnlPct()"
        tone="pnl"
        unit="%"
      />
      <sb-metric-card
        label="Risk used"
        [value]="store.riskUsedPct()"
        [tone]="riskTone()"
        unit="%"
        [sub]="riskSub()"
      />
    </div>

    <div class="chips">
      <sb-metric-chip label="Open trades" [value]="store.openTrades()" [decimals]="0" />
      <!-- Confidence is a QUALITY judgement, not money, so it stays plain:
           green and red mean P&L direction on this screen and nothing else. -->
      <sb-metric-chip label="Avg confidence" [value]="store.avgConfidence()" [decimals]="1" />
      <sb-metric-chip label="Win rate" [value]="store.winRate()" unit="%" [decimals]="1" />
      <!-- Expectancy is money per unit of risk, which is P&L direction, so it
           is one of the few figures here allowed the green/red pair. -->
      <sb-metric-chip label="Expectancy" [value]="store.expectancyR()" tone="pnl" unit="R" />

      <!-- The equity chip is written out rather than composed from
           MetricChip because MetricChip has no projection slot, and widening
           its contract for this one call site would push a chart-shaped hole
           into the five chips that will never use it. The classes below
           deliberately mirror MetricChip's so the row reads as one set. -->
      <div class="chip equity">
        <span class="label">Equity 30d</span>
        <sb-sparkline [points]="store.equityPoints()" label="Equity, last 30 days" />
        <span class="value num" [class]="equityClass()">{{ equityChange() }}</span>
      </div>

      <sb-metric-chip
        label="Position premium"
        [value]="store.positionPremium()"
        [unit]="premiumUnit()"
        [decimals]="0"
      />
    </div>

    <sb-panel heading="Open positions" [flush]="true">
      <!-- The link out is in the panel header rather than under the table:
           it belongs to this table, and a "see all" floating below a capped
           list reads as pagination. -->
      <a panel-actions class="all-link" routerLink="/trades" [queryParams]="{ status: 'open' }">
        {{ allLinkLabel() }}
      </a>

      @if (trades.error(); as message) {
        <!-- Without this the failed first load renders as the table's empty
             state, and "No open positions" is a claim about the account
             rather than about the network -- the one misreading on this
             screen that could get someone to stop watching a live trade. -->
        <p class="table-error" role="status">{{ message }}</p>
      }

      <sb-data-table
        [rows]="openPositions()"
        [columns]="columns()"
        [visible]="visible"
        [rowKey]="rowKey"
        [loading]="trades.loading()"
        [emptyState]="emptyState"
        (rowActivate)="open($event)"
      />
    </sb-panel>

    <!-- cells ---------------------------------------------------------- -->

    <!-- A real anchor, not a click handler: row activation is mouse-only by
         the table's design, so this is the keyboard route into a position. -->
    <ng-template #tickerCell let-row>
      <a class="row-link" [routerLink]="['/trades', row.id]">{{ row.ticker }}</a>
    </ng-template>

    <ng-template #pnlCell let-row>
      <span [class]="pnlClass(row.pnl_pct)">{{ fmtPct(row.pnl_pct) }}</span>
    </ng-template>
  `,
  styles: `
    :host { display: grid; gap: var(--space-20); }

    .head {
      display: flex;
      align-items: baseline;
      gap: var(--space-14);
    }
    h1 {
      margin: 0;
      font-size: var(--text-title);
      font-weight: 600;
    }
    .stale {
      color: var(--warn);
      font-size: var(--text-table);
    }
    .primary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--space-14);
      /* Three across down to 1280px, which is the width the layout is
         committed to (NG52). Below that they stack rather than shrink --
         a 23px metric in a 90px column is not a metric anyone can read. */
      max-width: 960px;
    }

    .chips {
      display: grid;
      /* auto-fit rather than a fixed six: the chips are the secondary tier
         and are allowed to reflow, where the three cards above are not. */
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: var(--space-8);
      max-width: 960px;
    }
    /* The equity chip carries a chart as well as a number, so it takes two
       tracks where they exist -- a 100px sparkline shows noise, not shape. */
    .equity { grid-column: span 2; }

    .chip {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-8);
      padding: var(--space-6) var(--space-10);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      white-space: nowrap;
    }
    .equity sb-sparkline { flex: 1 1 auto; min-width: 60px; }
    .value { font-size: var(--text-subhead); font-weight: 600; }

    /* The panel is flush so the table can run edge to edge; anything else
       inside it has to bring its own padding. */
    .table-error {
      padding: var(--space-8) var(--space-14);
      color: var(--warn);
      font-size: var(--text-table);
    }

    .all-link {
      color: var(--accent);
      font-size: var(--text-table);
      text-decoration: none;
      white-space: nowrap;
    }
    .all-link:hover { text-decoration: underline; }

    .row-link { color: var(--accent); font-family: var(--font-mono); text-decoration: none; }
    .row-link:hover { text-decoration: underline; }

    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    .absent { color: var(--text-faint); }

    @media (max-width: 720px) {
      .primary { grid-template-columns: 1fr; }
      .equity { grid-column: auto; }
    }
  `,
})
export class Cockpit {
  private readonly router = inject(Router);
  protected readonly store = inject(CockpitStore);
  /** The open-positions table's data. Same component, same store shape and
   *  the same `trades` event as the Trades workspace -- what differs is only
   *  the query, which is set once below and never changes. */
  protected readonly trades = inject(TradesStore);

  protected readonly rowKey = (row: TradeRow) => row.id;

  protected readonly emptyState = {
    title: 'No open positions',
    hint: 'They appear here as the bot opens them.',
  };

  private readonly tickerCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('tickerCell');
  private readonly pnlCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('pnlCell');

  /** Four columns, and no column picker: this is a summary, and every field
   *  it omits is one click away in Trades with the picker attached. */
  protected readonly visible = ['ticker', 'now', 'pnl_pct', 'held'];

  protected readonly columns = computed<ColumnDef<TradeRow>[]>(() => [
    { key: 'ticker', header: 'Ticker', cell: this.tickerCell() },
    { key: 'now', header: 'Now', value: (row) => num(row.current_price), numeric: true },
    { key: 'pnl_pct', header: 'P&L %', numeric: true, cell: this.pnlCell() },
    { key: 'held', header: 'Held', value: (row) => held(row.held_hours), numeric: true },
  ]);

  /** Belt and braces over the server's `per_page`: if the API ever ignores or
   *  raises the cap, the Cockpit still shows a glanceable list rather than
   *  silently growing into a second Trades page. */
  protected readonly openPositions = computed(() =>
    this.trades.rows().slice(0, OPEN_POSITIONS_CAP),
  );

  /** Counts come from the Cockpit endpoint rather than the table, because the
   *  table is capped: "All 23 open" is the truth the link leads to, where
   *  `rows.length` would say 6 and be wrong in exactly the case the link
   *  matters most. */
  protected readonly allLinkLabel = computed(() => {
    const total = this.store.openTrades();
    return total > OPEN_POSITIONS_CAP ? `All ${total} open →` : 'Open in Trades →';
  });

  /** Amber once exposure is most of the cap. Amber means caution, which is
   *  what "nearly out of risk budget" is -- it is not a loss, so it must
   *  not be red. */
  protected readonly riskTone = computed(() =>
    (this.store.riskUtilisation() ?? 0) >= 0.8 ? 'caution' : 'plain',
  );

  protected readonly riskSub = computed(() => {
    const cap = this.store.riskCapPct();
    return cap === null ? null : `of ${cap.toFixed(1)}% cap`;
  });

  /** Signed, so a gain and a loss are told apart without reading the colour
   *  -- which the ~8% who cannot rely on the green/red pair depend on. */
  protected readonly equityChange = computed(() => pct(this.store.equityChangePct(), 1));

  protected readonly equityClass = computed(() => {
    const change = this.store.equityChangePct();
    if (change === null) return 'absent';
    return this.pnlClass(change);
  });

  /** In risk-% sizing there is no single premium -- position value varies per
   *  trade with the stop distance, up to the max-position cap -- so the chip
   *  says "max" rather than presenting a ceiling as a typical cost. */
  protected readonly premiumUnit = computed(() =>
    this.store.positionPremiumIsCap() ? ' USD max' : ' USD',
  );

  constructor() {
    // Set once, synchronously, before the store's effect first runs: one
    // request with the right query rather than a default fetch followed by a
    // corrected one. Nothing here ever changes it -- there is no filter UI on
    // this screen, and adding one would be building Trades again.
    this.trades.setQuery({
      status: 'open',
      // Newest first: the position most likely to need attention is the one
      // just opened, and it is the one the alert that brought you here is
      // about.
      sort: '-opened_at',
      page: 1,
      per_page: OPEN_POSITIONS_CAP,
    });
  }

  protected fmtPct = pct;

  protected pnlClass(value: number | null): string {
    if (value === null) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }

  /** Mouse activation, matching Trades: a row leads to its detail view. The
   *  ticker cell's anchor is the keyboard equivalent. */
  protected open(row: TradeRow): void {
    void this.router.navigate(['/trades', row.id]);
  }
}
