import { ABSENT, MINUS, amount, riskPct } from './format';

/**
 * A risk figure in both units at once -- money and % of account, "1,420 $ ·
 * 1.42%" -- for open risk and cap headroom (v195 section 5.2). The partner's 2% cap
 * limits money risked, so a %-only tile hides the figure the cap is about
 * and a money-only tile hides how close it is.
 *
 * `pct` is the source figure: the server sends heat as % of the account
 * balance. The money part uses the server's own relation, pct / 100 x
 * balance (`trade_risk_pct`, swingbot/admin/api_v1/risk.py), so it is never
 * a second, drifting computation. No balance: the money part is the em dash
 * and the percentage still shows ("— · 1.42%") -- never an invented figure.
 * No percentage: the whole figure is absent.
 *
 * Both parts are levels, formatted by the unsigned `amount` (whole units)
 * and v194's `riskPct` (two decimals, "<0.01%" for a sliver). A negative
 * value -- headroom past the cap -- carries one true minus on each part.
 */
export function riskUnits(
  pct: number | null | undefined,
  balance: number | null | undefined,
  unit: string,
): string {
  if (!isFiniteNumber(pct)) return ABSENT;
  const sign = pct < 0 ? MINUS : '';
  const magnitude = Math.abs(pct);
  const money = isFiniteNumber(balance)
    ? `${sign}${amount((magnitude / 100) * balance, unit, 0)}`
    : ABSENT;
  return `${money} · ${sign}${riskPct(magnitude)}`;
}

function isFiniteNumber(value: number | null | undefined): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}
