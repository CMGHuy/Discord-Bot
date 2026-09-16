import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { AnalyticsExitQuality } from '../../../api/models';
import { DonutComponent, DonutSlice } from '../../../ui/donut';
import { Histogram, HistogramBin } from '../../../ui/histogram';
import { Panel } from '../../../ui/layout';
import { ScatterComponent, ScatterPoint } from '../../../ui/scatter';

@Component({selector:'sb-exit-quality',standalone:true,changeDetection:ChangeDetectionStrategy.OnPush,imports:[Panel,DonutComponent,Histogram,ScatterComponent],
template:`@if(data();as d){<sb-panel heading="Exit quality"><p class="coverage">{{coverageText()}}</p><div class="grid"><section><h3>Exit reason mix</h3><sb-donut [slices]="reasons()"/></section><section><h3>Outcome mix</h3><sb-donut [slices]="outcomes()"/></section><section><h3>Exit efficiency — winners only</h3><sb-histogram [bins]="efficiency()"/><p>{{d.efficiency.n}} winner trades · median {{d.efficiency.median ?? '—'}}R</p></section><section><h3>MAE — winners only</h3><sb-histogram [bins]="mae()"/><p>{{d.mae.n}} winner trades · median {{d.mae.median ?? '—'}}R</p></section><section><h3>Disposition</h3><p>{{disposition()}}</p></section><section><h3>MFE versus MAE</h3><sb-scatter [points]="scatter()" xLabel="MAE (R)" yLabel="MFE (R)"/></section></div></sb-panel>}`,
styles:`.coverage{color:var(--text-muted);font-size:var(--text-micro)}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:var(--space-14)}h3{font-size:var(--text-table);margin:0 0 var(--space-8)}p{font-size:var(--text-micro);color:var(--text-muted)}`})
export class ExitQualitySectionComponent {
  readonly data=input.required<AnalyticsExitQuality|null>();
  protected readonly coverageText=computed(()=>Object.entries(this.data()?.coverage??{}).map(([name,c])=>`${name}: ${c.non_null} of ${c.total} (${c.pct}%)`).join(' · '));
  protected readonly reasons=computed<DonutSlice[]>(()=>this.data()?.exit_reasons.map((r:any)=>({label:r.reason,count:r.n}))??[]);
  protected readonly outcomes=computed<DonutSlice[]>(()=>{const h:any=this.data()?.hold_by_outcome??{};return[{label:'Winners',count:h.n_winners??0,tone:'pos'},{label:'Losers',count:h.n_losers??0,tone:'neg'}];});
  private bins(key:'efficiency'|'mae'):HistogramBin[]{return (this.data()?.[key].bins??[] as any[]).map(b=>({label:`${Number(b.lo).toFixed(1)}–${Number(b.hi).toFixed(1)}R`,count:b.count}));}
  protected readonly efficiency=computed(()=>this.bins('efficiency')); protected readonly mae=computed(()=>this.bins('mae'));
  protected readonly scatter=computed<ScatterPoint[]>(()=>this.data()?.scatter.map((p:any)=>({x:p.mae_r,y:p.mfe_r,label:`${p.ticker} · ${p.strategy}`,tone:p.outcome==='win'?'pos':'neg'}))??[]);
  protected readonly disposition=computed(()=>{const h:any=this.data()?.hold_by_outcome??{};return h.ratio==null?'Insufficient winner and loser samples to state a hold-time ratio.':`Losers were held ${h.ratio.toFixed(2)}× as long as winners (${h.severity??'unclassified'}).`;});
}
