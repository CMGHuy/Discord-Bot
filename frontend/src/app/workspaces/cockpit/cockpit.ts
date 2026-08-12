import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { CockpitStore } from '../../stores/cockpit.store';
import { MetricCard } from '../../ui/metric-card';

/**
 * The tracer bullet: `/api/v1/cockpit` → `ApiClient` → `CockpitStore` →
 * three `MetricCard`s, refetching on an event.
 *
 * **Every workspace in Phase 4 repeats this shape**, so the parts worth
 * copying are: the store is provided on the component (not root), the
 * component reads signals and never fetches, and there is no subscription
 * or refresh call anywhere in this file -- the store's own effect owns
 * both the first load and every refetch.
 *
 * The remaining six secondary metrics are NG47.
 */
@Component({
  selector: 'sb-cockpit',
  imports: [MetricCard],
  changeDetection: ChangeDetectionStrategy.OnPush,
  // Provided here rather than in root: the store is created on entry and
  // destroyed on exit, so a workspace does not hold stale state while you
  // are looking at another one.
  providers: [CockpitStore],
  template: `
    <header class="head">
      <h1>Cockpit</h1>
      @if (store.error(); as message) {
        <!-- Beside the numbers, not instead of them: the previous values
             are still the best information available, and replacing nine
             live figures with an error panel because one poll failed is
             worse than showing them slightly stale. -->
        <span class="stale" role="status">{{ message }}</span>
      }
    </header>

    <div class="primary">
      <sb-metric-card
        label="Account balance"
        [value]="store.balance()"
        unit=" USD"
      />
      <sb-metric-card
        label="Open P&L"
        [value]="store.openPnlPct()"
        tone="pnl"
        unit="%"
      />
      <sb-metric-card
        label="Risk used"
        [value]="store.riskUsedPct()"
        [tone]="riskTone()"
        unit="%"
        [sub]="riskSub()"
      />
    </div>
  `,
  styles: `
    .head {
      display: flex;
      align-items: baseline;
      gap: var(--space-14);
      margin-bottom: var(--space-20);
    }
    h1 {
      margin: 0;
      font-size: var(--text-title);
      font-weight: 600;
    }
    .stale {
      color: var(--warn);
      font-size: var(--text-table);
    }
    .primary {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: var(--space-14);
      /* Three across down to 1280px, which is the width the layout is
         committed to (NG52). Below that they stack rather than shrink --
         a 23px metric in a 90px column is not a metric anyone can read. */
      max-width: 960px;
    }
    @media (max-width: 720px) {
      .primary { grid-template-columns: 1fr; }
    }
  `,
})
export class Cockpit {
  protected readonly store = inject(CockpitStore);

  /** Amber once exposure is most of the cap. Amber means caution, which is
   *  what "nearly out of risk budget" is -- it is not a loss, so it must
   *  not be red. */
  protected readonly riskTone = computed(() =>
    (this.store.riskUtilisation() ?? 0) >= 0.8 ? 'caution' : 'plain',
  );

  protected readonly riskSub = computed(() => {
    const cap = this.store.riskCapPct();
    return cap === null ? null : `of ${cap.toFixed(1)}% cap`;
  });
}
