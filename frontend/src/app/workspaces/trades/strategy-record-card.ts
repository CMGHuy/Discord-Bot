import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { StrategyRow } from '../../api/models';
import { num, pct, text } from '../../ui/format';
import { Panel } from '../../ui/layout';

@Component({
  selector: 'sb-trade-strategy-record', imports: [Panel], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sb-panel heading="Strategy record">
      @if (error()) {
        <p class="not-journaled">{{ error() }}</p>
      } @else if (!strategy()) {
        <p class="not-journaled">This position has no strategy recorded.</p>
      } @else if (row(); as row) {
        <dl>
          <div><dt>Strategy</dt><dd>{{ row.strategy }}</dd></div>
          <div><dt>Status</dt><dd>{{ row.status }}</dd></div>
          <div><dt>OOS sample</dt><dd>{{ fmt(row.n) }}</dd></div>
          <div><dt>OOS win rate</dt><dd>{{ fmtPct(row.win_rate) }}</dd></div>
          <div><dt>OOS expectancy</dt><dd>{{ fmt(row.expectancy_r) }}R</dd></div>
          <div><dt>Live sample</dt><dd>{{ fmt(row.live_n) }}</dd></div>
          <div><dt>Live win rate</dt><dd>{{ fmtPct(row.live_wr) }}</dd></div>
          <div><dt>Live vs OOS</dt><dd>{{ fmtPct(row.delta_vs_oos) }}</dd></div>
          <div><dt>Window</dt><dd>{{ fmtText(row.window) }}</dd></div>
        </dl>
        @if (row.decayed) {
          <p class="decayed">Live results have decayed against this strategy's out-of-sample record.</p>
        }
      } @else {
        <p class="not-journaled">The registry has no entry for {{ fmtText(strategy()) }}.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; overflow-wrap: anywhere; }
    dl { display: grid; gap: var(--space-6); margin: 0; }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); min-width: 0; }
    dt { color: var(--text-secondary); }
    dt, dd { min-width: 0; font-size: var(--text-table); }
    dd { margin: 0; text-align: right; }
    .not-journaled { margin: 0; color: var(--text-secondary); font-size: var(--text-table); }
    .decayed { margin-top: var(--space-10); color: var(--warn); font-size: var(--text-table); }
  `,
})
export class StrategyRecordCard {
  readonly strategy = input<string | null>(null);
  readonly row = input<StrategyRow | null>(null);
  readonly error = input<string | null>(null);
  protected readonly fmt = num;
  protected readonly fmtPct = pct;
  protected readonly fmtText = text;
}
