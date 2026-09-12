import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { Panel } from '../../../ui/layout';
import { DonutComponent, DonutSlice } from '../../../ui/donut';
import { TradesStore } from '../../../stores/trades.store';

/**
 * Open risk grouped by horizon — v85 D31/sheet 1.
 *
 * The mockup's allocation donut has no honest occupant here: this book is
 * one asset class with no cash line. Its slot takes the composition question
 * this book actually has instead — how much open risk sits in each swing
 * horizon.
 *
 * Its own `TradesStore` instance, scoped to `status=open` (the ACTIVE-or-
 * PARTIAL alias) at the server's own page-size cap, rather than reusing the
 * Dashboard's activity-feed store: that one is a most-recent-20-of-every-
 * status query, which would silently under-count once the trade log holds
 * more than 20 rows.
 */
@Component({
  selector: 'sb-exposure-by-horizon',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, DonutComponent],
  providers: [TradesStore],
  template: `
    <sb-panel heading="Exposure by horizon">
      @if (slices().length) {
        <sb-donut [slices]="slices()" />
      } @else {
        <p class="empty">No open exposure yet.</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    .empty { margin: 0; color: var(--text-faint); font-size: var(--text-chip); }
  `,
})
export class ExposureByHorizon {
  private readonly trades = inject(TradesStore);

  constructor() {
    this.trades.setQuery({ status: 'open', per_page: 200, sort: '-opened_at' });
  }

  /** Dollar risk still on the table per position: distance from entry to the
   *  ORIGINAL stop, times the shares still exposed to it -- the same "risk"
   *  every other risk figure on this book means. Skipped, not zero-filled,
   *  when either price is missing (should not happen for an open position,
   *  but this is display code, not the source of truth for what is open). */
  protected readonly slices = computed<DonutSlice[]>(() => {
    const byHorizon = new Map<string, number>();
    for (const row of this.trades.rows()) {
      if (row.entry === null || row.stop_loss === null) continue;
      const shares = row.open_shares ?? row.shares ?? 0;
      const risk = Math.abs(row.entry - row.stop_loss) * shares;
      if (risk <= 0) continue;
      const label = row.horizon ?? 'Unknown';
      byHorizon.set(label, (byHorizon.get(label) ?? 0) + risk);
    }
    return [...byHorizon.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([label, count]) => ({ label, count: Math.round(count) }));
  });
}
