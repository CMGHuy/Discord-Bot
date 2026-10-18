import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Confirmation } from '../../stores/trade-detail.store';
import { Panel } from '../../ui/layout';

export function hasLevelSources(target: readonly string[], stop: readonly string[], target2: readonly string[], confirmedBy: readonly Confirmation[]): boolean {
  return [target, stop, target2, confirmedBy].some(list => list.length > 0);
}
export function confirmationText(confirmation: Confirmation): string {
  return confirmation.horizon ? `${confirmation.strategy} (${confirmation.horizon})` : confirmation.strategy;
}

@Component({
  selector: 'sb-trade-level-sources', imports: [Panel], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sb-panel heading="Level sources">
      <dl>
        @for (row of rows(); track row.label) {
          @if (row.values.length) {
            <div [attr.data-source]="row.label"><dt>{{ row.label }}</dt><dd><ul>
              @for (value of row.values; track $index) { <li>{{ value }}</li> }
            </ul></dd></div>
          }
        }
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; overflow-wrap: anywhere; }
    dl { display: grid; gap: var(--space-10); margin: 0; }
    dl > div { min-width: 0; }
    dt { color: var(--text-secondary); }
    dt, dd { font-size: var(--text-table); }
    dd { margin: var(--space-4) 0 0; }
    ul { margin: 0; padding-inline-start: var(--space-20); }
    @container (min-width: 640px) {
      dl { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: var(--space-20); }
    }
  `,
})
export class LevelSourcesCard {
  readonly target = input<readonly string[]>([]);
  readonly stop = input<readonly string[]>([]);
  readonly target2 = input<readonly string[]>([]);
  readonly confirmedBy = input<readonly Confirmation[]>([]);
  protected readonly rows = computed(() => [
    { label: 'Target', values: this.target() }, { label: 'Stop', values: this.stop() },
    { label: 'Target 2', values: this.target2() },
    { label: 'Confirmed by', values: this.confirmedBy().map(confirmationText) },
  ]);
}
