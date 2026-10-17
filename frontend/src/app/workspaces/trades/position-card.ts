import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Chip } from '../../ui/chip';
import { date, num, share, text } from '../../ui/format';
import { Panel } from '../../ui/layout';

export interface PositionFigures {
  status: string; shares: number | null; positionValue: number | null;
  dollarAtRisk: number | null; sizingMode: string | null; gapP90Pct: number | null;
  gapFragile: boolean | null; tp1Pct: number | null; breakevenTriggerPct: number | null;
  trailAtrMult: number | null; expiresOn: string | null; timeExitOn: string | null;
  holdCapBars: number | null;
}
export interface PositionRow { label: string; value: string; sub: string | null; fragile: boolean; }
export const SNAPSHOT_SENTENCE = 'Position size is snapshotted when the trade opens. A trade with no sizing snapshot was logged before that feature existed.';
export const PARTIAL_RISK_SUB = 'open shares, at original stop';

export function positionRows(f: PositionFigures): PositionRow[] {
  const rows: PositionRow[] = [];
  const add = (label: string, raw: unknown, value: string, sub: string | null = null, fragile = false): void => {
    if (raw !== null) rows.push({ label, value, sub, fragile });
  };
  const partial = f.status === 'PARTIAL';
  add(partial ? 'Open shares' : 'Shares', f.shares, num(f.shares, 0));
  add('Deployed', f.positionValue, num(f.positionValue));
  add('$ at risk', f.dollarAtRisk, num(f.dollarAtRisk), partial ? PARTIAL_RISK_SUB : null);
  add('Sizing mode', f.sizingMode, text(f.sizingMode));
  add('Gap risk (p90)', f.gapP90Pct, share(f.gapP90Pct, 2), null, f.gapFragile === true);
  add('TP1 closes', f.tp1Pct, share(f.tp1Pct));
  add('Break-even at', f.breakevenTriggerPct, `${share(f.breakevenTriggerPct)} of TP1`);
  add('Trail', f.trailAtrMult, `${num(f.trailAtrMult, 1)} × ATR`);
  add('Expires on', f.expiresOn, date(f.expiresOn));
  add('Time exit on', f.timeExitOn, date(f.timeExitOn));
  add('Hold cap', f.holdCapBars, `${num(f.holdCapBars, 0)} bars`);
  return rows;
}

@Component({
  selector: 'sb-trade-position-card', imports: [Panel, Chip], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sb-panel heading="Position">
      @if (figures().sizingMode === null) { <p class="section-help">{{ snapshotSentence }}</p> }
      <dl>
        @for (row of rows(); track row.label) {
          <div [attr.data-row]="row.label">
            <dt>{{ row.label }}</dt>
            <dd>
              <span class="num">{{ row.value }}</span>
              @if (row.fragile) {
                <sb-chip label="fragile" tone="warn" [caps]="false"
                  title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." />
              }
              @if (row.sub) { <span class="row-sub muted">{{ row.sub }}</span> }
            </dd>
          </div>
        }
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; overflow-wrap: anywhere; }
    @container (min-width: 640px) {
      dl { grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: var(--space-20); }
    }
    dl { display: grid; gap: var(--space-6); margin: 0; }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); min-width: 0; }
    dt { color: var(--text-secondary); }
    dt, dd { font-size: var(--text-table); min-width: 0; }
    dd { margin: 0; text-align: right; }
    .row-sub { display: block; }
    sb-chip { display: inline-block; margin-left: var(--space-6); }
  `,
})
export class PositionCard {
  readonly figures = input.required<PositionFigures>();
  protected readonly rows = computed(() => positionRows(this.figures()));
  protected readonly snapshotSentence = SNAPSHOT_SENTENCE;
}
