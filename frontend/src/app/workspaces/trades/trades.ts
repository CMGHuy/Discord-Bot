import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiClient } from '../../api/api-client';
import { TradeQuery, TradeRow } from '../../api/models';
import { PreferencesStore } from '../../stores/preferences.store';
import { DEFAULT_PER_PAGE, TradesStore, toSortParam } from '../../stores/trades.store';
import { Button } from '../../ui/button';
import { QualityChip } from '../../ui/chip';
import { ColumnPickerComponent } from '../../ui/column-picker';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, SortSpec } from '../../ui/data-table/data-table.types';
import { FilterBar, FilterChips } from '../../ui/filter-bar';
import { dateTime, pct, text } from '../../ui/format';
import { Select, TextInput } from '../../ui/form-controls';
import { StatusIndicator } from '../../ui/status-indicator';
import {
  ACTION_LABELS,
  ACTION_TITLES,
  TradeActionKind,
  actionConsequence,
  availableActions,
  runTradeAction,
} from './trade-actions';
import {
  DEFAULT_TRADE_COLUMNS,
  STATUS_CHIPS,
  TRADES_TABLE_ID,
  tradeColumns,
} from './trades.columns';

type PendingAction = { kind: TradeActionKind; row: TradeRow } | null;

/**
 * The Trades workspace — the entity that Plans, Journal and the dashboard's
 * two tables collapse into.
 *
 * **Query parameters are the source of truth.** Nothing here mutates the
 * store's query directly: every control navigates, the route's parameters
 * arrive back as signal inputs, and an effect hands them to the store. That
 * one-way loop is what makes a filtered, sorted, paged view survive a reload
 * and be pasteable to someone else — which a store-only filter cannot do, and
 * fails to do silently.
 *
 * It also means the back button works on filters, for free.
 */
@Component({
  selector: 'sb-trades',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [TradesStore],
  imports: [
    RouterLink,
    DataTable,
    ColumnPickerComponent,
    FilterBar,
    FilterChips,
    Select,
    TextInput,
    Button,
    ConfirmDialog,
    StatusIndicator,
    QualityChip,
  ],
  template: `
    <header class="head">
      <h1>Trades</h1>
      <div class="head-actions">
        <!-- A plain anchor, not a fetch: the browser gets a Save dialog and
             the server's filename, both of which an XHR throws away. It
             carries the current query, so the file matches the list on
             screen rather than the whole book. -->
        <a class="export" [href]="store.exportUrl()" download>Export CSV</a>
        <button sb-button variant="ghost" type="button" (click)="bulk.set('open')">
          Clear open
        </button>
        <button sb-button variant="ghost" type="button" (click)="bulk.set('history')">
          Clear history
        </button>
        <sb-column-picker
          [tableId]="tableId"
          [columns]="allColumns()"
          [defaults]="defaultColumns"
          [visible]="visible()"
          (visibleChange)="visible.set($event)"
        />
      </div>
    </header>

    @if (store.clearResult(); as message) {
      <!-- The count, not just "done": "cleared 0" and "cleared 40" are
           different answers and want different reactions. -->
      <p class="cleared" role="status">{{ message }}</p>
    }
    @if (store.clearError(); as message) {
      <p class="command-error" role="alert">{{ message }}</p>
    }

    <sb-filter-chips
      [chips]="statusChips"
      [selected]="status() ?? null"
      label="Status"
      (selectedChange)="navigate({ status: $event })"
    />

    <sb-filter-bar [activeCount]="store.activeFilterCount()" (cleared)="clearFilters()">
      <sb-text-input
        type="search"
        label="Ticker"
        placeholder="AAPL"
        [value]="ticker() ?? ''"
        (valueChange)="navigate({ ticker: $event })"
      />
      <sb-select
        label="Direction"
        placeholder="Any"
        [value]="direction() ?? ''"
        [options]="directionOptions"
        (valueChange)="navigate({ direction: $event })"
      />
      <sb-select
        label="Origin"
        placeholder="Any"
        [value]="origin() ?? ''"
        [options]="originOptions"
        (valueChange)="navigate({ origin: $event })"
      />
    </sb-filter-bar>

    @if (store.error(); as message) {
      <p class="error">{{ message }}</p>
    }

    <sb-data-table
      [rows]="store.rows()"
      [columns]="allColumns()"
      [visible]="visible()"
      [rowKey]="rowKey"
      [sort]="store.sort()"
      [pagination]="store.pagination()"
      [loading]="store.loading()"
      [expansion]="expansionTemplate()"
      [emptyState]="emptyState()"
      (sortChange)="onSort($event)"
      (pageChange)="navigate({ page: $event }, false)"
      (rowActivate)="open($event)"
    />

    <!-- cells ---------------------------------------------------------- -->

    <ng-template #numCell let-row>
      <a class="row-link" [routerLink]="['/trades', row.id]">{{ shortId(row) }}</a>
    </ng-template>

    <ng-template #statusCell let-row>
      <sb-status-indicator
        [status]="row.status"
        [current]="row.current_price"
        [entry]="row.entry"
        [stop]="row.stop_loss"
        [target]="row.target"
      />
    </ng-template>

    <ng-template #pnlCell let-row>
      <span [class]="pnlClass(row.pnl_pct)">{{ fmtPct(row.pnl_pct) }}</span>
    </ng-template>

    <ng-template #tierCell let-row>
      @if (row.tier) {
        <sb-quality-chip [value]="row.tier" [label]="row.tier" />
      }
    </ng-template>

    <ng-template #confidenceCell let-row>
      @if (row.confidence_level !== null) {
        <sb-quality-chip [value]="row.confidence_level" [label]="'Lv' + row.confidence_level" />
      }
    </ng-template>

    <ng-template #openedCell let-row>{{ fmtDate(row.opened_at) }}</ng-template>
    <ng-template #closedCell let-row>{{ fmtDate(row.closed_at) }}</ng-template>

    <ng-template #actionsCell let-row>
      <span class="actions">
        @for (kind of actionsFor(row.status); track kind) {
          <button sb-button variant="ghost" type="button" (click)="ask(kind, row)">
            {{ actionLabels[kind] }}
          </button>
        }
      </span>
    </ng-template>

    <!-- expansion: the four groups spec 3 names ------------------------- -->

    <ng-template #expansion let-row>
      <div class="groups">
        <dl>
          <dt class="group">Plan levels</dt>
          <div><dt>Entry</dt><dd class="num">{{ fmtNum(row.entry) }}</dd></div>
          <div><dt>Stop</dt><dd class="num">{{ fmtNum(row.stop_loss) }}</dd></div>
          <div><dt>Target</dt><dd class="num">{{ fmtNum(row.target) }}</dd></div>
          <div><dt>R:R</dt><dd class="num">{{ fmtNum(row.risk_reward) }}</dd></div>
        </dl>
        <dl>
          <dt class="group">Setup</dt>
          <div><dt>Strategy</dt><dd>{{ fmtText(row.strategy) }}</dd></div>
          <div><dt>Horizon</dt><dd>{{ fmtText(row.horizon) }}</dd></div>
          <div><dt>Confidence</dt><dd class="num">{{ fmtNum(row.confidence_level, 0) }}</dd></div>
          <div><dt>Score</dt><dd class="num">{{ fmtNum(row.confidence_score, 0) }}</dd></div>
        </dl>
        <dl>
          <dt class="group">Sizing</dt>
          <div><dt>Shares</dt><dd class="num">{{ fmtNum(row.shares, 0) }}</dd></div>
          <div><dt>Deployed</dt><dd class="num">{{ fmtNum(row.position_value) }}</dd></div>
          <div><dt>Unrealised</dt><dd class="num">{{ fmtNum(row.realized_pnl_amount) }}</dd></div>
        </dl>
        <dl>
          <dt class="group">Opened</dt>
          <div><dt>At</dt><dd>{{ fmtDate(row.opened_at) }}</dd></div>
        </dl>
      </div>
    </ng-template>

    <sb-confirm-dialog
      [open]="pending() !== null"
      [title]="confirmTitle()"
      [consequence]="confirmConsequence()"
      [confirmLabel]="confirmLabel()"
      [working]="working()"
      (confirmed)="runPending()"
      (cancelled)="pending.set(null)"
    />

    <!-- Its own dialog rather than a widened pending action: the row
         actions act on a named trade and these act on all of them, and one
         dialog serving both would have to describe "the selected trade, or
         every trade" in a single sentence. -->
    <sb-confirm-dialog
      [open]="bulk() !== null"
      [title]="bulkTitle()"
      [consequence]="bulkConsequence()"
      confirmLabel="Clear"
      [working]="store.clearing() !== null"
      (confirmed)="runBulk()"
      (cancelled)="bulk.set(null)"
    />
  `,
  styles: `
    .head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
    }
    h1 { font-size: var(--text-title); font-weight: 600; }
    .head-actions { display: flex; align-items: center; gap: var(--space-8); }
    .export { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .export:hover { text-decoration: underline; }

    .cleared { color: var(--text-secondary); font-size: var(--text-table); }
    /* Red rather than the amber error style above: that one means "a poll
       failed, these numbers are stale", and this one means "the thing you
       asked for did not happen". */
    .command-error { color: var(--neg); font-size: var(--text-table); }

    .error {
      padding: var(--space-8) var(--space-10);
      border: 1px solid var(--warn);
      border-radius: var(--radius);
      color: var(--warn);
      font-size: var(--text-table);
    }

    .row-link { color: var(--accent); font-family: var(--font-mono); text-decoration: none; }
    .row-link:hover { text-decoration: underline; }

    .pos { color: var(--pos); }
    .neg { color: var(--neg); }

    .actions { display: inline-flex; gap: var(--space-4); }

    .groups {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: var(--space-20);
      padding: var(--space-10) var(--space-14);
    }
    dl { display: grid; gap: var(--space-4); align-content: start; }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    .group {
      color: var(--text-muted);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }
  `,
})
export class Trades {
  private readonly router = inject(Router);
  private readonly api = inject(ApiClient);
  private readonly preferences = inject(PreferencesStore);
  protected readonly store = inject(TradesStore);

  /* Query parameters, arriving as inputs through withComponentInputBinding.
   * All strings, because that is what a URL carries. */
  readonly page = input<string>();
  readonly sort = input<string>();
  readonly status = input<string>();
  readonly ticker = input<string>();
  readonly strategy = input<string>();
  readonly horizon = input<string>();
  readonly direction = input<string>();
  readonly tier = input<string>();
  readonly origin = input<string>();

  protected readonly statusChips = STATUS_CHIPS;
  protected readonly defaultColumns = DEFAULT_TRADE_COLUMNS;
  protected readonly tableId = TRADES_TABLE_ID;
  protected readonly rowKey = (row: TradeRow) => row.id;

  protected readonly directionOptions = [
    { value: 'bullish', label: 'Long' },
    { value: 'bearish', label: 'Short' },
  ];
  protected readonly originOptions = [
    { value: 'plan', label: 'Plan' },
    { value: 'legacy', label: 'Legacy' },
  ];

  /** Read once from preferences; the picker owns every write from here on. */
  protected readonly visible = signal<string[]>(
    this.preferences.columns(TRADES_TABLE_ID) ?? DEFAULT_TRADE_COLUMNS,
  );

  protected readonly pending = signal<PendingAction>(null);
  protected readonly working = signal(false);

  /** Which bulk clear is awaiting confirmation. */
  protected readonly bulk = signal<'open' | 'history' | null>(null);

  private readonly numCell = viewChild.required<TemplateRef<unknown>>('numCell');
  private readonly statusCell = viewChild.required<TemplateRef<unknown>>('statusCell');
  private readonly pnlCell = viewChild.required<TemplateRef<unknown>>('pnlCell');
  private readonly tierCell = viewChild.required<TemplateRef<unknown>>('tierCell');
  private readonly confidenceCell =
    viewChild.required<TemplateRef<unknown>>('confidenceCell');
  private readonly openedCell = viewChild.required<TemplateRef<unknown>>('openedCell');
  private readonly closedCell = viewChild.required<TemplateRef<unknown>>('closedCell');
  private readonly actionsCell = viewChild.required<TemplateRef<unknown>>('actionsCell');
  protected readonly expansionTemplate =
    viewChild.required<TemplateRef<{ $implicit: TradeRow }>>('expansion');

  /** The declared column list with rich cells attached by key. Kept apart
   *  from `trades.columns.ts` so that file stays free of templates. */
  protected readonly allColumns = computed<ColumnDef<TradeRow>[]>(() => {
    const cells: Record<string, TemplateRef<{ $implicit: TradeRow }>> = {
      num: this.numCell(),
      status: this.statusCell(),
      pnl_pct: this.pnlCell(),
      tier: this.tierCell(),
      confidence_level: this.confidenceCell(),
      opened_at: this.openedCell(),
      closed_at: this.closedCell(),
      actions: this.actionsCell(),
    } as Record<string, TemplateRef<{ $implicit: TradeRow }>>;

    return tradeColumns().map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column,
    );
  });

  protected readonly emptyState = computed(() =>
    this.store.activeFilterCount() > 0
      ? {
          title: 'No trades match these filters',
          hint: 'Clear them to see the full history.',
        }
      : { title: 'No trades yet', hint: 'They appear here as the bot opens them.' },
  );

  constructor() {
    // The one place the URL becomes store state. Reading every parameter
    // signal here is what makes a navigation refetch.
    effect(() => {
      const query: TradeQuery = {
        page: Number(this.page() ?? 1) || 1,
        per_page: DEFAULT_PER_PAGE,
        sort: this.sort(),
        status: this.status(),
        ticker: this.ticker(),
        strategy: this.strategy(),
        horizon: this.horizon(),
        direction: this.direction(),
        tier: this.tier(),
        origin: this.origin(),
      };
      this.store.setQuery(query);
    });
  }

  protected fmtPct = pct;
  protected fmtText = text;
  protected fmtDate = dateTime;
  protected fmtNum(value: number | null, decimals = 2): string {
    return value === null || value === undefined ? '—' : value.toFixed(decimals);
  }

  protected pnlClass(value: number | null): string {
    if (value === null) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }

  /** Plan ids are long; the column is 3rem wide and the full id is on the
   *  detail page it links to. */
  protected shortId(row: TradeRow): string {
    return row.id.length > 6 ? row.id.slice(-6) : row.id;
  }

  /**
   * Every control routes through here. `resetPage` is the default because a
   * filter or sort change makes the current page meaningless — staying on
   * page 4 of a list that now has two pages shows an empty table, which reads
   * as "no results" and is the most common self-inflicted bug in a filtered
   * list.
   */
  protected navigate(patch: Record<string, string | number | null>, resetPage = true): void {
    const queryParams: Record<string, string | number | null> = { ...patch };
    if (resetPage) queryParams['page'] = null;

    for (const [key, value] of Object.entries(queryParams)) {
      // null drops the parameter, which is what keeps a cleared filter out of
      // the URL instead of leaving `status=` behind.
      if (value === '') queryParams[key] = null;
    }

    this.router.navigate([], { queryParams, queryParamsHandling: 'merge' });
  }

  protected onSort(sort: SortSpec): void {
    this.navigate({ sort: toSortParam(sort) ?? null });
  }

  protected clearFilters(): void {
    this.navigate({
      status: null,
      ticker: null,
      strategy: null,
      horizon: null,
      direction: null,
      tier: null,
      origin: null,
    });
  }

  protected open(row: TradeRow): void {
    this.router.navigate(['/trades', row.id]);
  }

  protected ask(kind: TradeActionKind, row: TradeRow): void {
    this.pending.set({ kind, row });
  }

  protected readonly actionLabels = ACTION_LABELS;
  protected readonly actionsFor = availableActions;

  protected readonly confirmTitle = computed(() => {
    const action = this.pending();
    return action ? ACTION_TITLES[action.kind] : '';
  });

  protected readonly confirmLabel = computed(() => {
    const action = this.pending();
    return action ? ACTION_LABELS[action.kind] : 'Confirm';
  });

  protected readonly confirmConsequence = computed(() => {
    const action = this.pending();
    return action ? actionConsequence(action.kind, action.row) : '';
  });

  protected readonly bulkTitle = computed(() =>
    this.bulk() === 'history' ? 'Clear trade history' : 'Clear open positions',
  );

  /** Names what goes and what stays, per spec v14 — these are the two widest
   *  destructive actions in the product, and "are you sure?" is answered yes
   *  reflexively. The counts are deliberately not quoted from the table:
   *  it is one filtered page, and these commands ignore the filter. */
  protected readonly bulkConsequence = computed(() =>
    this.bulk() === 'history'
      ? 'Every closed trade is deleted permanently, along with its notes — the whole history, not just this page or this filter. Open positions are untouched. This cannot be undone.'
      : 'Every open position is deleted permanently — the whole book, not just this page or this filter. Closed history is untouched, and nothing is closed at a price: the records simply go. This cannot be undone.',
  );

  protected runBulk(): void {
    const kind = this.bulk();
    if (!kind) return;
    if (kind === 'history') this.store.clearHistory();
    else this.store.clearOpen();
    this.bulk.set(null);
  }

  protected runPending(): void {
    const action = this.pending();
    if (!action) return;

    this.working.set(true);
    runTradeAction(this.api, action.kind, action.row.id).subscribe({
      // No manual refetch on success: the command changes trades, the server
      // emits a `trades` event, and the store's effect reissues the current
      // query. Refetching here as well would double every command.
      next: () => {
        this.working.set(false);
        this.pending.set(null);
      },
      error: () => {
        this.working.set(false);
        this.pending.set(null);
      },
    });
  }
}
