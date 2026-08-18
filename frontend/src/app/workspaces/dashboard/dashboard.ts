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
import { Button } from '../../ui/button';
import { ColumnDef, Density, EmptyState, RowContext } from '../../ui/data-table/data-table.types';
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
import { dateTime, held, money, num, pct, rMultiple } from '../../ui/format';
import { ControlRow, Panel } from '../../ui/layout';
import { MetricCard } from '../../ui/metric-card';
import { MetricChip } from '../../ui/metric-chip';
import { Sparkline } from '../../ui/sparkline';
import {
  deriveClosedVisible,
  deriveOpenVisible,
  expectedPnlPct,
  expectedR,
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
    RouterLink, MetricCard, MetricChip, Sparkline, Panel, TradeGroup,
    StatusCell, DirectionArrow, PlanCell, ConfidenceCell, Button, ControlRow,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Provided here rather than in root: the store is created on entry and
  // destroyed on exit, so a workspace does not hold stale state while you
  // are looking at another one. Each `sb-trade-group` below provides its own
  // `TradesStore` instance (see trade-group.ts) -- neither this one nor
  // those three touch the Trades workspace's own copy.
  providers: [DashboardStore],
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
      <sb-control-row class="scope" role="group" aria-label="Date scope">
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
    </header>

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

    <!-- SR58. Realised, scoped by the toggle above -- distinct from the
         Open P&L card, which is unrealised and always all-open. -->
    <div class="realized">
      <sb-metric-card
        [label]="realizedLabel()"
        [value]="store.realizedAmount()"
        tone="pnl"
        [unit]="currencyUnit()"
      />
      <sb-metric-card
        label="Realised, average"
        [value]="store.realizedPct()"
        tone="pnl"
        unit="%"
      />
      <span class="realized-count">
        {{ store.realizedCount() }} closed{{ closedQualifier() }} ·
        {{ store.realizedWins() }}W / {{ store.realizedLosses() }}L
      </span>
    </div>

    <div class="primary">
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

    <!-- The % alone didn't say how much money that was -- pairing it with
         the realised amount (same sign, same field realized_pnl_amount
         Trade History already shows in its own "Realised" column) answers
         that without a second column. Only ever populated together: both are
         null until a position closes.

         pnl_pct itself is null for every PENDING/ACTIVE/PARTIAL row --
         dashboard.py's closed_pnl needs an exit_price, which does not
         exist until a position closes -- so those three groups fell through
         to an em dash regardless of how good the plan looked. The else
         branch computes what the % (and, in rMultipleCell below, the R)
         WOULD be if price reaches target, from the same entry/stop/target
         the Plan cell already shows; the dashed underline (PlanCell's own
         "pending" look) marks it as projected rather than realised. -->
    <ng-template #pnlCell let-row>
      @if (row.pnl_pct !== null) {
        <span [class]="pnlClass(row.pnl_pct)">
          {{ fmtPct(row.pnl_pct) }}
          <span class="pnl-amount"> ({{ fmtMoney(row.realized_pnl_amount) }})</span>
        </span>
      } @else {
        <span
          class="expected"
          [class]="pnlClass(expectedPnlPct(row))"
          title="Projected P&L if price reaches target"
        >{{ fmtPct(expectedPnlPct(row)) }}</span>
      }
    </ng-template>

    <!-- See pnlCell above -- same real-vs-projected split, same reasoning. -->
    <ng-template #rMultipleCell let-row>
      @if (row.r_multiple !== null) {
        {{ fmtR(row.r_multiple) }}
      } @else {
        <span
          class="expected"
          [class]="pnlClass(expectedR(row))"
          title="Projected R if price reaches target"
        >{{ fmtR(expectedR(row)) }}</span>
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

    /* The break between the Active/Pending/Partial/Closed group tables.
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
       selector needs no :host translation at all. A visibly stronger rule
       than the --border used inside a table (row dividers, the panel's own
       edge) -- four same-shaped tables stacked in one flush panel need a
       break the eye catches without reading the heading text, not just a
       hairline that reads as another row divider. */
    sb-trade-group + sb-trade-group {
      display: block;
      margin-top: var(--space-20);
      border-top: 2px solid var(--border-strong);
      padding-top: var(--space-14);
    }

    .footnote {
      margin-top: var(--space-8);
      color: var(--text-faint);
      font-size: var(--text-chip);
      text-align: right;
    }
    .footnote code { font-family: var(--font-mono); }

    /* -- SR58: scope toggle and realised row ---------------------- */
    .scope { margin-left: auto; }
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

    /* minmax(0, 1fr), not the implicit auto track. An auto column is floored
       at its widest child's min-content, so one un-shrinkable panel stretched
       the workspace past the viewport and took the page sideways with it.
       Clamping the track is what makes the children's own overflow-x
       containers the thing that scrolls instead.
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-20); }

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

    .row-link { color: var(--accent); font-family: var(--font-mono); text-decoration: none; }
    .row-link:hover { text-decoration: underline; }

    .pos { color: var(--pos); }
    .neg { color: var(--neg); }
    /* Muted and smaller than the % it rides beside -- the percentage is the
       headline figure, the amount is context for it, not a second headline. */
    .pnl-amount { color: var(--text-secondary); font-size: var(--text-chip); }
    /* Same "not real yet" language as PlanCell's own .entry.pending -- a
       dashed underline rather than a colour, since the pos/neg palette
       already means something else (gain vs loss) and this axis (realised
       vs projected) is orthogonal to it. */
    .expected { border-bottom: 1px dashed currentColor; }
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
  /** For the currency symbol alone. `ConnectionStore` is root-provided and
   *  the shell already keeps it fresh, so reading it here costs no request. */
  private readonly connection = inject(ConnectionStore);

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
  private readonly directionCell =
    viewChild.required<TemplateRef<RowContext<TradeRow>>>('directionCell');
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
      direction: this.directionCell(),
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

    const cap = typeof maxAbs === 'number' && maxAbs > 0
      ? `${maxPct}% of balance or ${maxAbs.toLocaleString()} absolute, whichever is tighter`
      : `${maxPct}% of balance`;

    return `Risk % mode — risks ${risk.toLocaleString()} (${riskPct}%) if stopped `
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
    this.store.positionPremiumIsCap()
      ? `${this.currencyUnit()} max`
      : this.currencyUnit(),
  );

  protected fmtPct = pct;
  protected fmtDate = dateTime;
  protected fmtR = rMultiple;

  protected fmtMoney(value: number | null): string {
    return money(value, this.connection.currency());
  }

  protected pnlClass(value: number | null): string {
    if (value === null) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }

  /** See dashboard.helpers.ts's `expectedPnlPct`/`expectedR` for what a
   *  projected value means and why it is null when it is. */
  protected expectedPnlPct = expectedPnlPct;
  protected expectedR = expectedR;

  /** Mouse activation, matching Trades: a row leads to its detail view. The
   *  ticker cell's anchor is the keyboard equivalent. */
  protected open(row: TradeRow): void {
    void this.router.navigate(['/trades', row.id]);
  }
}
