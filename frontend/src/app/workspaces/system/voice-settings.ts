import { ChangeDetectionStrategy, Component, DestroyRef, Signal, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

import { ApiClient } from '../../api/api-client';
import { FeedKind, FeedKindFamily } from '../../api/models';
import { Panel } from '../../ui/layout';
import { PanelError } from '../../ui/panel-error';
import { Spinner } from '../../ui/spinner';
import { Switch } from '../../ui/switch';
import { VoicePrefs } from '../../voice/voice-prefs';

export const VOICE_OFF_REASON = 'Turn on voice to choose kinds';

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
 * outside its sb-async -- it works while that payload loads or fails.
 *
 * The kinds come from GET /feed-posts/kinds, so a kind added to the server's
 * registry appears here with no frontend change. The master switch sits
 * outside the details element so voice can be switched off without opening
 * anything; the details start open so a first visit shows every choice.
 */
@Component({
  selector: 'sb-voice-settings',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Switch, Spinner, PanelError],
  template: `
    <sb-panel heading="Voice notifications">
      <div class="master">
        <sb-switch label="Speak simple-channel posts" [checked]="enabled()" (checkedChange)="prefs.setEnabled($event)" />
        @if (!enabled()) {
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
                    </li>
                  }
                </ul>
              </section>
            }
          </div>
        }
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
    .families { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--space-14); margin-top: var(--space-10); }
    @media (min-width: 640px) {
      .families { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    .family { min-width: 0; }
    .kinds { display: grid; gap: var(--space-4); margin: var(--space-4) 0 0; padding: 0 0 0 var(--space-14); list-style: none; }
    .kind { display: flex; align-items: flex-start; gap: var(--space-8); min-width: 0; }
    .kind sb-switch { flex: 1 1 auto; min-width: 0; }
  `,
})
export class VoiceSettings {
  protected readonly prefs = inject(VoicePrefs);
  private readonly api = inject(ApiClient);
  private readonly destroyRef = inject(DestroyRef);

  protected readonly offReason = VOICE_OFF_REASON;

  private readonly kindList = signal<FeedKindFamily[] | null>(null);
  protected readonly loadError = signal(false);

  readonly families: Signal<FeedKindFamily[] | null> = this.kindList.asReadonly();
  readonly enabled = computed(() => this.prefs.value().enabled);

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
