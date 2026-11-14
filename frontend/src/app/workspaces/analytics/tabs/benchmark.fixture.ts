import { AnalyticsBenchmark, BenchmarkPoint, BenchmarkStat } from '../../../api/models';

const st = (value: number | null, n: number, reason: string | null = null): BenchmarkStat => ({ value, n, reason });
const SHORT = 'needs ≥ 20 sessions';
const CAP = 'needs ≥ 10 index-up and ≥ 10 index-down sessions';
const NO_ALPHA = { value: null, t: null, n: 3, reason: 'needs ≥ 60 sessions', headline: false };
const NO_BETA = { value: null, se: null, n: 3, reason: SHORT };
const DATES = ['2026-10-28', '2026-10-29', '2026-10-30', '2026-11-02', '2026-11-03', '2026-11-04'];
/** One point per date; index 0 is the rebase close (0 %, no day return). */
const line = (cums: (number | null)[], extra: Record<string, Partial<BenchmarkPoint>> = {}): BenchmarkPoint[] =>
  DATES.map((date, i) => ({
    date, cum_pct: cums[i], day_pct: i === 0 || cums[i] === null ? null : (cums[i] as number) - (cums[i - 1] ?? 0),
    span: 1, missing: false, proxy: false, approx: false, clipped: false, ...extra[date],
  }));
const day = (date: string, lines: Record<string, number | null>, exposure: number | null, open: number,
             beat: boolean | null, over: { span?: number; missing?: boolean } = {}) =>
  ({ date, lines, exposure_pct: exposure, open_n: open, beat, span: over.span ?? 1, missing: over.missing ?? false });

export const BENCHMARK_FIXTURE: AnalyticsBenchmark = {
  range: { from: '2026-10-29', to: '2026-11-04', live_since: '2026-08-07', sessions_n: 5, clamped: false, is_all: false },
  as_of: '2026-11-05T15:35:00+00:00', session_state: 'open',
  account_currency: 'USD', mixed_tickers: [],
  benchmarks_status: 'ok', benchmarks_last_session: '2026-11-04',
  today: { session: '2026-11-05', final: false, as_of: '2026-11-05T15:35:00+00:00', lines: {
    bot_account: { pct: 0.31, final: false }, bot_deployed: { pct: 0.82, final: false },
    SPY: { pct: 1.02, final: false }, QQQ: { pct: 1.4, final: false },
    '^IXIC': { pct: null, final: false }, '^DJI': { pct: -0.55, final: false } } },
  series: [
    { key: 'bot_account', label: 'Bot · account', kind: 'bot', total_return: true,
      points: line([0, 0.4, null, 0.9, 0.7, 0.58], { '2026-10-30': { missing: true }, '2026-11-02': { span: 2 } }) },
    { key: 'bot_deployed', label: 'Bot · deployed', kind: 'bot', total_return: true,
      points: line([0, 1.1, null, 2.0, 1.6, 1.9], { '2026-10-30': { missing: true }, '2026-11-03': { approx: true } }) },
    { key: 'SPY', label: 'SPY', kind: 'index', total_return: true, points: line([0, 0.5, 0.8, 1.1, 1.0, 1.4]) },
    { key: 'QQQ', label: 'QQQ', kind: 'index', total_return: true, points: line([0, 0.7, 1.2, 1.5, 1.3, 1.8]) },
    { key: '^IXIC', label: 'Nasdaq Comp. (price)', kind: 'index', total_return: false, points: line([0, 0.6, 1.1, 1.6, 1.7, 2.1]) },
    { key: '^DJI', label: 'Dow (price)', kind: 'index', total_return: false,
      points: line([0, 0.2, 0.3, 0.6, 0.5, 0.7], { '2026-10-30': { proxy: true } }) },
  ],
  markers: [{ date: '2026-11-03', kind: 'base_balance' }],
  exposure: [
    { date: '2026-10-29', pct: 41.2, open_n: 3, approx: true }, { date: '2026-10-30', pct: null, open_n: 0, approx: false },
    { date: '2026-11-02', pct: 35.0, open_n: 2, approx: false }, { date: '2026-11-03', pct: 38.0, open_n: 2, approx: false },
    { date: '2026-11-04', pct: 38.0, open_n: 2, approx: false },
  ],
  stats: {
    bot_account: { total_pct: st(0.58, 4), max_dd_pct: st(-0.32, 4), sharpe: st(null, 3, SHORT),
                   money_dd: st(-41.5, 4), losing_streak: 2, approx_share: null },
    bot_deployed: { total_pct: st(1.9, 3), max_dd_pct: st(-0.6, 3), sharpe: st(null, 3, SHORT),
                    money_dd: st(null, 3, 'account line only'), losing_streak: 1, approx_share: 38 },
    SPY: { total_pct: st(1.4, 5), max_dd_pct: st(-0.09, 5), sharpe: st(null, 5, SHORT) },
    QQQ: { total_pct: st(1.8, 5), max_dd_pct: st(-0.2, 5), sharpe: st(null, 5, 'no variance') },
    '^IXIC': { total_pct: st(2.1, 5), max_dd_pct: st(0, 5), sharpe: st(null, 5, SHORT) },
    '^DJI': { total_pct: st(0.7, 5), max_dd_pct: st(-0.1, 5), sharpe: st(null, 5, SHORT) },
  },
  vs: {
    SPY: { lead_pp: st(-0.82, 4), beta: NO_BETA, alpha: NO_ALPHA },
    QQQ: { lead_pp: st(-1.22, 4), beta: { value: 0.42, se: 0.18, n: 61, reason: null },
           alpha: { value: 6.1, t: 0.9, n: 61, reason: null, headline: false } },
    '^IXIC': { lead_pp: st(-1.52, 4), beta: NO_BETA, alpha: NO_ALPHA },
    '^DJI': { lead_pp: st(-0.12, 4), beta: NO_BETA, alpha: NO_ALPHA },
  },
  capture: { index: 'SPY', up_pct: st(null, 2, CAP), down_pct: st(null, 1, CAP), ratio: st(null, 3, CAP),
             up_n: 2, down_n: 1, beat: { up_days: 2, up_beat: 1, down_days: 1, down_beat: 1 } },
  daily: [
    day('2026-11-04', { bot_account: -0.12, bot_deployed: 0.3, SPY: 0.4, QQQ: 0.5, '^IXIC': 0.4, '^DJI': 0.2 }, 38, 2, false),
    day('2026-11-03', { bot_account: null, bot_deployed: null, SPY: -0.1, QQQ: -0.2, '^IXIC': 0.1, '^DJI': -0.1 }, 38, 2, null),
    day('2026-11-02', { bot_account: 0.5, bot_deployed: 0.9, SPY: 0.3, QQQ: 0.3, '^IXIC': 0.5, '^DJI': 0.3 }, 35, 2, null, { span: 2 }),
    day('2026-10-30', { bot_account: null, bot_deployed: null, SPY: 0.3, QQQ: 0.5, '^IXIC': 0.5, '^DJI': 0.1 }, null, 0, null, { missing: true }),
    day('2026-10-29', { bot_account: 0.4, bot_deployed: 1.1, SPY: 0.5, QQQ: 0.7, '^IXIC': 0.6, '^DJI': 0.2 }, 41.2, 3, false),
  ],
  daily_has_more: true,
};

export const benchmarkWith = (over: Partial<AnalyticsBenchmark>): AnalyticsBenchmark => ({ ...BENCHMARK_FIXTURE, ...over });
