import { DestroyRef, Directive, ElementRef, NgZone, effect, inject, input, untracked } from '@angular/core';

import { ABSENT } from '../format';
import { MotionStartKind, MotionStarts } from './motion-starts';
import { MotionService } from './motion.service';
import { RouteEntryService } from './route-entry.service';

/** `--dur-count` (spec v168 §1), held in TS because frames are timed here. */
export const COUNT_MS = 900;

export function easeOutCubic(t: number): number {
  const rest = 1 - t;
  return 1 - rest * rest * rest;
}

type Format = (value: number) => string;
type CountKind = Extract<MotionStartKind, 'count-first' | 'count-change'>;

/**
 * Number count-up (spec v168 §3 #3). **Owns its host's text**: the host
 * element has no interpolation of its own, and this directive writes
 * `textContent`.
 *
 * The first value spends `RouteEntryService.claim(countKey)` whatever the
 * mode, and counts from 0 only when the claim was fresh and Motion is On, so
 * a refetch that re-creates the element shows the value at once. A later
 * change eases from the old value under On -- an intended push reaction,
 * scoped to the number that changed. Everything else writes the final text
 * synchronously, which is what keeps every spec under the Off test default
 * reading `.textContent` straight after one `detectChanges`.
 */
@Directive({ selector: '[sbCountUp]' })
export class CountUp {
  readonly sbCountUp = input.required<number | null>();
  readonly countFormat = input.required<Format>();
  readonly countKey = input.required<string>();
  readonly countAbsent = input<string>(ABSENT);

  private readonly host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly entry = inject(RouteEntryService);
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
  private readonly zone = inject(NgZone);
  private target: number | null = null;
  private claimed = false;
  private frame: number | null = null;

  constructor() {
    effect(() => {
      const value = this.sbCountUp();
      const format = this.countFormat();
      const absent = this.countAbsent();
      untracked(() => this.render(value, format, absent));
    });
    inject(DestroyRef).onDestroy(() => this.cancel());
  }

  private render(value: number | null, format: Format, absent: string): void {
    this.cancel();
    const previous = this.target;
    this.target = value;
    if (value === null) {
      this.write(absent);
      return;
    }
    const kind = this.kindFor(previous, value);
    if (kind === null || typeof requestAnimationFrame === 'undefined') {
      this.write(format(value));
      return;
    }
    this.play(kind === 'count-first' ? 0 : (previous ?? 0), value, format, kind);
  }

  /** The first value spends the claim; only On ever counts. */
  private kindFor(previous: number | null, value: number): CountKind | null {
    if (!this.claimed) {
      this.claimed = true;
      const fresh = this.entry.claim(this.countKey());
      return fresh && this.motion.full() ? 'count-first' : null;
    }
    if (previous === null || previous === value) return null;
    return this.motion.full() ? 'count-change' : null;
  }

  private play(from: number, to: number, format: Format, kind: CountKind): void {
    this.starts.record(kind, this.countKey());
    this.write(format(from));
    let start: number | null = null;
    const step = (now: number): void => {
      start ??= now;
      const t = Math.min(1, (now - start) / COUNT_MS);
      this.write(format(t < 1 ? from + (to - from) * easeOutCubic(t) : to));
      this.frame = t < 1 ? requestAnimationFrame(step) : null;
    };
    this.zone.runOutsideAngular(() => {
      this.frame = requestAnimationFrame(step);
    });
  }

  private cancel(): void {
    if (this.frame !== null && typeof cancelAnimationFrame !== 'undefined') cancelAnimationFrame(this.frame);
    this.frame = null;
  }

  private write(text: string): void {
    if (this.host.textContent !== text) this.host.textContent = text;
  }
}
