import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Placeholder. NG36 makes this the tracer bullet — three MetricCards fed
 *  by /api/v1/cockpit through CockpitStore, refetching on an `account`
 *  event. Everything in Phase 4 repeats that shape. */
@Component({
  selector: 'sb-cockpit',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>Cockpit</h1><p class="todo">NG36</p>`,
  styles: `
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class Cockpit {}
