import {
  ChangeDetectionStrategy,
  Component,
  TemplateRef,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';

import {
  ANALYTICS_TABS,
  AnalyticsStore,
  AnalyticsTab,
  BREAKDOWN_DIMENSIONS,
  BreakdownDimension,
  BreakdownRow,
  DriftRow,
  GridRow,
  HeatmapCell,
  JobStatus,
  JobSummary,
  ProposalRow,
  Streaks,
  StrategyRow,
  TierRow,
} from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { Button } from '../../ui/button';
import { Chip, QualityChip, qualityTone } from '../../ui/chip';
import { ChipRow } from '../../ui/chip-row';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { createClientPage } from '../../ui/data-table/client-page';
import { Select, TextInput } from '../../ui/form-controls';
import { ABSENT, date, dateTime } from '../../ui/format';
import { ControlRow, Panel, Tab, TabBar } from '../../ui/layout';
import { SectionHead } from '../../ui/section-head';
import { Histogram, HistogramBin } from '../../ui/histogram';
import { LineChart, LineChartSeries } from '../../ui/line-chart';
import { MetricChip } from '../../ui/metric-chip';
import { PaginationComponent } from '../../ui/pagination';
import { Sparkline } from '../../ui/sparkline';
import {
  CONFIDENCE_COLUMNS,
  breakdownColumns,
  DECILE_COLUMNS,
  DRIFT_COLUMNS,
  GRID_COLUMNS,
  PAST_JOBS_COLUMNS,
  STRATEGY_COLUMNS,
  TIER_COLUMNS,
  allKeys,
  expectancy,
  rate,
} from './analytics.columns';

/** Performance · Strategies · Calibration · Tuning · Plans — spec v14
 *  Decision 6, in its order. **Tabs, not sub-navigation**: five sections is
 *  within what a tab strip carries comfortably, and a second level of
 *  navigation inside one of six workspaces reintroduces exactly the depth
 *  the IA change removed. */
const TABS: Tab[] = [
  { id: 'performance', label: 'Performance' },
  { id: 'strategies', label: 'Strategies' },
  { id: 'calibration', label: 'Calibration' },
  { id: 'tuning', label: 'Tuning' },
  { id: 'plans', label: 'Plans' },
];

const TAB_IDS = new Set<string>(ANALYTICS_TABS);

/** A proposal with its parameter diff already paired up for rendering. */
interface ProposalView extends ProposalRow {
  params: { key: string; current: string; proposed: string }[];
  trainSummary: string;
}

/**
 * Analytics — the workspace that absorbs the old Performance, Strategies,
 * Calibration and Tuning pages (spec v14 Decision 6).
 *
 * Three things here are load-bearing and easy to lose in a later edit:
 *
 * **The six relocated Dashboard metrics are on the Performance tab.** Spec 3
 * accepted the cost of moving wins, losses, average realised P&L, best trade,
 * worst trade and average holding period one click away from the header —
 * *not* the cost of losing them. They are rendered from
 * `RELOCATED_METRICS`, and the store reports any the payload failed to carry
 * so the loss would be visible rather than silent.
 *
 * **The active tab is a query parameter.** Same reason the Trades list keeps
 * its filters there: a tab held only in component state cannot be linked to,
 * does not survive a reload, and makes the back button skip the entire
 * workspace instead of stepping back through it.
 *
 * **Tuning has no timer.** The Jinja page polled `/api/jobs/:id` every three
 * seconds and called `window.location.reload()` when the job finished. Here
 * the `jobs` event drives the refetch and the log tail updates in place —
 * which also means a failed grid's traceback stays on screen instead of being
 * reloaded away at the moment it becomes worth reading.
 */
@Component({
  selector: 'sb-analytics',
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Provided here rather than in root, matching Dashboard and Trades: the store
  // is created on entry and destroyed on exit, so this workspace never holds
  // stale analytics while you are looking at another one.
  providers: [AnalyticsStore],
  imports: [
    TabBar,
    Panel,
    ControlRow,
    DataTable,
    MetricChip,
    Histogram,
    LineChart,
    Chip,
    ChipRow,
    QualityChip,
    Sparkline,
    Select,
    TextInput,
    Button,
    ConfirmDialog,
    PaginationComponent,
    SectionHead,
  ],
  template: `
    <sb-section-head heading="Analytics">
      @if (store.error(); as message) {
        <!-- Beside the data, never instead of it: one failed refetch should
             not empty a table that is still the best information available. -->
        <span actions class="stale" role="status">{{ message }}</span>
      }
    </sb-section-head>

    <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

    @switch (activeTab()) {
      <!-- -- performance ---------------------------------------------- -->
      @case ('performance') {
        @if (store.missingRelocated(); as missing) {
          @if (missing.length) {
            <!-- The relocation's own alarm. These six moved off the Dashboard
                 header on the promise that they would appear here; a missing
                 one otherwise looks exactly like a metric with no value yet. -->
            <p class="alert" role="alert">
              Not returned by the API: {{ missing.join(', ') }}. These metrics
              moved here from the Dashboard and should be present.
            </p>
          }
        }

        <h2 class="section">Snapshot</h2>
        <div class="panels">
          <sb-panel heading="Record">
            <sb-chip-row class="chips">
              @for (metric of store.relocated(); track metric.key) {
                <sb-metric-chip
                  [label]="metric.label"
                  [value]="metric.value"
                  [unit]="metric.unit"
                  [decimals]="metric.decimals"
                  [tone]="metric.pnl ? 'pnl' : 'plain'"
                />
              }
            </sb-chip-row>
          </sb-panel>

          <sb-panel heading="Overall">
            <dl>
              <div><dt>Win rate</dt><dd class="num">{{ fmtRate(store.winRate()) }}</dd></div>
              <div>
                <dt>Expectancy</dt>
                <dd class="num">{{ fmtExpectancy(store.expectancyR()) }}</dd>
              </div>
              <div><dt>Trades</dt><dd class="num">{{ fmtCount(store.totals().total) }}</dd></div>
              <div><dt>Open</dt><dd class="num">{{ fmtCount(store.totals().open) }}</dd></div>
              <div><dt>Closed</dt><dd class="num">{{ fmtCount(store.totals().closed) }}</dd></div>
            </dl>
          </sb-panel>
        </div>

        <!-- SR50. Everything below comes from GET /analytics/snapshot, which
             the server has been building and serving all along. -->
        @if (store.snapshotError(); as message) {
          <!-- Its own line, not the tab-wide error: the panels above came from
               a different endpoint and are not implicated. -->
          <p class="stale" role="status">Snapshot unavailable — {{ message }}</p>
        }

        <div class="panels">
          <sb-panel heading="Risk-adjusted">
            <sb-chip-row class="chips">
              <sb-metric-chip label="Profit factor" [value]="store.profitFactor()" />
              <sb-metric-chip label="Sharpe" [value]="store.sharpe()" />
              <sb-metric-chip label="Sortino" [value]="store.sortino()" />
              <!-- Max drawdown is always a loss, and always reported positive
                   by the server. Amber, not red: it is the cost of the track
                   record, not a loss happening now. -->
              <sb-metric-chip
                label="Max drawdown"
                [value]="store.maxDrawdownPct()"
                unit="%"
                [decimals]="1"
                tone="caution"
              />
              <sb-metric-chip
                label="Total P&L"
                [value]="store.totalPnl()"
                tone="pnl"
                [unit]="currencyUnit()"
              />
            </sb-chip-row>
          </sb-panel>

          @if (store.streaks(); as streaks) {
            <sb-panel heading="Streaks">
              <dl>
                <div>
                  <dt>Current</dt>
                  <dd class="num">{{ currentStreak(streaks) }}</dd>
                </div>
                <div>
                  <dt>Best win run</dt>
                  <dd class="num">{{ fmtCount(streaks.bestWin) }}</dd>
                </div>
                <div>
                  <dt>Worst loss run</dt>
                  <dd class="num">{{ fmtCount(streaks.worstLoss) }}</dd>
                </div>
              </dl>
            </sb-panel>
          }
        </div>

        <h2 class="section">Distributions</h2>
        <!-- SR54. Everything below is scoped by the range control; the two
             panels above are deliberately all-time, so the heading says which
             is which rather than leaving the reader to guess. -->
        <sb-panel [heading]="derivedHeading()">
          <sb-control-row class="range" role="group" aria-label="Analytics date range">
            <sb-text-input
              type="date"
              label="From"
              [value]="store.rangeFrom() ?? ''"
              (valueChange)="onRangeFrom($event)"
            />
            <sb-text-input
              type="date"
              label="To"
              [value]="store.rangeTo() ?? ''"
              (valueChange)="onRangeTo($event)"
            />
            @if (store.rangeActive()) {
              <button sb-button type="button" variant="ghost"
                      (click)="store.clearRange()">
                Clear
              </button>
            }
            <!-- The sample size sits with the control, not the cards: a Calmar
                 over four trades and one over four hundred must not read as
                 equally authoritative. -->
            <span class="sample">{{ sampleLabel() }}</span>
          </sb-control-row>

          @if (store.rangeSampleSize() === 0) {
            <!-- Not an error. An empty window is a legitimate answer, and the
                 cards below would otherwise be twelve em dashes with no
                 explanation of why. -->
            <p class="stale" role="status">
              No closed trades in this window.
            </p>
          }

          <sb-chip-row class="chips">
            @for (metric of store.derivedMetrics(); track metric.key) {
              <sb-metric-chip
                [label]="metric.label"
                [value]="metric.value"
                [unit]="metric.unit"
                [decimals]="metric.decimals"
                [tone]="metric.pnl ? 'pnl' : 'plain'"
              />
            }
          </sb-chip-row>
        </sb-panel>

        <div class="panels">
          <sb-panel heading="Return distribution">
            @if (store.returnsHistogram().length) {
              <sb-histogram [bins]="store.returnsHistogram()" />
            } @else {
              <p class="stale">No closed trades to distribute.</p>
            }
          </sb-panel>

          <sb-panel heading="R-multiple distribution (selected range)">
            @if (store.rHistogram().length) {
              <sb-histogram [bins]="store.rHistogram()" />
            } @else {
              <p class="stale">No R-multiples — trades need an entry and a stop.</p>
            }
          </sb-panel>
        </div>

        @if (store.rMultipleBins().length) {
          <sb-panel heading="R-multiple distribution (all-time)">
            <!-- Bars, not a pie and not a line: this is a distribution, and
                 the shape IS the finding -- a healthy edge is a cluster of
                 small losses with a tail of larger wins. -->
            <sb-histogram [bins]="store.rMultipleBins()" />
          </sb-panel>
        }

        <div class="panels">
          <sb-panel heading="By holding period">
            <!-- Every band renders, including empty ones: "the edge is all in
                 8-30d" is only legible next to the bands that are empty. -->
            <dl>
              @for (band of store.holdingSplit(); track band.bucket) {
                <div>
                  <dt>{{ band.bucket }}</dt>
                  <dd class="num">
                    {{ fmtCount(band.n) }} · {{ fmtRate(band.win_rate) }}
                  </dd>
                </div>
              }
            </dl>
          </sb-panel>

          <sb-panel heading="By month">
            @if (store.monthHistogram().length) {
              <sb-histogram [bins]="store.monthHistogram()" />
            } @else {
              <p class="stale">No months with closed trades.</p>
            }
          </sb-panel>
        </div>

        <h2 class="section">Over time</h2>
        @if (store.equitySeries().length) {
          <div class="panels">
            <sb-panel heading="Account balance">
              <sb-line-chart [series]="store.balanceWithBenchmark()" [valueFormat]="fmtLineValue" />
              <p class="series-note">
                {{ store.equitySeries().length }} points ·
                {{ seriesRange(store.equitySeries()) }}
              </p>
            </sb-panel>

            <sb-panel heading="Drawdown">
              <sb-line-chart [series]="drawdownSeriesForChart()" [valueFormat]="fmtLineValue" />
              <p class="series-note">
                Peak-to-trough, as a share of the running high. Higher is worse.
              </p>
            </sb-panel>
          </div>
        }
        <div class="panels">
          <sb-panel heading="Rolling returns">
            <sb-line-chart [series]="store.rollingReturnsChart()" [valueFormat]="fmtLineValue" />
          </sb-panel>
          <sb-panel heading="Cumulative return by strategy">
            @if (store.cumulativeByStrategyChart().length) {
              <sb-line-chart [series]="store.cumulativeByStrategyChart()" [valueFormat]="fmtLineValue" />
            } @else {
              <p class="stale">No strategies with closed trades yet.</p>
            }
          </sb-panel>
        </div>

        <h2 class="section">By segment</h2>
        <!-- SR55. NOT a rebuilt Journal page: spec v14 Decision 4 collapsed
             that deliberately. The digest and lessons are analytics and live
             here; a single trade's excursions live beside the note that
             explains them, on the detail view. -->
        <sb-panel heading="Journal">
          @if (store.journalError(); as message) {
            <p class="stale" role="status">Journal unavailable — {{ message }}</p>
          } @else if (store.journalEmpty()) {
            <p class="stale" role="status">
              No journal entries yet — they are written when a trade closes.
            </p>
          } @else {
            <p class="series-note">
              From {{ store.journalEntryCount() }}
              {{ store.journalEntryCount() === 1 ? 'entry' : 'entries' }}.
            </p>
            @if (store.digest().length) {
              <h3 class="sub">This week</h3>
              <ul class="lines">
                @for (line of store.digest(); track line) {
                  <li>{{ line }}</li>
                }
              </ul>
            }
            @if (store.lessons().length) {
              <h3 class="sub">Recurring lessons</h3>
              <ul class="lines">
                @for (lesson of store.lessons(); track lesson) {
                  <li>{{ lesson }}</li>
                }
              </ul>
            }
          }
        </sb-panel>

        <sb-panel heading="By confidence level" [flush]="true">
          <sb-data-table
            [rows]="confidencePage.visible()"
            [columns]="confidenceColumns()"
            [visible]="confidenceKeys"
            [rowKey]="confidenceKey"
            [loading]="store.loading()"
            [emptyState]="confidenceEmpty"
            [pagination]="confidencePage.pageSpec()"
            (pageChange)="confidencePage.setPage($event)"
          />
        </sb-panel>

        <sb-panel [heading]="'By ' + store.breakdownLabel().toLowerCase()" [flush]="true">
          <!-- One table with a dimension picker rather than eight tables. The
               Jinja page had three of these plus seven pie charts over the
               same by-dimension block; the picker says outright they are one
               question asked eight ways. -->
          <div panel-actions class="dimension">
            <sb-select
              label="Group by"
              [value]="store.breakdown()"
              [options]="dimensions"
              (valueChange)="onBreakdown($event)"
            />
          </div>
          <sb-data-table
            [rows]="breakdownPage.visible()"
            [columns]="breakdownColumns()"
            [visible]="breakdownKeys"
            [rowKey]="breakdownKey"
            [loading]="store.loading()"
            [emptyState]="breakdownEmpty()"
            [pagination]="breakdownPage.pageSpec()"
            (pageChange)="breakdownPage.setPage($event)"
          />
        </sb-panel>
      }

      <!-- -- strategies ----------------------------------------------- -->
      @case ('strategies') {
        @if (decayed(); as names) {
          @if (names.length) {
            <p class="alert" role="alert">
              Edge decay flagged for {{ names.join(', ') }} — live win rate has
              drifted meaningfully below the out-of-sample figure.
            </p>
          }
        }

        <!-- SR61. strategies.html:10-18, copied rather than paraphrased --
             it states exactly how a badge is earned and what it feeds. -->
        <p class="section-help">
          This page answers "is this strategy's edge still working?" for every
          confirming method the bot trades. Each was backtested once on a
          held-out out-of-sample (OOS) window and given a
          <strong>VALIDATED</strong> badge if it cleared the acceptance bar, or
          <strong>WEAK</strong> if it didn't — that badge feeds directly into a
          live plan's quality score and A/B/C tier (see the Calibration tab's
          Tier calibration table). The Live columns then track how that
          strategy is actually doing right now; a DECAY chip means live win
          rate has fallen meaningfully below what OOS testing promised.
        </p>

        <sb-panel heading="Strategy registry" [flush]="true">
          <p class="panel-subtitle">out-of-sample validation status per strategy</p>
          <sb-data-table
            [rows]="strategyPage.visible()"
            [columns]="strategyColumns()"
            [visible]="strategyKeys"
            [rowKey]="strategyKey"
            [loading]="store.loading()"
            [emptyState]="strategyEmpty"
            [pagination]="strategyPage.pageSpec()"
            (pageChange)="strategyPage.setPage($event)"
          />

          <!-- SR61. The twelve column tips from strategies.html:30-41. A
               glossary under the table rather than a tip icon per header,
               per this task's Step 2: the SPA has no tip-icon component and
               adding one would be a design decision, not a copy task. -->
          <details class="glossary">
            <summary>What these columns mean</summary>
            <dl>
              @for (entry of strategyGlossary; track entry.term) {
                <div><dt>{{ entry.term }}</dt><dd>{{ entry.gloss }}</dd></div>
              }
            </dl>
          </details>
        </sb-panel>

        @if (store.heatmap(); as heatmap) {
          <sb-panel heading="Win rate by strategy and horizon" [flush]="true">
            <div class="scroller">
              <table class="heat">
                <thead>
                  <tr>
                    <th></th>
                    @for (horizon of heatmap.horizons; track horizon) {
                      <th class="num">{{ horizon }}</th>
                    }
                  </tr>
                </thead>
                <tbody>
                  @for (strategy of heatmap.strategies; track strategy) {
                    <tr>
                      <th scope="row">{{ strategy }}</th>
                      @for (horizon of heatmap.horizons; track horizon) {
                        <td class="num cell" [style.--heat]="heat(strategy, horizon)">
                          {{ heatLabel(strategy, horizon) }}
                        </td>
                      }
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </sb-panel>
        }
      }

      <!-- -- calibration ---------------------------------------------- -->
      @case ('calibration') {
        <!-- SR61. calibration.html:5-15. The tab used to open straight into
             a table whose numbers mean nothing without this. -->
        <p class="section-help">
          Calibration asks one question: does a higher confidence score
          actually win more? Every closed trade is bucketed into a decile by
          its confidence score at entry, and each decile's realised win rate is
          judged against the 80% target. A well-calibrated system produces a
          roughly upward-sloping staircase — top-decile trades should win
          noticeably more often than bottom-decile trades. A flat or inverted
          staircase means the score isn't actually predictive yet and needs
          revisiting before it's trusted for sizing or filtering decisions.
        </p>

        <sb-panel heading="Quality score vs outcome" [flush]="true">
          <!-- SR61. The Jinja chart drew an 80% line across the deciles; the
               SPA rewrite dropped it and kept only this sentence. Restored
               below -- 80 is calibration.py:_meets_band's A-tier bar,
               verified -- with the table underneath for the exact figures. -->
          <p class="panel-subtitle">
            Each decile's realised win rate, against an 80% target.
          </p>
          @if (store.decileHistogram().length) {
            <sb-histogram [bins]="store.decileHistogram()" [max]="100" [referenceLine]="80" />
          }
          <sb-data-table
            [rows]="decilePage.visible()"
            [columns]="decileColumns"
            [visible]="decileKeys"
            [rowKey]="decileKey"
            [loading]="store.loading()"
            [emptyState]="decileEmpty"
            [pagination]="decilePage.pageSpec()"
            (pageChange)="decilePage.setPage($event)"
          />
        </sb-panel>

        <sb-panel heading="Tier calibration" [flush]="true">
          <!-- SR61. stats.html:19 and :21. Both numbers verified against code
               before being written down: the A/B/C SCORE bands are
               quality.py:_tier (>=75, 50-74, <50) and the win-rate bands
               each tier is judged against are calibration.py:EXPECTED_BAND
               (A >=80, B 70-80, C <70). They are different scales and the
               original copy was right to name only the first. -->
          <p class="panel-subtitle">
            Every plan is graded A (score ≥75), B (50–74) or C (below 50) when
            it is built. This table checks whether that grading holds up: does
            tier A actually win more often live than tier C? "Pass" means the
            tier's live win rate falls inside the band it is supposed to
            deliver — and a verdict needs at least 10 closed trades, below
            which it reads as unknown rather than as a failure.
          </p>
          <p class="section-help">
            If A/B rows stay empty or thin (N small), it usually means too few
            trades have closed yet at that tier — not that the tiering is
            broken. See the Strategies tab for why a strategy's badge
            (VALIDATED vs WEAK) may be dragging its tier down.
          </p>
          <sb-data-table
            [rows]="tierPage.visible()"
            [columns]="tierColumns()"
            [visible]="tierKeys"
            [rowKey]="tierKey"
            [loading]="store.loading()"
            [emptyState]="tierEmpty"
            [pagination]="tierPage.pageSpec()"
            (pageChange)="tierPage.setPage($event)"
          />
        </sb-panel>

        <sb-panel heading="Badge drift" [flush]="true">
          <!-- SR61. stats.html:48 and :50. The rule is
               calibration.py:DRIFT_LIVE_N_FLOOR (20) and
               DRIFT_THRESHOLD_POINTS (10.0), both verified. -->
          <p class="panel-subtitle">
            "Decay" = edge decay. A strategy earns a VALIDATED badge from a
            historical out-of-sample backtest with a committed win rate; this
            table compares that to how it is actually performing live. A decay
            flag is an early warning that the edge may no longer hold in
            current market conditions.
          </p>
          <p class="section-help">
            Flagged only once a strategy has at least 20 closed live trades
            (fewer than that is too noisy to judge) AND live win rate is more
            than 10 percentage points below its out-of-sample win rate.
          </p>
          <sb-data-table
            [rows]="driftPage.visible()"
            [columns]="driftColumns()"
            [visible]="driftKeys"
            [rowKey]="driftKey"
            [loading]="store.loading()"
            [emptyState]="driftEmpty"
            [pagination]="driftPage.pageSpec()"
            (pageChange)="driftPage.setPage($event)"
          />
        </sb-panel>
      }

      <!-- -- tuning --------------------------------------------------- -->
      @case ('tuning') {
        <sb-panel heading="Run a TRAIN grid">
          <p class="section-help">
            A grid search runs one strategy's parameters through every
            combination in its tuning grid against the fixed TRAIN window
            (2020-01-01 .. 2023-12-31) —
            never the VALIDATION window the badges on the Strategies tab are
            measured against. That firewall is what keeps those badges honest,
            so no date input exists here or anywhere in this workbench.
          </p>

          @if (store.jobActive()) {
            <p class="section-help">
              A job is running. The server allows one at a time, so the
              launcher returns when it finishes.
            </p>
          } @else {
            <sb-control-row class="launch">
              <sb-select
                label="Strategy"
                placeholder="Pick a strategy"
                [(value)]="strategy"
                [options]="strategyOptions()"
              />
              <button
                sb-button
                type="button"
                variant="primary"
                [disabled]="strategy() === ''"
                [loading]="store.launching()"
                (click)="launch()"
              >
                Launch TRAIN grid
              </button>
            </sb-control-row>
            @if (store.launchError(); as message) {
              <p class="alert" role="alert">{{ message }}</p>
            }
          }
        </sb-panel>

        @if (store.job(); as job) {
          <sb-panel [heading]="'Job ' + job.id" [flush]="true">
            <div class="jobhead">
              <sb-chip [label]="jobStateLabel(job)" [tone]="jobTone(job)" />
              <span class="muted">started {{ fmtDateTime(job.started_at) }}</span>
            </div>
            <pre class="log">{{ job.log_tail || 'No output yet.' }}</pre>
            <p class="section-help">
              Progress arrives on the <code>jobs</code> event. Nothing on this
              page polls, and the log stays put when the job ends.
            </p>
          </sb-panel>
        }

        <!-- SR51. The results table, and the Propose button that lived in it.
             Without this the tab could start work and file work away but not
             act on what a run found -- which left the Proposals panel below
             unreachable by any normal route. -->
        @if (store.grid().length) {
          <sb-panel [heading]="gridHeading()" [flush]="true">
            @if (store.proposeResult(); as message) {
              <p class="section-help" role="status">{{ message }}</p>
            }
            @if (store.proposeError(); as message) {
              <p class="alert" role="alert">{{ message }}</p>
            }

            <sb-data-table
              [rows]="gridPage.visible()"
              [columns]="gridColumns()"
              [visible]="gridKeys"
              [rowKey]="gridRowKey"
              [pagination]="gridPage.pageSpec()"
              (pageChange)="gridPage.setPage($event)"
            />

            <p class="section-help">
              A row clears the bar at 30 or more evaluated trades, a win rate of
              80% or better, positive expectancy, and no more than half the
              candidate signals excluded. Among the rows that clear it, prefer
              the highest expectancy.
            </p>
          </sb-panel>
        }

        @if (store.pastJobs(); as past) {
          @if (past.length) {
            <sb-panel heading="Earlier jobs" [flush]="true">
              <sb-data-table
                [rows]="pastJobsPage.visible()"
                [columns]="pastJobsColumns"
                [visible]="pastJobsKeys"
                [rowKey]="pastJobRowKey"
                [pagination]="pastJobsPage.pageSpec()"
                (pageChange)="pastJobsPage.setPage($event)"
              />
            </sb-panel>
          }
        }

        <sb-panel heading="Proposals">
          <p class="section-help">
            A proposal is a staged parameter change, not an applied one:
            applying means editing <code>entry_filters.DEFAULT_PARAMS</code> by
            hand, running the suite, and only then spending a validation shot.
          </p>

          @if (proposalViews().length === 0) {
            <p class="muted">No proposals yet.</p>
          }
          @for (proposal of proposalsPage.visible(); track proposal.filename) {
            <div class="proposal">
              <header class="proposal-head">
                <strong>{{ proposal.strategy }}</strong>
                <span class="muted">
                  {{ fmtDateTime(proposal.created_at) }} · job {{ proposal.job_id }}
                </span>
              </header>
              <table class="diff">
                <thead>
                  <tr><th>Parameter</th><th class="num">Current</th><th class="num">Proposed</th></tr>
                </thead>
                <tbody>
                  @for (param of proposal.params; track param.key) {
                    <tr>
                      <td>{{ param.key }}</td>
                      <td class="num muted">{{ param.current }}</td>
                      <td class="num">{{ param.proposed }}</td>
                    </tr>
                  }
                </tbody>
              </table>
              <p class="muted">{{ proposal.trainSummary }}</p>
              <button
                sb-button
                type="button"
                variant="danger"
                (click)="pendingDelete.set(proposal)"
              >
                Delete
              </button>
            </div>
          }
          <sb-pagination [pagination]="proposalsPage.pageSpec()" (pageChange)="proposalsPage.setPage($event)" />
        </sb-panel>
      }

      <!-- -- plans ---------------------------------------------------- -->
      @case ('plans') {
        <p class="section-help">
          Every plan ever posted, and how far it got: PENDING (posted,
          waiting for its entry trigger) &rarr; ACTIVE (filled) &rarr;
          PARTIAL (TP1 hit) &rarr; CLOSED, or CANCELLED at any point before
          filling. Fill rate and time-to-fill are measured over RESOLVED
          plans only (CLOSED or CANCELLED) &mdash; a plan still waiting
          hasn't finished its journey yet, and counting it would bias the
          rate toward "undecided".
        </p>

        <sb-panel heading="Lifecycle funnel">
          @if (store.funnelChart().length) {
            <sb-histogram [bins]="store.funnelChart()" />
            <p class="series-note">{{ store.inFlight() }} currently in flight (not counted above).</p>
          } @else {
            <p class="stale">No plans posted yet.</p>
          }
        </sb-panel>

        <div class="panels">
          <sb-panel heading="Fill rate">
            <sb-chip-row class="chips">
              <sb-metric-chip label="Filled" [value]="store.fillRatePct()" unit="%" [decimals]="1" />
              <sb-metric-chip label="Median days to fill" [value]="store.medianDaysToFill()" [decimals]="1" />
            </sb-chip-row>
          </sb-panel>

          <sb-panel heading="Badge distribution">
            @if (store.badgeChart().length) {
              <sb-histogram [bins]="store.badgeChart()" [isNegative]="isWeakBadge" />
            } @else {
              <p class="stale">No plans posted yet.</p>
            }
          </sb-panel>
        </div>

        <sb-panel heading="Tier distribution">
          @if (store.tierChart().length) {
            <sb-histogram [bins]="store.tierChart()" />
          } @else {
            <p class="stale">No plans posted yet.</p>
          }
        </sb-panel>
      }
    }

    <!-- cells ----------------------------------------------------------
         Declared at the top level, never inside the @switch: a template
         inside an inactive branch does not exist, and the viewChild queries
         below are required. -->

    <ng-template #rollingCell let-row>
      @if (series(row); as points) {
        @if (points.length > 1) {
          <sb-sparkline [points]="points" [label]="row.strategy + ' rolling win rate'" />
        } @else {
          <span class="muted">—</span>
        }
      }
    </ng-template>

    <ng-template #badgeCell let-row>
      <!-- Greyscale, not green/red: a validation badge is a quality judgement
           and green means P&L direction and nothing else. -->
      <sb-chip
        [label]="row.status"
        [tone]="row.status === 'VALIDATED' ? 'q5' : 'q2'"
      />
    </ng-template>

    <ng-template #levelCell let-row>
      <sb-quality-chip [value]="row.level" [label]="'Lv' + row.level" />
    </ng-template>

    <ng-template #tierCell let-row>
      <sb-quality-chip [value]="row.tier" [label]="row.tier" />
    </ng-template>

    <ng-template #bandCell let-row>
      @if (row.ok === null) {
        <!-- Three-valued, and this is the third: "not enough live data to
             judge" is not the same claim as "judged and missing its band". -->
        <span class="muted" title="Fewer than 10 closed trades — not judged yet">—</span>
      } @else if (row.ok) {
        <span>In band</span>
      } @else {
        <sb-chip label="Off band" tone="q2" />
      }
    </ng-template>

    <ng-template #decayCell let-row>
      @if (row.drift_alert) {
        <sb-chip label="DECAY" tone="q2" />
      } @else {
        <span class="muted">—</span>
      }
    </ng-template>

    <ng-template #gridPassesCell let-row>
      @if (row.passes) {
        <sb-chip label="Clears" tone="q5" />
      }
    </ng-template>
    <ng-template #gridProposeCell let-row>
      <button
        sb-button
        variant="secondary"
        type="button"
        [loading]="store.proposing() === row.row_index"
        (click)="askPropose(row)"
      >
        Propose
      </button>
    </ng-template>

    <sb-confirm-dialog
      [open]="pendingDelete() !== null"
      title="Delete this proposal?"
      [consequence]="deleteConsequence()"
      confirmLabel="Delete"
      (confirmed)="confirmDelete()"
      (cancelled)="pendingDelete.set(null)"
    />

    <!-- Proposing writes a file that stages a change to how the bot trades.
         It is not destructive, but it is not nothing either, and the dialog is
         where the difference between staging and applying gets said out loud
         rather than left to a panel note further down the page. -->
    <sb-confirm-dialog
      [open]="pendingPropose() !== null"
      title="Stage these parameters?"
      [consequence]="proposeConsequence()"
      confirmLabel="Propose"
      [working]="store.proposing() !== null"
      (confirmed)="confirmPropose()"
      (cancelled)="pendingPropose.set(null)"
    />
  `,
  styles: `
    /* This component has no :host layout of its own -- .head's
       margin-bottom was the only thing separating the header from the
       content below, so it moves to the primitive's own host tag. */
    sb-section-head { margin-bottom: var(--space-14); }
    .stale { color: var(--warn); font-size: var(--text-table); }

    sb-panel { display: block; margin-top: var(--space-14); }

    .section {
      margin: var(--space-20) 0 var(--space-10);
      color: var(--text-faint);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .section:first-of-type { margin-top: 0; }

    .alert {
      margin-top: var(--space-14);
      padding: var(--space-8) var(--space-10);
      border: 1px solid var(--warn);
      border-radius: var(--radius);
      color: var(--warn);
      font-size: var(--text-table);
    }

    .panels {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
      gap: var(--space-14);
      align-items: start;
    }
    @media (max-width: 1000px) {
      .panels { grid-template-columns: 1fr; }
    }

    /* Overrides sb-chip-row's own flex-wrap default with a grid -- the
       type selector plus this class gives it enough specificity to beat
       the primitive's own :host rule. */
    sb-chip-row.chips {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: var(--space-8);
    }

    dl { display: grid; gap: var(--space-6); }

    /* -- SR54: the range control ---------------------------------------- */

    .range { margin-bottom: var(--space-8); }

    .range .sample {
      margin-left: auto;
      color: var(--text-faint);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
    }

    /* .panel-subtitle and .section-help carry no horizontal padding of
       their own (styles.css). Inside a [flush]="true" sb-panel that leaves
       them flush against the panel's left border while the panel's own
       <header> keeps its 14px padding -- visibly misaligned against the
       heading directly above. Every flush panel on this workspace (Strategy
       registry, Tier calibration, Badge drift, and Task 8's restored
       Calibration chart) gets this fix from one rule. */
    sb-panel .panel-subtitle,
    sb-panel .section-help {
      padding: 0 var(--space-14);
    }

    /* -- SR55/SR61: explanatory copy ------------------------------------ */

    .glossary, .sub {
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    .glossary { margin-top: var(--space-8); }
    .glossary summary { cursor: pointer; color: var(--text-faint); }
    .glossary dl, .lines { display: grid; margin: 0; }
    .glossary dl { gap: var(--space-6); margin-top: var(--space-8); }
    .glossary dt { color: var(--text-primary); font-weight: 600; }
    .glossary dd { margin: 0; line-height: 1.5; }
    .sub {
      margin: var(--space-8) 0 var(--space-4);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .lines {
      gap: var(--space-4);
      padding-left: var(--space-8);
      color: var(--text-primary);
    }

    /* -- SR50: the snapshot's panels ------------------------------------ */

    .series-note { margin-top: var(--space-6); color: var(--text-faint); }
    .series-note { font-size: var(--text-chip); }
    .dimension { min-width: 160px; }


    /* -- SR51: the grid results ----------------------------------------- */

    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); font-size: var(--text-table); }
    dd { color: var(--text); font-size: var(--text-table); }

    .muted { color: var(--text-muted); font-size: var(--text-table); }
    /* The global .section-help (styles.css) already supplies colour,
       font-size, line-height and margin-bottom -- this only adds the
       reading-width cap and this page's own sibling spacing. */
    .section-help { max-width: 70ch; }
    .section-help + .section-help, .section-help + .launch { margin-top: var(--space-10); }
    code { font-family: var(--font-mono); }

    /* -- heatmap ------------------------------------------------------
       Intensity is a greyscale wash rather than a green-to-red ramp. A win
       rate is a quality figure, not money, and the colour rules reserve
       green and red for P&L direction — a red cell here would mean the same
       thing as a red P&L two tabs away, which it does not. */
    .scroller { overflow-x: auto; }
    .heat { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .heat th, .heat td {
      padding: var(--space-6) var(--space-10);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }
    .heat thead th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .heat tbody th { text-align: left; font-weight: 600; }
    .heat .num { text-align: right; font-family: var(--font-mono); }
    .cell {
      background: color-mix(in srgb, var(--text) calc(var(--heat, 0) * 14%), transparent);
    }

    /* -- tuning -------------------------------------------------------- */
    /* .launch keeps its class as a marker only -- sb-control-row supplies
       every declaration the rule used to carry. */

    .jobhead {
      display: flex;
      align-items: center;
      gap: var(--space-10);
      padding: var(--space-10) var(--space-14);
    }
    .log {
      max-height: 320px;
      margin: 0;
      padding: var(--space-10) var(--space-14);
      overflow: auto;
      background: var(--bg);
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      color: var(--text-secondary);
      font-family: var(--font-mono);
      font-size: var(--text-table);
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .log + .section-help { padding: var(--space-10) var(--space-14); }

    .proposal {
      margin-top: var(--space-10);
      padding: var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .proposal-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: var(--space-10);
      margin-bottom: var(--space-8);
      font-size: var(--text-table);
    }
    .diff { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .diff th, .diff td {
      padding: var(--space-4) var(--space-8);
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    .diff th {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .diff .num { text-align: right; font-family: var(--font-mono); }
    .proposal .muted { display: block; margin: var(--space-8) 0; }
  `,
})
export class Analytics {
  private readonly router = inject(Router);
  protected readonly store = inject(AnalyticsStore);
  private readonly connection = inject(ConnectionStore);

  /** The account's currency symbol, as a metric-chip unit. Same fix as the
   *  Dashboard's: `" USD"` was written into the template while
   *  `CURRENCY_SYMBOL` has defaulted to `€`. */
  protected readonly currencyUnit = computed(() => ` ${this.connection.currency()}`);

  /** The active tab, as a query parameter — arriving through
   *  `withComponentInputBinding` rather than `ActivatedRoute`, so this
   *  component is testable without standing up a router. */
  readonly tab = input<string>();

  protected readonly tabs = TABS;

  /** An unknown or absent `?tab=` falls back to Performance rather than
   *  rendering nothing, so a hand-edited or stale URL still shows data. */
  protected readonly activeTab = computed<AnalyticsTab>(() => {
    const requested = this.tab();
    return requested && TAB_IDS.has(requested)
      ? (requested as AnalyticsTab)
      : 'performance';
  });

  /* -- formatters (shared with the column declarations) ---------------- */

  protected readonly fmtRate = rate;
  protected readonly fmtDateTime = dateTime;

  protected fmtExpectancy(value: number | null): string {
    return value === null ? ABSENT : `${expectancy(value)}R`;
  }

  protected fmtCount(value: number | null): string {
    return value === null ? ABSENT : String(value);
  }

  /* -- SR61: the column glossary --------------------------------------- */

  /**
   * The eleven `?` tips from `strategies.html:30-41` (originally twelve --
   * v31 Task 14 removed the "R:R" entry along with the per-strategy fixed
   * reward:risk override it described: every strategy's target is now a
   * real structural level, chosen per-plan by
   * plan_engine.select_structural_target).
   */
  protected readonly strategyGlossary: { term: string; gloss: string }[] = [
    {
      term: 'Rolling WR',
      gloss: 'Win rate over just the last 10 closed trades for this strategy — '
        + 'a short-window sanity check, separate from the full Live WR column.',
    },
    {
      term: 'Badge',
      gloss: 'VALIDATED = this strategy cleared its out-of-sample acceptance '
        + 'bar in a one-shot backtest. WEAK = it did not. A live plan only '
        + 'gets full badge-quality points when its primary confirming method '
        + 'is VALIDATED.',
    },
    { term: 'OOS N', gloss: 'Number of trades in the out-of-sample backtest this badge is based on.' },
    {
      term: 'OOS WR',
      gloss: 'Win rate achieved in that one-shot out-of-sample backtest — the '
        + 'number the badge and the live comparison are measured against.',
    },
    {
      term: 'OOS ExpR',
      gloss: 'Expectancy in R-multiples from the same backtest — average return '
        + 'per trade as a multiple of planned risk.',
    },
    { term: 'Live N', gloss: 'Number of closed live trades attributed to this strategy so far.' },
    { term: 'Live WR', gloss: 'Actual win rate from live closed trades attributed to this strategy.' },
    {
      term: 'Δ vs OOS',
      gloss: 'Live WR minus OOS WR. Decay is flagged once Live N reaches at '
        + 'least 20 trades AND this delta drops below −10 points — enough live '
        + 'sample to trust, and a large enough gap to call it decay rather '
        + 'than noise.',
    },
    { term: 'Window', gloss: 'The date range of historical data the OOS backtest was run over.' },
    { term: 'Run date', gloss: "When this strategy's OOS validation was last run and committed." },
    { term: 'Gate', gloss: 'The entry-confirmation rule this strategy must satisfy to fire a signal at all.' },
  ];

  /* -- SR54: the range control ----------------------------------------- */

  /** Says out loud which figures the range covers. The two panels above it
   *  are all-time, and a heading that just said "Derived" would leave the
   *  reader to work that out from the numbers. */
  protected readonly derivedHeading = computed(() =>
    this.store.rangeActive() ? 'Derived (selected range)' : 'Derived (all time)',
  );

  /** Trades in the window, so a figure computed on a handful is not read with
   *  the confidence of one computed on hundreds. */
  protected readonly sampleLabel = computed(() => {
    const n = this.store.rangeSampleSize();
    return `${n} closed ${n === 1 ? 'trade' : 'trades'}`;
  });

  protected onRangeFrom(value: string): void {
    this.store.setRange(value || null, this.store.rangeTo());
  }

  protected onRangeTo(value: string): void {
    this.store.setRange(this.store.rangeFrom(), value || null);
  }

  /* -- cell templates --------------------------------------------------- */

  private readonly rollingCell = viewChild.required<TemplateRef<unknown>>('rollingCell');
  private readonly badgeCell = viewChild.required<TemplateRef<unknown>>('badgeCell');
  private readonly levelCell = viewChild.required<TemplateRef<unknown>>('levelCell');
  private readonly tierCell = viewChild.required<TemplateRef<unknown>>('tierCell');
  private readonly bandCell = viewChild.required<TemplateRef<unknown>>('bandCell');
  private readonly decayCell = viewChild.required<TemplateRef<unknown>>('decayCell');
  private readonly gridPassesCell = viewChild.required<TemplateRef<unknown>>('gridPassesCell');
  private readonly gridProposeCell = viewChild.required<TemplateRef<unknown>>('gridProposeCell');

  /** The declared columns with rich cells attached by key — the same split
   *  Trades uses, so `analytics.columns.ts` stays free of templates. */
  protected readonly strategyColumns = computed<ColumnDef<StrategyRow>[]>(() =>
    attach(STRATEGY_COLUMNS, {
      rolling: this.rollingCell(),
      status: this.badgeCell(),
    }),
  );

  protected readonly confidenceColumns = computed(() =>
    attach(CONFIDENCE_COLUMNS, { level: this.levelCell() }),
  );

  protected readonly tierColumns = computed(() =>
    attach(TIER_COLUMNS, { tier: this.tierCell(), ok: this.bandCell() }),
  );

  protected readonly driftColumns = computed(() =>
    attach(DRIFT_COLUMNS, { drift_alert: this.decayCell() }),
  );

  protected readonly gridColumns = computed(() =>
    attach(GRID_COLUMNS, {
      passes: this.gridPassesCell(),
      propose: this.gridProposeCell(),
    }),
  );

  protected readonly decileColumns = DECILE_COLUMNS;

  protected readonly strategyKeys = allKeys(STRATEGY_COLUMNS);
  protected readonly confidenceKeys = allKeys(CONFIDENCE_COLUMNS);
  protected readonly decileKeys = allKeys(DECILE_COLUMNS);
  protected readonly tierKeys = allKeys(TIER_COLUMNS);
  protected readonly driftKeys = allKeys(DRIFT_COLUMNS);
  protected readonly gridKeys = allKeys(GRID_COLUMNS);
  protected readonly pastJobsKeys = allKeys(PAST_JOBS_COLUMNS);

  protected readonly strategyKey = (row: StrategyRow) => row.strategy;
  protected readonly strategyPage = createClientPage(() => this.store.strategyRows());
  protected readonly confidenceKey = (row: { level: number }) => String(row.level);
  protected readonly confidencePage = createClientPage(() => this.store.byConfidence());
  protected readonly decileKey = (row: { decile: string }) => row.decile;
  protected readonly decilePage = createClientPage(() => this.store.deciles());
  protected readonly tierKey = (row: TierRow) => row.tier;
  protected readonly tierPage = createClientPage(() => this.store.tiers());
  protected readonly driftKey = (row: DriftRow) => row.strategy;
  protected readonly driftPage = createClientPage(() => this.store.drift());
  protected readonly gridRowKey = (row: GridRow) => String(row.row_index);
  protected readonly gridPage = createClientPage(() => this.store.grid());
  protected readonly pastJobRowKey = (row: JobSummary) => row.id;
  protected readonly pastJobsPage = createClientPage(() => this.store.pastJobs());
  protected readonly pastJobsColumns = PAST_JOBS_COLUMNS; // static, no cell slots needed

  /** WEAK reads as the "loss" side of this bar list -- greyscale would be
   *  equally defensible (a badge is a quality judgement, not P&L), but
   *  VALIDATED-vs-WEAK is structurally the same "good/bad split" the
   *  green/red pair exists for elsewhere on this workspace's strategy
   *  badges (see #badgeCell's own note on why THAT one stays greyscale --
   *  the difference is this chart has no chip carrying the badge word
   *  beside it, so colour is the only signal available here). */
  protected readonly isWeakBadge = (bin: HistogramBin): boolean => bin.label === 'WEAK';

  /* Empty states are sentences about *this* table's situation, never a
   * generic "No data" — see `EmptyStateComponent`. */
  protected readonly strategyEmpty = {
    title: 'No strategies in the registry',
    hint: 'The validation registry is committed with the code; an empty one means it has not been generated yet.',
  };
  protected readonly confidenceEmpty = {
    title: 'No trades to break down',
    hint: 'Levels appear once trades have been logged against them.',
  };

  /* -- SR50: the snapshot's panels ------------------------------------- */

  protected readonly dimensions = BREAKDOWN_DIMENSIONS.map((d) => ({
    value: d.value,
    label: d.label,
  }));

  protected readonly breakdownColumns = computed(() =>
    breakdownColumns(this.store.breakdownLabel()),
  );
  protected readonly breakdownKeys = allKeys(breakdownColumns(''));
  protected readonly breakdownKey = (row: BreakdownRow) => row.key;
  protected readonly breakdownPage = createClientPage(() => this.store.breakdownRows());

  protected readonly breakdownEmpty = computed(() => ({
    title: `Nothing grouped by ${this.store.breakdownLabel().toLowerCase()} yet`,
    hint: 'Groups appear once trades close against them.',
  }));

  protected onBreakdown(value: string): void {
    this.store.setBreakdown(value as BreakdownDimension);
    this.breakdownPage.setPage(1);
  }

  protected readonly fmtLineValue = (value: number): string => `${value.toFixed(2)}%`;

  protected readonly drawdownSeriesForChart = computed<LineChartSeries[]>(() => [
    { name: 'Drawdown', points: this.store.drawdownSeries() },
  ]);

  /** "3 wins" rather than "3". The number alone does not say which way the run
   *  is going, and a current streak is the one figure here where that is the
   *  whole point. */
  protected currentStreak(streaks: Streaks): string {
    if (streaks.current === null || streaks.current === 0 || !streaks.currentKind) {
      return 'none';
    }
    const plural = streaks.current === 1 ? '' : 's';
    const noun = streaks.currentKind === 'win' ? 'win' : 'loss';
    return `${streaks.current} ${noun === 'loss' ? (plural ? 'losses' : 'loss') : noun + plural}`;
  }

  protected seriesRange(series: { date: string }[]): string {
    if (!series.length) return ABSENT;
    return `${date(series[0].date)} → ${date(series[series.length - 1].date)}`;
  }
  protected readonly decileEmpty = {
    title: 'No scored trades yet',
    hint: 'Only closed trades carrying a quality score can be bucketed.',
  };
  protected readonly tierEmpty = {
    title: 'No tier calibration available',
    hint: 'The analytics snapshot has not been built yet.',
  };
  protected readonly driftEmpty = {
    title: 'No validated strategies to watch',
    hint: 'Drift is only measured for strategies that hold a VALIDATED badge.',
  };

  /* -- strategies ------------------------------------------------------- */

  protected readonly decayed = computed(() =>
    this.store
      .strategyRows()
      .filter((row) => row.decayed)
      .map((row) => row.strategy),
  );

  /** Nulls dropped: the server emits one for a window it could not compute,
   *  and the sparkline plots numbers. */
  protected series(row: StrategyRow): number[] {
    return (row.win_rate_series ?? []).filter((point): point is number => point !== null);
  }

  /** The flattened cells, indexed for O(1) lookup while rendering the grid.
   *  A linear scan per cell would be strategies × horizons × cells. */
  private readonly heatIndex = computed(() => {
    const index = new Map<string, HeatmapCell>();
    for (const cell of this.store.heatmap()?.cells ?? []) {
      index.set(`${cell.strategy}|${cell.horizon}`, cell);
    }
    return index;
  });

  /** 0–1, feeding the greyscale wash. A cell with no sample gets 0 rather
   *  than a faint tint, so "untested" and "tested and terrible" look
   *  different. */
  protected heat(strategy: string, horizon: string): number {
    const cell = this.heatIndex().get(`${strategy}|${horizon}`);
    if (!cell || cell.win_rate === null) return 0;
    return Math.max(0, Math.min(1, cell.win_rate / 100));
  }

  protected heatLabel(strategy: string, horizon: string): string {
    const cell = this.heatIndex().get(`${strategy}|${horizon}`);
    if (!cell || cell.win_rate === null) return ABSENT;
    return `${cell.win_rate.toFixed(0)}% (${cell.n ?? 0})`;
  }

  /* -- tuning ----------------------------------------------------------- */

  protected readonly strategy = signal('');

  protected readonly strategyOptions = computed(() =>
    this.store.strategyNames().map((name) => ({ value: name, label: name })),
  );

  protected jobStateLabel(job: JobStatus): string {
    const state = job.state.toUpperCase();
    return job.returncode === null || job.returncode === undefined
      ? state
      : `${state} (exit ${job.returncode})`;
  }

  /** Amber for a failure, greyscale otherwise. A failed job is a caution to
   *  act on, not a loss — and red is reserved for P&L. */
  protected jobTone(job: JobStatus) {
    if (job.state === 'failed') return qualityTone('C');
    if (job.state === 'running' || job.state === 'queued') return qualityTone('A');
    return qualityTone(null);
  }

  protected launch(): void {
    const strategy = this.strategy();
    if (strategy) this.store.startTune(strategy);
  }

  /* -- SR51: the grid results ------------------------------------------- */

  protected readonly pendingPropose = signal<GridRow | null>(null);

  protected readonly gridHeading = computed(() => {
    const strategy = this.store.gridStrategy();
    return strategy ? `Grid results — ${strategy}` : 'Grid results';
  });

  protected askPropose(row: GridRow): void {
    this.pendingPropose.set(row);
  }

  protected readonly proposeConsequence = computed(() => {
    const row = this.pendingPropose();
    if (!row) return '';
    const strategy = this.store.gridStrategy() ?? 'this strategy';
    // Says outright what staging is and is not. The Jinja page put this in a
    // tip icon on a card heading, where it was read once.
    return (
      `Records ${row.paramLabel} as a candidate for ${strategy}. ` +
      'Nothing changes about how the bot trades: applying means editing ' +
      'entry_filters.DEFAULT_PARAMS by hand, running the suite, and only then ' +
      'spending a validation shot.' +
      (row.passes
        ? ''
        : ' This row did NOT clear the acceptance bar.')
    );
  });

  protected confirmPropose(): void {
    const row = this.pendingPropose();
    if (!row) return;
    this.store.propose(row.row_index);
    this.pendingPropose.set(null);
  }

  /* -- proposals -------------------------------------------------------- */

  protected readonly pendingDelete = signal<ProposalRow | null>(null);

  /** Proposals with their parameter diff paired up. Built once per change
   *  rather than by a method the template calls per row: a method would
   *  return a new array on every check and defeat `@for`'s tracking. */
  protected readonly proposalViews = computed<ProposalView[]>(() =>
    this.store.proposals().map((proposal) => {
      const current = proposal.current_params ?? {};
      const proposed = proposal.proposed_params ?? {};
      return {
        ...proposal,
        params: Object.entries(proposed).map(([key, value]) => ({
          key,
          // An em dash, not "undefined": a parameter the code does not
          // currently set is missing, not set to the string "undefined".
          current: current[key] === undefined ? ABSENT : String(current[key]),
          proposed: String(value),
        })),
        trainSummary: trainSummary(proposal),
      };
    }),
  );

  /** Each proposal is a card with its own nested diff table, not flat row
   *  data -- `sb-data-table` doesn't fit, so this gets its own small pager
   *  rather than the shared component. */
  protected readonly proposalsPage = createClientPage(() => this.proposalViews(), 8);

  protected readonly deleteConsequence = computed(() => {
    const proposal = this.pendingDelete();
    return proposal
      ? `Removes the staged ${proposal.strategy} proposal from disk. Nothing running changes — a proposal was never applied.`
      : '';
  });

  protected confirmDelete(): void {
    const proposal = this.pendingDelete();
    if (!proposal) return;
    this.store.removeProposal(proposal.filename);
    this.pendingDelete.set(null);
  }

  /* -- wiring ----------------------------------------------------------- */

  constructor() {
    // The one place the URL becomes store state, and the only thing that
    // decides which payload is fetched.
    effect(() => this.store.setTab(this.activeTab()));
  }

  protected goToTab(tab: string): void {
    // replaceUrl: flipping between tabs should not fill the history with
    // steps, but the tab must still be in the URL so it can be linked to.
    this.router.navigate([], {
      queryParams: { tab: tab === 'performance' ? null : tab },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}

/** Attach rich cell templates to declared columns by key. */
function attach<T>(
  columns: ColumnDef<T>[],
  cells: Record<string, TemplateRef<unknown>>,
): ColumnDef<T>[] {
  return columns.map((column) =>
    cells[column.key]
      ? // The templates are declared once for every table on the workspace, so
        // they cannot be typed to one row shape at their declaration site. The
        // cast is contained here rather than repeated at four call sites.
        { ...column, cell: cells[column.key] as unknown as ColumnDef<T>['cell'] }
      : column,
  );
}

/** The TRAIN-window figures a proposal was frozen from, on one line. */
function trainSummary(proposal: ProposalRow): string {
  const stats = proposal.train_stats ?? {};
  const n = typeof stats['n_eval'] === 'number' ? stats['n_eval'] : null;
  const wr = typeof stats['win_rate'] === 'number' ? stats['win_rate'] : null;
  const er = typeof stats['expectancy_r'] === 'number' ? stats['expectancy_r'] : null;
  return `TRAIN: N=${n ?? ABSENT} · WR=${rate(wr)} · ExpR=${expectancy(er)}`;
}
