import { describe, expect, it } from 'vitest';

import { TradeRow } from '../api/models';
import { bankedLegPct } from './plan-cell';
import { NO_RUNNER_CELL, runnerCellInputs } from './runner-cell';

function row(overrides: Partial<TradeRow>): TradeRow {
  return {
    id: 't1', origin: 'plan', status: 'CLOSED', ticker: 'RKLB',
    direction: 'bearish', strategy: null, horizon: null, tier: null, badge: null,
    confidence_level: null, confidence_score: null, quality_score: null,
    entry: 60.67, stop_loss: 61.85, target: 58.33, target2: null,
    banked_fraction: null, banked_exit_price: null, banked_r: null,
    risk_reward: null, shares: 10, open_shares: null, position_value: null,
    current_price: null, current_price_stale: false, exit_price: null, realized_pnl_amount: null,
    pnl_pct: null, r_multiple: null, held_hours: null, opened_at: null, closed_at: null,
    has_note: false, today: true, created_at: null, trigger_price: null,
    follow_score: null, progress_pct: null, entry_pct: null, progress_band: null,
    blink_seconds: null, status_label: 'CLOSED', target_is_banked_tp1: false,
    stop_kind: 'risk', bar_kind: 'none', floor_r: null, price_r: null,
    headroom_r: null, distance_to_trigger_r: null, bars_to_expiry: null,
    leg_index: 0, leg_total: 1,
    ...overrides,
  };
}

/** The RKLB runner row as V177-1's backend serves it on the PARTIAL tab. */
const RKLB_RUNNER_ROW: Partial<TradeRow> = {
  status: 'PARTIAL', status_label: 'PARTIAL', stop_loss: 52.437, target: null,
  target_is_banked_tp1: true, stop_kind: 'trailing', bar_kind: 'trailing',
  banked_fraction: 0.5, banked_exit_price: 58.33, banked_r: 1.98,
  risk_stop: 61.85, runner_best: 49.94, tp1: 58.33,
  best_pnl_pct: 17.69, stop_pnl_pct: 13.57, leg_index: 1, leg_total: 2,
};

describe('runnerCellInputs', () => {
  it('feeds the two-line cell from a PARTIAL trailing runner row', () => {
    expect(runnerCellInputs(row(RKLB_RUNNER_ROW))).toEqual({
      ...NO_RUNNER_CELL,
      planTp1: 58.33, planStop: 61.85,
      trailBest: 49.94, trailBestPct: 17.69, trailExitPct: 13.57,
    });
  });

  it('uses the TP1 fill as the best price until a tick has recorded one', () => {
    const rc = runnerCellInputs(row({ ...RKLB_RUNNER_ROW, runner_best: null }));
    expect(rc.trailBest).toBe(58.33);
  });

  it('passes a missing percentage through as null, so the cell drops line 2', () => {
    const rc = runnerCellInputs(row({ ...RKLB_RUNNER_ROW, best_pnl_pct: undefined }));
    expect(rc.planTp1).toBe(58.33);
    expect(rc.trailBestPct).toBeNull();
  });

  it('leaves a PARTIAL runner with a TP2 on today\'s cell', () => {
    expect(runnerCellInputs(row({ ...RKLB_RUNNER_ROW, bar_kind: 'progress', tp1: null })))
      .toEqual(NO_RUNNER_CELL);
  });

  it('leaves the TP1-leg row of a still-PARTIAL plan on today\'s cell', () => {
    // Status CLOSED, bar_kind still 'trailing' (the leg icon reads it); the
    // backend nulls tp1 and the percentages, and the runner has not closed.
    const leg = row({ ...RKLB_RUNNER_ROW, status: 'CLOSED', tp1: null,
      best_pnl_pct: null, stop_pnl_pct: null, runner_exit_price: null, leg_index: 0 });
    expect(runnerCellInputs(leg)).toEqual(NO_RUNNER_CELL);
  });

  it('never draws the runner cell on a CLOSED row, even if tp1 leaked', () => {
    expect(runnerCellInputs(row({ ...RKLB_RUNNER_ROW, status: 'CLOSED' }))).toEqual(NO_RUNNER_CELL);
  });

  it('feeds the closed cell from a CLOSED row with a runner exit', () => {
    const rc = runnerCellInputs(row({ runner_exit_price: 52.44, runner_exit_reason: 'tp1_runner_trail' }));
    expect(rc).toEqual({
      ...NO_RUNNER_CELL,
      runnerExit: 52.44,
      runnerExitPct: bankedLegPct(60.67, 52.44, 'bearish'),
      runnerExitReason: 'tp1_runner_trail',
    });
    expect(rc.runnerExitPct!).toBeCloseTo(13.565, 3);
  });

  it('signs a long runner closed below its entry as a loss', () => {
    const rc = runnerCellInputs(row({ direction: 'bullish', entry: 100, stop_loss: 90, target: 120,
      runner_exit_price: 97, runner_exit_reason: 'tp1_runner_be' }));
    expect(rc.runnerExitPct!).toBeCloseTo(-3, 6);
  });

  it('carries a missing reason as null', () => {
    expect(runnerCellInputs(row({ runner_exit_price: 52.44 })).runnerExitReason).toBeNull();
  });

  it('ignores a runner exit on a row that is not CLOSED', () => {
    expect(runnerCellInputs(row({ status: 'ACTIVE', runner_exit_price: 52.44 }))).toEqual(NO_RUNNER_CELL);
  });

  it('leaves PENDING, ACTIVE and legacy rows on today\'s cell', () => {
    for (const status of ['PENDING', 'ACTIVE', 'CANCELLED']) {
      expect(runnerCellInputs(row({ status }))).toEqual(NO_RUNNER_CELL);
    }
    expect(runnerCellInputs(row({ origin: 'legacy' }))).toEqual(NO_RUNNER_CELL);
  });

  it('returns null, never undefined, for every field', () => {
    expect(Object.values(NO_RUNNER_CELL).every((v) => v === null)).toBe(true);
    expect(Object.keys(NO_RUNNER_CELL).sort()).toEqual([
      'planStop', 'planTp1', 'runnerExit', 'runnerExitPct', 'runnerExitReason',
      'trailBest', 'trailBestPct', 'trailExitPct',
    ]);
  });
});
