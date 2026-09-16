import {
  ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, input,
  signal, untracked,
} from '@angular/core';

import { ScanProgressRecord } from '../api/models';

/** How long a finished bar stays at 100% before it fades.
 *
 *  A scan that ends mid-sweep would otherwise just vanish, which reads as a
 *  scan that was cancelled rather than one that completed. */
export const LINGER_MS = 1_500;

/** Silence from the bot past this and the bar stops claiming to be live.
 *
 *  The bot republishes roughly once a second, so this is ~30 missed writes --
 *  long enough to ride out a slow ticker or a paused container, short enough
 *  that a dead bot is visible while someone is still looking at the screen. */
export const STALE_AFTER_MS = 30_000;

/** How often the strip re-checks the record's age while a scan is running. */
const TICK_MS = 2_000;

type Mode = 'hidden' | 'indeterminate' | 'active' | 'stalled' | 'complete';

/** The bot's phase names are domain vocabulary, not display text. */
const STAGE_LABELS: Record<string, string> = {
  'starting': 'Starting',
  'crawling data': 'Fetching data',
  'analyzing': 'Analysing',
  'building alerts': 'Building alerts',
};

/**
 * The scan progress bar, over the top of the workspace.
 *
 * **Pure inputs, no store.** Like `sb-connection-status` beside it: the shell
 * owns the wiring and this owns the presentation, which is what lets every
 * state below be a two-line test instead of a store harness.
 *
 * **It never renders a percentage it was not given.** A running scan with no
 * record yet sweeps indeterminately rather than sitting at 0% -- "a scan has
 * started" and "a scan has started and achieved nothing" are different
 * claims, and only the first one is known at that moment. Same reasoning
 * behind the stalled state: a frozen bar that still looks live is the
 * failure this component exists to make impossible.
 *
 * **It does not reflow the page.** Absolutely positioned inside `.workspace`,
 * because an automatic scan runs every `SCAN_INTERVAL_MINUTES` all session
 * and a strip in the flow would shunt whatever is being read down 40px and
 * back, several times an hour.
 */
@Component({
  selector: 'sb-scan-progress',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (mode() !== 'hidden') {
      <div class="strip" [class.stalled]="mode() === 'stalled'"
           [class.complete]="mode() === 'complete'">
        <div class="track" role="progressbar" aria-label="Scan progress"
             aria-valuemin="0" aria-valuemax="100"
             [attr.aria-valuenow]="value()"
             [attr.aria-valuetext]="caption()">
          <div class="fill" [class.sweeping]="mode() === 'indeterminate'"
               [style.width.%]="value() ?? 100"></div>
        </div>
        <p class="caption" aria-live="polite">{{ caption() }}</p>
      </div>
    }
  `,
  styleUrl: './scan-progress.css',
})
export class ScanProgressStrip {
  readonly running = input.required<boolean>();
  readonly progress = input.required<ScanProgressRecord | null>();
  /** Pinned by the specs; null in the app, where wall-clock time is read. */
  readonly now = input<number | null>(null);

  /** Bumped on a timer so the staleness check below re-evaluates. Without it
   *  `Date.now()` is read once and a bot that goes quiet never looks stale --
   *  nothing else would push a new value in, because the thing that stopped
   *  IS the thing that pushes. */
  private readonly ticks = signal(0);
  private readonly lingering = signal(false);
  private wasRunning = false;
  private lingerTimer: ReturnType<typeof setTimeout> | null = null;
  private tickTimer: ReturnType<typeof setInterval> | null = null;

  protected readonly mode = computed<Mode>(() => {
    if (!this.running()) return this.lingering() ? 'complete' : 'hidden';

    const record = this.progress();
    if (record === null) return 'indeterminate';

    this.ticks();
    const at = Date.parse(record.at);
    // An unparseable timestamp is stale, never fresh -- the same call
    // `sb-freshness` makes, for the same reason.
    if (Number.isNaN(at)) return 'stalled';
    return this.clock() - at > STALE_AFTER_MS ? 'stalled' : 'active';
  });

  /** Null means "no percentage is known", which the template renders as a
   *  sweep rather than as a number. */
  protected readonly value = computed<number | null>(() => {
    const mode = this.mode();
    if (mode === 'complete') return 100;
    if (mode === 'indeterminate') return null;
    return this.progress()?.pct ?? null;
  });

  protected readonly caption = computed(() => {
    const record = this.progress();
    switch (this.mode()) {
      case 'complete':
        return 'Scan complete';
      case 'indeterminate':
        return 'Scanning…';
      case 'stalled': {
        const age = record ? this.clock() - Date.parse(record.at) : NaN;
        return Number.isFinite(age)
          ? `Scanning — no progress for ${Math.round(age / 1000)}s`
          : 'Scanning — no progress reported';
      }
      default:
        return record ? this.describe(record) : 'Scanning…';
    }
  });

  private describe(record: ScanProgressRecord): string {
    const stage = STAGE_LABELS[record.stage] ?? record.stage;
    // Every part is dropped rather than rendered empty, so the separators
    // never end up doubled or trailing.
    return [
      stage,
      record.total ? `${record.done}/${record.total}` : null,
      record.current_ticker,
    ].filter(Boolean).join(' · ');
  }

  private clock(): number {
    return this.now() ?? Date.now();
  }

  constructor() {
    const destroyRef = inject(DestroyRef);

    effect(() => {
      const running = this.running();
      untracked(() => {
        this.stopTimers();
        if (running) {
          this.lingering.set(false);
          this.tickTimer = setInterval(() => this.ticks.update((n) => n + 1), TICK_MS);
        } else if (this.wasRunning) {
          this.lingering.set(true);
          this.lingerTimer = setTimeout(() => this.lingering.set(false), LINGER_MS);
        }
        this.wasRunning = running;
      });
    });

    destroyRef.onDestroy(() => this.stopTimers());
  }

  private stopTimers(): void {
    if (this.lingerTimer !== null) clearTimeout(this.lingerTimer);
    if (this.tickTimer !== null) clearInterval(this.tickTimer);
    this.lingerTimer = this.tickTimer = null;
  }
}
