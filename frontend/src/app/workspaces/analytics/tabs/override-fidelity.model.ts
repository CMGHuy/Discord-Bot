import {
  OverrideRowDto, OverrideStatus, OverrideSummary, OverrideVerdict, OverrideWaitingOn,
} from '../../../api/models';

/* v173 — copy and formatting for "Overrides vs engine". Every figure is
 * computed server-side; these helpers only word it. The copy is frozen by
 * the spec (§5 and its plan panel review): scoped to overrides already
 * made, never a policy, and no conclusion before one is recorded. */

export type Tone = 'pos' | 'neg' | 'neutral';

export const CAPTION = 'Compares the overrides you made with what the engine would have done. '
  + 'Past closes only, not advice on future ones. A close for a reason the engine cannot see '
  + '(a gap, earnings, needing the cash) can still be right. Figures are after modelled costs '
  + "and before tax. Dollars use the plan's modelled position size. Closing early can also "
  + 'change the tax holding period. There is no target number of overrides.';
export const EMPTY_COPY = 'No manual overrides in scope.';
export const APPROX_LABEL = 'estimated exit: daily close, not your fill';
export const COUNTS_HINT = 'counts ignore size';

/** Lower-case: each label also sits inside an exclusion sentence. */
export const STATUS_LABEL: Record<OverrideStatus, string> = {
  resolved: 'resolved', open: 'still open', unstamped: 'unstamped', stale: 'stale data',
  ambiguous: 'ambiguous', parity_mismatch: 'replay mismatch',
  split_affected: 'split or dividend adjusted', unreplayable: 'unreplayable',
};

/** The excluded statuses after `open`, in the order their notes are printed. */
const LEFT_OUT: OverrideStatus[] =
  ['unstamped', 'stale', 'ambiguous', 'parity_mismatch', 'split_affected', 'unreplayable'];

/** The `Waiting on:` items; `count` is never listed (the badge already says it). */
const WAITING_ITEM: Record<Exclude<OverrideWaitingOn, 'count'>, (v: OverrideVerdict) => string> = {
  weeks: (v) => `at least ${v.week_floor} distinct weeks (now ${v.weeks})`,
  open: (v) => `no open rows (now ${v.open_n} open)`,
  excluded: (v) => `left-out rows at most 20% (now ${Math.round(v.excluded_share * 100)}%)`,
};

const MINUS = '−';   // negatives line up with positives in tabular figures

const known = (x: number | null): x is number => x !== null && Number.isFinite(x);
const sign = (x: number): string => (x > 0 ? '+' : x < 0 ? MINUS : '');
const be = (n: number): string => (n === 1 ? 'is' : 'are');
const abs2 = (x: number | null): string => Math.abs(x ?? 0).toFixed(2);

function magnitude(x: number, currency: string): string {
  return currency + Math.abs(x).toLocaleString('en-US',
    { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fixed2(x: number | null): string {
  return known(x) ? `${sign(x)}${Math.abs(x).toFixed(2)}` : '—';
}

export const plural = (n: number, one: string, many: string): string =>
  `${n} ${n === 1 ? one : many}`;

export function signedUsd(x: number | null, currency: string): string {
  return known(x) ? sign(x) + magnitude(x, currency) : '—';
}

export function signedR(x: number | null): string {
  return known(x) ? `${sign(x)}${Math.abs(x).toFixed(2)} R` : '—';
}

export function netEffect(summary: OverrideSummary, currency: string): string {
  return `${signedUsd(summary.sum_delta_usd, currency)} · ${signedR(summary.sum_delta_r)}`;
}

export function netTone(verdict: OverrideVerdict, summary: OverrideSummary): Tone {
  if (verdict.state === 'WAITING') return 'neutral';
  const r = summary.sum_delta_r;
  if (!known(r) || r === 0) return 'neutral';
  return r > 0 ? 'pos' : 'neg';
}

function waitingBadge(v: OverrideVerdict): string {
  if (v.evaluable) {
    return `Floors met (${v.n} of ${v.needed}). Awaiting the one recorded evaluation. No conclusion yet.`;
  }
  if (v.n >= v.needed) {
    return `${v.n} of ${v.needed} counted. Waiting on other conditions. No conclusion yet.`;
  }
  return `${v.n} of ${v.needed} needed. No conclusion yet.`;
}

export function badgeCopy(verdict: OverrideVerdict, currency: string): string {
  if (verdict.state === 'WAITING') return waitingBadge(verdict);
  if (verdict.state === 'INCONCLUSIVE') return 'No clear difference vs the engine';
  const amount = known(verdict.sum_delta_usd)
    ? `${magnitude(verdict.sum_delta_usd, currency)} (${abs2(verdict.sum_delta_r)} R)`
    : `${abs2(verdict.sum_delta_r)} R`;
  return `Your overrides ${verdict.state === 'COST' ? 'cost' : 'saved'} ${amount} vs the engine`;
}

export function badgeTone(verdict: OverrideVerdict): Tone {
  if (verdict.state === 'COST') return 'neg';
  return verdict.state === 'SAVED' ? 'pos' : 'neutral';
}

export function waitingOnLine(verdict: OverrideVerdict): string | null {
  if (verdict.state !== 'WAITING' || verdict.evaluable || verdict.n < verdict.needed) return null;
  const items = verdict.waiting_on
    .filter((w): w is Exclude<OverrideWaitingOn, 'count'> => w !== 'count')
    .map((w) => WAITING_ITEM[w](verdict));
  return items.length ? `Waiting on: ${items.join('; ')}` : null;
}

export function recordedLine(verdict: OverrideVerdict): string | null {
  if (!verdict.recorded) return null;
  const [lo, hi] = verdict.ci ?? [null, null];
  const head = `Recorded on ${verdict.recorded_on} from ${verdict.n} overrides over ${verdict.weeks} weeks: `
    + `mean ${fixed2(verdict.mean_delta_r)} R per override, 95% CI ${fixed2(lo)} to ${fixed2(hi)} R. `
    + `Before costs: ${fixed2(verdict.mean_delta_r_gross)} R.`;
  const bars = verdict.bar_close_n;
  return bars > 0
    ? `${head} ${plural(bars, 'override', 'overrides')} priced from a bar close, not a quote.` : head;
}

export function liveHint(verdict: OverrideVerdict): string | null {
  return verdict.recorded ? `live, may have moved since recorded on ${verdict.recorded_on}` : null;
}

function bulkNotes(summary: OverrideSummary): string[] {
  return Object.entries(summary.bulk_dates).map(([day, n]) =>
    `${plural(n, 'close', 'closes')} from one bulk clear on ${day} `
    + `${n === 1 ? 'is not a decision, so it is' : 'are not decisions, so they are'} left out`);
}

function statusNotes(summary: OverrideSummary): string[] {
  return LEFT_OUT.filter((s) => summary.n_by_status[s] > 0).map((s) => {
    const n = summary.n_by_status[s];
    return `${plural(n, `${STATUS_LABEL[s]} row`, `${STATUS_LABEL[s]} rows`)} ${be(n)} left out`;
  });
}

export function exclusionNotes(summary: OverrideSummary, verdict: OverrideVerdict): string[] {
  const notes = bulkNotes(summary);
  if (summary.approx_n > 0) {
    notes.push(`${plural(summary.approx_n, 'estimated row', 'estimated rows')} ${be(summary.approx_n)} shown but not counted`);
  }
  if (verdict.open_n > 0) {
    notes.push(`${plural(verdict.open_n, 'row', 'rows')} ${be(verdict.open_n)} still open and not counted yet. `
      + 'No conclusion is recorded while any are open.');
  }
  return notes.concat(statusNotes(summary));
}

export function isCounted(row: OverrideRowDto): boolean {
  return !row.bulk && !row.approx && row.status === 'resolved';
}
