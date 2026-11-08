/** v208 — the Benchmark tab. API numbers are percentages; this tab only formats them.
 * Null is —, never 0%. */
import { AnalyticsBenchmark, BenchmarkKey } from '../../../api/models';
import { MINUS } from '../../../ui/format';

export const SERIES_ORDER: readonly BenchmarkKey[] = ['bot_account', 'bot_deployed', 'SPY', 'QQQ', '^IXIC', '^DJI'];
export const CHIP_LABELS: Record<BenchmarkKey, string> = {
  bot_account: 'Bot · account', bot_deployed: 'Bot · deployed', SPY: 'SPY', QQQ: 'QQQ',
  '^IXIC': 'Nasdaq Comp. (price)', '^DJI': 'Dow (price)',
};
export const DEFAULT_VISIBLE: readonly BenchmarkKey[] = ['bot_account', 'bot_deployed', 'SPY', 'QQQ'];
export const POLL_MS = 300_000;
export const SERIES_TOKENS: Record<BenchmarkKey, string> = {
  bot_account: '--accent', bot_deployed: '--accent', SPY: '--chart-2', QQQ: '--chart-3',
  '^IXIC': '--chart-4', '^DJI': '--chart-5',
};
export const PAPER_LINE = 'Paper trades only. Returns are pre-tax and exclude fees and slippage; '
  + 'indexes are buy-and-hold. Not a recommendation or forecast.';
export const MIXED_BANNER = 'Benchmark assumes a USD account trading USD stocks — figures may be mixed-currency';
export const DEPLOYED_LABEL = 'on capital in trades — not account return';
export const UNREALISED = 'unrealised · paper';
export const EMPTY_BARS = 'No benchmark data yet';
export const STALE_BARS = 'Benchmarks not updating — refresher is off';

export function signedPct(value: number | null, dp = 2): string {
  if (value === null) return '—';
  if (value === 0) return `${(0).toFixed(dp)}%`;
  return `${value > 0 ? '+' : MINUS}${Math.abs(value).toFixed(dp)}%`;
}

export function etClock(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(new Date(iso));
}

export function stateStamp(payload: AnalyticsBenchmark): string {
  const today = payload.today;
  if (!today?.session) return 'no session yet';
  if (payload.session_state === 'open' && !today.final) return `as of ${etClock(payload.as_of)} ET`;
  return `${today.session} · final`;
}

export interface TodayCell { key: BenchmarkKey; label: string; value: string; caption: string | null; }

export function todayCells(payload: AnalyticsBenchmark): TodayCell[] {
  const lines = payload.today?.lines;
  if (!lines) return [];
  return SERIES_ORDER.flatMap((key) => {
    const line = lines[key];
    if (!line) return [];
    const liveBot = key.startsWith('bot_') && payload.session_state === 'open' && !line.final;
    return [{ key, label: CHIP_LABELS[key], value: signedPct(line.pct), caption: liveBot ? UNREALISED : null }];
  });
}

export function statusNote(payload: AnalyticsBenchmark): string | null {
  if (payload.benchmarks_status === 'empty') return EMPTY_BARS;
  if (payload.benchmarks_status === 'stale') return STALE_BARS;
  return null;
}

export function isMixedCurrency(payload: AnalyticsBenchmark): boolean {
  return payload.account_currency !== 'USD' || payload.mixed_tickers.length > 0;
}
