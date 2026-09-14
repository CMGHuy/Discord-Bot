import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { CLOCK } from '../../ui/clock';

import { ApiClient } from '../../api/api-client';
import { TradeQuery, TradeRow } from '../../api/models';
import { Async, asyncInputs } from '../../ui/async';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { Density } from '../../ui/data-table/data-table.types';
import {
  perPageForApi,
  readTableColumns,
  readTableDensity,
  readTablePerPage,
  writeTableColumns,
  writeTableDensity,
  writeTablePerPage,
} from '../../ui/table-prefs';
import { TradesStore, toSortParam } from '../../stores/trades.store';
import { Button } from '../../ui/button';
import { QualityChip } from '../../ui/chip';
import { ColumnPickerComponent } from '../../ui/column-picker';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef, SortSpec } from '../../ui/data-table/data-table.types';
import { FilterBar, FilterChips } from '../../ui/filter-bar';
import { Flash } from '../../ui/flash';
import { dateTime, money, pct, signed, text } from '../../ui/format';
import { Magnitude } from '../../ui/magnitude';
import { Select, TextInput } from '../../ui/form-controls';
import { ControlRow } from '../../ui/layout';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { ConfidenceCell } from '../../ui/confidence-cell';
import { ControlBar } from '../../ui/control-bar';
import { DateRange } from '../../ui/date-range';
import { DirectionArrow } from '../../ui/direction-arrow';
import { PlanCell, bankedLegAmount, bankedLegPct } from '../../ui/plan-cell';
import { StatusCell } from '../../ui/status-cell';
import {
  ACTION_LABELS,
  ACTION_TITLES,
  TradeActionKind,
  actionConsequence,
  availableActions,
  runTradeAction,
} from './trade-actions';
import {
  COMPACT_COLUMNS,
  FULL_COLUMNS,
  PINNED_COLUMNS,
  TRADES_TABLE_ID,
  tradeColumns,
} from './trades.columns';

type PendingAction = { kind: TradeActionKind; row: TradeRow } | null;

/**
 * One promoted chip in the control bar's status/outcome/direction lane
 * (v85 D32). `param` says which of the three query keys the chip drives;
 * `onLaneChip` always writes all three together so switching chips can
 * never leave a stale value from one of the other two behind.
 */
interface LaneChip {
  value: string;
  label: string;
  param: 'status' | 'outcome' | 'direction';
}

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
  // v54 D1: this workspace is a table (plus the row-expansion detail grid
  // below it) -- tight rows, more per screen -- so it defaults to the
  // instrument register. On the host (a static class, not a template
  // wrapper) because :host is the ancestor the register's three variables
  // need to reach.
  host: { class: 'register-instrument' },
  imports: [
    Async,
    ControlRow,
    ControlBar,
    DataTable,
    DateRange,
    ColumnPickerComponent,
    FilterBar,
    FilterChips,
    Select,
    TextInput,
    Button,
    ConfirmDialog,
    Flash,
    StatusCell,
    DirectionArrow,
    PlanCell,
    ConfidenceCell,
    Magnitude,
    QualityChip,
    RowLink,
    SectionHead,
  ],
  template: `
    <sb-section-head>
      <sb-control-row actions class="head-actions">
        <button sb-button variant="ghost" type="button" (click)="bulk.set('open')">
          Clear open
        </button>
        <button sb-button variant="ghost" type="button" (click)="bulk.set('history')">
          Clear history
        </button>
        <div class="density" role="group" aria-label="Row density">
          <button
            sb-button
            variant="ghost"
            type="button"
            [attr.aria-pressed]="density() === 'compact'"
            (click)="setDensity('compact')"
          >
            Compact
          </button>
          <button
            sb-button
            variant="ghost"
            type="button"
            [attr.aria-pressed]="density() === 'full'"
            (click)="setDensity('full')"
          >
            Full
          </button>
        </div>
      </sb-control-row>
    </sb-section-head>

    @if (store.clearResult(); as message) {
      <!-- The count, not just "done": "cleared 0" and "cleared 40" are
           different answers and want different reactions. -->
      <p class="cleared" role="status">{{ message }}</p>
    }
    @if (store.clearError(); as message) {
      <p class="command-error" role="alert">{{ message }}</p>
    }

    <!-- v85 D32: the eight controls actually reached for -- status, outcome
         and direction -- promoted out of the collapsible filter bar below
         into the shared control bar, one click instead of two. sb-filter-chips
         (not deprecated sb-segmented: this lane needs the "All" leading chip
         and the three-key write onLaneChip already provides) still owns the
         chip markup; only its data and handler changed. The export link and
         column picker move into the bar's scope slot -- they are the two
         controls the mockup's own asset-class lane sat beside, not filters. -->
    <sb-control-bar>
      <sb-filter-chips
        filters
        [chips]="laneChips"
        [selected]="laneSelected()"
        label="Status"
        (selectedChange)="onLaneChip($event)"
      />
      <!-- v85 D32: the opened-at range. A scope control, not a filter-bar
           filter -- it narrows WHEN, not WHAT, the same distinction that
           already separates this bar's two slots for the export link and
           column picker beside it. -->
      <sb-date-range
        scope
        [from]="opened_from() ?? null"
        [to]="opened_to() ?? null"
        (changed)="onDateRange($event)"
      />
      <!-- A plain anchor, not a fetch: the browser gets a Save dialog and
           the server's filename, both of which an XHR throws away.
           The title names what comes out, because it is NOT what is on
           screen: the export is the whole trade log, unfiltered. Saying so
           here is the same courtesy the two Clear dialogs already pay. -->
      <a
        scope
        class="export"
        [href]="store.exportUrl()"
        title="Downloads the entire trade log. The filters above do not narrow it."
        download
        >Export CSV</a
      >
      <sb-column-picker
        scope
        [tableId]="tableId"
        [density]="density()"
        [pinned]="pinned"
        [columns]="allColumns()"
        [defaults]="defaultColumns()"
        [visible]="visible()"
        (visibleChange)="visible.set($event)"
      />
    </sb-control-bar>

    <sb-filter-bar [activeCount]="store.activeFilterCount()" (cleared)="clearFilters()">
      <sb-text-input
        type="search"
        label="Ticker"
        placeholder="AAPL"
        [value]="ticker() ?? ''"
        (valueChange)="navigate({ ticker: $event })"
      />
      <sb-select
        label="Origin"
        placeholder="Any"
        [value]="origin() ?? ''"
        [options]="originOptions"
        (valueChange)="navigate({ origin: $event })"
      />

      <!-- SR52. The five the parity audit found, in the order they narrow a
           search: what the setup was, then how it was graded, then whether it
           has been written up. Eight controls is a lot for one bar (Direction
           moved to the control bar's chip lane at v85 D32), which is why the
           filter bar wraps and reports how many are active. -->
      <sb-text-input
        type="search"
        label="Strategy"
        placeholder="RSI"
        [value]="strategy() ?? ''"
        (valueChange)="navigate({ strategy: $event })"
      />
      <sb-select
        label="Horizon"
        placeholder="Any"
        [value]="horizon() ?? ''"
        [options]="horizonOptions"
        (valueChange)="navigate({ horizon: $event })"
      />
      <sb-select
        label="Confidence"
        placeholder="Any"
        [value]="confidence() ?? ''"
        [options]="confidenceOptions"
        (valueChange)="navigate({ confidence: $event })"
      />
      <sb-select
        label="Tier"
        placeholder="Any"
        [value]="tier() ?? ''"
        [options]="tierOptions"
        (valueChange)="navigate({ tier: $event })"
      />
      <sb-select
        label="Badge"
        placeholder="Any"
        [value]="badge() ?? ''"
        [options]="badgeOptions"
        (valueChange)="navigate({ badge: $event })"
      />
      <sb-select
        label="Note"
        placeholder="Any"
        [value]="has_note() ?? ''"
        [options]="noteOptions"
        (valueChange)="navigate({ has_note: $event })"
      />
    </sb-filter-bar>

    <!-- v54: rows=12 cols=8, measured against a full table page at Slow
         3G (Task 21 G6). measured-zero always -- an empty filtered set is
         a measured answer, not missing data; asyncInputs already suppresses
         no-data-yet for the pre-first-response case. -->
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      [emptyTitle]="store.activeFilterCount() > 0 ? 'No trades match this filter' : 'No trades yet'"
      [emptyHint]="store.activeFilterCount() > 0 ? 'Clear the filters to see the full log.' : undefined"
      [skeletonRows]="12"
      [skeletonCols]="8"
      [announce]="announce()"
      (retry)="store.load()"
    >
      <sb-data-table
        [rows]="store.rows()"
        [columns]="allColumns()"
        [visible]="visible()"
        [rowKey]="rowKey"
        [sort]="store.sort()"
        [pagination]="store.pagination()"
        [expansion]="expansionTemplate()"
        (sortChange)="onSort($event)"
        (pageChange)="navigate({ page: $event }, false)"
        (rowActivate)="open($event)"
        [pinned]="pinned"
        (reorder)="onReorder($event)"
        [showPerPage]="true"
        (perPageChange)="onPerPage($event)"
      />
    </sb-async>

    <!-- R6-05: the count footer. Lives outside sb-async on purpose --
         store.pagination() is set as soon as the first response lands,
         table or no table, so this still has an answer when async() is
         showing its own empty state instead of sb-data-table (which happens
         whenever the page is empty, and is why this can't be reached from
         inside sb-pagination's own [pagination] binding). Beside, not
         instead of, that pager's own range span: this is the one that
         distinguishes a filter that matched nothing from a genuinely empty
         log, the same measured-zero distinction emptyTitle above already
         draws. -->
    @if (countText(); as count) {
      <p class="count">{{ count }}</p>
    }

    <!-- cells ---------------------------------------------------------- -->

    <ng-template #numCell let-row>
      <sb-row-link [link]="['/trades', row.id]">{{ shortId(row) }}</sb-row-link>
    </ng-template>

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
        [stopKind]="row.stop_kind"
        [targetIsBankedTp1]="row.target_is_banked_tp1"
        [floorR]="row.floor_r" [priceR]="row.price_r" [headroomR]="row.headroom_r"
        [bankedFraction]="row.banked_fraction"
        [bankedR]="row.banked_r"
        [bankedEntry]="row.banked_exit_price"
        [bankedPct]="bankedLegPct(row.entry, row.banked_exit_price, row.direction)"
        [bankedAmount]="bankedLegAmount(row.entry, row.banked_exit_price, row.banked_fraction, row.shares, row.direction)"
        [currency]="connection.currency()"
      />
    </ng-template>

    <!-- See dashboard.ts's own pnlCell -- same pairing, same reasoning:
         the % alone doesn't say how much money that was. The percentage
         carries its unit (fmtPct, not fmtSigned) because this cell holds
         two figures in two different units, and on a phone the header sits
         in a <dt> beside them rather than above a column -- see
         dashboard.ts's fmtPct note for the full reversal of v54 Task 28. -->
    <ng-template #pnlCell let-row>
      <span [sbFlash]="row.pnl_pct" [class]="pnlClass(row.pnl_pct)">
        {{ fmtPct(row.pnl_pct) }}
        <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
      </span>
    </ng-template>

    <!-- v54 Task 28: sb-magnitude beneath the R figure -- the header ('R')
         already names the unit, so the cell drops it (signed(), not
         rMultiple()). -->
    <ng-template #rMultipleCell let-row>
      <span [sbFlash]="row.r_multiple" [class]="pnlClass(row.r_multiple)">{{ fmtSigned(row.r_multiple) }}</span>
      <sb-magnitude [value]="row.r_multiple" [max]="maxRMultiple()" />
    </ng-template>

    <ng-template #tierCell let-row>
      @if (row.tier) {
        <sb-quality-chip [value]="row.tier" [label]="row.tier" />
      }
    </ng-template>

    <ng-template #confidenceCell let-row>
      <sb-confidence-cell [level]="row.confidence_level" [score]="row.confidence_score" />
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
      <!-- Label/value grid. SR24 reuses this markup verbatim for the phone
           card, so its shape has a second consumer -- change it here and the
           card changes with it. -->
      <div class="groups">
        <dl>
          <dt class="group">Hidden in this view</dt>
          @for (field of hiddenFields(); track field.key) {
            <div>
              <dt>{{ field.header }}</dt>
              <dd [class.num]="field.numeric">{{ field.render(row) }}</dd>
            </div>
          } @empty {
            <div><dd class="none">Every column is showing.</dd></div>
          }
        </dl>
        <dl>
          <!-- Never columns at any density, so the expansion is the only
               place they can live.
               The task names target sources, the leg breakdown and the note.
               None of the three is on TradeRow -- they are TradeDetail
               fields, and this template renders a row. Showing them would
               mean a fetch per expanded row. These are the row's own
               never-column fields; the rest stay one click away in the
               detail view, which is where the row already links to. -->
          <dt class="group">Detail</dt>
          <div><dt>Tier</dt><dd>{{ fmtText(row.tier) }}</dd></div>
          <div><dt>Badge</dt><dd>{{ fmtText(row.badge) }}</dd></div>
          <div><dt>Quality</dt><dd class="num">{{ fmtNum(row.quality_score, 0) }}</dd></div>
          <div><dt>Note</dt><dd>{{ row.has_note ? 'Yes' : 'No' }}</dd></div>
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
    /* sb-control-row supplies display, alignment, wrap and gap. */
    .export { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .export:hover { text-decoration: underline; }

    .cleared { color: var(--text-secondary); font-size: var(--text-table); }
    /* Red rather than the amber error style above: that one means "a poll
       failed, these numbers are stale", and this one means "the thing you
       asked for did not happen". */
    .command-error { color: var(--neg); font-size: var(--text-table); }

    /* R6-05. Same voice as sb-pagination's own .range (muted, --text-table)
       so the two read as one family, not a mismatched addition. */
    .count { color: var(--text-secondary); font-size: var(--text-table); margin: var(--space-4) 0; }

    sb-row-link { color: var(--accent); font-family: var(--font-mono); }

    /* No size or colour of its own -- it used to render smaller and muted,
       which read as a footnote rather than the dollar side of the same
       figure the % (pnlClass, above) already names. Both are the headline
       number now, just in different units, so it inherits pnlClass()'s
       colour from the span it sits inside instead of its own muted tone. */

    .actions { display: inline-flex; gap: var(--space-4); }

    /* v54 D1: instrument register. gap/padding were --space-20/--space-10
       --space-14 -- both shrink to the tighter --register-pad rung (10px),
       which is the whole point of this being a table's row-expansion detail
       rather than a presentation panel. dl's own inner gap and .actions'
       stay hardcoded at --space-4, below the register-pad rung -- routing
       them through the var would GROW those, which is exactly the
       regression this register exists to prevent. */
    .groups {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: var(--register-pad);
      padding: var(--register-pad);
    }
    dl { display: grid; gap: var(--space-4); align-content: start; }
    dl > div { display: flex; justify-content: space-between; gap: var(--register-pad); }
    .group {
      color: var(--text-muted);
      /* --text-micro, not --register-label -- this is an eyebrow tag; see
         styles.css's register comment for why an eyebrow must not grow. */
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    dt { color: var(--text-secondary); font-size: var(--register-label); }
    dd { color: var(--text); font-size: var(--text-table); }
  `,
})
export class Trades {
  private readonly now = inject(CLOCK);
  private readonly router = inject(Router);
  private readonly api = inject(ApiClient);
  private readonly preferences = inject(PreferencesStore);
  protected readonly store = inject(TradesStore);
  /** For the currency symbol alone, same as the Dashboard's own use of it. */
  protected readonly connection = inject(ConnectionStore);

  /* Query parameters, arriving as inputs through withComponentInputBinding.
   * All strings, because that is what a URL carries. */
  readonly page = input<string>();
  readonly sort = input<string>();
  readonly status = input<string>();
  readonly outcome = input<string>();
  readonly ticker = input<string>();
  readonly strategy = input<string>();
  readonly horizon = input<string>();
  readonly direction = input<string>();
  readonly tier = input<string>();
  readonly origin = input<string>();
  // SR52 — the rest of the filters that had no control. `strategy`, `horizon`
  // and `tier` above were already here and already accepted by the endpoint;
  // they simply had nothing sending them.
  readonly badge = input<string>();
  readonly confidence = input<string>();
  readonly has_note = input<string>();
  // Dashboard lifecycle-strip click-through (Today / Today+open scope). No
  // control here sets it -- only the Dashboard's status cards send it -- but
  // it still has to arrive through the same URL-is-truth path as every other
  // filter, or a reload/shared link would silently drop it.
  readonly today = input<string>();
  // v85 D32 — the opened-at range. Snake_case, matching the wire/URL name
  // (`opened_from`/`opened_to`) the same way `has_note` does above; the
  // store's own `TradeQuery` slice is camelCase (`openedFrom`/`openedTo`),
  // bridged in the effect below.
  readonly opened_from = input<string>();
  readonly opened_to = input<string>();

  /** v85 D32 — the control bar's promoted lane: All, then the eight the
   *  filter bar's own status/outcome/direction controls used to be reached
   *  for through two clicks. `value`/`label` are what `sb-filter-chips`
   *  needs; `param` is read only by `onLaneChip` below. */
  protected readonly laneChips: LaneChip[] = [
    { value: 'open', label: 'Open', param: 'status' },
    { value: 'CLOSED', label: 'Closed', param: 'status' },
    { value: 'PENDING', label: 'Pending', param: 'status' },
    { value: 'win', label: 'Win', param: 'outcome' },
    { value: 'loss', label: 'Loss', param: 'outcome' },
    { value: 'bullish', label: 'Long', param: 'direction' },
    { value: 'bearish', label: 'Short', param: 'direction' },
  ];
  protected readonly tableId = TRADES_TABLE_ID;
  protected readonly pinned = PINNED_COLUMNS;

  /** Compact or full. Read once from preferences; compact for anyone who has
   *  never chosen, because the table exists to show many rows at once. */
  protected readonly density = signal<Density>(
    readTableDensity(this.preferences.values(), TRADES_TABLE_ID),
  );

  /** What "Reset to default" restores, for whichever density is showing. */
  protected readonly defaultColumns = computed(() =>
    this.density() === 'full' ? FULL_COLUMNS : COMPACT_COLUMNS,
  );
  protected readonly rowKey = (row: TradeRow) => `${row.id}:${row.leg_index}`;

  protected readonly originOptions = [
    { value: 'plan', label: 'Plan' },
    { value: 'legacy', label: 'Legacy' },
  ];
  protected readonly tierOptions = [
    { value: 'A', label: 'Tier A' },
    { value: 'B', label: 'Tier B' },
    { value: 'C', label: 'Tier C' },
  ];
  protected readonly badgeOptions = [
    { value: 'VALIDATED', label: 'Validated' },
    { value: 'WEAK', label: 'Weak' },
  ];
  /** Strings, because these travel as query parameters and the server compares
   *  them as strings. */
  protected readonly confidenceOptions = [1, 2, 3, 4, 5].map((level) => ({
    value: String(level),
    label: 'Lv' + level,
  }));
  protected readonly noteOptions = [
    { value: '1', label: 'Has a note' },
    { value: '0', label: 'No note' },
  ];
  /**
   * Every horizon the bot trades, from `HORIZONS` in `strategy_types.py`.
   *
   * Hard-coded rather than derived from the rows on screen. A horizon with no
   * trades yet is still a perfectly real thing to filter for, and a list that
   * grew as trades arrived would leave the control looking broken on a fresh
   * install — which is the mistake the Jinja page's ticker dropdown avoided by
   * building its options from the COMPLETE history rather than the page.
   */
  protected readonly horizonOptions =
    ['2w', '4w', '2m', '3m', '4m', '5m', '6m', '7m', '8m', '9m'].map((key) => ({
      value: key,
      label: key,
    }));

  /** The visible set for the CURRENT density, in order.
   *
   *  Re-read on every density change rather than held as one list: the two
   *  densities are separate preferences, so switching has to load the other
   *  one rather than carry this one across. */
  protected readonly visible = signal<string[]>(
    readTableColumns(
      this.preferences.values(),
      TRADES_TABLE_ID,
      readTableDensity(this.preferences.values(), TRADES_TABLE_ID),
      readTableDensity(this.preferences.values(), TRADES_TABLE_ID) === 'full'
        ? FULL_COLUMNS
        : COMPACT_COLUMNS,
    ),
  );

  /** Rows per page. 0 means "All", translated at the API boundary. */
  protected readonly perPage = signal<number>(
    readTablePerPage(this.preferences.values(), TRADES_TABLE_ID),
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
    const density = readTableDensity(prefs, TRADES_TABLE_ID);
    untracked(() => {
      this.density.set(density);
      this.visible.set(
        readTableColumns(prefs, TRADES_TABLE_ID, density,
                         density === 'full' ? FULL_COLUMNS : COMPACT_COLUMNS),
      );
      this.perPage.set(readTablePerPage(prefs, TRADES_TABLE_ID));
    });
  });

  protected setDensity(next: Density): void {
    if (next === this.density()) return;
    this.density.set(next);
    this.preferences.update((prefs) => writeTableDensity(prefs, TRADES_TABLE_ID, next));
    // Load the other density's saved arrangement, not this one's.
    this.visible.set(
      readTableColumns(this.preferences.values(), TRADES_TABLE_ID, next,
                       next === 'full' ? FULL_COLUMNS : COMPACT_COLUMNS),
    );
  }

  protected onReorder(order: string[]): void {
    this.visible.set(order);
    this.preferences.update((prefs) =>
      writeTableColumns(prefs, TRADES_TABLE_ID, this.density(), order),
    );
  }

  protected onPerPage(value: number): void {
    this.perPage.set(value);
    this.preferences.update((prefs) => writeTablePerPage(prefs, TRADES_TABLE_ID, value));
    // `per_page` must land in the URL, not just the local signal/prefs: this
    // route is server-paginated via a resolver (trades.routes.ts's
    // queryFor()) that reads `per_page` straight from the query params on
    // every navigation, `runGuardsAndResolvers: 'always'` included -- so
    // the very navigate() call below used to stomp this choice back to the
    // URL-less default on its own next run (2026-09-14 fix).
    this.navigate({ per_page: value });
  }

  protected readonly pending = signal<PendingAction>(null);
  protected readonly working = signal(false);

  /** Which bulk clear is awaiting confirmation. */
  protected readonly bulk = signal<'open' | 'history' | null>(null);

  private readonly numCell = viewChild.required<TemplateRef<unknown>>('numCell');
  private readonly statusCell = viewChild.required<TemplateRef<unknown>>('statusCell');
  private readonly directionCell = viewChild.required<TemplateRef<unknown>>('directionCell');
  private readonly planCell = viewChild.required<TemplateRef<unknown>>('planCell');
  private readonly pnlCell = viewChild.required<TemplateRef<unknown>>('pnlCell');
  private readonly rMultipleCell = viewChild.required<TemplateRef<unknown>>('rMultipleCell');
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
      direction: this.directionCell(),
      plan: this.planCell(),
      pnl_pct: this.pnlCell(),
      r_multiple: this.rMultipleCell(),
      tier: this.tierCell(),
      confidence_level: this.confidenceCell(),
      opened_at: this.openedCell(),
      closed_at: this.closedCell(),
      actions: this.actionsCell(),
    } as Record<string, TemplateRef<{ $implicit: TradeRow }>>;

    return tradeColumns(this.now).map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column,
    );
  });

  /**
   * What the current density hides.
   *
   * Computed from the visible set rather than fixed, so the expansion is
   * always the complement of what is on screen: switching to Full empties it
   * of everything Full now shows, which is the behaviour that makes the
   * expansion worth opening at all.
   */
  protected readonly hiddenFields = computed(() => {
    const shown = new Set(this.visible());
    return this.allColumns()
      .filter((column) => !shown.has(column.key) && !PINNED_COLUMNS.includes(column.key))
      .map((column) => ({
        key: column.key,
        header: column.header || column.key,
        numeric: !!column.numeric,
        render: (row: TradeRow): string => {
          const value = column.value ? column.value(row) : (row as never)[column.key];
          return value === null || value === undefined ? '—' : String(value);
        },
      }));
  });

  /** measured-zero always -- an empty filtered set is a measured answer,
   *  not missing data. sb-async's own empty branch (below) pre-empts
   *  sb-data-table's [emptyState] entirely (the table never renders while
   *  empty() is true), so that prop is gone rather than left as a second,
   *  now-unreachable answer to the same question. */
  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.items.length === 0 }),
  );

  /** A polite summary for the workspace's one live region — null until the
   *  first page has loaded. */
  protected readonly announce = computed(() => {
    const page = this.store.pagination();
    return page ? `${page.total} trades` : null;
  });

  /**
   * R6-05: "Showing 1–12 of 142" — a measured answer, not a decoration. Null
   * until the first page has loaded (same guard as `announce` above).
   *
   * A `total` of zero is not one state but two, and this repo distinguishes
   * them everywhere else (see the `emptyTitle` this mirrors, above): a
   * filter that narrowed the log to nothing is a measured zero, not the same
   * fact as a log that has never had a trade in it. The upper bound is
   * clamped to `total` so the last page never claims rows past the end of
   * the log (page 12 of 12 at 142 total, 12/page reads "133–142", not
   * "133–144").
   */
  protected readonly countText = computed(() => {
    const page = this.store.pagination();
    if (!page) return null;
    const { total, page: current, perPage } = page;
    if (total === 0) {
      return this.store.activeFilterCount() > 0
        ? 'No trades match this filter'
        : 'No trades yet';
    }
    const from = (current - 1) * perPage + 1;
    const to = Math.min(current * perPage, total);
    return `Showing ${from}–${to} of ${total}`;
  });

  constructor() {
    // The one place the URL becomes store state. Reading every parameter
    // signal here is what makes a navigation refetch.
    effect(() => {
      const query: TradeQuery = {
        page: Number(this.page() ?? 1) || 1,
        // Reading the signal here is what makes a per-page change refetch --
        // the effect re-runs on every signal it reads, and DEFAULT_PER_PAGE
        // is a constant, so the selector wrote a preference that nothing
        // acted on. perPageForApi turns "All" (0) into the endpoint's cap;
        // 0 itself is rejected by _positive_int.
        per_page: perPageForApi(this.perPage()),
        sort: this.sort(),
        status: this.status(),
        outcome: this.outcome(),
        ticker: this.ticker(),
        strategy: this.strategy(),
        horizon: this.horizon(),
        direction: this.direction(),
        tier: this.tier(),
        origin: this.origin(),
        badge: this.badge(),
        confidence: this.confidence(),
        // Tri-state in the URL ('1' / '0' / absent), boolean on the wire.
        // Absent must stay undefined rather than becoming false: "no note" is
        // a filter, and not asking is not the same as asking for un-noted
        // trades. `_BOOLEAN_FILTERS` on the server compares it as a bool for
        // the same reason a `?has_note=1` string comparison matched nothing.
        has_note:
          this.has_note() === undefined ? undefined : this.has_note() === '1',
        today:
          this.today() === undefined ? undefined : this.today() === '1',
        openedFrom: this.opened_from() ?? null,
        openedTo: this.opened_to() ?? null,
      };
      this.store.setQuery(query, false);
    });
  }

  // v54 Task 28 dropped the unit from both columns on the header's
  // authority. That still holds for R -- one bare number under a header
  // that reads 'R'. It no longer holds for P&L: the cell pairs a percentage
  // with a money amount, and in card mode (below 640px) the header is a
  // <dt> label beside the value rather than a column head above it, so
  // '+2.34 (+118.20 USD)' loses which unit belongs to which figure. The
  // percentage units itself; R does not. See dashboard.ts's matching note.
  protected fmtSigned = signed;
  protected fmtPct = pct;
  protected fmtText = text;
  protected fmtDate = dateTime;
  protected bankedLegPct = bankedLegPct;
  protected bankedLegAmount = bankedLegAmount;
  protected fmtNum(value: number | null, decimals = 2): string {
    return value === null || value === undefined ? '—' : value.toFixed(decimals);
  }

  protected fmtMoney(value: number | null): string {
    return money(value, this.connection.currency());
  }

  /** sb-magnitude's max, from the currently-loaded page rather than the
   *  whole trade history -- a page the user is actually looking at, not a
   *  scale that shifts under them as older extreme trades page out. Floored
   *  at 1 so a page of small/absent R figures doesn't divide by ~0. */
  protected readonly maxRMultiple = computed(() =>
    Math.max(1, ...this.store.rows().map((r) => Math.abs(r.r_multiple ?? 0))),
  );

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

  /** Whichever of the lane's three parameters is set — only one ever is,
   *  because `onLaneChip` always writes all three together. */
  protected readonly laneSelected = computed(
    () => this.outcome() ?? this.status() ?? this.direction() ?? null,
  );

  /**
   * Drive `status`, `outcome` or `direction` from one control-bar chip.
   *
   * All three are always written — one to the chip's value, the other two to
   * null — so switching from Win to Long cannot leave `outcome=win` behind in
   * the URL and silently intersect two filters, which would show an empty
   * table for a chip that looks selected. `null` (All) clears all three: it
   * is the lane's cleared state, not a ninth filter value, and leaves every
   * other filter (strategy, horizon, ...) untouched.
   */
  protected onLaneChip(value: string | null): void {
    const chip = this.laneChips.find((c) => c.value === value);
    this.navigate({
      status: chip?.param === 'status' ? chip.value : null,
      outcome: chip?.param === 'outcome' ? chip.value : null,
      direction: chip?.param === 'direction' ? chip.value : null,
    });
  }

  protected onSort(sort: SortSpec): void {
    this.navigate({ sort: toSortParam(sort) ?? null });
  }

  /** `sb-date-range`'s `changed` -- routes through `navigate()` like every
   *  other filter here, never `store.setQuery` directly, so the range
   *  survives a reload and stays pasteable. */
  protected onDateRange(range: { from: string | null; to: string | null }): void {
    this.navigate({ opened_from: range.from, opened_to: range.to });
  }

  protected clearFilters(): void {
    this.navigate({
      status: null,
      outcome: null,
      ticker: null,
      strategy: null,
      horizon: null,
      direction: null,
      tier: null,
      origin: null,
      // Every filter, or Clear becomes a control that clears most of them —
      // which is worse than none, because the count beside it would then
      // disagree with what is on screen.
      badge: null,
      confidence: null,
      has_note: null,
      today: null,
      opened_from: null,
      opened_to: null,
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
