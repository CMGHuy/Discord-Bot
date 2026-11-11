import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import {
  PartialsEnding, PartialsEndingRow, PartialsOddsSegment, PartialsRunnerEndings, PartialsShare,
} from '../../../api/models';
import { ABSENT, MINUS } from '../../../ui/format';
import { Hint } from '../../../ui/hint';

/* v219 — Runner endings: how each closed runner ended (TP2, trailing stop,
 * breakeven floor, other) and how many gave back a good move. Every figure is
 * computed server-side (`partials.py::runner_endings`); these helpers only
 * format it. Statistics only: nothing here is a gate or a rule. */

export type EndingTone = 'pos' | 'neg' | 'warn' | 'accent';
export interface EndingMeta { label: string; card: string; tone: EndingTone; hint: string; }

export const RUNNER_ENDINGS_HINT =
  'How each closed runner ended, and the R behind each ending. R, before commissions and tax.';
export const PEAK_HINT = 'The peak is known only afterwards; it is not a target.';
export const BREAKEVEN_HINT = 'The floor locks ⅔ of the TP1 gain.';
export const ODDS_HINT = 'Read off this book; any threshold taken from it is screened on backtest data first.';
const GIVEBACK_HINT = 'Got at least half way from TP1 to TP2, then closed below the TP1 price, whatever '
  + 'the ending. Its share is of the decidable runners, not of the four endings.';

export const ENDING_META: Record<PartialsEnding, EndingMeta> = {
  tp2: { label: 'TP2', card: 'Runner at TP2', tone: 'pos', hint: '' },
  trail: { label: 'Trailing stop', card: 'Trailing stop', tone: 'accent', hint: '' },
  floor: { label: 'Breakeven', card: 'Runner at breakeven', tone: 'neg', hint: BREAKEVEN_HINT },
  other: { label: 'Other', card: 'Other', tone: 'warn', hint: 'Stall, time, manual and unrecorded closes.' },
  giveback: { label: 'Giveback (any ending)', card: 'Giveback', tone: 'warn', hint: GIVEBACK_HINT },
};

export interface EndingCardView {
  ending: PartialsEnding; label: string; tone: EndingTone; hint: string;
  share: string; interval: string; count: string; thin: boolean;
}
export interface ScorecardRowView {
  ending: PartialsEnding; label: string; tone: EndingTone; hint: string; thin: boolean; cross: boolean;
  n: string; share: string; interval: string; of: string;
  /** Avg R, Med R, Total R, vs all-out, Best R seen, % to TP2, Gave back, Sessions. */
  cells: string[];
}
export interface OddsSegmentView {
  ending: PartialsEnding; label: string; tone: EndingTone; grow: number; text: string; interval: string;
}
export interface OddsBarView {
  level: number; label: string; n: number; thin: boolean; aria: string; segments: OddsSegmentView[];
}

type Pct = Pick<PartialsShare, 'share' | 'lo' | 'hi'>;

export const shareText = (s: Pct): string => (s.share === null ? ABSENT : `${s.share.toFixed(1)}%`);
export const intervalText = (s: Pct): string =>
  (s.lo === null || s.hi === null ? '' : `95% CI ${s.lo.toFixed(1)}–${s.hi.toFixed(1)}%`);
const signedR = (v: number | null): string =>
  (v === null ? ABSENT : `${v < 0 ? MINUS : '+'}${Math.abs(v).toFixed(2)}R`);
const plainR = (v: number | null): string =>
  (v === null ? ABSENT : `${v < 0 ? MINUS : ''}${Math.abs(v).toFixed(2)}R`);
const pctCell = (v: number | null): string => (v === null ? ABSENT : `${v.toFixed(1)}%`);
const sessionsCell = (v: number | null): string =>
  (v === null ? ABSENT : Number.isInteger(v) ? String(v) : v.toFixed(1));
const countText = (ending: PartialsEnding, s: PartialsShare): string =>
  `${s.n} of ${s.denominator} ${ending === 'giveback' ? 'decidable' : 'runners'}`;

export function endingCards(block: PartialsRunnerEndings): EndingCardView[] {
  return block.cards.map((c) => {
    const meta = ENDING_META[c.ending];
    return { ending: c.ending, label: meta.card, tone: meta.tone, hint: meta.hint,
      share: shareText(c), interval: intervalText(c), count: countText(c.ending, c), thin: c.thin };
  });
}

function scoreCells(r: PartialsEndingRow): string[] {
  return [signedR(r.avg_r), signedR(r.median_r), signedR(r.total_r), signedR(r.vs_all_out),
    signedR(r.best_r), pctCell(r.progress), plainR(r.gave_back), sessionsCell(r.sessions)];
}

export function scorecardRows(block: PartialsRunnerEndings): ScorecardRowView[] {
  return block.rows.map((r) => {
    const meta = ENDING_META[r.ending];
    const cross = r.ending === 'giveback';
    return { ending: r.ending, label: meta.label, tone: meta.tone, hint: meta.hint, thin: r.thin, cross,
      n: String(r.n), share: shareText(r), interval: intervalText(r),
      of: cross ? `of ${r.denominator} decidable` : '', cells: scoreCells(r) };
  });
}

function oddsSegment(seg: PartialsOddsSegment): OddsSegmentView {
  const meta = ENDING_META[seg.ending];
  return { ending: seg.ending, label: meta.label, tone: meta.tone, grow: seg.share ?? 0,
    text: `${meta.label} ${seg.n} · ${shareText(seg)}`, interval: intervalText(seg) };
}

export function oddsBars(block: PartialsRunnerEndings): OddsBarView[] {
  return block.odds.map((bar) => {
    const label = `Got ${bar.level}% of the way to TP2`;
    const segments = bar.split.map(oddsSegment);
    return { level: bar.level, label, n: bar.n, thin: bar.thin, segments,
      aria: `${label}, N ${bar.n}: ${segments.map((s) => s.text).join(', ')}` };
  });
}

export function exclusionNote(block: PartialsRunnerEndings): string {
  const x = block.excluded;
  return `${block.n} closed runners with a TP2 (${x.no_tp2} closed without a TP2 left out). `
    + `Best R seen, % to TP2, Gave back, Giveback and the odds read ${block.decidable} decidable runners; `
    + `left out: ${x.manual_close} manual closes, ${x.unpathed} without a price path, `
    + `${x.runner_r_unavailable} without a runner price (counted in N and Share only), `
    + `${x.no_tp2_distance} with TP2 at or below TP1.`;
}

@Component({
  selector: 'sb-runner-endings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    <div class="cards">@for (card of cards(); track card.ending) {
      <article class="card" [attr.data-tone]="card.tone" [class.thin]="card.thin">
        <p class="card-label"><span class="card-name">{{ card.label }}</span>
          @if (card.hint) { <sb-hint [text]="card.hint" [label]="card.label + ' definition'" /> }</p>
        <p class="card-share">{{ card.share }}</p>
        <p class="card-interval">{{ card.interval }}</p>
        <p class="card-count">{{ card.count }}@if (card.thin) { <span class="thin-mark" [title]="thinTitle()">thin</span> }</p>
      </article>
    }</div>
    <div class="table-scroll"><table class="scorecard">
      <thead><tr>
        <th class="pin" scope="col">Ending</th><th scope="col">N</th><th scope="col">Share</th>
        <th scope="col">Avg R</th><th scope="col">Med R</th><th scope="col">Total R</th><th scope="col">vs all-out</th>
        <th scope="col">Best R seen <sb-hint [text]="peakHint" label="Best R seen definition" /></th>
        <th scope="col">% to TP2 <sb-hint [text]="peakHint" label="% to TP2 definition" /></th>
        <th scope="col">Gave back</th><th scope="col">Sessions</th>
      </tr></thead>
      <tbody>@for (row of rows(); track row.ending) {
        <tr [class.thin]="row.thin" [class.cross]="row.cross">
          <th class="pin" scope="row"><span class="key" [attr.data-tone]="row.tone"></span><span class="row-label">{{ row.label }}</span>
            @if (row.hint) { <sb-hint [text]="row.hint" [label]="row.label + ' definition'" /> }
            @if (row.thin) { <span class="thin-mark" [title]="thinTitle()">thin</span> }</th>
          <td class="num">{{ row.n }}</td>
          <td class="num share">{{ row.share }}@if (row.of) { <span class="of">{{ row.of }}</span> }<small>{{ row.interval }}</small></td>
          @for (cell of row.cells; track $index) { <td class="num">{{ cell }}</td> }
        </tr>
      }</tbody>
    </table></div>
    <div class="odds">
      <p class="odds-title">If the runner got this far, how it ended</p>
      @for (bar of odds(); track bar.level) {
        <div class="odds-row" [class.thin]="bar.thin">
          <p class="odds-label">{{ bar.label }} <span class="odds-n">N {{ bar.n }}</span>
            @if (bar.thin) { <span class="thin-mark" [title]="thinTitle()">thin</span> }</p>
          <div class="track" role="img" [attr.aria-label]="bar.aria">@for (s of bar.segments; track s.ending) {
            @if (s.grow > 0) { <span class="seg" [attr.data-tone]="s.tone" [style.flex-grow]="s.grow"></span> }
          }</div>
          <ul class="legend">
            @if (bar.n === 0) { <li class="none">no runner got this far</li> }
            @for (s of bar.segments; track s.ending) {
              <li><span class="key" [attr.data-tone]="s.tone"></span><span>{{ s.text }}</span><small>{{ s.interval }}</small></li>
            }
          </ul>
        </div>
      }
      <p class="note">{{ oddsHint }}</p>
    </div>
    <p class="note">{{ exclusions() }}</p>
  `,
  styles: `:host{display:grid;grid-template-columns:minmax(0,1fr);gap:var(--space-14);min-width:0}[data-tone='pos']{--tone:var(--pos)}[data-tone='neg']{--tone:var(--neg)}[data-tone='warn']{--tone:var(--warn)}[data-tone='accent']{--tone:var(--accent)}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:var(--space-10)}.card{min-width:0;padding:var(--space-10);border:var(--panel-border);border-top:3px solid var(--tone,var(--accent));border-radius:var(--panel-radius)}.card p{margin:0}.card-label{display:flex;align-items:center;flex-wrap:wrap;gap:var(--space-4);font-size:var(--text-chip);color:var(--text-secondary)}.card-share{margin-top:var(--space-4);font-size:var(--text-metric);font-variant-numeric:tabular-nums}.card.thin .card-share{color:var(--text-faint)}.card-interval,.card-count{font-size:var(--text-micro);color:var(--text-secondary);overflow-wrap:anywhere}.key{display:inline-block;flex:none;width:10px;height:10px;margin-right:var(--space-6);border-radius:var(--radius-sm);background:var(--tone,var(--accent))}.thin-mark{margin-left:var(--space-4);font-size:var(--text-micro);color:var(--text-faint);text-transform:uppercase}.table-scroll{overflow-x:auto;max-width:100%}.scorecard{width:100%;border-collapse:separate;border-spacing:0;font-size:var(--text-table)}.scorecard th,.scorecard td{padding:var(--space-4) var(--space-8);text-align:left;border-bottom:1px solid var(--border);white-space:nowrap;vertical-align:top}.scorecard .num{text-align:right;font-variant-numeric:tabular-nums}.scorecard .pin{position:sticky;left:0;z-index:1;background:var(--panel-bg);white-space:normal;min-width:8rem;max-width:11rem}.scorecard small,.scorecard .of{display:block;font-size:var(--text-micro);color:var(--text-faint)}.scorecard tr.thin td{color:var(--text-faint)}.scorecard tr.cross>*{border-top:2px solid var(--border-strong)}.odds{display:grid;gap:var(--space-10);min-width:0}.odds p{margin:0}.odds-title{font-size:var(--text-chip);color:var(--text-secondary)}.odds-row{display:grid;grid-template-columns:minmax(10rem,14rem) minmax(0,1fr);gap:var(--space-4) var(--space-10);align-items:center}.odds-row .legend{grid-column:2}.odds-label{font-size:var(--text-table);overflow-wrap:anywhere}.odds-n{color:var(--text-secondary);font-variant-numeric:tabular-nums}.track{display:flex;gap:2px;height:14px;overflow:hidden;background:var(--bg);border-radius:var(--radius-sm)}.seg{display:block;flex-basis:0;min-width:2px;background:var(--tone,var(--accent))}.odds-row.thin .track{opacity:.6}.legend{display:flex;flex-wrap:wrap;gap:var(--space-6) var(--space-14);margin:0;padding:0;list-style:none;font-size:var(--text-chip)}.legend li{display:inline-flex;align-items:baseline;flex-wrap:wrap;gap:var(--space-4);min-width:0;color:var(--text-secondary)}.legend li span:not(.key){overflow-wrap:anywhere}.legend small{color:var(--text-faint);font-size:var(--text-micro)}.legend .none{color:var(--text-faint);font-style:italic}.note{margin:0;font-size:var(--text-micro);color:var(--text-faint)}@media(max-width:1023px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:639px){.odds-row{grid-template-columns:minmax(0,1fr)}.odds-row .legend{grid-column:1}}`,
})
export class RunnerEndings {
  readonly block = input.required<PartialsRunnerEndings>();
  readonly thinN = input.required<number>();
  readonly peakHint = PEAK_HINT;
  readonly oddsHint = ODDS_HINT;
  readonly cards = computed(() => endingCards(this.block()));
  readonly rows = computed(() => scorecardRows(this.block()));
  readonly odds = computed(() => oddsBars(this.block()));
  readonly exclusions = computed(() => exclusionNote(this.block()));
  readonly thinTitle = computed(() => `Under N=${this.thinN()}: shown, not trusted.`);
}
