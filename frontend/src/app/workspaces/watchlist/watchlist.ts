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
import { PreferencesStore } from '../../stores/preferences.store';
import { TapeStore } from '../../stores/tape.store';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { Chip } from '../../ui/chip';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { createClientPage } from '../../ui/data-table/client-page';
import { FilterChip, FilterChips } from '../../ui/filter-bar';
import { Freshness } from '../../ui/freshness';
import { readTablePerPage, writeTablePerPage } from '../../ui/table-prefs';
import { ColumnDef, RowContext, SortSpec } from '../../ui/data-table/data-table.types';
import { date, num, pct, text } from '../../ui/format';
import { Select, TextInput } from '../../ui/form-controls';
import { Icon } from '../../ui/icon';
import { Toolbar, ToolbarControl } from '../../ui/toolbar';
import { ControlRow, Panel, Tab, TabBar } from '../../ui/layout';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { Sparkline } from '../../ui/sparkline';
import { readWatchlistTags, writeWatchlistTags } from '../../ui/watchlist-prefs';
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
 *  read as "most urgent" for the one thing that carries no urgency at all.
 *
 *  `flagged` is the tape's own symbol set (`TapeStore.symbols()`) -- the
 *  'tape' column's value lives there, not on `Ticker`, so it has to be
 *  threaded in rather than read off the row like every other column. */
export function compareTickers(
  a: Ticker, b: Ticker, sort: SortSpec, flagged: readonly string[] = [],
): number {
  const dir = sort.direction === 'asc' ? 1 : -1;
  const av = sortValue(a, sort.key, flagged);
  const bv = sortValue(b, sort.key, flagged);
  if (av === null && bv === null) return 0;
  if (av === null) return 1;
  if (bv === null) return -1;
  if (av < bv) return -dir;
  if (av > bv) return dir;
  return 0;
}

function sortValue(row: Ticker, key: string, flagged: readonly string[]): string | number | null {
  switch (key) {
    case 'symbol': return row.symbol;
    case 'company_name': return row.company_name;
    case 'next_earnings_date': return row.next_earnings_date;
    case 'open_trades': return row.open_trades;
    case 'closed_trades': return row.closed_trades;
    // Same formula as the tapeCell's own `tape.symbols().includes(...)` and
    // the tape column's `value` -- flagged (0) sorts ahead of unflagged (1).
    case 'tape': return flagged.includes(row.symbol) ? 0 : 1;
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

/**
 * Column floors — v95 C7, exported for E1's parity gate.
 *
 * Module-level rather than a class member: cell templates are `viewChild`
 * (instance-scoped, unavailable until the view exists), so this carries
 * every column's shape and floor without them, and `Watchlist.columns`
 * below layers its own templates on at render time — the same split
 * Dashboard's `DASHBOARD_COLUMNS` uses over `tradeColumns()`.
 *
 * `price` and the 1-day change are what a glance at a watchlist is for; the
 * two coarser change windows and everything else wait for `md`. `symbol` is
 * deliberately left undeclared: v80 pins it because a narrow Tape toggle
 * sits before it, B2's pin exemption ignores any floor it carries anyway,
 * and declaring one would be a comment that lies about what the code does.
 */
export const WATCHLIST_COLUMNS: ColumnDef<Ticker>[] = [
  { key: 'tape', header: 'Tape', width: '1%', sortable: true, inlineFrom: 'sm' },
  { key: 'symbol', header: 'Symbol', sortable: true },
  { key: 'company_name', header: 'Company', value: (row) => text(row.company_name), sortable: true, inlineFrom: 'md' },
  { key: 'price', header: 'Price', numeric: true, inlineFrom: 'xs' },
  { key: 'change_1d_pct', header: '1D%', value: (row) => pct(row.change_1d_pct), numeric: true, inlineFrom: 'xs' },
  { key: 'change_1w_pct', header: '1W%', value: (row) => pct(row.change_1w_pct), numeric: true, inlineFrom: 'md' },
  { key: 'change_1m_pct', header: '1M%', value: (row) => pct(row.change_1m_pct), numeric: true, inlineFrom: 'md' },
  { key: 'spark', header: '30d', width: '90px', inlineFrom: 'md' },
  { key: 'signal', header: 'Signal', inlineFrom: 'md' },
  {
    key: 'next_earnings_date', header: 'Next earnings', sortable: true, inlineFrom: 'md',
    value: (row) => (row.next_earnings_date ? date(row.next_earnings_date) : null),
  },
  { key: 'open_trades', header: 'Open', value: (row) => row.open_trades, numeric: true, sortable: true, inlineFrom: 'md' },
  { key: 'closed_trades', header: 'Closed', value: (row) => row.closed_trades, numeric: true, sortable: true, inlineFrom: 'md' },
  { key: 'actions', header: '', width: '1%', inlineFrom: 'md' },
];

/**
 * What the Watchlist bar shows where — v95 C7.
 *
 * The tag filter and symbol search are how anyone narrows ten-odd rows down
 * to the one they came for, so both stay inline at every width. Add-tag and
 * the freshness marker are scope, not filters (same split Trades' export
 * link and column picker draw) and wait for `sm`.
 */
export const WATCHLIST_CONTROLS: ToolbarControl[] = [
  { id: 'tag', label: 'Tag', inlineFrom: 'xs' },
  { id: 'search', label: 'Search', inlineFrom: 'xs' },
  { id: 'add-tag', label: 'Add tag', inlineFrom: 'sm' },
  { id: 'freshness', label: 'Updated', inlineFrom: 'sm' },
];

@Component({
  selector: 'sb-watchlist',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DataTable, Panel, Button, Chip, ConfirmDialog, Toolbar, ControlRow, FilterChips, Freshness, Select, TabBar, TextInput, EarningsCalendar, RowLink, SectionHead, Async, Icon, Sparkline],
  // v54 D1: the whole point of this workspace (spec v14 Decision 9) is the
  // ticker table -- tight rows, more per screen -- so it defaults to the
  // instrument register. On the host (a static class, not a template
  // wrapper) because :host is the ancestor the register's three variables
  // need to reach.
  host: { class: 'register-instrument' },
  template: `
    <sb-section-head>
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

    <!-- v85 D35/R7-05: tag chips filter the view (never the scanner -- no
         request changes, symbols and their scan cadence are untouched);
         search narrows by symbol; add-tag and the table's own freshness
         marker are scope, not filters, same slot split trades.ts uses. -->
    <sb-toolbar [controls]="toolbarControls()">
      <sb-filter-chips
        slot="tag"
        [chips]="tagChips()"
        [selected]="tagFilter()"
        label="Tag"
        (selectedChange)="onTagChip($event)"
      />
      <sb-text-input
        slot="search"
        type="search"
        ariaLabel="Filter the watchlist by symbol"
        placeholder="Filter by symbol"
        [value]="symbolQuery()"
        (valueChange)="symbolQuery.set($event)"
      />
      <button
        slot="add-tag"
        type="button"
        class="add-tag"
        sb-button
        variant="ghost"
        (click)="addingTag.set(!addingTag())"
      >
        + Tag
      </button>
      <sb-freshness slot="freshness" [at]="maxAsOf()" />
    </sb-toolbar>

    @if (addingTag()) {
      <sb-control-row class="tag-form">
        <sb-select
          label="Symbol"
          placeholder="Choose a symbol"
          [value]="newTagSymbol()"
          (valueChange)="newTagSymbol.set($event)"
          [options]="symbolOptions()"
        />
        <sb-text-input
          label="Tag"
          placeholder="e.g. Tech"
          [value]="newTagValue()"
          (valueChange)="newTagValue.set($event)"
          (keydown.enter)="addTag()"
        />
        <button sb-button variant="primary" type="button" [disabled]="!canAddTag()" (click)="addTag()">
          Add
        </button>
      </sb-control-row>
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
          [rows]="watchlistPage.visible()"
          [columns]="columns()"
          [visible]="visible"
          [rowKey]="rowKey"
          [rowClass]="rowClassFn"
          [sort]="sort()"
          [emptyState]="emptyState"
          [pagination]="watchlistPage.pageSpec()"
          [showPerPage]="true"
          (sortChange)="setSort($event)"
          (pageChange)="watchlistPage.setPage($event)"
          (perPageChange)="onPerPage($event)"
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

    <ng-template #tapeCell let-row>
      <!-- A button, so \`data-table.ts:758\` exempts it from row activation and
           clicking the flag never navigates to the ticker. -->
      <button
        type="button"
        class="tape-toggle"
        sb-button
        variant="ghost"
        [attr.aria-pressed]="tape.symbols().includes(row.symbol)"
        [attr.aria-label]="'Show ' + row.symbol + ' in the live tape'"
        (click)="tape.toggle(row.symbol)"
      >{{ tape.symbols().includes(row.symbol) ? '◉' : '○' }}</button>
    </ng-template>

    <ng-template #symbolCell let-row>
      <sb-row-link [link]="['/watchlist', row.symbol]">{{ row.symbol }}</sb-row-link>
    </ng-template>

    <!-- v85 D33/R7-04: the price and the bar date it was computed from, in
         one cell -- the two travel together (the docstring on Ticker.as_of
         is what a lagging cache actually threatens: the PRICE, not some
         separate figure), so pairing them here is what lets the row's
         .lagging tint read as "this price is stale" rather than an
         unexplained row colour. -->
    <ng-template #priceCell let-row>
      <span class="price">{{ num(row.price) }}</span>
      <span class="as-of">{{ text(row.as_of) }}</span>
    </ng-template>

    <ng-template #sparkCell let-row>
      @if (row.spark?.length) {
        <sb-sparkline [points]="row.spark" [label]="row.symbol + ' price, last 30 bars'" />
      }
    </ng-template>

    <!-- The bot's own verdict (v85 D34). Every state carries a WORD, not
         just a tone, per the repo-wide "never colour alone" rule --
         "No setup"/"In position" read the same on a screenshot with the
         colour desaturated. -->
    <ng-template #signalCell let-row>
      <span class="signal">
        @switch (row.signal.state) {
          @case ('active') {
            <span class="signal-state">In position</span>
            @if (row.signal.strategy) { <sb-chip [label]="row.signal.strategy" tone="good" /> }
          }
          @case ('pending') {
            <span class="signal-score">{{ row.signal.score }}</span>
            @if (row.signal.horizon) { <sb-chip [label]="row.signal.horizon" /> }
            @if (row.signal.strategy) { <sb-chip [label]="row.signal.strategy" tone="info" /> }
          }
          @default {
            No setup
          }
        }
      </span>
    </ng-template>

    <ng-template #actionsCell let-row>
      <button
        sb-button
        variant="danger-icon"
        type="button"
        [attr.aria-label]="'Remove ' + row.symbol"
        (click)="ask(row)"
      >
        <sb-icon name="trash" />
      </button>
    </ng-template>
    }

    @if (activeTab() === 'earnings') {
      <sb-async
        [loading]="async().loading"
        [error]="async().error"
        [empty]="async().empty"
        emptyReason="no-data-yet"
        emptyTitle="No earnings to display"
        emptyHint="Add a ticker to start tracking earnings dates."
        [skeletonRows]="5"
        [skeletonCols]="7"
        (retry)="store.load()"
      >
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
      </sb-async>
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
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }

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

    /* Price + the bar date it came from, stacked -- the .as-of caption is
       what makes a lagging row's tint (data-table.ts's .lagging rule)
       legible rather than mysterious: it names the date that is behind. */
    .price { display: block; font-variant-numeric: tabular-nums; }
    .as-of { display: block; color: var(--text-faint); font-size: var(--register-label); }

    .signal { display: inline-flex; align-items: center; gap: var(--space-6); }
    .signal-state { font-weight: 600; color: var(--pos); }
    .signal-score { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

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
  private readonly preferences = inject(PreferencesStore);
  protected readonly tape = inject(TapeStore);
  static readonly TABLE_ID = 'watchlist';
  // Bound so the cell templates above can call them -- a template resolves
  // `{{ foo(...) }}` against the component instance, never a module import.
  protected readonly num = num;
  protected readonly text = text;
  /** Watchlist is an at-a-glance index: ten alphabetised symbols leave room
   * for each row's price and signal detail without making the first page a
   * scroll. A saved preference continues to win over this initial default. */
  protected readonly perPage = signal(
    readTablePerPage(this.preferences.values(), Watchlist.TABLE_ID, 10),
  );
  protected onPerPage(value: number): void { this.perPage.set(value); this.preferences.update((prefs) => writeTablePerPage(prefs, Watchlist.TABLE_ID, value)); }

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

  /** The + Tag mini-form (spec D35): closed by default, one symbol and one
   *  tag name at a time. */
  protected readonly addingTag = signal(false);
  protected readonly newTagSymbol = signal('');
  protected readonly newTagValue = signal('');
  protected readonly canAddTag = computed(() => this.newTagSymbol() !== '' && this.newTagValue().trim() !== '');

  protected readonly symbolOptions = computed(() =>
    [...this.store.tickers()]
      .map((row) => ({ value: row.symbol, label: row.symbol }))
      .sort((a, b) => a.value.localeCompare(b.value)),
  );

  /** Appends one tag to one symbol's list, skipping a duplicate rather than
   *  storing it twice. Written through `PreferencesStore` (spec D35) --
   *  never `data/watchlist.json`, which the bot itself reads on every scan. */
  protected addTag(): void {
    if (!this.canAddTag()) return;
    const symbol = this.newTagSymbol();
    const tag = this.newTagValue().trim();
    this.preferences.update((prefs) => {
      const tags = readWatchlistTags(prefs);
      const existing = tags[symbol] ?? [];
      if (existing.includes(tag)) return prefs;
      return writeWatchlistTags(prefs, { ...tags, [symbol]: [...existing, tag] });
    });
    this.newTagValue.set('');
  }

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
    [...this.store.tickers()].sort((a, b) => compareTickers(a, b, this.sort(), this.tape.symbols())));

  /** Symbol -> tag names (spec D35, R7-03's reader). View-only: nothing here
   *  writes `data/watchlist.json` or touches what the scanner covers. */
  protected readonly watchlistTags = computed(() => readWatchlistTags(this.preferences.values()));

  /** One chip per tag in use, sorted -- "All" is `sb-filter-chips`' own
   *  leading chip, not one of these. */
  protected readonly tagChips = computed<FilterChip[]>(() => {
    const inUse = new Set<string>();
    for (const tags of Object.values(this.watchlistTags())) {
      for (const tag of tags) inUse.add(tag);
    }
    return [...inUse].sort().map((tag) => ({ value: tag, label: tag }));
  });

  protected readonly tagFilter = signal<string | null>(null);
  protected onTagChip(value: string | null): void {
    this.tagFilter.set(value);
  }

  protected readonly symbolQuery = signal('');

  /** The tag filter and the symbol search are both a view narrowing over
   *  the already-fetched watchlist, same as the tag chip's own rule (spec
   *  D35): neither changes `store.tickers()`, so the scanner keeps covering
   *  every symbol regardless of what is on screen right now. */
  protected readonly filteredRows = computed(() => {
    let list = this.sortedRows();
    const tag = this.tagFilter();
    if (tag !== null) {
      const tags = this.watchlistTags();
      list = list.filter((row) => (tags[row.symbol] ?? []).includes(tag));
    }
    const query = this.symbolQuery().trim().toUpperCase();
    if (query) list = list.filter((row) => row.symbol.toUpperCase().includes(query));
    return list;
  });

  protected readonly watchlistPage = createClientPage(() => this.filteredRows(), () => this.perPage());

  /** The most recent `as_of` across the WHOLE watchlist -- the reference
   *  `isLagging` compares every row against. `sortedRows`, not
   *  `watchlistPage.visible()`: the brief's own reason `.lagging` exists is
   *  "a symbol the cache did not refresh must not sit silently beside
   *  eighty that did", and with the default 25-per-page (`table-prefs.ts`'s
   *  `DEFAULT_PER_PAGE`) a watchlist that size is several pages -- scoping
   *  the comparison to one rendered page would miss exactly the case this
   *  exists to catch: a stale row whose whole page happens to share its
   *  (also-stale) date, or whose true-freshest sibling sits on a different
   *  page entirely. String comparison is exact for `YYYY-MM-DD`. */
  protected readonly maxAsOf = computed<string | null>(() => {
    const dates = this.sortedRows()
      .map((row) => row.as_of)
      .filter((value): value is string => value !== null);
    return dates.length ? dates.reduce((a, b) => (a > b ? a : b)) : null;
  });

  /** A symbol the market-data cache did not refresh must be flagged, not
   *  left to sit silently beside eighty fresher rows (spec D33/R7-04). A row
   *  with no bar at all (`as_of: null`) is lagging by the same rule -- it is
   *  certainly not the freshest thing on screen. */
  private isLagging(row: Ticker): boolean {
    const max = this.maxAsOf();
    return max !== null && row.as_of !== max;
  }

  /** Bound (not a method call in the template) so DataTable's identity
   *  check on the input doesn't see a new function every change-detection
   *  pass -- an arrow field, same pattern as `rowKey` below. */
  protected readonly rowClassFn = (row: Ticker): string | null => {
    const classes: string[] = [];
    if (isWithinCurrentWeek(row.next_earnings_date)) classes.push('blink');
    if (this.isLagging(row)) classes.push('lagging');
    // The Signal cell already says "In position" in words -- this is the
    // second, scannable cue the "never colour alone" rule asks for, same
    // background-tint convention as .lagging (data-table.ts).
    if (row.open_trades > 0) classes.push('has-position');
    return classes.length ? classes.join(' ') : null;
  };

  protected readonly rowKey = (row: Ticker) => row.symbol;

  protected readonly emptyState = {
    title: 'Nothing on the watchlist',
    hint: 'Add a symbol above and the scanner will start covering it.',
  };

  private readonly tapeCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('tapeCell');
  private readonly symbolCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('symbolCell');
  private readonly priceCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('priceCell');
  private readonly sparkCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('sparkCell');
  private readonly signalCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('signalCell');
  private readonly actionsCell =
    viewChild.required<TemplateRef<RowContext<Ticker>>>('actionsCell');

  protected readonly visible = [
    'tape', 'symbol', 'company_name', 'price', 'change_1d_pct', 'change_1w_pct', 'change_1m_pct',
    'spark', 'signal', 'next_earnings_date', 'open_trades', 'closed_trades', 'actions',
  ];

  /** v95 C7: layers this instance's cell templates onto the module-level
   *  WATCHLIST_COLUMNS, the same split Dashboard's own `columns` uses over
   *  `tradeColumns()` -- the floors live in one shared place, not duplicated
   *  per render path. */
  protected readonly columns = computed<ColumnDef<Ticker>[]>(() => {
    const cells: Partial<Record<string, TemplateRef<RowContext<Ticker>>>> = {
      tape: this.tapeCell(),
      symbol: this.symbolCell(),
      price: this.priceCell(),
      spark: this.sparkCell(),
      signal: this.signalCell(),
      actions: this.actionsCell(),
    };
    return WATCHLIST_COLUMNS.map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column,
    );
  });

  /** Guard 1 (v95 §5): the sheet must say when something inside it is
   *  narrowing the table. */
  protected readonly toolbarControls = computed<ToolbarControl[]>(() =>
    WATCHLIST_CONTROLS.map((control) => ({
      ...control,
      active: control.id === 'tag' ? this.tagFilter() !== null
        : control.id === 'search' ? this.symbolQuery().length > 0
        : false,
    })),
  );

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
