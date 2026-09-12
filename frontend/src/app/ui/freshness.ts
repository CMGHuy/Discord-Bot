import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * "as of 14:29:30" for one panel — spec v85 D30.
 *
 * `now` is an input purely so the spec can pin it; in the app it is left null
 * and `Date.now()` is read at render. This component deliberately does not tick
 * — a per-second timer per panel would be a dozen timers on Risk alone, and the
 * page's own refetch is what moves this value.
 *
 * An absent or unparseable timestamp is treated as **stale**, never as fresh.
 * The failure mode this guards is a panel that silently claims to be current
 * because its data arrived without a time on it.
 */
@Component({
  selector: 'sb-freshness',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="freshness" [class.stale]="stale()" aria-live="polite">
      @if (clock() === null) {
        age unknown
      } @else {
        as of {{ clock() }}@if (stale()) {<span class="flag"> · stale</span>}
      }
    </span>
  `,
  styles: `
    .freshness {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      color: var(--text-faint);
    }
    .stale { color: var(--warn); }
    .flag { font-style: italic; }
  `,
})
export class Freshness {
  readonly at = input.required<string | null>();
  readonly staleAfterSec = input<number>(900);
  readonly now = input<Date | null>(null);

  private readonly parsed = computed(() => {
    const raw = this.at();
    if (!raw) return null;
    const d = new Date(raw);
    return Number.isNaN(d.getTime()) ? null : d;
  });

  protected readonly clock = computed(() => {
    const d = this.parsed();
    if (d === null) return null;
    const raw = this.at();
    // A date-only ISO string ("2026-09-10", what a daily-bar `as_of` is --
    // there is no time-of-day to report) parses to UTC midnight. Slicing
    // out hh:mm:ss from that would print a bogus "00:00:00" regardless of
    // how fresh the underlying bar actually is. Print the date itself
    // instead of a fabricated time.
    if (raw !== null && /^\d{4}-\d{2}-\d{2}$/.test(raw)) return raw;
    return d.toISOString().slice(11, 19);
  });

  protected readonly stale = computed(() => {
    const d = this.parsed();
    if (d === null) return true;
    const now = this.now() ?? new Date();
    return (now.getTime() - d.getTime()) / 1000 > this.staleAfterSec();
  });
}
