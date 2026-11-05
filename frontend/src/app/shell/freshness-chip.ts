const MINUTE_MS = 60_000;

/**
 * How long ago the bot last completed a scan tick, at minute resolution --
 * v195 Phase 3. `format.ts`'s `age()` reads in hours ("<1h"), which is the
 * right unit for a plan's age and the wrong one for a bot that ticks every
 * few minutes. A time from the future (clock skew) reads "just now", never
 * a negative age. `null` when there is no readable time.
 */
export function scanAge(at: string | null, now: number): string | null {
  if (!at) return null;
  const then = Date.parse(at);
  if (Number.isNaN(then)) return null;
  const minutes = Math.floor(Math.max(0, now - then) / MINUTE_MS);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}
