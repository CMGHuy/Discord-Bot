import { TradeRow } from '../api/models';
import { bankedLegPct } from './plan-cell';

/**
 * v177 -- which Plan cell a trades row gets, decided in one place.
 *
 * The Dashboard's positions table and the Trades page render the same
 * `TradeRow` through an identical `#planCell` template, so they must give
 * the same answer; both call this. The gate is keyed on `row.status`: the
 * TP1-leg row of a still-PARTIAL plan is a CLOSED row that keeps
 * `bar_kind: 'trailing'` (for its leg icon), and it must keep today's cell.
 */
export interface RunnerCellInputs {
  planTp1: number | null;
  planStop: number | null;
  trailBest: number | null;
  trailBestPct: number | null;
  trailExitPct: number | null;
  runnerExit: number | null;
  runnerExitPct: number | null;
  runnerExitReason: string | null;
}

/** Every input null: the cell renders exactly as it did before v177. */
export const NO_RUNNER_CELL: RunnerCellInputs = Object.freeze({
  planTp1: null,
  planStop: null,
  trailBest: null,
  trailBestPct: null,
  trailExitPct: null,
  runnerExit: null,
  runnerExitPct: null,
  runnerExitReason: null,
});

export function runnerCellInputs(row: TradeRow): RunnerCellInputs {
  if (row.status === 'PARTIAL' && row.bar_kind === 'trailing' && row.tp1 != null) {
    return {
      ...NO_RUNNER_CELL,
      planTp1: row.tp1,
      planStop: row.risk_stop ?? null,
      // Same fallback as the backend's percentages: the TP1 fill until a
      // tick has recorded a best price.
      trailBest: row.runner_best ?? row.banked_exit_price ?? null,
      trailBestPct: row.best_pnl_pct ?? null,
      trailExitPct: row.stop_pnl_pct ?? null,
    };
  }
  if (row.status === 'CLOSED' && row.runner_exit_price != null) {
    return {
      ...NO_RUNNER_CELL,
      runnerExit: row.runner_exit_price,
      runnerExitPct: bankedLegPct(row.entry, row.runner_exit_price, row.direction),
      runnerExitReason: row.runner_exit_reason ?? null,
    };
  }
  return NO_RUNNER_CELL;
}
