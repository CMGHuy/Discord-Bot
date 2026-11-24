import { InjectionToken } from '@angular/core';

import { DEFAULT_PHONE_TAB_PATHS, NavEntry } from './nav';

/**
 * The pages the phone's bottom tab bar holds -- spec v240 §6 (D9).
 *
 * A per-BROWSER preference in localStorage['ui.tabbar'], not PreferencesStore:
 * the partner chose per browser (a phone and a desktop want different bars),
 * as for ui.theme (theme.service.ts's header records why that exception to
 * the plan v21 rule holds). Its own TAB_BAR_STORAGE token, mirroring
 * THEME_STORAGE, so a spec swaps in an in-memory map.
 *
 * The stored value is a JSON array of nav paths, validated on every read
 * against the pages the login may open (navEntriesFor(isAdmin)): unknown,
 * duplicate and admin-only-for-a-viewer paths drop, the Dashboard is forced
 * first, the list is cut to MAX_TAB_PAGES; nothing valid, or not JSON, gives
 * the default. A stored '/trades/calendar' (pre-v247) is '/calendar'.
 */
export const TAB_BAR_PREF_KEY = 'ui.tabbar';

/** Pages on the bar, the Dashboard included; More is always added after them. */
export const MAX_TAB_PAGES = 4;

/** The pinned first tab; the editor offers it no buttons. */
const HOME_PATH = '/dashboard';

/** Paths a stored list may still hold from before a move (v247: Calendar left Trades). */
const RENAMED_TAB_PATHS: Readonly<Record<string, string>> = { '/trades/calendar': '/calendar' };

/** The two calls the service needs; a spec swaps it for an in-memory map. */
export interface TabBarStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

function localStorageTabBar(): TabBarStorage {
  return {
    get(key: string): string | null {
      try { return globalThis.localStorage?.getItem(key) ?? null; } catch { return null; }
    },
    set(key: string, value: string): void {
      try { globalThis.localStorage?.setItem(key, value); } catch { /* Private mode or a full quota: the choice lasts this session. */ }
    },
  };
}

export const TAB_BAR_STORAGE = new InjectionToken<TabBarStorage>('TAB_BAR_STORAGE', {
  providedIn: 'root',
  factory: localStorageTabBar,
});

function defaultPaths(known: ReadonlySet<string>): string[] {
  return DEFAULT_PHONE_TAB_PATHS.filter((path) => known.has(path));
}

/** The valid bar for a raw stored value and the pages the login may open. Pure. */
export function sanitizeTabPaths(raw: unknown, visible: readonly NavEntry[]): string[] {
  const known = new Set(visible.map((entry) => entry.path));
  if (!Array.isArray(raw)) return defaultPaths(known);
  const kept = new Set(
    raw
      .filter((item): item is string => typeof item === 'string')
      .map((path) => RENAMED_TAB_PATHS[path] ?? path)
      .filter((path) => known.has(path)),
  );
  if (kept.size === 0) return defaultPaths(known);
  kept.delete(HOME_PATH);
  const home = known.has(HOME_PATH) ? [HOME_PATH] : [];
  return [...home, ...kept].slice(0, MAX_TAB_PAGES);
}

/** The stored value parsed, or null when it is missing, not JSON or unreadable. */
function parseStored(storage: TabBarStorage): unknown {
  try {
    const text = storage.get(TAB_BAR_PREF_KEY);
    return text === null ? null : JSON.parse(text);
  } catch {
    return null;
  }
}

export function readTabPaths(storage: TabBarStorage, visible: readonly NavEntry[]): string[] {
  return sanitizeTabPaths(parseStored(storage), visible);
}
