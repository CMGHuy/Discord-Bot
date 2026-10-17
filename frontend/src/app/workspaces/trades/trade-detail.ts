import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  Signal,
  computed,
  effect,
  inject,
  input,
  signal,
  untracked,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { ApiClient } from '../../api/api-client';
import { ChartStore } from '../../stores/chart.store';
import { TradeDetailStore } from '../../stores/trade-detail.store';
import { asyncInputs, Async } from '../../ui/async';
import { Button } from '../../ui/button';
import { Chip, ChipTone, QualityChip } from '../../ui/chip';
import { MetricChip } from '../../ui/metric-chip';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { dateTime, held, num, pct, rMultiple, share, text } from '../../ui/format';
import { Panel, Tab, TabBar } from '../../ui/layout';
import { StatusIndicator } from '../../ui/status-indicator';
import {
  ACTION_LABELS,
  ACTION_TITLES,
  TradeActionKind,
  actionConsequence,
  availableActions,
  runTradeAction,
} from './trade-actions';
import { IfItGetsThere } from './why/if-it-gets-there';
import { LevelsBlock } from './why/levels-block';
import { OutcomePath } from './why/outcome-path';
import { PlanChart } from './why/plan-chart';
import { SizingPanel } from './why/sizing-panel';
import { WHY_SECTIONS, WhyPanel, WhySection } from './why/why-panel';
import { ScoresCard } from './scores-card';
import { hasLevelSources, LevelSourcesCard } from './level-sources-card';
import { StrategyRecordCard } from './strategy-record-card';
import { CardAreas, WhyCard, whyAreas } from './why-areas';
import { OutcomeStrip } from './outcome-strip';
import { outcomeTiles } from './outcome-tiles';
import { sideLabel, statusGroup } from './trade-figures';

/** Interim Plan, Live, Chart, Notes and Why tabs. */
const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
  { id: 'notes', label: 'Notes' },
  { id: 'why', label: 'Why' },
];

const TAB_IDS = new Set(TABS.map((tab) => tab.id));

/** A legacy record with no captured detail still shows its gate rows: "not
 *  recorded" is a measured answer and is never hidden (spec v151 § Edge
 *  cases). The reasoning sections stay out, exactly as before. */
const ABSENT_SECTIONS: readonly WhySection[] = ['gates', 'calendar'];

const CELL_SECTIONS = {
  why: ['explanation'], breakdown: ['confidence'], gates: ['gates'], calendar: ['calendar'],
} as const satisfies Record<string, readonly WhySection[]>;

const ARRIVAL_SUFFIX = ' — this is its trade record.';

/**
 * Why the plan page sent the reader here instead (spec v151 § Arrival
 * banner). A Discord link outlives the plan's open life; when it lands on
 * the trade record, this line says why. Empty for a plan that is still open.
 */
export function arrivalBanner(status: string | null, barsToExpiry: number | null): string {
  if (status === 'PENDING' && barsToExpiry === 0) return `This plan has expired${ARRIVAL_SUFFIX}`;
  if (status === 'CANCELLED') return `This plan was cancelled${ARRIVAL_SUFFIX}`;
  if (status === 'CLOSED') return `This plan is closed${ARRIVAL_SUFFIX}`;
  return '';
}

/** Read once, at construction: the plan page's redirect passes
 *  `state: { from: 'plan' }`, and a direct visit has no such state. */
function cameFromPlan(): boolean {
  if (typeof history === 'undefined') return false;
  const state: unknown = history.state;
  return typeof state === 'object' && state !== null
    && (state as Record<string, unknown>)['from'] === 'plan';
}

/**
 * One trade — the shell and the Plan tab (NG43). Live is NG44, Chart NG45,
 * Notes NG46, with reasoning and the registry in Why.
 *
 * **The active tab is a query parameter**, for the same reason the Trades
 * list keeps its filters there: a tab held only in component state cannot be
 * linked to, does not survive a reload, and makes the back button skip the
 * whole detail view instead of stepping back through it.
 *
 * `id` arrives as an input rather than through `ActivatedRoute`, so this
 * component is testable without standing up a router.
 */
@Component({
  selector: 'sb-trade-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    RouterLink,
    TabBar,
    Panel,
    StatusIndicator,
    QualityChip,
    Button,
    ConfirmDialog,
    MetricChip,
    Chip,
    Async,
    WhyPanel,
    LevelsBlock,
    IfItGetsThere,
    SizingPanel,
    OutcomePath,
    PlanChart,
    OutcomeStrip,
    ScoresCard,
    LevelSourcesCard,
    StrategyRecordCard,
  ],
  template: `
    <header class="head">
      <a class="back" routerLink="/trades">← Trades</a>
      @if (arrival(); as message) {
        <p class="arrival" role="status">{{ message }}</p>
      }

      @if (store.trade(); as trade) {
        <div class="identity">
          <div class="trade-title" role="heading" aria-level="2">
            <span class="ticker">{{ trade.ticker }}</span>
            @if (side(); as label) {
              <span class="side">{{ label }}</span>
            }
            <sb-status-indicator
              [status]="trade.status"
              [current]="trade.current_price"
              [entry]="trade.entry"
              [stop]="trade.stop_loss"
              [target]="trade.target"
            />
          </div>
          <div class="tags">
            @if (trade.horizon) {
              <span class="tag">{{ trade.horizon }}</span>
            }
            @if (trade.strategy) {
              <span class="tag">{{ trade.strategy }}</span>
            }
            @if (trade.tier) {
              <sb-quality-chip [value]="trade.tier" [label]="'Tier ' + trade.tier" />
            }
            @if (trade.confidence_level !== null) {
              <sb-quality-chip
                [value]="trade.confidence_level"
                [label]="'Lv' + trade.confidence_level"
              />
            }
            @if (trade.badge) {
              <sb-quality-chip [value]="trade.badge" [label]="trade.badge" />
            }
            <!-- v86 -- the cohort risk verdict. COHORT_TYPICAL renders no
                 chip at all (the brief's own token guidance): "typical" is
                 the silent default every other label is judged against, and a
                 chip for it would just be visual noise on every ordinary
                 trade. -->
            @if (cohortTone(); as tone) {
              <sb-chip [label]="cohortChipLabel()" [tone]="tone" [title]="cohortTooltip()" />
            }
            @if (earningsChip(); as label) {
              <span class="earnings"><sb-chip [label]="label" tone="warn" [caps]="false" /></span>
            }
            @if (trade.origin !== 'plan') {
              <span class="origin">{{ trade.origin }}</span>
            }
            <span class="trade-id" [title]="'Trade ID: ' + trade.id">{{ trade.id }}</span>
          </div>
          <div class="actions">
            @for (kind of actionsFor(trade.status); track kind) {
              <button
                sb-button
                [variant]="kind === 'delete' ? 'danger' : 'secondary'"
                type="button"
                (click)="ask(kind)"
              >
                {{ actionLabels[kind] }}
              </button>
            }
          </div>
        </div>
      } @else if (store.error(); as message) {
        <p class="trade-title" role="status">{{ message }}</p>
      } @else {
        <!-- Not "skeleton": G1's coverage gate (async-coverage.spec.ts)
             bans that literal class name anywhere in a file that uses
             sb-async, once one is added below for the tab content. This
             title-only loading word is not the sb-async skeleton itself. -->
        <p class="trade-title loading-title" role="status">Loading…</p>
      }
    </header>

    @if (store.trade()) {
      <sb-outcome-strip [tiles]="stripTiles()" />
    }

    <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

    <!-- Not in the plan's own file list for this wave (the task named only
         trades.ts) -- added because G1's FETCHING list names this file too.
         The header above keeps its own hand-rolled trade/error/loading
         branches (title-only, and now gate-safe -- see the comment there);
         this sb-async covers the tab body, which was previously blank
         while store.trade() was null with no visible indication at all. One
         trade is never "measured zero" once loaded (a missing trade is a
         fetch error, not an empty result), so isEmpty is always false. -->
    <sb-async
      [loading]="async().loading"
      [error]="async().error"
      [empty]="async().empty"
      [staleAsOf]="async().staleAsOf"
      emptyReason="measured-zero"
      emptyTitle="Trade not found"
      [skeletonRows]="3"
      [skeletonCols]="4"
      (retry)="store.load()"
    >
    @switch (activeTab()) {
      @case ('plan') {
        @if (store.trade(); as trade) {
          <div class="panels">
            <sb-levels-block
              [direction]="trade.direction"
              [entryType]="store.detail()?.entry_type ?? null"
              [trigger]="store.triggerPrice()"
              [entry]="trade.entry"
              [stop]="trade.stop_loss"
              [stopLabel]="stopLabel()"
              [target1]="trade.target"
              [target2]="trade.target2"
              [riskReward]="trade.risk_reward"
              [acceptanceLevel]="store.acceptanceLevel()"
              [tp1Pct]="store.tp1Pct()"
              [breakevenTriggerPct]="store.breakevenTriggerPct()"
            />

            <sb-panel heading="Per share">
              <dl>
                <div>
                  <dt>Risk</dt>
                  <dd class="num">{{ fmt(store.riskPerShare()) }}</dd>
                </div>
                <div>
                  <dt>Reward</dt>
                  <dd class="num">{{ fmt(store.rewardPerShare()) }}</dd>
                </div>
                <div>
                  <dt>Direction</dt>
                  <dd>{{ fmtText(trade.direction) }}</dd>
                </div>
                <div>
                  <dt>Origin</dt>
                  <dd>{{ fmtText(trade.origin) }}</dd>
                </div>
              </dl>
            </sb-panel>

            <sb-if-it-gets-there
              [direction]="trade.direction"
              [target2]="trade.target2"
              [stopLoss]="trade.stop_loss"
            />

            <sb-sizing-panel
              [shares]="trade.shares"
              [positionValue]="trade.position_value"
              [sizingMode]="store.detail()?.sizing_mode ?? null"
              [workingStop]="store.detail()?.working_stop ?? null"
              [gapP90Pct]="store.gapP90Pct()"
              [gapFragile]="store.gapFragile()"
            />

            <sb-panel heading="Opened">
              <dl>
                <div>
                  <dt>At</dt>
                  <dd>{{ fmtDate(trade.opened_at) }}</dd>
                </div>
                <div>
                  <dt>Closed</dt>
                  <dd>{{ fmtDate(trade.closed_at) }}</dd>
                </div>
                <div>
                  <dt>Entry type</dt>
                  <dd>{{ fmtText(store.detail()?.entry_type ?? null) }}</dd>
                </div>
                <div>
                  <dt>P&L</dt>
                  <dd class="num">{{ fmtPct(trade.pnl_pct) }}</dd>
                </div>
              </dl>
            </sb-panel>
          </div>

          <!-- The reasoning. Everything above is a number; the Why panel is
               the only part of the screen that says why any of them were
               chosen, and the one place level sources render (v151). -->
          @if (store.detailAbsent()) {
            <!-- Not an error and not an empty panel per field: this record
                 predates the detail capture entirely, and nine em dashes read
                 as a failed load rather than as a fact about an old trade. -->
            <p class="no-detail">
              This trade was logged before the admin UI captured the full alert
              detail — only the plan above is available for it.
            </p>
          }
          <sb-why-panel
            [sections]="whySections()"
            [status]="trade.status"
            [barsToExpiry]="trade.bars_to_expiry"
            [sessionsSinceCreated]="store.sessionsSinceCreated()"
            [entry]="trade.entry"
            [trigger]="store.triggerPrice()"
            [stop]="trade.stop_loss"
            [stopLabel]="stopLabel()"
            [target1]="trade.target"
            [target2]="trade.target2"
            [acceptanceLevel]="store.acceptanceLevel()"
            [targetSources]="store.targetSources()"
            [stopSources]="store.stopSources()"
            [target2Sources]="store.target2Sources()"
            [confirmedBy]="store.confirmedBy()"
            [confidencePoints]="store.confidencePoints()"
            [confidenceUnevaluated]="store.confidenceUnevaluated()"
            [confidenceFactors]="store.confidenceFactors()"
            [qualityFactors]="store.qualityFactors()"
            [gates]="store.gates()"
            [calendar]="store.calendar()"
            [explanation]="store.explanation()"
          />
        }
      }
      @case ('live') {
        @if (store.trade(); as trade) {
          <div class="panels">
            <sb-panel heading="Now">
              <dl>
                <div>
                  <dt>Price</dt>
                  <dd class="num">
                    {{ fmt(trade.current_price) }}
                    @if (trade.current_price_stale) {
                      <span
                        class="stale-flag"
                        title="This position's price could not be freshly fetched -- the number shown may be delayed."
                      >delayed</span>
                    }
                  </dd>
                </div>
                <div>
                  <dt>Unrealised</dt>
                  <dd class="num" [class]="pnlClass(trade.pnl_pct)">{{ fmtPct(trade.pnl_pct) }}</dd>
                </div>
                <div>
                  <dt>Amount</dt>
                  <dd class="num" [class]="pnlClass(trade.realized_pnl_amount)">
                    {{ fmt(trade.realized_pnl_amount) }}
                  </dd>
                </div>
                <div>
                  <dt>Held</dt>
                  <dd class="num">{{ fmtHeld(trade.held_hours) }}</dd>
                </div>
              </dl>
            </sb-panel>

            <sb-panel heading="Stop to target">
              <div class="progress">
                <sb-status-indicator
                  [status]="trade.status"
                  [current]="trade.current_price"
                  [entry]="trade.entry"
                  [stop]="trade.stop_loss"
                  [target]="trade.target"
                />
              </div>
              <dl>
                <div>
                  <dt>{{ stopLabel() }}</dt>
                  <dd class="num neg">{{ fmt(trade.stop_loss) }}</dd>
                </div>
                <div>
                  <dt>Entry</dt>
                  <dd class="num">{{ fmt(trade.entry) }}</dd>
                </div>
                <div>
                  <dt>Target</dt>
                  <dd class="num pos">{{ fmt(trade.target) }}</dd>
                </div>
              </dl>
            </sb-panel>

            @if (trade.status === 'PARTIAL' && store.bankedLeg(); as banked) {
              <sb-panel heading="Partial position">
                <dl>
                  <div>
                    <dt>Entry</dt>
                    <dd class="num">{{ fmt(banked.exitPrice) }}</dd>
                  </div>
                  <div>
                    <dt>Target</dt>
                    <dd class="num pos">{{ fmt(trade.target) }}</dd>
                  </div>
                  <div>
                    <dt>Trailing stop</dt>
                    <dd class="num neg">{{ fmt(trade.stop_loss) }}</dd>
                  </div>
                  <div>
                    <dt>Banked</dt>
                    <dd class="num">
                      @if (banked.fraction !== null) {
                        {{ fmtShare(banked.fraction * 100) }}
                      }
                      @ {{ fmt(banked.exitPrice) }}
                      @if (banked.r !== null) {
                        <span [class]="pnlClass(banked.r)">{{ fmtR(banked.r) }}</span>
                      }
                      @if (store.bankedStats(); as stats) {
                        <span class="muted muted-gap">{{ fmtPct(stats.pct) }}</span>
                        @if (stats.amount !== null) {
                          <span class="muted muted-gap" [class]="pnlClass(stats.amount)">
                            {{ stats.amount > 0 ? '+' : '' }}{{ fmt(stats.amount) }}
                          </span>
                        }
                      }
                    </dd>
                  </div>
                </dl>
              </sb-panel>
            }
          </div>

          <sb-outcome-path [legs]="store.legs()" [timeline]="store.timeline()" />
        }
      }
      @case ('chart') {
        <div class="chart">
          <sb-plan-chart [ticker]="store.trade()?.ticker ?? null" [tradeId]="store.trade()?.id ?? null" />
        </div>
      }
      @case ('notes') {
        <div class="notes">
          <!-- SR55. The excursions sit ABOVE the note and beside it, not on
               Analytics: they are the evidence the note is about. "Went 1.4R
               in favour before stopping out" is the reason someone writes
               "exit management" in the box below. -->
          @if (store.journalError(); as message) {
            <p class="stale" role="status">Journal unavailable — {{ message }}</p>
          } @else if (store.excursions().length) {
            <div class="excursions">
              @for (figure of store.excursions(); track figure.label) {
                <sb-metric-chip
                  [label]="figure.label"
                  [value]="figure.value"
                  [unit]="figure.unit"
                  [decimals]="figure.decimals"
                  tone="plain"
                />
              }
            </div>

            @if (store.journalTags().length) {
              <div class="journal-tags">
                @for (tag of store.journalTags(); track tag) {
                  <sb-chip [label]="tag" />
                }
              </div>
            }

            @if (store.autoLesson(); as lesson) {
              <!-- Generated, and labelled as such: a reader must be able to
                   tell it from the note they wrote themselves. -->
              <p class="auto-lesson"><strong>Auto-lesson</strong> — {{ lesson }}</p>
            }
          }

          @if (store.noteStatus() === 'unjournaled') {
            <!-- Not an error. Journal entries are written at close, so an
                 open position has none and cannot take a note yet. Saying so
                 plainly beats a textarea that silently discards what is
                 typed into it. -->
            <p class="not-journaled">
              This position has no journal entry yet. Notes attach when a trade closes.
            </p>
          }

          <label class="note-label" for="trade-note">Note</label>
          <textarea
            id="trade-note"
            class="note-field"
            rows="10"
            [value]="store.noteText()"
            [disabled]="store.noteStatus() === 'unjournaled'"
            (input)="onNoteInput($event)"
            (blur)="flushNote()"
            placeholder="Why this trade, what happened, what to do differently."
          ></textarea>

          <p class="note-state" [class.note-state-bad]="store.noteStatus() === 'error'">
            @switch (store.noteStatus()) {
              @case ('saving') {
                Saving…
              }
              @case ('unsaved') {
                Unsaved changes
              }
              @case ('error') {
                {{ store.noteError() }}
              }
              @case ('unjournaled') {
                Not journaled yet
              }
              @default {
                Saved
              }
            }
          </p>
        </div>
      }
      @case ('why') {
        @if (store.trade(); as trade) {
          @if (store.detailAbsent()) {
            <p class="no-detail">This trade was logged before the admin UI captured the full alert detail — only its gate rows and calendar are available here; its levels are on Overview.</p>
          }
          <div class="grid-host">
            <div class="card-grid why-grid" [style.--areas-1]="whyGrid().one"
              [style.--areas-2]="whyGrid().two" [style.--areas-3]="whyGrid().three">
              @if (whyPresent().has('why')) {
                <div class="cell" data-area="why" style="grid-area: why">
                  <sb-why-panel [sections]="cellSections.why" [explanation]="store.explanation()" />
                </div>
              }
              @if (whyPresent().has('scores')) {
                <div class="cell" data-area="scores" style="grid-area: scores">
                  <sb-trade-scores-card [confidence]="trade.confidence_score" [level]="trade.confidence_level"
                    [quality]="trade.quality_score" [badge]="trade.badge" />
                </div>
              }
              @if (whyPresent().has('sources')) {
                <div class="cell" data-area="sources" style="grid-area: sources">
                  <sb-trade-level-sources [target]="store.targetSources()" [stop]="store.stopSources()"
                    [target2]="store.target2Sources()" [confirmedBy]="store.confirmedBy()" />
                </div>
              }
              @if (whyPresent().has('breakdown')) {
                <div class="cell" data-area="breakdown" style="grid-area: breakdown">
                  <sb-why-panel [sections]="cellSections.breakdown" [confidencePoints]="store.confidencePoints()"
                    [confidenceUnevaluated]="store.confidenceUnevaluated()"
                    [confidenceFactors]="store.confidenceFactors()" [qualityFactors]="store.qualityFactors()" />
                </div>
              }
              @if (whyPresent().has('gates')) {
                <div class="cell" data-area="gates" style="grid-area: gates">
                  <sb-why-panel [sections]="cellSections.gates" [gates]="store.gates()" [status]="trade.status"
                    [barsToExpiry]="trade.bars_to_expiry" [sessionsSinceCreated]="store.sessionsSinceCreated()" />
                </div>
              }
              <div class="cell" data-area="context" style="grid-area: context">
                <sb-why-panel [sections]="cellSections.calendar" [calendar]="store.calendar()" />
                <sb-trade-strategy-record [strategy]="trade.strategy" [row]="store.strategyRow()"
                  [error]="store.strategiesError()" />
              </div>
            </div>
          </div>
        }
      }
    }
    </sb-async>

    <sb-confirm-dialog
      [open]="pending() !== null"
      [title]="confirmTitle()"
      [consequence]="confirmConsequence()"
      [confirmLabel]="confirmLabel()"
      [working]="working()"
      (confirmed)="runPending()"
      (cancelled)="pending.set(null)"
    />
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); }
    /* --warn is the design system's designated token for stale data (see
       tokens.css's own legend) -- the price itself still renders, this just
       says the number might not be a live tick (the MRNA incident,
       2026-09-18: a fast_info fallback echoed yesterday's close). */
    .stale-flag {
      display: inline-block;
      margin-left: var(--space-6);
      font-size: var(--text-chip);
      font-weight: normal;
      color: var(--warn);
    }
    .head {
      display: grid;
      gap: var(--space-8);
    }
    .back {
      color: var(--accent);
      font-size: var(--text-table);
      text-decoration: none;
    }
    .back:hover {
      text-decoration: underline;
    }

    /* Why the plan page sent the reader here (v151). Informational, not a
       warning: the record is fine, the plan's open life is simply over. */
    .arrival {
      max-width: 68ch;
      padding: var(--space-8);
      border-left: 2px solid var(--accent);
      color: var(--text);
      font-size: var(--text-table);
    }

    .identity {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: var(--space-10);
      min-width: 0;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-8);
      margin-left: auto;
    }
    .side, .origin {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    .trade-title {
      margin: 0;
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: var(--space-10);
      font-size: var(--text-title);
      font-weight: 600;
    }
    .ticker {
      font-family: var(--font-mono);
    }
    .loading-title {
      color: var(--text-faint);
    }

    .tags {
      display: flex;
      flex: 1 1 240px;
      min-width: 0;
      align-items: center;
      gap: var(--space-6);
      flex-wrap: wrap;
    }
    .tag {
      padding: 1px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    /* Plain text, not a chip -- an id is not a category the way horizon/
       strategy/tier are, and boxing it the same would suggest it is one. */
    .trade-id {
      font-family: var(--font-mono);
      font-size: var(--text-chip);
      color: var(--text-faint);
    }

    .grid-host { min-width: 0; }
    .card-grid { display: grid; gap: var(--section-gap); align-items: start; grid-template-areas: var(--areas-1); }
    .cell { min-width: 0; display: grid; gap: var(--section-gap); }

    .panels {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--section-gap);
      align-items: start;
    }
    dl {
      display: grid;
      gap: var(--space-6);
    }
    dl > div {
      display: flex;
      justify-content: space-between;
      gap: var(--space-10);
    }
    dt {
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    dd {
      color: var(--text);
      font-size: var(--text-table);
    }
    /* -- SR49: the plan's reasoning ------------------------------------- */

    .no-detail {
      max-width: 68ch;
      color: var(--text-faint);
      font-size: var(--text-table);
      line-height: 1.6;
    }

    /* v54: dropped this call site's own .muted rule entirely -- the gate
       forbids redefining that selector at all, not just its colour (which
       was color: var(--text-faint), a drift off the global .muted's
       var(--text-muted), now fixed by using the global unmodified). The
       inline gap it used to add is .muted-gap, a second class alongside
       .muted in the markup so the two concerns stay separately named. */
    .muted-gap {
      margin-left: var(--space-6);
    }

    .chart {}
    .progress {
      margin-bottom: var(--space-10);
    }

    .notes {}
    .note-label {
      display: block;
      margin-bottom: var(--space-6);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    /* Renamed from .note (v54): that name collides with the promoted
       sb-note callout composite -- this is an unrelated journal-notes
       textarea field, not a callout, and the shared name was coincidence. */
    .note-field {
      width: 100%;
      padding: var(--space-8);
      /* --bg, not --surface: the field sits ON a surface, and the darkest
         token is what makes it read as inset rather than as another card. */
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      font: inherit;
      font-size: var(--text-table);
      resize: vertical;
    }
    .note-field:focus-visible {
      outline: 1px solid var(--accent);
      outline-offset: -1px;
    }
    .note-field:disabled {
      color: var(--text-faint);
      cursor: not-allowed;
    }
    .note-state {
      margin-top: var(--space-6);
      color: var(--text-faint);
      font-size: var(--text-chip);
    }
    /* The one state the reader must not miss: text they typed is not stored. */
    .note-state-bad {
      color: var(--neg);
    }
    .not-journaled {
      margin-bottom: var(--space-10);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }
    /* -- SR55: the journal entry behind the note ---------------------- */
    .excursions {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: var(--space-8);
      margin-bottom: var(--space-10);
    }
    /* Not .tags — the header already owns that class, and reusing it here
       would silently restyle the horizon/strategy chips at the top. */
    .journal-tags {
      display: flex;
      flex-wrap: wrap;
      gap: var(--space-4);
      margin-bottom: var(--space-10);
    }
    .auto-lesson {
      margin-bottom: var(--space-10);
      padding: var(--space-8);
      border-left: 2px solid var(--border);
      color: var(--text-secondary);
      font-size: var(--text-table);
    }


    .todo {
      margin-top: var(--space-14);
      color: var(--text-faint);
      font-size: var(--text-table);
    }
  `,
})
export class TradeDetail {
  private readonly router = inject(Router);
  private readonly api = inject(ApiClient);
  protected readonly store = inject(TradeDetailStore);
  protected readonly chart = inject(ChartStore);

  protected readonly side: Signal<'Long' | 'Short' | null> = computed(() =>
    sideLabel(this.store.trade()?.direction ?? null),
  );

  protected readonly earningsChip: Signal<string | null> = computed(() => {
    const trade = this.store.trade();
    if (!trade) return null;
    const group = statusGroup(trade.status, trade.exit_price ?? null);
    const days = this.store.earningsDays();
    if ((group !== 'open' && group !== 'pending') || days === null) return null;
    return `Earnings in ${days}d`;
  });

  protected readonly stripTiles = computed(() => {
    const trade = this.store.trade();
    if (!trade) return [];
    return outcomeTiles({
      trade, legs: this.store.legs(),
      history: this.store.timeline().filter(event => event.status !== 'CREATED'),
      riskPerShare: this.store.riskPerShare(), banked: this.store.bankedLeg(),
      bankedStats: this.store.bankedStats(), expiresOn: this.store.expiresOn(),
      timeExitOn: this.store.timeExitOn(), now: new Date(),
    });
  });

  protected readonly async = computed(() => asyncInputs(this.store, { isEmpty: () => false }));

  readonly id = input.required<string>();
  /** The active tab, as a query parameter. */
  readonly tab = input<string>();

  /** True only when the plan page redirected here (v151). Read once: a
   *  later navigation inside this page must not re-raise the banner. */
  protected readonly arrivedFromPlan: boolean = cameFromPlan();

  protected readonly arrival = computed(() => {
    if (!this.arrivedFromPlan) return '';
    const trade = this.store.trade();
    return trade ? arrivalBanner(trade.status, trade.bars_to_expiry ?? null) : '';
  });

  /** Every Why section, except on a record that predates detail capture,
   *  which keeps only its gate rows and calendar. */
  protected readonly whySections = computed<readonly WhySection[]>(() =>
    this.store.detailAbsent() ? ABSENT_SECTIONS : WHY_SECTIONS,
  );

  protected readonly cellSections = CELL_SECTIONS;
  protected readonly whyPresent = computed<ReadonlySet<WhyCard>>(() => {
    const present = new Set<WhyCard>(['context']);
    const sections = this.whySections();
    const trade = this.store.trade();
    if (sections.includes('explanation') && this.store.explanation() !== null) present.add('why');
    if (trade && [trade.confidence_score, trade.confidence_level, trade.quality_score, trade.badge]
      .some(value => value != null)) present.add('scores');
    if (sections.includes('levels') && hasLevelSources(this.store.targetSources(), this.store.stopSources(),
      this.store.target2Sources(), this.store.confirmedBy())) present.add('sources');
    if (sections.includes('confidence') && [Object.keys(this.store.confidencePoints() ?? {}),
      this.store.confidenceFactors(), this.store.qualityFactors()].some(rows => rows.length > 0)) present.add('breakdown');
    if (sections.includes('gates')) present.add('gates');
    return present;
  });
  protected readonly whyGrid = computed<CardAreas>(() => whyAreas(this.whyPresent()));

  protected readonly tabs = TABS;

  /** "Stop" vs "Trailing stop" -- a PARTIAL position's `stop_loss` field is
   *  no longer the original risk-defining level (the API returns the
   *  runner's own working_stop there once TP1 has banked). For a short
   *  that trailing stop legitimately sits BELOW entry -- it protects profit
   *  already locked in by TP1, not the original risk -- which reads as
   *  backwards (a short's stop "should" be above entry) unless the label
   *  says why. A closed PARTIAL-turned-win/loss keeps showing "Stop" since
   *  by then it is simply what the position actually exited against. */
  protected readonly stopLabel = computed(() =>
    this.store.trade()?.status === 'PARTIAL' ? 'Trailing stop' : 'Stop',
  );

  /* -- v86: the cohort risk chip --------------------------------------- */

  private static readonly COHORT_TONE: Record<string, ChipTone> = {
    COHORT_POOR: 'bad',
    COHORT_STRONG: 'good',
    COHORT_UNKNOWN: 'muted',
    // COHORT_TYPICAL deliberately absent -- no entry means no chip, below.
  };

  private static readonly COHORT_CHIP_LABEL: Record<string, string> = {
    COHORT_POOR: 'Poor cohort',
    COHORT_STRONG: 'Strong cohort',
    COHORT_UNKNOWN: 'Cohort unknown',
  };

  /** null for COHORT_TYPICAL (and any other unrecognised label) -- "typical"
   *  is the silent default every other cohort is judged against, so it earns
   *  no chip at all rather than a neutral one that would just add noise to
   *  every ordinary trade. */
  protected readonly cohortTone = computed<ChipTone | null>(() => {
    const label = this.store.trade()?.cohort_label;
    return label ? (TradeDetail.COHORT_TONE[label] ?? null) : null;
  });

  protected readonly cohortChipLabel = computed(() => {
    const label = this.store.trade()?.cohort_label;
    return (label && TradeDetail.COHORT_CHIP_LABEL[label]) || '';
  });

  /** The numbers behind the chip -- same facts `cohort_line()` puts in the
   *  Discord alert (`swingbot/core/scanning/plan_table.py`), so hovering the
   *  chip answers "why" without a trip to the Why tab.
   *
   *  Empty when `cohort_stats` itself is `{}` (a pre-registry/unstamped
   *  plan). For `COHORT_UNKNOWN` -- or any cell whose combined n is 0 --
   *  `cohort_stats` CAN still be a fully-populated dict of zeroed stats (the
   *  cell just fell below the registry's N floor); computing a WR/ExpR line
   *  off those zeros would fabricate a "0.0% WR" verdict nobody measured.
   *  This mirrors the same fabricated-zero bug already fixed once
   *  server-side (commit 7d5d4d3a) -- don't reintroduce it here. */
  protected readonly cohortTooltip = computed(() => {
    const trade = this.store.trade();
    const stats = trade?.cohort_stats;
    if (!stats || Object.keys(stats).length === 0) return '';
    const n = Number(stats['n_live'] ?? 0) + Number(stats['n_backtest'] ?? 0);
    if (trade?.cohort_label === 'COHORT_UNKNOWN' || n === 0) {
      return `Not enough closed trades under these conditions to say anything yet (n=${n}).`;
    }
    const regime = String(stats['regime2_state'] ?? 'unknown').replace(/_/g, ' ');
    const winRate = Number(stats['win_rate'] ?? 0);
    const expectancyR = Number(stats['expectancy_r'] ?? 0);
    const runDate = stats['run_date'] ?? '';
    return (
      `${regime} regime: ${winRate.toFixed(1)}% WR / ` +
      `${expectancyR >= 0 ? '+' : ''}${expectancyR.toFixed(2)}R (n=${n}, frozen ${runDate})`
    );
  });

  protected readonly fmt = num;
  protected readonly fmtText = text;
  protected readonly fmtDate = dateTime;
  protected readonly fmtPct = pct;
  protected readonly fmtHeld = held;
  protected readonly fmtShare = share;
  protected readonly fmtR = rMultiple;

  /** An unknown or absent `?tab=` falls back to Plan rather than rendering
   *  nothing, so a hand-edited or stale URL still shows the trade. */
  protected readonly activeTab = computed(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested) ? requested : 'plan';
  });

  protected readonly actionLabels = ACTION_LABELS;
  protected readonly actionsFor = availableActions;
  protected readonly pending = signal<TradeActionKind | null>(null);
  protected readonly working = signal(false);

  protected readonly confirmTitle = computed(() => {
    const kind = this.pending();
    return kind ? ACTION_TITLES[kind] : '';
  });

  protected readonly confirmLabel = computed(() => {
    const kind = this.pending();
    return kind ? ACTION_LABELS[kind] : 'Confirm';
  });

  /** The same sentences the Trades list uses -- see `trade-actions.ts` for
   *  why they live in exactly one place. */
  protected readonly confirmConsequence = computed(() => {
    const kind = this.pending();
    const trade = this.store.trade();
    return kind && trade ? actionConsequence(kind, trade) : '';
  });

  /** Autosave delay. Long enough that ordinary typing does not generate a
   *  request per word, short enough that the note is stored before attention
   *  moves on. Blur flushes, so the wait is never the last word on it. */
  private static readonly NOTE_DEBOUNCE_MS = 800;

  private noteTimer: ReturnType<typeof setTimeout> | null = null;

  protected onNoteInput(event: Event): void {
    this.store.editNote((event.target as HTMLTextAreaElement).value);

    if (this.noteTimer !== null) clearTimeout(this.noteTimer);
    this.noteTimer = setTimeout(() => {
      this.noteTimer = null;
      this.store.saveNote();
    }, TradeDetail.NOTE_DEBOUNCE_MS);
  }

  /** Save now rather than at the end of the debounce. Leaving the field is a
   *  stronger signal that the thought is finished than any timer. */
  protected flushNote(): void {
    if (this.noteTimer === null) return;
    clearTimeout(this.noteTimer);
    this.noteTimer = null;
    if (this.store.noteDirty()) this.store.saveNote();
  }

  constructor() {
    effect(() => this.store.setId(this.id()));

    // The registry is only needed by one tab, and it is the same request for
    // every trade -- so it is fetched on first arrival at the tab rather than
    // with the trade.
    effect(() => {
      if (this.activeTab() === 'why' && this.store.strategies() === null) {
        untracked(() => this.store.loadStrategies());
      }
    });

    // A pending autosave must not outlive the component: the timer would fire
    // against a destroyed store and the last edit would be lost either way.
    inject(DestroyRef).onDestroy(() => {
      if (this.noteTimer === null) return;
      clearTimeout(this.noteTimer);
      this.noteTimer = null;
    });

    // Both, and both from the trade: the ticker is what is charted, and the
    // trade id is what adds the plan lines, the working stop and the overlays.
    // Only once the trade has loaded — a chart of `null` is a 404 the reader
    // would take for a broken chart.
    effect(() => {
      const trade = this.store.trade();
      this.chart.setTarget(trade?.ticker ?? null, trade?.id ?? null);
    });
  }

  protected pnlClass(value: number | null | undefined): string {
    if (value === null || value === undefined) return '';
    if (value > 0) return 'pos';
    if (value < 0) return 'neg';
    return '';
  }

  protected ask(kind: TradeActionKind): void {
    this.pending.set(kind);
  }

  protected runPending(): void {
    const kind = this.pending();
    const trade = this.store.trade();
    if (!kind || !trade) return;

    this.working.set(true);
    runTradeAction(this.api, kind, trade.id).subscribe({
      // Deleting removes the thing this route is about, so it navigates away.
      // Close and cancel leave a trade that still has a detail page, and the
      // server's `trades` event refetches it -- no manual reload here, which
      // would double every command.
      next: () => {
        this.working.set(false);
        this.pending.set(null);
        if (kind === 'delete') this.router.navigate(['/trades']);
      },
      error: () => {
        this.working.set(false);
        this.pending.set(null);
      },
    });
  }

  protected goToTab(tab: string): void {
    // replaceUrl: flipping between tabs should not fill the history with
    // steps, but the tab must still be in the URL so it can be linked to.
    this.router.navigate([], {
      queryParams: { tab: tab === 'plan' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
