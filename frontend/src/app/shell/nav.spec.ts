import { describe, expect, it } from 'vitest';

import { routes } from '../app.routes';
import { ICON_NAMES } from '../ui/icon';
import { NAV_GROUPS, PHONE_TABS, breadcrumbFor, detailCrumb, navEntryFor } from './nav';

const paths = (entries: readonly { path: string }[]) => entries.map((entry) => entry.path);
const allEntries = NAV_GROUPS.flatMap((group) => [...group.entries]);

describe('NAV_GROUPS (v195 §5.1)', () => {
  it('is four groups in rail order, named in sentence case', () => {
    expect(NAV_GROUPS.map((group) => [group.id, group.label])).toEqual([
      ['nav-monitor', 'Monitor'],
      ['nav-review', 'Review'],
      ['nav-insights', 'Insights'],
      ['nav-system', 'System'],
    ]);
  });

  it('puts each workspace in its group, in order', () => {
    expect(NAV_GROUPS.map((group) => paths(group.entries))).toEqual([
      ['/dashboard', '/watchlist', '/risk'],
      ['/trades', '/calendar', '/cancels'],
      ['/analytics', '/research', '/reports'],
      ['/system', '/versions'],
    ]);
  });

  it('lists all eleven workspaces once and leaves the /ui gallery off the rail', () => {
    expect(allEntries).toHaveLength(11);
    expect(new Set(paths(allEntries)).size).toBe(11);
    expect(paths(allEntries)).not.toContain('/ui');
  });

  it('labels each entry with its route title', () => {
    for (const entry of allEntries) {
      const route = routes.find((candidate) => `/${candidate.path}` === entry.path);
      expect(route, `no route for ${entry.path}`).toBeDefined();
      expect(route!.title).toBe(entry.label);
    }
  });

  it('draws each entry with a known icon, no two entries sharing one', () => {
    const icons = allEntries.map((entry) => entry.icon);
    for (const icon of icons) expect(ICON_NAMES).toContain(icon);
    expect(new Set(icons).size).toBe(icons.length);
  });
});

describe('PHONE_TABS (v195 Phase 3)', () => {
  it('is Dashboard, Watchlist, Trades and Risk, taken from the same model', () => {
    expect(paths(PHONE_TABS)).toEqual(['/dashboard', '/watchlist', '/trades', '/risk']);
    for (const tab of PHONE_TABS) expect(allEntries).toContain(tab);
  });
});

describe('navEntryFor', () => {
  const at = (url: string) => {
    const found = navEntryFor(url);
    return found ? [found.group.label, found.entry.label] : null;
  };

  it.each([
    ['/trades', ['Review', 'Trades']],
    ['/trades/812?tab=plan#why', ['Review', 'Trades']],
    ['/plans/5', ['Review', 'Trades']],
    ['/watchlist/NVDA', ['Monitor', 'Watchlist']],
    ['/universe', ['Monitor', 'Watchlist']],
    ['/calendar/2026-10-01', ['Review', 'Calendar']],
    ['/system?tab=providers', ['System', 'System']],
    ['/analytics', ['Insights', 'Analytics']],
  ])('places %s', (url, expected) => {
    expect(at(url)).toEqual(expected);
  });

  it.each(['/ui', '/', '', '/nowhere'])('finds nothing for %j', (url) => {
    expect(navEntryFor(url)).toBeNull();
  });
});

describe('breadcrumbFor', () => {
  it('is group then page on a workspace', () => {
    expect(breadcrumbFor('/risk', null)).toEqual(['Monitor', 'Risk']);
  });

  it('adds the detail segment a detail route supplies', () => {
    expect(breadcrumbFor('/trades/812', 'NVDA #812')).toEqual(['Review', 'Trades', 'NVDA #812']);
  });

  it('treats an empty detail as none', () => {
    expect(breadcrumbFor('/risk', '')).toEqual(['Monitor', 'Risk']);
  });

  it('is empty off the nav, so the caller can fall back to the route title', () => {
    expect(breadcrumbFor('/ui', 'anything')).toEqual([]);
  });
});

describe('detailCrumb', () => {
  it.each([
    ['NVDA', 812, 'NVDA #812'],
    ['NVDA', '812', 'NVDA #812'],
    ['NVDA', null, 'NVDA'],
    [null, 812, '#812'],
    ['  ', 7, '#7'],
    [null, null, ''],
    [null, '', ''],
  ] as const)('(%j, %j) is %j', (ticker, id, expected) => {
    expect(detailCrumb(ticker, id)).toBe(expected);
  });
});
