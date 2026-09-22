import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { Histogram } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { PanelHeader } from '../../../ui/panel-header';

/** All-time plan lifecycle metrics; deliberately separated from the scoped
 * execution ledger because a plan can still be in flight. */
@Component({ selector: 'sb-pipeline-tab', changeDetection: ChangeDetectionStrategy.OnPush, imports: [Panel, PanelHeader, Histogram], template: `
  <div class="panels"><sb-panel><sb-panel-header title="Plan funnel" [allTime]="true" hint="Lifecycle counts from posted through closed." /><sb-histogram [bins]="funnelBins()" /></sb-panel>
  <sb-panel><sb-panel-header title="Fill rate" [allTime]="true" /><dl><div><dt>Resolved plans</dt><dd>{{plans()?.fill_rate?.resolved_n ?? 0}}</dd></div><div><dt>Fill rate</dt><dd>{{fillRateText()}}</dd></div><div><dt>Median days to fill</dt><dd>{{plans()?.fill_rate?.median_days_to_fill ?? '—'}}</dd></div></dl></sb-panel>
  <sb-panel><sb-panel-header title="Badges" [allTime]="true" /><sb-histogram [bins]="badgeBins()" /></sb-panel><sb-panel><sb-panel-header title="Tiers" [allTime]="true" /><sb-histogram [bins]="tierBins()" /></sb-panel></div>
`, styles: `.panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:var(--space-14)}dl{display:grid;gap:var(--space-8)}dt{font-size:var(--text-micro);text-transform:uppercase;letter-spacing:.1em;color:var(--text-faint)}dd{margin:2px 0;font-variant-numeric:tabular-nums}@media(max-width:800px){.panels{grid-template-columns:1fr}}` })
export class PipelineTab {
  readonly store = inject(AnalyticsStore); readonly plans = computed(() => this.store.plans());
  readonly funnelBins = computed(() => { const f = this.plans()?.funnel; return f ? [['Posted', f.posted], ['Filled', f.filled], ['Hit TP1', f.hit_tp1], ['Closed', f.closed]].map(([label, count]) => ({ label: String(label), count: Number(count) })) : []; });
  readonly badgeBins = computed(() => Object.entries(this.plans()?.badges ?? {}).map(([label, count]) => ({ label, count })));
  readonly tierBins = computed(() => Object.entries(this.plans()?.tiers ?? {}).map(([label, count]) => ({ label, count })));
  readonly fillRateText = computed(() => { const x = this.plans()?.fill_rate?.fill_rate_pct; return x === null || x === undefined ? '—' : `${x.toFixed(1)}%`; });
}
