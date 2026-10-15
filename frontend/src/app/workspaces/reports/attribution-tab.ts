import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import {
  LATEST_HEADING,
  R_CAPTION,
  ReadingView,
  ReportsStore,
} from '../../stores/reports.store';
import { BarList } from '../../ui/bar-list';
import { Chip } from '../../ui/chip';
import { Panel } from '../../ui/layout';

/** Signed R to two places, or an em dash: an absent figure is never zero. */
export function formatR(value: number | null): string {
  if (value === null) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}R`;
}

export function formatInterval(low: number | null, high: number | null): string {
  return low === null || high === null ? '—' : `[${formatR(low)}, ${formatR(high)}]`;
}

/**
 * Expectancy attribution (v146) — does confidence predict R, and which
 * buckets separate good trades from bad.
 *
 * Renders `ReportsStore.attribution()` and decides nothing: the verdict of
 * record, the thin flags and every q-value arrive already computed. Named
 * "Expectancy attribution" because the Analytics workspace has its own
 * "Attribution" tab, which answers a different question.
 *
 * One rule this template must keep: exactly ONE verdict chip, the verdict of
 * record. Everything below it is a reading, and is laid out as one.
 */
@Component({
  selector: 'sb-expectancy-attribution-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [BarList, Chip, Panel],
  template: `
    @if (store.attribution(); as view) {
      <sb-panel heading="Verdict of record">
        <div class="verdict">
          <sb-chip [label]="view.verdict.label" [tone]="view.verdict.tone" />
          <span class="aside">fixed {{ view.verdict.date }} · N {{ view.verdict.n }}</span>
          @if (view.verdict.inverted) {
            <span class="aside">inverted: the interval lies wholly below zero</span>
          }
        </div>
        <p class="caption">
          Does confidence predict R. Computed once, at the scheduled run; later runs never revise it.
        </p>
      </sb-panel>

      <sb-panel [heading]="latestHeading">
        <div class="pair">
          @for (reading of view.readings; track reading.population) {
            <div class="reading" [attr.data-population]="reading.population">
              <span class="population">{{ reading.population }}</span>
              @if (reading.present) {
                <dl>
                  <dt>Spearman ρ</dt><dd class="num">{{ rho(reading) }}</dd>
                  <dt>Top − bottom tercile ExpR</dt>
                  <dd class="num">{{ r(reading.spread) }} {{ interval(reading.ciLow, reading.ciHigh) }}</dd>
                  <dt>N</dt><dd class="num">{{ reading.n }}</dd>
                  <dt>Window</dt><dd>{{ reading.window ?? '—' }}</dd>
                </dl>
              } @else {
                <p class="aside">not in this run</p>
              }
            </div>
          }
        </div>
        <p class="caption">95% interval, week-clustered. {{ caption }}</p>
      </sb-panel>

      <sb-panel heading="Factors">
        <table class="figures">
          <thead>
            <tr><th>Factor</th><th>Live Δ ExpR</th><th>TRAIN Δ ExpR</th><th></th></tr>
          </thead>
          <tbody>
            @for (factor of view.factors; track factor.key) {
              <tr [attr.data-factor]="factor.key">
                <td>{{ factor.key }}</td>
                <td class="num">
                  @if (factor.live; as live) { {{ r(live.delta) }} {{ interval(live.ciLow, live.ciHigh) }} }
                  @else { <span class="aside">not in this run</span> }
                </td>
                <td class="num">
                  @if (factor.train; as train) { {{ r(train.delta) }} {{ interval(train.ciLow, train.ciHigh) }} }
                  @else { <span class="aside">not in this run</span> }
                </td>
                <td>@if (factor.candidate) { <span class="candidate">screen candidate</span> }</td>
              </tr>
            }
          </tbody>
        </table>
        <p class="caption">
          ExpR where the factor scored above zero, minus where it scored zero. A screen candidate
          (BH q &lt; 0.10) is a candidate for a Stage −2 screen, never a filter. {{ caption }}
        </p>
      </sb-panel>

      @for (dimension of view.dimensions; track dimension.key) {
        <sb-panel [heading]="dimension.label" [attr.data-dimension]="dimension.key">
          <div class="pair">
            <div>
              <span class="population">Live</span>
              @if (dimension.live; as rows) {
                <sb-bar-list [rows]="rows" mode="signed" [format]="r" />
              } @else { <p class="aside">not in this run</p> }
            </div>
            <div>
              <span class="population">TRAIN</span>
              @if (dimension.train; as rows) {
                <sb-bar-list [rows]="rows" mode="signed" [format]="r" />
              } @else { <p class="aside">not in this run</p> }
            </div>
          </div>
          @for (candidate of dimension.candidates; track candidate) {
            <span class="candidate">screen candidate: {{ candidate }}</span>
          }
          <p class="caption">ExpR per bucket. A faded bucket is below the report's floor: shown, not evidence. {{ caption }}</p>
        </sb-panel>
      }

      <sb-panel heading="Direction and horizon splits">
        <table class="figures">
          <thead>
            <tr><th>Split</th><th>Live top − bottom</th><th>Live N</th><th>TRAIN top − bottom</th><th>TRAIN N</th></tr>
          </thead>
          <tbody>
            @for (split of view.splits; track split.axis + split.name) {
              <tr [attr.data-split]="split.axis + ':' + split.name">
                <td>{{ split.axis }}: {{ split.name }}</td>
                <td class="num">{{ r(split.live?.spread ?? null) }} {{ interval(split.live?.ciLow ?? null, split.live?.ciHigh ?? null) }}</td>
                <td class="num">{{ split.live?.n ?? '—' }}</td>
                <td class="num">{{ r(split.train?.spread ?? null) }} {{ interval(split.train?.ciLow ?? null, split.train?.ciHigh ?? null) }}</td>
                <td class="num">{{ split.train?.n ?? '—' }}</td>
              </tr>
            }
          </tbody>
        </table>
        <p class="caption">The same reading per direction and per horizon, so a lift concentrated in one is visible. {{ caption }}</p>
      </sb-panel>

      <p class="footer">
        @for (reading of view.readings; track reading.population) {
          @if (reading.present) { {{ reading.population }}: {{ reading.window ?? 'window not recorded' }}, N {{ reading.n }}. }
        }
        Seed {{ view.seed }}. looks: {{ view.looks }} — BH family for every q on this tab.
        {{ caption }} descriptive — not a gate.
      </p>
    }
  `,
  styles: `
    :host { display: grid; gap: var(--space-14); }
    .verdict { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-10); }
    .pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr)); gap: var(--space-14); }
    .population { display: block; color: var(--text-muted); font-size: var(--text-micro); text-transform: uppercase; letter-spacing: 0.08em; }
    dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: var(--space-4) var(--space-14); margin: var(--space-6) 0 0; }
    dt { color: var(--text-muted); }
    dd { margin: 0; }
    .figures { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .figures th { text-align: left; color: var(--text-muted); font-weight: 500; }
    .figures th, .figures td { padding: var(--space-4) var(--space-8); border-bottom: 1px solid var(--border); }
    .aside, .caption, .footer { color: var(--text-faint); font-size: var(--text-micro); }
    .caption, .footer { margin: var(--space-8) 0 0; }
    .candidate { display: inline-block; margin: var(--space-6) var(--space-8) 0 0; color: var(--info); font-size: var(--text-micro); }
  `,
})
export class AttributionTab {
  protected readonly store = inject(ReportsStore);

  protected readonly latestHeading = LATEST_HEADING;
  protected readonly caption = R_CAPTION;

  /** Arrow functions: `sb-bar-list` calls `format` detached from this class. */
  protected readonly r = (value: number | null): string => formatR(value);
  protected readonly interval = formatInterval;

  protected rho(reading: ReadingView): string {
    return reading.rho === null ? '—' : reading.rho.toFixed(2);
  }
}
