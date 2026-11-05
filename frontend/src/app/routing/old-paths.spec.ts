import { describe, expect, it } from 'vitest';

import { TAB_PAGES } from '../shell/palette/palette-items';
import { allSources } from '../ui/testing/all-sources';

/**
 * v202 §2: the six page names that moved under a destination. Their old
 * paths still redirect (app.routes.ts, until Phase 4's close-out), but no
 * link inside the app may lean on that redirect: a hop through it costs a
 * navigation and lights the wrong rail entry for a frame.
 */
const OLD_PATH_WORDS = ['calendar', 'cancels', 'analytics', 'research', 'reports', 'versions'];

/**
 * Every way a source names a route: a static or bound routerLink, a router
 * call, a palette tab and a palette item's route. The path must START at the
 * old word, so '/trades/calendar' never matches, and the word must end there,
 * so '/reportsX' does not either. API paths ('/analytics/strategies' in a
 * comment, `${base}/calendar/pnl`) sit in no link context and never match.
 * `\x60` is a backtick (a template-literal route).
 */
const LINK_TO_OLD_PATH = new RegExp(
  String.raw`(?:routerLink="|\[routerLink\]="\['|navigate\(\['|navigateByUrl\(['\x60]|route: ['\x60]|tab\(')/(?:${OLD_PATH_WORDS.join('|')})(?![\w-])`,
);

const isOldPath = (route: string | null): boolean =>
  route !== null && OLD_PATH_WORDS.some((word) => route === `/${word}` || route.startsWith(`/${word}/`));

describe('no in-app link points at a pre-v202 path', () => {
  it.each([
    'routerLink="/calendar"',
    `[routerLink]="['/calendar', day]"`,
    `[routerLink]="['/calendar']"`,
    `tab('/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigateByUrl('/versions')`,
    `navigate(['/reports'], { queryParams })`,
    `route: '/research'`,
    'route: `/cancels/${id}`',
  ])('the scan catches %s', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(true);
  });

  it.each([
    'routerLink="/trades/calendar"',
    `[routerLink]="['/trades/calendar', day]"`,
    `tab('/insights/analytics', 'Analytics', 'edge', 'Edge')`,
    `navigate(['/trades', id])`,
    '/** `/analytics/strategies`, for the read-only Strategy tab. */',
    "{ path: 'calendar', pathMatch: 'full', redirectTo: 'trades/calendar' }",
    'routerLink="/reportsX"',
  ])('the scan lets %s through', (markup) => {
    expect(LINK_TO_OLD_PATH.test(markup)).toBe(false);
  });

  it('finds no such link in any source under frontend/src', () => {
    const offenders = allSources()
      .filter((file) => /\.(ts|html)$/.test(file.name))
      .filter((file) => LINK_TO_OLD_PATH.test(file.source))
      .map((file) => file.name);
    expect(offenders).toEqual([]);
  });

  it('opens no palette tab on an old path', () => {
    expect(TAB_PAGES.filter((item) => isOldPath(item.route)).map((item) => item.key)).toEqual([]);
  });
});
