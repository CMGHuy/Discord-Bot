import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { AnalyticsStore } from '../../../stores/analytics.store';
import { Histogram } from '../../../ui/histogram';
import { InlineMd } from '../../../ui/inline-md';
import { Panel } from '../../../ui/layout';
import { PanelHeader } from '../../../ui/panel-header';
import { ShareBar, ShareSegment } from '../../../ui/share-bar';
import { StripGroup, StripPlot } from '../../../ui/strip-plot';

/** Exit-quality is interpreted before it is charted: the verdict is the
 * actionable result; the distributions below explain it. */
@Component({ selector: 'sb-execution-tab', changeDetection: ChangeDetectionStrategy.OnPush, imports: [Panel, PanelHeader, Histogram, ShareBar, StripPlot, InlineMd], template: `
  <sb-panel><sb-panel-header title="Execution verdict" [n]="store.scopeN()" hint="Exit quality for the scoped closed book." />
    <dl class="verdict">@for (v of verdict(); track v.label) { <div><dt>{{v.label}}</dt><dd>{{v.value}}</dd><small>{{v.hint}}</small></div> }</dl>
  </sb-panel>
  <div class="panels"><sb-panel><sb-panel-header title="Exit reasons" [n]="store.scopeN()" /><sb-share-bar label="Exit reasons" [segments]="exitReasonSegments()" /></sb-panel>
  <sb-panel><sb-panel-header title="Hold time by outcome" [n]="store.scopeN()" /><sb-strip-plot [groups]="holdGroups()" unit="d" /></sb-panel>
  <sb-panel><sb-panel-header title="Exit efficiency" [n]="store.scopeN()" /><sb-histogram [bins]="efficiencyBins()" /></sb-panel>
  <sb-panel><sb-panel-header title="Journal" [n]="store.scopeN()" />@for(line of journal()?.digest ?? [];track line){<p><sb-inline-md [text]="line" /></p>}</sb-panel></div>
`, styles: `.verdict,.panels{display:grid;gap:var(--space-12)}.verdict{grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));margin:0}.verdict div{padding:var(--space-10);border:1px solid var(--border);border-radius:var(--radius)}dt,small{color:var(--text-faint);font-size:var(--text-chip)}dd{margin:var(--space-4) 0;color:var(--text);font-variant-numeric:tabular-nums}.panels{grid-template-columns:repeat(2,minmax(0,1fr))}@media(max-width:800px){.panels{grid-template-columns:1fr}}` })
export class ExecutionTab {
  readonly store = inject(AnalyticsStore);
  readonly journal = computed(() => this.store.journal());
  private readonly quality = computed(() => this.store.exitQuality());
  readonly verdict = computed(() => { const q = this.quality(); const hold = (q?.hold_by_outcome ?? {}) as Record<string, number | string | null>; const coverage = Object.values(q?.coverage ?? {}).map((v) => v.pct); return [{ label: 'Exit efficiency', value: q?.efficiency.median?.toFixed(2) ?? '—', hint: `N=${q?.efficiency.n ?? 0}` }, { label: 'Disposition ratio', value: hold['ratio'] === null || hold['ratio'] === undefined ? '—' : Number(hold['ratio']).toFixed(2), hint: String(hold['severity'] ?? '—') }, { label: 'Hold winners / losers', value: `${hold['avg_winner_days'] ?? '—'} / ${hold['avg_loser_days'] ?? '—'}d`, hint: 'calendar days' }, { label: 'Journal coverage', value: coverage.length ? `${Math.min(...coverage).toFixed(1)}%` : '—', hint: 'minimum recorded field' }]; });
  readonly exitReasonSegments = computed<ShareSegment[]>(() => { const q = this.quality(); const unmapped = (q?.unmapped_reasons ?? []).reduce((n, x) => n + x.n, 0); return (q?.exit_reasons as { reason: string; n: number }[] ?? []).map((r) => ({ label: r.reason === 'other' && unmapped ? 'unrecorded' : r.reason, count: r.n, tone: r.reason === 'other' ? 'warn' : 'accent' })); });
  readonly holdGroups = computed<StripGroup[]>(() => ['win', 'loss'].map((outcome) => ({ label: outcome === 'win' ? 'Winners' : 'Losers', tone: outcome === 'win' ? 'pos' : 'neg', values: (this.quality()?.hold_points ?? []).filter((p) => p.outcome === outcome).map((p) => p.days) })));
  readonly efficiencyBins = computed(() => ((this.quality()?.efficiency.bins ?? []) as { lo: number; count: number }[]).map((b) => ({ label: b.lo.toFixed(2), count: b.count })));
}
