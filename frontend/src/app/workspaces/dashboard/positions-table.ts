import {
  ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { TradeRow } from '../../api/models';
import { TradesStore } from '../../stores/trades.store';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, EmptyState } from '../../ui/data-table/data-table.types';
import { STATUS_ICON } from '../../ui/icon';
import { Tab, TabBar } from '../../ui/layout';

/** A cap, not a page — the Dashboard answers "what is happening right now" at
 *  a glance, and a glance does not scroll. Paging lives in Trades. */
export const OPEN_POSITIONS_CAP = 6;

/** Lifecycle order, not size order: this is the order a plan moves through,
 *  and sorting by count would reshuffle the strip every time a trade closed.
 *  icon reuses icon.ts's own STATUS_ICON map -- the same one Recent
 *  Activity's status glyph reads -- so both panels share one vocabulary
 *  rather than each inventing its own (2026-09-14: icons were deliberately
 *  kept OUT of the row-level StatusCell here, but the TAB strip is a
 *  different surface -- it names a whole group, not one row's status, and
 *  is exactly what a mobile-width icon-only tab needs to stay legible). */
export const POSITION_TABS: (Tab & { status: string; scoped: boolean })[] = [
  { id: 'ACTIVE',    label: 'Open',      icon: STATUS_ICON['ACTIVE'],    status: 'ACTIVE',    scoped: false },
  { id: 'PENDING',   label: 'Pending',   icon: STATUS_ICON['PENDING'],   status: 'PENDING',   scoped: false },
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
 */
@Component({
  selector: 'sb-positions-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TabBar, DataTable, RouterLink],
  providers: [TradesStore],
  template: `
    <sb-tab-bar [tabs]="tabs()" [active]="active()" (activeChange)="choose($event)" />

    <div class="table-head">
      <a class="all-link" routerLink="/trades" [queryParams]="{ status: active() }">
        View in Trades →
      </a>
      <ng-content select="[table-actions]" />
    </div>

    <sb-data-table
      [rows]="rows()"
      [columns]="columns()"
      [visible]="visible()"
      [pinned]="pinned()"
      [rowKey]="rowKey()"
      [emptyState]="emptyState()"
      (rowActivate)="rowActivate.emit($event)"
      (reorder)="reorder.emit($event)"
    />
  `,
  styles: `
    :host { display: block; }
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
  readonly columns = input.required<ColumnDef<TradeRow>[]>();
  /** Per-tab column order — see R5-02. Takes the tab id so each status can
   *  show the columns that mean something for it. */
  readonly visibleFor = input.required<(tab: string) => string[]>();
  readonly pinned = input<string[]>([]);
  readonly rowKey = input.required<(row: TradeRow) => string>();
  readonly cap = input(OPEN_POSITIONS_CAP);

  readonly rowActivate = output<TradeRow>();
  readonly reorder = output<string[]>();
  readonly tabChange = output<string>();

  protected readonly active = signal<string>('ACTIVE');
  private readonly page = signal(1);

  protected readonly rows = computed(() => this.trades.rows());
  protected readonly visible = computed(() => this.visibleFor()(this.active()));
  protected readonly emptyState = computed(() => EMPTY_STATES[this.active()] ?? null);

  protected readonly tabs = computed<Tab[]>(() =>
    POSITION_TABS.map((tab) => ({
      id: tab.id,
      label: `${tab.label} ${this.counts()[tab.status] ?? 0}`,
      icon: tab.icon,
    })),
  );

  protected choose(id: string): void {
    if (id === this.active()) return;
    this.active.set(id);
    this.tabChange.emit(id);
  }

  constructor() {
    // Page resets on tab change: landing on page 3 of a table you just
    // switched to shows a slice of something you have not seen the start of.
    effect(() => {
      this.active();
      untracked(() => this.page.set(1));
    });

    // The one query. Reading `active`/`today`/`cap`/`page` here IS the
    // subscription, so a tab change re-queries without a second code path.
    effect(() => {
      const tab = POSITION_TABS.find((t) => t.id === this.active());
      this.trades.setQuery({
        status: tab?.status ?? 'ACTIVE',
        today: tab?.scoped ? (this.today() ?? undefined) : undefined,
        sort: '-opened_at',
        page: this.page(),
        per_page: this.cap(),
      });
    });
  }
}
