import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { ConnectionStore } from '../../../stores/connection.store';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { BarList } from '../../../ui/bar-list';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { Histogram } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { LineChart, LineChartSeries } from '../../../ui/line-chart';
import { PanelHeader } from '../../../ui/panel-header';
import { ShareBar, ShareSegment } from '../../../ui/share-bar';
import { StatTile } from '../../../ui/stat-tile';
import { alwaysMoney, inUnit } from '../../../ui/unit-format';

/** v94 Overview: one scoped read of the book, not another source of truth. */
@Component({
  selector: 'sb-overview-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, EmptyStateComponent, StatTile, LineChart, ShareBar, Histogram, BarList],
  template: `
    <div class="kpis">@for (tile of kpiTiles(); track tile.label) {
      <sb-stat-tile [label]="tile.label" [value]="tile.value" [secondary]="tile.money" [sample]="tile.sample" />
    }</div>
    <div class="panels">
      <sb-panel><sb-panel-header title="Equity" [n]="store.scopeN()" hint="Cumulative realised result per closed trade." />
        @if (!points().length) { <sb-empty-state title="No closed trades in this scope" reason="measured-zero" /> }
        @else { <sb-line-chart [series]="equitySeries()" [referenceLine]="0" [valueFormat]="format" /><h3>Drawdown</h3><sb-line-chart [series]="drawdownSeries()" [valueFormat]="format" /> }
      </sb-panel>
      <sb-panel><sb-panel-header title="Outcome" [n]="store.scopeN()" hint="Wins and losses in the selected scope." /><sb-share-bar label="Outcome" [segments]="outcomes()" /></sb-panel>
      <sb-panel><sb-panel-header title="R distribution" [n]="store.scopeN()" />
        <sb-histogram [bins]="rBins()" [isNegative]="negativeBin" />
      </sb-panel>
      <sb-panel><sb-panel-header title="By month" [n]="store.scopeN()" />
        <sb-bar-list [rows]="monthBars()" mode="signed" [format]="format" />
      </sb-panel>
    </div>
  `,
  styles: `:host{display:grid;gap:var(--space-16)}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));gap:var(--space-10)}.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}h3{font-size:var(--text-chip);color:var(--text-secondary);margin:var(--space-12) 0 var(--space-4)}@media(max-width:800px){.panels{grid-template-columns:1fr}}`,
})
export class OverviewTab {
  readonly store = inject(AnalyticsStore);
  private readonly connection = inject(ConnectionStore);
  readonly format = (value: number) => inUnit({ r: value, pct: value, money: value }, this.store.unit(), this.connection.currency());
  readonly points = computed(() => this.store.equityCurve()?.points ?? []);
  readonly equitySeries = computed<LineChartSeries[]>(() => [{ name: 'Equity', points: this.points().map((p) => ({ date: p.date, value: this.store.unit() === 'money' ? p.cum_pnl : this.store.unit() === 'pct' ? (p.cum_pct ?? 0) : p.cum_r })) }]);
  readonly drawdownSeries = computed<LineChartSeries[]>(() => [{ name: 'Drawdown', points: this.points().map((p) => ({ date: p.date, value: -p.drawdown_r })) }]);
  readonly outcomes = computed<ShareSegment[]>(() => { const r = this.store.performance()?.relocated ?? {}; const wins = typeof r['wins'] === 'number' ? r['wins'] : 0; const losses = typeof r['losses'] === 'number' ? r['losses'] : 0; return [{ label: 'Wins', count: wins, tone: 'pos' }, { label: 'Losses', count: losses, tone: 'neg' }]; });
  readonly rBins = computed(() => (this.store.performance()?.distributions.r_multiples ?? []).map((b) => ({ label: `${b.lo}R`, count: b.count })));
  readonly monthBars = computed(() => (this.store.performance()?.calendar ?? []).map((m) => ({ label: m.month, value: m.return_pct, n: m.n })));
  readonly kpiTiles = computed(() => { const p = this.store.performance(); const last = this.points().at(-1); const currency = this.connection.currency(); const u = this.store.unit(); const tile = (label: string, r: number | null, pct: number | null, money: number | null, sample: number | null) => ({ label, value: inUnit({ r, pct, money }, u, currency), money: alwaysMoney({ r, pct, money }, currency), sample }); return [tile('Total R', last?.cum_r ?? null, p?.derived.total_return_pct ?? null, last?.cum_pnl ?? null, this.store.scopeN()), tile('ExpR', p?.expectancy_r ?? null, null, null, p?.expectancy_n ?? null), tile('Win rate', p?.win_rate ?? null, p?.win_rate ?? null, null, p?.win_rate_n ?? null)]; });
  readonly negativeBin = (bin: { label: string }) => bin.label.startsWith('-');
}
