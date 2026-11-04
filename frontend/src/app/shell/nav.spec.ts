import { describe, expect, it } from 'vitest';

import { routes } from '../app.routes';
import { ICON_NAMES } from '../ui/icon';
import {
  ALIASES, DESTINATION_LABEL_OVERRIDES, NAV_ENTRIES, NAV_GROUPS, PHONE_TABS, SECTION_LABEL_OVERRIDES,
  SECTION_WORDS, breadcrumbFor, detailCrumb, navEntryFor,
} from './nav';

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

  it('draws each entry with a known icon, no two entries sharing one', () => {
    const icons = allEntries.map((entry) => entry.icon);
    for (const icon of icons) expect(ICON_NAMES).toContain(icon);
    expect(new Set(icons).size).toBe(icons.length);
  });
});

const titleAt = (path: string) => routes.find((route) => `/${route.path}` === path)?.title;

describe('NAV_ENTRIES (v202 §1)', () => {
  it('is six destinations in rail order, System alone at the foot', () => {
    expect(NAV_ENTRIES.map((entry) => [entry.path, entry.label])).toEqual([
      ['/dashboard', 'Dashboard'], ['/watchlist', 'Watchlist'], ['/trades', 'Trades'],
      ['/risk', 'Risk'], ['/insights', 'Insights'], ['/system', 'System'],
    ]);
    expect(paths(NAV_ENTRIES.filter((entry) => entry.foot))).toEqual(['/system']);
  });

  it('gives Trades, Insights and System their sections, the first one the default', () => {
    const sections = Object.fromEntries(
      NAV_ENTRIES.map((entry) => [entry.path, entry.sections?.map((s) => [s.path, s.label]) ?? null]),
    );
    expect(sections).toEqual({
      '/dashboard': null, '/watchlist': null, '/risk': null,
      '/trades': [['/trades', 'Book'], ['/trades/calendar', 'Calendar'], ['/trades/cancels', 'Cancels']],
      '/insights': [['/insights/analytics', 'Analytics'], ['/insights/research', 'Research'], ['/insights/reports', 'Reports']],
      '/system': [['/system', 'Health'], ['/system/versions', 'Versions']],
    });
  });

  it('keeps every section under its destination and leaves the /ui gallery off the rail', () => {
    for (const entry of NAV_ENTRIES) {
      for (const section of entry.sections ?? []) {
        expect(section.path === entry.path || section.path.startsWith(`${entry.path}/`), section.path).toBe(true);
      }
    }
    expect(paths(NAV_ENTRIES)).not.toContain('/ui');
  });

  it('labels every section with its route title, unless an override records why not', () => {
    for (const section of NAV_ENTRIES.flatMap((entry) => entry.sections ?? [])) {
      expect(titleAt(section.path), `no route for ${section.path}`).toBeDefined();
      expect(section.label, section.path).toBe(SECTION_LABEL_OVERRIDES[section.path] ?? titleAt(section.path));
    }
  });

  it("labels every destination with its first section's route title, unless an override records why not", () => {
    for (const entry of NAV_ENTRIES) {
      const first = entry.sections?.[0].path ?? entry.path;
      expect(titleAt(first), `no route for ${first}`).toBeDefined();
      expect(entry.label, entry.path).toBe(DESTINATION_LABEL_OVERRIDES[entry.path] ?? titleAt(first));
    }
  });

  it('records exactly its overrides, each one differing from the title it stands in for', () => {
    expect(SECTION_LABEL_OVERRIDES).toEqual({ '/trades': 'Book', '/system': 'Health' });
    expect(DESTINATION_LABEL_OVERRIDES).toEqual({ '/insights': 'Insights' });
    for (const [path, label] of Object.entries(SECTION_LABEL_OVERRIDES)) expect(titleAt(path)).not.toBe(label);
    expect(titleAt('/insights/analytics')).not.toBe(DESTINATION_LABEL_OVERRIDES['/insights']);
  });

  it('draws each destination with a known icon, no two sharing one', () => {
    const icons = NAV_ENTRIES.map((entry) => entry.icon);
    for (const icon of icons) expect(ICON_NAMES).toContain(icon);
    expect(new Set(icons).size).toBe(icons.length);
  });

  it('names the section words of the second-segment rule', () => {
    expect([...SECTION_WORDS].sort()).toEqual(['analytics', 'calendar', 'cancels', 'reports', 'research', 'versions']);
  });
});

describe('ALIASES (v202 §1)', () => {
  it('maps every moved page and the older renames onto their new home', () => {
    expect(ALIASES).toEqual({
      '/plans': '/trades', '/universe': '/watchlist', '/cockpit': '/dashboard',
      '/calendar': '/trades/calendar', '/cancels': '/trades/cancels',
      '/analytics': '/insights/analytics', '/research': '/insights/research', '/reports': '/insights/reports',
      '/versions': '/system/versions',
    });
  });

  it('agrees with the redirects app.routes.ts declares', () => {
    for (const [from, to] of Object.entries(ALIASES)) {
      if (from === '/plans') continue; // plans/:id is a real detail route of the trade book, not a redirect
      const route = routes.find((candidate) => `/${candidate.path}` === from);
      expect(route?.redirectTo, from).toBe(to.slice(1));
    }
  });

  it('lands every alias on a destination path or one of its sections', () => {
    const known = new Set(NAV_ENTRIES.flatMap((entry) => [entry.path, ...paths(entry.sections ?? [])]));
    for (const to of Object.values(ALIASES)) expect(known.has(to), to).toBe(true);
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
