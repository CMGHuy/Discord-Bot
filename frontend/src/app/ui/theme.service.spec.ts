import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { resolveToken } from './testing/resolve-token';
import { resolveTokenIn } from './testing/theme-tokens';
import { THEME_PREF_KEY, THEME_STORAGE, ThemeService, ThemeStorage, readTheme } from './theme.service';

/** An in-memory store, as a spec's stand-in for localStorage. */
class MapStorage implements ThemeStorage {
  readonly map = new Map<string, string>();
  get(key: string): string | null {
    return this.map.get(key) ?? null;
  }
  set(key: string, value: string): void {
    this.map.set(key, value);
  }
}

/** Private mode, a blocked origin or a full quota: both calls throw. */
const refusing: ThemeStorage = {
  get() {
    throw new Error('SecurityError');
  },
  set() {
    throw new Error('QuotaExceededError');
  },
};

function serviceWith(storage?: ThemeStorage): ThemeService {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      ...(storage ? [{ provide: THEME_STORAGE, useValue: storage }] : []),
    ],
  });
  return TestBed.inject(ThemeService);
}

const html = document.documentElement;
const attribute = () => html.dataset['theme'];
let meta: HTMLMetaElement;
let navyStyle: HTMLStyleElement;

beforeEach(() => {
  // jsdom has no theme-color meta and resolves only the flat Graphite fixture:
  // add the meta, and a Navy --bg the way tokens.css would supply it.
  meta = document.createElement('meta');
  meta.name = 'theme-color';
  meta.content = resolveToken('--bg');
  document.head.appendChild(meta);
  navyStyle = document.createElement('style');
  navyStyle.textContent = `:root[data-theme="navy"] { --bg: ${resolveTokenIn('navy', '--bg')}; }`;
  document.head.appendChild(navyStyle);
});

afterEach(() => {
  meta.remove();
  navyStyle.remove();
  delete html.dataset['theme'];
  localStorage.removeItem(THEME_PREF_KEY);
  vi.restoreAllMocks();
});

describe('readTheme (v225, v240: Navy is the default)', () => {
  it('defaults to navy when nothing is stored', () => {
    expect(readTheme(new MapStorage())).toBe('navy');
  });

  it('restores a stored graphite (Black) choice', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'graphite');
    expect(readTheme(storage)).toBe('graphite');
  });

  it('restores a stored navy choice', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'navy');
    expect(readTheme(storage)).toBe('navy');
  });

  it.each(['GRAPHITE', 'graphite ', ' graphite', '', 'black', 'dark', '{"theme":"graphite"}'])('reads %j as navy', (value) => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, value);
    expect(readTheme(storage)).toBe('navy');
  });

  it('falls back to navy when the storage throws', () => {
    expect(readTheme(refusing)).toBe('navy');
  });

  it('stores under the per-browser key ui.theme', () => {
    expect(THEME_PREF_KEY).toBe('ui.theme');
  });
});

describe('ThemeService (v225, v240)', () => {
  it('writes data-theme="navy" at construction when nothing is stored, and paints the meta Navy', () => {
    serviceWith(new MapStorage());
    expect(attribute()).toBe('navy');
    expect(meta.content).toBe(resolveTokenIn('navy', '--bg'));
  });

  it('restores a stored graphite choice onto <html> and the theme-color meta', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'graphite');
    const service = serviceWith(storage);
    expect(service.theme()).toBe('graphite');
    expect(attribute()).toBe('graphite');
    expect(meta.content).toBe(resolveToken('--bg'));
  });

  it('set() moves the signal, the attribute, the stored key and the meta together', () => {
    const storage = new MapStorage();
    const service = serviceWith(storage);
    service.set('graphite');
    expect([service.theme(), attribute(), storage.map.get(THEME_PREF_KEY)]).toEqual(['graphite', 'graphite', 'graphite']);
    expect(meta.content).toBe(resolveToken('--bg'));
    service.set('navy');
    expect([service.theme(), attribute(), storage.map.get(THEME_PREF_KEY)]).toEqual(['navy', 'navy', 'navy']);
    expect(meta.content).toBe(resolveTokenIn('navy', '--bg'));
  });

  it('toggle() flips between the two themes, starting from Navy', () => {
    const service = serviceWith(new MapStorage());
    service.toggle();
    expect(service.theme()).toBe('graphite');
    service.toggle();
    expect(service.theme()).toBe('navy');
  });

  it('does not rewrite a junk stored value until the user chooses', () => {
    const storage = new MapStorage();
    storage.set(THEME_PREF_KEY, 'GRAPHITE');
    const service = serviceWith(storage);
    expect(service.theme()).toBe('navy');
    expect(storage.map.get(THEME_PREF_KEY)).toBe('GRAPHITE');
  });

  it('starts navy, and still switches for the page life, when storage refuses both calls', () => {
    const service = serviceWith(refusing);
    expect(service.theme()).toBe('navy');
    expect(() => service.set('graphite')).not.toThrow();
    expect(service.theme()).toBe('graphite');
    expect(attribute()).toBe('graphite');
  });

  it('switches without a theme-color meta in the document', () => {
    meta.remove();
    const service = serviceWith(new MapStorage());
    expect(() => service.set('graphite')).not.toThrow();
    expect(attribute()).toBe('graphite');
  });
});

describe('the default storage is localStorage, guarded', () => {
  it('reads and writes ui.theme through localStorage', () => {
    localStorage.setItem(THEME_PREF_KEY, 'graphite');
    const service = serviceWith();
    expect(service.theme()).toBe('graphite');
    service.set('navy');
    expect(localStorage.getItem(THEME_PREF_KEY)).toBe('navy');
  });

  it('falls back to navy and keeps working when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('denied', 'SecurityError'); });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full', 'QuotaExceededError'); });
    const service = serviceWith();
    expect(service.theme()).toBe('navy');
    service.set('graphite');
    expect(attribute()).toBe('graphite');
  });
});

describe('the app boots the theme service', () => {
  it('app.config.ts instantiates ThemeService in an app initializer', () => {
    const config = readFileSync(join(process.cwd(), 'src/app/app.config.ts'), 'utf8');
    expect(config).toContain("import { ThemeService } from './ui/theme.service';");
    expect(config).toContain('provideAppInitializer(() => { inject(ThemeService); })');
  });
});
