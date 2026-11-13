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
