# v227 — Voice notifications, Part 2: API client, prefs and speaker (V227-7..V227-8b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v227 — Voice notifications: bomeo-capital.com speaks every simple-channel post](../specs/2026-11-12-v227-voice-notifications-design.md) (§ 3 Speaking it; § 4 storage and defaults; § Testing frontend)

Part 2 of the index's Parts table, split for the 1500-line cap (never
compressed): V227-9..V227-11 continue in
[`2026-11-12-v227-voice-notifications_2b-chip-switch.md`](2026-11-12-v227-voice-notifications_2b-chip-switch.md).
V227-8 passed the 20 KB task cap and is split into V227-8 and V227-8b. Goal, architecture, **Global Constraints**,
**Parallelisation** and the task ledger live in the index:
[`2026-11-12-v227-voice-notifications_0-index.md`](2026-11-12-v227-voice-notifications_0-index.md).
Every task below implicitly carries those constraints. Work happens in the
worktree `.claude/worktrees/2026-11-12-v227-voice-notifications` (all paths
below are relative to it). Frontend runs are narrow:
`node frontend/scripts/ng-test.mjs frontend --include <spec>` (the spec path is
relative to `frontend/`). Never `cd frontend` (the repo hooks forbid it).

Repo rules these tasks lean on (each one bit an earlier plan):

- **Effects flush on `TestBed.tick()`** (Angular 21, zoneless). A root service
  that creates an `effect` outside its constructor passes
  `{ injector: this.injector }` so the effect lives with the root, not with
  the component that called the method.
- **`@keyframes` live only in `src/styles/motion.css`** and **no source queries
  `prefers-reduced-motion`** (`ui/motion-home.spec.ts`): an animated icon uses
  an existing keyframe (`sb-pulse-dim`); the shell's `data-motion` attribute
  already stills it for users who turned motion off.
- **No `@media (pointer: coarse)` block outside `tokens.css`**
  (`ui/hit-area.spec.ts`): 44 px rows come from `min-height: var(--hit-min)`,
  which `tokens.css` already raises to 44 px on touch and below 1024 px.
- **A raw `<button>` outside `ui/` needs a `RAW_BUTTON_ALLOWLIST` entry with a
  comment** (`ui/primitives.spec.ts`); primitives under `ui/` are exempt
  (`ui/testing/call-sites.ts`).
- **jsdom has no `speechSynthesis` or `SpeechSynthesisUtterance`**: the
  `SPEECH` token resolves to `null` there, and every spec that speaks provides
  `FakeSpeech` and `fakeUtterance` (V227-8) through `SPEECH`/`UTTERANCE`.

# Phase 5 — Client, preferences and speech

### Task V227-7: API client methods and `VoicePrefs` (localStorage)

**Model:** sonnet — two thin typed client wrappers and a guarded localStorage service modelled line for line on `density.service.ts`; no cross-package design.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (append the four feed types; joins this task beyond its ledger row, touched by no other task)
- Modify: `frontend/src/app/api/api-client.ts` (import the types; two methods after `refreshMarket`, ~line 180)
- Modify: `frontend/src/app/api/api-client.spec.ts` (one new `describe`)
- Create: `frontend/src/app/voice/voice-prefs.ts`
- Create: `frontend/src/app/voice/voice-prefs.spec.ts`

**Interfaces:**
- Consumes: `GET /api/v1/feed-posts?after=&limit=` → `{"items": [{id, posted_at, kind, family, ticker, headline}], "latest_id"}` and `GET /api/v1/feed-posts/kinds` → `{"families": [{family, label, default_on, kinds: [{kind, label, phrase, sample}]}]}` (V227-6).
- Produces (final; V227-8, V227-9, V227-12, V227-13 consume):
  - `models.ts`: `FeedPost {id: number; posted_at: string; kind: string; family: string | null; ticker: string | null; headline: string}`, `FeedPostsPage {items: FeedPost[]; latest_id: number}`, `FeedKind {kind: string; label: string; phrase: string; sample: string}`, `FeedKindFamily {family: string; label: string; default_on: boolean; kinds: FeedKind[]}`.
  - `ApiClient.feedPosts(after: number | null, limit = 20): Observable<FeedPostsPage>` (sends `after` only when not null, `limit` always); `ApiClient.feedPostKinds(): Observable<FeedKindFamily[]>`.
  - `voice-prefs.ts`: `VOICE_STORAGE_KEY = 'swingbot.voice.v1'`; `interface VoicePrefsValue {enabled: boolean; kinds: Record<string, boolean>; voice: string | null; rate: number}`; `interface VoiceStorage {get(key: string): string | null; set(key: string, value: string): void}`; `VOICE_STORAGE: InjectionToken<VoiceStorage>`; `RATE_MIN = 0.8`, `RATE_MAX = 1.4`, `RATE_STEP = 0.05`, `RATE_DEFAULT = 1.0`; `VOICE_DEFAULTS: VoicePrefsValue`; `familyDefault(family: string | null): boolean`; `parseVoicePrefs(raw: string | null): VoicePrefsValue`; `VoicePrefs` (root) with `value: Signal<VoicePrefsValue>`, `isKindOn(kind, family)`, `setEnabled(on)`, `setKind(kind, on)`, `setKinds(kinds, on)`, `setVoice(name)`, `setRate(rate)`.

`isKindOn` answers the per-kind question only; it never reads `enabled` (the
notifier and the settings block check the master switch themselves).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/app/api/api-client.spec.ts` (the imports at the top of
the file already cover everything used here):

```ts
describe('ApiClient — v227 feed posts', () => {
  let api: ApiClient;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideZonelessChangeDetection(),
        provideHttpClient(withInterceptors([loadingInterceptor, errorInterceptor, authInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    api = TestBed.inject(ApiClient);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('asks for the latest id only when there is no cursor', () => {
    let latest = -1;
    api.feedPosts(null).subscribe((page) => (latest = page.latest_id));
    const req = http.expectOne((r) => r.url === '/api/v1/feed-posts');
    expect(req.request.params.has('after')).toBe(false);
    expect(req.request.params.get('limit')).toBe('20');
    req.flush({ items: [], latest_id: 41 });
    expect(latest).toBe(41);
  });

  it('pages after a cursor with the asked limit, oldest first as served', () => {
    let ids: number[] = [];
    api.feedPosts(41, 50).subscribe((page) => (ids = page.items.map((item) => item.id)));
    const req = http.expectOne((r) => r.url === '/api/v1/feed-posts');
    expect(req.request.params.get('after')).toBe('41');
    expect(req.request.params.get('limit')).toBe('50');
    req.flush({
      items: [
        { id: 42, posted_at: '2026-11-12T14:30:00Z', kind: 'FILLED', family: 'ENTRY', ticker: 'MSFT', headline: 'Order filled, MSFT' },
        { id: 43, posted_at: '2026-11-12T14:31:00Z', kind: 'CANCEL', family: 'MANAGE', ticker: null, headline: 'Order cancelled' },
      ],
      latest_id: 43,
    });
    expect(ids).toEqual([42, 43]);
  });

  it('unwraps the kinds listing into its families', () => {
    let families: string[] = [];
    api.feedPostKinds().subscribe((list) => (families = list.map((f) => f.family)));
    http.expectOne('/api/v1/feed-posts/kinds').flush({
      families: [
        { family: 'NEW_SETUP', label: 'New setup', default_on: true, kinds: [] },
        { family: 'WATCH', label: 'Watch', default_on: false, kinds: [] },
      ],
    });
    expect(families).toEqual(['NEW_SETUP', 'WATCH']);
  });
});
```

Create `frontend/src/app/voice/voice-prefs.spec.ts`:

```ts
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/api/api-client.spec.ts --include src/app/voice/voice-prefs.spec.ts
```

Expected: FAIL — `api.feedPosts is not a function` and `Cannot find module './voice-prefs'`.

- [ ] **Step 3: Write the implementation**

Append to `frontend/src/app/api/models.ts`:

```ts
/* -- v227: simple-channel posts the admin speaks ------------------------- */

/** One recorded simple-channel post. `family` is null for a kind this
 *  server's registry no longer knows. */
export interface FeedPost {
  id: number;
  posted_at: string;
  kind: string;
  family: string | null;
  ticker: string | null;
  headline: string;
}

/** A page after a cursor, oldest first; `latest_id` is read before the page. */
export interface FeedPostsPage {
  items: FeedPost[];
  latest_id: number;
}

/** A toggleable kind: Discord label, the spoken phrase and a sample headline. */
export interface FeedKind {
  kind: string;
  label: string;
  phrase: string;
  sample: string;
}

/** One family of kinds, in the server's order. */
export interface FeedKindFamily {
  family: string;
  label: string;
  default_on: boolean;
  kinds: FeedKind[];
}
```

`frontend/src/app/api/api-client.ts`: add `FeedKindFamily` and `FeedPostsPage`
to the `from './models'` import list (after `ExpectancyAttribution`), then add
after `refreshMarket` (~line 180):

```ts
  /* -- v227: voice notifications ------------------------------------------ */

  /** Simple-channel posts after `after`, oldest first. `null` asks only for
   *  `latest_id` (the server returns no items), which is how a fresh page
   *  starts without speaking a backlog. */
  feedPosts(after: number | null, limit = 20): Observable<FeedPostsPage> {
    let params = new HttpParams().set('limit', String(limit));
    if (after !== null) params = params.set('after', String(after));
    return this.http.get<FeedPostsPage>(`${this.base}/feed-posts`, { params });
  }

  /** The kinds Settings may silence, grouped by family. */
  feedPostKinds(): Observable<FeedKindFamily[]> {
    return this.http
      .get<{ families: FeedKindFamily[] }>(`${this.base}/feed-posts/kinds`)
      .pipe(map((body) => body.families));
  }
```

Create `frontend/src/app/voice/voice-prefs.ts`:

```ts
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/api/api-client.spec.ts --include src/app/voice/voice-prefs.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/api/api-client.ts frontend/src/app/api/api-client.spec.ts
git commit -m "feat(ui): v227 ApiClient.feedPosts and feedPostKinds (V227-7)"
git add frontend/src/app/voice/voice-prefs.ts frontend/src/app/voice/voice-prefs.spec.ts
git commit -m "feat(ui): v227 VoicePrefs, per-browser voice settings in localStorage (V227-7)"
```

### Task V227-8: `VoiceSpeaker`: the chip state machine and the unlock

**Model:** sonnet — one root service and a test double around the browser's `speechSynthesis`; the state rules are fixed below and every transition has a test.

**Files:**
- Create: `frontend/src/app/voice/voice-speaker.ts`
- Create: `frontend/src/app/voice/fake-speech.ts` (test helper; imported only by specs)
- Create: `frontend/src/app/voice/voice-speaker.spec.ts`

**Interfaces:**
- Consumes: `VoicePrefs.value()` (`enabled`, `voice`, `rate`), `VOICE_STORAGE`, `VOICE_STORAGE_KEY` (V227-7).
- Produces (final; V227-9, V227-10, V227-12, V227-13 consume):
  - `interface SpeechPort {speak(u: SpeechSynthesisUtterance): void; cancel(): void; getVoices(): SpeechSynthesisVoice[]; readonly speaking: boolean; onvoiceschanged: (() => void) | null}`
  - `SPEECH: InjectionToken<SpeechPort | null>` (factory: `globalThis.speechSynthesis ?? null`; `null` under jsdom)
  - `UTTERANCE: InjectionToken<(text: string) => SpeechSynthesisUtterance>`
  - `type VoiceState = 'off' | 'locked' | 'live' | 'muted' | 'blocked' | 'unavailable'`
  - `BLOCK_TIMEOUT_MS = 2000`; `UNLOCK_PHRASE = 'Voice notifications on'`
  - `VoiceSpeaker` (root): `state: Signal<VoiceState>`, `busy: Signal<boolean>`, `voices: Signal<string[] | null>` (null = still loading), `unlock()`, `mute()`, `rearm()` (`say(lines: string[])` and `preview(text: string)` are added by V227-8b, split from this task at the 20 KB cap)
  - `fake-speech.ts`: `class FakeSpeech implements SpeechPort` with `spoken: SpeechSynthesisUtterance[]`, `texts(): string[]`, `cancelled: number`, `speaking: boolean`, `start()`, `finish()`, `fail(error = 'not-allowed')`, `setVoices(names: string[])`; `fakeUtterance(text: string): SpeechSynthesisUtterance`

State rules (spec §3 chip states; index notes V227-8):

| From | Event | To |
|---|---|---|
| any | no `speechSynthesis` | `unavailable` (always) |
| any | prefs `enabled` false | `off` (cancel, clear queue; the hidden phase resets to `locked`) |
| `locked` / `blocked` | `unlock()` speaks `UNLOCK_PHRASE`; `onstart` or `onend`, or `speaking` true at 2 s | `live` |
| `locked` / `blocked` | `onerror`, or not speaking at 2 s | `blocked` |
| `live` | `mute()` | `muted` (cancel, clear queue) |
| `muted` | `rearm()` | `live` |

This task builds the service with its queue machinery (`pump`, `speakOne`,
`silence`, the generation counter) and every state transition; V227-8b adds the
two public methods that feed the queue. Every callback carries the generation
it was spoken in, so the `onerror` a browser fires for a cancelled utterance
never releases the next line after a mute.

- [ ] **Step 1: Write the test helper and the failing tests**

Create `frontend/src/app/voice/fake-speech.ts`:

```ts
import { SpeechPort } from './voice-speaker';

/** A stand-in for the browser's `speechSynthesis` (jsdom has none). The
 *  test drives the current utterance's events by hand. Imported by specs only. */
export class FakeSpeech implements SpeechPort {
  readonly spoken: SpeechSynthesisUtterance[] = [];
  cancelled = 0;
  speaking = false;
  onvoiceschanged: (() => void) | null = null;
  private voiceList: SpeechSynthesisVoice[] = [];
  private current: SpeechSynthesisUtterance | null = null;

  speak(utterance: SpeechSynthesisUtterance): void {
    this.spoken.push(utterance);
    this.current = utterance;
  }

  /** Like Chrome: a cancelled utterance reports an "interrupted" error. */
  cancel(): void {
    this.cancelled += 1;
    this.fail('interrupted');
  }

  getVoices(): SpeechSynthesisVoice[] {
    return this.voiceList;
  }

  texts(): string[] {
    return this.spoken.map((utterance) => utterance.text);
  }

  start(): void {
    this.speaking = true;
    this.current?.onstart?.call(this.current, {} as SpeechSynthesisEvent);
  }

  finish(): void {
    const utterance = this.release();
    utterance?.onend?.call(utterance, {} as SpeechSynthesisEvent);
  }

  fail(error = 'not-allowed'): void {
    const utterance = this.release();
    utterance?.onerror?.call(utterance, { error } as unknown as SpeechSynthesisErrorEvent);
  }

  setVoices(names: string[]): void {
    this.voiceList = names.map((name) => ({ name }) as unknown as SpeechSynthesisVoice);
    this.onvoiceschanged?.();
  }

  private release(): SpeechSynthesisUtterance | null {
    const utterance = this.current;
    this.current = null;
    this.speaking = false;
    return utterance;
  }
}

/** A plain-object utterance: jsdom has no SpeechSynthesisUtterance. */
export function fakeUtterance(text: string): SpeechSynthesisUtterance {
  return { text, rate: 1, voice: null, onstart: null, onend: null, onerror: null } as unknown as SpeechSynthesisUtterance;
}
```

Create `frontend/src/app/voice/voice-speaker.spec.ts`:

```ts
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FakeSpeech, fakeUtterance } from './fake-speech';
import { VOICE_STORAGE, VOICE_STORAGE_KEY, VoicePrefs, VoicePrefsValue } from './voice-prefs';
import { BLOCK_TIMEOUT_MS, SPEECH, UNLOCK_PHRASE, UTTERANCE, VoiceSpeaker } from './voice-speaker';

function setup(speech: FakeSpeech | null, stored: Partial<VoicePrefsValue> = {}) {
  const map = new Map([[VOICE_STORAGE_KEY, JSON.stringify(stored)]]);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      { provide: SPEECH, useValue: speech },
      { provide: UTTERANCE, useValue: fakeUtterance },
      { provide: VOICE_STORAGE, useValue: { get: (k: string) => map.get(k) ?? null, set: (k: string, v: string) => map.set(k, v) } },
    ],
  });
  const speaker = TestBed.inject(VoiceSpeaker);
  TestBed.tick();
  return { speaker, prefs: TestBed.inject(VoicePrefs) };
}

/** Unlocked and the unlock phrase finished: an idle, live speaker. */
function live(speech: FakeSpeech, stored: Partial<VoicePrefsValue> = {}) {
  const ctx = setup(speech, stored);
  ctx.speaker.unlock();
  speech.start();
  speech.finish();
  return ctx;
}

describe('VoiceSpeaker (v227)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('is unavailable without speechSynthesis and then does nothing at all', () => {
    const { speaker } = setup(null);
    expect(speaker.state()).toBe('unavailable');
    speaker.unlock();
    speaker.mute();
    expect(speaker.state()).toBe('unavailable');
    expect(speaker.busy()).toBe(false);
    expect(speaker.voices()).toBeNull();
  });

  it('is off while the master switch is off, and unlock does not speak', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech, { enabled: false });
    expect(speaker.state()).toBe('off');
    speaker.unlock();
    expect(speech.texts()).toEqual([]);
  });

  it('starts locked; the unlock tap speaks the phrase and goes live on start', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    expect(speaker.state()).toBe('locked');
    speaker.unlock();
    expect(speech.texts()).toEqual([UNLOCK_PHRASE]);
    expect(speaker.state()).toBe('locked');
    speech.start();
    expect(speaker.state()).toBe('live');
  });

  it('goes live on end when a browser never reports the start', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    speaker.unlock();
    speech.finish();
    expect(speaker.state()).toBe('live');
  });

  it('is blocked when the unlock phrase errors, and a second tap retries', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    speaker.unlock();
    speech.fail('not-allowed');
    expect(speaker.state()).toBe('blocked');
    speaker.unlock();
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, UNLOCK_PHRASE]);
    speech.start();
    expect(speaker.state()).toBe('live');
  });

  it('is blocked when nothing is speaking after 2 s, live when something is', () => {
    const silent = new FakeSpeech();
    const first = setup(silent);
    first.speaker.unlock();
    vi.advanceTimersByTime(BLOCK_TIMEOUT_MS - 1);
    expect(first.speaker.state()).toBe('locked');
    vi.advanceTimersByTime(1);
    expect(first.speaker.state()).toBe('blocked');

    TestBed.resetTestingModule();
    const quiet = new FakeSpeech();
    const second = setup(quiet);
    second.speaker.unlock();
    quiet.speaking = true;
    vi.advanceTimersByTime(BLOCK_TIMEOUT_MS);
    expect(second.speaker.state()).toBe('live');
  });

  it('is busy while the unlock phrase speaks', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    expect(speaker.busy()).toBe(false);
    speaker.unlock();
    expect(speaker.busy()).toBe(true);
    speech.start();
    speech.finish();
    expect(speaker.busy()).toBe(false);
  });

  it('mutes only from live, cancelling speech, and rearm goes live again', () => {
    const speech = new FakeSpeech();
    const locked = setup(speech);
    locked.speaker.mute();
    expect(locked.speaker.state()).toBe('locked');
    locked.speaker.rearm();
    expect(locked.speaker.state()).toBe('locked');

    TestBed.resetTestingModule();
    const other = new FakeSpeech();
    const { speaker } = live(other);
    const before = other.cancelled;
    speaker.mute();
    expect(other.cancelled).toBeGreaterThan(before);
    expect(speaker.state()).toBe('muted');
    speaker.unlock();
    expect(speaker.state()).toBe('muted');
    speaker.rearm();
    expect(speaker.state()).toBe('live');
  });

  it('turning voice off cancels; turning it back on asks for a tap again', () => {
    const speech = new FakeSpeech();
    const { speaker, prefs } = live(speech);
    const before = speech.cancelled;
    prefs.setEnabled(false);
    TestBed.tick();
    expect(speaker.state()).toBe('off');
    expect(speech.cancelled).toBeGreaterThan(before);
    expect(speaker.busy()).toBe(false);
    prefs.setEnabled(true);
    TestBed.tick();
    expect(speaker.state()).toBe('locked');
  });

  it('speaks with the stored rate and voice, and the system voice when the stored one is missing', () => {
    const speech = new FakeSpeech();
    speech.setVoices(['Alex', 'Daniel']);
    const { speaker } = setup(speech, { voice: 'Daniel', rate: 1.2 });
    speaker.unlock();
    expect(speech.spoken[0].rate).toBe(1.2);
    expect(speech.spoken[0].voice?.name).toBe('Daniel');

    TestBed.resetTestingModule();
    const other = new FakeSpeech();
    other.setVoices(['Alex']);
    const second = setup(other, { voice: 'Gone' });
    second.speaker.unlock();
    expect(other.spoken[0].voice).toBeNull();
  });

  it('keeps voices null until a non-empty list arrives', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    expect(speaker.voices()).toBeNull();
    speech.setVoices([]);
    expect(speaker.voices()).toBeNull();
    speech.setVoices(['Alex', 'Daniel']);
    expect(speaker.voices()).toEqual(['Alex', 'Daniel']);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-speaker.spec.ts
```

Expected: FAIL — `Cannot find module './voice-speaker'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/voice/voice-speaker.ts`:

```ts
import { Injectable, InjectionToken, Signal, computed, effect, inject, signal, untracked } from '@angular/core';

import { VoicePrefs } from './voice-prefs';

/**
 * The only code that touches the browser's `speechSynthesis` (spec v227 §3).
 *
 * It owns two things: the queue (one utterance in flight, never overlapping)
 * and the state the top-bar chip shows. Browsers refuse speech until the page
 * has had a user gesture, on every load, so voice starts `locked` and the
 * chip's tap calls `unlock()`. A browser that still refuses -- an error, or
 * nothing speaking 2 s later -- is `blocked`.
 *
 * Every utterance remembers the generation it was spoken in. Mute, voice off
 * and a preview bump it, so the error event a browser fires for a cancelled
 * utterance can never release the next line after a mute.
 */
export interface SpeechPort {
  speak(utterance: SpeechSynthesisUtterance): void;
  cancel(): void;
  getVoices(): SpeechSynthesisVoice[];
  readonly speaking: boolean;
  onvoiceschanged: (() => void) | null;
}

/** The browser's speech engine, or null where there is none (jsdom, old browsers). */
export const SPEECH = new InjectionToken<SpeechPort | null>('SPEECH', {
  providedIn: 'root',
  factory: () =>
    ((globalThis as unknown as { speechSynthesis?: unknown }).speechSynthesis as SpeechPort | undefined) ?? null,
});

/** Builds an utterance; specs provide `fakeUtterance`. */
export const UTTERANCE = new InjectionToken<(text: string) => SpeechSynthesisUtterance>('UTTERANCE', {
  providedIn: 'root',
  factory: () => (text: string) => new SpeechSynthesisUtterance(text),
});

export type VoiceState = 'off' | 'locked' | 'live' | 'muted' | 'blocked' | 'unavailable';

/** The four states a speaking-capable, switched-on browser moves between. */
type Phase = 'locked' | 'live' | 'muted' | 'blocked';

export const BLOCK_TIMEOUT_MS = 2000;
export const UNLOCK_PHRASE = 'Voice notifications on';

@Injectable({ providedIn: 'root' })
export class VoiceSpeaker {
  private readonly speech = inject(SPEECH);
  private readonly utter = inject(UTTERANCE);
  private readonly prefs = inject(VoicePrefs);

  private readonly phase = signal<Phase>('locked');
  private readonly inFlight = signal(false);
  private readonly queue = signal<string[]>([]);
  private readonly voiceNames = signal<string[] | null>(null);
  private generation = 0;
  private watchdog: ReturnType<typeof setTimeout> | null = null;

  readonly state: Signal<VoiceState> = computed(() => {
    if (!this.speech) return 'unavailable';
    if (!this.prefs.value().enabled) return 'off';
    return this.phase();
  });
  readonly busy: Signal<boolean> = computed(() => this.inFlight() || this.queue().length > 0);
  readonly voices: Signal<string[] | null> = this.voiceNames.asReadonly();

  constructor() {
    if (!this.speech) return;
    this.loadVoices();
    this.speech.onvoiceschanged = () => this.loadVoices();
    // Voice switched off in Settings: stop now, and ask for a tap when it comes back.
    effect(() => {
      const enabled = this.prefs.value().enabled;
      untracked(() => {
        if (!enabled) this.silence('locked');
      });
    });
  }

  /** The chip's tap from `locked` or `blocked`: speak the unlock phrase. */
  unlock(): void {
    const state = this.state();
    if (state !== 'locked' && state !== 'blocked') return;
    this.silence(this.phase());
    const generation = this.generation;
    this.watchdog = setTimeout(() => {
      if (generation === this.generation) this.settleUnlock(this.speech!.speaking);
    }, BLOCK_TIMEOUT_MS);
    this.speakOne(UNLOCK_PHRASE, () => this.settleUnlock(true), () => this.settleUnlock(false));
  }

  /** The chip's tap while live: stop, clear and stay quiet this session. */
  mute(): void {
    if (this.state() === 'live') this.silence('muted');
  }

  /** The chip's tap while muted. */
  rearm(): void {
    if (this.state() === 'muted') this.phase.set('live');
  }

  private settleUnlock(ok: boolean): void {
    this.clearWatchdog();
    if (this.phase() === 'live') return;
    this.phase.set(ok ? 'live' : 'blocked');
  }

  private pump(): void {
    if (this.inFlight() || this.state() !== 'live') return;
    const [next, ...rest] = this.queue();
    if (next === undefined) return;
    this.queue.set(rest);
    this.speakOne(next);
  }

  private speakOne(text: string, onStart?: () => void, onFail?: () => void): void {
    const generation = this.generation;
    const current = () => generation === this.generation;
    const release = () => {
      if (!current()) return;
      this.inFlight.set(false);
      this.pump();
    };
    const utterance = this.prepare(text);
    utterance.onstart = () => {
      if (current()) onStart?.();
    };
    utterance.onend = () => {
      if (current()) onStart?.();
      release();
    };
    utterance.onerror = () => {
      if (current()) onFail?.();
      release();
    };
    this.inFlight.set(true);
    this.speech!.speak(utterance);
  }

  private prepare(text: string): SpeechSynthesisUtterance {
    const { rate, voice } = this.prefs.value();
    const utterance = this.utter(text);
    utterance.rate = rate;
    const match = voice ? this.speech!.getVoices().find((candidate) => candidate.name === voice) : undefined;
    if (match) utterance.voice = match;
    return utterance;
  }

  /** Stop whatever is speaking, drop the queue, and land in `next`. */
  private silence(next: Phase): void {
    this.generation += 1;
    this.clearWatchdog();
    this.speech?.cancel();
    this.inFlight.set(false);
    this.queue.set([]);
    this.phase.set(next);
  }

  private clearWatchdog(): void {
    if (this.watchdog !== null) clearTimeout(this.watchdog);
    this.watchdog = null;
  }

  private loadVoices(): void {
    const names = this.speech!.getVoices().map((voice) => voice.name);
    if (names.length > 0) this.voiceNames.set(names);
  }
}
```

`say` and `preview` arrive in V227-8b; until then the queue stays empty and
`pump()` is the hook they use. `unlock()` calls `silence(this.phase())` first: it bumps the generation (so the
previous attempt's watchdog and callbacks go stale) and calls `cancel()` without
changing the phase. `speak()` runs synchronously inside the chip's click
handler, which is what browsers accept as the user gesture.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-speaker.spec.ts --include src/app/voice/voice-prefs.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/voice/voice-speaker.ts frontend/src/app/voice/fake-speech.ts frontend/src/app/voice/voice-speaker.spec.ts
git commit -m "feat(ui): v227 VoiceSpeaker state machine, unlock and voices (V227-8)"
```

### Task V227-8b: `VoiceSpeaker`: `say` and `preview` feed the queue

**Model:** sonnet — two public methods on the V227-8 service, whose queue machinery already exists; the ordering and cut-off rules are fixed below and tested.

**Files:**
- Modify: `frontend/src/app/voice/voice-speaker.ts` (two methods, between `unlock()` and `mute()`)
- Modify: `frontend/src/app/voice/voice-speaker.spec.ts` (nine tests inside the existing `describe`)

**Interfaces:**
- Consumes (V227-8, same files): `state()`, `inFlight`, `queue`, `generation`, `pump()`, `speakOne(text, onStart?, onFail?)`, `clearWatchdog()`, `silence(next)`; `FakeSpeech`, `fakeUtterance`, `UNLOCK_PHRASE`, the spec's `setup()` and `live()` helpers.
- Produces (final; V227-9 consumes `say`, V227-12 and V227-13 consume `preview`): `VoiceSpeaker.say(lines: string[]): void`, `VoiceSpeaker.preview(text: string): void`.

Rules (spec §3; index notes V227-8): one utterance is in flight at a time;
`say` queues only while `live` and drops blank lines; each `onend`/`onerror`
releases the slot and speaks the next; the line a mute cancels never releases
the next (the generation guard from V227-8). `preview` is a Settings tap: it
speaks in any state except `off` and `unavailable`, never changes the state,
cuts off whatever is speaking, and leaves the queue to carry on afterwards.

- [ ] **Step 1: Write the failing tests**

Add inside `describe('VoiceSpeaker (v227)', …)` in
`frontend/src/app/voice/voice-speaker.spec.ts`, after the last test:

```ts
  it('says and previews nothing without speechSynthesis or with voice off', () => {
    const none = setup(null).speaker;
    none.say(['Order filled, MSFT']);
    none.preview('New long alert, AAPL');
    expect(none.busy()).toBe(false);

    TestBed.resetTestingModule();
    const speech = new FakeSpeech();
    const off = setup(speech, { enabled: false }).speaker;
    off.say(['Order filled, MSFT']);
    off.preview('New long alert, AAPL');
    expect(speech.texts()).toEqual([]);
  });

  it('ignores say() until live', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    speaker.say(['Order filled, MSFT']);
    expect(speaker.busy()).toBe(false);
    speaker.unlock();
    speech.start();
    speech.finish();
    expect(speech.texts()).toEqual([UNLOCK_PHRASE]);
  });

  it('speaks one line at a time, in order, and only after the unlock phrase ends', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    speaker.unlock();
    speech.start();
    speaker.say(['A', 'B']);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE]);
    expect(speaker.busy()).toBe(true);
    speech.finish();
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A']);
    speaker.say(['C']);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A']);
    speech.finish();
    speech.finish();
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A', 'B', 'C']);
    expect(speaker.busy()).toBe(true);
    speech.finish();
    expect(speaker.busy()).toBe(false);
  });

  it('drops blank lines', () => {
    const speech = new FakeSpeech();
    const { speaker } = live(speech);
    speaker.say(['', '   ']);
    expect(speaker.busy()).toBe(false);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE]);
  });

  it('moves on to the next line when one errors, and stays live', () => {
    const speech = new FakeSpeech();
    const { speaker } = live(speech);
    speaker.say(['A', 'B']);
    speech.fail('synthesis-failed');
    expect(speech.texts().slice(-1)).toEqual(['B']);
    expect(speaker.state()).toBe('live');
  });

  it('mute cancels, clears the queue and ignores the cancelled line; rearm goes live again', () => {
    const speech = new FakeSpeech();
    const { speaker } = live(speech);
    speaker.say(['A', 'B', 'C']);
    speaker.mute();
    expect(speech.cancelled).toBeGreaterThan(0);
    expect(speaker.state()).toBe('muted');
    expect(speaker.busy()).toBe(false);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A']);
    speaker.say(['D']);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A']);
    speaker.rearm();
    expect(speaker.state()).toBe('live');
    speaker.say(['E']);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A', 'E']);
  });

  it('turning voice off drops the queue', () => {
    const speech = new FakeSpeech();
    const { speaker, prefs } = live(speech);
    speaker.say(['A', 'B']);
    expect(speaker.busy()).toBe(true);
    prefs.setEnabled(false);
    TestBed.tick();
    expect(speaker.busy()).toBe(false);
    expect(speech.texts()).toEqual([UNLOCK_PHRASE, 'A']);
  });

  it('speaks each headline with the current rate', () => {
    const speech = new FakeSpeech();
    const { speaker, prefs } = live(speech);
    prefs.setRate(1.3);
    speaker.say(['A']);
    expect(speech.spoken.at(-1)!.rate).toBe(1.3);
  });

  it('previews while locked without unlocking, and cuts off what is speaking', () => {
    const speech = new FakeSpeech();
    const { speaker } = setup(speech);
    speaker.preview('Order filled, AAPL');
    expect(speech.texts()).toEqual(['Order filled, AAPL']);
    expect(speaker.state()).toBe('locked');

    TestBed.resetTestingModule();
    const busy = new FakeSpeech();
    const ctx = live(busy);
    ctx.speaker.say(['A', 'B']);
    ctx.speaker.preview('Stopped out, AAPL');
    expect(busy.texts()).toEqual([UNLOCK_PHRASE, 'A', 'Stopped out, AAPL']);
    busy.finish();
    expect(busy.texts().at(-1)).toBe('B');
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-speaker.spec.ts
```

Expected: FAIL — `speaker.say is not a function` / `speaker.preview is not a function` (a TypeScript error on the same names is the same failure).

- [ ] **Step 3: Write the implementation**

In `frontend/src/app/voice/voice-speaker.ts`, add between `unlock()` and `mute()`:

```ts
  /** Queue headlines; ignored unless live. */
  say(lines: string[]): void {
    if (this.state() !== 'live') return;
    const clean = lines.filter((line) => line.trim() !== '');
    if (clean.length === 0) return;
    this.queue.update((queued) => [...queued, ...clean]);
    this.pump();
  }

  /** A Settings preview: a user's tap, so it speaks now in any switched-on state. */
  preview(text: string): void {
    const state = this.state();
    if (state === 'off' || state === 'unavailable') return;
    if (this.inFlight()) {
      this.generation += 1;
      this.clearWatchdog();
      this.speech!.cancel();
      this.inFlight.set(false);
    }
    this.speakOne(text);
  }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-speaker.spec.ts --include src/app/voice/voice-prefs.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/voice/voice-speaker.ts frontend/src/app/voice/voice-speaker.spec.ts
git commit -m "feat(ui): v227 VoiceSpeaker say and preview, one line at a time (V227-8b)"
```

