import { Directive, effect, ElementRef, inject, input, untracked } from '@angular/core';

import { MotionStarts } from './motion/motion-starts';
import { MotionService } from './motion/motion.service';

/**
 * Flash a cell when its value actually changed.
 *
 * Under real-time push a CARD flash on every event is a permanent flicker
 * rather than feedback, so v168 still forbids re-animating anything on a push
 * (styles/motion.css, spec v168 §4). What stays open is motion scoped to the
 * specific cell whose number moved, which is the useful half.
 *
 * Two rules make it feedback instead of noise:
 *   - never on first render (everything is new on arrival — that is a strobe)
 *   - never when a re-render reports the same value (a re-render is not a
 *     change, and Angular does plenty of them)
 *
 * The tint is --pos-soft / --neg-soft fading over 1.1s, with the text briefly
 * in --flash-up-text / --flash-down-text (styles/motion.css). Motion = Off
 * scales that duration to zero, and an animation that never runs never fires
 * animationend to take the class off again, so under Off this adds nothing.
 * Reduced keeps the flash: it is colour, not movement. Every flash it starts
 * is recorded in MotionStarts for the no-replay gate.
 */
@Directive({ selector: '[sbFlash]' })
export class Flash {
  readonly sbFlash = input.required<number | null | undefined>();

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
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
      // Read untracked: a mode change is not a value change and must not
      // re-run this effect.
      if (untracked(() => this.motion.mode()) === 'off') return;

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
      this.starts.record('flash', 'flash');
    });
  }
}
