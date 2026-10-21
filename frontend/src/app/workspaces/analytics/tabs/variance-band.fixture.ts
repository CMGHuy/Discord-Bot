import { BandHorizon, VarianceBandInsufficient, VarianceBandOk } from '../../../api/models';

/** v175 — `/analytics/variance-band` payloads shared by the panel and tab
 *  specs. Hand-written in the Band shape of the plan's Global Constraints;
 *  the statistics themselves are tested in tests/analytics/. */
const H20: BandHorizon = {
  horizon: 20, weeks_span: 5.3,
  run: { p80: 3, p95: 4, p95_lo: 4, p95_hi: 5 },
  drawdown: { p80: 3.12, p95: 4.4, p95_lo: 3.9, p95_hi: 5.06 },
};
const H50: BandHorizon = {
  horizon: 50, weeks_span: 13.2,
  run: { p80: 4, p95: 7, p95_lo: 6, p95_hi: 8 },
  drawdown: { p80: 4.81, p95: 6.62, p95_lo: 5.9, p95_hi: 7.4 },
};

/** A full band with no `dollars` key: the server omits it, never nulls it. */
const BASE: VarianceBandOk = {
  status: 'ok', scope: 'whole_book', asof: '2026-10-16', days: 160, weeks: 38, pool: 'v2',
  composition: { days_by_era: { v2: 118, legacy: 42 }, trades_by_horizon: { '2w': 88, '4w': 131, unknown: 3 } },
  horizons: [H20, H50],
  current: {
    run: 4, run_age_days: 9, drawdown: 5.27, drawdown_age_days: 23,
    run_zone: 'normal', drawdown_zone: 'rough', zone: 'rough',
  },
  expr: { value: 0.214, n: 222, start: '2026-01-05', end: '2026-10-16', ci: [0.02, 0.41], not_positive: false },
};

/** Run normal, drawdown rough, positive ExpR, dollars present. */
export const BAND_OK: VarianceBandOk = { ...BASE, dollars: { median_risk: 59.26, drawdown_usd: 312.34 } };

/** The 50-day run band tied (p80 == p95): its rough zone is empty. No dollars. */
export const BAND_TIE: VarianceBandOk = {
  ...BASE,
  horizons: [H20, { ...H50, run: { p80: 5, p95: 5, p95_lo: 4, p95_hi: 6 } }],
};

/** Both statistics outside, ExpR interval straddling 0: the caveat shows. */
export const BAND_NOT_POSITIVE: VarianceBandOk = {
  ...BASE,
  current: {
    run: 9, run_age_days: 15, drawdown: 8.4, drawdown_age_days: 41,
    run_zone: 'outside', drawdown_zone: 'outside', zone: 'outside',
  },
  expr: { value: 0.05, n: 140, start: '2026-02-02', end: '2026-10-16', ci: [-0.12, 0.22], not_positive: true },
  dollars: { median_risk: 59.26, drawdown_usd: 497.78 },
};

export const BAND_INSUFFICIENT: VarianceBandInsufficient = {
  status: 'insufficient', scope: 'whole_book', days: 64, weeks: 15,
};
