import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { LiveValuesStore } from '../stores/live-values.store';

/** v201: the refresher stopped beating, so every price on screen is ageing. */
@Component({
  selector: 'sb-refresher-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@if (live.stalled()) {<div class="refresher-strip" role="alert">Prices paused: refresher not running</div>}`,
  styles: `
    .refresher-strip {
      padding: var(--space-6) var(--space-14);
      background: var(--warn-soft);
      border-bottom: 1px solid var(--warn);
      color: var(--warn);
      font-size: var(--text-chip);
      font-weight: 600;
      letter-spacing: 0.08em;
      text-align: center;
    }
  `,
})
export class RefresherBanner {
  protected readonly live = inject(LiveValuesStore);
}
