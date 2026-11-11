import {
  PartialsEnding, PartialsEndingRow, PartialsOddsSegment, PartialsRunnerEndings, PartialsShare,
} from '../../../api/models';
import { ABSENT, MINUS } from '../../../ui/format';

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
