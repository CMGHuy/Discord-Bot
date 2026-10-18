import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { LiveLossRow } from '../../../api/models';
import { AnalyticsStore, DriftRow } from '../../../stores/analytics.store';
import { DataTable } from '../../../ui/data-table/data-table';
import { EmptyState } from '../../../ui/data-table/data-table.types';
import { Histogram } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelHeader } from '../../../ui/panel-header';
import { MultiplePane, SmallMultiples } from '../../../ui/small-multiples';
import {
  allKeys,
  DRIFT_COLUMNS,
  LIVE_LOSS_COLUMNS,
  LIVE_LOSS_LOOKS_CAVEAT,
  LIVE_LOSS_MEANING,
  liveLossCountsLine,
  liveLossLabel,
  REGISTRY_CONTEXT_LABEL,
} from '../analytics.columns';

/** Scoped edge monitoring above all-time validation evidence; under it, the
 *  v164 live loss watch and the win-rate drift table it sits beside. */
@Component({
  selector: 'sb-edge-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, LineChart, SmallMultiples, Histogram, DataTable],
  template: `<div class="panels">
    <sb-panel><sb-panel-header title="Rolling win rate" [n]="store.scopeN()"/><sb-line-chart [series]="rollingWr()" [referenceLine]="performance()?.win_rate ?? null" [valueFormat]="pct"/></sb-panel>
    <sb-panel><sb-panel-header title="Rolling ExpR" [n]="store.scopeN()"/><sb-line-chart [series]="rollingExpR()" [referenceLine]="0" [valueFormat]="r"/></sb-panel>
    <sb-panel><sb-panel-header title="Strategy cumulative R" [n]="store.scopeN()"/><sb-small-multiples [panes]="strategyPanes()" [valueFormat]="r"/></sb-panel>
    <sb-panel><sb-panel-header title="Calibration deciles" [allTime]="true"/><sb-histogram [bins]="decileBins()"/></sb-panel>
    <sb-panel class="wide">
      <sb-panel-header title="Live loss watch" [hint]="liveLossHint"/>
      <p class="note">An alert means: {{ meaning }}.</p>
      <sb-data-table [rows]="store.liveLossWatch()" [columns]="liveLossColumns" [visible]="liveLossVisible" [rowKey]="liveLossKey" [emptyState]="liveLossEmpty"/>
      <p class="note">Registry columns: {{ contextLabel }}.</p>
      @if (store.liveLossWatch().length) { <p class="note">{{ countsLine() }}</p> }
      <p class="note">{{ caveat }}.</p>
    </sb-panel>
    <sb-panel class="wide">
      <sb-panel-header title="Win-rate drift" [allTime]="true" [hint]="driftHint"/>
      <sb-data-table [rows]="store.drift()" [columns]="driftColumns" [visible]="driftVisible" [rowKey]="driftKey" [emptyState]="driftEmpty"/>
    </sb-panel>
  </div>`,
  styles: `.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}.wide{grid-column:1/-1}.note{margin:var(--space-6) 0 0;color:var(--text-muted);font-size:var(--text-table)}@media(max-width:639px){.panels{grid-template-columns:1fr}}`,
})
export class EdgeTab {
  readonly store = inject(AnalyticsStore);
  readonly performance = computed(() => this.store.performance());
  readonly pct = (value: number) => `${value.toFixed(1)}%`;
  readonly r = (value: number) => `${value.toFixed(2)}R`;
  readonly rollingWr = computed<LineChartSeries[]>(() => [{ name: 'Win rate', points: (this.performance()?.rolling_wr ?? []).map((point) => ({ date: point.date, value: point.win_rate })) }]);
  readonly rollingExpR = computed<LineChartSeries[]>(() => [{ name: 'ExpR', points: (this.performance()?.rolling_exp_r ?? []).map((point) => ({ date: point.date, value: point.exp_r })) }]);
  readonly strategyPanes = computed<MultiplePane[]>(() =>
    Object.entries(this.store.strategies()?.cumulative ?? {}).map(([title, rows]) => ({
      title, series: [{ name: title, points: rows.map((point) => ({ date: point.date, value: point.cum_r })) }],
    })));
  // HistogramBin.count is otherwise always an integer observation count; a
  // calibration decile's win rate is a percentage borrowing that same bar,
  // so it must be rounded before display -- a screenshot pass once caught
  // an unrounded division (2/3 -> 66.66666...) overflowing the panel.
  readonly decileBins = computed(() => ((this.store.calibration()?.deciles ?? []) as { decile: string; win_rate: number | null }[])
    .filter((row) => row.win_rate !== null).map((row) => ({ label: row.decile, count: Math.round(row.win_rate! * 10) / 10 })));

  /* -- v164 D4: live loss watch ------------------------------------------ */
  readonly meaning = LIVE_LOSS_MEANING;
  readonly caveat = LIVE_LOSS_LOOKS_CAVEAT;
  readonly contextLabel = REGISTRY_CONTEXT_LABEL;
  readonly liveLossHint = 'Live trades opened on or after 2026-10-16 (Berlin date), both ledgers, manual closes included. Ignores the scope filter. Rows keep the server order: alerts first.';
  readonly liveLossColumns = LIVE_LOSS_COLUMNS;
  readonly liveLossVisible = allKeys(LIVE_LOSS_COLUMNS);
  readonly liveLossKey = (row: LiveLossRow) => liveLossLabel(row);
  readonly liveLossEmpty: EmptyState = {
    title: 'No live loss watch rows yet',
    hint: 'The analytics snapshot predates this table; a snapshot older than an hour is rebuilt on the next request.',
  };
  readonly countsLine = computed(() => liveLossCountsLine(this.store.liveLossCounts()));

  /* -- win-rate drift (badge_drift, unchanged; first rendered in v164) ---- */
  readonly driftHint = 'Live win rate against the out-of-sample win rate of validated registry rows (badge_drift).';
  readonly driftColumns = DRIFT_COLUMNS;
  readonly driftVisible = allKeys(DRIFT_COLUMNS);
  readonly driftKey = (row: DriftRow) => row.strategy;
  readonly driftEmpty: EmptyState = {
    title: 'No drift rows',
    hint: 'badge_drift reports only validated registry rows.',
  };
}
