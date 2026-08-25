import { Directive, effect, ElementRef, inject, input } from '@angular/core';

/**
 * Flash a cell when its value actually changed.
 *
 * `tokens.css` already rules out the thing this must not become: a CARD flash
 * on every push event, which under real-time updates is a permanent flicker
 * rather than feedback. What it left open is motion scoped to the specific
 * cell whose number moved, which is the useful half.
 *
 * Two rules make it feedback instead of noise:
 *   - never on first render (everything is new on arrival — that is a strobe)
 *   - never when a re-render reports the same value (a re-render is not a
 *     change, and Angular does plenty of them)
 *
 * The colours are --pos-soft / --neg-soft, and `prefers-reduced-motion`
 * already zeroes the durations globally, so this needs no separate guard.
 */
@Directive({ selector: '[sbFlash]' })
export class Flash {
  readonly sbFlash = input.required<number | null | undefined>();

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private previous: number | null | undefined;
  private seen = false;

  constructor() {
    effect(() => {
      const next = this.sbFlash();
      const prior = this.previous;
      this.previous = next;

      if (!this.seen) { this.seen = true; return; }
      if (next === prior) return;
      if (typeof next !== 'number' || typeof prior !== 'number') return;

      const cls = next > prior ? 'flash-up' : 'flash-down';
      this.host.classList.remove('flash-up', 'flash-down');
      // Force a reflow so a second change within the animation restarts it
      // rather than being swallowed.
      void this.host.offsetWidth;
      this.host.classList.add(cls);
      this.host.addEventListener(
        'animationend',
        () => this.host.classList.remove(cls),
        { once: true },
      );
    });
  }
}
