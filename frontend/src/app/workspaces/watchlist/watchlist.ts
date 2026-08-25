import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';

import { Ticker } from '../../api/models';
import { WatchlistStore } from '../../stores/watchlist.store';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, RowContext, SortSpec } from '../../ui/data-table/data-table.types';
import { date, text } from '../../ui/format';
import { TextInput } from '../../ui/form-controls';
import { ControlRow, Panel, Tab, TabBar } from '../../ui/layout';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { EarningsCalendar } from './earnings-calendar';

const TABS: Tab[] = [
  { id: 'watchlist', label: 'Watchlist' },
  { id: 'earnings', label: 'Earnings' },
];
const TAB_IDS = new Set(TABS.map((t) => t.id));

/** Monday 00:00 through Sunday 23:59:59 of the week containing `now` --
 *  matches the calendar's own Monday-first week, so "this week" means the
 *  same seven days in both places. */
function currentWeekBounds(now: Date): { start: Date; end: Date } {
  const mondayOffset = (now.getDay() + 6) % 7;
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - mondayOffset);
  const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 6,
                       23, 59, 59, 999);
  return { start, end };
}

export function isWithinCurrentWeek(isoDate: string | null): boolean {
  if (!isoDate) return false;
  const [y, m, d] = isoDate.split('-').map(Number);
  const day = new Date(y, m - 1, d);
  const { start, end } = currentWeekBounds(new Date());
  return day >= start && day <= end;
}

/** Ascending by default (soonest first); a ticker with no known date sorts
 *  LAST regardless of direction -- "unknown" is not meaningfully before or
 *  after a real date, and floating it to the top of a descending sort would
 *  read as "most urgent" for the one thing that carries no urgency at all. */
export function compareTickers(a: Ticker, b: Ticker, sort: SortSpec): number {
  const dir = sort.direction === 'asc' ? 1 : -1;
  const av = sortValue(a, sort.key);
  const bv = sortValue(b, sort.key);
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  if (av < bv) return -dir;
  if (av > bv) return dir;
  return 0;
}

function sortValue(row: Ticker, key: string): string | number | null {
  switch (key) {
    case 'symbol': return row.symbol;
    case 'company_name': return row.company_name;
    case 'next_earnings_date': return row.next_earnings_date;
    case 'open_trades': return row.open_trades;
    case 'closed_trades': return row.closed_trades;
    default: return null;
  }
}

/**
 * Watchlist — the watchlist the scanner walks.
 *
 * Deliberately the thinnest workspace (spec v14 Decision 9): a table, an add
 * box and a remove button. Everything interesting about a symbol is one
 * click away on its detail view, and nothing here duplicates it.
 *
 * **One add box for single and bulk.** The endpoint absorbs both, so a
 * separate "bulk import" would be a second path to the same place with its
 * own validation to drift. Type one symbol and press Enter, or paste thirty
 * — the box splits on commas and whitespace either way, and the result names
 * what was added, what was already there and what was rejected.
 *
 * `DataTableComponent` is the fourth and last of its call sites (spec v14's
 * definition of done, property 3). A second table implementation anywhere is
 * a defect, and this screen is small enough to have been tempting.
 */
@Component({
  selector: 'sb-watchlist',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DataTable, Panel, Button, ConfirmDialog, ControlRow, TabBar, TextInput, EarningsCalendar, RowLink, SectionHead, Async],
  // v54 D1: the whole point of this workspace (spec v14 Decision 9) is the
  // ticker table -- tight rows, more per screen -- so it defaults to the
  // instrument register. On the host (a static class, not a template
  // wrapper) because :host is the ancestor the register's three variables
  // need to reach.
  host: { class: 'register-instrument' },
  providers: [WatchlistStore],
  template: `
    <sb-section-head heading="Watchlist">
      <!-- One wrapper, not two separate actions projections -- otherwise
           .count and .stale land at opposite ends of the space-between
           row instead of clustered beside each other. -->
      <div actions class="head-status">
        <span class="count">{{ store.count() }} watched</span>
        <!-- Only for Earnings: the Watchlist tab's own sb-async already
             turns this same store.error() into a scoped error panel or
             demoted stale badge on the table below, so showing it here too
             would duplicate it. Earnings has no sb-async of its own -- it
             renders sb-earnings-calendar from store.tickers(), which stays
             on its last good value on a refetch failure -- so this remains
             its only error surface. -->
        @if (activeTab() === 'earnings' && store.error(); as message) {
          <span class="stale" role="status">{{ message }}</span>
        }
      </div>
    </sb-section-head>

    <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

    @if (activeTab() === 'watchlist') {
    <sb-panel heading="Add tickers">
      <!-- SR62. watchlist.html:85-92. The gap table calls this the one
           cosmetic row with a functional consequence: an add that fails
           because the symbol format is wrong gives no hint what the right
           format was, and the format is not guessable. -->
      <p class="section-help">
        Ticker symbols must match Yahoo Finance format — e.g.
        <code>ASML.AS</code> for Euronext, <code>BTC-USD</code> for crypto,
        <code>^GSPC</code> for the S&amp;P 500 index. After adding or removing
        a ticker, the change takes effect on the next <code>!check</code> or
        scheduled background scan.
      </p>
      <sb-control-row class="add">
        <div class="box">
          <!-- (focusout), not (blur): blur does not bubble, so a listener on
               this host element would never see the inner input element lose
               focus. focusout is blur's bubbling equivalent. -->
          <sb-text-input
            class="input"
            [value]="entry()"
            (valueChange)="onEntry($event)"
            (keydown.enter)="add()"
            (focusout)="closeSuggestions()"
            placeholder="AAPL, or paste a list"
            ariaLabel="Ticker symbols to add"
          />

          @if (store.suggestions().length) {
            <!-- mousedown, not click: blur fires first on a click and would
                 close the list before the handler ran. -->
            <ul class="suggestions">
              @for (hit of store.suggestions(); track hit.symbol) {
                <li>
                  <button sb-button variant="ghost" type="button" (mousedown)="pick(hit.symbol)">
                    <span class="hit-symbol">{{ hit.symbol }}</span>
                    <span class="hit-name">{{ hit.name }}</span>
                    @if (store.symbols().has(hit.symbol)) {
                      <!-- Said before the round trip, because being told
                           "already watched" by the server is a request the
                           screen already had the answer to. -->
                      <span class="hit-have">watched</span>
                    }
                  </button>
                </li>
              }
            </ul>
          }
        </div>

        <button
          sb-button
          variant="primary"
          type="button"
          [loading]="store.adding()"
          [disabled]="!entry().trim()"
          (click)="add()"
        >
          Add
        </button>
      </sb-control-row>

      @if (store.addResult(); as message) {
        <p class="result" role="status">{{ message }}</p>
      }
      @if (store.addError(); as message) {
        <p class="error" role="alert">{{ message }}</p>
      }
    </sb-panel>

    @if (store.removeError(); as message) {
      <p class="error" role="alert">{{ message }}</p>
    }

    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="no-data-yet"
      emptyTitle="No tickers on the watchlist"
      emptyHint="Add a ticker to start scanning."
      [skeletonRows]="10"
      [skeletonCols]="4"
      [announce]="announce()"
      (retry)="store.load()"
    >
      <sb-panel heading="Watchlist" [flush]="true">
        <!-- A row blinks when its earnings date falls within the current
             week (Monday-Sunday, same boundary the Earnings tab's calendar
             uses) -- a gentle pulse, not a hard flash; see data-table.ts's
             .blink rule and its prefers-reduced-motion fallback. -->
        <p class="section-help panel-note">
          A row pulses when that ticker reports earnings this week.
        </p>
        <sb-data-table
          [rows]="sortedRows()"
          [columns]="columns()"
          [visible]="visible"
          [rowKey]="rowKey"
          [rowClass]="rowClassFn"
          [sort]="sort()"
          [emptyState]="emptyState"
          (sortChange)="setSort($event)"
          (rowActivate)="open($event)"
        />
      </sb-panel>
    </sb-async>

    <sb-confirm-dialog
      [open]="pending() !== null"
      title="Remove from the watchlist"
      [consequence]="consequence()"
      confirmLabel="Remove"
      [working]="store.removing() !== null"
      (confirmed)="remove()"
      (cancelled)="pending.set(null)"
    />

    <!-- cells ----------------------------------------------------------- -->

    <ng-template #symbolCell let-row>
      <sb-row-link [link]="['/watchlist', row.symbol]">{{ row.symbol }}</sb-row-link>
    </ng-template>

    <ng-template #actionsCell let-row>
      <button sb-button variant="ghost" type="button" (click)="ask(row)">Remove</button>
    </ng-template>
    }

    @if (activeTab() === 'earnings') {
      <sb-panel heading="Earnings">
        <p class="section-help">
          Every watchlist ticker's next known earnings date, one cell per
          day. Only tickers currently on the watchlist appear here, and a
          newly-added one shows up the next time this page loads — same
          data as the Watchlist tab's "Next earnings" column, just grouped
          by date instead of by ticker.
        </p>
        <sb-earnings-calendar [tickers]="store.tickers()" />
      </sb-panel>
    }
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    /* v54 D1: --space-20 was this rule's own literal before the registers
       existed; --register-pad's instrument rung is --space-10, so both
       gaps below shrink. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--register-pad); }

    .head-status { display: flex; align-items: baseline; gap: var(--register-pad); }
    /* The count caption beside the section head -- --text-table (13px)
       shrinks to the instrument rung (11px); never grows. */
    .count { color: var(--text-secondary); font-size: var(--register-label); }

    /* Was align-items: flex-start, which is why the Add button sat level with
       the input's top edge rather than its box. sb-control-row's flex-end is
       the fix; nothing here is the row's own any more. */
    .box { position: relative; flex: 1 1 auto; max-width: 420px; }
    /* sb-text-input's own template is unreachable from here (encapsulation),
       so only host-box layout and the naturally-inherited font-family
       survive as overrides -- background/padding/border/focus-ring are now
       the primitive's, and its placeholder loses the old sans-vs-mono
       distinction as a result. */
    .input { display: block; width: 100%; font-family: var(--font-mono); }

    .suggestions {
      position: absolute;
      z-index: 2;
      inset-inline: 0;
      margin-top: var(--space-4);
      max-height: 240px;
      overflow-y: auto;
      background: var(--surface-raised);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
    }
    /* justify-content/align-items/width/colour/font override the ghost
       variant's defaults for a full-width, baseline-aligned result row;
       the variant owns background and hover. */
    .suggestions button {
      justify-content: flex-start;
      align-items: baseline;
      gap: var(--space-8);
      width: 100%;
      padding: var(--space-4) var(--space-8);
      border: 0;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
    }
    .hit-symbol { font-family: var(--font-mono); }
    .hit-name { color: var(--text-secondary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .hit-have { margin-left: auto; color: var(--text-faint); font-size: var(--register-label); }

    .result { margin-top: var(--space-10); color: var(--text-secondary); font-size: var(--text-table); }

    sb-row-link { color: var(--accent); font-family: var(--font-mono); }

    /* The Watchlist panel is flush (the table needs edge-to-edge rows),
       which zeroes the body's own padding -- restores just the left/right
       inset so this note lines up with the panel heading above it, same
       fix as Dashboard's .panel-note. */
    .panel-note { padding: var(--register-pad) var(--register-pad) 0; }
  `,
})
export class Watchlist {
  private readonly router = inject(Router);
  protected readonly store = inject(WatchlistStore);

  /** `store.empty()` means "not loaded yet" (a boolean, not nullable data),
   *  so the nullable `data` asyncInputs() expects is synthesised here rather
   *  than added to the store for this one call site. */
  protected readonly async = computed(() =>
    asyncInputs(
      {
        data: () => (this.store.empty() ? null : this.store.tickers()),
        loading: this.store.loading,
        error: this.store.error,
      },
      { isEmpty: (tickers) => tickers.length === 0 },
    ),
  );

  /** A polite summary for the workspace's one live region — null until the
   *  watchlist has loaded. */
  protected readonly announce = computed(() =>
    this.store.empty() ? null : `${this.store.count()} tickers`,
  );

  protected readonly tabs = TABS;
  /** Bound from `?tab=` via the app-wide withComponentInputBinding(), same
   *  as Analytics. An unknown or absent value falls back to Watchlist. */
  readonly tab = input<string>();
  protected readonly activeTab = computed(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested) ? requested : 'watchlist';
  });

  protected goToTab(tab: string): void {
    void this.router.navigate([], {
      queryParams: { tab: tab === 'watchlist' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  protected readonly entry = signal('');
  /** The row awaiting confirmation, or null. */
  protected readonly pending = signal<Ticker | null>(null);

  /** Client-side: the whole watchlist loads in one plain-list response
   *  (data-table.ts's PageSpec convention -- Watchlist is one of the three
   *  unpaginated call sites), so sorting is a local re-order of what is
   *  already on screen rather than a server round trip.
   *
   *  Defaults to soonest-earnings-first: the whole point of the Earnings
   *  work is "what's coming up", and the table should open already
   *  answering that without a click. */
  protected readonly sort = signal<SortSpec>({ key: 'next_earnings_date', direction: 'asc' });

  protected setSort(next: SortSpec): void {
    this.sort.set(next);
  }

  protected readonly sortedRows = computed(() =>
    [...this.store.tickers()].sort((a, b) => compareTickers(a, b, this.sort())));

  /** Bound (not a method call in the template) so DataTable's identity
   *  check on the input doesn't see a new function every change-detection
   *  pass -- an arrow field, same pattern as `rowKey` below. */
  protected readonly rowClassFn = (row: Ticker): string | null =>
    isWithinCurrentWeek(row.next_earnings_date) ? 'blink' : null;

  protected readonly rowKey = (row: Ticker) => row.symbol;

  protected readonly emptyState = {
    title: 'Nothing on the watchlist',
    hint: 'Add a symbol above and the scanner will start covering it.',
  };

  private readonly symbolCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('symbolCell');
  private readonly actionsCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('actionsCell');

  protected readonly visible = [
    'symbol', 'company_name', 'next_earnings_date', 'open_trades', 'closed_trades', 'actions',
  ];

  protected readonly columns = computed<ColumnDef<Ticker>[]>(() => [
    { key: 'symbol', header: 'Symbol', cell: this.symbolCell(), sortable: true },
    { key: 'company_name', header: 'Company', value: (row) => text(row.company_name), sortable: true },
    {
      key: 'next_earnings_date', header: 'Next earnings', sortable: true,
      value: (row) => (row.next_earnings_date ? date(row.next_earnings_date) : null),
    },
    { key: 'open_trades', header: 'Open', value: (row) => row.open_trades, numeric: true, sortable: true },
    { key: 'closed_trades', header: 'Closed', value: (row) => row.closed_trades, numeric: true, sortable: true },
    { key: 'actions', header: '', cell: this.actionsCell(), width: '1%' },
  ]);

  protected readonly consequence = computed(() => {
    const row = this.pending();
    if (!row) return '';
    const held = row.open_trades
      ? ` It has ${row.open_trades} open position${row.open_trades === 1 ? '' : 's'}, which stay open and keep being monitored.`
      : '';
    // Naming what does NOT happen matters as much here: removing a symbol
    // stops future scanning, and someone expecting it to close positions
    // would be wrong in the dangerous direction.
    return `${row.symbol} will no longer be scanned for new setups.${held} Its trade history is kept.`;
  });

  protected onEntry(value: string): void {
    this.entry.set(value);
    // Only the last fragment is a query: pasting a list should not fire a
    // suggestion request for the whole blob.
    const last = value.split(/[,\s]+/).pop() ?? '';
    this.store.suggest(last);
  }

  protected pick(symbol: string): void {
    // Replaces the fragment being typed, keeping anything already entered
    // before it — so picking from the list works mid-paste as well.
    const parts = this.entry().split(/[,\s]+/);
    parts[parts.length - 1] = symbol;
    this.entry.set(parts.join(', '));
    this.store.clearSuggestions();
  }

  protected closeSuggestions(): void {
    this.store.clearSuggestions();
  }

  protected add(): void {
    this.store.addTickers(this.entry());
    this.entry.set('');
  }

  protected ask(row: Ticker): void {
    this.pending.set(row);
  }

  protected remove(): void {
    const row = this.pending();
    if (!row) return;
    this.store.removeTicker(row.symbol);
    this.pending.set(null);
  }

  protected open(row: Ticker): void {
    void this.router.navigate(['/watchlist', row.symbol]);
  }
}
