import { describe, expect, it } from 'vitest';

import { routes } from '../app.routes';
import { ICON_NAMES } from '../ui/icon';
import {
  ALIASES, DESTINATION_LABEL_OVERRIDES, NAV_ENTRIES, PHONE_TABS, SECTION_LABEL_OVERRIDES, SECTION_WORDS,
  breadcrumbFor, destinationFor, detailCrumb, isSectionUrl, navEntryFor, phoneTabPathFor,
} from './nav';

const paths = (entries: readonly { path: string }[]) => entries.map((entry) => entry.path);

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

describe('PHONE_TABS', () => {
  it('is Home, Watchlist, Calendar and Trades, each drawn with its destination or section icon', () => {
    expect(paths(PHONE_TABS)).toEqual(['/dashboard', '/watchlist', '/trades/calendar', '/trades']);
    expect(PHONE_TABS.map((tab) => tab.label)).toEqual(['Home', 'Watchlist', 'Calendar', 'Trades']);
    for (const tab of PHONE_TABS.filter((candidate) => candidate.path !== '/trades/calendar')) {
      expect(NAV_ENTRIES.find((entry) => entry.path === tab.path)?.icon).toBe(tab.icon);
    }
  });
});

describe('navEntryFor (v202 second-segment rule)', () => {
  const at = (url: string) => {
    const found = navEntryFor(url);
    return found ? [found.entry.label, found.section?.label ?? null] : null;
  };

  it.each([
    ['/dashboard', ['Dashboard', null]],
    ['/trades', ['Trades', 'Book']],
    ['/trades/812?tab=plan#why', ['Trades', 'Book']],
    ['/trades/calendar', ['Trades', 'Calendar']],
    ['/trades/calendar/2026-10-01', ['Trades', 'Calendar']],
    ['/trades/cancels?page=2', ['Trades', 'Cancels']],
    // Another destination's word is a detail id here, not a section.
    ['/trades/analytics', ['Trades', 'Book']],
    ['/plans/5', ['Trades', 'Book']],
    ['/watchlist/NVDA', ['Watchlist', null]],
    ['/universe', ['Watchlist', null]],
    ['/cockpit', ['Dashboard', null]],
    ['/calendar/2026-10-01', ['Trades', 'Calendar']],
    ['/cancels', ['Trades', 'Cancels']],
    ['/analytics?tab=tuning#x', ['Insights', 'Analytics']],
    ['/research', ['Insights', 'Research']],
    ['/reports', ['Insights', 'Reports']],
    ['/insights', ['Insights', 'Analytics']],
    ['/insights/reports?tab=gates', ['Insights', 'Reports']],
    ['/system?tab=providers', ['System', 'Health']],
    ['/system/versions', ['System', 'Versions']],
    ['/versions', ['System', 'Versions']],
  ])('places %s', (url, expected) => {
    expect(at(url)).toEqual(expected);
  });

  it.each(['/ui', '/', '', '/nowhere', '/nowhere/calendar'])('finds nothing for %j', (url) => {
    expect(navEntryFor(url)).toBeNull();
  });
});

describe('phoneTabPathFor', () => {
  it.each([
    ['/trades/calendar/2026-10-01', '/trades/calendar'],
    ['/calendar', '/trades/calendar'],
    ['/trades', '/trades'],
    ['/trades/cancels', '/trades'],
    ['/trades/812', '/trades'],
    ['/plans/5', '/trades'],
    ['/dashboard', '/dashboard'],
    ['/risk', '/risk'],
    ['/system/versions', '/system'],
    ['/ui', null],
  ])('lights %s on the %j tab', (url, expected) => {
    expect(phoneTabPathFor(url)).toBe(expected);
  });
});

describe('destinationFor', () => {
  it.each([
    ['/analytics?tab=tuning#x', '/insights'],
    ['/trades/812', '/trades'],
    ['/trades/calendar/2026-10-01', '/trades'],
    ['/system/versions', '/system'],
    ['/risk', '/risk'],
    ['/ui', null],
    ['', null],
  ])('is the destination path of %j', (url, expected) => {
    expect(destinationFor(url)).toBe(expected);
  });
});

describe('isSectionUrl', () => {
  it.each(['/trades/calendar', '/trades/calendar/2026-10-01', '/trades/cancels', '/insights/analytics',
    '/insights/research?page=2', '/system/versions', '/calendar', '/versions'])('is true for %s', (url) => {
    expect(isSectionUrl(url)).toBe(true);
  });

  it.each(['/trades', '/trades/812', '/trades/analytics', '/system', '/system?tab=logs', '/risk',
    '/watchlist/NVDA', '/plans/5', '/ui', ''])('is false for %j', (url) => {
    expect(isSectionUrl(url)).toBe(false);
  });
});

describe('breadcrumbFor (Destination / Section)', () => {
  it.each([
    ['/risk', null, ['Risk']],
    ['/risk', '', ['Risk']],
    ['/trades', null, ['Trades', 'Book']],
    ['/trades/calendar', null, ['Trades', 'Calendar']],
    ['/insights/analytics?tab=edge', null, ['Insights', 'Analytics']],
    ['/system', null, ['System', 'Health']],
    ['/system/versions', null, ['System', 'Versions']],
    ['/trades/812', 'NVDA #812', ['Trades', 'Book', 'NVDA #812']],
    ['/trades/calendar/2026-10-01', 'Calendar day', ['Trades', 'Calendar', 'Calendar day']],
    ['/watchlist/NVDA', 'NVDA', ['Watchlist', 'NVDA']],
  ])('reads %s (detail %j) as %j', (url, detail, expected) => {
    expect(breadcrumbFor(url, detail)).toEqual(expected);
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
