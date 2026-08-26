import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
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
import { Chip, QualityChip } from '../../ui/chip';
import { MetricChip } from '../../ui/metric-chip';
import { ChartContainer } from '../../ui/chart-container';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { TradeChart } from '../../ui/chart/trade-chart';
import { dateTime, held, num, pct, rMultiple, share, text } from '../../ui/format';
import { ControlRow, Panel, Tab, TabBar } from '../../ui/layout';
import { StatusIndicator } from '../../ui/status-indicator';
import {
  ACTION_LABELS,
  ACTION_TITLES,
  TradeActionKind,
  actionConsequence,
  availableActions,
  runTradeAction,
} from './trade-actions';

/** Plan · Live · Chart · Notes · Strategy — spec 3's five, in its order. */
const TABS: Tab[] = [
  { id: 'plan', label: 'Plan' },
  { id: 'live', label: 'Live' },
  { id: 'chart', label: 'Chart' },
  { id: 'notes', label: 'Notes' },
  { id: 'strategy', label: 'Strategy' },
];

const TAB_IDS = new Set(TABS.map((tab) => tab.id));

/**
 * One trade — the shell and the Plan tab (NG43). Live is NG44, Chart NG45,
 * Notes and Strategy NG46.
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
  providers: [TradeDetailStore, ChartStore],
  imports: [
    RouterLink,
    TabBar,
    Panel,
    ControlRow,
    StatusIndicator,
    QualityChip,
    Button,
    ConfirmDialog,
    ChartContainer,
    TradeChart,
    MetricChip,
    Chip,
    Async,
  ],
  template: `
    <header class="head">
      <a class="back" routerLink="/trades">← Trades</a>

      @if (store.trade(); as trade) {
        <h1>
          <span class="ticker">{{ trade.ticker }}</span>
          <sb-status-indicator
            [status]="trade.status"
            [current]="trade.current_price"
            [entry]="trade.entry"
            [stop]="trade.stop_loss"
            [target]="trade.target"
          />
        </h1>
        <div class="tags">
          <!-- The id a Discord command (!trade ID) or the API needs to name
               this exact trade -- previously only visible in the Trades
               list's # column (and truncated there, see shortId()), so
               reaching this page by clicking a row lost the one thing
               someone might come here to copy. -->
          <span class="trade-id" [title]="'Trade ID: ' + trade.id">{{ trade.id }}</span>
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
        </div>
      } @else if (store.error(); as message) {
        <h1>{{ message }}</h1>
      } @else {
        <!-- Not "skeleton": G1's coverage gate (async-coverage.spec.ts)
             bans that literal class name anywhere in a file that uses
             sb-async, once one is added below for the tab content. This
             title-only loading word is not the sb-async skeleton itself. -->
        <h1 class="loading-title">Loading…</h1>
      }
    </header>

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
            <sb-panel heading="Levels">
              <dl>
                <div>
                  <dt>Entry</dt>
                  <dd class="num">{{ fmt(trade.entry) }}</dd>
                </div>
                <div>
                  <dt>{{ stopLabel() }}</dt>
                  <dd class="num neg">{{ fmt(trade.stop_loss) }}</dd>
                </div>
                <div>
                  <dt>Target 1</dt>
                  <dd class="num pos">{{ fmt(trade.target) }}</dd>
                </div>
                <div>
                  <dt>Target 2</dt>
                  <dd class="num pos">{{ fmt(trade.target2) }}</dd>
                </div>
                <div>
                  <dt>R:R</dt>
                  <dd class="num">{{ fmt(trade.risk_reward) }}</dd>
                </div>
                <!-- The trigger is the only actionable price on a PENDING
                     plan: the entry price stays null until it fills. Shown only when
                     there is one, so a filled position does not carry a row
                     about a threshold it crossed days ago. -->
                @if (store.triggerPrice() !== null) {
                  <div>
                    <dt>Trigger</dt>
                    <dd class="num">{{ fmt(store.triggerPrice()) }}</dd>
                  </div>
                }
                @if (store.tp1Pct() !== null) {
                  <div>
                    <dt>TP1 closes</dt>
                    <dd class="num">{{ fmtShare(store.tp1Pct()) }}</dd>
                  </div>
                }
                @if (store.breakevenTriggerPct() !== null) {
                  <div>
                    <dt>Break-even at</dt>
                    <dd class="num">{{ fmtShare(store.breakevenTriggerPct()) }} of TP1</dd>
                  </div>
                }
              </dl>

              <!-- What put each level where it is. Separate lists rather than
                   the Jinja tooltip's merged one: there is room here to say
                   which level a source justifies, which the tooltip could not. -->
              @if (store.targetSources().length || store.stopSources().length) {
                <div class="sources">
                  @if (store.targetSources().length) {
                    <p><span class="src-label">Target confirmed by</span>
                      {{ store.targetSources().join(', ') }}</p>
                  }
                  @if (store.stopSources().length) {
                    <p><span class="src-label">Stop confirmed by</span>
                      {{ store.stopSources().join(', ') }}</p>
                  }
                  @if (store.target2Sources().length) {
                    <p><span class="src-label">Target 2 confirmed by</span>
                      {{ store.target2Sources().join(', ') }}</p>
                  }
                </div>
              }
            </sb-panel>

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

            <!-- SR60. trade_detail.html:96-104. Derived from target2 and
                 stop_loss, both of which the Levels panel already shows --
                 what was missing was the sentence saying what they MEAN if
                 price actually gets to TP1. -->
            <sb-panel [heading]="ifItGetsThereHeading()">
              <dl>
                <div>
                  <dt>Continues past {{ levelWord() }} 1</dt>
                  <dd class="num">
                    @if (trade.target2 !== null) {
                      next stop {{ fmt(trade.target2) }}
                    } @else {
                      <span class="absent">no further level found</span>
                    }
                  </dd>
                </div>
                <div>
                  <dt>Reverses at {{ levelWord() }} 1</dt>
                  <dd class="num">
                    pulls back toward {{ oppositeWord() }} at {{ fmt(trade.stop_loss) }}
                  </dd>
                </div>
              </dl>
            </sb-panel>

            <sb-panel heading="Sizing">
              <!-- SR60. _trade_history_rows.html:67. The number was already
                   here as a picker-addable column; what was missing is that a
                   trade logged before sizing snapshots existed shows an
                   estimate, not a recorded figure. -->
              <p class="section-help">
                Position size is snapshotted when the trade opens. A trade with
                no sizing snapshot was logged before that feature existed.
              </p>
              <dl>
                <div>
                  <dt>Shares</dt>
                  <dd class="num">{{ fmt(trade.shares, 0) }}</dd>
                </div>
                <div>
                  <dt>Deployed</dt>
                  <dd class="num">{{ fmt(trade.position_value) }}</dd>
                </div>
                <div>
                  <dt>Sizing mode</dt>
                  <dd>{{ fmtText(store.detail()?.sizing_mode ?? null) }}</dd>
                </div>
                <div>
                  <dt>Working stop</dt>
                  <dd class="num">{{ fmt(store.detail()?.working_stop ?? null) }}</dd>
                </div>
              </dl>
            </sb-panel>

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

          <!-- The reasoning. Everything above is a number; this is the only
               part of the screen that says why any of them were chosen. -->
          @if (store.detailAbsent()) {
            <!-- Not an error and not an empty panel per field: this record
                 predates the detail capture entirely, and nine em dashes read
                 as a failed load rather than as a fact about an old trade. -->
            <p class="no-detail">
              This trade was logged before the admin UI captured the full alert
              detail — only the plan above is available for it.
            </p>
          } @else {
            @if (store.explanation(); as why) {
              <sb-panel heading="Why this trade">
                <p class="prose">{{ why }}</p>
              </sb-panel>
            }

            @if (store.confirmedBy().length) {
              <sb-panel heading="Confirmed by">
                <ul class="confirmations">
                  @for (c of store.confirmedBy(); track c.strategy + (c.horizon ?? '')) {
                    <li>
                      {{ c.strategy }}
                      @if (c.horizon) {
                        <span class="muted muted-gap">({{ c.horizon }})</span>
                      }
                    </li>
                  }
                </ul>
              </sb-panel>
            }

            @if (store.confidenceFactors().length) {
              <sb-panel heading="Confidence breakdown">
                <dl class="factors">
                  @for (f of store.confidenceFactors(); track f.factor) {
                    <div><dt>{{ f.factor }}</dt><dd>{{ f.note }}</dd></div>
                  }
                </dl>
              </sb-panel>
            }

            @if (store.qualityFactors().length) {
              <sb-panel heading="Quality breakdown">
                <dl class="factors">
                  @for (f of store.qualityFactors(); track f.label) {
                    <div>
                      <dt>{{ f.label }}</dt>
                      <dd class="num">{{ signed(f.points) }}</dd>
                    </div>
                  }
                </dl>
              </sb-panel>
            }
          }
        }
      }
      @case ('live') {
        @if (store.trade(); as trade) {
          <div class="panels">
            <sb-panel heading="Now">
              <dl>
                <div>
                  <dt>Price</dt>
                  <dd class="num">{{ fmt(trade.current_price) }}</dd>
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

            <sb-panel heading="Actions">
              <sb-control-row class="commands">
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
              </sb-control-row>
            </sb-panel>
          </div>

          <!-- Scale-out legs. A position that took TP1 and is riding a runner
               is TWO results, and a single P&L figure describes neither. -->
          @if (store.legs().length > 1) {
            <sb-panel heading="Scale-out">
              <dl class="factors">
                @for (leg of store.legs(); track $index) {
                  <div>
                    <dt>
                      @if ($index === 0) { First } @else { Runner }
                      @if (leg.fraction !== null) {
                        <span class="muted muted-gap">{{ fmtShare(leg.fraction * 100) }}</span>
                      }
                    </dt>
                    <dd class="num">
                      @if (leg.exitPrice !== null) {
                        {{ fmt(leg.exitPrice) }}
                        @if (leg.r !== null) {
                          <span [class]="pnlClass(leg.r)">{{ fmtR(leg.r) }}</span>
                        }
                        @if (leg.reason) {
                          <span class="muted muted-gap">{{ leg.reason }}</span>
                        }
                      } @else {
                        <span class="muted muted-gap">still open</span>
                      }
                    </dd>
                  </div>
                }
              </dl>
            </sb-panel>
          }

          <!-- The plan's audit trail. Every transition carries the reason it
               happened, which is the only place "why did this cancel" is
               answered. -->
          @if (store.timeline().length) {
            <sb-panel heading="Timeline">
              <ol class="timeline">
                @for (event of store.timeline(); track $index) {
                  <li>
                    <span class="tl-status">{{ event.status }}</span>
                    @if (event.reason) {
                      <span class="tl-reason">{{ event.reason }}</span>
                    }
                    @if (event.at) {
                      <span class="tl-at">{{ fmtDate(event.at) }}</span>
                    }
                  </li>
                }
              </ol>
            </sb-panel>
          }
        }
      }
      @case ('chart') {
        <div class="chart">
          <sb-chart-container
            [loading]="chart.loading()"
            [error]="chart.error()"
            [hasData]="!chartEmpty()"
            [height]="520"
            [caption]="chartCaption()"
            [canRetry]="true"
            (retry)="chart.retry()"
          >
            <sb-trade-chart [data]="chart.data()" />
          </sb-chart-container>
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
      @case ('strategy') {
        <div class="strategy">
          @if (store.strategiesError()) {
            <p class="not-journaled">{{ store.strategiesError() }}</p>
          } @else if (!store.trade()?.strategy) {
            <p class="not-journaled">This position has no strategy recorded.</p>
          } @else if (store.strategyRow(); as row) {
            <!-- Read-only on purpose: this is a window into the registry, and
                 the place to change a strategy's numbers is a validation run,
                 not a trade. -->
            <dl>
              <div>
                <dt>Strategy</dt>
                <dd>{{ row.strategy }}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{{ row.status }}</dd>
              </div>
              <div>
                <dt>OOS sample</dt>
                <dd>{{ fmt(row.n) }}</dd>
              </div>
              <div>
                <dt>OOS win rate</dt>
                <dd>{{ fmtPct(row.win_rate) }}</dd>
              </div>
              <div>
                <dt>OOS expectancy</dt>
                <dd>{{ fmt(row.expectancy_r) }}R</dd>
              </div>
              <div>
                <dt>Live sample</dt>
                <dd>{{ fmt(row.live_n) }}</dd>
              </div>
              <div>
                <dt>Live win rate</dt>
                <dd>{{ fmtPct(row.live_wr) }}</dd>
              </div>
              <div>
                <dt>Live vs OOS</dt>
                <dd>{{ fmtPct(row.delta_vs_oos) }}</dd>
              </div>
              <div>
                <dt>Window</dt>
                <dd>{{ fmtText(row.window) }}</dd>
              </div>
            </dl>
            @if (row.decayed) {
              <!-- The pre-registered decay rule fired. This belongs on the
                   trade, not only on the Analytics page: it is the reason to
                   distrust this position's edge. -->
              <p class="decayed">
                Live results have decayed against this strategy's out-of-sample record.
              </p>
            }
          } @else {
            <p class="not-journaled">
              The registry has no entry for {{ fmtText(store.trade()?.strategy) }}.
            </p>
          }
        </div>
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

    h1 {
      display: flex;
      align-items: center;
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

    .panels {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: var(--space-14);
      margin-top: var(--space-14);
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

    /* Prose, not data. Wider measure than a table cell and a real line
       height, because this is the one part of the screen meant to be read
       rather than scanned. */
    .prose {
      max-width: 68ch;
      color: var(--text);
      font-size: var(--text-table);
      line-height: 1.6;
    }
    .no-detail {
      margin-top: var(--space-14);
      max-width: 68ch;
      color: var(--text-faint);
      font-size: var(--text-table);
      line-height: 1.6;
    }

    .sources {
      margin-top: var(--space-10);
      padding-top: var(--space-10);
      border-top: 1px solid var(--border);
    }
    .sources p {
      color: var(--text);
      font-size: var(--text-chip);
      line-height: 1.5;
    }
    .src-label {
      display: block;
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }

    .confirmations {
      display: grid;
      gap: var(--space-6);
      list-style: none;
    }
    .confirmations li {
      color: var(--text);
      font-size: var(--text-table);
    }

    /* The two breakdowns and the scale-out legs share a shape: a label and a
       value that is usually a sentence, so the value is allowed to wrap where
       the plain definition list above keeps everything on one line. */
    .factors > div {
      align-items: baseline;
      gap: var(--space-14);
    }
    .factors dd {
      text-align: right;
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

    /* A rule down the left with a node per event: the shape says "these
       happened in order", which a plain list does not. */
    .timeline {
      display: grid;
      gap: var(--space-8);
      margin-left: var(--space-6);
      padding-left: var(--space-14);
      border-left: 1px solid var(--border-strong);
      list-style: none;
    }
    .timeline li {
      position: relative;
      font-size: var(--text-table);
    }
    .timeline li::before {
      content: '';
      position: absolute;
      left: calc(-1 * var(--space-14) - 3px);
      top: 0.45em;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: var(--border-strong);
    }
    .tl-status {
      color: var(--text);
      font-weight: 600;
    }
    .tl-reason {
      margin-left: var(--space-6);
      color: var(--text-secondary);
    }
    .tl-at {
      margin-left: var(--space-6);
      color: var(--text-faint);
      font-size: var(--text-chip);
    }

    .chart {
      margin-top: var(--space-14);
    }
    .progress {
      margin-bottom: var(--space-10);
    }
    /* .commands keeps its class as a marker only -- sb-control-row supplies
       display, alignment, wrap and gap. */

    .notes,
    .strategy {
      margin-top: var(--space-14);
    }
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
    .decayed {
      margin-top: var(--space-10);
      color: var(--warn);
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

  protected readonly async = computed(() => asyncInputs(this.store, { isEmpty: () => false }));

  readonly id = input.required<string>();
  /** The active tab, as a query parameter. */
  readonly tab = input<string>();

  protected readonly tabs = TABS;

  /* -- SR60: the "if it gets there" wording ---------------------------- */

  /** `admin/app.py:691` -- Resistance for a long, Support for a short. The
   *  words matter: "next stop 210" reads differently above and below price. */
  protected readonly levelWord = computed(() =>
    this.store.trade()?.direction === 'bearish' ? 'support' : 'resistance',
  );

  protected readonly oppositeWord = computed(() =>
    this.store.trade()?.direction === 'bearish' ? 'resistance' : 'support',
  );

  protected readonly ifItGetsThereHeading = computed(() => 'If it gets there');

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

  protected readonly chartCaption = computed(() => {
    const trade = this.store.trade();
    if (!trade) return null;
    // The confirming methods, when the trade has any. An empty list is an
    // ordinary state — an older trade with no recorded sources — so the
    // caption simply says less rather than announcing an absence. Both sides
    // are named when both are drawn: they are different methods, and the
    // legend below is the only other place that says which.
    const source = (this.chart.data()?.overlays ?? [])
      .map((overlay) => overlay.source)
      .join(' · ');
    const base = `${trade.ticker} — daily, with this plan's levels`;
    return source ? `${base} · ${source}` : base;
  });

  /** No bars is distinct from an error and from still loading: the request
   *  succeeded and the window is empty. */
  protected readonly chartEmpty = this.chart.isEmpty;

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
      if (this.activeTab() === 'strategy' && this.store.strategies() === null) {
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

  /** Quality-score points, signed. These are contributions to a total, and a
   *  factor that cost the plan points is as informative as one that earned
   *  them — an unsigned "5" beside "Badge" would read as a credit either way. */
  protected signed(points: number): string {
    return `${points > 0 ? '+' : ''}${points}`;
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
