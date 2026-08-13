import { ColumnDef } from '../../ui/data-table/data-table.types';
import { ABSENT, date } from '../../ui/format';
import {
  ConfidenceRow,
  DecileRow,
  DriftRow,
  StrategyRow,
  TierRow,
} from '../../stores/analytics.store';

/* Column declarations for the Analytics tables, kept out of `analytics.ts` for
 * the same reason `trades.columns.ts` is: a file that describes data should not
 * have to import templates. The two columns that need rich cells (the rolling
 * win-rate sparkline, the badge chip) are declared here without one and have it
 * attached by key in the component — see `Analytics.strategyColumns`.
 */

/* -- formatters ---------------------------------------------------------
 *
 * Deliberately NOT `format.ts`'s `pct()`. That one prefixes a `+` because it
 * formats a *change*, and a sign is how a gain is told apart from a loss
 * without reading the colour. Nothing on this workspace is a change: a win
 * rate of 82% is a level, and "+82.00%" reads as an improvement of 82 points.
 * The one genuine delta below (`delta` — live win rate minus out-of-sample)
 * does carry a sign, for exactly the original reason.
 */

/** A win rate, expressed 0–100 by the server. One decimal: the third digit of
 *  a percentage computed over 40 trades is noise dressed as precision. */
export function rate(value: number | null | undefined): string {
  return value === null || value === undefined ? ABSENT : `${value.toFixed(1)}%`;
}

/** Expectancy in R. Three decimals, because it is typically a fraction of a
 *  risk unit and two would round most strategies to the same number. */
/** A signed difference in percentage points. Local to this file -- knip
 *  reports it as an "unused export" because nothing IMPORTS it, which is not
 *  the same as unused: the win-rate delta column below calls it. */
function delta(value: number | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}`;
}

export function expectancy(value: number | null | undefined): string {
  if (value === null || value === undefined) return ABSENT;
  return `${value > 0 ? '+' : ''}${value.toFixed(3)}`;
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? ABSENT : String(value);
}

/* -- strategies --------------------------------------------------------- */

/** `rolling` and `status` render through templates; their `value` is omitted
 *  so the table has nothing to fall back to and a missing cell is obvious. */
export const STRATEGY_COLUMNS: ColumnDef<StrategyRow>[] = [
  { key: 'strategy', header: 'Strategy' },
  { key: 'rolling', header: 'Rolling WR', width: '90px' },
  { key: 'status', header: 'Badge' },
  { key: 'rr_override', header: 'R:R', numeric: true, value: (r) => (r.rr_override === null ? null : r.rr_override.toFixed(2)) },
  { key: 'n', header: 'OOS N', numeric: true, value: (r) => count(r.n) },
  { key: 'win_rate', header: 'OOS WR', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'OOS ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
  { key: 'live_n', header: 'Live N', numeric: true, value: (r) => count(r.live_n) },
  { key: 'live_wr', header: 'Live WR', numeric: true, value: (r) => rate(r.live_wr) },
  { key: 'delta_vs_oos', header: 'Δ vs OOS', numeric: true, value: (r) => delta(r.delta_vs_oos) },
  { key: 'window', header: 'Window', value: (r) => r.window },
  { key: 'run_date', header: 'Run date', value: (r) => (r.run_date ? date(r.run_date) : null) },
  { key: 'gate_description', header: 'Gate', value: (r) => r.gate_description },
];

/* -- performance -------------------------------------------------------- */

export const CONFIDENCE_COLUMNS: ColumnDef<ConfidenceRow>[] = [
  { key: 'level', header: 'Confidence' },
  { key: 'total', header: 'Total', numeric: true, value: (r) => count(r.total) },
  { key: 'open', header: 'Open', numeric: true, value: (r) => count(r.open) },
  { key: 'closed', header: 'Closed', numeric: true, value: (r) => count(r.closed) },
  { key: 'wins', header: 'Wins', numeric: true, value: (r) => count(r.wins) },
  { key: 'losses', header: 'Losses', numeric: true, value: (r) => count(r.losses) },
  { key: 'win_rate', header: 'Win rate', numeric: true, value: (r) => rate(r.win_rate) },
];

/* -- calibration -------------------------------------------------------- */

export const DECILE_COLUMNS: ColumnDef<DecileRow>[] = [
  { key: 'decile', header: 'Score decile' },
  { key: 'n', header: 'N', numeric: true, value: (r) => count(r.n) },
  { key: 'win_rate', header: 'Win rate', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
];

export const TIER_COLUMNS: ColumnDef<TierRow>[] = [
  { key: 'tier', header: 'Tier' },
  { key: 'n', header: 'N', numeric: true, value: (r) => count(r.n) },
  { key: 'win_rate', header: 'Live WR', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
  { key: 'expected_band', header: 'Design band' },
  { key: 'ok', header: 'In band' },
];

export const DRIFT_COLUMNS: ColumnDef<DriftRow>[] = [
  { key: 'strategy', header: 'Strategy' },
  { key: 'oos_n', header: 'OOS N', numeric: true, value: (r) => count(r.oos_n) },
  { key: 'oos_wr', header: 'OOS WR', numeric: true, value: (r) => rate(r.oos_wr) },
  { key: 'live_n', header: 'Live N', numeric: true, value: (r) => count(r.live_n) },
  { key: 'live_wr', header: 'Live WR', numeric: true, value: (r) => rate(r.live_wr) },
  { key: 'delta_wr', header: 'Δ', numeric: true, value: (r) => delta(r.delta_wr) },
  { key: 'drift_alert', header: 'Decay' },
];

/** Every column, every table: none of these paginate, none of them are wide
 *  enough to need hiding, and no `ColumnPicker` is wired here — so `visible`
 *  is simply "all of them" rather than a stored preference that could drift
 *  out of step with the declarations above. */
export function allKeys<T>(columns: ColumnDef<T>[]): string[] {
  return columns.map((column) => column.key);
}
