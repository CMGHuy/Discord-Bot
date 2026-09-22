import { ParamMap, Params } from '@angular/router';

import { AnalyticsUnit, BookScope, LedgerScope } from '../../api/models';
import { ANALYTICS_TABS, AnalyticsTab, DEFAULT_SCOPE, LEGACY_TABS } from '../../stores/analytics.store';

const LEDGERS: LedgerScope[] = ['main', 'weak', 'both'];
const UNITS: AnalyticsUnit[] = ['r', 'pct', 'money'];
const DIRECTIONS = ['bullish', 'bearish'];
const ISO = /^\d{4}-\d{2}-\d{2}$/;

const pick = <T extends string>(raw: string | null, allowed: readonly T[], fallback: T): T =>
  (allowed as readonly string[]).includes(raw ?? '') ? (raw as T) : fallback;

/** The URL is the scope (spec v94 D2): a filtered view is a link, and it
 *  survives a tab switch and a reload. Anything unrecognised falls back to
 *  the default rather than 400ing the first request. */
export function scopeFromParams(params: ParamMap): { tab: AnalyticsTab; scope: BookScope; unit: AnalyticsUnit } {
  const raw = params.get('tab');
  const tab = (ANALYTICS_TABS as readonly string[]).includes(raw ?? '')
    ? (raw as AnalyticsTab)
    : (LEGACY_TABS[raw ?? ''] ?? 'overview');
  const day = (name: string): string | null => {
    const value = params.get(name);
    return value && ISO.test(value) ? value : null;
  };
  return {
    tab,
    scope: {
      from: day('from'), to: day('to'),
      ledger: pick(params.get('ledger'), LEDGERS, DEFAULT_SCOPE.ledger),
      strategy: params.get('strategy') || null,
      horizon: params.get('horizon') || null,
      direction: pick(params.get('direction'), DIRECTIONS, '') || null,
    },
    unit: pick(params.get('unit'), UNITS, 'r'),
  };
}

/** A field equal to its default is written as `null` so the URL stays short
 *  and one state has exactly one URL — two spellings of the same view would
 *  make a shared link ambiguous about what was actually being looked at. */
export function scopeToQueryParams(tab: AnalyticsTab, scope: BookScope, unit: AnalyticsUnit): Params {
  return {
    tab: tab === 'overview' ? null : tab,
    from: scope.from, to: scope.to,
    ledger: scope.ledger === DEFAULT_SCOPE.ledger ? null : scope.ledger,
    strategy: scope.strategy, horizon: scope.horizon, direction: scope.direction,
    unit: unit === 'r' ? null : unit,
  };
}
