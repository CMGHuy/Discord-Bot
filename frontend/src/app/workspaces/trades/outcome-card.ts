import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Leg, StatusEvent } from '../../stores/trade-detail.store';
import { ABSENT, num, rMultiple, share } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { reasonLabel } from './exit-reasons';
import { outcomeTone, StatusGroup, Tone } from './trade-figures';
import { IfItGetsThere } from './why/if-it-gets-there';
import { OutcomePath } from './why/outcome-path';

export interface LegRow { share: string; exit: string; r: string; tone: Tone; reason: string; }
export function legRows(legs: readonly Leg[]): LegRow[] {
  return legs.map(leg => {
    const settled = leg.exitPrice !== null;
    return {
      share: share(leg.fraction === null ? null : leg.fraction * 100),
      exit: num(leg.exitPrice),
      r: settled ? rMultiple(leg.r) : ABSENT,
      tone: settled ? outcomeTone(leg.r) : null,
      reason: settled ? reasonLabel(leg.reason) ?? ABSENT : ABSENT,
    };
  });
}

@Component({
  selector: 'sb-trade-outcome-card', imports: [Panel, IfItGetsThere, OutcomePath],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (group() === 'open' || group() === 'pending') {
      <sb-if-it-gets-there [direction]="direction()" [target2]="target2()" [stopLoss]="stopLoss()" />
    }
    @if (group() === 'closed' && rows().length) {
      <sb-panel heading="Exit legs">
        <div class="table-scroll">
          <table class="legs">
            <thead><tr><th scope="col">Share</th><th scope="col">Exit</th><th scope="col">R</th><th scope="col">Reason</th></tr></thead>
            <tbody>
              @for (row of rows(); track $index) {
                <tr><td class="num">{{ row.share }}</td><td class="num">{{ row.exit }}</td>
                  <td class="num" [class.pos]="row.tone === 'pos'" [class.neg]="row.tone === 'neg'">{{ row.r }}</td>
                  <td>{{ row.reason }}</td></tr>
              }
            </tbody>
          </table>
        </div>
      </sb-panel>
    }
    <sb-outcome-path [legs]="[]" [timeline]="events()" />
  `,
  styles: `
    :host { display: grid; grid-template-columns: minmax(0, 1fr); align-content: start; gap: var(--section-gap); min-width: 0; overflow-wrap: anywhere; }
    .table-scroll { max-width: 100%; overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th, td { padding: var(--space-6); text-align: right; vertical-align: top; }
    th { color: var(--text-secondary); font-weight: 400; }
    th:last-child, td:last-child { text-align: left; }
  `,
})
export class OutcomeCard {
  readonly group = input.required<StatusGroup>();
  readonly direction = input<string | null>(null);
  readonly target2 = input<number | null>(null);
  readonly stopLoss = input<number | null>(null);
  readonly legs = input<readonly Leg[]>([]);
  readonly timeline = input<readonly StatusEvent[]>([]);
  protected readonly rows = computed(() => legRows(this.legs()));
  protected readonly events = computed(() => [...this.timeline()]);
}
