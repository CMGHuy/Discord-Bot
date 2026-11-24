import { describe, expect, it } from 'vitest';

import { TAB_PAGES } from '../shell/palette/palette-items';
import { allSources } from '../ui/testing/all-sources';

/**
 * v202 §2: the five page names that moved under a destination. Their old
 * paths still redirect (app.routes.ts, until Phase 4's close-out), but no
 * link inside the app may lean on that redirect: a hop through it costs a
 * navigation and lights the wrong rail entry for a frame. `/calendar` left
 * this list in v247, when Calendar became a destination again.
 */
const OLD_PATH_WORDS = ['cancels', 'analytics', 'research', 'reports', 'versions'];

/** v247 (spec v240 §6): whole addresses that moved and redirect, for the same reason. */
const MOVED_PATHS = ['/trades/calendar'];

/**
 * Every way a source names a route: a static or bound routerLink, a router
 * call, a palette tab and a palette item's route. API paths
 * ('/analytics/strategies' in a comment, `${base}/calendar/pnl`) sit in no
 * link context and never match. `\x60` is a backtick (a template-literal route).
 */
const LINK_CONTEXT = String.raw`(?:routerLink="|\[routerLink\]="\['|navigate\(\['|navigateByUrl\(['\x60]|route: ['\x60]|tab\(')`;

/** The path must START at the old word, so '/insights/analytics' never
 *  matches, and the word must end there, so '/reportsX' does not either. */
const LINK_TO_OLD_PATH = new RegExp(String.raw`${LINK_CONTEXT}/(?:${OLD_PATH_WORDS.join('|')})(?![\w-])`);

const LINK_TO_MOVED_PATH = new RegExp(String.raw`${LINK_CONTEXT}(?:${MOVED_PATHS.join('|')})(?![\w-])`);

const isOldPath = (route: string | null): boolean =>
  route !== null && OLD_PATH_WORDS.some((word) => route === `/${word}` || route.startsWith(`/${word}/`));

const isMovedPath = (route: string | null): boolean =>
  route !== null && MOVED_PATHS.some((path) => route === path || route.startsWith(`${path}/`));

const offendersOf = (pattern: RegExp) => allSources()
  .filter((file) => /\.(ts|html)$/.test(file.name))
  .filter((file) => pattern.test(file.source))
  .map((file) => file.name);

describe('no in-app link points at a pre-v202 path', () => {
  it.each([
    'routerLink="/analytics"',
    `[routerLink]="['/versions', id]"`,
    `[routerLink]="['/research']"`,
    `tab('/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigateByUrl('/versions')`,
    `navigate(['/reports'], { queryParams })`,
    `route: '/research'`,
    'route: `/cancels/${id}`',
  ])('the scan catches %s', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(true);
  });

  it.each([
    'routerLink="/calendar"',
    `[routerLink]="['/calendar', day]"`,
    `tab('/insights/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigate(['/trades', id])`,
    '/** `/analytics/strategies`, for the read-only Strategy tab. */',
    "{ path: 'analytics', pathMatch: 'full', redirectTo: 'insights/analytics' }",
    'routerLink="/reportsX"',
  ])('the scan lets %s through', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(false);
  });

  it('finds no such link in any source under frontend/src', () => {
    expect(offendersOf(LINK_TO_OLD_PATH)).toEqual([]);
  });

  it('opens no palette tab on an old path', () => {
    expect(TAB_PAGES.filter((item) => isOldPath(item.route)).map((item) => item.key)).toEqual([]);
  });
});

describe('no in-app link points at /trades/calendar (v247)', () => {
  it.each([
    'routerLink="/trades/calendar"',
    `[routerLink]="['/trades/calendar', day]"`,
    `[routerLink]="['/trades/calendar']"`,
    `navigateByUrl('/trades/calendar?month=2026-11')`,
    `route: '/trades/calendar'`,
  ])('the scan catches %s', (markup) => {
    expect(LINK_TO_MOVED_PATH.test(markup)).toBe(true);
  });

  it.each([
    'routerLink="/calendar"',
    `[routerLink]="['/calendar', day]"`,
    `[routerLink]="['/trades', id]"`,
    "{ path: 'trades/calendar', pathMatch: 'full', redirectTo: 'calendar' }",
    'routerLink="/trades/calendarX"',
  ])('the scan lets %s through', (markup) => {
    expect(LINK_TO_MOVED_PATH.test(markup)).toBe(false);
  });

  it('finds no such link in any source under frontend/src', () => {
    expect(offendersOf(LINK_TO_MOVED_PATH)).toEqual([]);
  });

  it('opens no palette tab on the moved address', () => {
    expect(TAB_PAGES.filter((item) => isMovedPath(item.route)).map((item) => item.key)).toEqual([]);
  });
});
