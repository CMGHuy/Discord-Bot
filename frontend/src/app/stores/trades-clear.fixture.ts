import { ClearHistoryResult } from '../api/models';

/* v189 A6: the clear-history replies, as V189-16's endpoint sends them. */

export const REFUSED = 'Reset refused: the kill switch is tripped. Release it first, or force the reset '
  + '(`force=true` on the endpoint, `!trades clear history force` or '
  + '`/trades-clear-history force:True`); the kill switch stays on either way.';

export const RESET: ClearHistoryResult = {
  removed: 4, removed_plans: 2, archive: 'account-reset-20261024T101500Z.json',
  throttle: { multiplier: 1, paused: false }, kill_switch: false,
  notice: 'Account reset: removed 4 closed trade(s) and 2 finished plan(s). ...\nArchive: account-reset-20261024T101500Z.json\n...',
};
