import { ChangeDetectionStrategy, Component } from '@angular/core';

/** v94 Tuning — launch a TRAIN grid, watch it, stage a proposal. A stub so
 *  the shell compiles; Task T6 moves the old monolith's tuning panels here.
 *  The store keeps `loadTuning`/`loadJob`/`loadProposals`/`loadGrid` and
 *  their state intact for it to read. */
@Component({
  selector: 'sb-tuning-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '',
})
export class TuningTab {}
