import type { CancelFigure, CancelOutcome, CancelPlanRow } from '../../api/models';
import type { CancelFilter } from '../../stores/cancels.store';

const EXCLUDED: Record<string, string> = {
  no_bars: 'no bars', split_guard: 'split in window', bad_levels: 'bad levels',
  unknown_horizon: 'unknown horizon', no_cancel_entry: 'no cancel-day bar',
};
const CANCEL_WORDS: Record<CancelOutcome, string> = {
  right: 'Right cancel', wrong: 'Wrong cancel',
  unresolved: 'Unresolved', untriggered_after_cancel: 'Untriggered after cancel',
};
// risk_cap: the cap limits dollar risk, so a TP1 hit is the outcome of a
// skipped setup, never a mistaken cancel (spec: What risk_cap precision means).
const SETUP_WORDS: Record<CancelOutcome, string> = {
  ...CANCEL_WORDS, right: 'Setup lost', wrong: 'Setup reached TP1',
};

const HEADLINE_REASONS = ['risk_cap', 'invalidated', 'expired'];

/** `62% of 37`, or `— of 0` when there is no precision (never 0%). */
export function figureText(f: CancelFigure): string {
  return f.precision === null ? `— of ${f.n}` : `${Math.round(f.precision * 100)}% of ${f.n}`;
}

/** The 95% interval of a precision, in whole percent. */
export function ciText(ci: [number, number] | null): string {
  if (ci === null) return '95% CI —';
  return `95% CI ${Math.round(ci[0] * 100)}–${Math.round(ci[1] * 100)}%`;
}

/** Signed R to two places: `+1.85R`, `-3.40R`, `0.00R`; a dash for none. */
export function rText(r: number | null): string {
  if (r === null) return '—';
  return `${r > 0 ? '+' : ''}${r.toFixed(2)}R`;
}

/** The verdict wording of a replayed row. */
export function verdictLabel(row: CancelPlanRow): string {
  if (row.excluded !== null || row.outcome === null) {
    const code = row.excluded ?? 'unscored';
    return `Excluded: ${EXCLUDED[code] ?? code}`;
  }
  const words = row.reason === 'risk_cap' ? SETUP_WORDS : CANCEL_WORDS;
  return words[row.outcome] + (row.tie ? ' (tie)' : '');
}

function inPopulation(row: CancelPlanRow, card: CancelFilter['card']): boolean {
  if (card === 'risk_cap_fill') return row.reason === 'risk_cap' && row.entry_model === 'cancel_fill';
  if (card !== null) return row.reason === card && row.entry_model === 'trigger';
  return HEADLINE_REASONS.includes(row.reason) && row.entry_model === 'trigger';
}

function splitValue(row: CancelPlanRow, dim: 'origin' | 'direction' | 'horizon'): string {
  if (dim === 'horizon') return row.horizon_key;
  return row[dim];
}

/** Rows behind the clicked figure; card, outcome and split combine (AND). */
export function filterRows(rows: CancelPlanRow[], f: CancelFilter): CancelPlanRow[] {
  if (f.card === null && f.outcome === null && f.split === null) return [...rows];
  const { outcome, split } = f;
  return rows.filter((row) =>
    inPopulation(row, f.card)
    && (outcome === null || row.outcome === outcome)
    && (split === null || splitValue(row, split.dim) === split.value));
}
