import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { scanAge } from '../freshness-chip';
import { liveSummaryLabel } from './live-edge-tab';
import { LiveWarning } from './live-state';

const HEAT_WARNINGS: ReadonlySet<LiveWarning> = new Set(['heat-near-cap', 'over-cap']);

/**
 * The live strip -- v203 (spec v202 §4 "Live strip"). Tablet and phone
 * only: one 40px line under the tape that opens the dock as a sheet. It
 * takes the edge tab's warning tone and label, so a state reads the same
 * on both.
 */
@Component({
  selector: 'sb-live-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="live-strip sb-hit" [class.warn]="warnings().length > 0"
            aria-haspopup="dialog" [attr.aria-label]="label()" (click)="opened.emit()">
      <span class="dot" aria-hidden="true"></span>
      <span class="age" aria-hidden="true">{{ age() }}</span>
      <span class="heat" [class.near]="heatWarn()" aria-hidden="true">{{ heatText() }}</span>
      @if (awaitingCount() !== null) { <span class="count" aria-hidden="true">{{ awaitingCount() }} awaiting order</span> }
      <span class="go" aria-hidden="true">Live ›</span>
    </button>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .live-strip {
      display: flex; align-items: center; gap: var(--space-10);
      width: 100%; height: 40px; padding: 0 var(--space-14); overflow: hidden;
      border: 0; border-bottom: 1px solid var(--border); background: var(--surface);
      color: var(--text-secondary); font: inherit; font-size: var(--text-chip); text-align: left; cursor: pointer;
    }
    .live-strip:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--pos); }
    .age, .count, .go { flex: none; white-space: nowrap; }
    .heat { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); font-variant-numeric: tabular-nums; }
    .heat.near { color: var(--warn); }
    .go { margin-left: auto; color: var(--accent); }
    .warn { background: var(--warn-soft); }
    .warn .dot { background: var(--warn); }
  `,
})
export class LiveStrip {
  readonly warnings = input<readonly LiveWarning[]>([]);
  readonly heatText = input.required<string>();
  readonly awaitingCount = input<number | null>(null);
  readonly lastSuccess = input<string | null>(null);
  readonly now = input.required<Date>();
  readonly opened = output<void>();

  protected readonly age = computed(() => scanAge(this.lastSuccess(), this.now().getTime()) ?? 'No scan yet');
  protected readonly heatWarn = computed(() => this.warnings().some((warning) => HEAT_WARNINGS.has(warning)));
  protected readonly label = computed(() =>
    `${liveSummaryLabel(this.warnings(), this.heatText(), this.awaitingCount())}. Last scan ${this.age()}`);
}
