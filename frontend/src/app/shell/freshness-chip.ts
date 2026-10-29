import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const MINUTE_MS = 60_000;

/**
 * How long ago the bot last completed a scan tick, at minute resolution --
 * v195 Phase 3. `format.ts`'s `age()` reads in hours ("<1h"), which is the
 * right unit for a plan's age and the wrong one for a bot that ticks every
 * few minutes. A time from the future (clock skew) reads "just now", never
 * a negative age. `null` when there is no readable time.
 */
export function scanAge(at: string | null, now: number): string | null {
  if (!at) return null;
  const then = Date.parse(at);
  if (Number.isNaN(then)) return null;
  const minutes = Math.floor(Math.max(0, now - then) / MINUTE_MS);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/**
 * Data freshness, in the top bar on every device -- v195 Phase 3.
 *
 * Scan health leaves the Risk page for System (§5.1), so this chip is what
 * keeps "is the bot still scanning" in view from every page, phone
 * included. Pure inputs, like `sb-connection-status` beside it: the shell
 * passes the time and its 30s clock, so every state is a two-line test.
 * It answers "when did the bot last finish a tick"; each panel's own
 * `sb-freshness` still answers "how old are these numbers".
 */
@Component({
  selector: 'sb-freshness-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [class.unknown]="age() === null">
      @if (age(); as text) {
        Scan <time [attr.datetime]="at()">{{ text }}</time>
      } @else {
        No scan yet
      }
    </span>
  `,
  styles: `
    :host { display: inline-flex; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--border);
      border-radius: var(--chip-radius);
      color: var(--text-muted);
      font-size: var(--text-chip);
      line-height: 1.4;
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    time { color: var(--text-secondary); }
    /* Before the first answer and when the bot never ticked: dashed, not
       warn-coloured, so every page load does not flash an alarm. */
    .chip.unknown { border-style: dashed; }
  `,
})
export class FreshnessChip {
  /** ISO time of the bot's last successful tick (or, failing that, its last
   *  heartbeat); `null` when it has never reported one. */
  readonly at = input<string | null>(null);
  /** The shell's clock, in ms. */
  readonly now = input.required<number>();

  protected readonly age = computed(() => scanAge(this.at(), this.now()));
}
