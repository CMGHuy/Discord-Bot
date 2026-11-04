import { ChangeDetectionStrategy, Component, inject, input } from '@angular/core';

import { LiveValuesStore } from '../stores/live-values.store';
import { Button } from './button';

/** v201: asks the refresher for fresh quotes of the symbols on screen. */
@Component({
  selector: 'sb-market-refresh',
  imports: [Button],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<button sb-button variant="secondary" type="button" class="sb-hit" [disabled]="symbols().length === 0" (click)="refresh()">Refresh</button>`,
})
export class MarketRefresh {
  readonly symbols = input<string[]>([]);
  private readonly live = inject(LiveValuesStore);

  protected refresh(): void {
    this.live.requestRefresh(this.symbols());
  }
}
