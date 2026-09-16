import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export interface DonutSlice { label: string; count: number; tone?: 'pos' | 'neg'; }
const R = 60; const C = 2 * Math.PI * R;

/** A compact SVG composition chart. Zero rows are deliberately legended but
 * have no arc: absence must never impersonate a zero-valued outcome. */
@Component({
  selector: 'sb-donut', standalone: true, imports: [DecimalPipe], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@if (total()) {<div class="wrap"><svg viewBox="0 0 160 160" role="img" [attr.aria-label]="summary()"><g transform="rotate(-90 80 80)">@for (a of arcs(); track a.label) {@if (a.count) {<circle class="slice" cx="80" cy="80" r="60" [attr.stroke]="a.fill" [attr.stroke-dasharray]="a.dash" [attr.stroke-dashoffset]="a.offset"/>}}</g><text x="80" y="80" text-anchor="middle" dy=".35em">{{total()}}</text></svg><ul>@for(a of arcs();track a.label){<li><i [style.background]="a.fill"></i>{{a.label}} <span>n={{a.count}}</span> <span>{{a.share|number:'1.1-1'}}%</span></li>}</ul></div>}`,
  styles: `.wrap{display:flex;gap:1rem;align-items:center;flex-wrap:wrap}svg{width:160px;height:160px}text{fill:var(--text-secondary);font-size:var(--text-table);font-variant-numeric:tabular-nums}.slice{fill:none;stroke-width:20}ul{list-style:none;margin:0;padding:0;min-width:14rem}li{display:grid;grid-template-columns:.8rem 1fr auto auto;gap:.4rem}i{width:.7rem;height:.7rem;border-radius:2px;margin:auto 0}span{font-size:var(--text-micro);color:var(--text-muted);font-variant-numeric:tabular-nums}`,
})
export class DonutComponent {
  readonly slices=input.required<readonly DonutSlice[]>();
  protected readonly total=computed(()=>this.slices().reduce((n,s)=>n+Math.max(0,s.count),0));
  protected readonly arcs=computed(()=>{let used=0,i=0;const total=this.total(), n=this.slices().filter(s=>s.count>0).length;return this.slices().map(s=>{const share=total?s.count/total*100:0;const fill=s.tone==='pos'?'var(--pos)':s.tone==='neg'?'var(--neg)':`color-mix(in oklab,var(--text) ${Math.round(70-(n>1?i/(n-1):0)*45)}%,transparent)`;const a={...s,share,dash:`${C*share/100} ${C}`,offset:-C*used/total,fill};if(s.count>0){used+=s.count;i++;}return a;});});
  protected readonly summary=computed(()=>this.arcs().filter(a=>a.count).map(a=>`${a.label} ${a.share.toFixed(1)}%`).join(', '));
}
