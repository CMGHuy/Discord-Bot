import { Preferences } from '../api/models';

/**
 * Reading and writing per-symbol watchlist tags -- view-only labels/groups
 * (v85 R7-03, spec D35).
 *
 * `data/watchlist.json` is read by the **bot** on every scan; a tag is a pure
 * UI concern the trading process must never see, so it is stored here, in the
 * same server-side preferences blob as everything else in `ui/table-prefs.ts`,
 * under one flat key (`watchlistTags`) rather than nested per-table dotted
 * keys -- there is no "table" or "density" axis to a symbol's tags, just a
 * map from symbol to its tag names.
 *
 * Follows `table-prefs.ts`'s tolerant-read convention: a stored value is a
 * *hint*, not a contract. Anything that is not a `Record<string, string[]>`
 * -- wrong type, a non-array value, a non-string entry -- is dropped rather
 * than trusted, so a hand-edited or stale blob degrades to "no tags" instead
 * of breaking whatever reads it.
 *
 * Per-symbol tagging actions (add one tag, remove one tag, rename a tag
 * across every symbol that has it) are deliberately not here: R7-05 is the
 * task that renders the tagging UI and knows what shape those actions need,
 * the same way SR15 -- not SR12 -- is what added `per_page`'s reader/writer
 * pair once the control that used it existed.
 */
export function readWatchlistTags(prefs: Preferences): Record<string, string[]> {
  const stored = prefs['watchlistTags'];
  if (typeof stored !== 'object' || stored === null || Array.isArray(stored)) return {};

  const result: Record<string, string[]> = {};
  for (const [symbol, tags] of Object.entries(stored as Record<string, unknown>)) {
    if (Array.isArray(tags) && tags.every((tag) => typeof tag === 'string')) {
      result[symbol] = [...tags];
    }
  }
  return result;
}

export function writeWatchlistTags(
  prefs: Preferences,
  tags: Record<string, string[]>,
): Preferences {
  return { ...prefs, watchlistTags: { ...tags } };
}
