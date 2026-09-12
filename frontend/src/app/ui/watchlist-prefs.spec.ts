import { describe, expect, it } from 'vitest';

import { Preferences } from '../api/models';
import { readWatchlistTags, writeWatchlistTags } from './watchlist-prefs';

/* v85 R7-03 -- tags are a pure UI concern stored in the preferences blob,
 * never in the bot-facing data/watchlist.json (spec D35). These are pure
 * functions over a plain object, tested directly for the same reason
 * table-prefs.spec.ts tests its readers directly: the tolerance is the whole
 * point, and a store's plumbing would obscure it. */

describe('readWatchlistTags', () => {
  it('defaults to an empty object rather than missing', () => {
    expect(readWatchlistTags({})).toEqual({});
  });

  it('returns a stored tag map', () => {
    const prefs = { watchlistTags: { AAPL: ['Tech'], MSFT: ['Tech', 'Mega Cap'] } };
    expect(readWatchlistTags(prefs)).toEqual({ AAPL: ['Tech'], MSFT: ['Tech', 'Mega Cap'] });
  });

  it('treats a non-object value as absent', () => {
    // Cast past the typed property on purpose: the point of these cases is a
    // hand-edited or stale blob, which the type system cannot rule out at
    // runtime -- that is exactly why every reader validates (models.ts).
    expect(readWatchlistTags({ watchlistTags: 'not an object' } as unknown as Preferences)).toEqual({});
    expect(readWatchlistTags({ watchlistTags: null } as unknown as Preferences)).toEqual({});
    expect(readWatchlistTags({ watchlistTags: ['AAPL'] } as unknown as Preferences)).toEqual({});
  });

  it('drops a symbol whose tags are not a string array, keeps the rest', () => {
    const prefs = {
      watchlistTags: {
        AAPL: ['Tech'],
        MSFT: 'Tech',
        TSLA: [1, 2],
      },
    } as unknown as Preferences;
    expect(readWatchlistTags(prefs)).toEqual({ AAPL: ['Tech'] });
  });
});

describe('writeWatchlistTags', () => {
  it('sets the whole tag map', () => {
    const result = writeWatchlistTags({}, { AAPL: ['Tech'] });
    expect(result.watchlistTags).toEqual({ AAPL: ['Tech'] });
  });

  it('keeps other preference keys untouched', () => {
    const result = writeWatchlistTags({ tables: { trades: ['ticker'] } }, { AAPL: ['Tech'] });
    expect(result.tables).toEqual({ trades: ['ticker'] });
    expect(result.watchlistTags).toEqual({ AAPL: ['Tech'] });
  });
});
