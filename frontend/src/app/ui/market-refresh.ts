import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';

import { LiveValuesStore } from '../stores/live-values.store';
import { Button } from './button';

/** Asks the refresher to update the quotes and snapshots on screen. */
@Component({
  selector: 'sb-market-refresh',
  imports: [Button],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button sb-button variant="secondary" type="button" class="sb-hit" [disabled]="symbols().length === 0 && snapshots().length === 0" (click)="refresh()">Refresh</button>`,
})
export class MarketRefresh {
  readonly symbols = input<string[]>([]);
  readonly snapshots = input<string[]>([]);
  private readonly live = inject(LiveValuesStore);

  protected refresh(): void {
    this.live.requestRefresh(this.symbols(), this.snapshots());
  }
}
