import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it } from 'vitest';

import {
  RATE_DEFAULT,
  RATE_MAX,
  RATE_MIN,
  VOICE_DEFAULTS,
  VOICE_STORAGE,
  VOICE_STORAGE_KEY,
  VoicePrefs,
  VoiceStorage,
  familyDefault,
  parseVoicePrefs,
} from './voice-prefs';

class MapStorage implements VoiceStorage {
  readonly map = new Map<string, string>();
  writes = 0;
  get(key: string): string | null {
    return this.map.get(key) ?? null;
  }
  set(key: string, value: string): void {
    this.writes += 1;
    this.map.set(key, value);
  }
}

const refusing: VoiceStorage = {
  get: () => {
    throw new Error('blocked');
  },
  set: () => {
    throw new Error('quota');
  },
};

function prefsWith(storage: VoiceStorage): VoicePrefs {
  TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection(), { provide: VOICE_STORAGE, useValue: storage }],
  });
  return TestBed.inject(VoicePrefs);
}

const stored = (storage: MapStorage) => JSON.parse(storage.map.get(VOICE_STORAGE_KEY)!);

describe('parseVoicePrefs (v227)', () => {
  it('falls back to the defaults on nothing, garbage and non-objects', () => {
    for (const raw of [null, '', '{', 'null', '42', '"on"', '[]']) {
      expect(parseVoicePrefs(raw)).toEqual(VOICE_DEFAULTS);
    }
  });

  it('defaults to voice on, no stored kinds, the system voice and rate 1.0', () => {
    expect(VOICE_DEFAULTS).toEqual({ enabled: true, kinds: {}, voice: null, rate: RATE_DEFAULT });
  });

  it('keeps each well-typed field and repairs each bad one on its own', () => {
    const value = parseVoicePrefs(JSON.stringify({
      enabled: 'yes', kinds: { FILLED: false, CANCEL: 'no', NEAR_STOP: true }, voice: 7, rate: 'fast',
    }));
    expect(value).toEqual({ enabled: true, kinds: { FILLED: false, NEAR_STOP: true }, voice: null, rate: RATE_DEFAULT });
    expect(parseVoicePrefs(JSON.stringify({ enabled: false, kinds: [], voice: 'Samantha', rate: 1.2 })))
      .toEqual({ enabled: false, kinds: {}, voice: 'Samantha', rate: 1.2 });
  });

  it('clamps the rate into 0.8..1.4 and rejects a non-finite one', () => {
    expect(parseVoicePrefs(JSON.stringify({ rate: 3 })).rate).toBe(RATE_MAX);
    expect(parseVoicePrefs(JSON.stringify({ rate: 0.1 })).rate).toBe(RATE_MIN);
    expect(parseVoicePrefs('{"rate": 1e999}').rate).toBe(RATE_DEFAULT);
  });
});

describe('familyDefault (v227)', () => {
  it('is off for Watch only; an unknown family is on', () => {
    expect(familyDefault('WATCH')).toBe(false);
    for (const family of ['NEW_SETUP', 'ENTRY', 'MANAGE', 'RESULT', null]) {
      expect(familyDefault(family)).toBe(true);
    }
  });
});

describe('VoicePrefs (v227)', () => {
  afterEach(() => localStorage.removeItem(VOICE_STORAGE_KEY));

  it('reads the stored value once at start', () => {
    const storage = new MapStorage();
    storage.map.set(VOICE_STORAGE_KEY, JSON.stringify({ enabled: false, kinds: { FILLED: false }, voice: null, rate: 1.1 }));
    const prefs = prefsWith(storage);
    expect(prefs.value()).toEqual({ enabled: false, kinds: { FILLED: false }, voice: null, rate: 1.1 });
  });

  it('answers a kind from the map, else from its family default', () => {
    const storage = new MapStorage();
    storage.map.set(VOICE_STORAGE_KEY, JSON.stringify({ kinds: { FILLED: false, NEAR_TP: true } }));
    const prefs = prefsWith(storage);
    expect(prefs.isKindOn('FILLED', 'ENTRY')).toBe(false);
    expect(prefs.isKindOn('NEAR_TP', 'WATCH')).toBe(true);
    expect(prefs.isKindOn('NEAR_STOP', 'WATCH')).toBe(false);
    expect(prefs.isKindOn('BRAND_NEW_KIND', 'RESULT')).toBe(true);
    expect(prefs.isKindOn('UNKNOWN', null)).toBe(true);
  });

  it('persists every setter and keeps the signal in step', () => {
    const storage = new MapStorage();
    const prefs = prefsWith(storage);
    prefs.setEnabled(false);
    prefs.setKind('CANCEL', false);
    prefs.setVoice('Daniel');
    prefs.setRate(1.25);
    const expected = { enabled: false, kinds: { CANCEL: false }, voice: 'Daniel', rate: 1.25 };
    expect(prefs.value()).toEqual(expected);
    expect(stored(storage)).toEqual(expected);
    prefs.setVoice(null);
    expect(stored(storage).voice).toBeNull();
  });

  it('writes a whole family in one save', () => {
    const storage = new MapStorage();
    const prefs = prefsWith(storage);
    prefs.setKinds(['NEAR_STOP', 'NEAR_TP'], true);
    expect(storage.writes).toBe(1);
    expect(stored(storage).kinds).toEqual({ NEAR_STOP: true, NEAR_TP: true });
  });

  it('clamps a rate set out of range', () => {
    const prefs = prefsWith(new MapStorage());
    prefs.setRate(9);
    expect(prefs.value().rate).toBe(RATE_MAX);
    prefs.setRate(Number.NaN);
    expect(prefs.value().rate).toBe(RATE_DEFAULT);
  });

  it('survives a store that throws on read and on write', () => {
    const prefs = prefsWith(refusing);
    expect(prefs.value()).toEqual(VOICE_DEFAULTS);
    prefs.setKind('FILLED', false);
    expect(prefs.isKindOn('FILLED', 'ENTRY')).toBe(false);
  });

  it('uses real localStorage by default, under swingbot.voice.v1', () => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const prefs = TestBed.inject(VoicePrefs);
    prefs.setEnabled(false);
    expect(JSON.parse(localStorage.getItem('swingbot.voice.v1')!).enabled).toBe(false);
  });
});
