import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/* v189: the golden scaled-out trade, one JSON shared with pytest
 * (tests/analytics/test_golden_partial_trade_metrics.py and friends), so the
 * backend and the frontend cannot drift. Read from the repo, never copied. */

/** Relative to `process.cwd()`, which is `frontend/` under `ng test`. */
export const GOLDEN_FIXTURE_PATH = '../tests/analytics/golden_partial_trade.json';

export interface GoldenLeg { fraction: number; exit_price: number; r?: number; reason?: string; }

export interface GoldenOpenCase {
  name: string; quote: number | null; shares: number; entry_shares: number;
  r_multiple: number | null; banked_r: number; banked_contribution_r: number;
  banked_amount: number; unrealized_pnl_amount: number | null; working_stop: number;
  risk_of_loss_amount: number; open_profit_to_stop: number | null;
}

export interface GoldenClosedCase {
  name: string; runner_exit: number; runner_r: number; net_r: number;
  realized_pnl_amount: number; pnl_pct: number; status: string; close_reason: string | null;
  backtest_label?: string;
}

export interface GoldenPartialTrade {
  trade: {
    ticker: string; direction: string; shares: number; tp1_fraction: number;
    entry: number; stop_loss: number; tp1: number; tp2: number; risk_per_share: number;
    tp1_leg: GoldenLeg;
  };
  tolerance: number;
  closed_cases: GoldenClosedCase[];
  open_cases: GoldenOpenCase[];
}

let memo: GoldenPartialTrade | null = null;

export function loadGoldenPartialTrade(): GoldenPartialTrade {
  memo ??= JSON.parse(readFileSync(join(process.cwd(), GOLDEN_FIXTURE_PATH), 'utf8')) as GoldenPartialTrade;
  return memo;
}

/** One open case by name; throws on a typo rather than testing nothing. */
export function goldenOpenCase(name: string): GoldenOpenCase {
  const found = loadGoldenPartialTrade().open_cases.find((c) => c.name === name);
  if (!found) throw new Error(`no golden open case "${name}"`);
  return found;
}
