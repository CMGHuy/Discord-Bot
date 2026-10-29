import { Killswitch, LastKnownKillswitch } from './models';

/** Project a failed read without promoting an old observation to current state. */
export function unavailableKillswitch(
  previous: Killswitch | null, checkedAt = new Date().toISOString(),
): Killswitch {
  const last: LastKnownKillswitch | undefined = typeof previous?.on === 'boolean'
    ? { on: previous.on, reason: previous.reason, at: previous.at,
        checked_at: previous.availability.checked_at }
    : previous?.last_known;
  return {
    on: null, reason: null, at: null,
    availability: { state: 'unavailable', checked_at: checkedAt, reason: 'request_unavailable' },
    ...(last ? { last_known: last } : {}),
  };
}
