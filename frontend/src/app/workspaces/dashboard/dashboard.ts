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
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { DashboardStore } from '../../stores/dashboard.store';
import { Async, asyncInputs } from '../../ui/async';
import { Button } from '../../ui/button';
import { ChipRow } from '../../ui/chip-row';
import { ColumnDef, Density, EmptyState, RowContext } from '../../ui/data-table/data-table.types';
import { ConfidenceCell } from '../../ui/confidence-cell';
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
import { amount, dateTime, held, money, num, pct, signed } from '../../ui/format';
import { Magnitude } from '../../ui/magnitude';
import { ControlRow, Panel } from '../../ui/layout';
import { RowLink } from '../../ui/row-link';
import { SectionHead } from '../../ui/section-head';
import { MetricCard } from '../../ui/metric-card';
import { MetricChip } from '../../ui/metric-chip';
import { PlanLifecycleDiagram } from '../../ui/plan-lifecycle-diagram';
import {
  deriveClosedVisible,
  deriveOpenVisible,
  expectedPnlPct,
  expectedR,
  expectedSlPct,
  liveUnrealizedAmount,
  livePnlPct,
  reconcileReorder,
} from './dashboard.helpers';
import { TradeGroup } from './trade-group';

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
    RouterLink, MetricCard, MetricChip, Magnitude, Panel, TradeGroup,
    StatusCell, PlanCell, ConfidenceCell, Async, Button, ChipRow, ControlRow,
    PlanLifecycleDiagram, RowLink, SectionHead,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Provided here rather than in root: the store is created on entry and
  // destroyed on exit, so a workspace does not hold stale state while you
  // are looking at another one. Each `sb-trade-group` below provides its own
  // `TradesStore` instance (see trade-group.ts) -- neither this one nor
  // those three touch the Trades workspace's own copy.
  providers: [DashboardStore],
  template: `
    <!-- v54: sb-async's own staleAsOf badge (below) now owns the "these
         numbers stopped updating" signal -- a second one here would be a
         duplicate, not a backstop, so store.error() no longer binds here
         directly (it also skipped the v13 refetch mapping asyncInputs
         provides, which this raw binding never applied). -->
    <sb-section-head heading="Dashboard">
      <!-- SR58. The Jinja dashboard's three date scopes. A server parameter,
           not a client filter: the realised figures below are computed from
           the scoped set, and a client-side scope over an all-time payload
           could not narrow them at all. -->
      <sb-control-row actions class="scope" role="group" aria-label="Date scope">
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
      </sb-control-row>
    </sb-section-head>

    <!-- SR59. Copied from dashboard.html:60-68, not paraphrased: it states
         a specific rule about what does and does not reach this screen, and a
         looser wording would describe a looser rule. -->
    <p class="explainer">
      <strong>What appears here:</strong>
      Only trades that meet <em>every</em> configured requirement (min reward,
      stop distance, risk:reward, min strategies confirmed, min confidence) are
      logged here as paper trades. Trade plans shown by <code>!check</code> that
      don't clear all requirements appear in Discord but are <strong>not</strong>
      logged — they're marked in bold red in the Discord embed. The automatic
      background scan only ever posts and logs fully-qualifying setups.
    </p>

    <!-- v54: rows=3 cols=5, measured against the .primary row of five
         metric cards (skeletonRows/skeletonCols verified at Slow 3G --
         Task 21 G6). -->
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="No open positions"
      emptyHint="The scan found no qualifying setups in this scope."
      [skeletonRows]="3"
      [skeletonCols]="5"
      (retry)="store.load()"
    >
    <!-- SR58 / reorg: Realised today, Account balance, Open P&L, Risk used
         and Realised average all read together as one row -- Realised is
         scoped by the toggle above and the other three are always all-open,
         but they are all "the account right now" and splitting them into two
         rows only used to say "these five cards were added at different
         times", not anything about the numbers themselves. -->
    <div class="primary">
      <sb-metric-card
        [label]="realizedLabel()"
        [value]="store.realizedAmount()"
        tone="pnl"
        [unit]="currencyUnit()"
      />
      <sb-metric-card
        label="Account balance"
        [value]="store.balance()"
        [unit]="currencyUnit()"
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
      <sb-metric-card
        label="Realised, average"
        [value]="store.realizedPct()"
        tone="pnl"
        unit="%"
      />
    </div>
    <span class="realized-count">
      {{ store.realizedCount() }} closed{{ closedQualifier() }} ·
      {{ store.realizedWins() }}W / {{ store.realizedLosses() }}L
    </span>

    <sb-chip-row class="chips">
      <sb-metric-chip label="Open trades" [value]="store.openTrades()" [decimals]="0" />
      <!-- Confidence is a QUALITY judgement, not money, so it stays plain:
           green and red mean P&L direction on this screen and nothing else. -->
      <sb-metric-chip label="Avg confidence" [value]="store.avgConfidence()" [decimals]="1" />
      <sb-metric-chip label="Win rate" [value]="store.winRate()" unit="%" [decimals]="1" />
      <!-- Expectancy is money per unit of risk, which is P&L direction, so it
           is one of the few figures here allowed the green/red pair. -->
      <sb-metric-chip label="Expectancy" [value]="store.expectancyR()" tone="pnl" unit="R" />
      <sb-metric-chip
        label="Position premium"
        [value]="store.positionPremium()"
        [unit]="premiumUnit()"
        [decimals]="0"
      />
    </sb-chip-row>

    <!-- SR59. The chip carries the number and the "max" qualifier; this is
         the reasoning behind it, from dashboard_fragment.html:81-87. -->
    @if (premiumExplanation(); as explanation) {
      <p class="section-help">{{ explanation }}</p>
    }

    <!-- SR53. The lifecycle strip: five counts, each a link into Trades
         filtered to that status. The Jinja dashboard had exactly this and the
         SPA had the chips it navigated to with no numbers on them.

         The click-through also carries the page's OWN date scope now: in
         Today, the today param narrows Trades to rows that either opened
         today or are still open regardless of age -- see todayParam's
         docstring. In All days it is omitted, so the click-through stays
         all-time. Only the destination narrows this way; the counts on the
         chips themselves stay exactly as they always were (see the note
         below). -->
    @if (store.lifecycle().length) {
      <nav class="lifecycle" aria-label="Plans by lifecycle status">
        @for (entry of store.lifecycle(); track entry.status) {
          <a
            class="lc"
            routerLink="/trades"
            [queryParams]="{ status: entry.status, outcome: null, today: todayParam() }"
            [attr.title]="lifecycleTip(entry.status)"
          >
            <span class="lc-count num">{{ entry.count }}</span>
            {{ ' ' }}
            <span class="lc-label">{{ entry.status }}</span>
          </a>
        }
      </nav>

      <!-- SR59. _plans_board.html:22-27, verbatim. The per-status wording
           from lc_tips rides each card's title attribute: the SPA has no
           tip-icon component, and adding one would be a design decision
           rather than a copy task. -->
      <p class="section-help">
        A plan moves PENDING → ACTIVE → PARTIAL → CLOSED as price hits its
        entry trigger, TP1, then TP2/stop (or CANCELLED if it expires or
        invalidates before filling). PENDING/ACTIVE/PARTIAL counts are
        all-time; CLOSED/CANCELLED only count today's — click a card to filter
        the board below by that status
        @if (store.scope() !== 'all') { , narrowed in Today mode to what
          opened today plus anything still open, however old }.
      </p>
      <!-- Centred as a row, the diagram to the left of the terms it uses --
           it is a figure illustrating the paragraph above, not more running
           copy, and the rest of this page is left-aligned precisely so that
           distinction reads. -->
      <div class="lifecycle-figure">
        <sb-plan-lifecycle-diagram />
        <dl class="lifecycle-legend">
          <div>
            <dt>Fills</dt>
            <dd>Price crosses the entry trigger and the position opens.</dd>
          </div>
          <div>
            <dt>Expires</dt>
            <dd>
              Price never reached the trigger within {{ store.defaultExpiryBars() }} bars
              of the plan being posted (the default expiry window; an individual
              plan can be built with a different one).
            </dd>
          </div>
          <div>
            <dt>Invalidated</dt>
            <dd>Price moved enough against the setup to invalidate it before triggering.</dd>
          </div>
          <div>
            <dt>TP1 hit</dt>
            <dd>Price reaches the first target — half the position closes and the stop moves to break-even.</dd>
          </div>
          <div>
            <dt>Stop hit</dt>
            <dd>Price hits the stop before ever reaching TP1 — the full position closes at a loss.</dd>
          </div>
          <div>
            <dt>TP2 / trail stop</dt>
            <dd>Price reaches the second target, or the trailing stop (which ratchets up after TP1) is hit — the remainder closes.</dd>
          </div>
        </dl>
      </div>
    }

    <sb-panel heading="Open positions" [flush]="true">
      <!-- SR59, the last cosmetic row: dashboard_fragment.html:391's
           shares tooltip. A panel note rather than a per-cell title, per this
           task's Step 2 — and because the per-trade half of it (which sizing
           mode a position was opened under, and whether that still matches
           today's setting) reads from sizing_mode, which lives on the
           detail payload and belongs on the detail view.

           Padded explicitly: the panel is flush (the tables below need
           edge-to-edge rows), which zeroes the body's own padding, so
           without this the text would sit flush against the panel's left
           edge while the "Open positions" heading above keeps the header's
           padding — two pieces of text in one panel with different left
           edges. The panel-note class below restores just that one inset. -->
      <p class="section-help panel-note">
        Share counts are snapshotted when a position opens. A trade logged
        before that snapshot existed shows an estimate instead, and a position
        opened under a different sizing mode will not match the premium note
        above.
      </p>

      <!-- Four groups, not one merged list. status=open (ACTIVE-or-PARTIAL)
           is the only existing alias and it drops PENDING and CLOSED
           entirely; splitting this way is also what "clear separation for
           each category" needs, not just what the endpoint happens to
           support. Each group is its own store instance -- see
           trade-group.ts -- so a slow or failed fetch for one category never
           blocks or blanks the other three.

           Active first: it is what "what is happening right now" actually
           means -- a filled, live position -- with Pending (waiting to fill)
           and Partial (already de-risked) behind it. Closed goes last: it is
           the one category that is no longer live. -->
      <!-- Active/Pending/Partial share openVisible -- the shared picker
           list with 'closed_at' dropped, since a position that has not
           closed has nothing to put there. See openVisible/closedVisible
           below for why each group gets its own derived list rather than
           the raw visible signal. -->
      <sb-trade-group
        status="ACTIVE"
        heading="Active"
        explanation="Entry has filled — position is open and being tracked toward TP1/stop."
        [columns]="columns()"
        [visible]="openVisible()"
        [pinned]="pinned"
        [rowKey]="rowKey"
        [emptyState]="activeEmptyState"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      />
      <sb-trade-group
        status="PENDING"
        heading="Pending"
        explanation="Plan built and posted, but price has not yet reached the entry trigger."
        [columns]="columns()"
        [visible]="openVisible()"
        [pinned]="pinned"
        [rowKey]="rowKey"
        [emptyState]="pendingEmptyState"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      />
      <sb-trade-group
        status="PARTIAL"
        heading="Partial"
        explanation="TP1 hit — half the position closed, the remainder rides toward TP2 with its stop at break-even."
        [columns]="columns()"
        [visible]="openVisible()"
        [pinned]="pinned"
        [rowKey]="rowKey"
        [emptyState]="partialEmptyState"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      />
      <!-- Closed last: unlike the three above, it is scope-aware -- Today
           narrows it to today's closes (mirroring the lifecycle strip's own
           CLOSED count), All days shows the most recent closes regardless of
           date. The today input re-binds on every scope toggle rather than
           only at mount -- see trade-group.ts's own constructor comment.

           closedVisible, not the raw visible list: 'now' (a live price) is
           meaningless once a position has closed, and 'hold' (the completed
           hold duration) belongs here and nowhere else. -->
      <sb-trade-group
        status="CLOSED"
        heading="Closed"
        [explanation]="closedExplanation()"
        [today]="closedToday()"
        [columns]="columns()"
        [visible]="closedVisible()"
        [pinned]="pinned"
        [rowKey]="rowKey"
        [emptyState]="closedEmptyState()"
        (rowActivate)="open($event)"
        (reorder)="onReorder($event)"
      />
    </sb-panel>

    <!-- SR59. dashboard_fragment.html:443-445, with ONE claim deliberately
         changed rather than copied: that line said "live prices refresh
         approximately every 15 seconds", which was true of the Jinja page's
         polling timer. DASHBOARD_REFRESH_SECONDS is read only by
         admin/app.py and admin/pages.py -- both Jinja. This SPA refreshes
         on server events, so copying the sentence would have stated a stale
         threshold, which the task's Step 3 calls worse than no copy. -->
    <p class="footnote">
      Prices and P&L update when the bot reports a change, not on a timer.
      @if (riskSizingNote(); as note) {
        · {{ note }}
      }
      · <code>!account</code> to change
    </p>
    </sb-async>

    <ng-template #statusCell let-row>
      <sb-status-cell [row]="row" />
    </ng-template>
    <ng-template #planCell let-row>
      <sb-plan-cell
        [entry]="row.entry"
        [target]="row.target"
        [stop]="row.stop_loss"
        [trigger]="row.trigger_price"
        [trailing]="row.status === 'PARTIAL'"
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
        <span [class]="pnlClass(row.pnl_pct)">
          {{ fmtPct(row.pnl_pct) }}
          <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
        </span>
      } @else {
        <span
          class="pnl-plan"
          title="Live P&L, then projected P&L at target and at stop"
        >
          <span [class]="pnlClass(livePnlPct(row))">
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
        <span [class]="pnlClass(row.r_multiple)">{{ fmtSigned(row.r_multiple) }}</span>
        <sb-magnitude [value]="row.r_multiple" [max]="R_MAGNITUDE_MAX" />
      } @else {
        <span
          class="expected"
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
  `,
  styles: `
    /* -- SR59: explanatory copy ----------------------------------- */
    .explainer {
      margin-bottom: var(--space-10);
      padding: var(--space-8) var(--space-10);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      border-radius: var(--radius-sm);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      line-height: 1.5;
    }
    .explainer code { font-family: var(--font-mono); }

    /* The GAP between the Active/Pending/Partial/Closed group cards (each
       card's own border/background is trade-group.ts's .group rule).
       Lives HERE rather than in trade-group.ts's own styles: a component's
       emulated-encapsulation stylesheet can only style its own template's
       elements, and "the sibling group before this one" is not one of
       them -- there is no legal selector inside TradeGroup for "the
       previous instance of myself". The previous attempt tried a
       :host + :host rule anyway; Angular's compiler accepted it, but its
       ShadowCSS shim cannot actually translate a repeated :host in one
       compound selector and silently emitted an invalid selector in its
       place (an nghost attribute selector joined to a literal, unclosed
       "-shadowcsshost" token) -- not valid CSS, so the rule never matched
       in the browser either (confirmed by grepping the built chunk).

       This rule has none of that problem: the sb-trade-group tag here is a
       plain child element of THIS component's own template, so a plain tag
       selector needs no :host translation at all. --space-20 is the largest
       spacing token the scale offers (v18 deliberately removed --space-28 as
       unused) -- reported as the four tables running together with no
       separation at all, so real margin plus each one's own card border
       (rather than a shared hairline that reads as just another row
       divider) is what actually answers that, not a bigger number. */
    sb-trade-group + sb-trade-group {
      display: block;
      margin-top: var(--space-20);
    }

    .footnote {
      margin-top: var(--space-8);
      color: var(--text-faint);
      font-size: var(--text-chip);
      text-align: right;
    }
    .footnote code { font-family: var(--font-mono); }

    /* -- SR58: scope toggle ---------------------------------------- */
    /* Groups the stale message and the scope toggle into one actions
       projection -- as two separate ones they would land at opposite
       ends of sb-section-head's space-between instead of clustered. */
    /* :host's own grid gap (below) already separates this from .primary
       above it -- no margin of its own needed, just the right alignment. */
    .realized-count {
      display: block;
      text-align: right;
      color: var(--text-faint);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
    }

    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

    /* Flexbox, not a fixed grid track count, across all three rows below
       (.primary, .chips, .lifecycle): equal width was never the actual
       requirement, filling the row was -- a label long enough to need more
       room should get it rather than every card being squeezed to the same
       fraction. flex: 1 1 auto sizes each card to its own content first
       (so a short "Lv4" card and a long "Position premium" one are allowed
       to differ) and then grows every card by an equal SHARE of whatever
       width is left, which is what actually fills the row edge to edge.
       align-items: stretch (flex's own default, stated explicitly here
       because it is the point) is what makes every card in the row match
       the row's tallest one -- MetricCard/MetricChip's own host fills that
       stretched height with their visible border/background box; see their
       own height: 100% rule for why that isn't automatic. No max-width cap
       any more: the row fills whatever width the page column has, matching
       the Open positions tables below, which never had one. */
    .primary {
      display: flex;
      align-items: stretch;
      gap: var(--space-14);
    }
    .primary > sb-metric-card { flex: 1 1 auto; min-width: 140px; }

    /* Overrides sb-chip-row's own align-items: center -- stretch is what
       makes every card in the row match its tallest sibling. The type
       selector plus this class gives it enough specificity to beat the
       primitive's own :host rule. */
    sb-chip-row.chips { align-items: stretch; }
    sb-chip-row.chips > sb-metric-chip { flex: 1 1 auto; min-width: 150px; }

    /* SR53. One row, lifecycle order, sized to the count rather than the
       label -- the number is what is being read. */
    .lifecycle {
      display: flex;
      align-items: stretch;
      flex-wrap: wrap;
      gap: var(--space-8);
    }
    /* One line -- "1 PENDING" -- not the count stacked over the label.
       Baseline-aligned like a MetricChip's own label/value pair, just
       count-first: this is a count of plans, not a labelled figure the
       label should lead. */
    .lc {
      flex: 1 1 auto;
      min-width: 100px;
      display: flex;
      align-items: baseline;
      gap: var(--space-6);
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

    /* margin: 0 auto centres the ROW (diagram + legend together) in the
       page column, which is otherwise left-aligned throughout -- a figure
       reads as a figure partly by not sharing the running copy's edge.
       max-width caps it well short of the full-width column so it doesn't
       stretch into two things floating far apart on a wide screen. */
    .lifecycle-figure {
      display: flex;
      /* stretch, not center: the two children should share the ROW's own
         height rather than each sitting at its own natural size with a gap
         above or below whichever one is shorter. The diagram centres its
         SVG vertically within that stretched height (its own :host), and
         the legend spreads its six rows across it (align-content below) --
         between the two, whichever side ends up taller sets the row's
         height and the other one fills it, rather than looking mismatched. */
      align-items: stretch;
      justify-content: center;
      /* nowrap: the two MUST be one row, not wrap onto two stacked ones --
         flex-wrap's default single-row-if-it-fits behaviour is not a
         guarantee, and this was observed wrapping despite fitting the
         column width. Stacks below 720px instead (media query at the
         bottom), matching every other row on this page. */
      flex-wrap: nowrap;
      gap: var(--space-20);
      /* width: 100% alongside max-width, not max-width alone: this is a
         GRID item (the Dashboard's own :host) that ALSO happens to be a
         flex container -- under that combination "auto" resolved to a
         shrink-to-fit width around the children's shrunk sizes instead of
         the grid's own stretch default, so the row rendered at ~660px
         (and centred inside itself) even though the column had 1300px to
         give it and max-width said 960 was fine. Forcing width: 100% first
         is what makes max-width actually the cap it looks like on paper. */
      width: 100%;
      max-width: 960px;
      margin: 0 auto;
    }
    sb-plan-lifecycle-diagram { flex: 1 1 420px; min-width: 280px; max-width: 620px; }
    .lifecycle-legend {
      flex: 1 1 300px;
      max-width: 340px;
      margin: 0;
      display: grid;
      gap: var(--space-6);
      /* Spreads the six rows across the full stretched height (see
         .lifecycle-figure's own comment) instead of clumping them at the
         top with empty space below -- the grid equivalent of
         justify-content: space-between. */
      align-content: space-between;
    }
    .lifecycle-legend > div {
      display: flex;
      gap: var(--space-8);
      align-items: baseline;
    }
    .lifecycle-legend dt {
      flex: 0 0 auto;
      min-width: 96px;
      color: var(--text);
      font-weight: 600;
      font-size: var(--text-chip);
    }
    .lifecycle-legend dd {
      margin: 0;
      color: var(--text-secondary);
      font-size: var(--text-chip);
      line-height: 1.4;
    }

    /* The panel is flush so the table can run edge to edge; anything else
       inside it has to bring its own padding. */
    .table-error {
      padding: var(--space-8) var(--space-14);
      color: var(--warn);
      font-size: var(--text-table);
    }

    /* Restores the header's left inset for text sitting directly in the
       flush panel body -- see the template comment above .panel-note's one
       use. Top spacing too, so it doesn't crowd the panel's header rule. */
    .panel-note {
      padding: var(--space-10) var(--space-14) 0;
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
      .primary { flex-direction: column; }
      .lifecycle-figure { flex-direction: column; align-items: center; }
      sb-plan-lifecycle-diagram, .lifecycle-legend { max-width: 100%; }
    }
  `,
})
export class Dashboard {
  private readonly router = inject(Router);
  protected readonly store = inject(DashboardStore);
  /** For the currency symbol alone. `ConnectionStore` is root-provided and
   *  the shell already keeps it fresh, so reading it here costs no request. */
  private readonly connection = inject(ConnectionStore);

  /** Zero open positions is a RESULT (the scan found nothing qualifying in
   *  this scope), not missing data -- measured-zero, not no-data-yet. */
  protected readonly async = computed(() =>
    asyncInputs(this.store, { isEmpty: (data) => data.open_trades === 0 }),
  );

  /** The suffix a money card renders after its number — a leading space, then
   *  the account's symbol. Three cards had `" USD"` written into the template
   *  while `CURRENCY_SYMBOL` has defaulted to `€` all along. */
  protected readonly currencyUnit = computed(() => ` ${this.connection.currency()}`);

  protected readonly rowKey = (row: TradeRow) => row.id;

  /** One per lifecycle category shown below -- `sb-trade-group` owns its own
   *  data, but the empty-state copy is naming a plan's absence at a specific
   *  stage, which reads as three different facts and not one. */
  protected readonly pendingEmptyState: EmptyState = {
    title: 'No pending plans',
    hint: 'They appear here once a plan is posted, waiting for its entry trigger.',
  };
  protected readonly activeEmptyState: EmptyState = {
    title: 'No active positions',
    hint: 'They appear here once a plan’s entry fills.',
  };
  protected readonly partialEmptyState: EmptyState = {
    title: 'No partial positions',
    hint: 'They appear here once TP1 hits and part of the position closes.',
  };

  /** The Closed group's `today` input: `true` in Today mode (narrows to
   *  trades closed today, same rule the lifecycle strip's CLOSED count
   *  already uses), `null` in All days (unfiltered -- most recent closes). */
  protected readonly closedToday = computed(() =>
    this.store.scope() === 'all' ? null : true,
  );

  /** Copy for the Closed group, scope-aware like `realizedLabel` above --
   *  wording that says "today" would mislead in All days, and vice versa. */
  protected readonly closedExplanation = computed(() =>
    this.store.scope() === 'all'
      ? 'Fully closed (win, loss, or scratch) — most recent closes.'
      : 'Fully closed today (win, loss, or scratch).',
  );
  protected readonly closedEmptyState = computed<EmptyState>(() => ({
    title: this.store.scope() === 'all' ? 'No closed trades yet' : 'No trades closed today',
    // Not "TP2 or a stop" -- that names only the PARTIAL exit. A position
    // closes on hitting ITS target or ITS stop regardless of which lifecycle
    // stage it was in when that happened: straight from Active (stop before
    // TP1, or a single-target strategy's only target) just as much as from
    // Partial (TP2, or the break-even stop after TP1).
    hint: 'They appear here once a position’s target or stop closes it out '
      + '— whether that happens straight from Active or after TP1 from Partial.',
  }));

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

  /** See dashboard.helpers.ts -- `deriveClosedVisible`/`deriveOpenVisible`
   *  for what each group's own column order does and why, `reconcileReorder`
   *  for how a drag inside one group's table writes back to the shared
   *  picker list without leaking that group's own additions/omissions into
   *  the other three. */
  protected readonly closedVisible = computed(() => deriveClosedVisible(this.visible()));
  protected readonly openVisible = computed(() => deriveOpenVisible(this.visible()));

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
      ticker: this.tickerCell(),
      pnl_pct: this.pnlCell(),
      r_multiple: this.rMultipleCell(),
      status: this.statusCell(),
      plan: this.planCell(),
      confidence_level: this.confidenceCell(),
      opened_at: this.openedCell(),
      closed_at: this.closedCell(),
    };
    return tradeColumns().map((column) =>
      cells[column.key] ? { ...column, cell: cells[column.key] } : column,
    );
  });

  /** Amber once exposure is most of the cap. Amber means caution, which is
   *  what "nearly out of risk budget" is -- it is not a loss, so it must
   *  not be red. */
  /* -- SR59: the copy ------------------------------------------------- */

  /** The Jinja page appended "· closed today" only in the today/active
   *  modes, because in All days the count is not today's. Same rule here. */
  protected readonly closedQualifier = computed(() =>
    this.store.scope() === 'all' ? '' : ' today',
  );

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

  /** The risk-% half of the footer note, present only when that is the mode
   *  actually in use. */
  protected readonly riskSizingNote = computed<string | null>(() => {
    const note = this.store.sizingNote();
    const riskPct = note?.['risk_pct'];
    return typeof riskPct === 'number' ? `Sizing based on ${riskPct}% risk` : null;
  });

  /** `_plans_board.html`'s `lc_tips`, verbatim. */
  private readonly lifecycleTips: Record<string, string> = {
    PENDING:
      'Plan built and posted, but price has not yet reached the entry trigger. '
      + 'Cancelled automatically if it expires or the setup is invalidated first.',
    ACTIVE:
      'Entry has filled — position is open and being tracked toward TP1/stop.',
    PARTIAL:
      'TP1 hit: half the position was closed for a partial win, the remainder '
      + 'rides toward TP2 with its stop moved to break-even.',
    CLOSED:
      'Fully closed today (win, loss, or scratch) — see Trade History for the '
      + 'full log.',
    CANCELLED:
      'Cancelled today, before ever filling — either it expired waiting for '
      + 'entry, or the setup was invalidated.',
  };

  protected lifecycleTip(status: string): string | null {
    return this.lifecycleTips[status] ?? null;
  }

  /* -- SR58: the date scope ------------------------------------------- */

  /** The Jinja dashboard had three; `active` ("Today + open") and `today`
   *  are merged into this one Today button. The server already computed the
   *  realised figures identically for both, and Today's definition now
   *  folds in "or still open, however old" on its own (see `todayParam`),
   *  so a separate "+ open" choice had nothing left to distinguish. */
  protected readonly scopes: { mode: DashboardScope; label: string }[] = [
    { mode: 'today', label: 'Today' },
    { mode: 'all', label: 'All days' },
  ];

  /** Names the window in the card itself, so a figure cannot be read as
   *  today's when the toggle is on All days. */
  protected readonly realizedLabel = computed(() =>
    this.store.scope() === 'all' ? 'Realised, all days' : 'Realised today',
  );

  /** The lifecycle strip's click-through date filter, mirroring this same
   *  `=== 'all'` split -- `null` drops the query param entirely (an empty
   *  string would land in the URL as `today=`), so All days keeps sending
   *  what "click a card" always meant: status only, no date. */
  protected readonly todayParam = computed(() =>
    this.store.scope() === 'all' ? null : '1',
  );

  protected readonly riskTone = computed(() =>
    (this.store.riskUtilisation() ?? 0) >= 0.8 ? 'caution' : 'plain',
  );

  protected readonly riskSub = computed(() => {
    const cap = this.store.riskCapPct();
    return cap === null ? null : `of ${cap.toFixed(1)}% cap`;
  });

  /** In risk-% sizing there is no single premium -- position value varies per
   *  trade with the stop distance, up to the max-position cap -- so the chip
   *  says "max" rather than presenting a ceiling as a typical cost. */
  protected readonly premiumUnit = computed(() =>
    this.store.positionPremiumIsCap()
      ? `${this.currencyUnit()} max`
      : this.currencyUnit(),
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

  /** sb-magnitude's max for the R column. Not an observed max from the
   *  store: the four groups below (Active/Pending/Partial/Closed) each fetch
   *  their own page through their own TradeGroup-scoped TradesStore, and all
   *  four share this one cell template -- there is no single "this table's
   *  rows" to measure from here. R is already a normalised unit (the risk
   *  taken, by definition 1R), so a fixed reference scale is the more
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
