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
