import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { Histogram } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelHeader } from '../../../ui/panel-header';
import { MultiplePane, SmallMultiples } from '../../../ui/small-multiples';

/** Scoped edge monitoring above all-time validation evidence. */
@Component({selector:'sb-edge-tab',changeDetection:ChangeDetectionStrategy.OnPush,imports:[Panel,PanelHeader,LineChart,SmallMultiples,Histogram],template:`<div class="panels"><sb-panel><sb-panel-header title="Rolling win rate" [n]="store.scopeN()"/><sb-line-chart [series]="rollingWr()" [referenceLine]="performance()?.win_rate ?? null" [valueFormat]="pct"/></sb-panel><sb-panel><sb-panel-header title="Rolling ExpR" [n]="store.scopeN()"/><sb-line-chart [series]="rollingExpR()" [referenceLine]="0" [valueFormat]="r"/></sb-panel><sb-panel><sb-panel-header title="Strategy cumulative R" [n]="store.scopeN()"/><sb-small-multiples [panes]="strategyPanes()" [valueFormat]="r"/></sb-panel><sb-panel><sb-panel-header title="Calibration deciles" [allTime]="true"/><sb-histogram [bins]="decileBins()"/></sb-panel></div>`,styles:`.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}@media(max-width:800px){.panels{grid-template-columns:1fr}}`})
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
  readonly decileBins = computed(() => ((this.store.calibration()?.deciles ?? []) as { decile: string; win_rate: number | null }[])
    .filter((row) => row.win_rate !== null).map((row) => ({ label: row.decile, count: row.win_rate! })));
}
