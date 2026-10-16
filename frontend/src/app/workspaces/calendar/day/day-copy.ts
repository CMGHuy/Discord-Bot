/* v165 D7 -- presentation honesty (financial-advisor seat). The spec's
 * exact strings, in one place, so the day page and the drawer cannot drift
 * apart and a spec asserts them verbatim. */

/** Top of the day page and the drawer's summary. `realized_pnl_amount`
 *  deducts no frictions (verified 2026-10-15). */
export const PAPER_CAPTION = 'Paper trades · P&L before commissions, fees and tax';

/** Fixed line in the "How this day compares" panel. */
export const ONE_DAY_CAVEAT = 'One day is not evidence of edge.';

/** Tooltip on every R figure's header. */
export const R_TOOLTIP = "R = the trade's initial risk (entry to stop). +1R made what was risked.";

/** The stop tick is the final recorded stop: a trailed or break-even
 *  runner's stop moved after entry. */
export const FINAL_STOP_LABEL = 'final stop';

/** The tiles' sample line when any row is a scale-out leg. */
export function legsSampleNote(rows: number): string {
  return `${rows} rows · scale-out legs count separately`;
}
