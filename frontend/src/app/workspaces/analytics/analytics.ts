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
  WritableSignal,
} from '@angular/core';
import { Router } from '@angular/router';

import { AnalyticsByDimensionRow } from '../../api/models';
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
  rateOrWithheld,
} from '../../stores/analytics.store';
import { ConnectionStore } from '../../stores/connection.store';
import { PreferencesStore } from '../../stores/preferences.store';
import { asyncInputs, Async, AsyncInputs } from '../../ui/async';
import { Button } from '../../ui/button';
import { Chip, QualityChip, qualityTone } from '../../ui/chip';
import { ChipRow } from '../../ui/chip-row';
import { ConfirmDialog } from '../../ui/confirm-dialog';
import { DataTable } from '../../ui/data-table/data-table';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { createClientPage } from '../../ui/data-table/client-page';
import { readTablePerPage, writeTablePerPage } from '../../ui/table-prefs';
import { ControlBar } from '../../ui/control-bar';
import { DateRange } from '../../ui/date-range';
import { DonutComponent } from '../../ui/donut';
import { Select, TextInput } from '../../ui/form-controls';
import { ABSENT, dateTime, rMultiple, signed } from '../../ui/format';
import { Freshness } from '../../ui/freshness';
import { ControlRow, Panel, Tab, TabBar } from '../../ui/layout';
import { LineChart } from '../../ui/line-chart';
import { Magnitude } from '../../ui/magnitude';
import { SectionHead } from '../../ui/section-head';
import { Segmented, SegmentOption } from '../../ui/segmented';
import { Histogram, HistogramBin } from '../../ui/histogram';
import { MetricChip } from '../../ui/metric-chip';
import { PaginationComponent } from '../../ui/pagination';
import { Sparkline } from '../../ui/sparkline';
import { MIN_SAMPLE_N, StatTile } from '../../ui/stat-tile';
import { ExitQualitySectionComponent } from './sections/exit-quality';
import { StrategyContributionComponent } from './sections/strategy-contribution';
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
  count,
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
  // v54 D1: this workspace's bulk is tables (strategy registry, tier
  // calibration, badge drift, grid results, plans) -- tight rows, more per
  // screen -- so it defaults to the instrument register. On the host (a
  // static class, not a template wrapper) because :host is the ancestor the
  // register's three variables need to reach; the Snapshot panels below
  // override it back to register-presentation for the hero figures.
  host: { class: 'register-instrument' },
  // Provided here rather than in root, matching Dashboard and Trades: the store
  // is created on entry and destroyed on exit, so this workspace never holds
  // stale analytics while you are looking at another one.
  imports: [
    TabBar,
    Panel,
    ControlRow,
    ControlBar,
    DataTable,
    DateRange,
    DonutComponent,
    MetricChip,
    Histogram,
    Chip,
    ChipRow,
    QualityChip,
    Sparkline,
    Select,
    TextInput,
    Button,
    ConfirmDialog,
    Freshness,
    LineChart,
    Magnitude,
    PaginationComponent,
    SectionHead,
    Segmented,
    Async,
    ExitQualitySectionComponent,
    StrategyContributionComponent,
    StatTile,
  ],
  template: `
    <sb-section-head>
      <!-- Only for Tuning: the other four tabs each carry their own
           sb-async now, which already turns this same store.error() into
           either a first-load error panel or a demoted stale badge scoped
           to the panel that actually failed -- showing it here too would
           duplicate it. Tuning has no sb-async (its fetch is one of several
           independent, event/action-driven pieces of that tab, not a single
           mount-time load), so this remains its only error surface. -->
      @if (activeTab() === 'tuning' && store.error(); as message) {
        <span actions class="stale" role="status">{{ message }}</span>
      }
    </sb-section-head>

    <sb-tab-bar [tabs]="tabs" [active]="activeTab()" (activeChange)="goToTab($event)" />

    @switch (activeTab()) {
      <!-- -- performance ---------------------------------------------- -->
      @case ('performance') {
        <h2 class="section">Snapshot</h2>

        <!-- v85 D39 (R9-03) fix round 1. The KPI row used to sit inside the
             sb-async below (gated on performanceAsync alone), but five of
             its six tiles -- Total R, R per month, Sharpe (R), Max drawdown
             (R), Profit factor -- read snapshot()/riskMetrics(), not
             performance(); only Win rate does. sb-async's error branch
             replaces its ENTIRE projected content, so a /performance-only
             failure was blanking all six tiles, including the five that had
             nothing to do with it -- the exact "one fetch's failure blanks
             another fetch's valid data" bug SR50/SR55 already guard against
             for the panels below. This row gets its own sb-async, gated on
             kpiAsync (see its doc comment on the class): a combined
             AsyncInputs that only raises an error banner when BOTH
             performance and snapshot have failed. Each tile already renders
             its own em dash when its own source is null (sb-stat-tile), so
             a single failed fetch degrades only the tiles it actually
             backs; risk failures degrade the same way already (silently,
             like exitQuality -- see the store's own comment), independent
             of both. -->
        <sb-async
          [loading]="kpiAsync().loading"
          [error]="kpiAsync().error"
          [empty]="kpiAsync().empty"
          [staleAsOf]="kpiAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades in this range"
          [skeletonRows]="1"
          [skeletonCols]="6"
          (retry)="store.load()"
        >
          <div class="kpi-row">
            @for (tile of kpiTiles(); track tile.label) {
              <sb-stat-tile [label]="tile.label" [value]="tile.value" [sample]="tile.sample" />
            }
          </div>
        </sb-async>

        <!-- v85 D39 (R9-04). Equity | Drawdown share one fetch (R9-01) --
             the toggle swaps which field of the same points is plotted,
             never refetches. The range picker re-requests performance,
             snapshot, journal AND this curve together (one from/to scope);
             the strategy picker narrows only the curve, which is the one
             panel the /performance endpoint itself has no strategy
             parameter for. -->
        <sb-control-bar>
          <sb-date-range
            filters
            [from]="store.rangeFrom()"
            [to]="store.rangeTo()"
            (changed)="onRangeChange($event)"
          />
          <sb-select
            scope
            class="strategy"
            placeholder="Any strategy"
            [value]="store.equityCurveStrategy() ?? ''"
            (valueChange)="onEquityStrategy($event)"
            [options]="strategyOptions()"
          />
        </sb-control-bar>

        <sb-async
          [loading]="equityAsync().loading"
          [error]="equityAsync().error"
          [empty]="equityAsync().empty"
          [staleAsOf]="equityAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades in this range"
          [skeletonRows]="3"
          [skeletonCols]="4"
          (retry)="store.load()"
        >
          <div class="panels register-presentation">
            <sb-panel heading="Equity">
              <sb-segmented
                class="equity-toggle"
                label="Chart"
                [options]="equityViewOptions"
                [value]="store.equityCurveView()"
                (valueChange)="onEquityView($event)"
              />
              <div class="equity">
                <!-- Per panel, not global (D30): the bar date the equity
                     curve was computed from -- the KPI row above has no
                     equivalent single date, only a range. -->
                <sb-freshness [at]="store.equityCurveAsOf()" />
                <sb-line-chart [series]="store.activeEquitySeries()" [valueFormat]="fmtR" />
              </div>
            </sb-panel>

            <sb-panel heading="Win / loss">
              <div class="winloss">
                <sb-donut [slices]="store.winLossSlices()" />
                <dl>
                  <div><dt>Avg win</dt><dd class="num pos">{{ fmtR(store.avgWinR()) }}</dd></div>
                  <div><dt>Avg loss</dt><dd class="num neg">{{ fmtR(store.avgLossR()) }}</dd></div>
                </dl>
              </div>
            </sb-panel>
          </div>
        </sb-async>

        <!-- v85 D40 (R9-02/R9-05). One sb-segmented drives both panels --
             the strategy table's sort order AND the horizon bars' values
             read the same measure() signal, so there is exactly one place
             "ExpR vs total R" gets decided, not two that could disagree. -->
        <sb-async
          [loading]="strategyAggAsync().loading"
          [error]="strategyAggAsync().error"
          [empty]="strategyAggAsync().empty"
          [staleAsOf]="strategyAggAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades in this range"
          [skeletonRows]="4"
          [skeletonCols]="3"
          (retry)="store.load()"
        >
          <sb-segmented
            class="measure-toggle"
            label="Measure"
            [options]="measureViewOptions"
            [value]="measure()"
            (valueChange)="setMeasure($event)"
          />
          <div class="panels register-presentation">
            <sb-panel heading="By strategy" [flush]="true">
              <sb-data-table
                [rows]="sortedStrategyAgg()"
                [columns]="strategyAggColumns()"
                [visible]="strategyAggVisible"
                [rowKey]="strategyRowKey"
                [rowClass]="strategyRowClass"
                [emptyState]="strategyAggEmptyState"
              />
            </sb-panel>

            <sb-panel heading="By horizon">
              <div class="horizon-bars">
                @for (row of store.horizonAgg(); track row.key) {
                  <div class="horizon-row" [class.neg]="(measureValue(row) ?? 0) < 0">
                    <span class="horizon-key">{{ row.key }}</span>
                    <sb-magnitude [value]="measureValue(row)" [max]="horizonMax()" />
                    <span class="horizon-value num">{{ fmtMeasure(row) }}</span>
                    <span class="horizon-n num">N={{ row.n }}</span>
                  </div>
                }
              </div>
            </sb-panel>
          </div>
        </sb-async>

        <sb-async
          [loading]="performanceAsync().loading"
          [error]="performanceAsync().error"
          [empty]="performanceAsync().empty"
          [staleAsOf]="performanceAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades in this range"
          [skeletonRows]="5"
          [skeletonCols]="3"
          (retry)="store.load()"
        >
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

          <!-- v54 D1: this is the summary strip -- "how am I doing?", hero
               figures -- so it overrides the workspace's instrument default
               back to presentation. Both Snapshot panels-divs get the class
               (this one and Risk-adjusted/Streaks below): together they are
               the strip; everything past "Distributions" is tables/charts
               and stays on the instrument default from the host. -->
          <div class="panels register-presentation">
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
        </sb-async>

        <!-- SR50. Everything below comes from GET /analytics/snapshot, a
             separate fetch from 'performance' above — its own sb-async so a
             snapshot failure cannot blank the record/overall panels. -->
        <sb-async
          [loading]="snapshotAsync().loading"
          [error]="snapshotAsync().error"
          [empty]="snapshotAsync().empty"
          [staleAsOf]="snapshotAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades in this range"
          [skeletonRows]="4"
          [skeletonCols]="3"
          (retry)="store.load()"
        >
          <!-- Second half of the summary strip -- see the comment above the
               Record/Overall panels-div. -->
          <div class="panels register-presentation">
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
          </div>
        </sb-async>

        <!-- Distributions through "By segment" — same 'performance' fetch as
             the Snapshot section above, split into its own sb-async only
             because the Journal panel (a third, independent fetch) sits
             between this block and the by-confidence/by-dimension tables
             further down; the DOM order is not being restructured. -->
        <sb-async
          [loading]="performanceAsync().loading"
          [error]="performanceAsync().error"
          [empty]="performanceAsync().empty"
          [staleAsOf]="performanceAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades in this range"
          [skeletonRows]="8"
          [skeletonCols]="6"
          (retry)="store.load()"
        >
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
        </sb-async>

        <!-- v85 D41 (R9-06), combined into ONE disclosure (previously three
             separate <details class="breakdowns">, each with its own
             "Breakdowns" toggle stacked on the page -- reported back as
             confusing duplication). Every binding/computed below is
             untouched from where it used to sit; only the toggle boundaries
             changed. The band is a preference (spec's own convention for
             state whose only writer is this browser), collapsed by default
             so the first screen is the KPI row and the equity curve, not
             thirteen histograms.

             The <details>/<summary> toggle itself sits OUTSIDE every
             sb-async inside it, deliberately -- an early version put the
             whole element inside performanceAsync's own sb-async, which
             made the Journal section (its own fetch, its own emptiness,
             normally reachable even with zero closed trades) disappear
             along with the histograms the moment performanceAsync went
             empty. Each of the three pieces below keeps its OWN sb-async,
             exactly as before the merge; only the outer toggle became one
             element instead of three. -->
        <details
          class="breakdowns"
          [open]="breakdownsOpen()"
          (toggle)="onBreakdownsToggle($any($event.target).open)"
        >
          <summary>Breakdowns</summary>

          <sb-async
            [loading]="performanceAsync().loading"
            [error]="performanceAsync().error"
            [empty]="performanceAsync().empty"
            [staleAsOf]="performanceAsync().staleAsOf"
            emptyReason="measured-zero"
            emptyTitle="No closed trades in this range"
            [skeletonRows]="6"
            [skeletonCols]="2"
          >
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

          <div class="panels">
            <sb-panel heading="By holding period">
              <sb-histogram
                [bins]="store.holdingPeriodHistogram()"
                [max]="100"
                [referenceLine]="store.derived().win_rate"
              />
            </sb-panel>

            <sb-panel heading="By month">
              @if (store.monthHistogram().length) {
                <sb-histogram [bins]="store.monthHistogram()" />
              } @else {
                <p class="stale">No months with closed trades.</p>
              }
            </sb-panel>
          </div>

          <!-- Both R-multiple-framed, so paired rather than each on its own
               row -- the all-time one used to stand alone outside .panels
               entirely, leaving By planned R:R as the one panel with no
               partner and empty space beside it. -->
          <div class="panels">
            @if (store.rMultipleBins().length) {
              <sb-panel heading="R-multiple distribution (all-time)">
                <!-- Bars, not a pie and not a line: this is a distribution, and
                     the shape IS the finding -- a healthy edge is a cluster of
                     small losses with a tail of larger wins. -->
                <sb-histogram [bins]="store.rMultipleBins()" />
              </sb-panel>
            }
            <sb-panel heading="By planned R:R">
              <sb-histogram [bins]="store.riskRewardHistogram()" [max]="100" [referenceLine]="store.derived().win_rate" />
            </sb-panel>
          </div>

          <h2 class="section">By segment</h2>
          <div class="panels">
            <sb-panel heading="By direction">
              <sb-histogram [bins]="store.directionHistogram()" [max]="100" [referenceLine]="store.winRate()" />
            </sb-panel>
            <sb-panel heading="By day of week">
              <sb-histogram [bins]="store.dowHistogram()" [max]="100" [referenceLine]="store.winRate()" />
            </sb-panel>
          </div>

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
          </sb-async>

          <!-- SR55. NOT a rebuilt Journal page: spec v14 Decision 4 collapsed
               that deliberately. The digest and lessons are analytics and live
               here; a single trade's excursions live beside the note that
               explains them, on the detail view. Its own sb-async: the journal
               lives in its own store/module with its own empty message ("no
               entries yet" vs "no closed trades"), and a failed read here
               must not touch the tables around it -- nor may performanceAsync's
               OWN emptiness hide it, which is exactly why this sb-async, and
               the <details> toggle around it, sit at the same level rather
               than one nested inside the other. -->
          <sb-async
            [loading]="journalAsync().loading"
            [error]="journalAsync().error"
            [empty]="journalAsync().empty"
            [staleAsOf]="journalAsync().staleAsOf"
            emptyReason="measured-zero"
            emptyTitle="No journal entries yet"
            emptyHint="They are written when a trade closes."
            [skeletonRows]="3"
            [skeletonCols]="1"
            (retry)="store.load()"
          >
            <sb-panel heading="Journal">
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
            </sb-panel>
          </sb-async>

          <sb-async
            [loading]="performanceAsync().loading"
            [error]="performanceAsync().error"
            [empty]="performanceAsync().empty"
            [staleAsOf]="performanceAsync().staleAsOf"
            emptyReason="measured-zero"
            emptyTitle="No closed trades in this range"
            [skeletonRows]="5"
            [skeletonCols]="6"
          >
          <sb-panel heading="By confidence level" [flush]="true">
            <!-- No [pagination] here, deliberately (2026-09-14): there are
                 exactly 5 rows (Lv1-5), a fixed set that will never grow, so
                 DataTable's own filler-row padding (data-table.ts's
                 fillerRows, which pads a short page out to the preference's
                 25-per-page default) was rendering 20 empty rows below Lv5
                 for nothing -- there is no second page this table could
                 ever need to look consistent WITH. -->
            <sb-data-table
              [rows]="confidencePage.visible()"
              [columns]="confidenceColumns()"
              [visible]="confidenceKeys"
              [rowKey]="confidenceKey"
              [emptyState]="confidenceEmpty"
            />
          </sb-panel>
          </sb-async>
        </details>

        <sb-exit-quality [data]="store.exitQuality()" />

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

        <sb-async
          [loading]="strategiesAsync().loading"
          [error]="strategiesAsync().error"
          [empty]="strategiesAsync().empty"
          [staleAsOf]="strategiesAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No strategy has a closed trade in this range"
          [skeletonRows]="8"
          [skeletonCols]="6"
          (retry)="store.load()"
        >
          <sb-panel heading="Strategy registry" [flush]="true">
            <p class="panel-subtitle">out-of-sample validation status per strategy</p>
            <sb-data-table
              [rows]="strategyPage.visible()"
              [columns]="strategyColumns()"
              [visible]="strategyKeys"
              [rowKey]="strategyKey"
              [emptyState]="strategyEmpty"
              [pagination]="strategyPage.pageSpec()"
              [showPerPage]="true"
              (pageChange)="strategyPage.setPage($event)"
              (perPageChange)="onPerPage('strategy', $event)"
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
                          <td class="num cell" [attr.data-heat-cell]="true" [class.thin]="heatWithheld(strategy, horizon)" [style.--heat]="heat(strategy, horizon)">
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
          <sb-strategy-contribution [rows]="store.strategyContribution()" />
        </sb-async>
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

        <sb-async
          [loading]="calibrationAsync().loading"
          [error]="calibrationAsync().error"
          [empty]="calibrationAsync().empty"
          [staleAsOf]="calibrationAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No closed trades to calibrate against"
          [skeletonRows]="8"
          [skeletonCols]="6"
          (retry)="store.load()"
        >
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
              [emptyState]="decileEmpty"
              [pagination]="decilePage.pageSpec()"
              [showPerPage]="true"
              (pageChange)="decilePage.setPage($event)"
              (perPageChange)="onPerPage('decile', $event)"
            />
          </sb-panel>

          <sb-panel heading="Confidence-level calibration" [flush]="true">
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
              [emptyState]="tierEmpty"
              [pagination]="tierPage.pageSpec()"
              [showPerPage]="true"
              (pageChange)="tierPage.setPage($event)"
              (perPageChange)="onPerPage('tier', $event)"
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
              [emptyState]="driftEmpty"
              [pagination]="driftPage.pageSpec()"
              [showPerPage]="true"
              (pageChange)="driftPage.setPage($event)"
              (perPageChange)="onPerPage('drift', $event)"
            />
          </sb-panel>
        </sb-async>
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
              [showPerPage]="true"
              (pageChange)="gridPage.setPage($event)"
              (perPageChange)="onPerPage('grid', $event)"
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

        <sb-async
          [loading]="plansAsync().loading"
          [error]="plansAsync().error"
          [empty]="plansAsync().empty"
          [staleAsOf]="plansAsync().staleAsOf"
          emptyReason="measured-zero"
          emptyTitle="No plans posted yet"
          [skeletonRows]="6"
          [skeletonCols]="4"
          (retry)="store.load()"
        >
          <sb-panel heading="Lifecycle funnel">
            @if (store.funnelChart().length) {
              <sb-histogram [bins]="store.funnelChart()" />
              <p class="series-note">{{ store.inFlight() }} currently in flight (not counted above).</p>
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
              }
            </sb-panel>
          </div>

          <sb-panel heading="Tier distribution">
            @if (store.tierChart().length) {
              <sb-histogram [bins]="store.tierChart()" />
            }
          </sb-panel>
        </sb-async>
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

    /* Two even columns -- the uneven 2fr/1fr split this used to be left one
       lone panel (Planned R:R) sitting in the wide column with the narrow
       one empty beside it, which read as leftover dead space rather than a
       deliberate layout. Stacks to one column below 1000px, same
       breakpoint the rest of this page already uses. */
    .panels {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: var(--space-14);
      align-items: start;
    }
    @media (max-width: 1000px) {
      .panels { grid-template-columns: 1fr; }
    }

    /* The six-tile KPI row (v85 D39) -- same auto-fit tile grid as the Risk
       workspace's own institutional-metrics row (.metric-grid there). */
    .kpi-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: var(--space-14);
      margin-bottom: var(--space-14);
    }

    /* -- equity curve and win/loss (v85 D39, R9-04) -- */
    .equity-toggle { margin: var(--space-8) 0; }
    .equity { min-width: 0; }
    .winloss { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-14); }
    .winloss dl { display: grid; gap: var(--space-4); }
    .winloss div { display: flex; justify-content: space-between; gap: var(--space-10); }
    .winloss dt { color: var(--text-secondary); }
    .winloss .pos { color: var(--pos); }
    .winloss .neg { color: var(--neg); }

    /* -- strategy table and horizon bars (v85 D40, R9-05) -- */
    .measure-toggle { margin-bottom: var(--space-10); }
    /* Badge rail: a left border plus the badge word already in the cell's
       own text (spec's second-cue rule) -- ::ng-deep reaches DataTable's
       own <tr>, which this component's scoped styles cannot select
       otherwise. */
    :host ::ng-deep tr.badge-validated td:first-child { border-left: 3px solid var(--quality-5); }
    :host ::ng-deep tr.badge-weak td:first-child { border-left: 3px solid var(--quality-2); }
    :host ::ng-deep tr.thin { opacity: 0.7; }
    .horizon-bars { display: grid; gap: var(--space-10); }
    .horizon-row {
      display: grid;
      grid-template-columns: 40px 1fr auto auto;
      align-items: center;
      gap: var(--space-8);
      font-size: var(--text-table);
    }
    .horizon-key { color: var(--text-secondary); }
    .horizon-value { color: var(--pos); }
    .horizon-row.neg .horizon-value { color: var(--neg); }
    .horizon-n { color: var(--text-faint); font-size: var(--text-chip); }

    /* -- Breakdowns band (v85 D41, R9-06) -- */
    .breakdowns { margin: var(--space-14) 0; }
    /* Direct children (the histogram .panels rows, Journal, By confidence
       level, By segment's own h2) have no gap of their own -- <details> is
       plain block flow, not a flex/grid parent with a shared gap -- so
       spacing between them depended entirely on incidental margins some
       happened to carry and others didn't (Journal's own content padding
       gave it 14px above and below; two adjacent empty sb-async states sat
       flush with none). One rule, applied uniformly, reads as either
       "consistent breathing room" or "redundant space" depending which pair
       you were looking at before this existed. */
    .breakdowns > * + * { margin-top: var(--space-14); }
    .breakdowns summary {
      cursor: pointer;
      padding: var(--space-8) 0;
      color: var(--text-secondary);
      font-size: var(--text-table);
      font-weight: 600;
      list-style: none;
    }
    .breakdowns summary::-webkit-details-marker { display: none; }
    .breakdowns summary::before { content: '▸ '; }
    .breakdowns[open] summary::before { content: '▾ '; }
    .breakdowns summary:hover { color: var(--text); }

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
    /* A number long enough to wrap a summary row (Overall/Streaks) grows
       that one row taller than its neighbours -- ellipsis plus a smaller
       size keeps it on one line instead (2026-09-14), the same fix
       calendar.ts applies to its own info-panel cards. min-width: 0 is
       needed on a flex item (dl > div, above) before text-overflow does
       anything at all. */
    dd.num {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: var(--text-chip);
    }
    /* Reaches inside sb-metric-chip's own encapsulated styles -- this
       component's scoped styles cannot select .value otherwise (same
       ::ng-deep reasoning as the DataTable row rules above). */
    :host ::ng-deep .panels sb-metric-chip .value {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: var(--text-table);
    }

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
  private readonly preferences = inject(PreferencesStore);
  private readonly perPageSignals = new Map<string, WritableSignal<number>>();
  private perPageFor(table: string) { let current = this.perPageSignals.get(table); if (!current) { current = signal(readTablePerPage(this.preferences.values(), 'analytics-' + table)); this.perPageSignals.set(table, current); } return current; }
  protected onPerPage(table: string, value: number): void { this.perPageFor(table).set(value); this.preferences.update((prefs) => writeTablePerPage(prefs, 'analytics-' + table, value)); }

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

  /* -- per-panel async state --------------------------------------------
   * Three independent fetches back the Performance tab (performance,
   * snapshot, journal — see analytics.store.ts loadPerformance), so a
   * failed snapshot must not blank the equity curve or vice versa. Each
   * gets its own AsyncInputs rather than one wrapper around the page. */

  protected readonly performanceAsync = computed(() =>
    asyncInputs(
      { data: this.store.performance, loading: this.store.loading, error: this.store.error },
      { isEmpty: () => this.store.totals().total === 0 },
    ),
  );

  protected readonly snapshotAsync = computed(() =>
    asyncInputs(
      {
        data: this.store.snapshot,
        loading: this.store.loading,
        error: this.store.snapshotError,
      },
      { isEmpty: () => this.store.totals().total === 0 },
    ),
  );

  /**
   * v85 D39 (R9-03) fix round 1 -- the KPI row's own gate, combining the two
   * fetches its six tiles actually depend on (`performanceAsync` for Win
   * rate; `snapshotAsync` for Total R, R per month, Profit factor -- Sharpe
   * (R)/Max drawdown (R) come from `riskMetrics()`, which degrades silently
   * with no error state of its own, same as `exitQuality`).
   *
   * `error` only fires when BOTH have failed: either one alone still leaves
   * real data for the tiles it backs, and blanking those over an unrelated
   * fetch's failure is the exact bug this fix exists to remove. `loading`
   * doesn't need the same guard -- both sources share the one `store.loading`
   * flag, so they are never out of step with each other. `staleAsOf` takes
   * whichever source has one (a background refresh failing on data already
   * on screen is worth flagging even if only one side of the row is stale).
   * `empty` is always false: a KPI row has no meaningful "measured zero" of
   * its own distinct from its tiles' individual em dashes.
   */
  protected readonly kpiAsync = computed<AsyncInputs>(() => {
    const perf = this.performanceAsync();
    const snap = this.snapshotAsync();
    return {
      loading: perf.loading && snap.loading,
      error: perf.error && snap.error ? perf.error : null,
      empty: false,
      staleAsOf: perf.staleAsOf ?? snap.staleAsOf,
    };
  });

  /** v85 D39 (R9-04). No dedicated error field -- like `exitQuality`/
   *  `riskMetrics` above, a failed fetch degrades silently (an empty
   *  panel), never a warning about the rest of the tab. */
  protected readonly equityAsync = computed<AsyncInputs>(() =>
    asyncInputs(
      { data: this.store.equityCurve, loading: this.store.loading, error: () => null },
      { isEmpty: () => this.store.equityCurveEmpty() },
    ),
  );

  protected readonly equityViewOptions: SegmentOption[] = [
    { value: 'equity', label: 'Equity' },
    { value: 'drawdown', label: 'Drawdown' },
  ];

  protected readonly fmtR = rMultiple;

  protected onRangeChange(range: { from: string | null; to: string | null }): void {
    this.store.setRange(range.from, range.to);
  }

  protected onEquityStrategy(strategy: string): void {
    this.store.setEquityCurveStrategy(strategy || null);
  }

  protected onEquityView(view: string): void {
    this.store.setEquityCurveView(view === 'drawdown' ? 'drawdown' : 'equity');
  }

  /* -- v85 D40 (R9-05): strategy table and horizon bars, one toggle -----
   *
   * The measure is a preference, not component state -- persisted through
   * PreferencesStore so it survives a reload, same convention as every
   * other SR12-onward flat key. Read once at construction: this is the one
   * piece of state whose only writer is this browser (PreferencesStore's
   * own doc comment), so re-reading it later could only overwrite what the
   * reader just chose with what they chose a moment earlier. */

  protected readonly measure = signal<'exp_r' | 'total_r'>(
    this.preferences.values()['analyticsMeasure'] === 'total_r' ? 'total_r' : 'exp_r',
  );

  protected readonly measureLabel = computed(() => (this.measure() === 'total_r' ? 'Total R' : 'ExpR'));

  protected setMeasure(value: string): void {
    const measure = value === 'total_r' ? 'total_r' : 'exp_r';
    this.measure.set(measure);
    this.preferences.update((prefs) => ({ ...prefs, analyticsMeasure: measure }));
  }

  protected readonly measureViewOptions: SegmentOption[] = [
    { value: 'exp_r', label: 'ExpR' },
    { value: 'total_r', label: 'Total R' },
  ];

  /** Null-safe: a row with no computable value for the active measure
   *  sorts last and formats as an em dash, never a false zero. */
  protected measureValue(row: AnalyticsByDimensionRow): number | null {
    return this.measure() === 'total_r' ? row.total_r : row.exp_r;
  }

  protected fmtMeasure(row: AnalyticsByDimensionRow): string {
    const value = this.measureValue(row);
    return this.measure() === 'total_r' ? rMultiple(value) : expectancy(value);
  }

  /** Descending: the strategy the active measure rates best leads. A null
   *  value sorts to the bottom regardless of direction -- "unmeasured" is
   *  not meaningfully better or worse than a real number. */
  protected readonly sortedStrategyAgg = computed(() => {
    const rows = [...this.store.strategyAgg()];
    return rows.sort((a, b) => {
      const av = this.measureValue(a);
      const bv = this.measureValue(b);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      return bv - av;
    });
  });

  /** Badge rail plus a thin-sample flag (spec's second-cue rule -- colour
   *  alone never carries state) -- MIN_SAMPLE_N, the same threshold
   *  sb-stat-tile uses. */
  protected readonly strategyRowClass = (row: AnalyticsByDimensionRow): string | null => {
    const classes: string[] = [];
    if (row.badge) classes.push(`badge-${row.badge.toLowerCase()}`);
    if (row.n < MIN_SAMPLE_N) classes.push('thin');
    return classes.length ? classes.join(' ') : null;
  };

  protected readonly strategyRowKey = (row: AnalyticsByDimensionRow) => row.key;

  protected readonly strategyAggColumns = computed<ColumnDef<AnalyticsByDimensionRow>[]>(() => [
    {
      key: 'key', header: 'Strategy',
      value: (row) => (row.badge ? `${row.key} — ${row.badge}` : row.key),
    },
    { key: 'value', header: this.measureLabel(), numeric: true, value: (row) => this.fmtMeasure(row) },
    { key: 'n', header: 'N', numeric: true, value: (row) => count(row.n) },
  ]);

  protected readonly strategyAggVisible = ['key', 'value', 'n'];

  protected readonly strategyAggEmptyState = { title: 'No closed trades', hint: 'Nothing to group yet.' };

  /** No dedicated error field: `/by-dimension` degrades silently, same as
   *  `exitQuality`/`riskMetrics` above -- and `strategyAgg`/`horizonAgg`
   *  default to `[]` rather than `null`, so "not yet fetched" and "fetched,
   *  nothing closed" are told apart by `store.loading` instead of
   *  `asyncInputs`' usual has-data check. */
  protected readonly strategyAggAsync = computed<AsyncInputs>(() => {
    const empty = this.store.strategyAgg().length === 0 && this.store.horizonAgg().length === 0;
    return {
      loading: this.store.loading() && empty,
      error: null,
      empty: !this.store.loading() && empty,
      staleAsOf: null,
    };
  });

  /** The largest magnitude across all horizons for the active measure --
   *  `sb-magnitude`'s own scale, so no single bar's width depends on
   *  anything but the whole row set it is being compared against. */
  protected readonly horizonMax = computed(() => {
    const values = this.store.horizonAgg()
      .map((row) => this.measureValue(row))
      .filter((v): v is number => v !== null)
      .map(Math.abs);
    return values.length ? Math.max(...values) : 1;
  });

  /* -- v85 D41 (R9-06): the Breakdowns band -----------------------------
   *
   * Same convention as `measure` above: a preference, not component state,
   * read once at construction. Collapsed by default so the first screen a
   * reader sees is the KPI row and the equity curve, not thirteen
   * histograms below the fold. One `<details class="breakdowns">` on the
   * Performance tab binds this signal -- it used to be three separate
   * `<details>` sharing it (reading as one toggle for what looked like
   * three unrelated "Breakdowns" sections stacked on the page), merged into
   * one element once the histograms, the journal digest (its own nested
   * sb-async: a genuinely separate fetch) and the confidence-level table
   * all landed inside it.
   */
  protected readonly breakdownsOpen = signal<boolean>(
    this.preferences.values()['analyticsBreakdownsOpen'] === true,
  );

  protected onBreakdownsToggle(open: boolean): void {
    this.breakdownsOpen.set(open);
    this.preferences.update((prefs) => ({ ...prefs, analyticsBreakdownsOpen: open }));
  }

  protected readonly journalAsync = computed(() =>
    asyncInputs(
      { data: this.store.journal, loading: this.store.loading, error: this.store.journalError },
      { isEmpty: (data) => data.digest.length === 0 && data.lessons.length === 0 },
    ),
  );

  protected readonly strategiesAsync = computed(() =>
    asyncInputs(
      { data: this.store.strategies, loading: this.store.loading, error: this.store.error },
      { isEmpty: (data) => data.strategies.length === 0 },
    ),
  );

  protected readonly calibrationAsync = computed(() =>
    asyncInputs(
      { data: this.store.calibration, loading: this.store.loading, error: this.store.error },
      {
        isEmpty: (data) =>
          data.deciles.length === 0 && data.levels.length === 0 && data.drift.length === 0,
      },
    ),
  );

  protected readonly plansAsync = computed(() =>
    asyncInputs(
      { data: this.store.plans, loading: this.store.loading, error: this.store.error },
      { isEmpty: (data) => data.funnel.posted === 0 },
    ),
  );

  /* -- formatters (shared with the column declarations) ---------------- */

  protected readonly fmtRate = rate;
  protected readonly fmtDateTime = dateTime;

  protected fmtExpectancy(value: number | null): string {
    return value === null ? ABSENT : `${expectancy(value)}R`;
  }

  protected fmtCount(value: number | null): string {
    return value === null ? ABSENT : String(value);
  }

  /** An R total (Total R, R per month) -- signed, since both can go
   *  negative, three decimals for the same reason `fmtExpectancy` uses
   *  three: a fraction of a risk unit rounds to the same number at two. */
  private fmtTotalR(value: number | null): string {
    return value === null ? ABSENT : `${signed(value, 3)}R`;
  }

  /** Sharpe (R) -- unsigned formatting, matching the Risk workspace's own
   *  `fmtRatio` for the identical figure (v85 D37/D39): a plain ratio, no
   *  unit. Not `fmtTotalR`'s signed style -- that one exists to tell a
   *  P&L gain from a loss without the colour; a Sharpe ratio is not one. */
  private fmtSharpeR(value: number | null): string {
    return value === null ? ABSENT : value.toFixed(2);
  }

  /** Max drawdown (R) -- matches the Risk workspace's own `fmtDrawdownR`
   *  (v85 D37/D39): the server always reports this positive (a cost of the
   *  track record), so no sign is added here either. */
  private fmtMaxDrawdownR(value: number | null): string {
    return value === null ? ABSENT : `${value.toFixed(2)}R`;
  }

  /** Profit factor -- matches `analytics.columns.ts`'s own
   *  `profit_factor` column formatter: two decimals, no unit, ABSENT
   *  (never 0) when there is no losing amount to divide by. */
  private fmtProfitFactor(value: number | null): string {
    return value === null ? ABSENT : value.toFixed(2);
  }

  /**
   * The six-tile KPI row (v85 D39) -- Total R, R per month, Sharpe (R),
   * Max drawdown (R), Win rate, Profit factor, in that exact order. Each
   * carries the sample it was actually computed from, never a shared/global
   * one (see the store's own comments on where each of the six -- and each
   * one's `n` -- actually comes from).
   */
  protected readonly kpiTiles = computed(() => [
    { label: 'Total R', value: this.fmtTotalR(this.store.totalR()), sample: this.store.totalRSample() },
    { label: 'R per month', value: this.fmtTotalR(this.store.rPerMonth()), sample: this.store.totalRSample() },
    { label: 'Sharpe (R)', value: this.fmtSharpeR(this.store.sharpeR()), sample: this.store.sharpeRSample() },
    { label: 'Max drawdown (R)', value: this.fmtMaxDrawdownR(this.store.maxDrawdownR()), sample: this.store.maxDrawdownRSample() },
    { label: 'Win rate', value: this.fmtRate(this.store.winRate()), sample: this.store.totals().closed },
    { label: 'Profit factor', value: this.fmtProfitFactor(this.store.profitFactor()), sample: this.store.profitFactorSample() },
  ]);

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

  protected readonly tierColumns = computed(() => TIER_COLUMNS(this.store.minCellN()));

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
  protected readonly tierKeys = allKeys(TIER_COLUMNS(0));
  protected readonly driftKeys = allKeys(DRIFT_COLUMNS);
  protected readonly gridKeys = allKeys(GRID_COLUMNS);
  protected readonly pastJobsKeys = allKeys(PAST_JOBS_COLUMNS);

  protected readonly strategyKey = (row: StrategyRow) => row.strategy;
  protected readonly strategyPage = createClientPage(() => this.store.strategyRows(), () => this.perPageFor('strategy')());
  protected readonly confidenceKey = (row: { level: number }) => String(row.level);
  protected readonly confidencePage = createClientPage(() => this.store.byConfidence(), () => this.perPageFor('confidence')());
  protected readonly decileKey = (row: { decile: string }) => row.decile;
  protected readonly decilePage = createClientPage(() => this.store.deciles(), () => this.perPageFor('decile')());
  protected readonly tierKey = (row: TierRow) => String(row.level);
  protected readonly tierPage = createClientPage(() => this.store.tiers(), () => this.perPageFor('tier')());
  protected readonly driftKey = (row: DriftRow) => row.strategy;
  protected readonly driftPage = createClientPage(() => this.store.drift(), () => this.perPageFor('drift')());
  protected readonly gridRowKey = (row: GridRow) => String(row.row_index);
  protected readonly gridPage = createClientPage(() => this.store.grid(), () => this.perPageFor('grid')());
  protected readonly pastJobRowKey = (row: JobSummary) => row.id;
  protected readonly pastJobsPage = createClientPage(() => this.store.pastJobs(), () => this.perPageFor('past-jobs')());
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
    breakdownColumns(this.store.breakdownLabel(), this.store.minCellN()),
  );
  protected readonly breakdownKeys = allKeys(breakdownColumns(''));
  protected readonly breakdownKey = (row: BreakdownRow) => row.key;
  protected readonly breakdownPage = createClientPage(() => this.store.breakdownRows(), () => this.perPageFor('breakdown')());

  protected readonly breakdownEmpty = computed(() => ({
    title: `Nothing grouped by ${this.store.breakdownLabel().toLowerCase()} yet`,
    hint: 'Groups appear once trades close against them.',
  }));

  protected onBreakdown(value: string): void {
    this.store.setBreakdown(value as BreakdownDimension);
    this.breakdownPage.setPage(1);
  }


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
    if (!cell || this.heatWithheld(strategy, horizon)) return 0;
    const rate = cell.win_rate;
    return rate === null ? 0 : Math.max(0, Math.min(1, rate / 100));
  }

  protected heatLabel(strategy: string, horizon: string): string {
    const cell = this.heatIndex().get(`${strategy}|${horizon}`);
    if (!cell || cell.win_rate === null) return ABSENT;
    if (this.heatWithheld(strategy, horizon)) return `n=${cell.n ?? 0}`;
    return `${cell.win_rate.toFixed(0)}% (${cell.n ?? 0})`;
  }

  protected heatWithheld(strategy: string, horizon: string): boolean {
    const cell = this.heatIndex().get(`${strategy}|${horizon}`);
    return rateOrWithheld(cell?.n ?? 0, cell?.win_rate, this.store.minCellN()).withheld;
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
    effect(() => this.store.setTab(this.activeTab(), false));
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
