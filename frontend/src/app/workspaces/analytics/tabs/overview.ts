import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { HistogramBucket } from '../../../api/models';
import { ConnectionStore } from '../../../stores/connection.store';
import { AnalyticsStore, RELOCATED_METRICS } from '../../../stores/analytics.store';
import { BarList } from '../../../ui/bar-list';
import { ColumnDef } from '../../../ui/data-table/data-table.types';
import { DataTable } from '../../../ui/data-table/data-table';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { ABSENT, money, num, pct as pctText, rMultiple, share, signed } from '../../../ui/format';
import { Histogram } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelHeader } from '../../../ui/panel-header';
import { PanelError } from '../../../ui/panel-error';
import { ShareBar, ShareSegment } from '../../../ui/share-bar';
import { StatTile } from '../../../ui/stat-tile';
import { alwaysMoney, inUnit, unitLabel } from '../../../ui/unit-format';

/** One KPI tile's resolved, pre-formatted content -- `StatTile` never formats. */
interface KpiTile {
  label: string;
  value: string | null;
  money: string | null;
  sample: number | null;
  trend: readonly number[] | null;
  hint?: string;
}

/** One relocated metric, resolved against the payload for the Outcome
 *  panel's `<dl>` and its Table view -- see `relocatedRows`' own comment for
 *  why `missing` and a real `null` are two different renders. */
interface RelocatedRow {
  key: string;
  label: string;
  text: string;
  missing: boolean;
}

type RBucketRow = HistogramBucket;
interface MonthRow {
  month: string;
  return_pct: number | null;
  pnl?: number;
  n: number;
}
interface OutcomeTableRow {
  metric: string;
  value: string;
}

/** Peak-to-current drawdown, the max over the series -- the same
 *  non-negative "distance below the running high" `drawdown_r` already
 *  carries per-point from the server, just computed here for `cum_pnl`
 *  (Max drawdown's money line), which has no server-side equivalent. */
function maxDrawdown(values: readonly number[]): number | null {
  if (!values.length) return null;
  let peak = values[0];
  let worst = 0;
  for (const value of values) {
    if (value > peak) peak = value;
    worst = Math.max(worst, peak - value);
  }
  return worst;
}

/** v94 Overview: one scoped read of the book, not another source of truth. */
@Component({
  selector: 'sb-overview-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    Panel, PanelHeader, PanelError, EmptyStateComponent, StatTile, LineChart,
    ShareBar, Histogram, BarList, DataTable, RouterLink,
  ],
  template: `
    <div class="kpis">@for (tile of kpiTiles(); track tile.label) {
      <sb-stat-tile [label]="tile.label" [value]="tile.value" [secondary]="tile.money"
        [sample]="tile.sample" [trend]="tile.trend" [hint]="tile.hint" />
    }</div>

    <div class="panels">
      <sb-panel>
        <sb-panel-header title="Equity" [n]="store.scopeN()" [total]="equityMoney()"
          hint="Cumulative {{ unitLabelText() }} per closed trade, ordered by close date. A day with no closes is not a flat day: the x-axis is the sequence of trades, dated." />
        @if (store.equityCurveError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('equityCurve')" />
        } @else if (!points().length) {
          <sb-empty-state title="No closed trades in this scope" reason="measured-zero" />
        } @else {
          <sb-line-chart [series]="equitySeries()" [referenceLine]="0" [valueFormat]="format" />
          <h4 class="pane-label">Drawdown</h4>
          <sb-line-chart [series]="drawdownSeries()" [valueFormat]="format" />
          @if (store.unit() === 'pct' && benchmarkSeries().length) {
            <p class="benchmark-note">SPY indexed to the range start, for context.</p>
          } @else if (store.unit() !== 'pct') {
            <p class="benchmark-note">SPY appears in % mode only — an R curve and a price index share no axis.</p>
          }
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="Outcome" [n]="store.scopeN()" [tableable]="true" [(tableOpen)]="outcomeTableOpen"
          hint="Win = TP1 touched. Average win and loss are means of the R-multiples on each side." />
        @if (store.performanceError(); as error) {
          <sb-panel-error [message]="error" (retry)="store.reload('performance')" />
        } @else {
          <sb-share-bar label="Outcome" [segments]="outcomeSegments()" />
          <dl class="pairs">
            <div><dt>Avg win</dt><dd>{{ avgWin() }}</dd></div>
            <div><dt>Avg loss</dt><dd>{{ avgLoss() }}</dd></div>
            <div><dt>Payoff</dt><dd>{{ payoff() }}</dd></div>
            <div><dt>Streaks</dt><dd>{{ streaksText() }}</dd></div>
            @for (row of relocatedRows(); track row.key) {
              <div [class.missing]="row.missing"><dt>{{ row.label }}</dt><dd>{{ row.text }}</dd></div>
            }
          </dl>
          @if (outcomeTableOpen()) {
            <sb-data-table [rows]="outcomeTableRows()" [columns]="outcomeColumns" [visible]="outcomeVisible" [rowKey]="outcomeRowKey" />
          }
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="R distribution" [n]="store.scopeN()" [tableable]="true" [(tableOpen)]="rTableOpen"
          hint="Every closed trade's realised R. The shape is the finding: a cluster of small losses with a tail of larger wins is a different book from a symmetric one." />
        <sb-histogram [bins]="rBins()" [isNegative]="negativeBin" />
        @if (rTableOpen()) {
          <sb-data-table [rows]="rRows()" [columns]="rColumns" [visible]="rVisible" [rowKey]="rRowKey" />
        }
      </sb-panel>

      <sb-panel>
        <sb-panel-header title="By month" [n]="store.scopeN()" [tableable]="true" [(tableOpen)]="monthTableOpen"
          hint="Realised result per calendar month of the scoped book. The day grid lives on the Calendar workspace." />
        <sb-bar-list [rows]="monthBars()" mode="signed" [format]="format" />
        @if (monthTableOpen()) {
          <sb-data-table [rows]="monthRows()" [columns]="monthColumns" [visible]="monthVisible" [rowKey]="monthRowKey" />
        }
        <a routerLink="/calendar">Open the calendar</a>
      </sb-panel>
    </div>
  `,
  styles: `
    :host { display: grid; gap: var(--space-20); }
    .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: var(--space-10); }
    .panels { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-14); }
    .pane-label { font-size: var(--text-chip); color: var(--text-secondary); margin: var(--space-10) 0 var(--space-4); }
    /* Named .benchmark-note, not .note (v54 precedent, trade-detail.ts):
       that name is a promoted sb-note callout composite -- this is an
       unrelated one-line caption, not a callout, and the shared name would
       be coincidence. */
    .benchmark-note { font-size: var(--text-chip); color: var(--text-faint); margin: var(--space-6) 0 0; }
    .pairs { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); gap: var(--space-8); margin: var(--space-10) 0 0; }
    .pairs dt { font-size: var(--text-micro); color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.1em; }
    .pairs dd { margin: var(--space-4) 0 0; color: var(--text); font-variant-numeric: tabular-nums; }
    .pairs .missing dd { color: var(--warn); font-style: italic; }
    @media (max-width: 639px) { .panels { grid-template-columns: 1fr; } }
  `,
})
export class OverviewTab {
  readonly store = inject(AnalyticsStore);
  private readonly connection = inject(ConnectionStore);

  readonly format = (value: number) =>
    inUnit({ r: value, pct: value, money: value }, this.store.unit(), this.connection.currency());

  protected readonly unitLabelText = computed(() => unitLabel(this.store.unit(), this.connection.currency()));

  readonly points = computed(() => this.store.equityCurve()?.points ?? []);

  readonly equityMoney = computed(() => {
    const last = this.points().at(-1);
    return last ? money(last.cum_pnl, this.connection.currency()) : null;
  });

  readonly equitySeries = computed<LineChartSeries[]>(() => [{
    name: 'Equity',
    points: this.points().map((p) => ({
      date: p.date,
      value: this.store.unit() === 'money' ? p.cum_pnl : this.store.unit() === 'pct' ? (p.cum_pct ?? 0) : p.cum_r,
    })),
  }]);
  readonly drawdownSeries = computed<LineChartSeries[]>(() => [{
    name: 'Drawdown',
    points: this.points().map((p) => ({ date: p.date, value: -p.drawdown_r })),
  }]);

  /** No producer emits this in production (B3's `spy_indexed` was dropped in
   *  `4ae117dc` and nothing replaced it, a previously-ruled defect) -- this
   *  reads the payload honestly and stays `[]` rather than fabricating a
   *  series, and the template's two-branch note never claims SPY is present
   *  when this is empty. */
  readonly benchmarkSeries = computed(() => this.store.equityCurve()?.benchmark?.spy_indexed ?? []);

  /** Last 30 `cum_r` deltas, not cumulative values -- a sparkline of the
   *  running total would just look like the equity chart it sits beside. */
  private readonly totalRTrend = computed<readonly number[] | null>(() => {
    const points = this.points();
    if (points.length < 2) return null;
    const deltas = points.slice(1).map((p, i) => p.cum_r - points[i].cum_r);
    const last30 = deltas.slice(-30);
    return last30.length ? last30 : null;
  });

  private readonly winRateTrend = computed<readonly number[] | null>(() => {
    const last30 = (this.store.performance()?.rolling_wr ?? []).slice(-30).map((row) => row.win_rate);
    return last30.length ? last30 : null;
  });

  readonly kpiTiles = computed<KpiTile[]>(() => {
    const performance = this.store.performance();
    const derived = performance?.derived ?? null;
    const points = this.points();
    const last = points.at(-1) ?? null;
    const equityCurve = this.store.equityCurve();
    const currency = this.connection.currency();
    const unit = this.store.unit();

    const tile = (
      label: string,
      r: number | null,
      pct: number | null,
      moneyValue: number | null,
      sample: number | null,
      trend: readonly number[] | null = null,
      hint?: string,
    ): KpiTile => ({
      label,
      value: inUnit({ r, pct, money: moneyValue }, unit, currency),
      money: alwaysMoney({ r, pct, money: moneyValue }, currency),
      sample,
      trend,
      hint,
    });

    // Win rate, profit factor and Sharpe are unitless (or already a fixed
    // percentage) — they have no R-multiple or money reading at all, so
    // routing them through the R/%/$ control-bar toggle produced nonsense
    // like "+3.50R" and "+3.50 €" for a profit factor. This helper renders
    // them the same way regardless of the selected unit, with no secondary
    // money line, per `AnalyticsDerivedMetrics.profit_factor`'s own doc
    // comment ("unitless like sharpe_ann/sortino_ann").
    const fixedTile = (
      label: string,
      formattedValue: string | null,
      sample: number | null,
      trend: readonly number[] | null = null,
      hint?: string,
    ): KpiTile => ({ label, value: formattedValue, money: null, sample, trend, hint });

    const expectancyN = performance?.expectancy_n ?? null;
    const expectancyMoney = last && expectancyN ? last.cum_pnl / expectancyN : null;

    const drawdownR = points.length ? Math.max(...points.map((p) => p.drawdown_r)) : null;
    const drawdownMoney = points.length ? maxDrawdown(points.map((p) => p.cum_pnl)) : null;

    const profitFactor = derived?.profit_factor ?? null;
    const sharpe = derived?.sharpe_ann ?? null;
    const winRate = performance?.win_rate ?? null;

    return [
      tile('Total R', last?.cum_r ?? null, derived?.total_return_pct ?? null, last?.cum_pnl ?? null,
        equityCurve?.points_n ?? null, this.totalRTrend()),
      tile('ExpR', performance?.expectancy_r ?? null, null, expectancyMoney, expectancyN),
      fixedTile('Win rate', share(winRate, 2), performance?.win_rate_n ?? null, this.winRateTrend()),
      fixedTile('Profit factor', num(profitFactor, 2), this.store.scopeN(), null,
        'Gross realised win ÷ gross realised loss.'),
      tile('Max drawdown', drawdownR, null, drawdownMoney, equityCurve?.points_n ?? null, null,
        'Largest peak-to-trough decline in the scope.'),
      fixedTile('Sharpe', signed(sharpe, 2), this.store.scopeN(), null, 'Annualised, from realised returns.'),
    ];
  });

  readonly outcomeSegments = computed<ShareSegment[]>(() => {
    const relocated = (this.store.performance()?.relocated ?? {}) as Record<string, unknown>;
    if (!('wins' in relocated) && !('losses' in relocated)) return [];
    const wins = typeof relocated['wins'] === 'number' ? relocated['wins'] : 0;
    const losses = typeof relocated['losses'] === 'number' ? relocated['losses'] : 0;
    return [{ label: 'Wins', count: wins, tone: 'pos' }, { label: 'Losses', count: losses, tone: 'neg' }];
  });

  readonly avgWin = computed(() => rMultiple(this.store.performance()?.derived?.avg_win_r ?? null));
  readonly avgLoss = computed(() => rMultiple(this.store.performance()?.derived?.avg_loss_r ?? null));
  readonly payoff = computed(() => num(this.store.performance()?.derived?.payoff_r ?? null, 2));
  readonly streaksText = computed(() => {
    const streaks = this.store.performance()?.streaks;
    if (!streaks) return ABSENT;
    return `Best win ${streaks.best_win_streak} · Worst loss ${streaks.worst_loss_streak}`;
  });

  /**
   * `RELOCATED_METRICS` resolved against the payload -- driving the render
   * off that one array (rather than six hand-written template lines) is
   * what makes a lost metric a visible defect instead of a card that
   * quietly stops appearing (the store's own rationale for the constant).
   *
   * A key **absent** from `relocated` is flagged `missing` -- the API
   * stopped sending it, spec 3's relocation promise broken. A key present
   * with value `null` is a real answer ("no data yet") and renders as an
   * ordinary em dash, not a flag. Returns `[]` before the first response
   * lands, so a still-loading tab does not flash six false "missing" rows.
   */
  readonly relocatedRows = computed<RelocatedRow[]>(() => {
    const performance = this.store.performance();
    if (!performance) return [];
    const relocated = performance.relocated as Record<string, unknown>;
    return RELOCATED_METRICS.map((metric) => {
      const present = metric.key in relocated;
      const raw = present ? relocated[metric.key] : undefined;
      const value = typeof raw === 'number' ? raw : null;
      const text = !present ? 'missing' : value === null ? ABSENT : `${value.toFixed(metric.decimals)}${metric.unit}`;
      return { key: metric.key, label: metric.label, text, missing: !present };
    });
  });

  readonly rBins = computed(() => (this.store.performance()?.distributions.r_multiples ?? [])
    .map((b) => ({ label: `${b.lo}R`, count: b.count })));
  readonly monthBars = computed(() => (this.store.performance()?.calendar ?? [])
    .map((m) => ({ label: m.month, value: m.return_pct, n: m.n })));
  readonly negativeBin = (bin: { label: string }) => bin.label.startsWith('-');

  /* -- Table views -- one signal per panel, local like the Gallery's
   * segmented-control pattern (`gallery.ts`'s `segmentValue`/`rangeValue`);
   * `store.tableOpen`/`setTableOpen` exist for cross-navigation persistence
   * but no tab reads them back yet, and this task's spec doesn't exercise
   * that round-trip, so this stays local rather than guessing at a
   * persistence contract nothing else has adopted. */
  protected readonly rTableOpen = signal(false);
  protected readonly monthTableOpen = signal(false);
  protected readonly outcomeTableOpen = signal(false);

  protected readonly rRows = computed<RBucketRow[]>(() => this.store.performance()?.distributions.r_multiples ?? []);
  protected readonly rColumns: ColumnDef<RBucketRow>[] = [
    { key: 'range', header: 'R range', value: (row) => `${row.lo}R to ${row.hi}R` },
    { key: 'count', header: 'Count', numeric: true, value: (row) => row.count },
  ];
  protected readonly rVisible = ['range', 'count'];
  protected readonly rRowKey = (row: RBucketRow) => `${row.lo}-${row.hi}`;

  protected readonly monthRows = computed<MonthRow[]>(() => this.store.performance()?.calendar ?? []);
  protected readonly monthColumns: ColumnDef<MonthRow>[] = [
    { key: 'month', header: 'Month', value: (row) => row.month },
    { key: 'return_pct', header: 'Return', numeric: true, value: (row) => pctText(row.return_pct) },
    { key: 'pnl', header: 'P&L', numeric: true, value: (row) => money(row.pnl ?? null, this.connection.currency()) },
    { key: 'n', header: 'N', numeric: true, value: (row) => row.n },
  ];
  protected readonly monthVisible = ['month', 'return_pct', 'pnl', 'n'];
  protected readonly monthRowKey = (row: MonthRow) => row.month;

  protected readonly outcomeTableRows = computed<OutcomeTableRow[]>(() => [
    { metric: 'Avg win', value: this.avgWin() },
    { metric: 'Avg loss', value: this.avgLoss() },
    { metric: 'Payoff', value: this.payoff() },
    { metric: 'Streaks', value: this.streaksText() },
    ...this.relocatedRows().map((row) => ({ metric: row.label, value: row.text })),
  ]);
  protected readonly outcomeColumns: ColumnDef<OutcomeTableRow>[] = [
    { key: 'metric', header: 'Metric', value: (row) => row.metric },
    { key: 'value', header: 'Value', value: (row) => row.value },
  ];
  protected readonly outcomeVisible = ['metric', 'value'];
  protected readonly outcomeRowKey = (row: OutcomeTableRow) => row.metric;
}
