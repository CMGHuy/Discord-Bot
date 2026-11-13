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

let openHttp: HttpTestingController | null = null;

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
  openHttp = http;
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
  afterEach(() => {
    openHttp?.verify();
    openHttp = null;
  });

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
