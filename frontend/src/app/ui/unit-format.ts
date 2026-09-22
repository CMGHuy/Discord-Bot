import { AnalyticsUnit } from '../api/models';
import { ABSENT, money, pct, rMultiple } from './format';

/** One quantity expressed for the analytics control-bar unit toggle. */
export interface UnitValues { r: number | null; pct: number | null; money: number | null; }

export function inUnit(values: UnitValues, unit: AnalyticsUnit, currency: string): string {
  if (unit === 'r') return rMultiple(values.r);
  if (unit === 'pct') return pct(values.pct);
  return money(values.money, currency);
}

/** Currency remains available regardless of the chosen headline unit (v94 D3). */
export function alwaysMoney(values: UnitValues, currency: string): string | null {
  return values.money === null || values.money === undefined ? null : money(values.money, currency);
}

export function unitLabel(unit: AnalyticsUnit, currency = '$'): string {
  return unit === 'r' ? 'R' : unit === 'pct' ? '%' : currency;
}

export { ABSENT };
