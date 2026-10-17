import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { ABSENT } from '../../ui/format';
import { Panel } from '../../ui/layout';

export const SCORES_NOTE = 'Scores rank setups; they are not win probabilities.';
export function scoreWidth(value: number | null): number | null {
  return value === null || !Number.isFinite(value) ? null : Math.max(0, Math.min(100, value));
}

@Component({
  selector: 'sb-trade-scores-card', imports: [Panel], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sb-panel heading="Scores">
      <dl>
        <div data-score="confidence">
          <dt>Confidence</dt>
          <dd class="num">{{ scoreWidth(confidence()) === null ? absent : confidence() }}@if (level() !== null && scoreWidth(confidence()) !== null) { · Lv{{ level() }} }</dd>
          @if (scoreWidth(confidence()) !== null) { <span class="track" aria-hidden="true"><span class="fill" [style.width.%]="scoreWidth(confidence())"></span></span> }
        </div>
        <div data-score="quality">
          <dt>Quality</dt><dd class="num">{{ scoreWidth(quality()) === null ? absent : quality() }}</dd>
          @if (scoreWidth(quality()) !== null) { <span class="track" aria-hidden="true"><span class="fill" [style.width.%]="scoreWidth(quality())"></span></span> }
        </div>
        <div data-score="badge"><dt>Badge</dt><dd>{{ badge() ?? absent }}</dd></div>
      </dl>
      <p class="scores-foot muted">{{ scoresNote }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; overflow-wrap: anywhere; }
    dl { display: grid; gap: var(--space-10); margin: 0; }
    dl > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: var(--space-4); }
    dt { color: var(--text-secondary); }
    dt, dd { min-width: 0; font-size: var(--text-table); }
    dd { margin: 0; text-align: right; }
    .track { grid-column: 1 / -1; height: 4px; background: var(--surface-raised); }
    .fill { display: block; height: 100%; background: var(--text-secondary); }
    .scores-foot { margin: var(--space-10) 0 0; font-size: var(--text-chip); }
  `,
})
export class ScoresCard {
  readonly confidence = input<number | null>(null);
  readonly level = input<number | null>(null);
  readonly quality = input<number | null>(null);
  readonly badge = input<string | null>(null);
  protected readonly absent = ABSENT;
  protected readonly scoresNote = SCORES_NOTE;
  protected readonly scoreWidth = scoreWidth;
}
