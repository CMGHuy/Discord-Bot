import { EquityBasis, EquityTimeframe, Preferences } from '../api/models';

/**
 * The Dashboard equity chart's timeframe and basis — spec v172 § 5.
 *
 * Flat dotted keys in the server-backed preferences, like `tape-prefs.ts`,
 * never localStorage (`preferences.store.ts`): the same viewer on a laptop and
 * a phone sees the same chart.
 *
 * **The read is tolerant.** The value is hand-editable on the server and is
 * written by one version of the app and read by the next, so anything the
 * reader does not recognise falls back to the default for that key alone.
 */
export const EQUITY_TF_KEY = 'dashboard.equity.tf';
export const EQUITY_BASIS_KEY = 'dashboard.equity.basis';

export const EQUITY_TIMEFRAMES: readonly EquityTimeframe[] = ['1H', '4H', '1D', '1W'];
export const EQUITY_BASES: readonly EquityBasis[] = ['mtm', 'realized'];

export interface EquityChartPrefs {
  tf: EquityTimeframe;
  basis: EquityBasis;
}

/** 1D and mark-to-market: this is a swing system, and the daily candle is
 *  the one that answers "how did the account do". */
export const DEFAULT_EQUITY_CHART_PREFS: EquityChartPrefs = { tf: '1D', basis: 'mtm' };

function pick<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === 'string' && (allowed as readonly string[]).includes(value)
    ? (value as T)
    : fallback;
}

export function readEquityChartPrefs(prefs: Preferences): EquityChartPrefs {
  return {
    tf: pick(prefs?.[EQUITY_TF_KEY], EQUITY_TIMEFRAMES, DEFAULT_EQUITY_CHART_PREFS.tf),
    basis: pick(prefs?.[EQUITY_BASIS_KEY], EQUITY_BASES, DEFAULT_EQUITY_CHART_PREFS.basis),
  };
}

export function writeEquityChartPrefs(prefs: Preferences, value: EquityChartPrefs): Preferences {
  // Normalised through the reader, so a bad value is never persisted.
  const clean = readEquityChartPrefs({ [EQUITY_TF_KEY]: value.tf, [EQUITY_BASIS_KEY]: value.basis });
  return { ...prefs, [EQUITY_TF_KEY]: clean.tf, [EQUITY_BASIS_KEY]: clean.basis };
}

/* -- v181: the Dashboard's scope preset ----------------------------------- */

/** The scope control's presets, in control order (spec v181 § 1). Defined
 *  here, beside the timeframes, because `equity-range.model.ts` imports from
 *  this module -- the model re-exports both, and consumers import them from
 *  there. An ad-hoc Range is not a preset and is never stored. */
export type ScopePreset = '1D' | '5D' | '1M' | '3M' | '6M' | 'YTD' | '1Y' | 'All';
export const SCOPE_PRESETS: readonly ScopePreset[] = ['1D', '5D', '1M', '3M', '6M', 'YTD', '1Y', 'All'];

export const SCOPE_PRESET_KEY = 'dashboard.scope.preset';

/** 1D: what the Today toggle showed before v181. */
export const DEFAULT_SCOPE_PRESET: ScopePreset = '1D';

export function readScopePreset(prefs: Preferences): ScopePreset {
  return pick(prefs?.[SCOPE_PRESET_KEY], SCOPE_PRESETS, DEFAULT_SCOPE_PRESET);
}

export function writeScopePreset(prefs: Preferences, preset: ScopePreset): Preferences {
  // Normalised through the reader, so a bad value is never persisted.
  return { ...prefs, [SCOPE_PRESET_KEY]: readScopePreset({ [SCOPE_PRESET_KEY]: preset }) };
}
