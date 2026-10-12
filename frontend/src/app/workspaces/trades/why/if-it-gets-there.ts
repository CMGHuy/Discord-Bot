import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Panel } from '../../../ui/layout';
import { num } from '../../../ui/format';

@Component({
  selector: 'sb-if-it-gets-there',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="If it gets there">
      <dl>
        <div>
          <dt>Continues past {{ levelWord() }} 1</dt>
          <dd class="sb-num">
            @if (target2() !== null) {
              next stop {{ fmtNum(target2()) }}
            } @else {
              <span class="absent">no further level found</span>
            }
          </dd>
        </div>
        <div>
          <dt>Reverses at {{ levelWord() }} 1</dt>
          <dd class="sb-num">pulls back toward {{ oppositeWord() }} at {{ fmtNum(stopLoss()) }}</dd>
        </div>
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    dl { display: grid; gap: var(--space-6); margin: 0; }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt, .absent { color: var(--text-secondary); }
    dt, dd { font-size: var(--text-table); }
    dd { margin: 0; color: var(--text); }
  `,
})
export class IfItGetsThere {
  readonly direction = input<string | null>(null);
  readonly target2 = input<number | null>(null);
  readonly stopLoss = input<number | null>(null);

  protected readonly fmtNum = num;
  protected readonly levelWord = computed(() => this.direction() === 'bearish' ? 'support' : 'resistance');
  protected readonly oppositeWord = computed(() => this.direction() === 'bearish' ? 'resistance' : 'support');
}
