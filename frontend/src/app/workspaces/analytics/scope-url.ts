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

/** The scope fields, in the order `BookScope` declares them. */
const SCOPE_KEYS = ['from', 'to', 'ledger', 'strategy', 'horizon', 'direction'] as const;

/**
 * The same read as `scopeFromParams`, minus the defaults: only the fields
 * the URL actually carries.
 *
 * `scopeFromParams` substitutes a default for every absent field, which is
 * right for "what is the scope" and wrong for "what did the URL say". The
 * store's `hydrate` merges this patch onto state seeded from the remembered
 * preference, so the URL wins where it speaks and the preference answers
 * where it is silent. Handing it the defaulted scope instead would
 * overwrite every remembered field on every navigation, and the preference
 * would be written forever and never read.
 *
 * A present-but-invalid value (`?from=yesterday`) counts as the URL
 * speaking: it patches to the default rather than falling through to the
 * preference. Resurrecting a stored filter that the URL visibly does not
 * contain would be the worse surprise of the two.
 */
export function scopePatchFromParams(
  params: ParamMap,
): { tab: AnalyticsTab; scope: Partial<BookScope>; unit: AnalyticsUnit | undefined } {
  const { tab, scope, unit } = scopeFromParams(params);
  const patch: Partial<BookScope> = {};
  for (const key of SCOPE_KEYS) {
    if (params.has(key)) Object.assign(patch, { [key]: scope[key] });
  }
  // `tab` is unconditional: it always resolves to a real tab (legacy-mapped
  // or defaulted) and there is no remembered tab for it to trample.
  return { tab, scope: patch, unit: params.has('unit') ? unit : undefined };
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
