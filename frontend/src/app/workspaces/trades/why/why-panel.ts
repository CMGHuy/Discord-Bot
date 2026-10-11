import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { CalendarRow, GateRow } from '../../../api/models';
import { ConfidenceFactor, Confirmation, QualityFactor } from '../../../stores/trade-detail.store';
import { Panel } from '../../../ui/layout';
import { Chip } from '../../../ui/chip';
import { InlineMd } from '../../../ui/inline-md';
import { num, signed, text } from '../../../ui/format';

export type WhySection = 'levels' | 'confidence' | 'gates' | 'calendar' | 'explanation';
export const WHY_SECTIONS: WhySection[] = ['levels', 'confidence', 'gates', 'calendar', 'explanation'];
export const GATE_CAVEAT = "Margins are measured against today's thresholds, not the ones in force when this plan was issued.";

export function marginTone(
  status: string | null | undefined,
  barsToExpiry: number | null | undefined,
  sessionsSinceCreated: number | null | undefined,
): 'signed' | 'neutral' | 'indicative' {
  if (!['PENDING', 'ACTIVE', 'PARTIAL'].includes(status ?? '')) return 'neutral';
  if (status === 'PENDING' && barsToExpiry === 0) return 'neutral';
  if (sessionsSinceCreated == null || sessionsSinceCreated > 5) return 'indicative';
  return 'signed';
}

@Component({
  selector: 'sb-why-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Chip, InlineMd],
  template: `
    @if (has('levels')) {
      <sb-panel heading="Levels & methods">
        <dl class="levels">
          <div><dt>{{ entry() === null ? 'Trigger' : 'Entry' }}</dt><dd>{{ fmtNum(entry() ?? trigger()) }}</dd></div>
          <div><dt>{{ stopLabel() }}</dt><dd>{{ fmtNum(stop()) }}</dd></div>
          <div><dt>Target 1</dt><dd>{{ fmtNum(target1()) }}</dd></div>
          <div><dt>Target 2</dt><dd>{{ fmtNum(target2()) }}</dd></div>
          @if (acceptanceLevel() !== null) {
            <div><dt>Acceptance level</dt><dd>{{ fmtNum(acceptanceLevel()) }}</dd></div>
          }
        </dl>
        @for (source of sources(); track source.label) {
          <p class="source"><span class="muted">{{ source.label }}:</span> {{ source.values.join(', ') }}</p>
        }
        @if (confirmedBy().length) {
          <p class="source"><span class="muted">Confirmed by:</span>
            @for (confirmation of confirmedBy(); track $index) {
              <span>{{ confirmation.strategy }}@if (confirmation.horizon) { ({{ confirmation.horizon }}) }@if (!$last) {, }</span>
            }
          </p>
        }
      </sb-panel>
    }
    @if (has('confidence') && (pointRows().length || confidenceFactors().length || qualityFactors().length)) {
      <sb-panel [heading]="pointRows().length || confidenceFactors().length ? 'Confidence breakdown' : null">
        <div class="confidence">
          @if (pointRows().length) {
            @for (row of pointRows(); track row.factor) {
              <div class="factor-row">
                <span>{{ row.factor }}
                  @if (row.unevaluated) {
                    <sb-chip label="unevaluated" tone="muted" [caps]="false" title="no data — neutral points awarded" />
                  }
                </span>
                <span class="point sb-num" [class.muted]="row.unevaluated">{{ fmtSigned(row.points, 0) }}</span>
                @if (row.note) { <span class="note muted">{{ row.note }}</span> }
              </div>
            }
            <div class="factor-row total"><span>Total</span><strong class="sb-num">{{ fmtSigned(totalPoints(), 0) }}</strong></div>
          } @else {
            @for (factor of confidenceFactors(); track $index) {
              <div class="factor-row"><span>{{ factor.factor }}</span><span class="muted">{{ factor.note }}</span></div>
            }
          }
        </div>
        @if (qualityFactors().length) {
          <section class="quality">
            <h3 class="sb-label">Quality breakdown</h3>
            @for (factor of qualityFactors(); track $index) {
              <div class="factor-row"><span>{{ factor.label }}</span><span class="sb-num">{{ fmtSigned(factor.points, 0) }}</span></div>
            }
          </section>
        }
      </sb-panel>
    }
    @if (has('gates')) {
      <sb-panel heading="Gate margins (vs today's thresholds)">
        @if (tone() === 'indicative') { <sb-chip class="indicative" label="indicative" [caps]="false" /> }
        <div class="gates">
          @for (gate of gates(); track $index) {
            <div class="gate-row">
              <div class="gate-summary">
                <span>{{ gate.label }}</span>
                @if (!gate.applies) { <sb-chip label="off" [caps]="false" title="off in current config" /> }
                <span>Value <span class="sb-num">{{ gateValue(gate.value) }}</span></span>
                <span>Threshold <span class="sb-num">{{ fmtNum(gate.threshold) }}</span></span>
                <span>Margin <span class="margin sb-num" [class.pos]="coloredMargin(gate) > 0" [class.neg]="coloredMargin(gate) < 0">{{ fmtSigned(gate.margin) }}</span></span>
              </div>
              @if (gate.parts.length) {
                <p class="parts">@for (part of gate.parts; track $index) {
                  <span>{{ part.label }}: {{ gateValue(part.value) }}@if (!$last) {; }</span>
                }</p>
              }
              @if (gate.note) { <p class="note muted">{{ gate.note }}</p> }
            </div>
          } @empty { <p>—</p> }
        </div>
        <p class="caveat muted">{{ caveat }}</p>
      </sb-panel>
    }
    @if (has('calendar')) {
      <sb-panel heading="Calendar in the holding window">
        @for (row of calendar(); track $index) {
          <p><time [attr.datetime]="row.date">{{ row.date }}</time> {{ row.label }}</p>
        } @empty { <p>None in the window</p> }
      </sb-panel>
    }
    @if (has('explanation') && explanation() !== null) {
      <sb-panel heading="Why this trade"><sb-inline-md [text]="explanation()" /></sb-panel>
    }
  `,
  styles: `
    :host { display: grid; gap: var(--section-gap); min-width: 0; }
    dl, p { margin: 0; }
    .levels { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: var(--space-14); }
    dt, .muted { color: var(--text-secondary); }
    dd { margin: var(--space-4) 0 0; font-variant-numeric: tabular-nums; }
    .source { margin-top: var(--space-10); }
    .factor-row { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: var(--space-8); padding: var(--space-4) 0; }
    .factor-row .note { grid-column: 1 / -1; }
    .total { border-top: 1px solid var(--border); margin-top: var(--space-8); }
    .quality { padding-top: var(--space-14); }
    h3 { margin: 0 0 var(--space-8); }
    .gate-row + .gate-row { border-top: 1px solid var(--border); margin-top: var(--space-10); padding-top: var(--space-10); }
    .gate-summary { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-8) var(--space-14); }
    .parts, .note, .caveat { margin-top: var(--space-8); }
    .indicative { display: block; margin-bottom: var(--space-10); }
  `,
})
export class WhyPanel {
  readonly sections = input<WhySection[]>(WHY_SECTIONS);
  readonly status = input<string | null>(null);
  readonly barsToExpiry = input<number | null>(null);
  readonly sessionsSinceCreated = input<number | null>(null);
  readonly entry = input<number | null>(null);
  readonly trigger = input<number | null>(null);
  readonly stop = input<number | null>(null);
  readonly target1 = input<number | null>(null);
  readonly target2 = input<number | null>(null);
  readonly acceptanceLevel = input<number | null>(null);
  readonly stopLabel = input('Stop');
  readonly targetSources = input<string[]>([]);
  readonly stopSources = input<string[]>([]);
  readonly target2Sources = input<string[]>([]);
  readonly confirmedBy = input<Confirmation[]>([]);
  readonly confidencePoints = input<Record<string, number> | null>(null);
  readonly confidenceUnevaluated = input<string[]>([]);
  readonly confidenceFactors = input<ConfidenceFactor[]>([]);
  readonly qualityFactors = input<QualityFactor[]>([]);
  readonly gates = input<GateRow[]>([]);
  readonly calendar = input<CalendarRow[]>([]);
  readonly explanation = input<string | null>(null);

  protected readonly fmtNum = num;
  protected readonly fmtSigned = signed;
  protected readonly caveat = GATE_CAVEAT;
  protected readonly tone = computed(() => marginTone(this.status(), this.barsToExpiry(), this.sessionsSinceCreated()));
  protected readonly sources = computed(() => [
    { label: 'Target confirmed by', values: this.targetSources() },
    { label: 'Stop confirmed by', values: this.stopSources() },
    { label: 'Target 2 confirmed by', values: this.target2Sources() },
  ].filter(row => row.values.length));
  protected readonly pointRows = computed(() => Object.entries(this.confidencePoints() ?? {}).map(([factor, points]) => ({
    factor, points,
    note: this.confidenceFactors().find(row => row.factor === factor)?.note ?? null,
    unevaluated: this.confidenceUnevaluated().includes(factor),
  })));
  protected readonly totalPoints = computed(() => this.pointRows().reduce((sum, row) => sum + row.points, 0));

  protected has(section: WhySection): boolean { return this.sections().includes(section); }
  protected gateValue(value: number | string | null): string { return typeof value === 'number' ? num(value) : text(value); }
  protected coloredMargin(gate: GateRow): number {
    return this.tone() === 'signed' && gate.applies ? gate.margin ?? 0 : 0;
  }
}
