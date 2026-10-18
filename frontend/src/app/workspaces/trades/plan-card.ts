import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { num, pct } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { orderWording, pctFrom, Tone } from './trade-figures';
import { PAPER_LINE } from './why/levels-block';

export interface PlanFigures {
  direction: string | null; status: string; entryType: string | null;
  trigger: number | null; entry: number | null; riskStop: number | null;
  stopLoss: number | null; workingStop: number | null; target1: number | null;
  target2: number | null; acceptance: number | null; riskReward: number | null;
  riskPerShare: number | null; rewardPerShare: number | null;
}
export interface PlanRow {
  level: string; price: number | null; pctFromEntry: number | null; tone: Tone; note: string | null;
}
export const GAP_NOTE = 'A gap through the trigger fills at the open, not at entry.';

function workingStopDiffers(f: PlanFigures): boolean {
  return f.workingStop !== null && f.riskStop !== null && f.workingStop !== f.riskStop;
}
export function gapNoteApplies(f: PlanFigures): boolean {
  return f.trigger !== null && f.trigger !== f.entry;
}
export function planRows(f: PlanFigures): PlanRow[] {
  const row = (level: string, price: number | null, tone: Tone = null, note: string | null = null): PlanRow =>
    ({ level, price, pctFromEntry: level === 'Entry' ? null : pctFrom(f.entry, price), tone, note });
  const rows = [row('Order', null, null, orderWording(f.entryType, f.direction, f.trigger ?? f.entry))];
  if (gapNoteApplies(f)) rows.push(row('Trigger', f.trigger));
  rows.push(row('Entry', f.entry), row('Stop', f.riskStop ?? f.stopLoss, 'neg'));
  if (workingStopDiffers(f)) rows.push(row('Working stop', f.workingStop, null, `(was ${num(f.riskStop)})`));
  rows.push(row('Target 1', f.target1, 'pos'));
  if (f.target2 !== null) rows.push(row('Target 2', f.target2, 'pos'));
  if (f.acceptance !== null) rows.push(row('Acceptance', f.acceptance));
  return rows;
}
export function restingStopLine(f: PlanFigures): string | null {
  if (!['ACTIVE', 'PARTIAL'].includes(f.status) || !workingStopDiffers(f)) return null;
  return `Move your resting stop to ${num(f.workingStop)}`;
}
export function rrLine(f: PlanFigures): string | null {
  if (f.riskReward === null) return null;
  const ratio = `R:R ${num(f.riskReward)}`;
  return f.riskPerShare !== null && f.rewardPerShare !== null
    ? `${ratio} · risk ${num(f.riskPerShare)} / reward ${num(f.rewardPerShare)} per share` : ratio;
}

@Component({
  selector: 'sb-trade-plan-card', imports: [Panel], changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <sb-panel heading="Plan">
      <div class="table-scroll">
        <table class="levels">
          <thead><tr><th scope="col">Level</th><th scope="col">Price</th><th scope="col">% from entry</th></tr></thead>
          <tbody>
            @for (row of rows(); track row.level) {
              <tr [attr.data-level]="row.level">
                <th scope="row">{{ row.level }}</th>
                <td class="num price" [class.pos]="row.tone === 'pos'" [class.neg]="row.tone === 'neg'">
                  @if (row.level === 'Order') { {{ row.note }} } @else {
                    {{ fmt(row.price) }} @if (row.note) { <span class="muted">{{ row.note }}</span> }
                  }
                </td>
                <td class="num from">@if (row.pctFromEntry !== null) { {{ fmtPct(row.pctFromEntry) }} }</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
      @if (resting(); as line) { <p class="resting-stop">{{ line }}</p> }
      @if (ratio(); as line) { <p class="rr-line">{{ line }}</p> }
      @if (gap()) { <p class="gap-line muted">{{ gapNote }}</p> }
      <p class="paper-line muted">{{ paperLine }}</p>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; overflow-wrap: anywhere; }
    .table-scroll { max-width: 100%; overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    th, td { padding: var(--space-6); text-align: right; vertical-align: top; }
    th:first-child { text-align: left; color: var(--text-secondary); font-weight: 400; }
    p { margin-top: var(--space-10); font-size: var(--text-table); line-height: 1.6; }
    .resting-stop { color: var(--text); font-weight: 600; }
  `,
})
export class PlanCard {
  readonly figures = input.required<PlanFigures>();
  protected readonly rows = computed(() => planRows(this.figures()));
  protected readonly resting = computed(() => restingStopLine(this.figures()));
  protected readonly ratio = computed(() => rrLine(this.figures()));
  protected readonly gap = computed(() => gapNoteApplies(this.figures()));
  protected readonly fmt = num;
  protected readonly fmtPct = pct;
  protected readonly paperLine = PAPER_LINE;
  protected readonly gapNote = GAP_NOTE;
}
