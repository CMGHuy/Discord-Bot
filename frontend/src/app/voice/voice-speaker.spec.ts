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
});
