import { Injectable, InjectionToken, Signal, inject, signal } from '@angular/core';

/**
 * Voice notification preferences (spec v227 §4): the master switch, one flag
 * per kind, the chosen voice and the speaking rate.
 *
 * Per BROWSER, so localStorage under one versioned key, never the server and
 * never `.env`: a phone on the desk and a laptop in a meeting want different
 * answers. Modelled on `ui/density.service.ts`: every storage call is guarded
 * (private mode, a blocked origin or a full quota never breaks the app; the
 * choice then lasts for the session) and anything unreadable falls back to the
 * defaults field by field.
 *
 * A kind missing from `kinds` takes its family default, so a kind added on the
 * server later starts on (or off, for Watch) without a migration here.
 */
export const VOICE_STORAGE_KEY = 'swingbot.voice.v1';

export const RATE_MIN = 0.8;
export const RATE_MAX = 1.4;
export const RATE_STEP = 0.05;
export const RATE_DEFAULT = 1.0;

export interface VoicePrefsValue {
  enabled: boolean;
  kinds: Record<string, boolean>;
  voice: string | null;
  rate: number;
}

export const VOICE_DEFAULTS: VoicePrefsValue = { enabled: true, kinds: {}, voice: null, rate: RATE_DEFAULT };

/** The two calls the service needs from a key-value store. */
export interface VoiceStorage {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

function localStorageVoice(): VoiceStorage {
  return {
    get(key: string): string | null {
      try {
        return globalThis.localStorage?.getItem(key) ?? null;
      } catch {
        return null;
      }
    },
    set(key: string, value: string): void {
      try {
        globalThis.localStorage?.setItem(key, value);
      } catch {
        /* Private mode or a full quota: the choice lasts this session. */
      }
    },
  };
}

/** The store `VoicePrefs` reads and writes; specs override it. */
export const VOICE_STORAGE = new InjectionToken<VoiceStorage>('VOICE_STORAGE', {
  providedIn: 'root',
  factory: localStorageVoice,
});

/** Watch (near stop / near target) is the noisiest family: off by default. */
export function familyDefault(family: string | null): boolean {
  return family !== 'WATCH';
}

function clampRate(rate: unknown): number {
  if (typeof rate !== 'number' || !Number.isFinite(rate)) return RATE_DEFAULT;
  return Math.min(RATE_MAX, Math.max(RATE_MIN, rate));
}

function onlyBooleans(kinds: unknown): Record<string, boolean> {
  if (!kinds || typeof kinds !== 'object' || Array.isArray(kinds)) return {};
  return Object.fromEntries(Object.entries(kinds).filter(([, on]) => typeof on === 'boolean'));
}

/** A stored string to a value, each field repaired on its own. */
export function parseVoicePrefs(raw: string | null): VoicePrefsValue {
  let data: unknown;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    return { ...VOICE_DEFAULTS };
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return { ...VOICE_DEFAULTS };
  const record = data as Record<string, unknown>;
  return {
    enabled: typeof record['enabled'] === 'boolean' ? record['enabled'] : true,
    kinds: onlyBooleans(record['kinds']),
    voice: typeof record['voice'] === 'string' ? record['voice'] : null,
    rate: clampRate(record['rate']),
  };
}

function readPrefs(storage: VoiceStorage): VoicePrefsValue {
  try {
    return parseVoicePrefs(storage.get(VOICE_STORAGE_KEY));
  } catch {
    return { ...VOICE_DEFAULTS };
  }
}

@Injectable({ providedIn: 'root' })
export class VoicePrefs {
  private readonly storage = inject(VOICE_STORAGE);
  private readonly current = signal<VoicePrefsValue>(readPrefs(this.storage));

  readonly value: Signal<VoicePrefsValue> = this.current.asReadonly();

  /** The kind's stored flag, else its family default. Ignores `enabled`. */
  isKindOn(kind: string, family: string | null): boolean {
    const stored = this.current().kinds[kind];
    return typeof stored === 'boolean' ? stored : familyDefault(family);
  }

  setEnabled(on: boolean): void {
    this.save({ ...this.current(), enabled: on });
  }

  setKind(kind: string, on: boolean): void {
    this.setKinds([kind], on);
  }

  /** Every listed kind in one save (the family switch). */
  setKinds(kinds: string[], on: boolean): void {
    const next = { ...this.current().kinds };
    for (const kind of kinds) next[kind] = on;
    this.save({ ...this.current(), kinds: next });
  }

  setVoice(name: string | null): void {
    this.save({ ...this.current(), voice: name || null });
  }

  setRate(rate: number): void {
    this.save({ ...this.current(), rate: clampRate(rate) });
  }

  private save(value: VoicePrefsValue): void {
    this.current.set(value);
    try {
      this.storage.set(VOICE_STORAGE_KEY, JSON.stringify(value));
    } catch {
      /* A custom store may throw; the signal already holds the choice. */
    }
  }
}
