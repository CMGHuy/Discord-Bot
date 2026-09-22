import { AnalyticsByDimensionRow, AnalyticsUnit } from '../../api/models';
import { ColumnDef } from '../../ui/data-table/data-table.types';
import { ABSENT, date, dateTime, money, rMultiple, share, signed } from '../../ui/format';
import {
  ConfidenceRow,
  DecileRow,
  DriftRow,
  GridRow,
  JobSummary,
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
 *  the same as unused: the win-rate delta column below calls it.
 *  v54 Task 28: signed(), not a hand-rolled '+' -- a hand-rolled negative
 *  used the default hyphen-minus, narrower than a digit even in the mono
 *  face, which breaks the tabular alignment the numeric law exists for. */
function delta(value: number | null | undefined): string {
  return signed(value, 1);
}

/** Expectancy in R. Three decimals, because it is typically a fraction of a
 *  risk unit and two would round most strategies to the same number.
 *  v54 Task 28: signed(), same reasoning as `delta` above. Every column
 *  using this already names the unit in its own header ('ExpR'), so this
 *  never appended one -- only the sign glyph was ever the gap. */
export function expectancy(value: number | null | undefined): string {
  return signed(value, 3);
}

export function count(value: number | null | undefined): string {
  return value === null || value === undefined ? ABSENT : String(value);
}

/** The v93 shadow-soak verdict (`swingbot.core.edge.strategy_soak.soak_verdict`
 *  serialised straight onto the row) -- `{ pass, n_closed, clauses }`, `unknown`
 *  because nothing on the frontend owns that shape. A screenshot pass once
 *  caught this rendered as the raw `JSON.stringify`'d object
 *  (`{"clauses":{...},"n_closed":1,"pass":false}`) sitting in a table cell;
 *  this reads the two fields a reader actually needs -- whether the strategy
 *  cleared the gate, and how many shadow trades that verdict rests on. */
export function soakLabel(value: unknown): string | null {
  if (value === null || value === undefined || typeof value !== 'object') return null;
  const verdict = value as { pass?: unknown; n_closed?: unknown };
  if (typeof verdict.pass !== 'boolean') return null;
  const n = typeof verdict.n_closed === 'number' ? verdict.n_closed : null;
  return `${verdict.pass ? 'PASS' : 'FAIL'}${n === null ? '' : ` · n=${n}`}`;
}

/* -- strategies --------------------------------------------------------- */

/** `rolling` and `status` render through templates; their `value` is omitted
 *  so the table has nothing to fall back to and a missing cell is obvious. */
export const STRATEGY_COLUMNS: ColumnDef<StrategyRow>[] = [
  { key: 'strategy', header: 'Strategy', value: (r) => r.strategy },
  { key: 'rolling', header: 'Rolling WR', width: '90px' },
  { key: 'status', header: 'Badge' },
  { key: 'n', header: 'OOS N', numeric: true, value: (r) => count(r.n) },
  { key: 'win_rate', header: 'OOS WR', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'OOS ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
  { key: 'live_n', header: 'Live N', numeric: true, value: (r) => count(r.live_n) },
  { key: 'live_wr', header: 'Live WR', numeric: true, value: (r) => rate(r.live_wr) },
  { key: 'delta_vs_oos', header: 'Δ vs OOS', numeric: true, value: (r) => delta(r.delta_vs_oos) },
  { key: 'window', header: 'Window', value: (r) => r.window },
  { key: 'run_date', header: 'Run date', value: (r) => (r.run_date ? date(r.run_date) : null) },
  // Reads next to the run date it is derived from. "fresh" renders as ABSENT
  // rather than the word: no news is not news, and a table of "fresh" cells
  // just costs the eye a column. "unknown" is undated, not a warning.
  { key: 'evidence_decay', header: 'Evidence',
    value: (r) => (r.evidence_decay === 'fresh' ? ABSENT
                   : r.evidence_decay === 'unknown' ? 'undated' : r.evidence_decay) },
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
  { key: 'decile', header: 'Score decile', value: (r) => r.decile },
  { key: 'n', header: 'N', numeric: true, value: (r) => count(r.n) },
  { key: 'win_rate', header: 'Win rate', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
];

export function TIER_COLUMNS(floor: number): ColumnDef<TierRow>[] { return [
  { key: 'level', header: 'Confidence level', value: (r) => String(r.level) },
  { key: 'n', header: 'N', numeric: true, value: (r) => count(r.n) },
  // v89: the Trades column carries n; a win-rate column holds a rate or nothing.
  { key: 'win_rate', header: 'Live WR', numeric: true, value: (r) => r.n < floor || r.win_rate === null ? ABSENT : rate(r.win_rate) },
  { key: 'expectancy_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
]; }

/**
 * v94 T2 -- one column set for every dimension the Attribution breakdown
 * table can group by (`store.breakdown()`). This reads
 * `AnalyticsByDimensionRow` straight off `/analytics/by-dimension` --
 * `exp_r`/`total_r` are two distinct sums, not one derived from the other
 * (models.ts's own note on why), and `total_pnl` needs a currency unit that
 * row shape never carried.
 *
 * `total_r` and `total_pnl` are both always-rendered columns, never one
 * standing in for the other the way `inUnit()` picks a single
 * representation elsewhere on this workspace -- there is nothing for a
 * `unit` toggle to hide or reorder between two figures that both stay on
 * screen regardless of it. `unit` is accepted (matching the tab's
 * `store.unit()` call site) but currently unused; `currency` is what
 * `total_pnl`'s `money()` formatting actually needs.
 *
 * A `null` rate is a thin cell (H1): it renders as `ABSENT`, never as a
 * computed or defaulted 0 -- `n < floor` is exactly the case the server
 * already declined to answer for.
 */
export function dimensionColumns(
  label: string, _unit: AnalyticsUnit, currency: string, floor: number,
): ColumnDef<AnalyticsByDimensionRow>[] {
  return [
    { key: 'key', header: label, value: (r) => r.key },
    { key: 'n', header: 'Trades', numeric: true, value: (r) => count(r.n) },
    { key: 'win_rate', header: 'Win rate', numeric: true,
      value: (r) => (r.n < floor || r.win_rate === null ? ABSENT : rate(r.win_rate)) },
    { key: 'exp_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.exp_r) },
    { key: 'total_r', header: 'Total R', numeric: true,
      value: (r) => (r.total_r === null ? ABSENT : rMultiple(r.total_r)) },
    { key: 'total_pnl', header: 'P&L', numeric: true,
      value: (r) => (r.total_pnl === null ? ABSENT : money(r.total_pnl, currency)) },
    { key: 'avg_win_r', header: 'Avg win', numeric: true, value: (r) => expectancy(r.avg_win_r) },
    { key: 'avg_loss_r', header: 'Avg loss', numeric: true, value: (r) => expectancy(r.avg_loss_r) },
    // Present only for `dim=strategy` (badge) or where the server attaches a
    // soak record; the table's `visible` list omits the key entirely when no
    // row on screen carries it, rather than showing a column of dashes.
    { key: 'badge', header: 'Badge', value: (r) => r.badge ?? null },
    { key: 'soak', header: 'Soak', value: (r) => soakLabel(r.soak) },
  ];
}

export const DRIFT_COLUMNS: ColumnDef<DriftRow>[] = [
  { key: 'strategy', header: 'Strategy', value: (r) => r.strategy },
  { key: 'oos_n', header: 'OOS N', numeric: true, value: (r) => count(r.oos_n) },
  { key: 'oos_wr', header: 'OOS WR', numeric: true, value: (r) => rate(r.oos_wr) },
  { key: 'live_n', header: 'Live N', numeric: true, value: (r) => count(r.live_n) },
  { key: 'live_wr', header: 'Live WR', numeric: true, value: (r) => rate(r.live_wr) },
  { key: 'delta_wr', header: 'Δ', numeric: true, value: (r) => delta(r.delta_wr) },
  { key: 'drift_alert', header: 'Decay' },
];

/* -- tuning grid --------------------------------------------------------- */

/** `passes` and `propose` render through templates; their `value` is omitted
 *  so the table has nothing to fall back to and a missing cell is obvious. */
export const GRID_COLUMNS: ColumnDef<GridRow>[] = [
  { key: 'paramLabel', header: 'Parameters', value: (r) => r.paramLabel },
  { key: 'n_eval', header: 'N', numeric: true, value: (r) => count(r.n_eval) },
  { key: 'win_rate', header: 'Win rate', numeric: true, value: (r) => rate(r.win_rate) },
  { key: 'expectancy_r', header: 'ExpR', numeric: true, value: (r) => expectancy(r.expectancy_r) },
  // The excluded share arrives as a fraction and is a share, not a change --
  // same reasoning as the deleted `fmtExcluded` this column replaces.
  { key: 'excluded_share', header: 'Excluded', numeric: true,
    value: (r) => (r.excluded_share === null ? ABSENT : share(r.excluded_share * 100)) },
  { key: 'passes', header: 'Bar' },     // cell slot, filled in analytics.ts
  { key: 'propose', header: '' },       // cell slot, filled in analytics.ts
];

/* -- past jobs ------------------------------------------------------------
 *
 * `started_at` takes `dateTime`, not `date`: a tuning job's history reads by
 * time of day as much as by date, and the hand-rolled list this replaces
 * already showed it that way (`fmtDateTime`). */
export const PAST_JOBS_COLUMNS: ColumnDef<JobSummary>[] = [
  { key: 'id', header: 'Job', value: (r) => r.id },
  { key: 'state', header: 'State', value: (r) => r.state },
  { key: 'started_at', header: 'Started', value: (r) => dateTime(r.started_at) },
];

/** Every column, every table: none of these paginate, none of them are wide
 *  enough to need hiding, and no `ColumnPicker` is wired here — so `visible`
 *  is simply "all of them" rather than a stored preference that could drift
 *  out of step with the declarations above. */
export function allKeys<T>(columns: ColumnDef<T>[]): string[] {
  return columns.map((column) => column.key);
}
