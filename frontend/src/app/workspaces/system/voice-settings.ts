import { ChangeDetectionStrategy, Component, DestroyRef, Signal, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiClient } from '../../api/api-client';
import { FeedKind, FeedKindFamily } from '../../api/models';
import { Button } from '../../ui/button';
import { Select, SelectOption } from '../../ui/form-controls';
import { Panel } from '../../ui/layout';
import { PanelError } from '../../ui/panel-error';
import { Spinner } from '../../ui/spinner';
import { Switch } from '../../ui/switch';
import { RATE_MAX, RATE_MIN, RATE_STEP, VoicePrefs } from '../../voice/voice-prefs';
import { VoiceSpeaker } from '../../voice/voice-speaker';

export const VOICE_OFF_REASON = 'Turn on voice to choose kinds';
export const NO_VOICE_NOTE = 'No voice on this browser';
export const SYSTEM_DEFAULT_VOICE = 'System default';
export const LOADING_VOICES = 'Loading voices…';
export const MISSING_VOICE_NOTE = "Your saved voice isn't on this device; using the system default.";
export const TEST_VOICE_FALLBACK = 'New long alert, AAPL, buy at 187.50';

/** The picker's options: one loading row until the browser lists its voices. */
export function voiceOptions(voices: string[] | null): SelectOption[] {
  if (voices === null) return [{ value: '', label: LOADING_VOICES }];
  return [{ value: '', label: SYSTEM_DEFAULT_VOICE }, ...voices.map((name) => ({ value: name, label: name }))];
}

export function rateText(rate: number): string {
  return `${rate.toFixed(2)}×`;
}

/** Test voice says the server's own new-alert sample, else a fixed one. */
export function testVoiceSample(families: FeedKindFamily[] | null): string {
  for (const family of families ?? []) {
    const setup = family.kinds.find((kind) => kind.kind === 'SETUP_SIMPLE');
    if (setup?.sample) return setup.sample;
  }
  return TEST_VOICE_FALLBACK;
}

/** The plain-words line under a kind: what the site will say for it. */
export function spokenHint(phrase: string): string {
  return `Says: ${phrase}, <ticker>`;
}

export interface KindRow extends FeedKind {
  on: boolean;
  hint: string;
}

export interface FamilyRow {
  family: string;
  label: string;
  kinds: KindRow[];
  /** Every kind on (an empty family is never "all on"). */
  allOn: boolean;
  /** Some kinds on, some off: the family switch reads aria-checked="mixed". */
  mixed: boolean;
}

/** One family's switches from the stored flags; pure, so it is tested alone. */
export function familyRow(family: FeedKindFamily, isOn: (kind: string) => boolean): FamilyRow {
  const kinds = family.kinds.map((kind) => ({ ...kind, on: isOn(kind.kind), hint: spokenHint(kind.phrase) }));
  const onCount = kinds.filter((kind) => kind.on).length;
  return {
    family: family.family,
    label: family.label,
    kinds,
    allOn: kinds.length > 0 && onCount === kinds.length,
    mixed: onCount > 0 && onCount < kinds.length,
  };
}

/**
 * System → Settings → Voice notifications (spec v227 §4).
 *
 * Per-browser choices only (VoicePrefs, localStorage): nothing here reads or
 * writes the /system/settings payload, which is why the tab mounts this block
 * outside its async panel -- it works while that payload loads or fails.
 *
 * The kinds come from GET /feed-posts/kinds, so a kind added to the server's
 * registry appears here with no frontend change. The master switch sits
 * outside the details element so voice can be switched off without opening
 * anything; the details start open so a first visit shows every choice.
 */
@Component({
  selector: 'sb-voice-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Switch, Button, Spinner, PanelError, Select],
  template: `
    <sb-panel heading="Voice notifications">
      <div class="master">
        <sb-switch label="Speak simple-channel posts" [checked]="enabled()" (checkedChange)="prefs.setEnabled($event)" />
        @if (unavailable()) {
          <p class="reason" role="status">{{ noVoice }}</p>
        } @else if (!enabled()) {
          <p class="reason">{{ offReason }}</p>
        }
      </div>
      <details class="voice" open>
        <summary class="sb-hit">Kinds, voice and speed</summary>
        @if (loadError()) {
          <sb-panel-error message="voice kinds" (retry)="load()" />
        } @else if (families() === null) {
          <sb-spinner label="Loading kinds" />
        } @else {
          <div class="families">
            @for (family of rows(); track family.family) {
              <section class="family" role="group" [attr.aria-label]="family.label">
                <sb-switch
                  [label]="family.label"
                  [checked]="family.allOn"
                  [mixed]="family.mixed"
                  [disabled]="!enabled()"
                  (checkedChange)="setFamily(family, $event)"
                />
                <ul class="kinds">
                  @for (kind of family.kinds; track kind.kind) {
                    <li class="kind">
                      <sb-switch
                        [label]="kind.label"
                        [checked]="kind.on"
                        [hint]="kind.hint"
                        [disabled]="!enabled()"
                        (checkedChange)="prefs.setKind(kind.kind, $event)"
                      />
                      <button
                        sb-button
                        variant="ghost"
                        type="button"
                        class="preview"
                        [attr.aria-label]="'Preview ' + kind.label"
                        [disabled]="!canSpeak()"
                        (click)="speaker.preview(kind.sample)"
                      >▶</button>
                    </li>
                  }
                </ul>
              </section>
            }
          </div>
        }
        <div class="voice-controls">
          <sb-select
            label="Voice"
            [options]="voiceList()"
            [value]="selectedVoice()"
            [disabled]="!canSpeak() || speaker.voices() === null"
            (valueChange)="prefs.setVoice($event || null)"
          />
          <label class="rate">
            <span class="sb-label">Rate</span>
            <span class="rate-row">
              <input
                type="range"
                [min]="rateMin"
                [max]="rateMax"
                [step]="rateStep"
                [value]="rate()"
                [disabled]="!enabled()"
                (input)="onRate($event)"
              />
              <output>{{ rateLabel() }}</output>
            </span>
          </label>
          <button sb-button variant="secondary" type="button" [disabled]="!canSpeak()" (click)="testVoice()">
            Test voice
          </button>
          @if (missingVoice()) {
            <p class="reason missing">{{ missingVoiceNote }}</p>
          }
        </div>
      </details>
    </sb-panel>
  `,
  styles: `
    /* No backticks in here: these styles live in a TS template literal. */
    :host { display: block; min-width: 0; }
    .master { display: flex; flex-direction: column; gap: var(--space-4); }
    .reason { margin: 0; color: var(--text-secondary); font-size: var(--text-table); overflow-wrap: anywhere; }
    .voice { margin-top: var(--space-14); font-size: var(--text-table); }
    summary { color: var(--text-secondary); cursor: pointer; }
    .families { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 20rem), 1fr)); gap: var(--space-14); margin-top: var(--space-10); }
    .family { min-width: 0; }
    .kinds { display: grid; gap: var(--space-4); margin: var(--space-4) 0 0; padding: 0 0 0 var(--space-14); list-style: none; }
    .kind { display: flex; align-items: center; gap: var(--space-8); min-width: 0; }
    .kind sb-switch { flex: 1 1 auto; min-width: 0; }
    .preview { flex: none; min-width: var(--hit-min); }
    .voice-controls { display: flex; flex-wrap: wrap; align-items: flex-start; gap: var(--space-10) var(--space-14); margin-top: var(--space-14); }
    .missing { flex-basis: 100%; }
    .voice-controls > button { align-self: flex-end; }
    .rate { display: inline-flex; flex: 1 1 220px; flex-direction: column; gap: var(--space-4); min-width: 0; }
    .rate-row { display: flex; align-items: center; gap: var(--space-8); }
    .rate input {
      flex: 1 1 auto;
      min-width: 0;
      height: var(--hit-min);
      margin: 0;
      background: transparent;
      -webkit-appearance: none;
      appearance: none;
    }
    .rate input:disabled { opacity: 0.45; }
    .rate input::-webkit-slider-runnable-track { height: 4px; border-radius: var(--chip-radius); background: var(--border-strong); }
    .rate input::-webkit-slider-thumb { -webkit-appearance: none; width: var(--hit-min); height: var(--hit-min); margin-top: calc(2px - var(--hit-min) / 2); border-radius: 50%; background: var(--accent); }
    .rate input::-moz-range-track { height: 4px; border-radius: var(--chip-radius); background: var(--border-strong); }
    .rate input::-moz-range-thumb { width: var(--hit-min); height: var(--hit-min); border: 0; border-radius: 50%; background: var(--accent); }
    .rate output { min-width: 5ch; color: var(--text); font-variant-numeric: tabular-nums; }
  `,
})
export class VoiceSettings {
  protected readonly prefs = inject(VoicePrefs);
  protected readonly speaker = inject(VoiceSpeaker);
  private readonly api = inject(ApiClient);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly offReason = VOICE_OFF_REASON;
  protected readonly noVoice = NO_VOICE_NOTE;

  private readonly kindList = signal<FeedKindFamily[] | null>(null);
  protected readonly loadError = signal(false);

  readonly families: Signal<FeedKindFamily[] | null> = this.kindList.asReadonly();
  readonly enabled = computed(() => this.prefs.value().enabled);
  readonly unavailable = computed(() => this.speaker.state() === 'unavailable');
  /** Previews and Test voice: the master is on and the browser can speak. */
  readonly canSpeak = computed(() => this.enabled() && !this.unavailable());

  protected readonly rateMin = RATE_MIN;
  protected readonly rateMax = RATE_MAX;
  protected readonly rateStep = RATE_STEP;
  protected readonly missingVoiceNote = MISSING_VOICE_NOTE;

  protected readonly voiceList = computed(() => voiceOptions(this.speaker.voices()));
  /** A stored voice this device's loaded list does not have. */
  protected readonly missingVoice = computed(() => {
    const stored = this.prefs.value().voice;
    const voices = this.speaker.voices();
    return stored !== null && voices !== null && !voices.includes(stored);
  });
  protected readonly selectedVoice = computed(() => (this.missingVoice() ? '' : (this.prefs.value().voice ?? '')));
  protected readonly rate = computed(() => this.prefs.value().rate);
  protected readonly rateLabel = computed(() => rateText(this.rate()));

  protected onRate(event: Event): void {
    this.prefs.setRate(Number((event.target as HTMLInputElement).value));
  }

  protected testVoice(): void {
    this.speaker.preview(testVoiceSample(this.families()));
  }

  /** isKindOn reads the prefs signal, so a toggle recomputes the rows. */
  protected readonly rows = computed(() =>
    (this.kindList() ?? []).map((family) => familyRow(family, (kind) => this.prefs.isKindOn(kind, family.family))),
  );

  constructor() {
    this.load();
  }

  /** Fetch the kinds; Retry on the error line calls this again. */
  load(): void {
    this.loadError.set(false);
    this.api
      .feedPostKinds()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (families) => this.kindList.set(families),
        error: () => this.loadError.set(true),
      });
  }

  protected setFamily(family: FamilyRow, on: boolean): void {
    this.prefs.setKinds(family.kinds.map((kind) => kind.kind), on);
  }
}
