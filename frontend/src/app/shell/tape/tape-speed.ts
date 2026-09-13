/**
 * Shared between `sb-market-lane` and `sb-names-lane` so the two scroll at
 * the same pixels-per-second rate rather than the same fixed duration.
 *
 * The track is doubled and translated -50% over one duration (tape.css's
 * `tape-slide` keyframes), so the distance covered per loop is one copy's
 * rendered width -- `trackEl.scrollWidth / 2`. A single fixed duration for
 * every lane -- what this replaced -- made lanes with different tile
 * content visibly different speeds: the market lane's compact
 * symbol/price/change tiles and the watchlist tape's wider symbol/price/
 * change/context tiles do not render to the same width per tile, so even
 * scaling duration by TILE COUNT (tried first, and wrong) still left one
 * lane covering more pixels per second than the other. Measuring the
 * track's own actual width and dividing by a fixed pixels-per-second
 * target is the only way both are the same speed regardless of what their
 * tiles happen to contain.
 *
 * 5.3px/s reproduces the market lane's own historical rate: 26s (the fixed
 * duration this replaced) over its typical ~137px one-loop width with
 * today's four fixed indices, measured live rather than guessed.
 */
export const TAPE_PIXELS_PER_SECOND = 5.3;

/** A one-tile lane still needs to move; without a floor, a very narrow
 *  track (a single short symbol) would compute a near-zero duration and
 *  flicker rather than scroll. */
export const TAPE_MIN_DURATION_S = 4;

/** `trackWidth` is the DOUBLED track's full `scrollWidth` (both passes);
 *  callers pass it straight from `el.scrollWidth`, this halves it. */
export function tapeDurationSeconds(trackWidth: number): number {
  const oneLoop = trackWidth / 2;
  return Math.max(TAPE_MIN_DURATION_S, oneLoop / TAPE_PIXELS_PER_SECOND);
}
