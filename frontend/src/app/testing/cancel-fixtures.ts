import { CancelFigure, CancelPlanRow, CancelPrecision } from '../api/models';

/** A zeroed figure; override what a test cares about. */
export function fig(over: Partial<CancelFigure> = {}): CancelFigure {
  return {
    n: 0,
    total: 0,
    excluded: 0,
    precision: null,
    precision_ci: null,
    r_avoided: 0,
    r_missed: 0,
    net_r: 0,
    net_r_ci: null,
    counts: { right: 0, wrong: 0, unresolved: 0, untriggered_after_cancel: 0 },
    unresolved_r: 0,
    ties: 0,
    small_n: true,
    ...over,
  };
}

type Quad = [number, number, number, number];

function figure(
  n: number, total: number, excluded: number, precision: number | null,
  precisionCi: [number, number] | null, rAvoided: number, rMissed: number, netR: number,
  netRCi: [number, number] | null, c: Quad, unresolvedR: number, ties: number, smallN: boolean,
): CancelFigure {
  return {
    n, total, excluded, precision, precision_ci: precisionCi,
    r_avoided: rAvoided, r_missed: rMissed, net_r: netR, net_r_ci: netRCi,
    counts: { right: c[0], wrong: c[1], unresolved: c[2], untriggered_after_cancel: c[3] },
    unresolved_r: unresolvedR, ties, small_n: smallN,
  };
}

function row(over: Partial<CancelPlanRow>): CancelPlanRow {
  return {
    plan_id: '', ticker: '', strategy: '', horizon_key: '4w', direction: 'long',
    origin: 'regular', reason: 'invalidated', raw_reason: null, cancel_date: '',
    entry_model: 'trigger', entry_source: null, entry: null, stop: null, tp1: null,
    badge: null, stop_ceiling_pct: null, cap_size_pct: null, outcome: null, r: null,
    tie: false, exit_date: null, excluded: null,
    ...over,
  };
}

const ROWS: CancelPlanRow[] = [
  row({ plan_id: 'P-AAPL', ticker: 'AAPL', strategy: 'EMA20', reason: 'risk_cap', raw_reason: 'risk_cap',
    cancel_date: '2026-10-20', entry: 100, stop: 94, tp1: 111, badge: 'VALIDATED', stop_ceiling_pct: 6,
    cap_size_pct: 72.5, outcome: 'right', r: -1, tie: true, exit_date: '2026-10-21' }),
  row({ plan_id: 'P-AAPL', ticker: 'AAPL', strategy: 'EMA20', reason: 'risk_cap', raw_reason: 'risk_cap',
    cancel_date: '2026-10-20', entry_model: 'cancel_fill', entry_source: 'estimated', entry: 102.5, stop: 94,
    tp1: 111, badge: 'VALIDATED', stop_ceiling_pct: 6, cap_size_pct: 72.5, outcome: 'wrong', r: 1,
    exit_date: '2026-10-22' }),
  row({ plan_id: 'P-MSFT', ticker: 'MSFT', strategy: 'RSI', horizon_key: '2m', reason: 'invalidated',
    raw_reason: 'invalidated', cancel_date: '2026-10-14', entry: 400, stop: 390, tp1: 421, badge: 'WEAK',
    stop_ceiling_pct: 6, outcome: 'wrong', r: 2.1, exit_date: '2026-10-17' }),
  row({ plan_id: 'P-NVDA', ticker: 'NVDA', strategy: 'EMA20', reason: 'expired', raw_reason: 'expired',
    cancel_date: '2026-10-10', entry: 180, stop: 172, tp1: 196, badge: 'VALIDATED', stop_ceiling_pct: 6,
    outcome: 'unresolved', r: 0.35 }),
  row({ plan_id: 'P-TSLA', ticker: 'TSLA', strategy: 'Fibonacci', direction: 'short', origin: 'next_session',
    reason: 'invalidated', raw_reason: 'invalidated', cancel_date: '2026-09-30', entry: 250, stop: 262,
    tp1: 226, badge: 'WEAK', stop_ceiling_pct: 6, outcome: 'untriggered_after_cancel' }),
  row({ plan_id: 'P-XOM', ticker: 'XOM', strategy: 'RSI', horizon_key: '2m', reason: 'other',
    raw_reason: 'never_triggered', cancel_date: '2026-09-02', entry: 110, stop: 105, tp1: 120,
    excluded: 'split_guard' }),
];

const TOP = {
  generated_at: '2026-10-23T09:00:00+00:00',
  caption: 'Hypothetical replay, before commissions, slippage and tax',
  risk_cap_label: 'Outcome of the skipped setup, unaffordable at the cap',
  tp1_note: 'A TP1 hit counts the full target R with no partial exit; the bot does not bank winners in full.',
  small_n_threshold: 10,
};

export const CANCEL_PAYLOAD: CancelPrecision = {
  ...TOP,
  data_as_of: '2026-10-22',
  window: { first: '2026-07-27', last: '2026-10-22' },
  rule_changes: [{ date: '2026-09-28', label: 'v104 structural stops and stop-ceiling scope' }],
  out_of_scope: { manual: 1 },
  headline: {
    all: figure(37, 52, 2, 0.6216, [0.45, 0.78], 23, 26.4, -3.4, [-9.1, 2.3], [23, 14, 9, 4], 1.35, 3, false),
    without_risk_cap: figure(8, 12, 1, 0.75, [0.4, 1], 6, 4.2, 1.8, [-2, 5.1], [6, 2, 2, 1], 0.4, 1, true),
  },
  baseline: figure(120, 140, 0, 0.5833, [0.5, 0.66], 70, 98.5, -28.5, [-40.2, -15.1], [70, 50, 20, 0], 2.1, 4, false),
  cards: {
    risk_cap: figure(29, 40, 1, 0.5862, [0.4, 0.76], 17, 22.2, -5.2, [-11, 1.4], [17, 12, 7, 3], 0.95, 2, false),
    risk_cap_fill: figure(26, 40, 2, 0.6923, [0.5, 0.86], 18, 13.1, 4.9, [-1.2, 10.3], [18, 8, 8, 4], 0.6, 1, false),
    invalidated: figure(6, 9, 1, 0.8333, [0.5, 1], 5, 1.9, 3.1, [0.2, 5], [5, 1, 2, 0], 0.4, 1, true),
    expired: figure(2, 3, 0, 0.5, [0, 1], 1, 2.3, -1.3, [-2.3, 1], [1, 1, 0, 1], 0, 0, true),
    other: figure(0, 2, 0, null, null, 0, 0, 0, null, [0, 0, 0, 2], 0, 0, true),
  },
  splits: {
    origin: {
      regular: figure(30, 42, 2, 0.6, [0.42, 0.77], 18, 22.1, -4.1, [-9.8, 1.6], [18, 12, 8, 2], 1.1, 2, false),
      next_session: figure(7, 10, 0, 0.7143, [0.29, 1], 5, 4.3, 0.7, [-3, 4], [5, 2, 1, 2], 0.25, 1, true),
    },
    direction: {
      long: figure(33, 46, 2, 0.6061, [0.44, 0.77], 20, 24.2, -4.2, [-9.9, 1.5], [20, 13, 8, 3], 1.2, 3, false),
      short: figure(4, 6, 0, 0.75, [0.25, 1], 3, 2.2, 0.8, [-2.2, 3], [3, 1, 1, 1], 0.15, 0, true),
    },
    horizon: {
      '4w': figure(25, 35, 1, 0.64, [0.44, 0.84], 16, 17.3, -1.3, [-6.5, 3.9], [16, 9, 6, 3], 0.9, 2, false),
      '2m': figure(12, 17, 1, 0.5833, [0.3, 0.86], 7, 9.1, -2.1, [-6, 1.8], [7, 5, 3, 1], 0.45, 1, false),
    },
  },
  rows: ROWS,
};

export const EMPTY_CANCEL_PAYLOAD: CancelPrecision = {
  ...TOP,
  data_as_of: null,
  window: { first: null, last: null },
  rule_changes: [],
  out_of_scope: { manual: 0 },
  headline: { all: fig(), without_risk_cap: fig() },
  baseline: fig(),
  cards: { risk_cap: fig(), risk_cap_fill: fig(), invalidated: fig(), expired: fig(), other: fig() },
  splits: { origin: {}, direction: {}, horizon: {} },
  rows: [],
};
