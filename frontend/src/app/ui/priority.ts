import { Viewport } from './breakpoints';

/**
 * Content priority — spec v95 §3.
 *
 * One field, `inlineFrom`, on every displayable thing: the NARROWEST viewport
 * at which it appears inline. Below that floor it is **demoted, never
 * removed** — every demoted item has a named destination (`DemotionTarget`),
 * and the parity gate asserts it is reachable through one.
 *
 * Deliberately not a numeric rank. Reusing `Viewport` means there is one
 * scale in the app rather than two that have to be kept in step, and it makes
 * a declaration readable on its own: `inlineFrom: 'md'` says where it appears,
 * not how important someone thought it was.
 *
 * Pure, so it tests without a browser — jsdom lays nothing out, so a test that
 * asserted on a resolved width here would be theatre.
 */

/** Every viewport, narrowest first. The order comparisons are made in. */
export const VIEWPORT_ORDER: readonly Viewport[] = ['xs', 'sm', 'md', 'lg', 'xl'] as const;

/** Position in `VIEWPORT_ORDER`. `-1` is unreachable for a typed `Viewport`. */
export function rankOf(viewport: Viewport): number {
  return VIEWPORT_ORDER.indexOf(viewport);
}

/**
 * Does this item render inline at this viewport?
 *
 * The floor is INCLUSIVE — `isInline('md', 'md')` is `true` — matching the
 * min-width semantics `BREAKPOINTS` already uses. An undeclared floor means
 * always inline, so adding `inlineFrom` to an existing type changes nothing
 * until a call site opts in.
 */
export function isInline(inlineFrom: Viewport | undefined, viewport: Viewport): boolean {
  if (inlineFrom === undefined) return true;
  return rankOf(viewport) >= rankOf(inlineFrom);
}

/** Where a demoted item goes. One per kind — spec v95 §4. */
export type DemotionTarget =
  /** A column, into the row's existing `expansion` template. */
  | 'expansion'
  /** A control, into its toolbar's filter sheet. */
  | 'sheet'
  /** A panel, into its own collapsed digest. */
  | 'digest';

/** What the parity gate (E1) walks. */
export interface PriorityDecl {
  /** Unique within its surface — a column key, a control name, a panel id. */
  id: string;
  inlineFrom?: Viewport;
  demotesTo: DemotionTarget;
}

/**
 * Which of these declarations are NOT reachable at some viewport — v95 §9.
 *
 * Returns the failing ids, empty when every item is reachable everywhere.
 * Returning ids rather than throwing keeps it usable outside a test, and
 * makes a failure name what broke instead of only that something did.
 *
 * A declaration fails when it demotes but names no destination, or names one
 * this surface does not provide. It does NOT fail merely for being demoted —
 * that is the whole design.
 */
export function assertReachable(decls: PriorityDecl[]): string[] {
  const failed: string[] = [];
  const targets: ReadonlySet<DemotionTarget> = new Set(['expansion', 'sheet', 'digest']);

  for (const decl of decls) {
    const demotesSomewhere = VIEWPORT_ORDER.some((v) => !isInline(decl.inlineFrom, v));
    if (demotesSomewhere && !targets.has(decl.demotesTo)) {
      failed.push(decl.id);
    }
  }
  return failed;
}
