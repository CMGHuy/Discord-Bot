import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  TemplateRef,
  computed,
  effect,
  inject,
  signal,
  untracked,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { CLOCK } from '../../ui/clock';

import { CloseScope, TradeRow } from '../../api/models';
import { ApiClient } from '../../api/api-client';
import { ToastService } from '../../shell/toast.service';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { DashboardStore } from '../../stores/dashboard.store';
import { TapeStore } from '../../stores/tape.store';
import { TradesStore } from '../../stores/trades.store';
import { Async, asyncInputs } from '../../ui/async';
import { Button } from '../../ui/button';
import { ColumnDef, Density, RowContext } from '../../ui/data-table/data-table.types';
import { ConfidenceCell } from '../../ui/confidence-cell';
import { Flash } from '../../ui/flash';
import { PlanCell, bankedLegAmount, bankedLegPct } from '../../ui/plan-cell';
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
import { amount, dateTime, money, pct, signed } from '../../ui/format';
import { Magnitude } from '../../ui/magnitude';
import { Panel } from '../../ui/layout';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { Hint } from '../../ui/hint';
import { RowLink } from '../../ui/row-link';
import { Icon } from '../../ui/icon';
import { PlanLifecycleDiagram } from '../../ui/plan-lifecycle-diagram';
import {
  expectedPnlPct,
  expectedR,
  expectedSlPct,
  liveUnrealizedAmount,
  livePnlPct,
  reconcileReorder,
  visibleForTab,
} from './dashboard.helpers';
import { PositionsTable } from './positions-table';
import { RowActions } from './row-actions';
import { deriveActivity } from './panels/activity';
import { TradingPerformance } from './panels/trading-performance';
import { RecentActivity } from './panels/recent-activity';
import { MarketMovers } from './panels/market-movers';

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
    Magnitude, Panel, PositionsTable, RowActions, ConfirmDialog,
    StatusCell, PlanCell, ConfidenceCell, Async, Button, Flash,
    Hint, PlanLifecycleDiagram, RowLink, Icon, TradingPerformance,
    RecentActivity, MarketMovers,
  ],
  // TradesStore, not DashboardStore -- that one is provided at the route
  // level (dashboard.routes.ts). This instance is this page's own, for the
  // activity feed's own query (newest-first, every status), separate from
  // sb-positions-table's own instance (it provides its own -- see
  // positions-table.ts).
  providers: [TradesStore],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // v54 D1: this workspace answers "how am I doing?" -- hero figures, room
  // to breathe -- so it defaults to the presentation register. Set on the
  // host (a static class, not a template wrapper) because :host IS the grid
  // container the register's variables need to reach; a class in the
  // template's own markup would land one level too deep.
  host: {
    class: 'register-presentation',
    // Scoped to the close-all menu specifically (closeAllMenuRef, below),
    // not "outside this whole component" -- this component IS the page, so
    // almost every click on it would otherwise count as "outside".
    '(document:click)': 'onDocumentClickForCloseAllMenu($event)',
    '(document:keydown.escape)': 'closeAllMenuOpen.set(false)',
  },
  // Provided here rather than in root: the store is created on entry and
  // destroyed on exit, so a workspace does not hold stale state while you
  // are looking at another one. `sb-positions-table` below provides its own
  // `TradesStore` instance (see positions-table.ts) -- neither this one nor
  // that one touch the Trades workspace's own copy.
  template: `
    <!-- Each panel owns its first-load state. A slow dashboard summary must
         never hide the independently fetched positions table or activity. -->
    <sb-async class="performance-async"
      [loading]="async().loading"
      [error]="async().error"
      [empty]="false"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="No open positions"
      [skeletonRows]="3"
      [skeletonCols]="5"
      (retry)="store.load()"
    >
    <!-- v85: the five metric cards, the chip row, the realised-count line
         and the lifecycle nav strip are replaced by the panel below (D9).
         Portfolio Value merged into this one panel rather than sitting
         beside it as its own card -- both describe "how am I doing", and
         they never disagree, so one heading now covers both. -->
    <sb-trading-performance
      [balance]="store.balance()"
      [changePct]="store.equityChangePct()"
      [points]="store.equityPoints()"
      [openPnlPct]="store.openPnlPct()"
      [winRate]="store.winRate()"
      [expectancyR]="store.expectancyR()"
      [winRateN]="store.winRateN()"
      [expectancyN]="store.expectancyN()"
      [avgConfidence]="store.avgConfidence()"
      [realizedAmount]="store.realizedAmount()"
      [realizedLabel]="realizedLabel()"
      [openTrades]="store.openTrades()"
      [riskUsedPct]="store.riskUsedPct()"
      [riskCapPct]="store.riskCapPct()"
      [payoffRatio]="store.payoffRatio()"
      [currency]="connection.currency()"
      [scope]="store.scope()"
      (scopeChange)="store.setScope($event)"
    />
    </sb-async>

    <sb-panel class="positions-panel" heading="Open positions" [flush]="true">
      <!-- The lifecycle and sizing context share one help trigger. The
           per-trade sizing mode belongs on the detail view, where its source
           data is available. -->
      <sb-hint panel-actions class="lifecycle-hint" [xl]="true" align="left" glyph="?"
               label="About open positions">
        <span class="hint-heading">Plan lifecycle</span>
        <span class="hint-copy">
          <strong>What appears here:</strong> Only trades that meet <em>every</em>
          configured requirement (min reward, stop distance, risk:reward, min
          strategies confirmed, min confidence) are logged as paper trades.
          PENDING → ACTIVE → PARTIAL → CLOSED shows a plan from entry through
          its first and final exits.
        </span>
        <sb-plan-lifecycle-diagram />
        <span class="hint-heading">Sizing</span>
        @if (premiumExplanation(); as explanation) {
          <span class="hint-copy">{{ explanation }}</span>
        }
        <span class="hint-copy">
          Share counts are snapshotted when a position opens. A trade logged
          before that snapshot existed shows an estimate instead, and a position
          opened under a different sizing mode will not match the premium note
          above.
        </span>
      </sb-hint>

      <!-- v85 D11: one table, five lifecycle tabs, replacing the four
           stacked groups. Only the active tab fetches -- see
           positions-table.ts's own docstring for why that is strictly less
           work for the same answer. -->
      <sb-positions-table
        [counts]="lifecycleCounts()"
        [today]="closedToday()"
        [columns]="columns()"
        [visibleFor]="columnsForTab"
        [pinned]="pinned"
        [rowKey]="rowKey"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      >
        <!-- v85 D13/D14: replaces the mockup's "+ New Trade" -- there is no
             create-trade endpoint, the bot authors plans, the admin never
             does. Deliberately not clear-open (below the fold, DELETES
             records) -- see closeAllConsequence for the wording that keeps
             the two apart.

             A dropdown, not one button: ACTIVE and PARTIAL are different
             enough states (a scaled-out position vs one untouched since
             entry) that closing only one of them is a real, distinct
             action, not a convenience shortcut for the combined one. -->
        <div class="close-all-menu" table-actions #closeAllMenu>
          <button sb-button variant="secondary" type="button"
                  data-action="close-all"
                  [attr.aria-expanded]="closeAllMenuOpen()"
                  aria-haspopup="menu"
                  [disabled]="!openCount()"
                  (click)="toggleCloseAllMenu($event)">
            Close all open/partial
          </button>
          @if (closeAllMenuOpen()) {
            <div class="menu elev-overlay" role="menu">
              <button sb-button variant="ghost" type="button" role="menuitem"
                      [disabled]="!activeCount()"
                      (click)="requestCloseAll('open')">
                Close all open
              </button>
              <button sb-button variant="ghost" type="button" role="menuitem"
                      [disabled]="!partialCount()"
                      (click)="requestCloseAll('partial')">
                Close all partial
              </button>
              <button sb-button variant="ghost" type="button" role="menuitem"
                      [disabled]="!openCount()"
                      (click)="requestCloseAll('open_partial')">
                Close all open/partial
              </button>
            </div>
          }
        </div>
      </sb-positions-table>
    </sb-panel>

    <sb-confirm-dialog
      [open]="confirmCloseAll() !== null"
      [title]="closeAllTitle()"
      [consequence]="closeAllConsequence()"
      [confirmLabel]="closeAllConfirmLabel()"
      (confirmed)="closeAll()"
      (cancelled)="confirmCloseAll.set(null)"
    />

    <div class="bottom-row">
      <sb-async [loading]="activityAsync().loading" [error]="activityAsync().error" [empty]="false"
                emptyReason="measured-zero" emptyTitle="Recent activity"
                [skeletonRows]="4" [skeletonCols]="3"
                (retry)="recent.load()">
        <sb-recent-activity [events]="activity()" />
      </sb-async>
      <sb-async [loading]="tapeAsync().loading" [error]="tapeAsync().error" [empty]="false"
                emptyReason="measured-zero" emptyTitle="Market movers"
                [skeletonRows]="4" [skeletonCols]="2"
                (retry)="tape.load()">
        <sb-market-movers [rows]="tape.rows()" />
      </sb-async>
    </div>

    <ng-template #statusCell let-row>
      <sb-status-cell [row]="row" />
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
    <!-- Direction folds into this cell (no separate Direction column here --
         see deriveClosedVisible/deriveOpenVisible) to save the width a whole
         column cost for one glyph. -->
    <ng-template #confidenceCell let-row>
      <sb-confidence-cell
        [level]="row.confidence_level"
        [score]="row.confidence_score"
        [direction]="row.direction"
      />
    </ng-template>

    <!-- cells ---------------------------------------------------------- -->

    <!-- row.id IS the plan id (dashboard.py's _row_from_plan sets "id" to
         plan["plan_id"] directly, not a separate trade id) -- shortId below
         just trims it to something a 3rem column can hold; the full id is
         on the detail page this links to, same pattern as trades.ts. -->
    <ng-template #numCell let-row>
      <sb-row-link [link]="['/trades', row.id]">
        {{ shortId(row) }}
        <!-- v79 split a scaled-out position into one row per leg, both
             carrying the same id -- on the Closed tab that reads as a
             duplicate row unless the TP1 leg is marked apart from the
             runner that finished it. -->
        @if (isPartialLeg(row)) {
          <sb-icon name="partial" class="leg-icon" title="TP1 partial exit — the runner leg closed separately" />
        }
      </sb-row-link>
    </ng-template>

    <!-- A real anchor, not a click handler: row activation is mouse-only by
         the table's design, so this is the keyboard route into a position. -->
    <ng-template #tickerCell let-row>
      <sb-row-link [link]="['/trades', row.id]">{{ row.ticker }}</sb-row-link>
    </ng-template>

    <!-- The % alone didn't say how much money that was -- pairing it with
         the realised amount (same sign, same field realized_pnl_amount
         Trade History already shows in its own "Realised" column) answers
         that without a second column. Only ever populated together: both are
         null until a position closes.

         pnl_pct itself is null for every PENDING/ACTIVE/PARTIAL row --
         dashboard.py's closed_pnl needs an exit_price, which does not exist
         until a position closes -- so those three groups fell through to an
         em dash regardless of how the position was actually doing. The else
         branch reads the same way the Plan cell does (entry → target / stop)
         but in P&L% instead of price: LIVE (where it is right now, real,
         plain colour) → TP (green, dashed -- projected) - SL (red, dashed --
         projected), from the same entry/stop/target/current_price the Plan
         cell already shows. -->
    <ng-template #pnlCell let-row>
      @if (row.pnl_pct !== null) {
        <span [sbFlash]="row.pnl_pct" [class]="pnlClass(row.pnl_pct)">
          {{ fmtPct(row.pnl_pct) }}
          <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
        </span>
      } @else {
        <span
          class="pnl-plan"
          title="Live P&L, then projected P&L at target and at stop"
        >
          <span [sbFlash]="livePnlPct(row)" [class]="pnlClass(livePnlPct(row))">
            {{ fmtPct(livePnlPct(row)) }}
            <!-- Only once shares exist to have a dollar value at all -- a
                 PENDING row still projects a live PERCENTAGE off its
                 trigger, but has bought nothing yet. !== null, not a plain
                 truthy check: a break-even position is a real $0.00, not
                 "no value yet". Scaled by open_shares, not shares: a
                 PARTIAL row already closed part of itself at TP1, so this
                 is smaller than the same price move would show on the
                 original size. -->
            @if (liveUnrealizedAmount(row) !== null) {
              <span class="pnl-amount"> ({{ fmtMoney(liveUnrealizedAmount(row)) }})</span>
            }
          </span>
          <span class="sep">{{ ' → ' }}</span>
          <span class="tp expected">{{ fmtPct(expectedPnlPct(row)) }}</span>
          <span class="sep">{{ ' - ' }}</span>
          <span class="sl expected">{{ fmtPct(expectedSlPct(row)) }}</span>
        </span>
      }
    </ng-template>

    <!-- See pnlCell above -- same real-vs-projected split, same reasoning.
         The real branch colours by sign too (pnlClass), same as the
         projected branch already did -- a closed loss's R used to render
         in the same plain colour as a win's, which read as "no P&L info"
         at a glance where the pnl_pct column right next to it was
         unmistakably red or green.
         v54 Task 28: the header ('R') already names the unit, signed() not
         fmtR() so the cell does not repeat it; sb-magnitude beneath both
         branches (see R_MAGNITUDE_MAX for why it is a fixed reference
         scale, not an observed max, here specifically). -->
    <ng-template #rMultipleCell let-row>
      @if (row.r_multiple !== null) {
        <span [sbFlash]="row.r_multiple" [class]="pnlClass(row.r_multiple)">{{ fmtSigned(row.r_multiple) }}</span>
        <sb-magnitude [value]="row.r_multiple" [max]="R_MAGNITUDE_MAX" />
      } @else {
        <span
          class="expected"
          [sbFlash]="expectedR(row)"
          [class]="pnlClass(expectedR(row))"
          title="Projected R if price reaches target"
        >{{ fmtSigned(expectedR(row)) }}</span>
        <sb-magnitude [value]="expectedR(row)" [max]="R_MAGNITUDE_MAX" />
      }
    </ng-template>

    <!-- Trades has these two (trades.ts's own openedCell/closedCell); the
         Dashboard never did, so opened_at/closed_at fell through to the
         table's default cell renderer, which reads column.value -- and
         neither column defines one, so every row rendered the "no value"
         em dash regardless of what the row actually held. -->
    <ng-template #openedCell let-row>{{ fmtDate(row.opened_at) }}</ng-template>
    <ng-template #closedCell let-row>{{ fmtDate(row.closed_at) }}</ng-template>
    <ng-template #actionsCell let-row>
      <sb-row-actions [row]="row" (done)="store.load()" />
    </ng-template>
  `,
  styles: `

    /* -- SR58: scope toggle ---------------------------------------- */
    /* Groups the stale message and the scope toggle into one actions
       projection -- as two separate ones they would land at opposite
       ends of sb-section-head's space-between instead of clustered. */
    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal.
       v54: gap reads --register-pad, set by the register-presentation class
       on this same host element (above) -- --space-20 was this rule's own
       literal before, and register-presentation's rung is the same value,
       so this changes nothing visually while making the rhythm follow the
       register instead of a hardcoded token. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }

    /* Both panels below own their OWN top margin, on top of the grid's own
       --register-pad, rather than the panel above owning a bottom margin --
       one rule per element that wants extra space above it, so a later
       reorder doesn't leave a margin attached to the wrong edge. */
    .bottom-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: var(--section-gap);
    }

    /* Same overlay pattern as sb-profile-menu's own dropdown: relative
       wrapper, absolutely-positioned menu, elev-overlay for the shared
       surface/shadow treatment. Right-aligned under the trigger rather than
       left -- this sits inside the table's own right-aligned actions slot,
       and a left-aligned menu would spill it past the table's right edge. */
    .close-all-menu { position: relative; display: inline-flex; }
    .close-all-menu .menu {
      position: absolute;
      top: calc(100% + var(--space-6));
      right: 0;
      z-index: 20;
      min-width: 180px;
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      padding: var(--space-6);
    }
    .close-all-menu .menu button { justify-content: flex-start; }

    .lifecycle-hint { margin-left: var(--space-4); }
    .hint-heading, .hint-copy { display: block; }
    .hint-heading { margin-bottom: var(--space-4); font-weight: 600; }
    .hint-copy { margin-bottom: var(--space-8); color: var(--text-secondary); }
    .lifecycle-hint sb-plan-lifecycle-diagram { display: block; min-width: 280px; }

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

    /* Only colour and font-family reach through sb-row-link's own
       :host{display:contents} into its inner .row-link's color: inherit --
       text-decoration cannot: the primitive explicitly resets it to none,
       even on hover, so the old underline becomes the primitive's own
       background-tint hover instead. */
    sb-row-link { color: var(--accent); font-family: var(--font-mono); }

    /* Muted, not accent: the glyph flags the leg, it isn't part of the id. */
    sb-row-link .leg-icon { color: var(--text-muted); flex: none; }

    /* No size or weight of its own -- it used to render smaller than the %
       it rides beside, which read as a footnote rather than the dollar side
       of the same figure. Both are the headline number now, just in
       different units. No colour of its own either, so it inherits
       pnlClass() from the span it sits inside (row.pnl_pct on the Closed
       table, livePnlPct(row) on the other three) -- it is the same gain or
       loss, not a separate number. */
    /* Same "not real yet" language as PlanCell's own .entry.pending -- a
       dashed underline rather than a colour, since the pos/neg palette
       already means something else (gain vs loss) and this axis (realised
       vs projected) is orthogonal to it. */
    .expected { border-bottom: 1px dashed currentColor; }

    /* The live-to-target-to-stop P&L line -- same layout language as
       PlanCell's own entry → target / stop (font, separators, fixed
       target/stop colours), just in percent rather than price. */
    /* --cell-wrap/--sep-wrap: DataTable's card-mode wrap contract (see its
       .card-value block). Undefined in a table, so this stays nowrap; inside
       a card it becomes normal. This is the widest cell on the page -- four
       figures in two units, '+2.34% (+118.20 USD) → +8.00% - −3.00%' -- and
       it measured 279px inside a 255px card at 375px, which put the whole
       projected half of the line past the edge with body's overflow-x:hidden
       swallowing it. */
    .pnl-plan {
      font-family: var(--font-mono);
      font-size: var(--text-table);
      white-space: var(--cell-wrap, nowrap);
    }
    .pnl-plan .sep { color: var(--text-faint); white-space: var(--sep-wrap, pre); }
    .pnl-plan .tp { color: var(--pos); }
    .pnl-plan .sl { color: var(--neg); }

    @media (max-width: 720px) {
      /* Option 2: on phones, live positions come before every performance
         detail. The table keeps its pager on every lifecycle tab, but does
         not add blank filler rows below a short first page. */
      :host { display: flex; flex-direction: column; }
      .positions-panel { order: 1; }
      .performance-async { order: 2; }
      .bottom-row { order: 3; }
      .lifecycle-hint sb-plan-lifecycle-diagram { min-width: 0; }
    }
  `,
})
export class Dashboard {
  private readonly now = inject(CLOCK);
  private readonly router = inject(Router);
  private readonly api = inject(ApiClient);
  private readonly toast = inject(ToastService);
  protected readonly store = inject(DashboardStore);
  /** For the currency symbol alone. `ConnectionStore` is root-provided and
   *  the shell already keeps it fresh, so reading it here costs no request. */
  protected readonly connection = inject(ConnectionStore);
  /** Root-provided and already loaded by the shell (the top bar's own tape
   *  lanes) -- this page only reads `rows()`, it never calls `load()`. */
  protected readonly tape = inject(TapeStore);
  /** This page's own instance, and NOT the positions table's: that one holds
   *  whichever single tab is selected, which is the wrong population for a
   *  feed that must span opens and closes at once. Provided on this component
   *  (see `providers`), so it is created on entry and destroyed on exit. */
  protected readonly recent = inject(TradesStore);

  protected readonly activity = computed(() => deriveActivity(this.recent.rows()));
  protected readonly activityAsync = computed(() => asyncInputs(
    { data: () => this.recent.empty() ? null : this.recent.rows(),
      loading: this.recent.loading, error: this.recent.error },
    { isEmpty: () => false },
  ));
  protected readonly tapeAsync = computed(() => asyncInputs(
    { data: () => this.tape.rows(), loading: this.tape.loading, error: this.tape.error },
    { isEmpty: () => false },
  ));

  constructor() {
    // Every status, newest first. ACTIVITY_WINDOW rows in, at most six events
    // out (deriveActivity's own cap) -- a row can yield two events, so the
    // fetch has to be wider than the feed.
    this.recent.setQuery({ sort: '-opened_at', page: 1, per_page: 20 });
  }

  /** Zero open positions is a RESULT (the scan found nothing qualifying in
   *  this scope), not missing data -- measured-zero, not no-data-yet. */
  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.open_trades === 0 }),
  );

  /** A polite summary for the workspace's one live region — null while there
   *  is nothing loaded yet to summarise. Text that does not change does not
   *  re-announce; this is not a running commentary on every push. */
  protected readonly announce = computed(() =>
    this.store.empty() ? null : `${this.store.openTrades()} open trades`,
  );

  /** v79: a scaled-out position arrives from /api/v1/trades as one row per
   *  realized leg, and every leg carries the same plan id -- so the id alone
   *  is not unique and the table's trackBy would collapse the two rows into
   *  one. Same key Trades and the ticker detail use. */
  protected readonly rowKey = (row: TradeRow) => `${row.id}:${row.leg_index}`;

  /** The Closed tab's `today` input: `true` in Today mode (narrows to
   *  trades closed today, same rule the lifecycle strip's CLOSED count
   *  already used), `null` in All days (unfiltered -- most recent closes).
   *  PositionsTable applies this to CLOSED/CANCELLED only. */
  protected readonly closedToday = computed(() =>
    this.store.scope() === 'all' ? null : true,
  );

  /** The lifecycle strip's counts, reshaped for the tab labels. The strip
   *  itself is gone (R4-07) -- these numbers moved onto the tabs. */
  protected readonly lifecycleCounts = computed(() =>
    Object.fromEntries(this.store.lifecycle().map((e) => [e.status, e.count])),
  );

  /** Bound as a value, not called in the template: the table takes the
   *  function and applies it per tab.
   *
   *  Named `columnsForTab`, not `visibleForTab`: the imported helper is
   *  already called that, and a class member of the same name reads as a
   *  recursive call to anyone skimming it. */
  protected readonly columnsForTab = (tab: string) => visibleForTab(tab, this.visible());

  /* -- v85 D13/D14: close all open/partial ----------------------------- */

  /** `null` = no confirmation pending; otherwise which scope was picked
   *  from the dropdown and is now waiting on the confirm dialog. */
  protected readonly confirmCloseAll = signal<CloseScope | null>(null);

  protected readonly closeAllMenuOpen = signal(false);
  private readonly closeAllMenuRef =
    viewChild<ElementRef<HTMLElement>>('closeAllMenu');

  /** ACTIVE + PARTIAL only — a PENDING plan never filled, so there is nothing
   *  to close and cancelling is the different act that applies to it. */
  protected readonly activeCount = computed(() => this.lifecycleCounts()['ACTIVE'] ?? 0);
  protected readonly partialCount = computed(() => this.lifecycleCounts()['PARTIAL'] ?? 0);
  protected readonly openCount = computed(() => this.activeCount() + this.partialCount());

  protected toggleCloseAllMenu(event: MouseEvent): void {
    event.stopPropagation();
    this.closeAllMenuOpen.update((v) => !v);
  }

  protected onDocumentClickForCloseAllMenu(event: MouseEvent): void {
    if (!this.closeAllMenuOpen()) return;
    const wrapper = this.closeAllMenuRef()?.nativeElement;
    if (wrapper && !wrapper.contains(event.target as Node)) this.closeAllMenuOpen.set(false);
  }

  protected requestCloseAll(scope: CloseScope): void {
    this.closeAllMenuOpen.set(false);
    this.confirmCloseAll.set(scope);
  }

  /** The count the picked scope actually closes -- "This closes 2
   *  position(s)" would be wrong (and scarier or safer than the truth in
   *  either direction) if it always quoted the combined count regardless of
   *  which of the three menu items was picked. */
  private readonly closeAllScopeCount = computed(() => {
    switch (this.confirmCloseAll()) {
      case 'open': return this.activeCount();
      case 'partial': return this.partialCount();
      default: return this.openCount();
    }
  });

  protected readonly closeAllTitle = computed(() => {
    switch (this.confirmCloseAll()) {
      case 'open': return 'Close all open positions?';
      case 'partial': return 'Close all partial positions?';
      default: return 'Close all open/partial positions?';
    }
  });

  protected readonly closeAllConfirmLabel = computed(() => {
    switch (this.confirmCloseAll()) {
      case 'open': return 'Close open';
      case 'partial': return 'Close partial';
      default: return 'Close all';
    }
  });

  /** Names what the action does, in the words that distinguish it from
   *  clear-open next door: this REALISES profit or loss, that one deletes
   *  records and realises nothing. */
  protected readonly closeAllConsequence = computed(() =>
    `This closes ${this.closeAllScopeCount()} position(s) at their current price and `
    + 'realises the profit or loss. Pending plans are not affected. '
    + 'This cannot be undone.',
  );

  protected closeAll(): void {
    const scope = this.confirmCloseAll();
    this.confirmCloseAll.set(null);
    if (!scope) return;
    this.api.closeOpenTrades(scope).subscribe({
      next: (result) => {
        this.toast.show(
          result.failed
            ? `Closed ${result.closed}, ${result.failed} failed — check the log.`
            : `Closed ${result.closed} position${result.closed === 1 ? '' : 's'}.`,
          result.failed ? 'warn' : 'info',
        );
        this.store.load();
      },
      error: () => this.toast.show('Could not close positions.', 'error'),
    });
  }

  private readonly numCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('numCell');
  private readonly tickerCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('tickerCell');
  private readonly pnlCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('pnlCell');
  private readonly rMultipleCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('rMultipleCell');
  private readonly statusCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('statusCell');
  private readonly planCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('planCell');
  private readonly confidenceCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('confidenceCell');
  private readonly openedCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('openedCell');
  private readonly closedCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('closedCell');
  private readonly actionsCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('actionsCell');
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
    const merged = reconcileReorder(order, this.visible());
    this.visible.set(merged);
    this.preferences.update((prefs) =>
      writeTableColumns(prefs, DASHBOARD_TABLE_ID, this.density(), merged),
    );
  }

  /** The shared definitions, with this panel's own cells attached. */
  protected readonly columns = computed<ColumnDef<TradeRow>[]>(() => {
    const cells: Record<string, TemplateRef<RowContext<TradeRow>>> = {
      num: this.numCell(),
      ticker: this.tickerCell(),
      pnl_pct: this.pnlCell(),
      r_multiple: this.rMultipleCell(),
      status: this.statusCell(),
      plan: this.planCell(),
      confidence_level: this.confidenceCell(),
      opened_at: this.openedCell(),
      closed_at: this.closedCell(),
      actions: this.actionsCell(),
    };
    return tradeColumns(this.now).map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column,
    );
  });

  /* -- SR59: the copy ------------------------------------------------- */

  /**
   * The premium chip's reasoning, from `dashboard_fragment.html:81-87`.
   *
   * Assembled here rather than server-side because it is a sentence, and
   * `build_sizing_note` deliberately returns numbers. Null in account-%
   * mode's simple case where the chip's own number already says everything.
   */
  protected readonly premiumExplanation = computed<string | null>(() => {
    const note = this.store.sizingNote();
    if (!note) return null;

    if (note['mode'] === 'account_pct') {
      const pct = note['position_pct'];
      return typeof pct === 'number'
        ? `Account % mode — every trade is sized at ${pct}% of balance, `
          + 'regardless of stop distance.'
        : null;
    }

    const risk = note['risk_amount'];
    const riskPct = note['risk_pct'];
    const maxPct = note['max_position_pct'];
    const maxAbs = note['max_position_value_absolute'];
    if (typeof risk !== 'number' || typeof riskPct !== 'number') return null;

    const currency = this.connection.currency();
    const cap = typeof maxAbs === 'number' && maxAbs > 0
      ? `${maxPct}% of balance or ${amount(maxAbs, currency)} absolute, whichever is tighter`
      : `${maxPct}% of balance`;

    return `Risk % mode — risks ${amount(risk, currency)} (${riskPct}%) if stopped `
      + `out, capped at ${cap}. Varies per trade with stop distance — switch to `
      + '!account sizing account for a fixed premium instead.';
  });

  /** Names the window in the card itself, so a figure cannot be read as
   *  today's when the toggle is on All days. */
  protected readonly realizedLabel = computed(() =>
    this.store.scope() === 'all' ? 'Realised, all days' : 'Realised today',
  );

  // v54 Task 28 dropped the unit from both columns on the grounds that the
  // header already names it. That holds for R -- one number per cell, under
  // a header that reads 'R'. It does not hold for P&L: the projected branch
  // packs FOUR figures into one cell (live, its money amount in brackets,
  // then TP and SL), and only three of them are percentages. Reported as
  // unreadable, and it is: '+2.34 (+118.20 USD) → +8.00 - −3.00' gives no
  // clue which of those numbers the header's unit applies to. So the P&L
  // cell signs AND units its percentages (`fmtPct`) while R keeps the bare
  // signed figure (`fmtSigned`).
  protected fmtSigned = signed;
  protected fmtPct = pct;
  protected fmtDate = dateTime;

  /** row.id IS the plan id; the '#' column is 3rem wide and the full id is
   *  on the detail page it links to. Same rule trades.ts's own shortId
   *  uses -- kept in sync there rather than shared, since the two files
   *  don't otherwise depend on each other. */
  protected shortId(row: TradeRow): string {
    return row.id.length > 6 ? row.id.slice(-6) : row.id;
  }

  /** True for the TP1 leg of a v79 scale-out split, never for the runner
   *  leg that finishes it -- the runner IS the position's real close, so
   *  only the earlier partial exit needs a mark to explain why its row
   *  shares a hash with another one. Same rule trades.ts's own
   *  isPartialLeg uses. */
  protected isPartialLeg(row: TradeRow): boolean {
    return row.leg_total > 1 && row.leg_index < row.leg_total - 1;
  }

  /** sb-magnitude's max for the R column. Not an observed max from the
   *  store: sb-positions-table shows one lifecycle tab's rows at a time, and
   *  this same cell template serves every tab -- there is no single "this
   *  table's rows" to measure from here. R is already a normalised unit (the
   *  risk taken, by definition 1R), so a fixed reference scale is the more
   *  honest choice anyway: 3R covers a well-run multi-target scale-out
   *  without every ordinary trade landing near the same width. */
  protected readonly R_MAGNITUDE_MAX = 3;

  protected fmtMoney(value: number | null): string {
    return money(value, this.connection.currency());
  }

  protected pnlClass(value: number | null): string {
    if (value === null) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }

  /** See dashboard.helpers.ts's own comments for what each of these means
   *  and why it is null when it is. */
  protected expectedPnlPct = expectedPnlPct;
  protected bankedLegPct = bankedLegPct;
  protected bankedLegAmount = bankedLegAmount;
  protected expectedSlPct = expectedSlPct;
  protected livePnlPct = livePnlPct;
  protected liveUnrealizedAmount = liveUnrealizedAmount;
  protected expectedR = expectedR;

  /** Mouse activation, matching Trades: a row leads to its detail view. The
   *  ticker cell's anchor is the keyboard equivalent. */
  protected open(row: TradeRow): void {
    void this.router.navigate(['/trades', row.id]);
  }
}
