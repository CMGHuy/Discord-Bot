import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { num, share, text } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

export const PAPER_LINE = 'Paper plan — this page places no orders.';

export function entryTypeWord(entryType: string | null, direction: string | null): string {
  if (entryType === 'market') return 'At market';
  const words: Record<string, Record<string, string>> = {
    stop_entry: { bullish: 'Buy stop', bearish: 'Sell stop', fallback: 'Stop entry' },
    limit: { bullish: 'Buy limit', bearish: 'Sell limit', fallback: 'Limit entry' },
  };
  if (entryType === null) return text(entryType);
  if (!Object.hasOwn(words, entryType)) return entryType;
  const side = direction === 'bullish' || direction === 'bearish' ? direction : 'fallback';
  return words[entryType][side];
}

@Component({
  selector: 'sb-levels-block',
  imports: [Panel],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sb-panel heading="Levels">
      <dl>
        <div><dt>Order</dt><dd>{{ orderWord(entryType(), direction()) }}</dd></div>
        @if (trigger() !== null) {
          <div><dt>Trigger</dt><dd class="num">{{ fmt(trigger()) }}</dd></div>
        }
        <div><dt>Entry</dt><dd class="num">{{ fmt(entry()) }}</dd></div>
        <div><dt>{{ stopLabel() }}</dt><dd class="num neg">{{ fmt(stop()) }}</dd></div>
        <div><dt>Target 1</dt><dd class="num pos">{{ fmt(target1()) }}</dd></div>
        <div><dt>Target 2</dt><dd class="num pos">{{ fmt(target2()) }}</dd></div>
        <div><dt>R:R</dt><dd class="num">{{ fmt(riskReward()) }}</dd></div>
        @if (acceptanceLevel() !== null) {
          <div><dt>Acceptance level</dt><dd class="num">{{ fmt(acceptanceLevel()) }}</dd></div>
        }
        @if (tp1Pct() !== null) {
          <div><dt>TP1 closes</dt><dd class="num">{{ fmtShare(tp1Pct()) }}</dd></div>
        }
        @if (breakevenTriggerPct() !== null) {
          <div><dt>Break-even at</dt><dd class="num">{{ fmtShare(breakevenTriggerPct()) }} of TP1</dd></div>
        }
      </dl>
      <p class="paper-line muted">{{ paperLine }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; }
    dl { display: grid; gap: var(--space-6); }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt, dd { font-size: var(--text-table); }
    dt { color: var(--text-secondary); }
    dd { text-align: right; }
    .paper-line { margin-top: var(--space-10); font-size: var(--text-table); line-height: 1.6; }
  `,
})
export class LevelsBlock {
  readonly direction = input<string | null>(null);
  readonly entryType = input<string | null>(null);
  readonly trigger = input<number | null>(null);
  readonly entry = input<number | null>(null);
  readonly stop = input<number | null>(null);
  readonly target1 = input<number | null>(null);
  readonly target2 = input<number | null>(null);
  readonly riskReward = input<number | null>(null);
  readonly acceptanceLevel = input<number | null>(null);
  readonly tp1Pct = input<number | null>(null);
  readonly breakevenTriggerPct = input<number | null>(null);
  readonly stopLabel = input('Stop');
  protected readonly fmt = num;
  protected readonly fmtShare = share;
  protected readonly orderWord = entryTypeWord;
  protected readonly paperLine = PAPER_LINE;
}
