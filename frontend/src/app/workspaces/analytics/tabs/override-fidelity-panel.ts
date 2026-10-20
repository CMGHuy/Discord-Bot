import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { OverrideRowDto } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { createClientPage } from '../../../ui/data-table/client-page';
import { EmptyStateComponent } from '../../../ui/empty-state';
import { Panel } from '../../../ui/layout';
import { PaginationComponent } from '../../../ui/pagination';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import { tablePerPage } from '../../../ui/table-per-page';
import { reasonLabel } from '../../trades/exit-reasons';
import {
  APPROX_LABEL, CAPTION, COUNTS_HINT, EMPTY_COPY, STATUS_LABEL, badgeCopy, badgeTone, exclusionNotes,
  isCounted, liveHint, netEffect, netTone, recordedLine, signedR, signedUsd, waitingOnLine,
} from './override-fidelity.model';

/* v173 — manual overrides vs the engine left alone. Descriptive until the
 * frozen verdict is recorded; the badge shows that recorded verdict or WAITING. */
@Component({
  selector: 'sb-override-fidelity-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError, EmptyStateComponent, PaginationComponent],
  template: `
    <sb-panel><sb-panel-header title="Overrides vs engine" [n]="data()?.summary?.counted_n ?? null"
      hint="Each manual close replayed through the engine from its real fill. Δ is your exit minus the engine's, in dollars and R." />
      @if (store.overrideFidelityError(); as error) {
        <sb-panel-error [message]="error" (retry)="store.reload('overrideFidelity')" />
      } @else if (data(); as d) {
        @if (!d.rows.length) { <sb-empty-state [title]="emptyCopy" reason="measured-zero" /> }
        @else {
          <dl class="tiles">
            <div class="net" [attr.data-tone]="netToneValue()"><dt>Net effect vs engine</dt><dd>{{ net() }}</dd>@if (hint(); as h) { <small class="live">{{ h }}</small> }</div>
            <div><dt>Overrides counted</dt><dd>{{ d.summary.counted_n }}</dd>@if (hint(); as h) { <small class="live">{{ h }}</small> }</div>
            <div><dt>Helped / hurt / neutral</dt><dd>{{ d.summary.helped }} / {{ d.summary.hurt }} / {{ d.summary.neutral }}</dd><small>{{ countsHint }}</small></div>
            <div class="badge" [attr.data-tone]="tone()"><dt>Verdict</dt><dd class="badge-text">{{ badge() }}</dd></div>
          </dl>
          @if (waitingOn(); as line) { <p class="waiting-on">{{ line }}</p> }
          @if (recorded(); as line) { <p class="recorded">{{ line }}</p> }
          <p class="caption">{{ caption }}</p>
          @for (note of notes(); track note) { <p class="note">{{ note }}</p> }
          <div class="table-wrap"><table class="rows">
            <thead><tr><th>Close date</th><th>Ticker</th><th>Horizon</th><th>State at close</th><th class="num">Actual</th><th class="num">Engine</th><th class="num">Δ</th><th>Engine exit</th><th>Status</th></tr></thead>
            <tbody>@for (r of page.visible(); track r.plan_id) {
              <tr [class.excluded]="!counted(r)">
                <td>{{ r.close_date ?? '—' }}</td><td>{{ r.ticker }}</td><td>{{ r.horizon }}</td><td>{{ r.state_at_close }}</td>
                <td class="num">{{ pair(r.actual_usd, r.actual_r) }}</td><td class="num">{{ pair(r.engine_usd, r.engine_r) }}</td>
                <td class="num delta">{{ pair(r.delta_usd, r.delta_r) }}@if (r.approx) { <small class="approx">{{ approxLabel }}</small> }</td>
                <td>{{ exit(r) }}</td><td>{{ status(r) }}</td>
              </tr>
            }</tbody>
          </table></div>
          <ul class="cards">@for (r of page.visible(); track r.plan_id) {
            <li class="card" [class.excluded]="!counted(r)">
              <div class="lead"><strong>{{ r.ticker }}</strong><span>{{ r.close_date ?? '—' }}</span><span class="num">{{ pair(r.delta_usd, r.delta_r) }}</span></div>
              <div class="sub">Engine exit: {{ exit(r) }}</div><div class="sub">Status: {{ status(r) }}</div>
              @if (r.approx) { <div class="sub approx">{{ approxLabel }}</div> }
            </li>
          }</ul>
          @if (d.rows.length > 5) {
            <sb-pagination [pagination]="page.pageSpec()" [showPerPage]="true" [announce]="true"
              (pageChange)="page.setPage($event)" (perPageChange)="perPage.set($event)" />
          }
        }
      }
    </sb-panel>
  `,
  styles: `.tiles{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-10);margin:0}.tiles>div{min-width:0;padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}dt{font-size:var(--text-micro);text-transform:uppercase;letter-spacing:.1em;color:var(--text-faint)}dd{margin:var(--space-4) 0;color:var(--text);font-variant-numeric:tabular-nums;white-space:normal;overflow-wrap:break-word}small{display:block;font-size:var(--text-micro);color:var(--text-faint)}.net[data-tone=pos] dd,.badge[data-tone=pos] .badge-text{color:var(--pos)}.net[data-tone=neg] dd,.badge[data-tone=neg] .badge-text{color:var(--neg)}.caption{margin:var(--space-10) 0 0;font-size:var(--text-body);line-height:1.5;color:var(--text-secondary)}.note,.waiting-on,.recorded{margin:var(--space-8) 0 0;font-size:var(--text-table);color:var(--text-secondary)}.table-wrap{overflow-x:auto;margin-top:var(--space-10)}.rows{width:100%;border-collapse:collapse;font-size:var(--text-table)}.rows th,.rows td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border)}.rows .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.excluded,.excluded td{color:var(--text-faint)}.approx{display:block;color:var(--warn);white-space:normal}.cards{display:none;list-style:none;margin:var(--space-10) 0 0;padding:0;gap:var(--space-8)}.cards li{padding:var(--space-10);border:1px solid var(--border);border-radius:var(--panel-radius)}.lead{display:flex;flex-wrap:wrap;align-items:baseline;gap:var(--space-6) var(--space-10)}.lead .num{margin-left:auto;font-variant-numeric:tabular-nums}.sub{font-size:var(--text-micro);color:var(--text-secondary)}@media(max-width:1023px){.tiles{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:639px){.table-wrap{display:none}.cards{display:grid}}`,
})
export class OverrideFidelityPanel {
  readonly store = inject(AnalyticsStore);
  readonly data = computed(() => this.store.overrideFidelity());
  readonly perPage = tablePerPage('override-fidelity');
  readonly page = createClientPage<OverrideRowDto>(() => this.data()?.rows ?? [], () => this.perPage.value());
  readonly caption = CAPTION;
  readonly emptyCopy = EMPTY_COPY;
  readonly approxLabel = APPROX_LABEL;
  readonly countsHint = COUNTS_HINT;
  readonly counted = isCounted;

  private readonly currency = computed(() => this.data()?.currency_symbol ?? '');
  readonly net = computed(() => { const d = this.data(); return d ? netEffect(d.summary, this.currency()) : ''; });
  readonly netToneValue = computed(() => { const d = this.data(); return d ? netTone(d.verdict, d.summary) : 'neutral'; });
  readonly badge = computed(() => { const d = this.data(); return d ? badgeCopy(d.verdict, this.currency()) : ''; });
  readonly tone = computed(() => { const d = this.data(); return d ? badgeTone(d.verdict) : 'neutral'; });
  readonly waitingOn = computed(() => { const d = this.data(); return d ? waitingOnLine(d.verdict) : null; });
  readonly recorded = computed(() => { const d = this.data(); return d ? recordedLine(d.verdict) : null; });
  readonly hint = computed(() => { const d = this.data(); return d ? liveHint(d.verdict) : null; });
  readonly notes = computed(() => { const d = this.data(); return d ? exclusionNotes(d.summary, d.verdict) : []; });

  /** Every R figure carries its signed dollars beside it (the v170 convention). */
  pair(usd: number | null, r: number | null): string {
    return `${signedUsd(usd, this.currency())} · ${signedR(r)}`;
  }

  exit(r: OverrideRowDto): string {
    return reasonLabel(r.engine_exit_reason) ?? '—';
  }

  status(r: OverrideRowDto): string {
    return r.bulk ? `${STATUS_LABEL[r.status]} · bulk clear` : STATUS_LABEL[r.status];
  }
}
