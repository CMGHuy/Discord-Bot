import { ChangeDetectionStrategy, Component, computed, effect, inject, input } from '@angular/core';

import { ChartStore } from '../../../stores/chart.store';
import { ChartContainer } from '../../../ui/chart-container';
import { TradeChart } from '../../../ui/chart/trade-chart';

/**
 * The plan's chart (spec v151): daily bars with this plan's levels and the
 * methods that put them there. Extracted from the trade page's Chart tab so
 * the plan page draws the same chart.
 *
 * The one shared component that is not plain inputs: it reads `ChartStore`
 * from its injector (route-scoped on both pages) and points it at its own
 * ticker and plan id. `setTarget` is a no-op for the same pair, so a page that
 * already set the target (the trade page preloads it) costs no second request.
 */
@Component({
  selector: 'sb-plan-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [ChartContainer, TradeChart],
  template: `
    <sb-chart-container
      [loading]="chart.loading()"
      [error]="chart.error()"
      [hasData]="!chart.isEmpty()"
      [height]="520"
      [caption]="caption()"
      [canRetry]="true"
      (retry)="chart.retry()"
    >
      <sb-trade-chart [data]="chart.data()" />
    </sb-chart-container>
  `,
  styles: `
    :host { display: block; }
  `,
})
export class PlanChart {
  protected readonly chart = inject(ChartStore);

  readonly ticker = input<string | null>(null);
  readonly tradeId = input<string | null>(null);

  /** The confirming methods, when the chart draws any. An empty list is an
   *  ordinary state (an older trade with no recorded sources), so the caption
   *  simply says less rather than announcing an absence. */
  protected readonly caption = computed(() => {
    const ticker = this.ticker();
    if (!ticker) return null;
    const source = (this.chart.data()?.overlays ?? [])
      .map((overlay) => overlay.source)
      .join(' · ');
    const base = `${ticker} — daily, with this plan's levels`;
    return source ? `${base} · ${source}` : base;
  });

  constructor() {
    // Both, and both from the plan: the ticker is what is charted, and the id
    // is what adds the plan lines, the working stop and the overlays. A null
    // ticker asks for nothing (ChartStore.load returns early).
    effect(() => this.chart.setTarget(this.ticker(), this.tradeId()));
  }
}
