/**
 * Used by `sb-tape` (the combined market/watchlist strip) to size the
 * track's animation-duration from its own rendered width rather than a
 * fixed duration -- see `tapeDurationSeconds` below.
 *
 * The track is doubled and translated -50% over one duration (tape.css's
 * `tape-slide` keyframes), so the distance covered per loop is one copy's
 * rendered width -- `trackEl.scrollWidth / 2`. A fixed duration regardless
 * of content -- what this replaced -- made a short loop and a long one
 * scroll at visibly different speeds; measuring the track's own actual
 * width and dividing by a fixed pixels-per-second target is what keeps the
 * rate constant regardless of how many tiles happen to be flagged.
 *
 * History: 5.3px/s reproduced the original (pre-merge) market lane's rate.
 * Slowed to 3.5px/s (2026-09-14) once the `.track` flex-shrink bug
 * (tape.css) that had been crushing tiles into illegibility was fixed --
 * legible tiles made the original rate feel faster than intended. Doubled
 * to 7.0px/s (2026-09-14, same day) once the two lanes were combined into
 * one strip, then doubled again to 14.0px/s (2026-09-14, same day) on a
 * further direct request. Increased by 2.5x again so the combined strip
 * keeps moving at a glance without pausing on a single tile.
 */
export const TAPE_PIXELS_PER_SECOND = 35.0;

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
