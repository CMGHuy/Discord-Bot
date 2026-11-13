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
