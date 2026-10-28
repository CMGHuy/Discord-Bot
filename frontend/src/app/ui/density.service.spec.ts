import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  DENSITY_PREF_KEY,
  DENSITY_STORAGE,
  DensityService,
  DensityStorage,
  readDensity,
} from './density.service';

/** An in-memory store, as a spec's stand-in for localStorage. */
class MapStorage implements DensityStorage {
  readonly map = new Map<string, string>();
  get(key: string): string | null {
    return this.map.get(key) ?? null;
  }
  set(key: string, value: string): void {
    this.map.set(key, value);
  }
}

/** Private mode, a blocked origin or a full quota: both calls throw. */
const refusing: DensityStorage = {
  get() {
    throw new Error('SecurityError');
  },
  set() {
    throw new Error('QuotaExceededError');
  },
};

function serviceWith(storage?: DensityStorage): DensityService {
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      ...(storage ? [{ provide: DENSITY_STORAGE, useValue: storage }] : []),
    ],
  });
  return TestBed.inject(DensityService);
}

const attribute = () => document.documentElement.dataset['density'];

afterEach(() => {
  delete document.documentElement.dataset['density'];
  localStorage.removeItem(DENSITY_PREF_KEY);
  vi.restoreAllMocks();
});

describe('readDensity (v195 §1.4)', () => {
  it('defaults to dense when nothing is stored', () => {
    expect(readDensity(new MapStorage())).toBe('dense');
  });

  it('restores a stored comfortable choice', () => {
    const storage = new MapStorage();
    storage.set(DENSITY_PREF_KEY, 'comfortable');
    expect(readDensity(storage)).toBe('comfortable');
  });

  it.each(['dense', 'compact', 'COMFORTABLE', '', '{"density":"comfortable"}'])(
    'reads %j as dense',
    (stored) => {
      const storage = new MapStorage();
      storage.set(DENSITY_PREF_KEY, stored);
      expect(readDensity(storage)).toBe('dense');
    },
  );

  it('falls back to dense when the storage throws', () => {
    expect(readDensity(refusing)).toBe('dense');
  });

  it('stores under the per-device key ui.density', () => {
    expect(DENSITY_PREF_KEY).toBe('ui.density');
  });
});

describe('DensityService (v195 §1.4)', () => {
  it('writes data-density="dense" on <html> at construction when nothing is stored', () => {
    const service = serviceWith(new MapStorage());
    expect(service.density()).toBe('dense');
    expect(attribute()).toBe('dense');
  });

  it('restores a stored comfortable choice onto <html>', () => {
    const storage = new MapStorage();
    storage.set(DENSITY_PREF_KEY, 'comfortable');
    const service = serviceWith(storage);
    expect(service.density()).toBe('comfortable');
    expect(attribute()).toBe('comfortable');
  });

  it('set() moves the signal, the attribute and the stored key together', () => {
    const storage = new MapStorage();
    const service = serviceWith(storage);
    service.set('comfortable');
    expect(service.density()).toBe('comfortable');
    expect(attribute()).toBe('comfortable');
    expect(storage.map.get(DENSITY_PREF_KEY)).toBe('comfortable');
    service.set('dense');
    expect(attribute()).toBe('dense');
    expect(storage.map.get(DENSITY_PREF_KEY)).toBe('dense');
  });

  it('starts dense, and still switches for the session, when storage refuses both calls', () => {
    const service = serviceWith(refusing);
    expect(service.density()).toBe('dense');
    expect(attribute()).toBe('dense');
    expect(() => service.set('comfortable')).not.toThrow();
    expect(service.density()).toBe('comfortable');
    expect(attribute()).toBe('comfortable');
  });
});

describe('the default storage is localStorage, guarded', () => {
  it('reads and writes ui.density through localStorage', () => {
    localStorage.setItem(DENSITY_PREF_KEY, 'comfortable');
    const service = serviceWith();
    expect(service.density()).toBe('comfortable');
    service.set('dense');
    expect(localStorage.getItem(DENSITY_PREF_KEY)).toBe('dense');
  });

  it('falls back to dense and keeps working when localStorage throws', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('full', 'QuotaExceededError');
    });
    const service = serviceWith();
    expect(service.density()).toBe('dense');
    expect(() => service.set('comfortable')).not.toThrow();
    expect(attribute()).toBe('comfortable');
  });
});

describe('the app boots the density service', () => {
  it('app.config.ts instantiates DensityService in an app initializer', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/app.config.ts'), 'utf8');
    expect(source).toContain("import { DensityService } from './ui/density.service';");
    expect(source).toContain('provideAppInitializer(() => { inject(DensityService); })');
  });
});
