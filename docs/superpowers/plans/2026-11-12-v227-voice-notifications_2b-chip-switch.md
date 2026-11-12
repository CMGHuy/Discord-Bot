# v227 — Voice notifications, Part 2b: notifier, top-bar voice chip and the switch primitive (V227-9..V227-11)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor, bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Spec:** [v227 — Voice notifications: bomeo-capital.com speaks every simple-channel post](../specs/2026-11-12-v227-voice-notifications-design.md) (§ 3 `VoiceNotifier` and voice chip states; § 4 switch semantics, three widths; § Testing frontend)

Part 2 of the index's Parts table, continued: V227-7..V227-8b are in
[`2026-11-12-v227-voice-notifications_2-voice-services.md`](2026-11-12-v227-voice-notifications_2-voice-services.md)
(split for the 1500-line cap, never compressed); its header lists the repo
rules these tasks lean on (effects and `TestBed.tick()`, the one keyframe home,
`--hit-min` instead of a coarse-pointer block, the raw-button allowlist, no
`speechSynthesis` under jsdom). Goal, architecture, **Global Constraints**,
**Parallelisation** and the task ledger live in the index:
[`2026-11-12-v227-voice-notifications_0-index.md`](2026-11-12-v227-voice-notifications_0-index.md).
Work happens in the worktree `.claude/worktrees/2026-11-12-v227-voice-notifications`
(all paths below are relative to it). Frontend runs are narrow:
`node frontend/scripts/ng-test.mjs frontend --include <spec>`.

# Phase 6 — Notifier, top bar and the switch primitive

### Task V227-9: `VoiceNotifier`: `feed` event → fetch → filter → speak

**Model:** sonnet — one root service wiring an existing SSE counter to two client calls; the paging, cap and single-fetch rules are fixed below and each has a test.

**Files:**
- Create: `frontend/src/app/voice/voice-notifier.ts`
- Create: `frontend/src/app/voice/voice-notifier.spec.ts`

**Interfaces:**
- Consumes: `EventStream.changes('feed'): Signal<number>` (`'feed'` in `EventName`, V227-1); `ApiClient.feedPosts(after: number | null, limit?: number): Observable<FeedPostsPage>`, `FeedPost` (V227-7); `VoicePrefs.value().enabled`, `VoicePrefs.isKindOn(kind, family)` (V227-7); `VoiceSpeaker.say(lines)` (V227-8b); `SPEECH`, `FakeSpeech` (V227-8).
- Produces (final; V227-10 consumes `start()`): `RECONNECT_CAP = 5`; `FEED_PAGE_LIMIT = 50`; `moreLine(n: number): string` (`and ${n} more`); `VoiceNotifier` (root) with `start(): void` (idempotent) and `lastId: Signal<number | null>`.

Rules (spec §3 `VoiceNotifier`; index notes V227-9):

1. **No backlog.** `start()` asks `feedPosts(null)` (no items, just `latest_id`)
   and takes `latest_id` as the cursor. Nothing from before the page load is spoken.
2. **One fetch at a time.** A `feed` bump during a fetch sets `pending`; the
   fetch re-runs once when the current one ends. The initial latest-id read
   counts as a fetch, so a bump during it is not lost.
3. **Paging.** Each fetch asks `feedPosts(cursor, FEED_PAGE_LIMIT)` and keeps
   asking after the last id while a page comes back full, concatenating. The
   new cursor is the last item id, or `latest_id` when the last page is empty.
   Nothing is spoken until the last page is in.
4. **A failed fetch leaves the cursor unchanged**, so the next bump retries the
   same range; nothing from a half-read range was spoken, so nothing repeats.
5. **Filter, then cap.** With the master switch off nothing is spoken (the
   cursor still advances, so switching on later replays nothing). Otherwise the
   kept headlines are those whose kind `isKindOn`; the newest `RECONNECT_CAP` of
   them are spoken in id order, followed by `moreLine(skipped)` when any were
   dropped by the cap.
6. **A resync** bumps `feed` like every other name, which just runs a fetch
   from the cursor: nothing new, nothing spoken.
7. **No `speechSynthesis`** (`SPEECH` null): `start()` makes no request and
   creates no effect; the notifier never calls the API and never calls `say`.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/voice/voice-notifier.spec.ts`:

```ts
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Signal, WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { EventStream } from '../api/event-stream';
import { FeedPost } from '../api/models';
import { FakeSpeech } from './fake-speech';
import { FEED_PAGE_LIMIT, RECONNECT_CAP, VoiceNotifier, moreLine } from './voice-notifier';
import { VOICE_STORAGE, VOICE_STORAGE_KEY, VoicePrefsValue } from './voice-prefs';
import { SPEECH, VoiceSpeaker } from './voice-speaker';

/** A counter per event name, bumped by name, like `EventStream.changes()`. */
class FakeEvents {
  private readonly counters = new Map<string, WritableSignal<number>>();
  changes(name: string): Signal<number> {
    return this.counter(name).asReadonly();
  }
  emit(name: string): void {
    this.counter(name).update((n) => n + 1);
  }
  private counter(name: string): WritableSignal<number> {
    if (!this.counters.has(name)) this.counters.set(name, signal(0));
    return this.counters.get(name)!;
  }
}

const URL = '/api/v1/feed-posts';

const post = (id: number, kind = 'FILLED', family: string | null = 'ENTRY'): FeedPost => ({
  id, posted_at: '2026-11-12T14:30:00Z', kind, family, ticker: `T${id}`, headline: `${kind} ${id}`,
});

const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => post(from + i));

function setup(opts: { speech?: FakeSpeech | null; stored?: Partial<VoicePrefsValue> } = {}) {
  const events = new FakeEvents();
  const say = vi.fn();
  const map = new Map([[VOICE_STORAGE_KEY, JSON.stringify(opts.stored ?? {})]]);
  TestBed.configureTestingModule({
    providers: [
      provideZonelessChangeDetection(),
      provideHttpClient(),
      provideHttpClientTesting(),
      { provide: EventStream, useValue: events },
      { provide: VoiceSpeaker, useValue: { say } },
      { provide: SPEECH, useValue: opts.speech === undefined ? new FakeSpeech() : opts.speech },
      { provide: VOICE_STORAGE, useValue: { get: (k: string) => map.get(k) ?? null, set: () => undefined } },
    ],
  });
  const notifier = TestBed.inject(VoiceNotifier);
  const http = TestBed.inject(HttpTestingController);
  return { events, say, notifier, http };
}

/** Answer the one open feed-posts request, checking its cursor. */
function answer(http: HttpTestingController, after: number | null, items: FeedPost[], latest: number) {
  const req = http.expectOne((r) => r.url === URL);
  expect(req.request.params.get('after')).toBe(after === null ? null : String(after));
  req.flush({ items, latest_id: latest });
}

/** Started, with the cursor at `latest`. */
function started(latest = 40, opts: Parameters<typeof setup>[0] = {}) {
  const ctx = setup(opts);
  ctx.notifier.start();
  answer(ctx.http, null, [], latest);
  TestBed.tick();
  return ctx;
}

function bump(events: FakeEvents) {
  events.emit('feed');
  TestBed.tick();
}

describe('VoiceNotifier (v227)', () => {
  afterEach(() => TestBed.inject(HttpTestingController).verify());

  it('words the overflow line', () => {
    expect(moreLine(3)).toBe('and 3 more');
    expect(RECONNECT_CAP).toBe(5);
    expect(FEED_PAGE_LIMIT).toBe(50);
  });

  it('starts at the latest id and speaks no backlog', () => {
    const { notifier, say, http } = setup();
    notifier.start();
    answer(http, null, [], 40);
    TestBed.tick();
    expect(notifier.lastId()).toBe(40);
    expect(say).not.toHaveBeenCalled();
    http.expectNone((r) => r.url === URL);
  });

  it('starts once however often it is asked', () => {
    const { notifier, http } = setup();
    notifier.start();
    notifier.start();
    answer(http, null, [], 40);
  });

  it('fetches after the cursor on a feed event and speaks the headlines in order', () => {
    const { events, say, notifier, http } = started();
    bump(events);
    const req = http.expectOne((r) => r.url === URL);
    expect(req.request.params.get('limit')).toBe(String(FEED_PAGE_LIMIT));
    expect(req.request.params.get('after')).toBe('40');
    req.flush({ items: [post(41), post(42)], latest_id: 42 });
    expect(say).toHaveBeenCalledExactlyOnceWith(['FILLED 41', 'FILLED 42']);
    expect(notifier.lastId()).toBe(42);
  });

  it('drops the kinds the toggles silence, Watch by default, and still advances', () => {
    const { events, say, notifier, http } = started(40, { stored: { kinds: { CANCEL: false } } });
    bump(events);
    answer(http, 40, [post(41), post(42, 'CANCEL', 'MANAGE'), post(43, 'NEAR_STOP', 'WATCH')], 43);
    expect(say).toHaveBeenCalledExactlyOnceWith(['FILLED 41']);
    expect(notifier.lastId()).toBe(43);
  });

  it('speaks nothing with the master switch off, but keeps the cursor moving', () => {
    const { events, say, notifier, http } = started(40, { stored: { enabled: false } });
    bump(events);
    answer(http, 40, [post(41)], 41);
    expect(say).not.toHaveBeenCalled();
    expect(notifier.lastId()).toBe(41);
  });

  it('speaks the five newest and "and N more" after a burst', () => {
    const { events, say, http } = started();
    bump(events);
    answer(http, 40, range(41, 48), 48);
    expect(say).toHaveBeenCalledExactlyOnceWith(
      ['FILLED 44', 'FILLED 45', 'FILLED 46', 'FILLED 47', 'FILLED 48', 'and 3 more']);
  });

  it('pages on while a page is full, speaking once at the end', () => {
    const { events, say, notifier, http } = started();
    bump(events);
    answer(http, 40, range(41, 90), 92);
    expect(say).not.toHaveBeenCalled();
    answer(http, 90, range(91, 92), 92);
    expect(say).toHaveBeenCalledExactlyOnceWith(
      ['FILLED 88', 'FILLED 89', 'FILLED 90', 'FILLED 91', 'FILLED 92', 'and 47 more']);
    expect(notifier.lastId()).toBe(92);
  });

  it('a resync with nothing new speaks nothing and keeps the cursor', () => {
    const { events, say, notifier, http } = started();
    bump(events);
    answer(http, 40, [], 40);
    expect(say).not.toHaveBeenCalled();
    expect(notifier.lastId()).toBe(40);
  });

  it('runs one fetch at a time and catches up once after it', () => {
    // Three bumps while the first request is open: one open request; answering
    // it brings exactly one catch-up request from the new cursor, not two.
    const { events, say, http } = started();
    bump(events);
    bump(events);
    bump(events);
    const open = http.match((r) => r.url === URL);
    expect(open).toHaveLength(1);
    open[0].flush({ items: [post(41)], latest_id: 41 });
    expect(say).toHaveBeenCalledExactlyOnceWith(['FILLED 41']);
    answer(http, 41, [post(42)], 42);
    expect(say).toHaveBeenLastCalledWith(['FILLED 42']);
    http.expectNone((r) => r.url === URL);
  });

  it('leaves the cursor alone when a fetch fails, so the next event retries', () => {
    const { events, say, notifier, http } = started();
    bump(events);
    http.expectOne((r) => r.url === URL).flush('down', { status: 503, statusText: 'Service Unavailable' });
    expect(notifier.lastId()).toBe(40);
    bump(events);
    answer(http, 40, [post(41)], 41);
    expect(say).toHaveBeenCalledExactlyOnceWith(['FILLED 41']);
  });

  it('a bump during the first latest-id read is caught up, not lost', () => {
    const { events, say, notifier, http } = setup();
    notifier.start();
    TestBed.tick();
    bump(events);
    answer(http, null, [], 40);
    answer(http, 40, [post(41)], 41);
    expect(say).toHaveBeenCalledExactlyOnceWith(['FILLED 41']);
  });

  it('never calls the API or speaks without speechSynthesis', () => {
    const { events, say, notifier, http } = setup({ speech: null });
    notifier.start();
    bump(events);
    http.expectNone((r) => r.url === URL);
    expect(say).not.toHaveBeenCalled();
    expect(notifier.lastId()).toBeNull();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-notifier.spec.ts
```

Expected: FAIL — `Cannot find module './voice-notifier'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/voice/voice-notifier.ts`:

```ts
import { Injectable, Injector, Signal, effect, inject, signal, untracked } from '@angular/core';

import { ApiClient } from '../api/api-client';
import { EventStream } from '../api/event-stream';
import { FeedPost } from '../api/models';
import { VoicePrefs } from './voice-prefs';
import { SPEECH, VoiceSpeaker } from './voice-speaker';

/** At most this many headlines per fetch; the rest become "and N more". */
export const RECONNECT_CAP = 5;
/** The server's maximum page; a full page means there may be more. */
export const FEED_PAGE_LIMIT = 50;

export const moreLine = (n: number): string => `and ${n} more`;

/**
 * Turns `feed` events into speech (spec v227 §3).
 *
 * The bot records every accepted simple-channel post in `feed_posts`; its
 * NOTIFY trigger raises `feed` on the event stream. Each bump fetches the
 * rows after the last id this tab has seen -- one fetch at a time, paging
 * while a page is full -- drops the kinds the partner silenced and hands the
 * newest five headlines to `VoiceSpeaker`. The cursor starts at the latest id
 * when the page loads, so a post made while no tab was open is never spoken.
 *
 * A resync bumps `feed` like every other event; the fetch then simply finds
 * nothing after the cursor.
 */
@Injectable({ providedIn: 'root' })
export class VoiceNotifier {
  private readonly api = inject(ApiClient);
  private readonly events = inject(EventStream);
  private readonly prefs = inject(VoicePrefs);
  private readonly speaker = inject(VoiceSpeaker);
  private readonly speech = inject(SPEECH);
  private readonly injector = inject(Injector);

  private readonly cursor = signal<number | null>(null);
  /** The last post id this tab has dealt with; null before the first answer. */
  readonly lastId: Signal<number | null> = this.cursor.asReadonly();

  private started = false;
  private fetching = false;
  private pending = false;
  private seen = 0;

  /** Called once by the shell; later calls do nothing. */
  start(): void {
    if (this.started || !this.speech) return;
    this.started = true;
    const feed = this.events.changes('feed');
    this.seen = untracked(feed);
    effect(() => {
      const count = feed();
      untracked(() => this.onFeed(count));
    }, { injector: this.injector });
    this.fetch();
  }

  private onFeed(count: number): void {
    if (count === this.seen) return;
    this.seen = count;
    this.fetch();
  }

  private fetch(): void {
    if (this.fetching) {
      this.pending = true;
      return;
    }
    this.fetching = true;
    this.page(this.cursor(), []);
  }

  private page(after: number | null, collected: FeedPost[]): void {
    this.api.feedPosts(after, FEED_PAGE_LIMIT).subscribe({
      next: (page) => {
        const items = [...collected, ...page.items];
        const last = page.items.at(-1)?.id ?? null;
        if (last !== null && page.items.length >= FEED_PAGE_LIMIT) {
          this.page(last, items);
          return;
        }
        this.cursor.set(last ?? page.latest_id);
        this.speak(items);
        this.done();
      },
      error: () => this.done(),
    });
  }

  private done(): void {
    this.fetching = false;
    if (!this.pending) return;
    this.pending = false;
    this.fetch();
  }

  private speak(items: FeedPost[]): void {
    if (!this.prefs.value().enabled) return;
    const kept = items.filter((item) => this.prefs.isKindOn(item.kind, item.family)).map((item) => item.headline);
    if (kept.length === 0) return;
    const lines = kept.slice(-RECONNECT_CAP);
    const skipped = kept.length - lines.length;
    this.speaker.say(skipped > 0 ? [...lines, moreLine(skipped)] : lines);
  }
}
```

The first `fetch()` in `start()` runs with a null cursor, so it is the
latest-id read: the server returns no items, the cursor becomes `latest_id`,
and `speak([])` says nothing. Note the cursor when the last page is empty is
`latest_id` even after earlier full pages: `latest_id` is read before the page
on the server (V227-6), so it is never behind the rows already collected.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/voice/voice-notifier.spec.ts --include src/app/voice/voice-speaker.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/voice/voice-notifier.ts frontend/src/app/voice/voice-notifier.spec.ts
git commit -m "feat(ui): v227 VoiceNotifier, feed event to fetch, filter and speak without backlog (V227-9)"
```

### Task V227-10: Voice chip in the top bar; shell starts the notifier

**Model:** sonnet — one OnPush chip modelled on `killswitch-chip.ts` plus a two-line shell wiring change, with the copy and states fixed by the spec.

**Files:**
- Create: `frontend/src/app/shell/voice-chip.ts`
- Create: `frontend/src/app/shell/voice-chip.spec.ts`
- Modify: `frontend/src/app/shell/shell.html` (`.status-cluster`, ~line 84)
- Modify: `frontend/src/app/shell/shell.ts` (`imports:` ~line 82; constructor ~line 344)
- Modify: `frontend/src/app/shell/shell.css` (phone block, ~line 315)
- Modify: `frontend/src/app/shell/shell.spec.ts` (the cluster-children test ~line 755; one new `describe`)
- Modify: `frontend/src/app/ui/primitives.spec.ts` (`RAW_BUTTON_ALLOWLIST`; joins this task beyond its ledger row, touched by no other task)

**Interfaces:**
- Consumes: `VoiceSpeaker.state(): VoiceState`, `.busy()`, `.unlock()`, `.mute()`, `.rearm()` (V227-8); `VoiceNotifier.start()` (V227-9); `Hint` (`sb-hint`, input `text`, `label`) from `frontend/src/app/ui/hint.ts`.
- Produces (final): `sb-voice-chip` (no inputs); `UNAVAILABLE_SEEN_KEY = 'swingbot.voice.unavailable-seen'` (sessionStorage); `UNAVAILABLE_SHOW_MS = 8000`; `BLOCKED_HINT` (the blocked state's explanation).

Chip states (spec §3; copy exact, index Global Constraints):

| `state()` | Renders | Text | `aria-label` | Tap |
|---|---|---|---|---|
| `off` | nothing | — | — | — |
| `locked` | button | Enable voice | Enable voice notifications | `unlock()` |
| `live` | button, waves pulse while `busy()` | Voice on | Mute voice notifications | `mute()` |
| `muted` | button | Voice muted | Turn voice notifications back on | `rearm()` |
| `blocked` | button + `sb-hint` | Voice blocked | Try voice notifications again | `unlock()` |
| `unavailable` | a status span, first time per browser session only, gone after 8 s | No voice on this browser | — (`role="status"`) | — |

Placement: the chip goes in `.status-cluster` **after** the viewer badge and the
phone shock pill and **before** `sb-alarm-chip`. (The index note said "first";
`shell.spec.ts` pins the read-only badge as the cluster's first child for a
viewer, v207, so the chip sits right after it.) It is never hidden by CSS at any
width, so the phone block only stops it from shrinking; the badge keeps its
existing ellipsis. V227-14's layout audit decides any further phone fit.

The busy pulse reuses `sb-pulse-dim` from `styles/motion.css`; the shell's
`data-motion` attribute stills it for anyone who turned motion off (no
`prefers-reduced-motion` query in a source file: `ui/motion-home.spec.ts`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/app/shell/voice-chip.spec.ts`:

```ts
import { WritableSignal, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { VoiceSpeaker, VoiceState } from '../voice/voice-speaker';
import { BLOCKED_HINT, UNAVAILABLE_SEEN_KEY, UNAVAILABLE_SHOW_MS, VoiceChip } from './voice-chip';

interface FakeSpeaker {
  state: WritableSignal<VoiceState>;
  busy: WritableSignal<boolean>;
  unlock: ReturnType<typeof vi.fn>;
  mute: ReturnType<typeof vi.fn>;
  rearm: ReturnType<typeof vi.fn>;
}

describe('VoiceChip (v227)', () => {
  let speaker: FakeSpeaker;

  beforeEach(() => {
    sessionStorage.removeItem(UNAVAILABLE_SEEN_KEY);
    speaker = { state: signal<VoiceState>('locked'), busy: signal(false), unlock: vi.fn(), mute: vi.fn(), rearm: vi.fn() };
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: VoiceSpeaker, useValue: speaker }],
    });
  });

  afterEach(() => {
    sessionStorage.removeItem(UNAVAILABLE_SEEN_KEY);
    vi.useRealTimers();
  });

  function render(state: VoiceState) {
    speaker.state.set(state);
    const fixture = TestBed.createComponent(VoiceChip);
    fixture.detectChanges();
    return { fixture, el: fixture.nativeElement as HTMLElement };
  }

  const button = (el: HTMLElement) => el.querySelector<HTMLButtonElement>('button.voice-chip');

  it('renders nothing while voice is switched off in Settings', () => {
    const { el } = render('off');
    expect(el.textContent!.trim()).toBe('');
    expect(button(el)).toBeNull();
  });

  const CASES: [VoiceState, string, string, 'unlock' | 'mute' | 'rearm'][] = [
    ['locked', 'Enable voice', 'Enable voice notifications', 'unlock'],
    ['live', 'Voice on', 'Mute voice notifications', 'mute'],
    ['muted', 'Voice muted', 'Turn voice notifications back on', 'rearm'],
    ['blocked', 'Voice blocked', 'Try voice notifications again', 'unlock'],
  ];

  for (const [state, text, aria, action] of CASES) {
    it(`reads "${text}" when ${state}, names its action, and taps ${action}()`, () => {
      const { el } = render(state);
      const chip = button(el)!;
      expect(chip.querySelector('.text')!.textContent!.trim()).toBe(text);
      expect(chip.getAttribute('aria-label')).toBe(aria);
      expect(chip.classList).toContain('sb-hit');
      expect(chip.hasAttribute('title')).toBe(false);
      chip.click();
      expect(speaker[action]).toHaveBeenCalledTimes(1);
    });
  }

  it('explains a blocked browser in a hint beside the chip, and only then', () => {
    const blocked = render('blocked').el;
    expect(blocked.querySelector('sb-hint')).not.toBeNull();
    expect(BLOCKED_HINT).toBe(
      'Your browser blocked sound for this site. Allow sound in the site settings, then tap again.');
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), { provide: VoiceSpeaker, useValue: speaker }],
    });
    expect(render('locked').el.querySelector('sb-hint')).toBeNull();
  });

  it('pulses only while live and speaking', () => {
    const { fixture, el } = render('live');
    expect(button(el)!.classList).not.toContain('busy');
    speaker.busy.set(true);
    fixture.detectChanges();
    expect(button(el)!.classList).toContain('busy');
  });

  it('follows the speaker from locked to live without a re-render', () => {
    const { fixture, el } = render('locked');
    speaker.state.set('live');
    fixture.detectChanges();
    expect(button(el)!.querySelector('.text')!.textContent!.trim()).toBe('Voice on');
  });

  it('says "No voice on this browser" once per session, then hides after 8 s', () => {
    vi.useFakeTimers();
    const { fixture, el } = render('unavailable');
    const note = el.querySelector('[role="status"]')!;
    expect(note.textContent!.trim()).toBe('No voice on this browser');
    expect(button(el)).toBeNull();
    expect(sessionStorage.getItem(UNAVAILABLE_SEEN_KEY)).not.toBeNull();
    vi.advanceTimersByTime(UNAVAILABLE_SHOW_MS);
    fixture.detectChanges();
    expect(el.querySelector('[role="status"]')).toBeNull();
  });

  it('stays hidden on a later load in the same session', () => {
    sessionStorage.setItem(UNAVAILABLE_SEEN_KEY, '1');
    const { el } = render('unavailable');
    expect(el.textContent!.trim()).toBe('');
  });
});
```

In `frontend/src/app/shell/shell.spec.ts`, add the import
`import { VoiceNotifier } from '../voice/voice-notifier';`, change the
cluster-children test (~line 755) to:

```ts
  it('keeps only the voice, alarm and killswitch chips in the cluster, hidden at no width', async () => {
    // v203 Retired 'puts the killswitch and freshness chips in the cluster' and
    // 'ages the freshness chip …' (spec v202 D5: freshness, connection and the clock
    // live in the dock and strip; V203-4's botRows pins the freshness words).
    // v227: the voice chip joins, before the alarm chip.
    const { el } = await mount();
    const cluster = el.querySelector('header.topbar > .status-cluster')!;
    expect([...cluster.children].map((c) => c.tagName.toLowerCase()))
      .toEqual(['sb-voice-chip', 'sb-alarm-chip', 'sb-killswitch-chip']);
    expect(el.querySelector('header.topbar sb-freshness-chip, header.topbar sb-connection-status')).toBeNull();
    const css = readSource('src/app/shell/shell.css').replace(/\/\*[\s\S]*?\*\//g, '');
    expect(css).not.toMatch(/(sb-killswitch-chip|sb-alarm-chip|sb-voice-chip|\.status-cluster)[^{}]*\{[^}]*display:\s*none/);
  });
```

and append at the end of the file:

```ts
describe('shell voice notifications (v227)', () => {
  it('starts the voice notifier once, when the shell is created', () => {
    const start = vi.fn();
    TestBed.configureTestingModule({
      providers: [...shellProviders(), { provide: VoiceNotifier, useValue: { start } }],
    });
    createShell().detectChanges();
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('mounts the chip after the viewer badge and before the alarm chip', () => {
    const html = readSource('src/app/shell/shell.html');
    const cluster = html.slice(html.indexOf('class="status-cluster"'));
    const at = (tag: string) => cluster.indexOf(tag);
    expect(at('<sb-voice-chip />')).toBeGreaterThan(at('<sb-read-only-badge'));
    expect(at('<sb-voice-chip />')).toBeGreaterThan(at('<sb-shock-pill'));
    expect(at('<sb-voice-chip />')).toBeLessThan(at('<sb-alarm-chip'));
  });

  it('never lets the chip shrink on a phone', () => {
    const css = readSource('src/app/shell/shell.css');
    const phone = css.slice(css.lastIndexOf('@media (max-width: 639px)'));
    expect(phone).toMatch(/sb-voice-chip \{[^}]*flex: none;/);
  });
});
```

The other shell specs need no change: jsdom has no `speechSynthesis`, so the
real `SPEECH` token resolves to `null`, `VoiceNotifier.start()` makes no request
(V227-9 rule 7), and the chip is `unavailable`.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/shell/voice-chip.spec.ts --include src/app/shell/shell.spec.ts
```

Expected: FAIL — `Cannot find module './voice-chip'` (and the shell cluster test lists two chips).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/shell/voice-chip.ts`:

```ts
import { ChangeDetectionStrategy, Component, DestroyRef, computed, inject, signal } from '@angular/core';

import { Hint } from '../ui/hint';
import { VoiceSpeaker } from '../voice/voice-speaker';

/** sessionStorage: the "no voice here" note was already shown this session. */
export const UNAVAILABLE_SEEN_KEY = 'swingbot.voice.unavailable-seen';
export const UNAVAILABLE_SHOW_MS = 8000;
export const BLOCKED_HINT =
  'Your browser blocked sound for this site. Allow sound in the site settings, then tap again.';

type Action = 'unlock' | 'mute' | 'rearm';

interface ChipView {
  text: string;
  aria: string;
  action: Action;
  hint: string | null;
}

/** One row per tappable state; `off` and `unavailable` render no button. */
const VIEWS: Partial<Record<string, ChipView>> = {
  locked: { text: 'Enable voice', aria: 'Enable voice notifications', action: 'unlock', hint: null },
  live: { text: 'Voice on', aria: 'Mute voice notifications', action: 'mute', hint: null },
  muted: { text: 'Voice muted', aria: 'Turn voice notifications back on', action: 'rearm', hint: null },
  blocked: { text: 'Voice blocked', aria: 'Try voice notifications again', action: 'unlock', hint: BLOCKED_HINT },
};

/** True the first time this browser session asks; storage trouble counts as first. */
function firstTimeThisSession(): boolean {
  try {
    const store = globalThis.sessionStorage;
    if (store.getItem(UNAVAILABLE_SEEN_KEY)) return false;
    store.setItem(UNAVAILABLE_SEEN_KEY, '1');
  } catch {
    /* Blocked storage: show the note; it still hides after 8 s. */
  }
  return true;
}

/**
 * The voice state, in the top bar on every device (spec v227 §3).
 *
 * Browsers refuse speech until the page has had a tap, on every load, so a
 * switched-on voice starts as "Enable voice" and this chip is where that tap
 * happens. Live, it is the stop control: one tap cuts the current headline,
 * drops the queue and mutes for the session. The word carries the state; the
 * icon only repeats it. Voice off in Settings: no chip at all.
 */
@Component({
  selector: 'sb-voice-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Hint],
  template: `
    @if (view(); as v) {
      <button type="button" class="voice-chip sb-hit" [class.busy]="pulsing()" [class.warn]="v.hint !== null"
              [attr.aria-label]="v.aria" (click)="act(v.action)">
        <svg class="speaker" viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor"
             stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M2 6h3l4-3v10l-4-3H2z" />
          @if (v.action === 'mute') {
            <path class="waves" d="M11 5.5a3.5 3.5 0 0 1 0 5 M12.8 3.8a6 6 0 0 1 0 8.4" />
          } @else {
            <path d="M11.5 6l3 4 M14.5 6l-3 4" />
          }
        </svg>
        <span class="text">{{ v.text }}</span>
      </button>
      @if (v.hint) {
        <sb-hint [text]="v.hint" label="How to allow sound" />
      }
    } @else if (showUnavailable()) {
      <span class="voice-chip note" role="status">No voice on this browser</span>
    }
  `,
  styles: `
    :host { display: inline-flex; align-items: center; gap: var(--space-4); }
    .voice-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      background: transparent;
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-chip);
      line-height: 1.4;
      white-space: nowrap;
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .voice-chip:hover { color: var(--text); border-color: var(--text-muted); }
    .voice-chip.warn { color: var(--warn); border-color: var(--warn); background: var(--warn-soft); }
    .voice-chip.note { cursor: default; color: var(--text-muted); }
    .speaker { flex: none; }
    .busy .waves { animation: sb-pulse-dim 1.2s ease-in-out infinite; }
  `,
})
export class VoiceChip {
  private readonly speaker = inject(VoiceSpeaker);

  protected readonly view = computed(() => VIEWS[this.speaker.state()] ?? null);
  protected readonly pulsing = computed(() => this.speaker.state() === 'live' && this.speaker.busy());
  protected readonly showUnavailable = signal(false);

  constructor() {
    if (this.speaker.state() !== 'unavailable' || !firstTimeThisSession()) return;
    this.showUnavailable.set(true);
    const timer = setTimeout(() => this.showUnavailable.set(false), UNAVAILABLE_SHOW_MS);
    inject(DestroyRef).onDestroy(() => clearTimeout(timer));
  }

  /** Runs inside the click handler: `unlock()` must speak within the user's gesture. */
  protected act(action: Action): void {
    this.speaker[action]();
  }
}
```

`frontend/src/app/shell/shell.html`, inside `.status-cluster`, right after the
`@if (isPhone()) { <sb-shock-pill … /> }` block and before `<sb-alarm-chip …>`:

```html
        <!-- v227: speech for simple-channel posts. Every width, never in a menu:
             browsers need this chip's tap on every load before they speak. -->
        <sb-voice-chip />
```

`frontend/src/app/shell/shell.ts`: import `VoiceChip` from `./voice-chip` and
`VoiceNotifier` from `../voice/voice-notifier`, add `VoiceChip` to the
component's `imports:` array (after `KillswitchChip`), and add at the end of the
constructor:

```ts
    // v227: speak simple-channel posts while this tab is open. Root service;
    // start() is idempotent and does nothing on a browser without speech.
    inject(VoiceNotifier).start();
```

`frontend/src/app/shell/shell.css`, inside the last `@media (max-width: 639px)`
block, after `.status-cluster { min-width: 0; }`:

```css
  /* v227: the voice chip's word is the state and the tap target; the badge
     ellipsises first, the chip never shrinks. */
  sb-voice-chip { flex: none; }
```

`frontend/src/app/ui/primitives.spec.ts`, append to `RAW_BUTTON_ALLOWLIST`
(after the `live-strip` entry; the comment is required by "every allowlist
entry is justified"):

```ts
  // v227: the voice chip is a top-bar chip like the alarm chip -- speaker glyph
  // + state word, padded to 44px by .sb-hit, aria-label naming its action.
  ['shell/voice-chip.ts', 'class="voice-chip sb-hit"'],
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/shell/voice-chip.spec.ts --include src/app/shell/shell.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/title-usage.spec.ts --include src/app/ui/motion-home.spec.ts --include src/app/ui/spacing.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shell/voice-chip.ts frontend/src/app/shell/voice-chip.spec.ts frontend/src/app/ui/primitives.spec.ts
git commit -m "feat(ui): v227 voice chip, locked/live/muted/blocked/unavailable (V227-10)"
git add frontend/src/app/shell/shell.html frontend/src/app/shell/shell.ts frontend/src/app/shell/shell.css frontend/src/app/shell/shell.spec.ts
git commit -m "feat(ui): v227 mount the voice chip in the top bar and start the notifier (V227-10)"
```

### Task V227-11: `sb-switch` primitive (`role="switch"`, mixed state, 44 px)

**Model:** sonnet — a small self-contained `ui/` primitive with fixed inputs and output; no service or cross-package contract.

**Files:**
- Create: `frontend/src/app/ui/switch.ts`
- Create: `frontend/src/app/ui/switch.spec.ts`

No registry needs an entry: `ui/` primitives are outside `callSites()` (so the
raw `<button>` needs no allowlist row), and neither `register.spec.ts` nor
`primitives.spec.ts` enumerates the primitives themselves.

**Interfaces:**
- Consumes: tokens only (`--hit-min`, `--control-h`, `--space-*`, `--accent`, `--accent-soft`, `--border-strong`, `--surface-raised`, `--text`, `--text-muted`, `--text-table`, `--text-chip`, `--transition`).
- Produces (final; V227-12 consumes): `sb-switch` with inputs `label: string` (required), `checked: boolean = false`, `mixed: boolean = false`, `disabled: boolean = false`, `hint: string | null = null`; output `checkedChange: boolean` (from mixed → `true`, otherwise `!checked`). The component is controlled: it never flips its own `checked`; the parent feeds the new value back.

Semantics (spec §4; index notes V227-11): a native `<button type="button"
role="switch">` so Space and Enter work without key handlers; `aria-checked`
is `"true"`, `"false"` or `"mixed"`; the visible label is the button's text, so
no `aria-label` duplicates it; `disabled` is the real attribute (out of the tab
order, no click); the optional hint is a line under the control tied by
`aria-describedby`. The row is at least `--hit-min` tall — 44 px on touch and
below 1024 px through `tokens.css`, never through a coarse-pointer block of its
own (`ui/hit-area.spec.ts`). The label wraps; nothing truncates.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/app/ui/switch.spec.ts`:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Component, provideZonelessChangeDetection, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Switch } from './switch';

@Component({
  imports: [Switch],
  template: `
    <sb-switch [label]="label" [checked]="checked()" [mixed]="mixed()" [disabled]="disabled()" [hint]="hint()"
               (checkedChange)="changes.push($event); checked.set($event); mixed.set(false)" />
  `,
})
class Host {
  label = 'Order filled';
  readonly checked = signal(false);
  readonly mixed = signal(false);
  readonly disabled = signal(false);
  readonly hint = signal<string | null>(null);
  readonly changes: boolean[] = [];
}

describe('Switch (v227)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(setup: (host: Host) => void = () => undefined) {
    const fixture = TestBed.createComponent(Host);
    setup(fixture.componentInstance);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    return { fixture, host: fixture.componentInstance, el, button: el.querySelector('button')! };
  }

  it('is a button with role switch, named by its visible label', () => {
    const { button } = mount();
    expect(button.getAttribute('type')).toBe('button');
    expect(button.getAttribute('role')).toBe('switch');
    expect(button.textContent!.trim()).toBe('Order filled');
    expect(button.hasAttribute('aria-label')).toBe(false);
    expect(button.hasAttribute('title')).toBe(false);
  });

  it('reports aria-checked true, false and mixed', () => {
    const { fixture, host, button } = mount();
    expect(button.getAttribute('aria-checked')).toBe('false');
    host.checked.set(true);
    fixture.detectChanges();
    expect(button.getAttribute('aria-checked')).toBe('true');
    host.mixed.set(true);
    fixture.detectChanges();
    expect(button.getAttribute('aria-checked')).toBe('mixed');
  });

  it('emits the flipped value on a click and follows the parent', () => {
    const { fixture, host, button } = mount();
    button.click();
    fixture.detectChanges();
    expect(host.changes).toEqual([true]);
    expect(button.getAttribute('aria-checked')).toBe('true');
    button.click();
    expect(host.changes).toEqual([true, false]);
  });

  it('turns a mixed switch fully on', () => {
    const { host, button } = mount((h) => {
      h.checked.set(false);
      h.mixed.set(true);
    });
    button.click();
    expect(host.changes).toEqual([true]);
  });

  it('is really disabled: the attribute is set and a click emits nothing', () => {
    const { host, button } = mount((h) => h.disabled.set(true));
    expect(button.disabled).toBe(true);
    button.click();
    expect(host.changes).toEqual([]);
  });

  it('ties an optional hint line to the control', () => {
    const none = mount();
    expect(none.button.hasAttribute('aria-describedby')).toBe(false);
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    const { el, button } = mount((h) => h.hint.set('Says: Order filled, <ticker>'));
    const id = button.getAttribute('aria-describedby')!;
    expect(el.querySelector(`#${id}`)!.textContent!.trim()).toBe('Says: Order filled, <ticker>');
  });

  it('gives each switch its own hint id', () => {
    const a = mount((h) => h.hint.set('a')).button.getAttribute('aria-describedby');
    const b = mount((h) => h.hint.set('b')).button.getAttribute('aria-describedby');
    expect(a).not.toBe(b);
  });

  it('is at least --hit-min tall, lets the label wrap, and uses tokens only', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/ui/switch.ts'), 'utf8');
    expect(source).toMatch(/\.switch \{[^}]*min-height: var\(--hit-min\);/);
    expect(source).not.toMatch(/text-overflow|white-space: nowrap/);
    expect(source).not.toMatch(/pointer: coarse/);
    expect(source).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgba?\(/);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/ui/switch.spec.ts
```

Expected: FAIL — `Cannot find module './switch'`.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/app/ui/switch.ts`:

```ts
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

let nextId = 0;

/**
 * An on/off switch (spec v227 §4): a native button with `role="switch"`, so
 * Space and Enter toggle it and the visible label is its accessible name.
 *
 * `mixed` is for a group switch over a partly-on set (a Settings family): it
 * reads `aria-checked="mixed"`, and a tap turns the whole set on. Controlled:
 * it emits the wanted value and shows whatever `checked` the parent passes back.
 *
 * At least --hit-min tall, which tokens.css raises to 44px on touch and below
 * 1024px; the label wraps rather than truncating.
 */
@Component({
  selector: 'sb-switch',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" role="switch" class="switch" [attr.aria-checked]="ariaChecked()"
            [disabled]="disabled()" [attr.aria-describedby]="hint() ? hintId : null" (click)="toggle()">
      <span class="track" [class.on]="checked() && !mixed()" [class.mixed]="mixed()" aria-hidden="true">
        <span class="thumb"></span>
      </span>
      <span class="label">{{ label() }}</span>
    </button>
    @if (hint(); as text) {
      <span class="hint" [id]="hintId">{{ text }}</span>
    }
  `,
  styles: `
    :host { display: flex; flex-direction: column; min-width: 0; }
    .switch {
      display: inline-flex;
      align-items: center;
      gap: var(--space-8);
      min-height: var(--hit-min);
      padding: 0;
      border: 0;
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .switch:disabled { opacity: 0.45; cursor: default; }
    .switch:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .label { min-width: 0; overflow-wrap: anywhere; }
    .track {
      position: relative;
      flex: none;
      width: 28px;
      height: 16px;
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      background: var(--surface-raised);
      transition: background var(--transition), border-color var(--transition);
    }
    .thumb {
      position: absolute;
      top: 2px;
      left: 2px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--text-muted);
      transition: transform var(--transition);
    }
    .track.on { background: var(--accent-soft); border-color: var(--accent); }
    .track.on .thumb { transform: translateX(12px); background: var(--accent); }
    .track.mixed .thumb { transform: translateX(6px); background: var(--accent); }
    .hint { padding-left: calc(28px + var(--space-8)); color: var(--text-muted); font-size: var(--text-chip); }
  `,
})
export class Switch {
  readonly label = input.required<string>();
  readonly checked = input(false);
  readonly mixed = input(false);
  readonly disabled = input(false);
  readonly hint = input<string | null>(null);
  /** The wanted value: `true` from mixed, otherwise the flip of `checked`. */
  readonly checkedChange = output<boolean>();

  protected readonly hintId = `sb-switch-hint-${nextId++}`;
  protected readonly ariaChecked = computed(() => (this.mixed() ? 'mixed' : String(this.checked())));

  protected toggle(): void {
    if (this.disabled()) return;
    this.checkedChange.emit(this.mixed() ? true : !this.checked());
  }
}
```

If `ui/elevation.spec.ts`, `ui/tokens.spec.ts` or `ui/contrast.spec.ts` flags
the thumb's `border-radius: 50%` (the status-dot exception) or a token pair,
switch to the token the failing assertion names; do not add an allowlist entry.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
node frontend/scripts/ng-test.mjs frontend --include src/app/ui/switch.spec.ts --include src/app/ui/hit-area.spec.ts --include src/app/ui/spacing.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/tokens.spec.ts
```

Expected: PASS, `0 failed`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/ui/switch.ts frontend/src/app/ui/switch.spec.ts
git commit -m "feat(ui): v227 sb-switch primitive, role=switch with a mixed state (V227-11)"
```

