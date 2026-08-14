import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { DashboardScope, TradeRow } from '../../api/models';
import { PreferencesStore } from '../../stores/preferences.store';
import { DashboardStore } from '../../stores/dashboard.store';
import { TradesStore } from '../../stores/trades.store';
import { Button } from '../../ui/button';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, Density, RowContext } from '../../ui/data-table/data-table.types';
import { ConfidenceCell } from '../../ui/confidence-cell';
import { DirectionArrow } from '../../ui/direction-arrow';
import { PlanCell } from '../../ui/plan-cell';
import { StatusCell } from '../../ui/status-cell';
import {
  readTableColumns,
  readTableDensity,
  writeTableColumns,
  writeTableDensity,
} from '../../ui/table-prefs';
import {
  COMPACT_COLUMNS,
  DASHBOARD_TABLE_ID,
  FULL_COLUMNS,
  PINNED_COLUMNS,
  tradeColumns,
} from '../trades/trades.columns';
import { held, num, pct } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { MetricCard } from '../../ui/metric-card';
import { MetricChip } from '../../ui/metric-chip';
import { Sparkline } from '../../ui/sparkline';

/**
 * How many open positions the summary table shows.
 *
 * A cap, not a page. The Dashboard answers "what is happening right now" at a
 * glance, and a glance does not scroll; the full list is one click away in
 * Trades, which is where paging, filtering and sorting belong. This is also
 * why no pager is passed to the table -- a pager here would invite paging
 * through a summary, which is the Trades workspace wearing a disguise.
 */
export const OPEN_POSITIONS_CAP = 6;

/**
 * The Dashboard — spec v14 Decision 5's two-tier header plus a capped view of
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
  selector: 'sb-dashboard',
  imports: [
    RouterLink, MetricCard, MetricChip, Sparkline, Panel, DataTable,
    StatusCell, DirectionArrow, PlanCell, ConfidenceCell, Button,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Provided here rather than in root: the stores are created on entry and
  // destroyed on exit, so a workspace does not hold stale state while you
  // are looking at another one. `TradesStore` is a second, independent
  // instance -- the Trades workspace's own copy is unaffected by the query
  // this screen sets on its own.
  providers: [DashboardStore, TradesStore],
  template: `
    <header class="head">
      <h1>Dashboard</h1>
      @if (store.error(); as message) {
        <!-- Beside the numbers, not instead of them: the previous values
             are still the best information available, and replacing nine
             live figures with an error panel because one poll failed is
             worse than showing them slightly stale. -->
        <span class="stale" role="status">{{ message }}</span>
      }

      <!-- SR58. The Jinja dashboard's three date scopes. A server parameter,
           not a client filter: the realised figures below are computed from
           the scoped set, and a client-side scope over an all-time payload
           could not narrow them at all. -->
      <div class="scope" role="group" aria-label="Date scope">
        @for (option of scopes; track option.mode) {
          <button
            sb-button
            type="button"
            [variant]="store.scope() === option.mode ? 'secondary' : 'ghost'"
            [attr.aria-pressed]="store.scope() === option.mode"
            (click)="store.setScope(option.mode)"
          >
            {{ option.label }}
          </button>
        }
      </div>
    </header>

    <!-- SR58. Realised, scoped by the toggle above -- distinct from the
         Open P&L card, which is unrealised and always all-open. -->
    <div class="realized">
      <sb-metric-card
        [label]="realizedLabel()"
        [value]="store.realizedAmount()"
        tone="pnl"
        unit=" USD"
      />
      <sb-metric-card
        label="Realised, average"
        [value]="store.realizedPct()"
        tone="pnl"
        unit="%"
      />
      <span class="realized-count">
        {{ store.realizedCount() }} closed ·
        {{ store.realizedWins() }}W / {{ store.realizedLosses() }}L
      </span>
    </div>

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

    <!-- SR53. The lifecycle strip: five counts, each a link into Trades
         filtered to that status. The Jinja dashboard had exactly this and the
         SPA had the chips it navigated to with no numbers on them. -->
    @if (store.lifecycle().length) {
      <nav class="lifecycle" aria-label="Plans by lifecycle status">
        @for (entry of store.lifecycle(); track entry.status) {
          <a
            class="lc"
            routerLink="/trades"
            [queryParams]="{ status: entry.status, outcome: null }"
          >
            <span class="lc-count num">{{ entry.count }}</span>
            <span class="lc-label">{{ entry.status }}</span>
          </a>
        }
      </nav>
    }

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
        [visible]="visible()"
        [pinned]="pinned"
        [rowKey]="rowKey"
        [loading]="trades.loading()"
        [emptyState]="emptyState"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      />
    </sb-panel>

    <ng-template #statusCell let-row>
      <sb-status-cell [row]="row" />
    </ng-template>
    <ng-template #directionCell let-row>
      <sb-direction-arrow [direction]="row.direction" />
    </ng-template>
    <ng-template #planCell let-row>
      <sb-plan-cell
        [entry]="row.entry"
        [target]="row.target"
        [stop]="row.stop_loss"
        [trigger]="row.trigger_price"
      />
    </ng-template>
    <ng-template #confidenceCell let-row>
      <sb-confidence-cell [level]="row.confidence_level" [score]="row.confidence_score" />
    </ng-template>

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
    /* -- SR58: scope toggle and realised row ---------------------- */
    .scope { display: flex; gap: var(--space-4); margin-left: auto; }
    .realized {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-8);
      margin-bottom: var(--space-10);
    }
    .realized-count {
      margin-left: auto;
      color: var(--text-faint);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
    }

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

    /* SR53. One row, lifecycle order, sized to the count rather than the
       label -- the number is what is being read. */
    .lifecycle {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
      gap: var(--space-8);
      max-width: 960px;
    }
    .lc {
      display: grid;
      gap: 2px;
      padding: var(--space-8) var(--space-10);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      text-decoration: none;
    }
    .lc:hover { border-color: var(--border-strong); }
    .lc-count { color: var(--text); font-size: var(--text-subhead); font-weight: 600; }
    .lc-label {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }

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
export class Dashboard {
  private readonly router = inject(Router);
  protected readonly store = inject(DashboardStore);
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
  private readonly statusCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('statusCell');
  private readonly directionCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('directionCell');
  private readonly planCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('planCell');
  private readonly confidenceCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('confidenceCell');
  private readonly preferences = inject(PreferencesStore);

  protected readonly tableId = DASHBOARD_TABLE_ID;
  protected readonly pinned = PINNED_COLUMNS;

  /** Its own density and its own columns, under its own table id.
   *
   *  Same DEFINITIONS as Trades, separate PREFERENCES — spec v18 Decision 6
   *  reverses workspaces v14 Decision 5, which had this panel keep a private
   *  four-column list. Sharing the definitions is what stops the two tables
   *  drifting; sharing the preferences would mean arranging one silently
   *  rearranged the other, and these two are looked at for different reasons.
   */
  protected readonly density = signal<Density>(
    readTableDensity(this.preferences.values(), DASHBOARD_TABLE_ID),
  );

  protected readonly defaultColumns = computed(() =>
    this.density() === 'full' ? FULL_COLUMNS : COMPACT_COLUMNS,
  );

  protected readonly visible = signal<string[]>(
    readTableColumns(
      this.preferences.values(),
      DASHBOARD_TABLE_ID,
      readTableDensity(this.preferences.values(), DASHBOARD_TABLE_ID),
      readTableDensity(this.preferences.values(), DASHBOARD_TABLE_ID) === 'full'
        ? FULL_COLUMNS
        : COMPACT_COLUMNS,
    ),
  );

  /**
   * Apply the saved layout once the server's preferences arrive.
   *
   * The signals above are seeded synchronously, which reads `{}` while the
   * request is still in flight — so without this the saved density, column
   * order and page size are written correctly and then never applied. The
   * write path working is what makes it easy to miss.
   */
  private readonly applyStoredPreferences = effect(() => {
    if (!this.preferences.isLoaded()) return;
    const prefs = this.preferences.values();
    const density = readTableDensity(prefs, DASHBOARD_TABLE_ID);
    untracked(() => {
      this.density.set(density);
      this.visible.set(
        readTableColumns(prefs, DASHBOARD_TABLE_ID, density,
                         density === 'full' ? FULL_COLUMNS : COMPACT_COLUMNS),
      );
    });
  });

  protected setDensity(next: Density): void {
    if (next === this.density()) return;
    this.density.set(next);
    this.preferences.update((prefs) => writeTableDensity(prefs, DASHBOARD_TABLE_ID, next));
    this.visible.set(
      readTableColumns(this.preferences.values(), DASHBOARD_TABLE_ID, next,
                       next === 'full' ? FULL_COLUMNS : COMPACT_COLUMNS),
    );
  }

  protected onReorder(order: string[]): void {
    this.visible.set(order);
    this.preferences.update((prefs) =>
      writeTableColumns(prefs, DASHBOARD_TABLE_ID, this.density(), order),
    );
  }

  /** The shared definitions, with this panel's own cells attached. */
  protected readonly columns = computed<ColumnDef<TradeRow>[]>(() => {
    const cells: Record<string, TemplateRef<RowContext<TradeRow>>> = {
      ticker: this.tickerCell(),
      pnl_pct: this.pnlCell(),
      status: this.statusCell(),
      direction: this.directionCell(),
      plan: this.planCell(),
      confidence_level: this.confidenceCell(),
    };
    return tradeColumns().map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column,
    );
  });

  /** Belt and braces over the server's `per_page`: if the API ever ignores or
   *  raises the cap, the Dashboard still shows a glanceable list rather than
   *  silently growing into a second Trades page. */
  protected readonly openPositions = computed(() =>
    this.trades.rows().slice(0, OPEN_POSITIONS_CAP),
  );

  /** Counts come from the Dashboard endpoint rather than the table, because the
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
  /* -- SR58: the date scope ------------------------------------------- */

  /** The Jinja dashboard's three, in its order. `active` first because it is
   *  the default and the one that answers "what is happening now". */
  protected readonly scopes: { mode: DashboardScope; label: string }[] = [
    { mode: 'active', label: 'Today + open' },
    { mode: 'today', label: 'Today' },
    { mode: 'all', label: 'All days' },
  ];

  /** Names the window in the card itself, so a figure cannot be read as
   *  today's when the toggle is on All days. */
  protected readonly realizedLabel = computed(() =>
    this.store.scope() === 'all' ? 'Realised, all days' : 'Realised today',
  );

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
