import {
  ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeQuery, TradeRow } from '../../api/models';
import { TradesStore } from '../../stores/trades.store';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState, PhoneTap } from '../../ui/data-table/data-table.types';
import { STATUS_ICON } from '../../ui/icon';
import { Tab, TabBar } from '../../ui/layout';
import { Async, asyncInputs } from '../../ui/async';
import { tablePerPage } from '../../ui/table-per-page';
import { perPageForApi } from '../../ui/table-prefs';
import { TimeWindow } from './panels/equity-range.model';

/** Lifecycle order, not size order: this is the order a plan moves through,
 *  and sorting by count would reshuffle the strip every time a trade closed.
 *  icon reuses icon.ts's own STATUS_ICON map -- the same one Recent
 *  Activity's status glyph reads -- so both panels share one vocabulary
 *  rather than each inventing its own (2026-09-14: icons were deliberately
 *  kept OUT of the row-level StatusCell here, but the TAB strip is a
 *  different surface -- it names a whole group, not one row's status, and
 *  is exactly what a mobile-width icon-only tab needs to stay legible). */
export const POSITION_TABS: (Tab & { status: string; scoped: boolean })[] = [
  { id: 'PENDING',   label: 'Pending',   icon: STATUS_ICON['PENDING'],   status: 'PENDING',   scoped: false },
  { id: 'ACTIVE',    label: 'Open',      icon: STATUS_ICON['ACTIVE'],    status: 'ACTIVE',    scoped: false },
  { id: 'PARTIAL',   label: 'Partial',   icon: STATUS_ICON['PARTIAL'],   status: 'PARTIAL',   scoped: false },
  { id: 'CLOSED',    label: 'Closed',    icon: STATUS_ICON['CLOSED'],    status: 'CLOSED',    scoped: true  },
  { id: 'CANCELLED', label: 'Cancelled', icon: STATUS_ICON['CANCELLED'], status: 'CANCELLED', scoped: true  },
];

const EMPTY_STATES: Record<string, EmptyState> = {
  ACTIVE: { title: 'No active positions', hint: 'They appear here once a plan’s entry fills.' },
  PENDING: { title: 'No pending plans', hint: 'They appear here once a plan is posted, waiting for its entry trigger.' },
  PARTIAL: { title: 'No partial positions', hint: 'They appear here once TP1 hits and part of the position closes.' },
  CLOSED: { title: 'No closed trades', hint: 'They appear here once a position’s target or stop closes it out.' },
  CANCELLED: { title: 'No cancelled plans', hint: 'A plan lands here if it expires or is invalidated before filling.' },
};

/**
 * One table, five lifecycle tabs — v85 D11.
 *
 * **Only the selected tab fetches.** The four stacked groups this replaces
 * each held their own `TradesStore` and all four queried on every visit; one
 * store re-queried on tab change is strictly less work for the same answer.
 *
 * Only CLOSED and CANCELLED honour the page's Today/All scope. ACTIVE,
 * PENDING and PARTIAL are all-time by definition: a position that is open is
 * open regardless of when it opened, and narrowing those to "today" would
 * hide the book.
 *
 * Close all is the Dashboard page header's (v195 Phase 4), so this table
 * projects no actions of its own.
 */
@Component({
  selector: 'sb-positions-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Async, TabBar, DataTable, RouterLink],
  providers: [TradesStore],
  template: `
    <sb-tab-bar [tabs]="tabs()" [active]="active()" (activeChange)="choose($event)" />

    <sb-async [loading]="async().loading" [error]="async().error" [empty]="false"
              [staleAsOf]="async().staleAsOf"
              emptyReason="measured-zero" emptyTitle="Open positions"
              [skeletonRows]="3" [skeletonCols]="5"
              (retry)="trades.load()">
      <div class="table-head">
        <a class="all-link sb-hit" routerLink="/trades" [queryParams]="{ status: active() }">
          View in Trades →
        </a>
      </div>

      <sb-data-table
        [rows]="rows()"
        [columns]="columns()"
        [visible]="visible()"
        [pinned]="pinned()"
        [rowKey]="rowKey()"
        [phoneTap]="phoneTap()"
        [emptyState]="emptyState()"
        [pagination]="trades.pagination()"
        [fillPage]="false"
        [showPerPage]="true"
        [perPageChoice]="perPage()"
        (perPageChange)="onPerPage($event)"
        (rowActivate)="rowActivate.emit($event)"
        (reorder)="reorder.emit($event)"
        (pageChange)="goToPage($event)"
      />
    </sb-async>
  `,
  styles: `
    /* v195 §1.4: entry, stop, target and size are order figures and never
       shrink below the 14px body step, in either density. The table and the
       plan cell read --text-table; this table alone re-points it. */
    :host { display: block; --text-table: var(--text-body); }
    .table-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
      padding: var(--space-10) var(--space-14) var(--space-4);
    }
    .all-link { color: var(--accent); font-size: var(--text-chip); text-decoration: none; }
    .all-link:hover { text-decoration: underline; }
  `,
})
export class PositionsTable {
  protected readonly trades = inject(TradesStore);

  /** Lifecycle counts from the dashboard payload, keyed by status. Rendered
   *  on the tab labels so the strip answers "how many" before it is clicked. */
  readonly counts = input<Record<string, number>>({});
  readonly today = input<boolean | null>(null);
  /** v181 §6: the scope's `[from, to)` window outside 1D and All. On the
   *  Closed and Cancelled tabs it replaces `today`. */
  readonly closedWindow = input<TimeWindow | null>(null);

  readonly columns = input.required<ColumnDef<TradeRow>[]>();
  /** Per-tab column order — see R5-02. Takes the tab id so each status can
   *  show the columns that mean something for it. */
  readonly visibleFor = input.required<(tab: string) => string[]>();
  readonly pinned = input<string[]>([]);
  readonly rowKey = input.required<(row: TradeRow) => string>();
  /** What a phone row tap does (v179 §6a.4). The Dashboard sets 'emit': it
   *  opens its own trade drawer on every device, so the table's generic
   *  drawer must not open a second one. */
  readonly phoneTap = input<PhoneTap>('drawer');
  /** Rows per page: saved per device class, 10 on desktop and 5 on tablet
   *  and phone (v167). "All" is sent as the API's cap. */
  private readonly perPageState = tablePerPage('dashboard-positions');
  protected readonly perPage = this.perPageState.value;

  readonly rowActivate = output<TradeRow>();
  readonly reorder = output<string[]>();
  readonly tabChange = output<string>();

  protected readonly active = signal<string>('ACTIVE');
  private readonly page = signal(1);
  /** Equivalent bounds keep the same page; only a different result set resets it. */
  private readonly pageScope = computed(() => {
    const tab = POSITION_TABS.find((item) => item.id === this.active());
    return JSON.stringify([this.active(), this.closedScope(tab?.scoped ?? false)]);
  });

  protected readonly rows = computed(() => this.trades.rows());
  protected readonly async = computed(() => asyncInputs(
    { data: () => this.trades.empty() ? null : this.trades.rows(),
      loading: this.trades.loading, error: this.trades.error },
    { isEmpty: () => false },
  ));
  protected readonly visible = computed(() => this.visibleFor()(this.active()));
  protected readonly emptyState = computed(() => EMPTY_STATES[this.active()] ?? null);

  protected readonly tabs = computed<Tab[]>(() =>
    POSITION_TABS.map((tab) => {
      const count = this.counts()[tab.status] ?? 0;
      return { id: tab.id, label: `${tab.label} ${count}`, icon: tab.icon, count };
    }),
  );

  protected choose(id: string): void {
    if (id === this.active()) return;
    this.active.set(id);
    this.tabChange.emit(id);
  }

  /** The close-time filter for one tab: the window when there is one, else
   *  the Today flag, and nothing for the tabs that are all-time. */
  private closedScope(scoped: boolean): Pick<TradeQuery, 'today' | 'closedFrom' | 'closedTo'> {
    if (!scoped) return { today: undefined };
    const window = this.closedWindow();
    if (window) return { today: undefined, closedFrom: window.from, closedTo: window.to };
    return { today: this.today() ?? undefined };
  }

  /** The pager belongs to the selected server-side lifecycle query. */
  protected goToPage(page: number): void {
    this.page.set(page);
  }

  protected onPerPage(value: number): void {
    this.perPageState.set(value);
    this.page.set(1);
  }

  constructor() {
    // A tab or effective close filter selects a new result set. Start at its
    // first page so narrowing a paged Closed/Cancelled tab cannot hide its rows.
    effect(() => {
      this.pageScope();
      untracked(() => this.page.set(1));
    });

    // The one query. Reading `active`/`today`/`closedWindow`/`perPage`/`page` here IS the
    // subscription, so a tab change re-queries without a second code path.
    effect(() => {
      const tab = POSITION_TABS.find((t) => t.id === this.active());
      this.trades.setQuery({
        status: tab?.status ?? 'ACTIVE',
        ...this.closedScope(tab?.scoped ?? false),
        // Closed reads newest close first; every other tab by when it opened.
        sort: tab?.status === 'CLOSED' ? '-closed_at' : '-opened_at',
        page: this.page(),
        per_page: perPageForApi(this.perPage()),
      });
    });
  }
}
